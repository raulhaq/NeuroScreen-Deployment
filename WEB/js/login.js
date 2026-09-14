// ============================================================
// NeuroScreen — Firebase Authentication
// ============================================================

import {
  auth,
  db
} from "./firebase-config.js";

import {
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  GoogleAuthProvider,
  signInWithPopup,
  updateProfile,
  sendPasswordResetEmail
} from "https://www.gstatic.com/firebasejs/12.19.0/firebase-auth.js";

import {
  doc,
  getDoc,
  setDoc,
  serverTimestamp
} from "https://www.gstatic.com/firebasejs/12.19.0/firebase-firestore.js";


// ============================================================
// DOM ELEMENTS
// ============================================================
const passwordHint =
  document.getElementById("passwordHint");
const loginForm =
  document.getElementById("loginForm");

const authTitle =
  document.getElementById("authTitle");

const authSubtitle =
  document.getElementById("authSubtitle");

const nameField =
  document.getElementById("nameField");

const nameInput =
  document.getElementById("name");

const emailInput =
  document.getElementById("email");

const passwordInput =
  document.getElementById("password");

const confirmPasswordField =
  document.getElementById("confirmPasswordField");

const confirmPasswordInput =
  document.getElementById("confirmPassword");

const submitBtn =
  document.getElementById("submitBtn");

const googleBtn =
  document.getElementById("googleBtn");

const googleBtnText =
  document.getElementById("googleBtnText");

const googleDivider =
  document.getElementById("googleDivider");

const switchText =
  document.getElementById("switchText");

const switchModeBtn =
  document.getElementById("switchModeBtn");

const forgotPassword =
  document.getElementById("forgotPassword");

const forgotPasswordBtn =
  document.getElementById("forgotPasswordBtn");

const authError =
  document.getElementById("authError");

const authSuccess =
  document.getElementById("authSuccess");


// ============================================================
// STATE
// ============================================================

let isRegisterMode = false;


// ============================================================
// MESSAGE HANDLER
// ============================================================

function clearMessages() {

  authError.textContent = "";
  authError.classList.remove("show");

  authSuccess.textContent = "";
  authSuccess.classList.remove("show");

}


function showError(message) {

  authSuccess.textContent = "";
  authSuccess.classList.remove("show");

  authError.textContent = message;
  authError.classList.add("show");

}


function showSuccess(message) {

  authError.textContent = "";
  authError.classList.remove("show");

  authSuccess.textContent = message;
  authSuccess.classList.add("show");

}


// ============================================================
// FIREBASE ERROR TRANSLATION
// ============================================================

function getFirebaseErrorMessage(error) {

  const code = error?.code || "";

  switch (code) {

    case "auth/invalid-email":
      return "Format email tidak valid.";

    case "auth/user-not-found":
      return "Akun dengan email tersebut tidak ditemukan.";

    case "auth/wrong-password":
      return "Email atau kata sandi salah.";

    case "auth/invalid-credential":
      return "Email atau kata sandi salah.";

    case "auth/email-already-in-use":
      return "Email tersebut sudah terdaftar. Silakan masuk.";

    case "auth/weak-password":
      return "Kata sandi terlalu lemah. Gunakan minimal 6 karakter.";

    case "auth/password-does-not-meet-requirements":
      return "Kata sandi belum memenuhi persyaratan keamanan.";

    case "auth/popup-closed-by-user":
      return "Proses login Google dibatalkan.";

    case "auth/popup-blocked":
      return "Popup Google diblokir browser. Izinkan popup untuk NeuroScreen.";

    case "auth/cancelled-popup-request":
      return "Permintaan login Google dibatalkan.";

    case "auth/account-exists-with-different-credential":
      return "Email tersebut sudah terdaftar dengan metode login yang berbeda.";

    case "auth/unauthorized-domain":
      return "Domain aplikasi belum diizinkan oleh Firebase Authentication.";

    case "auth/too-many-requests":
      return "Terlalu banyak percobaan. Silakan coba lagi beberapa saat.";

    case "auth/network-request-failed":
      return "Koneksi internet bermasalah. Periksa koneksi Anda.";

    default:
      console.error("Firebase error:", error);
      return "Terjadi kesalahan saat proses autentikasi. Silakan coba lagi.";
  }
}


// ============================================================
// SAVE USER PROFILE TO FIRESTORE
// ============================================================

async function saveUserProfile(user, name = null) {

  const userRef =
    doc(db, "users", user.uid);

  const existing =
    await getDoc(userRef);

  const finalName =
    name ||
    user.displayName ||
    user.email?.split("@")[0] ||
    "Pengguna NeuroScreen";


  if (!existing.exists()) {

    await setDoc(userRef, {

      name: finalName,

      email: user.email || "",

      createdAt: serverTimestamp(),

      updatedAt: serverTimestamp()

    });

  } else {

    await setDoc(
      userRef,
      {
        name: finalName,
        email: user.email || "",
        updatedAt: serverTimestamp()
      },
      {
        merge: true
      }
    );

  }

}


// ============================================================
// REDIRECT AFTER LOGIN
// ============================================================

function goToUpload() {

  window.location.href =
    "Upload.html";

}


// ============================================================
// LOADING STATE
// ============================================================

function setLoading(isLoading, text = "Memproses…") {

  if (isLoading) {

    submitBtn.disabled = true;
    googleBtn.disabled = true;

    submitBtn.textContent = text;

    googleBtnText.textContent =
      "Memproses…";

    loginForm.classList.add("loading");
    googleBtn.classList.add("loading");

  } else {

    submitBtn.disabled = false;
    googleBtn.disabled = false;

    submitBtn.textContent =
      isRegisterMode
        ? "Buat akun"
        : "Masuk";

    googleBtnText.textContent =
      isRegisterMode
        ? "Daftar dengan Google"
        : "Lanjutkan dengan Google";

    loginForm.classList.remove("loading");
    googleBtn.classList.remove("loading");

  }

}


// ============================================================
// SWITCH LOGIN / REGISTER
// ============================================================

function updateAuthMode() {

  clearMessages();

  if (isRegisterMode) {

    authTitle.textContent =
      "Buat akun NeuroScreen";

    authSubtitle.textContent =
      "Daftarkan akun untuk mengakses NeuroScreen.";

    nameField.classList.remove("hidden");

    confirmPasswordField.classList.remove("hidden");

    forgotPassword.classList.add("hidden");

    submitBtn.textContent =
      "Buat akun";

    googleBtnText.textContent =
      "Daftar dengan Google";

    switchText.textContent =
      "Sudah punya akun?";

    switchModeBtn.textContent =
      "Masuk";

    nameInput.required = true;

    confirmPasswordInput.required = true;
    passwordHint.classList.remove("hidden");

    passwordInput.autocomplete =
      "new-password";

  } else {

    authTitle.textContent =
      "Masuk ke akun Anda";

    authSubtitle.textContent =
      "Gunakan akun Anda untuk mengakses NeuroScreen.";

    nameField.classList.add("hidden");

    confirmPasswordField.classList.add("hidden");

    forgotPassword.classList.remove("hidden");

    submitBtn.textContent =
      "Masuk";

    googleBtnText.textContent =
      "Lanjutkan dengan Google";

    switchText.textContent =
      "Belum punya akun?";

    switchModeBtn.textContent =
      "Daftar";

    nameInput.required = false;

    confirmPasswordInput.required = false;
    passwordHint.classList.add("hidden");
    passwordInput.autocomplete =
      "current-password";

  }

}


switchModeBtn.addEventListener(
  "click",
  () => {

    isRegisterMode =
      !isRegisterMode;

    updateAuthMode();

  }
);


// ============================================================
// EMAIL / PASSWORD
// ============================================================

loginForm.addEventListener(
  "submit",
  async (event) => {

    event.preventDefault();

    clearMessages();

    const email =
      emailInput.value.trim();

    const password =
      passwordInput.value;

    if (!email || !password) {

      showError(
        "Email dan kata sandi wajib diisi."
      );

      return;
    }


    // --------------------------------------------------------
    // REGISTER
    // --------------------------------------------------------

    if (isRegisterMode) {

      const name =
        nameInput.value.trim();

      const confirmPassword =
        confirmPasswordInput.value;


      if (!name) {

        showError(
          "Nama lengkap wajib diisi."
        );

        nameInput.focus();

        return;
      }


      if (name.length < 2) {

        showError(
          "Nama lengkap terlalu pendek."
        );

        nameInput.focus();

        return;
      }

      
      if (password.length < 8) {

        showError(
          "Kata sandi minimal 8 karakter."
        );

        passwordInput.focus();

        return;
      }


      if (password !== confirmPassword) {

        showError(
          "Konfirmasi kata sandi tidak sama."
        );

        confirmPasswordInput.focus();

        return;
      }


      setLoading(
        true,
        "Membuat akun…"
      );


      try {

        const credential =
          await createUserWithEmailAndPassword(
            auth,
            email,
            password
          );


        const user =
          credential.user;


        // Set display name pada Firebase Auth
        await updateProfile(
          user,
          {
            displayName: name
          }
        );


        // Simpan profil ke Firestore
        await saveUserProfile(
          user,
          name
        );


        showSuccess(
          "Akun berhasil dibuat. Membuka NeuroScreen…"
        );


        setTimeout(
          goToUpload,
          700
        );


      } catch (error) {

        showError(
          getFirebaseErrorMessage(error)
        );

        setLoading(
          false
        );

      }

      return;

    }


    // --------------------------------------------------------
    // LOGIN
    // --------------------------------------------------------

    setLoading(
      true,
      "Memverifikasi…"
    );


    try {

      const credential =
        await signInWithEmailAndPassword(
          auth,
          email,
          password
        );


      const user =
        credential.user;


      await saveUserProfile(
        user
      );


      showSuccess(
        "Login berhasil. Membuka NeuroScreen…"
      );


      setTimeout(
        goToUpload,
        500
      );


    } catch (error) {

      showError(
        getFirebaseErrorMessage(error)
      );

      setLoading(
        false
      );

    }

  }
);


// ============================================================
// GOOGLE SIGN-IN
// ============================================================

googleBtn.addEventListener(
  "click",
  async () => {

    clearMessages();

    setLoading(
      true,
      "Menghubungkan…"
    );


    try {

      const provider =
        new GoogleAuthProvider();


      provider.setCustomParameters({
        prompt: "select_account"
      });


      const result =
        await signInWithPopup(
          auth,
          provider
        );


      const user =
        result.user;


      await saveUserProfile(
        user,
        user.displayName
      );


      showSuccess(
        "Login Google berhasil. Membuka NeuroScreen…"
      );


      setTimeout(
        goToUpload,
        500
      );


    } catch (error) {

      showError(
        getFirebaseErrorMessage(error)
      );

      setLoading(
        false
      );

    }

  }
);


// ============================================================
// FORGOT PASSWORD
// ============================================================

forgotPasswordBtn.addEventListener(
  "click",
  async () => {

    clearMessages();

    const email =
      emailInput.value.trim();


    if (!email) {

      showError(
        "Masukkan email terlebih dahulu untuk mereset kata sandi."
      );

      emailInput.focus();

      return;
    }


    try {

      await sendPasswordResetEmail(
        auth,
        email
      );


      showSuccess(
        "Tautan reset kata sandi telah dikirim ke email Anda."
      );


    } catch (error) {

      showError(
        getFirebaseErrorMessage(error)
      );

    }

  }
);


// ============================================================
// INITIAL STATE
// ============================================================

updateAuthMode();

console.log(
  "NeuroScreen Firebase Authentication siap."
);