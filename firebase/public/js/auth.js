/**
 * Autenticación con Google corporativo y alta automática del operario.
 */
import { initializeApp } from 'https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js';
import {
  getAuth, GoogleAuthProvider, signInWithPopup, signInWithRedirect,
  getRedirectResult, signOut, onAuthStateChanged,
} from 'https://www.gstatic.com/firebasejs/10.14.1/firebase-auth.js';
import {
  getFirestore, doc, getDoc, setDoc, serverTimestamp,
  enableIndexedDbPersistence,
} from 'https://www.gstatic.com/firebasejs/10.14.1/firebase-firestore.js';

import { firebaseConfig, DOMINIO, USAR_PISTA_HD } from './config.js';

export const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const db = getFirestore(app);

// Los handheld trabajan con WiFi irregular: sin esto, perder la señal detiene
// el conteo. Con esto, Firestore encola y envía al reconectar.
enableIndexedDbPersistence(db).catch((e) => {
  // Falla si hay varias pestañas abiertas o el navegador no lo soporta.
  // No es crítico: la app funciona igual, solo sin modo sin conexión.
  console.warn('Modo sin conexión no disponible:', e.code);
});

const proveedor = new GoogleAuthProvider();
const parametros = { prompt: 'select_account' };  // no reutiliza la sesión anterior
// Ver USAR_PISTA_HD en config.js: activarlo sin tener Workspace esconde la
// cuenta del selector y deja al operario sin poder entrar.
if (USAR_PISTA_HD) parametros.hd = DOMINIO;
proveedor.setCustomParameters(parametros);

/** En móvil el popup suele bloquearse; el redirect es más fiable. */
function esMovil() {
  return /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
}

export async function entrar() {
  if (esMovil()) {
    await signInWithRedirect(auth, proveedor);
    return null;   // la página se recarga y vuelve por getRedirectResult
  }
  const cred = await signInWithPopup(auth, proveedor);
  return cred.user;
}

export async function recogerRedirect() {
  try {
    const cred = await getRedirectResult(auth);
    return cred ? cred.user : null;
  } catch (e) {
    console.error('Error al volver del login:', e);
    throw e;
  }
}

export async function salir() {
  await signOut(auth);
}

export function dominioValido(email) {
  return typeof email === 'string' &&
         email.toLowerCase().endsWith('@' + DOMINIO.toLowerCase());
}

/**
 * Dice si la cuenta está gestionada por Google Workspace.
 *
 * El token de Google trae `hd` solo en las cuentas de Workspace. Una cuenta de
 * Google creada con una dirección corporativa no lo trae. La app funciona en
 * ambos casos; sirve para saber si conviene activar USAR_PISTA_HD, y para
 * saber si el proxy de Apps Script tendrá cuota de Workspace o de consumidor.
 */
export async function esCuentaWorkspace(usuario) {
  try {
    const res = await usuario.getIdTokenResult();
    return { workspace: !!res.claims.hd, dominioToken: res.claims.hd || null };
  } catch {
    return { workspace: null, dominioToken: null };
  }
}

/**
 * Asegura el perfil del operario en Firestore.
 *
 * Sin Cloud Functions no hay Admin SDK, así que el rol vive en un documento y
 * las reglas lo leen. El alta es automática: quien entra con la cuenta
 * corporativa queda como OPERADOR. Las reglas impiden que alguien se cree a sí
 * mismo como ADMIN; promover a otro es cosa de un administrador.
 */
export async function asegurarPerfil(usuario) {
  const ref = doc(db, 'usuarios', usuario.uid);
  const snap = await getDoc(ref);

  if (snap.exists()) {
    return { ...snap.data(), nuevo: false };
  }

  const perfil = {
    uid: usuario.uid,
    email: usuario.email,
    nombre: usuario.displayName || usuario.email,
    foto: usuario.photoURL || null,
    rol: 'OPERADOR',
    activo: true,
    creadoEn: serverTimestamp(),
  };
  await setDoc(ref, perfil);
  return { ...perfil, nuevo: true };
}

/**
 * Observa la sesión.
 *
 * @param {(estado: object) => void} alCambiar
 *   Recibe { usuario, perfil, error } — `usuario` null si no hay sesión.
 */
export function observarSesion(alCambiar) {
  return onAuthStateChanged(auth, async (usuario) => {
    if (!usuario) return alCambiar({ usuario: null, perfil: null });

    // El parámetro `hd` es solo una pista: se puede saltar. Aquí se cierra la
    // sesión de quien no sea del dominio, para que no quede a medias.
    if (!dominioValido(usuario.email)) {
      await salir();
      return alCambiar({
        usuario: null, perfil: null,
        error: `Esta aplicación es solo para cuentas de ${DOMINIO}. ` +
               `Entraste con ${usuario.email}.`,
      });
    }

    try {
      const perfil = await asegurarPerfil(usuario);
      if (perfil.activo === false) {
        await salir();
        return alCambiar({
          usuario: null, perfil: null,
          error: 'Tu cuenta está desactivada. Habla con tu supervisor.',
        });
      }
      alCambiar({ usuario, perfil });
    } catch (e) {
      alCambiar({ usuario, perfil: null, error: traducirError(e) });
    }
  });
}

/** Mensajes accionables en vez de códigos de Firebase. */
export function traducirError(e) {
  const codigo = (e && e.code) || '';
  const mapa = {
    'auth/unauthorized-domain':
      'Este dominio no está autorizado en Firebase. Authentication → Settings → Authorized domains.',
    'auth/popup-blocked':
      'El navegador bloqueó la ventana de Google. Permite las ventanas emergentes de este sitio.',
    'auth/popup-closed-by-user':
      'Cerraste la ventana de Google antes de terminar.',
    'auth/cancelled-popup-request':
      'Se abrió otra ventana de login. Intenta de nuevo.',
    'auth/network-request-failed':
      'Sin conexión. Revisa el WiFi del dispositivo.',
    'auth/operation-not-allowed':
      'El acceso con Google no está activado. Authentication → Sign-in method → Google.',
    'permission-denied':
      'Las reglas de Firestore rechazaron la operación. ¿Se desplegaron las reglas?',
    'unavailable':
      'No se pudo contactar a Firestore. ¿Está creada la base de datos?',
    'failed-precondition':
      'Falta un índice de Firestore, o hay varias pestañas abiertas.',
  };
  return mapa[codigo] || (e && e.message) || String(e);
}
