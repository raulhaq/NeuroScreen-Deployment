// NeuroScreen — Upload page behavior

import {
  auth,
  db
} from "./firebase-config.js";

import {
  onAuthStateChanged,
  signOut
} from "https://www.gstatic.com/firebasejs/12.19.0/firebase-auth.js";

import {
  doc,
  getDoc
} from "https://www.gstatic.com/firebasejs/12.19.0/firebase-firestore.js";


const API_BASE_URL = 'http://127.0.0.1:8000';

const form = document.getElementById('uploadForm');
const submitBtn = document.getElementById('submitBtn');
const statusBox = document.getElementById('analysisStatus');

//user menu
const userMenuBtn =
  document.getElementById('userMenuBtn');

const userMenuArrow =
  document.querySelector('.user-menu-arrow');

const userDropdown =
  document.getElementById('userDropdown');

const userAvatar =
  document.getElementById('userAvatar');

const userDisplayName =
  document.getElementById('userDisplayName');

const dropdownUserName =
  document.getElementById('dropdownUserName');

const dropdownUserEmail =
  document.getElementById('dropdownUserEmail');

const logoutBtn =
  document.getElementById('logoutBtn');


function getInitials(name) {

  if (!name) {
    return "--";
  }

  const words =
    name
      .trim()
      .split(/\s+/)
      .filter(Boolean);

  if (words.length === 1) {

    return words[0]
      .substring(0, 2)
      .toUpperCase();

  }

  return (
    words[0][0] +
    words[words.length - 1][0]
  ).toUpperCase();
}

async function loadUserProfile(user) {

  let name =
    user.displayName ||
    user.email?.split("@")[0] ||
    "Pengguna NeuroScreen";

  try {

    const userRef =
      doc(db, "users", user.uid);

    const snapshot =
      await getDoc(userRef);

    if (snapshot.exists()) {

      const profile =
        snapshot.data();

      if (profile.name) {
        name = profile.name;
      }

    }

  } catch (error) {

    console.warn(
      "Profil Firestore tidak dapat dimuat:",
      error
    );

  }

  userAvatar.textContent =
    getInitials(name);

  userDisplayName.textContent =
    name;

  dropdownUserName.textContent =
    name;

  dropdownUserEmail.textContent =
    user.email || "Email tidak tersedia";
}


onAuthStateChanged(
  auth,
  async (user) => {

    if (!user) {

      window.location.href =
        "Login.html";

      return;
    }

    await loadUserProfile(user);

  }
);

if (userMenuBtn) {

  userMenuBtn.addEventListener(
    "click",
    (event) => {

      event.stopPropagation();

      const isOpen =
        userDropdown.classList.toggle("show");

      userMenuBtn.setAttribute(
        "aria-expanded",
        String(isOpen)
      );
      userMenuArrow.classList.toggle("open", isOpen);

    }
  );

}

document.addEventListener(
  "click",
  (event) => {

    if (
      userDropdown &&
      userMenuBtn &&
      !userDropdown.contains(event.target) &&
      !userMenuBtn.contains(event.target)
    ) {

      userDropdown.classList.remove(
        "show"
      );

      userMenuBtn.setAttribute(
        "aria-expanded",
        "false"
      );

      userMenuArrow.classList.remove("open");

    }

  }
);

if (logoutBtn) {

  logoutBtn.addEventListener(
    "click",
    async () => {

      try {

        await signOut(auth);

        window.location.href =
          "Login.html";

      } catch (error) {

        console.error(
          "Logout gagal:",
          error
        );

        showStatus(
          "Gagal keluar dari akun. Silakan coba lagi.",
          true
        );

      }

    }
  );

}

function setProgress(step) {

  const steps =
    document.querySelectorAll('.progress-step');

  steps.forEach((item, index) => {

    item.classList.remove(
      'active',
      'done'
    );

    if (index < step) {
      item.classList.add('done');
    }

    if (index === step) {
      item.classList.add('active');
    }

  });

}
setProgress(0);
function bindUpload(inputId, zoneId, filenameId) {

  const input = document.getElementById(inputId);
  const zone = document.getElementById(zoneId);
  const filenameEl = document.getElementById(filenameId);

  input.addEventListener('change', () => {

    if (input.files.length > 0) {

      filenameEl.textContent =
        input.files[0].name;

      zone.classList.add('filled');

    } else {

      filenameEl.textContent = '';

      zone.classList.remove('filled');

    }

  });

}


function showStatus(message, isError = false) {

  statusBox.textContent = message;

  statusBox.classList.add('show');

  statusBox.classList.toggle('error', isError);

}


const cancelBtn =
  document.getElementById('cancelBtn');

if (cancelBtn) {

  cancelBtn.addEventListener('click', () => {

    window.location.href = 'Login.html';

  });

}


bindUpload(
  'session1',
  'zone1',
  'filename1'
);


bindUpload(
  'session2',
  'zone2',
  'filename2'
);


form.addEventListener('submit', async (event) => {

  event.preventDefault();


  const session1 =
    document.getElementById('session1').files[0];

  const session2 =
    document.getElementById('session2').files[0];


  if (!session1 || !session2) {

    showStatus(
      'Pilih file EEG Sesi 1 dan Sesi 2 terlebih dahulu.',
      true
    );

    return;

  }


  // Validasi format file
  const allowedExtensions = ['.txt', '.csv'];

  const session1Extension =
    session1.name
      .substring(session1.name.lastIndexOf('.'))
      .toLowerCase();

  const session2Extension =
    session2.name
      .substring(session2.name.lastIndexOf('.'))
      .toLowerCase();


  if (
    !allowedExtensions.includes(session1Extension) ||
    !allowedExtensions.includes(session2Extension)
  ) {

    showStatus(
      'Format file tidak didukung. Gunakan file EEG dengan format .txt atau .csv.',
      true
    );

    return;

  }


  const patient = {

    id:
      document
        .getElementById('patientName')
        .value
        .trim(),

    age:
      Number(
        document
          .getElementById('patientAge')
          .value
      ),

    gender:
      document
        .getElementById('patientGender')
        .value,

    recordDate:
      document
        .getElementById('recordDate')
        .value,

    session1Filename:
      session1.name,

    session2Filename:
      session2.name

  };


  const payload =
    new FormData();


  payload.append(
    'session1',
    session1
  );


  payload.append(
    'session2',
    session2
  );


  submitBtn.disabled = true;

  submitBtn.innerHTML = `
    <span class="analysis-spinner"></span>
    Menganalisis…
  `;



  showStatus(
    'Rekaman EEG sedang diproses. Jangan tutup halaman ini.'
  );


  try {

  const response =
    await fetch(
      `${API_BASE_URL}/predict`,
      {
        method: 'POST',
        body: payload
      }
    );


  let data = null;


  // ----------------------------------------------------------
  // Coba membaca response JSON
  // ----------------------------------------------------------

  try {

    data =
      await response.json();

  } catch {

    data = null;

  }


  // ----------------------------------------------------------
  // Backend mengembalikan error HTTP
  // ----------------------------------------------------------

  if (!response.ok) {

    const detail =
      data?.detail ||
      `Server mengembalikan HTTP ${response.status}.`;

    throw new Error(
      detail
    );

  }


  // ----------------------------------------------------------
  // Analisis berhasil
  // ----------------------------------------------------------

  sessionStorage.setItem(
    'neuroscreenPatient',
    JSON.stringify(patient)
  );


  sessionStorage.setItem(
    'neuroscreenResult',
    JSON.stringify(data)
  );


  window.location.href =
    'Results.html';


} catch (error) {

  console.error(
    'NeuroScreen analysis error:',
    error
  );


  // ----------------------------------------------------------
  // Default message
  // ----------------------------------------------------------

  let errorMessage =
    'Terjadi kesalahan saat memproses analisis EEG. Silakan coba lagi.';


  // ----------------------------------------------------------
  // Error karena server tidak dapat dihubungi
  // ----------------------------------------------------------

  if (
    error instanceof TypeError &&
    error.message
      .toLowerCase()
      .includes('fetch')
  ) {

    errorMessage =
      'Server analisis tidak dapat dihubungi. Pastikan layanan sedang aktif, lalu coba lagi.';

  }


  // ----------------------------------------------------------
  // Error dari backend / file EEG
  // ----------------------------------------------------------

  else if (error?.message) {

    errorMessage =
      error.message;

  }


  // ----------------------------------------------------------
  // Tampilkan pesan
  // ----------------------------------------------------------

  showStatus(
    errorMessage,
    true
  );


  // ----------------------------------------------------------
  // Kembalikan UI ke kondisi awal
  // ----------------------------------------------------------

  setProgress(0);

  submitBtn.disabled = false;

  submitBtn.innerHTML =
    'Mulai analisis →';

}
});