/**
 * Autenticación con Google corporativo y alta automática del operario.
 */
import { initializeApp, deleteApp }
  from '../vendor/firebase-sdk.js?v=20261022-64';
import {
  getAuth, GoogleAuthProvider, signInWithPopup, signInWithRedirect,
  getRedirectResult, signOut, onAuthStateChanged,
  signInWithEmailAndPassword, createUserWithEmailAndPassword,
  updatePassword, updateProfile, EmailAuthProvider, reauthenticateWithCredential,
  sendPasswordResetEmail,
} from '../vendor/firebase-sdk.js?v=20261022-64';
import {
  initializeFirestore, doc, getDoc, setDoc, serverTimestamp,
  persistentLocalCache, persistentMultipleTabManager, writeBatch,
} from '../vendor/firebase-sdk.js?v=20261022-64';

import { firebaseConfig, DOMINIO, USAR_PISTA_HD, DATABASE_ID } from './config.js?v=20261022-64';
import * as local from './local.js?v=20261022-64';

/**
 * Dónde se resuelve el acceso.
 *
 * Servida desde el servidor de la red local, la sesión es una cookie suya y no
 * hay Firebase de por medio: entrar con Google necesita Internet, y la razón de
 * tener el servidor en la bodega es poder trabajar sin depender de él.
 *
 * Las pantallas siguen llamando a `observarSesion`, `entrarConClave` y `salir`
 * sin saber cuál de los dos está contestando.
 */
export const modoLocal = local.modoLocal;

export const app = modoLocal() ? null : initializeApp(firebaseConfig);
export const auth = modoLocal() ? null : getAuth(app);

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
export const db = modoLocal() ? null : initializeFirestore(app, {
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
  if (modoLocal()) { location.assign('/api/auth/google/iniciar'); return null; }
  if (esMovil()) {
    await signInWithRedirect(auth, proveedor);
    return null;   // la página se recarga y vuelve por getRedirectResult
  }
  const cred = await signInWithPopup(auth, proveedor);
  return cred.user;
}

export async function recogerRedirect() {
  if (modoLocal()) return null;
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

/**
 * Resuelve lo que escribe el operario a un correo real.
 *
 * El operario escribe `jperez`, no su correo: con guantes y en el relevo de
 * turno, cada carácter de más es un intento fallido. Pero la identidad NO puede
 * ser un correo inventado: suponer que `jperez@itsanet.com` existe es suponer
 * algo que nadie ha comprobado, y si mañana hay que escribirle a esa persona,
 * no hay a dónde.
 *
 * Así que el alias y el correo son cosas distintas. `alias/{usuario}` guarda el
 * correo real con el que se registró, y aquí se consulta.
 *
 * Ese documento se lee sin haber iniciado sesión —hace falta justo antes de
 * entrar—, pero solo de uno en uno: las reglas permiten `get` y prohíben
 * `list`, así que se puede comprobar un alias concreto y no se puede sacar la
 * lista de nadie.
 */
export function pareceCorreo(v) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(String(v || '').trim());
}

export const normalizarAlias = (v) =>
  String(v || '').trim().toLowerCase().replace(/[^a-z0-9._-]/g, '');

export async function resolverCorreo(entrada) {
  const v = String(entrada || '').trim().toLowerCase();
  if (!v) return '';
  if (v.includes('@')) return v;

  const alias = normalizarAlias(v);
  if (!alias) return '';
  try {
    const snap = await getDoc(doc(db, 'alias', alias));
    if (snap.exists() && snap.get('email')) return String(snap.get('email'));
  } catch {
    // Sin permiso o sin red: se deja que falle el acceso con su propio error.
  }
  return '';
}

export async function entrarConClave(usuarioOCorreo, clave) {
  if (modoLocal()) return local.entrarConClave(usuarioOCorreo, clave);
  if (!String(usuarioOCorreo || '').trim()) throw new Error('Escribe tu usuario o tu correo.');
  if (!clave) throw new Error('Escribe tu contraseña.');

  const correo = await resolverCorreo(usuarioOCorreo);
  if (!correo) {
    throw new Error(
      `No hay ningún usuario «${String(usuarioOCorreo).trim()}». Revisa cómo lo ` +
      'escribiste, o entra con tu correo completo.',
    );
  }
  try {
    const cred = await signInWithEmailAndPassword(auth, correo, clave);
    return cred.user;
  } catch (e) {
    // Una cuenta creada con Google no TIENE contraseña, así que Firebase
    // rechaza cualquiera que se escriba. Decir «usuario o contraseña
    // incorrectos» es engañoso: las credenciales no están mal, es que esa
    // cuenta no entra por aquí. Quien no cae en eso se da por bloqueado.
    if (/invalid-credential|wrong-password|user-not-found/.test(e?.code || '')
        && await entraConGoogle(usuarioOCorreo, correo)) {
      throw new Error(
        `La cuenta ${correo} entra con el botón «Entrar con Google», no con ` +
        'contraseña. Es la de más abajo en esta misma pantalla. Si necesitas ' +
        'una contraseña, pídele a un administrador que te la cree.',
      );
    }
    throw e;
  }
}

/** ¿Esa cuenta se creó entrando con Google? Lo dice su alias, que sí se puede leer. */
async function entraConGoogle(entrada, correo) {
  const candidatos = [
    normalizarAlias(entrada),
    normalizarAlias(String(correo).split('@')[0]),
  ].filter((a) => a.length >= 3);

  for (const alias of new Set(candidatos)) {
    try {
      const snap = await getDoc(doc(db, 'alias', alias));
      if (snap.exists() && snap.get('email') === correo) {
        return snap.get('tipoAcceso') === 'GOOGLE';
      }
    } catch { /* sin permiso o sin red: se deja el error original */ }
  }
  return false;
}

/**
 * Registro desde la pantalla de acceso.
 *
 * Nace SIEMPRE desactivado. Cualquiera que llegue al enlace puede pedir acceso,
 * y es un administrador quien decide: así el registro es cómodo sin que abra la
 * puerta a nadie. Hasta que lo activen, la cuenta existe pero no ve ni un dato.
 */
export async function registrarse({ nombre, apellido, usuario, correo, clave }) {
  if (modoLocal()) return local.registrarse({ nombre, apellido, usuario, correo, clave });
  const alias = normalizarAlias(usuario);
  const email = String(correo || '').trim().toLowerCase();
  const nom = limpiarNombre(nombre);
  const ape = limpiarNombre(apellido);

  if (!nom || !ape) throw new Error('Escribe tu nombre y tu apellido.');
  if (alias.length < 3) {
    throw new Error('El usuario necesita al menos 3 caracteres: letras, números, punto o guion.');
  }
  if (!pareceCorreo(email)) throw new Error('Escribe un correo electrónico válido.');
  if (!clave || clave.length < 6) {
    throw new Error('La contraseña necesita al menos 6 caracteres.');
  }

  const yaEsta = await getDoc(doc(db, 'alias', alias));
  if (yaEsta.exists()) {
    throw new Error(`El usuario «${alias}» ya está tomado. Prueba con otro.`);
  }

  // Una sesion separada evita que observarSesion() intente completar la
  // ficha y cerrar la sesion ANTES de que termine este registro.
  const appRegistro = initializeApp(firebaseConfig, 'registro-' + Date.now());
  const authRegistro = getAuth(appRegistro);
  const dbRegistro = initializeFirestore(appRegistro, {}, DATABASE_ID);
  try {
    const cred = await createUserWithEmailAndPassword(authRegistro, email, clave);
    const completo = `${nom} ${ape}`;
    await updateProfile(cred.user, { displayName: completo });
    // Ficha y alias se confirman juntos. Si otro registro toma el alias,
    // las reglas rechazan el lote entero: nunca se le entrega otra identidad.
    const lote = writeBatch(dbRegistro);
    lote.set(doc(dbRegistro, 'usuarios', cred.user.uid), {
      uid: cred.user.uid, email, usuario: alias, nombre: completo, foto: null,
      rol: 'OPERADOR', activo: false, tipoAcceso: 'CLAVE',
      creadoEn: serverTimestamp(),
    });
    lote.set(doc(dbRegistro, 'alias', alias), { email, uid: cred.user.uid, tipoAcceso: 'CLAVE' });
    await lote.commit();
    return { usuario: alias, email, nombre: completo };
  } finally {
    try { await signOut(authRegistro); } finally { await deleteApp(appRegistro); }
  }
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
export async function crearOperario({ usuario, correo, clave, nombre, rol = 'OPERADOR' }) {
  if (modoLocal()) return local.crearOperario({ usuario, correo, clave, nombre, rol });
  const alias = normalizarAlias(usuario);
  const email = String(correo || '').trim().toLowerCase();
  if (alias.length < 3) {
    throw new Error('El usuario necesita al menos 3 caracteres.');
  }
  if (!pareceCorreo(email)) {
    throw new Error('Escribe un correo electrónico válido para esta persona.');
  }
  if (!clave || clave.length < 6) {
    throw new Error('La contraseña necesita al menos 6 caracteres.');
  }
  if (!['OPERADOR', 'SUPERVISOR', 'ADMIN'].includes(rol)) {
    throw new Error('Rol no válido.');
  }

  const yaEsta = await getDoc(doc(db, 'alias', alias));
  if (yaEsta.exists()) throw new Error(`El usuario «${alias}» ya está tomado.`);

  const secundaria = initializeApp(firebaseConfig, 'alta-' + Date.now());
  try {
    const authSec = getAuth(secundaria);
    let cred;
    try {
      cred = await createUserWithEmailAndPassword(authSec, email, clave);
    } catch (e) {
      // La cuenta de acceso ya existe. No es «ya está dado de alta»: lo que
      // suele faltar es la ficha, y desde aquí no se puede escribir porque el
      // identificador de esa cuenta no se puede consultar desde el navegador.
      // El camino es que la persona entre una vez; al hacerlo, su ficha nace y
      // queda esperando aprobación.
      if (e?.code === 'auth/email-already-in-use') {
        const aviso = new Error(
          `Ya existe una cuenta de acceso para ${email}, pero puede que le falte ` +
          'la ficha. Envíale el correo para que ponga su contraseña: al entrar, ' +
          'su ficha aparecerá aquí esperando aprobación.',
        );
        aviso.code = 'CUENTA_EXISTENTE';
        aviso.email = email;
        throw aviso;
      }
      throw e;
    }
    const nombreFinal = limpiarNombre(nombre) || alias;
    await updateProfile(cred.user, { displayName: nombreFinal });

    // El perfil lo escribe el administrador con SU sesión: el operario recién
    // creado todavía no tiene permiso para nada. Y nace ACTIVO, porque el alta
    // ya la está haciendo quien decide.
    await setDoc(doc(db, 'usuarios', cred.user.uid), {
      uid: cred.user.uid,
      email,
      usuario: alias,
      nombre: nombreFinal,
      foto: null,
      rol,
      activo: true,
      tipoAcceso: 'CLAVE',
      creadoEn: serverTimestamp(),
    });
    await setDoc(doc(db, 'alias', alias), { email, uid: cred.user.uid });

    await signOut(authSec);
    return { uid: cred.user.uid, usuario: alias, email, nombre: nombreFinal, rol };
  } finally {
    await deleteApp(secundaria).catch(() => {});
  }
}

/**
 * Manda el correo para poner una contraseña nueva.
 *
 * Es la salida del callejón: una cuenta de acceso que existe sin ficha. La
 * persona pone su contraseña, entra, y al entrar nace su ficha —desactivada— en
 * la cola de aprobación. Nadie tiene que saber la contraseña anterior, que es
 * lo que lo hacía irresoluble desde el panel.
 */
export async function enviarRestablecimiento(correo) {
  const email = String(correo || '').trim().toLowerCase();
  if (!pareceCorreo(email)) throw new Error('Escribe un correo electrónico válido.');
  await sendPasswordResetEmail(auth, email);
  return email;
}

const limpiarNombre = (v) => String(v || '').replace(/\s+/g, ' ').trim().slice(0, 80);

/** Cambio de contraseña por el propio operario. Google exige la actual. */
export async function cambiarClave(claveActual, claveNueva) {
  if (modoLocal()) return local.cambiarClave(claveActual, claveNueva);
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
  // En el servidor no hay proveedores de Google: se entra con usuario y
  // contraseña y punto. Sin esto la pantalla lo daría por DESCONOCIDO y
  // escondería el cambio de contraseña a quien sí puede cambiarla.
  if (modoLocal()) return 'CLAVE';
  const ids = (usuario?.providerData || []).map((p) => p.providerId);
  if (ids.includes('google.com')) return 'GOOGLE';
  if (ids.includes('password')) return 'CLAVE';
  return 'DESCONOCIDO';
}

export async function salir() {
  if (modoLocal()) return local.salir();
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
export async function asegurarPerfil(usuario, { pedirUsuario } = {}) {
  const ref = doc(db, 'usuarios', usuario.uid);
  const snap = await getDoc(ref);

  if (snap.exists()) {
    return { ...snap.data(), nuevo: false };
  }

  // Quien entra con contraseña y no tiene ficha pasa a la cola de aprobación.
  //
  // Antes esto era un error sin salida, y la salida tampoco estaba por el otro
  // lado: el administrador intentaba darlo de alta y Firebase le respondía «ya
  // existe un usuario con ese correo», porque la cuenta de acceso SÍ existía —
  // lo que faltaba era la ficha—. La persona no podía entrar y el administrador
  // no podía crearla. Callejón sin salida por los dos extremos.
  //
  // Una contraseña no verifica quién es nadie, así que la ficha nace
  // DESACTIVADA: entra en la misma cola que el registro abierto y la aprueba un
  // supervisor, que es quien puede comprobarlo.
  if (tipoDeAcceso(usuario) === 'CLAVE') {
    const alias = await asegurarAlias(usuario, '', 'CLAVE');
    const pendiente = {
      uid: usuario.uid,
      email: usuario.email,
      usuario: alias || '',
      nombre: limpiarNombre(usuario.displayName) || usuario.email,
      foto: null,
      rol: 'OPERADOR',
      activo: false,
      tipoAcceso: 'CLAVE',
      creadoEn: serverTimestamp(),
    };
    await setDoc(ref, pendiente);
    return { ...pendiente, nuevo: true };
  }

  // Alta automática al entrar con Google, solo para el dominio corporativo: ahí
  // Google ya verificó quién es, así que no hace falta que lo apruebe nadie.
  // Cualquier otro correo tiene que pasar por el registro y por un administrador.
  if (!dominioValido(usuario.email)) {
    throw new Error(
      `${usuario.email} no está registrado en la aplicación. Usa «Registrarse» ` +
      'en la pantalla de acceso y pide que te activen.',
    );
  }

  // Se le pregunta el usuario, si quien llama sabe preguntar.
  //
  // La pantalla de acceso pasa `pedirUsuario`; el resto de las pantallas no,
  // porque un diálogo a mitad de una validación no tiene sentido. Sin él se
  // deriva del correo y ya está: lo importante es que NADIE acabe sin alias.
  const sugerido = normalizarAlias(String(usuario.email || '').split('@')[0]);
  let elegido = '', nombreDado = '';
  if (typeof pedirUsuario === 'function') {
    try {
      const r = await pedirUsuario({
        email: usuario.email,
        nombre: usuario.displayName || '',
        sugerido,
      });
      if (r) {
        elegido = normalizarAlias(r.usuario || '');
        nombreDado = limpiarNombre(r.nombre || '');
      }
    } catch {
      // Que falle el diálogo no puede dejar a nadie fuera: se sigue con la
      // sugerencia, igual que antes de que existiera esta pregunta.
    }
  }

  // Primero el alias, después la ficha: el alias puede estar cogido y hay que
  // saber cuál quedó para escribirlo en la ficha. Al contrario, la ficha diría
  // un usuario con el que no se puede entrar.
  const alias = await asegurarAlias(usuario, elegido);

  const perfil = {
    uid: usuario.uid,
    email: usuario.email,
    usuario: alias || '',
    nombre: nombreDado || usuario.displayName || usuario.email,
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
 * Rellena lo que falte en la ficha de quien ya existía.
 *
 * Las cuentas creadas con Google antes de que la ficha llevara `usuario`
 * quedaron sin ninguno: en la lista de usuarios salían con un guion y, al
 * cerrar sesión, no tenían nada que teclear. Esto les pone el alias que ya
 * tenían reservado —o uno nuevo— la primera vez que vuelven a entrar.
 */
export async function completarPerfil(usuario, perfil) {
  if (!perfil || perfil.usuario) return perfil;
  try {
    const alias = await asegurarAlias(usuario, '', tipoDeAcceso(usuario));
    if (!alias) return perfil;
    await setDoc(doc(db, 'usuarios', usuario.uid), { usuario: alias }, { merge: true });
    return { ...perfil, usuario: alias };
  } catch {
    return perfil;      // sin permiso o sin red: se queda como estaba
  }
}

/**
 * Reserva un alias para quien entró con Google.
 *
 * Sale de la parte del correo antes de la arroba. Si ya está tomado por otra
 * persona se le añade un número: no se puede listar la colección —las reglas lo
 * impiden a propósito, para que nadie saque el directorio de la empresa—, así
 * que se prueban candidatos de uno en uno.
 *
 * `tipoAcceso` queda escrito aquí porque el alias SÍ se puede leer sin haber
 * entrado, y es lo que permite decirle a alguien «esa cuenta entra con Google»
 * en vez de «usuario o contraseña incorrectos».
 */
async function asegurarAlias(usuario, sugerencia = '', tipoAcceso = 'GOOGLE') {
  const base = normalizarAlias(String(usuario.email || '').split('@')[0]);
  const pedido = normalizarAlias(sugerencia);

  // El que pidió la persona va primero; el del correo es el respaldo, y los
  // numerados detrás para cuando los dos están cogidos.
  const candidatos = [];
  if (pedido.length >= 3) candidatos.push(pedido);
  if (base.length >= 3 && base !== pedido) candidatos.push(base);
  if (!candidatos.length) return null;
  const raiz = candidatos[0];
  for (let i = 2; i <= 20; i++) candidatos.push(`${raiz}${i}`);

  for (const alias of candidatos) {
    try {
      const snap = await getDoc(doc(db, 'alias', alias));
      if (snap.exists()) {
        if (snap.get('uid') === usuario.uid) return alias;   // ya era suyo
        continue;                                            // de otra persona
      }
      await setDoc(doc(db, 'alias', alias), {
        email: usuario.email, uid: usuario.uid, tipoAcceso,
      });
      return alias;
    } catch {
      // Que no se pueda reservar no puede impedir entrar: el botón de Google
      // sigue funcionando. Solo se queda sin alias.
      return null;
    }
  }
  return null;
}

/**
 * Observa la sesión.
 *
 * @param {(estado: object) => void} alCambiar
 *   Recibe { usuario, perfil, error } — `usuario` null si no hay sesión.
 */
export function observarSesion(alCambiar, { pedirUsuario } = {}) {
  if (modoLocal()) return local.observarSesion(estado=>{import('./barra-supervision.js?v=20261022-64').then(m=>m.iniciarBarra(estado)).catch(()=>{});return alCambiar(estado);});
  return onAuthStateChanged(auth, async (usuario) => {
    if (!usuario) return alCambiar({ usuario: null, perfil: null });

    // Quien decide quién entra es el perfil, no el dominio del correo.
    //
    // El registro acepta cualquier correo real —incluido un gmail— porque
    // fabricar `usuario@itsanet.com` es inventarse una dirección que quizá no
    // existe. A cambio, toda cuenta nueva nace desactivada y la activa un
    // administrador: la puerta está, solo que la abre una persona.
    try {
      let perfil = await asegurarPerfil(usuario, { pedirUsuario });
      if (perfil.activo === false) {
        await salir();
        return alCambiar({
          usuario: null, perfil: null,
          error: 'Tu cuenta todavía no está activada. Un supervisor tiene que ' +
                 'aprobarla; en cuanto lo haga, entras con el mismo usuario y contraseña.',
        });
      }
      perfil = await completarPerfil(usuario, perfil);
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
      'Ese correo ya tiene cuenta. Entra con el correo y tu contraseña; si faltaba la ficha, se creará pendiente de aprobación.',
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
