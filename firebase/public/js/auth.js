/**
 * Autenticación con Google corporativo y alta automática del operario.
 */
import { initializeApp, deleteApp }
  from 'https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js';
import {
  getAuth, GoogleAuthProvider, signInWithPopup, signInWithRedirect,
  getRedirectResult, signOut, onAuthStateChanged,
  signInWithEmailAndPassword, createUserWithEmailAndPassword,
  updatePassword, updateProfile, EmailAuthProvider, reauthenticateWithCredential,
} from 'https://www.gstatic.com/firebasejs/10.14.1/firebase-auth.js';
import {
  initializeFirestore, doc, getDoc, setDoc, serverTimestamp,
  persistentLocalCache, persistentMultipleTabManager,
} from 'https://www.gstatic.com/firebasejs/10.14.1/firebase-firestore.js';

import { firebaseConfig, DOMINIO, USAR_PISTA_HD, DATABASE_ID } from './config.js';

export const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);

/**
 * Firestore con caché local, y con el ÚLTIMO argumento: la base es nombrada,
 * no la `(default)`.
 *
 * Los handheld trabajan con WiFi irregular: sin caché, perder la señal detiene
 * el conteo; con ella, Firestore encola y envía al reconectar.
 *
 * `persistentMultipleTabManager` en vez de la forma antigua: aquella fallaba en
 * cuanto había una segunda pestaña abierta —el supervisor con el listado y la
 * validación a la vez— y dejaba ese dispositivo sin modo sin conexión, con un
 * aviso en la consola que nadie mira.
 */
export const db = initializeFirestore(app, {
  localCache: persistentLocalCache({ tabManager: persistentMultipleTabManager() }),
}, DATABASE_ID);

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


// =========================================================================== //
// Acceso con usuario y contraseña
// =========================================================================== //
/**
 * Por qué existe este camino además del de Google.
 *
 * Los handheld son compartidos: varios operarios por turno, en un navegador
 * que ya arrastra las cuentas personales de quien lo usó antes. El selector de
 * Google obliga a elegir entre esas cuentas en cada relevo, y basta equivocarse
 * una vez para quedarse fuera sin saber por qué.
 *
 * Con usuario y contraseña el relevo es escribir dos campos. El administrador
 * da de alta a cada operario; nadie se registra solo. Es además lo que se pidió
 * desde el principio: que el operario no pueda hacerse pasar por otro.
 *
 * Google se queda para supervisores y administradores, que entran desde su
 * propio equipo.
 */

/** Completa un usuario suelto a correo del dominio: «jperez» → jperez@itsanet.com */
export function aCorreo(entrada) {
  const v = String(entrada || '').trim().toLowerCase();
  if (!v) return '';
  return v.includes('@') ? v : `${v}@${DOMINIO.toLowerCase()}`;
}

export async function entrarConClave(usuarioOCorreo, clave) {
  const correo = aCorreo(usuarioOCorreo);
  if (!correo) throw new Error('Escribe tu usuario.');
  if (!clave) throw new Error('Escribe tu contraseña.');
  const cred = await signInWithEmailAndPassword(auth, correo, clave);
  return cred.user;
}

/**
 * Da de alta a un operario sin perder la sesión de quien lo crea.
 *
 * `createUserWithEmailAndPassword` deja la sesión abierta como el usuario
 * recién creado. En el Admin SDK eso no pasa, pero el Admin SDK necesita Cloud
 * Functions y el plan de pago. La salida en Spark es crear el usuario en una
 * SEGUNDA instancia de la app: nace ahí, se cierra esa sesión y se desecha la
 * instancia. La sesión del administrador ni se entera.
 */
export async function crearOperario({ usuario, clave, nombre, rol = 'OPERADOR' }) {
  const correo = aCorreo(usuario);
  if (!dominioValido(correo)) {
    throw new Error(`El usuario debe ser del dominio @${DOMINIO}.`);
  }
  if (!clave || clave.length < 6) {
    throw new Error('La contraseña necesita al menos 6 caracteres.');
  }
  if (!['OPERADOR', 'SUPERVISOR', 'ADMIN'].includes(rol)) {
    throw new Error('Rol no válido.');
  }

  const secundaria = initializeApp(firebaseConfig, 'alta-' + Date.now());
  try {
    const authSec = getAuth(secundaria);
    const cred = await createUserWithEmailAndPassword(authSec, correo, clave);
    const nombreFinal = limpiarNombre(nombre) || correo.split('@')[0];
    await updateProfile(cred.user, { displayName: nombreFinal });

    // El perfil lo escribe el administrador con SU sesión: el operario recién
    // creado todavía no tiene permiso para nada.
    await setDoc(doc(db, 'usuarios', cred.user.uid), {
      uid: cred.user.uid,
      email: correo,
      nombre: nombreFinal,
      foto: null,
      rol,
      activo: true,
      tipoAcceso: 'CLAVE',
      creadoEn: serverTimestamp(),
    });

    await signOut(authSec);
    return { uid: cred.user.uid, email: correo, nombre: nombreFinal, rol };
  } finally {
    await deleteApp(secundaria).catch(() => {});
  }
}

const limpiarNombre = (v) => String(v || '').replace(/\s+/g, ' ').trim().slice(0, 80);

/** Cambio de contraseña por el propio operario. Google exige la actual. */
export async function cambiarClave(claveActual, claveNueva) {
  const u = auth.currentUser;
  if (!u) throw new Error('No hay sesión iniciada.');
  if (!claveNueva || claveNueva.length < 6) {
    throw new Error('La contraseña nueva necesita al menos 6 caracteres.');
  }
  await reauthenticateWithCredential(u, EmailAuthProvider.credential(u.email, claveActual));
  await updatePassword(u, claveNueva);
}

/** Dice si la sesión actual entró con contraseña o con Google. */
export function tipoDeAcceso(usuario) {
  const ids = (usuario?.providerData || []).map((p) => p.providerId);
  if (ids.includes('google.com')) return 'GOOGLE';
  if (ids.includes('password')) return 'CLAVE';
  return 'DESCONOCIDO';
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

  // Quien entra con contraseña no puede darse de alta a sí mismo: las reglas
  // exigen un correo verificado por Google para el alta automática, y una
  // contraseña no verifica nada. Sin esto, el operario vería un error de
  // permisos en bruto en vez de saber qué le falta.
  if (tipoDeAcceso(usuario) === 'CLAVE') {
    throw new Error(
      `La cuenta ${usuario.email} existe pero no está dada de alta en la ` +
      'aplicación. Pídele a un administrador que te registre en Usuarios.',
    );
  }

  const perfil = {
    uid: usuario.uid,
    email: usuario.email,
    nombre: usuario.displayName || usuario.email,
    foto: usuario.photoURL || null,
    rol: 'OPERADOR',
    activo: true,
    tipoAcceso: 'GOOGLE',
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
      'Ese método de acceso no está activado en Firebase. ' +
      'Authentication → Sign-in method → activa Google y Correo/contraseña.',
    'auth/invalid-credential':
      'Usuario o contraseña incorrectos.',
    'auth/wrong-password':
      'Contraseña incorrecta.',
    'auth/user-not-found':
      'Ese usuario no existe. Pídele a un administrador que te dé de alta.',
    'auth/invalid-email':
      'El usuario no tiene forma de correo válida.',
    'auth/user-disabled':
      'Esta cuenta está deshabilitada en Firebase.',
    'auth/too-many-requests':
      'Demasiados intentos fallidos. Espera unos minutos o pide que te cambien la contraseña.',
    'auth/email-already-in-use':
      'Ya existe un usuario con ese correo.',
    'auth/weak-password':
      'La contraseña es demasiado corta: mínimo 6 caracteres.',
    'auth/requires-recent-login':
      'Por seguridad, vuelve a entrar antes de cambiar la contraseña.',
    'permission-denied':
      'Las reglas de Firestore rechazaron la operación. ¿Se desplegaron las reglas?',
    'unavailable':
      'No se pudo contactar a Firestore. Si en la consola del navegador aparece ' +
      'ERR_BLOCKED_BY_CLIENT, lo está bloqueando una extensión (bloqueador de ' +
      'anuncios o antivirus): desactívala para este sitio. Si no, revisa el WiFi ' +
      'y que la base de datos esté creada.',
    'failed-precondition':
      'Falta un índice de Firestore, o hay varias pestañas abiertas.',
  };
  return mapa[codigo] || (e && e.message) || String(e);
}
