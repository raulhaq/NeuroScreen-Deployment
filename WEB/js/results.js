// NeuroScreen — Results page behavior

const API_BASE_URL =
  'http://127.0.0.1:8000';


function setResultsProgress() {

  const steps =
    document.querySelectorAll('.progress-step');

  steps.forEach((item, index) => {

    item.classList.remove(
      'active',
      'done'
    );

    if (index === 0) {
      item.classList.add('done');
    }

    if (index === 1) {
      item.classList.add('active');
    }

  });

}


function formatDate(dateString) {

  if (!dateString) {
    return 'tanggal tidak tersedia';
  }

  const date =
    new Date(`${dateString}T00:00:00`);

  return new Intl.DateTimeFormat(
    'id-ID',
    {
      day: 'numeric',
      month: 'short',
      year: 'numeric'
    }
  ).format(date);

}


function uncertaintyText(level, value) {

  const descriptions = {

    RENDAH:
      'Variasi prediksi antar Monte Carlo Dropout pass rendah.',

    SEDANG:
      'Variasi prediksi berada pada tingkat sedang; hasil dapat ditinjau bersama informasi klinis lainnya.',

    TINGGI:
      'Variasi prediksi antar Monte Carlo Dropout pass tinggi; diperlukan kehati-hatian dalam interpretasi.'

  };


  return `Nilai ${Number(value).toFixed(4)} — ${
    descriptions[level] ||
    'tingkat ketidakpastian tersedia.'
  }`;

}



function showNoResult() {

  document.querySelector('.result-hero').innerHTML = `

    <div
      class="empty-state"
      style="grid-column: 1 / -1;"
    >

      <h2>
        Belum ada hasil analisis
      </h2>

      <p>
        Halaman ini memerlukan hasil dari proses
        unggah EEG. Kembali ke halaman skrining
        untuk menjalankan analisis.
      </p>

      <button
        class="btn-download"
        type="button"
        onclick="window.location.href='Upload.html'"
      >
        Kembali ke unggah EEG
      </button>

    </div>

  `;


  document.querySelector(
    '.section-tag'
  ).style.display = 'none';


  document.querySelector(
    '.section-tag'
  ).nextElementSibling.style.display = 'none';


  document.querySelector(
    '.section-desc'
  ).style.display = 'none';


  document.querySelector(
    '.xai-grid'
  ).style.display = 'none';

}


const newScreeningBtn =
  document.getElementById('newScreeningBtn');

if (newScreeningBtn) {

  newScreeningBtn.addEventListener(
    'click',
    () => {

      sessionStorage.removeItem(
        'neuroscreenPatient'
      );

      sessionStorage.removeItem(
        'neuroscreenResult'
      );

      window.location.href =
        'Upload.html';

    }
  );

}
const patient =
  JSON.parse(
    sessionStorage.getItem(
      'neuroscreenPatient'
    ) || 'null'
  );


const result =
  JSON.parse(
    sessionStorage.getItem(
      'neuroscreenResult'
    ) || 'null'
  );



if (!patient || !result) {

  showNoResult();

}
else {

  setResultsProgress();


  /*
  ================================================
  PREDICTION
  ================================================
  */

  const isASD =
    result.prediction === 'ASD';



  document.getElementById(
    'resultTitle'
  ).textContent =
    `Hasil Skrining — ${
      patient.id || 'Pasien'
    }`;



  document.getElementById(
    'patientMeta'
  ).textContent =

    `Usia ${patient.age} tahun · ${
      patient.gender === 'L'
        ? 'Laki-laki'
        : patient.gender === 'P'
          ? 'Perempuan'
          : 'Jenis kelamin tidak tersedia'
    } · Rekaman ${
      formatDate(patient.recordDate)
    } · ${
      result.n_segments_analyzed
    } segmen dianalisis`;



  /*
  ================================================
  MODEL CONFIDENCE
  Confidence terhadap prediksi akhir
  ================================================
  */

  const probabilityASD =
    Number(
      result.probability_asd_calibrated
    );



  const modelConfidence =
    isASD
      ? probabilityASD
      : (1 - probabilityASD);



  document.getElementById(
    'scoreValue'
  ).textContent =

    `${(
      modelConfidence * 100
    ).toFixed(1)}%`;



  const scoreTag =
    document.getElementById(
      'scoreTag'
    );



  scoreTag.textContent =
    isASD
      ? 'Indikasi ASD'
      : 'Indikasi Non-ASD';



  scoreTag.className =
    `score-tag ${
      isASD
        ? 'asd'
        : 'normal'
    }`;



  document.getElementById(
    'rawProbability'
  ).textContent =

    `probabilitas ASD sebelum kalibrasi: ${
      Number(
        result.probability_asd_raw_mean
      ).toFixed(4)
    }`;



  /*
  ================================================
  UNCERTAINTY
  ================================================
  */

  const rawLevel =
    String(
      result.uncertainty_level || ''
    ).trim().toUpperCase();

  const validLevels = [
    'RENDAH',
    'SEDANG',
    'TINGGI'
  ];

  const hasValidLevel =
    validLevels.includes(rawLevel);

  const level =
    hasValidLevel
      ? rawLevel
      : '';

  const badge =
    document.getElementById(
      'uncertaintyBadge'
    );

  if (badge) {

    badge.classList.remove(
      'rendah',
      'sedang',
      'tinggi'
    );

    if (hasValidLevel) {
      badge.classList.add(
        rawLevel.toLowerCase()
      );
      const uncertaintyBar =
  document.getElementById('uncertaintyBar');

  if (uncertaintyBar) {

    uncertaintyBar.classList.remove(
      'rendah',
      'sedang',
      'tinggi'
    );

    uncertaintyBar.classList.add(
      level.toLowerCase()
    );

  }
    }
  }


  const uncertaintyLabel =
    document.getElementById(
      'uncertaintyLabel'
    );

  if (uncertaintyLabel) {

    uncertaintyLabel.textContent =
      hasValidLevel
        ? rawLevel
        : '—';
  }


  const rawUncertainty =
    Number(
      result.uncertainty
    );

  const uncertainty =
    Number.isFinite(rawUncertainty)
      ? Math.max(
          0,
          rawUncertainty
        )
      : 0;


  const rawHighThreshold =
    Number(
      result.uncertainty_thresholds
        ?.medium_to_high
    );

  const highThreshold =
    Number.isFinite(
      rawHighThreshold
    ) &&
    rawHighThreshold > 0

      ? rawHighThreshold

      : 0.15;


  const uncertaintyScaleMax =
    Math.max(
      highThreshold * 1.25,
      0.001
    );


  const barWidth =
    Math.min(
      100,
      Math.max(
        0,
        (
          uncertainty /
          uncertaintyScaleMax
        ) * 100
      )
    );


  const uncertaintyBar =
    document.getElementById(
      'uncertaintyBar'
    );

  if (uncertaintyBar) {

    uncertaintyBar.style.width =
      `${barWidth}%`;
  }


  const uncertaintyNote =
    document.getElementById(
      'uncertaintyNote'
    );

  if (uncertaintyNote) {

    uncertaintyNote.textContent =
      hasValidLevel

        ? uncertaintyText(
            rawLevel,
            uncertainty
          )

        : 'Informasi tingkat ketidakpastian tidak tersedia.';
  }


  const segmentInfo =
    document.getElementById(
      'segmentInfo'
    );

  if (segmentInfo) {

    const rawMcPasses =
      Number(
        result.mc_dropout_passes
      );

    const mcPasses =
      Number.isFinite(
        rawMcPasses
      ) &&
      rawMcPasses > 0

        ? rawMcPasses

        : 30;


    const rawSegments =
      Number(
        result.n_segments_analyzed
      );

    const segmentsText =
      Number.isFinite(
        rawSegments
      ) &&
      rawSegments > 0

        ? ` · ${rawSegments} segmen`

        : '';


    segmentInfo.textContent =
      `estimasi via ${mcPasses}x Monte Carlo Dropout pass${segmentsText}`;
  }



  /*
  ================================================
  GRAD-CAM
  ================================================
  */

  const gradcam =
    document.getElementById(
      'gradcamImage'
    );

  if (
    gradcam &&
    result.gradcam_image_base64_png
  ) {

    gradcam.src =
      `data:image/png;base64,${
        result.gradcam_image_base64_png
      }`;

    gradcam.alt =
      'Grad-CAM frekuensi-waktu hasil analisis EEG';

  } else if (gradcam) {

    gradcam.removeAttribute('src');

    gradcam.alt =
      'Grad-CAM tidak tersedia';

    gradcam.parentElement.classList.add(
      'xai-image-unavailable'
    );

    gradcam.parentElement.textContent =
      'Visualisasi Grad-CAM tidak tersedia untuk hasil ini.';

  }



  const freqAxis =
    Array.isArray(
      result.frequency_axis_hz
    )
      ? result.frequency_axis_hz
      : [];



  if (freqAxis.length) {

    document.getElementById(
      'gradcamCaption'
    ).textContent =

      `Grad-CAM menampilkan area time-frequency yang paling berkontribusi terhadap keputusan model. Representasi EEG dianalisis menggunakan transformasi STFT dengan rentang frekuensi sekitar ${
        Number(freqAxis[0]).toFixed(1)
      }–${
        Number(
          freqAxis[
            freqAxis.length - 1
          ]
        ).toFixed(1)
      } Hz.`;

  }



  /*
  ================================================
  TOPOGRAPHY
  ================================================
  */

  const topo =
    document.getElementById(
      'topographyImage'
    );

  if (
    topo &&
    result.topography_image_base64_png
  ) {

    topo.src =
      `data:image/png;base64,${
        result.topography_image_base64_png
      }`;

    topo.alt =
      'Peta kontribusi channel EEG';

  } else if (topo) {

    topo.removeAttribute('src');

    topo.alt =
      'Topography tidak tersedia';

    topo.parentElement.classList.add(
      'xai-image-unavailable'
    );

    topo.parentElement.textContent =
      'Visualisasi kontribusi channel tidak tersedia untuk hasil ini.';

  }



  if (
    Array.isArray(
      result.top_channels
    ) &&
    result.top_channels.length
  ) {

    const topThree =
      result.top_channels
        .slice(0, 3)
        .map(
          item =>
            `${item.channel} (${
              Number(
                item.contribution
              ).toFixed(2)
            })`
        )
        .join(', ');



    document.getElementById(
      'topographyCaption'
    ).textContent =

      `Kontribusi channel tertinggi pada segmen representatif: ${topThree}.`;

  }



    /*
  ================================================
  DISCLAIMER
  ================================================
  */

  if (result.disclaimer) {

    document.getElementById(
      'disclaimerText'
    ).textContent =
      result.disclaimer;

  }


  /*
  ================================================
  DOWNLOAD PDF REPORT
  ================================================
  */

  const downloadBtn =
    document.getElementById(
      'downloadBtn'
    );

  if (downloadBtn) {

    downloadBtn.addEventListener(
      'click',
      async () => {

        const originalText =
          downloadBtn.innerHTML;


        downloadBtn.disabled = true;

        downloadBtn.textContent =
          'Membuat laporan…';


        try {

          const response =
            await fetch(
              `${API_BASE_URL}/report/pdf`,
              {
                method: 'POST',

                headers: {
                  'Content-Type':
                    'application/json'
                },

                body: JSON.stringify({
                  patient: patient,
                  result: result
                })
              }
            );


          if (!response.ok) {

            let message =
              `Server mengembalikan HTTP ${response.status}.`;


            try {

              const errorData =
                await response.json();

              if (errorData?.detail) {
                message =
                  errorData.detail;
              }

            } catch {
              // gunakan pesan default
            }


            throw new Error(message);

          }


          const blob =
            await response.blob();


          const url =
            URL.createObjectURL(blob);


          const link =
            document.createElement('a');

          link.href = url;

          link.download =
            `NeuroScreen_Laporan_${
              patient.id || 'Pasien'
            }.pdf`;


          document.body.appendChild(
            link
          );

          link.click();

          link.remove();


          URL.revokeObjectURL(url);


        } catch (error) {

          alert(
            `Laporan PDF gagal dibuat: ${
              error.message
            }`
          );


        } finally {

          downloadBtn.disabled = false;

          downloadBtn.innerHTML =
            originalText;

        }

      }
    );

  }

}