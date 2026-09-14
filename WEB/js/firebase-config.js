// NeuroScreen — Firebase configuration

import { initializeApp } from "https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js";
import { getAuth } from "https://www.gstatic.com/firebasejs/12.19.0/firebase-auth.js";
import { getFirestore } from "https://www.gstatic.com/firebasejs/12.19.0/firebase-firestore.js";

const firebaseConfig = {
  apiKey: "AIzaSyDmcowT3nVT8RRM75kA0WkpDGcAGMOJyio",
  authDomain: "neuroscreen-4c942.firebaseapp.com",
  projectId: "neuroscreen-4c942",
  storageBucket: "neuroscreen-4c942.firebasestorage.app",
  messagingSenderId: "140414480662",
  appId: "1:140414480662:web:0d6160355ec017e5682037"
};

const app = initializeApp(firebaseConfig);

const auth = getAuth(app);
const db = getFirestore(app);

export { app, auth, db };