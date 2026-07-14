// Firebase SDK via CDN (no npm needed for static hosting)
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import { getAuth, GoogleAuthProvider, signInWithPopup, signOut, onAuthStateChanged } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";

// Your web app's Firebase configuration
const firebaseConfig = {
  apiKey: "AIzaSyAwzoxATMSS7ElI_Z4QjM6kywscVJ2GvDU",
  authDomain: "personal-ai-agent-3abfc.firebaseapp.com",
  projectId: "personal-ai-agent-3abfc",
  storageBucket: "personal-ai-agent-3abfc.firebasestorage.app",
  messagingSenderId: "911082420954",
  appId: "1:911082420954:web:6b3d0d248fa84d9eb683e3",
  measurementId: "G-R054S2CHSP"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const provider = new GoogleAuthProvider();

export { auth, provider, signInWithPopup, signOut, onAuthStateChanged };
