"""
Tahap 6: Backend API Lokal (FastAPI)

Membungkus seluruh pipeline jadi 1 endpoint yang bisa dipanggil dari
frontend nanti:

  Upload 2 file EEG (sesi 1 & 2) -> preprocessing -> segmentasi -> TF map
  -> prediksi model (EEGNet_TF) -> kalibrasi probabilitas -> uncertainty
  (MC Dropout) -> Grad-CAM -> JSON response

Cara jalankan:
  pip install fastapi uvicorn python-multipart torch scikit-learn numpy
              scipy mne joblib matplotlib
  uvicorn app:app --reload --port 8000

Cara test (setelah jalan):
  Buka http://127.0.0.1:8000/docs -- FastAPI otomatis kasih UI buat coba
  upload file langsung dari browser, tanpa perlu bikin frontend dulu.

CATATAN PENTING:
  - Wajib jalankan 06_compute_norm_stats.py dulu sebelum pakai API ini,
    supaya file norm_stats_fold*.npz tersedia.
  - Model yang dipakai: fold dengan AUC tertinggi dari training_summary.json
    (otomatis dipilih saat startup). Bisa dipaksa manual lewat FORCE_FOLD.
"""

import os
import io
import json
import base64
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

import uuid
from scipy.signal import butter, filtfilt, iirnotch, spectrogram
from scipy.interpolate import griddata
import mne

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
    KeepTogether,
)

mne.set_log_level("ERROR")

# ==============================================================================
# KONFIGURASI (harus identik dengan tahap 1-5)
# ==============================================================================
MODEL_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "model"
)

FS = 250
BANDPASS_LOW, BANDPASS_HIGH = 0.5, 45.0
NOTCH_FREQ = 50.0
WINDOW_SEC = 4
WINDOW_SIZE = WINDOW_SEC * FS
OVERLAP = 0.5   # dikonfirmasi sama dengan overlap yang dipakai saat generate data training
STEP_SIZE = int(WINDOW_SIZE * (1 - OVERLAP))
MIN_SAMPLES = 5 * 60 * FS
N_ICA_COMPONENTS = 16

STFT_NPERSEG, STFT_NOVERLAP = 64, 48
FREQ_MIN, FREQ_MAX = 0.5, 45.0

D_MULT, F1, F2, DROPOUT_RATE = 2, 4, 8, 0.5
MC_DROPOUT_PASSES = 30

FORCE_FOLD = None   # isi angka 1-9 kalau mau paksa fold tertentu, None = auto pilih terbaik

GRADCAM_OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "gradcam_output",
    "api_predictions"
)

DEVICE = "cpu"  # inference 1 pasien tidak perlu GPU

CHANNEL_NAMES = [
    "Fp1", "Fp2", "C3", "C4", "T5", "T6", "O1", "O2",
    "F3", "F4", "F7", "F8", "T3", "T4", "P3", "P4",
]
CHANNEL_COORDS = {
    "Fp1": (-0.35, 0.80), "Fp2": (0.35, 0.80),
    "F7": (-0.85, 0.40), "F3": (-0.40, 0.40), "F4": (0.40, 0.40), "F8": (0.85, 0.40),
    "T3": (-1.00, 0.00), "C3": (-0.50, 0.00), "C4": (0.50, 0.00), "T4": (1.00, 0.00),
    "T5": (-0.85, -0.40), "P3": (-0.40, -0.40), "P4": (0.40, -0.40), "T6": (0.85, -0.40),
    "O1": (-0.35, -0.80), "O2": (0.35, -0.80),
}


# ==============================================================================
# MODEL (identik dengan tahap 3-5)
# ==============================================================================
class EEGNet_TF(nn.Module):
    def __init__(self, n_channels=16, n_freq=11, n_time=59, n_classes=2,
                 d_mult=D_MULT, f1=F1, f2=F2, dropout=DROPOUT_RATE):
        super().__init__()
        self.n_channels = n_channels
        self.depthwise1 = nn.Conv2d(n_channels, n_channels * d_mult, kernel_size=(3, 3),
                                     padding=1, groups=n_channels, bias=False)
        self.bn1 = nn.BatchNorm2d(n_channels * d_mult)
        self.pointwise1 = nn.Conv2d(n_channels * d_mult, f1, kernel_size=(1, 1), bias=False)
        self.bn2 = nn.BatchNorm2d(f1)
        self.elu1 = nn.ELU()
        self.pool1 = nn.AvgPool2d((1, 2))
        self.drop1 = nn.Dropout(dropout)
        self.depthwise2 = nn.Conv2d(f1, f1, kernel_size=(3, 3), padding=1, groups=f1, bias=False)
        self.pointwise2 = nn.Conv2d(f1, f2, kernel_size=(1, 1), bias=False)
        self.bn3 = nn.BatchNorm2d(f2)
        self.elu2 = nn.ELU()
        self.pool2 = nn.AvgPool2d((2, 2))
        self.drop2 = nn.Dropout(dropout)
        with torch.no_grad():
            dummy = torch.zeros(1, n_channels, n_freq, n_time)
            out = self._forward_features(dummy)
            flat_dim = out.view(1, -1).shape[1]
        self.classifier = nn.Linear(flat_dim, n_classes)

    def _forward_features(self, x):
        x = self.depthwise1(x); x = self.bn1(x)
        x = self.pointwise1(x); x = self.bn2(x); x = self.elu1(x)
        x = self.pool1(x); x = self.drop1(x)
        x = self.depthwise2(x); x = self.pointwise2(x); x = self.bn3(x)
        x = self.elu2(x); x = self.pool2(x); x = self.drop2(x)
        return x

    def forward(self, x_tf):
        feats = self._forward_features(x_tf)
        return self.classifier(feats.view(feats.size(0), -1))


class GradCAM:
    def __init__(self, model, target_layer):
        self.model = model
        self.activations = None
        self.gradients = None
        target_layer.register_forward_hook(self._save_activation)
        target_layer.register_full_backward_hook(self._save_gradient)

    def _save_activation(self, module, input, output):
        self.activations = output

    def _save_gradient(self, module, grad_input, grad_output):
        self.gradients = grad_output[0]

    def generate(self, x, class_idx=None):
        self.model.zero_grad()
        logits = self.model(x)
        if class_idx is None:
            class_idx = logits.argmax(dim=1)
        score = logits[torch.arange(len(x)), class_idx].sum()
        score.backward()
        weights = self.gradients.mean(dim=(2, 3), keepdim=True)
        cam = (weights * self.activations).sum(dim=1)
        cam = torch.relu(cam)
        cam_flat = cam.view(cam.size(0), -1)
        cam_min = cam_flat.min(dim=1, keepdim=True)[0].unsqueeze(-1)
        cam_max = cam_flat.max(dim=1, keepdim=True)[0].unsqueeze(-1)
        cam = (cam - cam_min) / (cam_max - cam_min + 1e-8)
        return cam.detach().cpu().numpy(), class_idx.detach().cpu().numpy(), \
               torch.softmax(logits, dim=1).detach().cpu().numpy()


def enable_mc_dropout(model):
    for m in model.modules():
        if isinstance(m, nn.Dropout):
            m.train()


def compute_channel_saliency(model, x_batch, class_idx):
    x = x_batch.clone().detach().requires_grad_(True)
    model.zero_grad()
    logits = model(x)
    score = logits[torch.arange(len(x), device=x.device), class_idx].sum()
    score.backward()
    saliency = x.grad.detach().abs().mean(dim=(2, 3))
    cmin = saliency.min(dim=1, keepdim=True)[0]
    cmax = saliency.max(dim=1, keepdim=True)[0]
    saliency = (saliency - cmin) / (cmax - cmin + 1e-8)
    return saliency.cpu().numpy()


def axis_extent(axis):
    if len(axis) < 2:
        return float(axis[0] - 0.5), float(axis[0] + 0.5)
    half_step = float(axis[1] - axis[0]) / 2.0
    return float(axis[0] - half_step), float(axis[-1] + half_step)


def topography_png_base64(channel_values, title):
    fig, ax = plt.subplots(figsize=(5, 5))
    head = plt.Circle((0, 0), 1.05, fill=False, color="black", linewidth=1.5)
    ax.add_patch(head)
    ax.plot([-0.1, 0, 0.1], [1.02, 1.18, 1.02], color="black", linewidth=1.5)
    for side in (-1, 1):
        ax.add_patch(plt.Circle((side * 1.05, 0), 0.08, fill=False, color="black", linewidth=1.2))

    names = list(channel_values.keys())
    xs = np.array([CHANNEL_COORDS[name][0] for name in names])
    ys = np.array([CHANNEL_COORDS[name][1] for name in names])
    vals = np.array([channel_values[name] for name in names])
    grid_x, grid_y = np.mgrid[-1:1:200j, -1:1:200j]
    grid_z = griddata((xs, ys), vals, (grid_x, grid_y), method="cubic")
    grid_z[grid_x**2 + grid_y**2 > 1.0] = np.nan

    im = ax.contourf(grid_x, grid_y, grid_z, levels=20, cmap="RdYlBu_r", vmin=0, vmax=1)
    plt.colorbar(im, ax=ax, label="Kontribusi (0-1)", shrink=0.75)
    ax.scatter(xs, ys, c="black", s=18, zorder=5)
    for name, x_pos, y_pos in zip(names, xs, ys):
        ax.annotate(name, (x_pos, y_pos), textcoords="offset points", xytext=(0, 7),
                    ha="center", fontsize=8, fontweight="bold")
    ax.set_xlim(-1.3, 1.3)
    ax.set_ylim(-1.3, 1.3)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(title, fontsize=12, fontweight="bold")
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


# ==============================================================================
# PREPROCESSING (identik dengan tahap 1-2)
# ==============================================================================
def read_eeg_file_from_bytes(file_bytes: bytes, filename: str) -> pd.DataFrame:
    try:
        buf = io.BytesIO(file_bytes)
        if filename.lower().endswith(".txt"):
            df = pd.read_csv(buf, sep=",", skiprows=4, header=0, on_bad_lines="skip")
        else:
            df = pd.read_csv(buf, sep=",", header=0, on_bad_lines="skip")
            if df.shape[1] < 9:
                buf.seek(0)
                df = pd.read_csv(buf, sep="\t", header=0, on_bad_lines="skip")
        if df.shape[1] < 9:
            return pd.DataFrame()
        exg = df.iloc[:, 1:9].apply(pd.to_numeric, errors="coerce").dropna(how="all").reset_index(drop=True)
        return exg
    except Exception:
        return pd.DataFrame()


def apply_bandpass_notch(raw_16ch, fs):
    nyq = 0.5 * fs
    b_bp, a_bp = butter(4, [BANDPASS_LOW / nyq, BANDPASS_HIGH / nyq], btype="band")
    filtered = filtfilt(b_bp, a_bp, raw_16ch, axis=0)
    b_notch, a_notch = iirnotch(NOTCH_FREQ / nyq, Q=30)
    return filtfilt(b_notch, a_notch, filtered, axis=0)


def run_ica_artifact_removal(raw_16ch, fs):
    ch_names = [f"ch{i+1}" for i in range(raw_16ch.shape[1])]
    info = mne.create_info(ch_names=ch_names, sfreq=fs, ch_types="eeg")
    raw_mne = mne.io.RawArray(raw_16ch.T, info)
    ica = mne.preprocessing.ICA(n_components=N_ICA_COMPONENTS, random_state=42, max_iter="auto")
    ica.fit(raw_mne)
    sources = ica.get_sources(raw_mne).get_data()
    kurt = pd.DataFrame(sources.T).kurt().values
    ica.exclude = np.where(np.abs(kurt) > 5)[0].tolist()
    raw_clean = ica.apply(raw_mne.copy())
    return raw_clean.get_data().T


def segment_signal(clean_16ch, window_size, step_size):
    segments = []
    for start in range(0, clean_16ch.shape[0] - window_size + 1, step_size):
        segments.append(clean_16ch[start:start + window_size, :])
    return segments


def segment_to_tf(segment):
    tf_channels = []
    freq_used = None
    time_used = None
    for ch in range(segment.shape[1]):
        f, t, Sxx = spectrogram(segment[:, ch], fs=FS, nperseg=STFT_NPERSEG, noverlap=STFT_NOVERLAP)
        mask = (f >= FREQ_MIN) & (f <= FREQ_MAX)
        Sxx = np.log1p(Sxx[mask, :])
        tf_channels.append(Sxx)
        freq_used = f[mask]
        time_used = t
    return np.stack(tf_channels, axis=0), freq_used, time_used


# ==============================================================================
# LOAD MODEL & KALIBRATOR SEKALI SAAT STARTUP
# ==============================================================================
def pick_best_fold():
    summary_path = os.path.join(MODEL_DIR, "training_summary.json")
    if FORCE_FOLD is not None:
        return FORCE_FOLD
    if not os.path.exists(summary_path):
        return 1
    with open(summary_path) as f:
        summary = json.load(f)
    per_fold = summary.get("per_fold", [])
    if not per_fold:
        return 1
    best = max(per_fold, key=lambda r: r.get("auc", 0))
    return best["fold"]


BEST_FOLD = pick_best_fold()
print(f"[startup] Menggunakan model dari fold {BEST_FOLD} (AUC terbaik)")

_model = EEGNet_TF().to(DEVICE)
_model.load_state_dict(torch.load(os.path.join(MODEL_DIR, f"eegnet_tf_fold{BEST_FOLD}.pt"), map_location=DEVICE))
_model.eval()
_gradcam = GradCAM(_model, _model.elu1)

_calibrator = joblib.load(os.path.join(MODEL_DIR, f"calibrator_isotonic_fold{BEST_FOLD}.pkl"))

_norm_stats_path = os.path.join(MODEL_DIR, f"norm_stats_fold{BEST_FOLD}.npz")
if not os.path.exists(_norm_stats_path):
    raise RuntimeError(
        f"File {_norm_stats_path} tidak ditemukan. "
        f"Jalankan 06_compute_norm_stats.py dulu sebelum start API ini."
    )
_norm = np.load(_norm_stats_path)
_norm_mean, _norm_std = _norm["mean"], _norm["std"]

# Threshold uncertainty: pakai hasil analisis persentil (08_uncertainty_distribution.py)
# kalau tersedia, fallback ke angka default kalau belum dijalankan
_uncertainty_thresholds_path = os.path.join(MODEL_DIR, "uncertainty_thresholds.json")
if os.path.exists(_uncertainty_thresholds_path):
    with open(_uncertainty_thresholds_path) as f:
        _ut = json.load(f)
    UNCERTAINTY_LOW_THRESHOLD = _ut["rendah_sedang_threshold"]
    UNCERTAINTY_HIGH_THRESHOLD = _ut["sedang_tinggi_threshold"]
    print(f"[startup] Threshold uncertainty dari data asli: "
          f"RENDAH<{UNCERTAINTY_LOW_THRESHOLD:.4f}<=SEDANG<{UNCERTAINTY_HIGH_THRESHOLD:.4f}<=TINGGI")
else:
    UNCERTAINTY_LOW_THRESHOLD = 0.05
    UNCERTAINTY_HIGH_THRESHOLD = 0.15
    print("[startup] uncertainty_thresholds.json tidak ditemukan, pakai default 0.05/0.15. "
          "Jalankan 08_uncertainty_distribution.py untuk threshold berbasis data asli.")


# ==============================================================================
# FASTAPI APP
# ==============================================================================
app = FastAPI(
    title="NeuroScreen CDSS API"
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


os.makedirs(GRADCAM_OUTPUT_DIR, exist_ok=True)


@app.get("/health")
def health():
    return {"status": "ok", "model_fold_used": BEST_FOLD, "device": DEVICE}


@app.get("/gradcam/{filename}")
def get_gradcam_image(filename: str):
    filepath = os.path.join(GRADCAM_OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(404, "File tidak ditemukan.")
    return FileResponse(filepath, media_type="image/png")

# ==============================================================================
# PDF REPORT
# ==============================================================================

def _decode_base64_png(value):
    if not value:
        return None

    try:
        return io.BytesIO(
            base64.b64decode(value)
        )
    except Exception:
        return None


def _safe_text(value, default="—"):
    if value is None:
        return default

    text = str(value).strip()

    return text if text else default


@app.post("/report/pdf")
async def generate_pdf_report(payload: dict = Body(...)):

    patient = payload.get("patient") or {}
    result = payload.get("result") or {}

    # --------------------------------------------------------------------------
    # DATA PASIEN
    # --------------------------------------------------------------------------

    patient_id = _safe_text(
        patient.get("id"),
        "Pasien"
    )

    age = _safe_text(
        patient.get("age")
    )

    gender_code = patient.get("gender")

    if gender_code == "L":
        gender = "Laki-laki"
    elif gender_code == "P":
        gender = "Perempuan"
    else:
        gender = "Tidak tersedia"

    record_date = _safe_text(
        patient.get("recordDate")
    )

    # --------------------------------------------------------------------------
    # HASIL MODEL
    # --------------------------------------------------------------------------

    prediction = _safe_text(
        result.get("prediction")
    )

    probability_calibrated = float(
        result.get(
            "probability_asd_calibrated",
            0
        )
    )

    probability_raw = float(
        result.get(
            "probability_asd_raw_mean",
            0
        )
    )

    uncertainty = float(
        result.get(
            "uncertainty",
            0
        )
    )

    uncertainty_level = _safe_text(
        result.get("uncertainty_level")
    )

    n_segments = result.get(
        "n_segments_analyzed",
        "—"
    )

    mc_passes = result.get(
        "mc_dropout_passes",
        30
    )

    # Confidence terhadap kelas yang diprediksi
    model_confidence = (
        probability_calibrated
        if prediction == "ASD"
        else 1 - probability_calibrated
    )

    # --------------------------------------------------------------------------
    # PDF
    # --------------------------------------------------------------------------

    pdf_buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=f"Laporan Skrining NeuroScreen - {patient_id}",
        author="NeuroScreen — Prototipe CDSS, RKI USK 2026",
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "NeuroScreenTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        alignment=TA_CENTER,
        spaceAfter=6,
    )

    subtitle_style = ParagraphStyle(
        "NeuroScreenSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#666666"),
        spaceAfter=14,
    )

    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        spaceBefore=10,
        spaceAfter=7,
    )

    normal_style = ParagraphStyle(
        "NormalReport",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
    )

    small_style = ParagraphStyle(
        "SmallReport",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#555555"),
    )

    disclaimer_style = ParagraphStyle(
        "Disclaimer",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#444444"),
    )

    story = []

    # --------------------------------------------------------------------------
    # HEADER
    # --------------------------------------------------------------------------

    story.append(
        Paragraph(
            "NeuroScreen",
            title_style
        )
    )

    story.append(
        Paragraph(
            "Laporan Hasil Skrining EEG",
            subtitle_style
        )
    )

    # --------------------------------------------------------------------------
    # IDENTITAS PASIEN
    # --------------------------------------------------------------------------

    story.append(
        Paragraph(
            "1. Data Pasien",
            heading_style
        )
    )

    patient_table = Table(
        [
            ["Nama / ID Pasien", patient_id],
            ["Usia", f"{age} tahun"],
            ["Jenis Kelamin", gender],
            ["Tanggal Rekaman", record_date],
        ],
        colWidths=[5 * cm, 11 * cm],
    )

    patient_table.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (0, -1),
                colors.HexColor("#F2F2F2")
            ),
            (
                "TEXTCOLOR",
                (0, 0),
                (-1, -1),
                colors.HexColor("#222222")
            ),
            (
                "FONTNAME",
                (0, 0),
                (0, -1),
                "Helvetica-Bold"
            ),
            (
                "FONTNAME",
                (1, 0),
                (1, -1),
                "Helvetica"
            ),
            (
                "FONTSIZE",
                (0, 0),
                (-1, -1),
                9
            ),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.4,
                colors.HexColor("#DDDDDD")
            ),
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "MIDDLE"
            ),
            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                6
            ),
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                6
            ),
        ])
    )

    story.append(patient_table)
    story.append(Spacer(1, 10))

    # --------------------------------------------------------------------------
    # HASIL SKRINING
    # --------------------------------------------------------------------------

    story.append(
        Paragraph(
            "2. Hasil Skrining",
            heading_style
        )
    )

    result_table = Table(
        [
            ["Hasil Klasifikasi", prediction],
            [
                "Model Confidence",
                f"{model_confidence * 100:.1f}%"
            ],
            [
                "Probabilitas ASD setelah kalibrasi",
                f"{probability_calibrated:.4f}"
            ],
            [
                "Probabilitas ASD sebelum kalibrasi",
                f"{probability_raw:.4f}"
            ],
            [
                "Tingkat Ketidakpastian",
                uncertainty_level
            ],
            [
                "Nilai Ketidakpastian",
                f"{uncertainty:.4f}"
            ],
            [
                "Segmen Dianalisis",
                str(n_segments)
            ],
            [
                "Monte Carlo Dropout",
                f"{mc_passes} pass"
            ],
        ],
        colWidths=[7 * cm, 9 * cm],
    )

    result_table.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (0, -1),
                colors.HexColor("#F2F2F2")
            ),
            (
                "FONTNAME",
                (0, 0),
                (0, -1),
                "Helvetica-Bold"
            ),
            (
                "FONTNAME",
                (1, 0),
                (1, -1),
                "Helvetica"
            ),
            (
                "FONTSIZE",
                (0, 0),
                (-1, -1),
                9
            ),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.4,
                colors.HexColor("#DDDDDD")
            ),
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "MIDDLE"
            ),
            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                6
            ),
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                6
            ),
        ])
    )

    story.append(result_table)
    story.append(Spacer(1, 8))

    # --------------------------------------------------------------------------
    # EXPLAINABLE AI
    # --------------------------------------------------------------------------

    story.append(
        Paragraph(
            "3. Explainable AI",
            heading_style
        )
    )

    story.append(
        Paragraph(
            "Visualisasi berikut memberikan informasi tambahan "
            "mengenai area time-frequency dan distribusi kontribusi "
            "channel EEG yang berkaitan dengan keputusan model.",
            normal_style
        )
    )

    story.append(Spacer(1, 8))

    # --------------------------------------------------------------------------
    # GRAD-CAM
    # --------------------------------------------------------------------------

    gradcam_stream = _decode_base64_png(
        result.get(
            "gradcam_image_base64_png"
        )
    )

    if gradcam_stream:

        story.append(
            Paragraph(
                "Grad-CAM — Frekuensi × Waktu",
                heading_style
            )
        )

        gradcam_image = Image(
            gradcam_stream,
            width=15.5 * cm,
            height=10.3 * cm,
        )

        gradcam_image.hAlign = "CENTER"

        story.append(gradcam_image)

        story.append(Spacer(1, 4))

        story.append(
            Paragraph(
                "Grad-CAM menampilkan area time-frequency "
                "yang paling berkontribusi terhadap keputusan model.",
                small_style
            )
        )

    else:

        story.append(
            Paragraph(
                "Visualisasi Grad-CAM tidak tersedia "
                "untuk hasil ini.",
                small_style
            )
        )

    story.append(Spacer(1, 8))

    # --------------------------------------------------------------------------
    # TOPOGRAPHY
    # --------------------------------------------------------------------------

    topo_stream = _decode_base64_png(
        result.get(
            "topography_image_base64_png"
        )
    )

    if topo_stream:

        story.append(
            Paragraph(
                "Kontribusi Channel EEG",
                heading_style
            )
        )

        topo_image = Image(
            topo_stream,
            width=12 * cm,
            height=12 * cm,
        )

        topo_image.hAlign = "CENTER"

        story.append(topo_image)

    else:

        story.append(
            Paragraph(
                "Visualisasi kontribusi channel EEG "
                "tidak tersedia untuk hasil ini.",
                small_style
            )
        )

    # --------------------------------------------------------------------------
    # TOP CHANNELS
    # --------------------------------------------------------------------------

    top_channels = result.get(
        "top_channels"
    ) or []

    if top_channels:

        story.append(
            Paragraph(
                "Channel dengan kontribusi tertinggi",
                heading_style
            )
        )

        channel_rows = [
            ["Peringkat", "Channel", "Kontribusi"]
        ]

        for index, item in enumerate(
            top_channels[:5],
            start=1
        ):

            channel_rows.append([
                str(index),
                _safe_text(
                    item.get("channel")
                ),
                f"{float(item.get('contribution', 0)):.2f}",
            ])

        channel_table = Table(
            channel_rows,
            colWidths=[
                3 * cm,
                6 * cm,
                7 * cm
            ],
        )

        channel_table.setStyle(
            TableStyle([
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#F2F2F2")
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (-1, 0),
                    "Helvetica-Bold"
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.4,
                    colors.HexColor("#DDDDDD")
                ),
                (
                    "ALIGN",
                    (0, 0),
                    (-1, -1),
                    "CENTER"
                ),
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    9
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    5
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    5
                ),
            ])
        )

        story.append(channel_table)

    # --------------------------------------------------------------------------
    # DISCLAIMER
    # --------------------------------------------------------------------------

    story.append(
        Spacer(1, 14)
    )

    story.append(
        Paragraph(
            "<b>Catatan penting:</b> Hasil ini adalah alat bantu "
            "skrining, bukan diagnosis klinis. Keputusan akhir "
            "tetap berada pada profesional medis yang menangani pasien.",
            disclaimer_style
        )
    )

    story.append(Spacer(1, 8))

    story.append(
        Paragraph(
            "NeuroScreen — Prototipe CDSS, RKI USK 2026",
            small_style
        )
    )

    doc.build(story)

    pdf_bytes = pdf_buffer.getvalue()

    filename = (
        f"NeuroScreen_Laporan_{patient_id}"
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
                f'attachment; filename="{filename}.pdf"'
        },
    )
@app.post("/predict")
async def predict(session1: UploadFile = File(...), session2: UploadFile = File(...)):
    bytes1 = await session1.read()
    bytes2 = await session2.read()

    df1 = read_eeg_file_from_bytes(bytes1, session1.filename)
    df2 = read_eeg_file_from_bytes(bytes2, session2.filename)
    if df1.empty or df2.empty:
        raise HTTPException(400, "Salah satu file gagal dibaca atau formatnya tidak sesuai.")

    min_len = min(len(df1), len(df2))
    if min_len < WINDOW_SIZE:
        raise HTTPException(400, "Durasi rekaman terlalu pendek (minimal 4 detik setelah digabung).")

    raw_16ch = np.hstack((df1.values[:min_len, :], df2.values[:min_len, :]))
    filtered = apply_bandpass_notch(raw_16ch, FS)
    clean = run_ica_artifact_removal(filtered, FS)
    segments = segment_signal(clean, WINDOW_SIZE, STEP_SIZE)

    if len(segments) == 0:
        raise HTTPException(400, "Tidak ada segment valid yang dihasilkan dari rekaman ini.")

    tf_maps, freq_axis, time_axis = [], None, None
    for seg in segments:
        tf, freq_axis, time_axis = segment_to_tf(seg)
        tf_maps.append(tf)
    X_tf = np.array(tf_maps).astype(np.float32)  # (n_segment, 16, n_freq, n_time)
    X_tf_norm = ((X_tf - _norm_mean) / _norm_std).astype(np.float32)

    x_tensor = torch.tensor(X_tf_norm, dtype=torch.float32).to(DEVICE)

    # --- Prediksi mentah (dropout OFF) per segment ---
    _model.eval()
    with torch.no_grad():
        logits = _model(x_tensor)
        probs_raw = torch.softmax(logits, dim=1)[:, 1].cpu().numpy()  # prob kelas ASD

    # --- Kalibrasi ---
    probs_calibrated = _calibrator.predict(probs_raw)

    # --- Uncertainty (MC Dropout) ---
    enable_mc_dropout(_model)
    mc_probs = []
    with torch.no_grad():
        for _ in range(MC_DROPOUT_PASSES):
            logits_mc = _model(x_tensor)
            mc_probs.append(torch.softmax(logits_mc, dim=1)[:, 1].cpu().numpy())
    mc_probs = np.stack(mc_probs, axis=0)
    uncertainty_per_segment = mc_probs.std(axis=0)
    _model.eval()

    # --- Agregasi ke level pasien (rata-rata semua segment) ---
    final_prob_calibrated = float(probs_calibrated.mean())
    final_uncertainty = float(uncertainty_per_segment.mean())
    final_label = "ASD" if final_prob_calibrated >= 0.5 else "Normal"

    if final_uncertainty < UNCERTAINTY_LOW_THRESHOLD:
        uncertainty_level = "RENDAH"
    elif final_uncertainty < UNCERTAINTY_HIGH_THRESHOLD:
        uncertainty_level = "SEDANG"
    else:
        uncertainty_level = "TINGGI"

    # --- Grad-CAM untuk segment paling representatif (prob paling dekat rata-rata) ---
    rep_idx = int(np.argmin(np.abs(probs_calibrated - final_prob_calibrated)))
    x_rep = x_tensor[rep_idx:rep_idx+1]
    cam, pred_cls, _ = _gradcam.generate(x_rep, class_idx=torch.tensor([1 if final_label == "ASD" else 0]))
    cam = cam[0]

    fig, ax = plt.subplots(figsize=(6, 4))
    tf_mean_display = X_tf_norm[rep_idx].mean(axis=0)
    t0, t1 = axis_extent(time_axis)
    f0, f1 = axis_extent(freq_axis)
    extent = [t0, t1, f0, f1]
    ax.imshow(tf_mean_display, aspect="auto", origin="lower", cmap="gray", extent=extent)
    im = ax.imshow(cam, aspect="auto", origin="lower", cmap="jet", alpha=0.5, extent=extent)
    ax.set_xlabel("Waktu (s)")
    ax.set_ylabel("Frekuensi (Hz)")

    # Gunakan label frekuensi yang lebih sederhana dan mudah dibaca
    ax.set_yticks(freq_axis)
    ax.set_yticklabels([f"{float(f):.0f}" for f in freq_axis])

    ax.set_title(f"Grad-CAM (segment representatif) - Prediksi: {final_label}")
    plt.colorbar(im, ax=ax)
    plt.tight_layout()

    # --- Simpan ke file (bisa dibuka langsung lewat browser via endpoint /gradcam/{filename}) ---
    gradcam_filename = f"gradcam_{uuid.uuid4().hex[:12]}.png"
    gradcam_filepath = os.path.join(GRADCAM_OUTPUT_DIR, gradcam_filename)
    plt.savefig(gradcam_filepath, format="png", dpi=100)

    # --- Tetap sediakan base64 juga (buat frontend React nanti, tanpa perlu request kedua) ---
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    gradcam_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    # --- Kontribusi channel EEG untuk segment representatif ---
    target_class = torch.tensor([1 if final_label == "ASD" else 0], dtype=torch.long, device=DEVICE)
    saliency = compute_channel_saliency(_model, x_rep, target_class)[0]
    channel_contributions = {name: round(float(saliency[i]), 4) for i, name in enumerate(CHANNEL_NAMES)}
    top_channels = [
        {"channel": name, "contribution": value}
        for name, value in sorted(channel_contributions.items(), key=lambda kv: kv[1], reverse=True)[:5]
    ]
    topography_base64 = topography_png_base64(
        channel_contributions, f"Kontribusi Channel - Prediksi: {final_label}"
    )

    return {
        "prediction": final_label,
        "probability_asd_calibrated": round(final_prob_calibrated, 4),
        "probability_asd_raw_mean": round(float(probs_raw.mean()), 4),
        "uncertainty": round(final_uncertainty, 4),
        "uncertainty_level": uncertainty_level,
        "uncertainty_thresholds": {
            "low_to_medium": round(float(UNCERTAINTY_LOW_THRESHOLD), 4),
            "medium_to_high": round(float(UNCERTAINTY_HIGH_THRESHOLD), 4),
        },
        "mc_dropout_passes": MC_DROPOUT_PASSES,
        "n_segments_analyzed": len(segments),
        "representative_segment_index": rep_idx,
        "frequency_axis_hz": [round(float(v), 5) for v in freq_axis],
        "time_axis_seconds": [round(float(v), 5) for v in time_axis],
        "gradcam_image_url": f"/gradcam/{gradcam_filename}",
        "gradcam_image_base64_png": gradcam_base64,
        "channel_contributions": channel_contributions,
        "top_channels": top_channels,
        "topography_image_base64_png": topography_base64,
        "disclaimer": "Hasil ini adalah alat bantu skrining, BUKAN diagnosis klinis. "
                       "Konsultasikan dengan profesional (dokter/psikolog) untuk evaluasi lebih lanjut.",
    }