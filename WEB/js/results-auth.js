// ============================================================
// NeuroScreen — Results Authentication
// ============================================================

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


// ============================================================
// DOM
// ============================================================

const userMenuBtn =
  document.getElementById("userMenuBtn");

const userDropdown =
  document.getElementById("userDropdown");

const userAvatar =
  document.getElementById("userAvatar");

const userDisplayName =
  document.getElementById("userDisplayName");

const dropdownUserName =
  document.getElementById("dropdownUserName");

const dropdownUserEmail =
  document.getElementById("dropdownUserEmail");

const logoutBtn =
  document.getElementById("logoutBtn");


// ============================================================
// INITIALS
// ============================================================

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


// ============================================================
// LOAD USER PROFILE
// ============================================================

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

        name =
          profile.name;

      }

    }

  } catch (error) {

    console.warn(
      "Profil Firestore tidak dapat dimuat:",
      error
    );

  }


  if (userAvatar) {

    userAvatar.textContent =
      getInitials(name);

  }


  if (userDisplayName) {

    userDisplayName.textContent =
      name;

  }


  if (dropdownUserName) {

    dropdownUserName.textContent =
      name;

  }


  if (dropdownUserEmail) {

    dropdownUserEmail.textContent =
      user.email ||
      "Email tidak tersedia";

  }

}


// ============================================================
// AUTH GUARD
// ============================================================

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


// ============================================================
// DROPDOWN
// ============================================================

if (userMenuBtn) {

  userMenuBtn.addEventListener(
    "click",
    (event) => {

      event.stopPropagation();

      const isOpen =
        userDropdown.classList.toggle(
          "show"
        );

      userMenuBtn.setAttribute(
        "aria-expanded",
        String(isOpen)
      );

    }
  );

}


// ============================================================
// CLOSE DROPDOWN
// ============================================================

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

    }

  }
);


// ============================================================
// LOGOUT
// ============================================================

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

        alert(
          "Gagal keluar dari akun. Silakan coba lagi."
        );

      }

    }
  );

}