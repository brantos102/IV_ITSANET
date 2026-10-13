/**
 * Carga los módulos del navegador en Node.
 *
 * Los módulos importan el SDK de Firebase desde gstatic y `db` desde auth.js,
 * que inicializa la app real. Aquí se reescriben esos imports a stubs locales,
 * así la lógica pura (normalización, reparto por línea, resumen) se prueba sin
 * red ni credenciales.
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
export const getDoc = async () => ({ exists: () => false, data: () => ({}), get: () => undefined });
export const getDocs = async () => ({ docs: [], size: 0 });
export const setDoc = async () => {};
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
export const runTransaction = async (db, fn) => fn({
  get: async () => ({ exists: () => false, data: () => ({}), get: () => undefined }),
  set() {}, update() {}, delete() {},
});
export const increment = (n) => ({ __inc: n });
export const getFirestore = () => ({});
export const initializeApp = () => ({});
export const getAuth = () => ({ currentUser: null });
`;

const STUB_AUTH = `export const db = {}; export const auth = { currentUser: null };
export const app = {};`;

let dir = null;

/** Prepara una copia de ./public/js con los imports externos sustituidos. */
export function preparar() {
  if (dir) return dir;
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'iv-'));
  fs.writeFileSync(path.join(dir, 'sdk-stub.mjs'), STUB_SDK);
  fs.writeFileSync(path.join(dir, 'auth.js'), STUB_AUTH);

  for (const f of fs.readdirSync(path.join(PUBLIC, 'js'))) {
    if (!f.endsWith('.js') || f === 'auth.js') continue;
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
