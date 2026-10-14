/**
 * Carga los módulos del navegador en Node.
 *
 * Los módulos importan el SDK de Firebase desde gstatic, que no existe aquí.
 * Se reescribe ese import a un doble local y todo lo demás —incluido auth.js—
 * se carga tal cual, así la lógica pura se prueba sin red ni credenciales.
 */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const PUBLIC = path.join(AQUI, '..', 'public');

const STUB_SDK = `
export const doc = (...a) => ({ ruta: a.slice(1).join('/') });
export const collection = (...a) => ({ ruta: a.slice(1).join('/') });
/*
 * Lectura de UN documento.
 *
 * Lee de globalThis.__documentos, el mismo mapa que usa la transaccion. Antes
 * devolvia siempre «no existe», y con eso no se podia probar lo que pasa cuando
 * el alias que alguien pide ya es de otra persona: justo el caso en el que dos
 * operarios acaban compartiendo con que entran.
 */
export const getDoc = async (ref) => {
  const d = (globalThis.__documentos || {})[ref?.ruta] || null;
  return {
    exists: () => d !== null,
    data: () => d || {},
    get: (campo) => (d || {})[campo],
  };
};
/*
 * Lectura de colecciones.
 *
 * globalThis.__coleccion['ruta'] = [{ id, ...datos }] simula lo que hay. Las
 * clausulas where() NO se simulan: devuelve la coleccion entera. Para lo que se
 * prueba aqui es mas exigente, no menos, porque obliga a que el filtrado real
 * lo haga el codigo y no la consulta.
 */
export const getDocs = async (q) => {
  const ruta = Array.isArray(q) ? q.flat(9).find((x) => x && x.ruta)?.ruta : q?.ruta;
  const todos = (globalThis.__coleccion || {})[ruta] || [];
  return {
    size: todos.length,
    docs: todos.map((d) => ({
      id: d.id,
      ref: { ruta: ruta + '/' + d.id },
      data: () => d,
      get: (c) => d[c],
    })),
  };
};
/* globalThis.__sets recoge cada setDoc suelto: la forma de lo que se escribe
 * ya escondio un error una vez (el mapa de pallets) y no se ve en lo devuelto. */
export const setDoc = async (ref, datos, opciones) => {
  (globalThis.__sets = globalThis.__sets || []).push({ ruta: ref?.ruta, datos, opciones });
};
export const updateDoc = async () => {};
export const addDoc = async () => {};
export const deleteDoc = async () => {};
export const query = (...a) => a;
export const where = (...a) => a;
export const orderBy = (...a) => a;
export const limit = (...a) => a;
export const onSnapshot = () => () => {};
export const writeBatch = () => ({ set() {}, update() {}, delete() {}, commit: async () => {} });
export const serverTimestamp = () => '@ts';
/*
 * Transaccion que APUNTA lo que se escribe.
 *
 * Sin esto, una prueba solo puede comprobar lo que registrarConteo devuelve, y
 * el error que dejo la columna de pallets vacia estaba justo en la forma del
 * documento que se escribia, no en el valor devuelto.
 *
 * globalThis.__escrituras recoge cada set/update con su ruta y sus datos, y
 * globalThis.__documentos simula lo que ya hay en la base.
 */
export const runTransaction = async (db, fn) => {
  globalThis.__escrituras = [];
  const leer = (ref) => (globalThis.__documentos || {})[ref?.ruta] || null;
  return fn({
    get: async (ref) => {
      const d = leer(ref);
      return {
        exists: () => d !== null,
        data: () => d || {},
        get: (campo) => (d || {})[campo],
      };
    },
    set(ref, datos, opciones) {
      globalThis.__escrituras.push({ tipo: 'set', ruta: ref?.ruta, datos, opciones });
    },
    update(ref, datos) {
      globalThis.__escrituras.push({ tipo: 'update', ruta: ref?.ruta, datos });
    },
    delete() {},
  });
};
export const increment = (n) => ({ __inc: n });
export const arrayUnion = (...v) => ({ __union: v });
export const getFirestore = () => ({});
export const initializeFirestore = () => ({});
export const persistentLocalCache = () => ({});
export const persistentMultipleTabManager = () => ({});
export const enableIndexedDbPersistence = async () => {};
export const initializeApp = () => ({});
export const deleteApp = async () => {};
export const getAuth = () => ({ currentUser: null });
export class GoogleAuthProvider { setCustomParameters() {} }
export const signInWithPopup = async () => ({ user: null });
export const signInWithRedirect = async () => {};
export const getRedirectResult = async () => null;
export const signOut = async () => {};
export const onAuthStateChanged = () => () => {};
export const signInWithEmailAndPassword = async () => ({ user: null });
/* El alta puede fallar porque la cuenta ya exista: globalThis.__fallarAlta
 * pone ese codigo para poder probar la salida que se le ofrece. */
export const createUserWithEmailAndPassword = async (_auth, email) => {
  if (globalThis.__fallarAlta) {
    const e = new Error('simulado');
    e.code = globalThis.__fallarAlta;
    throw e;
  }
  return { user: { uid: 'nuevo', email } };
};
export const updatePassword = async () => {};
/* El correo de restablecimiento: se apunta a quien se mando, que es lo unico
 * comprobable sin un servidor de correo. */
export const sendPasswordResetEmail = async (_auth, email) => {
  (globalThis.__correos = globalThis.__correos || []).push(email);
};
export const updateProfile = async () => {};
export const reauthenticateWithCredential = async () => {};
export const EmailAuthProvider = { credential: () => ({}) };
`;

let dir = null;

/** Prepara una copia de ./public/js con los imports externos sustituidos. */
export function preparar() {
  if (dir) return dir;
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'iv-'));
  fs.writeFileSync(path.join(dir, 'sdk-stub.mjs'), STUB_SDK);

  // auth.js se carga TAL CUAL, no con un doble: así se prueban de verdad
  // `aCorreo`, `dominioValido` y la traducción de errores, que es donde el
  // operario se queda plantado cuando algo falla.
  for (const f of fs.readdirSync(path.join(PUBLIC, 'js'))) {
    if (!f.endsWith('.js')) continue;
    const codigo = fs.readFileSync(path.join(PUBLIC, 'js', f), 'utf8')
      .replace(/'https:\/\/www\.gstatic\.com\/firebasejs\/[^']+'/g, "'./sdk-stub.mjs'");
    fs.writeFileSync(path.join(dir, f), codigo);
  }
  return dir;
}

export function cargar(nombre) {
  return import('file://' + path.join(preparar(), nombre));
}

// --- utilidades de prueba, mismo estilo que el resto del proyecto --- //
export const estado = { pasadas: 0, falladas: 0 };

export function test(nombre, fn) {
  return Promise.resolve().then(fn)
    .then(() => { estado.pasadas++; console.log('  ok    ' + nombre); })
    .catch((e) => { estado.falladas++; console.log('  FALLA ' + nombre + '\n        ' + e.message); });
}
export function eq(a, b, msg) {
  if (JSON.stringify(a) !== JSON.stringify(b)) {
    throw new Error(`${msg || 'esperado'} ${JSON.stringify(b)}, obtenido ${JSON.stringify(a)}`);
  }
}
export function ok(c, msg) { if (!c) throw new Error(msg || 'condición falsa'); }

export function resumen() {
  console.log(`\n  ${estado.pasadas} pasadas, ${estado.falladas} falladas`);
  process.exit(estado.falladas ? 1 : 0);
}
