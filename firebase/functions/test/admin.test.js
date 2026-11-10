#!/usr/bin/env node
/** Pruebas del módulo de administración y del adaptador de Depot. */
'use strict';
const { FirestoreStub, FieldValueStub } = require('./firestore-stub');
const admin = require('../src/admin');
const { MockDepotAdapter, crearAdaptador, mapearProducto } = require('../src/depot');

const FV = { FieldValue: FieldValueStub };
let pasadas = 0, falladas = 0;
const test = (n, fn) => Promise.resolve().then(fn)
  .then(() => { pasadas++; console.log('  ok    ' + n); })
  .catch((e) => { falladas++; console.log('  FALLA ' + n + '\n        ' + e.message); });
function eq(a, b, m) { if (JSON.stringify(a) !== JSON.stringify(b))
  throw new Error(`${m || 'esperado'} ${JSON.stringify(b)}, obtenido ${JSON.stringify(a)}`); }
function ok(c, m) { if (!c) throw new Error(m || 'condición falsa'); }
async function lanza(fn, codigo) {
  try { await fn(); } catch (e) {
    if (codigo && e.codigo !== codigo) throw new Error(`esperaba ${codigo}, obtuvo ${e.codigo}: ${e.message}`);
    return e;
  }
  throw new Error('se esperaba un error ' + (codigo || ''));
}

/** Auth simulado. */
function nuevoAuth() {
  const usuarios = new Map();
  let n = 0;
  return {
    usuarios,
    claims: new Map(),
    revocados: [],
    async createUser(d) {
      if ([...usuarios.values()].some((u) => u.email === d.email)) {
        const e = new Error('ya existe'); e.code = 'auth/email-already-exists'; throw e;
      }
      const uid = 'uid-' + (++n);
      usuarios.set(uid, { uid, ...d });
      return { uid, ...d };
    },
    async setCustomUserClaims(uid, c) { this.claims.set(uid, c); },
    async updateUser(uid, d) { Object.assign(usuarios.get(uid), d); },
    async revokeRefreshTokens(uid) { this.revocados.push(uid); },
  };
}

const ctxAdmin = { uid: 'uid-root', rol: 'ADMIN' };
const ctxOperario = { uid: 'uid-op', rol: 'OPERADOR' };

(async () => {
console.log('\nOperarios');
await test('crea un operario con rol en los claims', async () => {
  const db = new FirestoreStub(), auth = nuevoAuth();
  const r = await admin.crearOperario(auth, db, ctxAdmin,
    { email: 'Juan@Itsanet.com ', nombre: 'Juan Pérez', rol: 'OPERADOR', clave: 'clave1234' }, FV);
  eq(r.email, 'juan@itsanet.com', 'el correo se normaliza a');
  eq(auth.claims.get(r.uid), { rol: 'OPERADOR', activo: true });
  const d = await db.doc('usuarios/' + r.uid).get();
  eq(d.get('nombre'), 'Juan Pérez');
  eq(d.get('creadoPorUid'), 'uid-root');
});

await test('un operario no puede crear usuarios', async () => {
  const db = new FirestoreStub(), auth = nuevoAuth();
  await lanza(() => admin.crearOperario(auth, db, ctxOperario,
    { email: 'x@y.com', nombre: 'Equis Ye', rol: 'ADMIN', clave: 'clave1234' }, FV), 'NO_AUTORIZADO');
});

await test('rechaza correo inválido, nombre corto, rol inexistente y clave débil', async () => {
  const db = new FirestoreStub(), auth = nuevoAuth();
  const c = (d) => admin.crearOperario(auth, db, ctxAdmin,
    { email: 'a@b.com', nombre: 'Nombre Largo', rol: 'OPERADOR', clave: 'clave1234', ...d }, FV);
  await lanza(() => c({ email: 'sin-arroba' }), 'EMAIL_INVALIDO');
  await lanza(() => c({ nombre: 'Jo' }), 'NOMBRE_INVALIDO');
  await lanza(() => c({ rol: 'JEFE' }), 'ROL_INVALIDO');
  await lanza(() => c({ clave: '123' }), 'CLAVE_DEBIL');
});

await test('desactivar revoca los tokens en el acto', async () => {
  const db = new FirestoreStub(), auth = nuevoAuth();
  const r = await admin.crearOperario(auth, db, ctxAdmin,
    { email: 'a@b.com', nombre: 'Ana Ruiz', rol: 'OPERADOR', clave: 'clave1234' }, FV);
  await admin.cambiarEstadoOperario(auth, db, ctxAdmin, { uid: r.uid, activo: false }, FV);
  eq(auth.claims.get(r.uid).activo, false);
  ok(auth.revocados.includes(r.uid), 'debe revocar los tokens vigentes');
  ok(auth.usuarios.get(r.uid).disabled === true, 'debe deshabilitar la cuenta');
});

await test('nadie puede desactivarse ni cambiarse el rol a sí mismo', async () => {
  const db = new FirestoreStub(), auth = nuevoAuth();
  await lanza(() => admin.cambiarEstadoOperario(auth, db, ctxAdmin,
    { uid: 'uid-root', activo: false }, FV), 'AUTO_BLOQUEO');
  await lanza(() => admin.cambiarRol(auth, db, ctxAdmin,
    { uid: 'uid-root', rol: 'OPERADOR' }, FV), 'AUTO_CAMBIO');
});

await test('cambiar el rol revoca el token viejo', async () => {
  const db = new FirestoreStub(), auth = nuevoAuth();
  const r = await admin.crearOperario(auth, db, ctxAdmin,
    { email: 'c@d.com', nombre: 'Carla Diaz', rol: 'OPERADOR', clave: 'clave1234' }, FV);
  await admin.cambiarRol(auth, db, ctxAdmin, { uid: r.uid, rol: 'SUPERVISOR' }, FV);
  eq(auth.claims.get(r.uid).rol, 'SUPERVISOR');
  ok(auth.revocados.includes(r.uid), 'el token viejo lleva el rol viejo: hay que revocarlo');
});

console.log('\nCredenciales de Depot');
await test('guarda el secreto aparte y solo expone una máscara', async () => {
  const db = new FirestoreStub(), sec = new admin.SecretMemoriaAdapter();
  await admin.guardarConfigDepot(sec, db, ctxAdmin, {
    baseUrl: 'https://wms.itsanet.com/api', cliente: 'VENTURA',
    token: 'tok_SUPERSECRETO_1234567890',
  }, FV);

  const pub = (await db.doc('config/depot').get()).data();
  eq(pub.baseUrl, 'https://wms.itsanet.com/api');
  eq(pub.tipoAuth, 'BEARER');
  ok(!JSON.stringify(pub).includes('SUPERSECRETO'), 'el secreto NO debe quedar en Firestore');
  ok(pub.credencialMascara.startsWith('to') && pub.credencialMascara.endsWith('90'),
     'la máscara deja reconocer la credencial sin revelarla');

  const cfg = await admin.cargarConfigDepot(sec, db);
  eq(cfg.token, 'tok_SUPERSECRETO_1234567890', 'el servidor sí puede leerla');
});

await test('rechaza http plano', async () => {
  const db = new FirestoreStub(), sec = new admin.SecretMemoriaAdapter();
  await lanza(() => admin.guardarConfigDepot(sec, db, ctxAdmin,
    { baseUrl: 'http://wms.local/api', token: 'x' }, FV), 'URL_INVALIDA');
});

await test('exige token o usuario y contraseña', async () => {
  const db = new FirestoreStub(), sec = new admin.SecretMemoriaAdapter();
  await lanza(() => admin.guardarConfigDepot(sec, db, ctxAdmin,
    { baseUrl: 'https://wms.local/api', usuario: 'juan' }, FV), 'SIN_CREDENCIAL');
});

await test('un supervisor no puede tocar las credenciales', async () => {
  const db = new FirestoreStub(), sec = new admin.SecretMemoriaAdapter();
  await lanza(() => admin.guardarConfigDepot(sec, db, { uid: 'u', rol: 'SUPERVISOR' },
    { baseUrl: 'https://x.com', token: 't' }, FV), 'NO_AUTORIZADO');
});

await test('probar conexión informa latencia y resultado', async () => {
  const db = new FirestoreStub(), sec = new admin.SecretMemoriaAdapter();
  await admin.guardarConfigDepot(sec, db, ctxAdmin,
    { baseUrl: 'https://wms.itsanet.com/api', token: 'tok12345678' }, FV);
  const fabrica = () => new MockDepotAdapter([
    { sku: '2H0525345', descripcion: 'WASHER', ean: '7501234567890' },
  ]);
  const r = await admin.probarConexionDepot(sec, db, ctxAdmin, { codigoPrueba: '2H0525345' }, fabrica);
  ok(r.ok && r.encontrado, 'debe encontrar el producto');
  eq(r.producto.descripcion, 'WASHER');
  ok(typeof r.ms === 'number', 'debe informar la latencia');
});

console.log('\nAdaptador de Depot');
await test('el mock resuelve por SKU, EAN y código alterno', async () => {
  const d = new MockDepotAdapter([{
    sku: '2H0525345', descripcion: 'WASHER', ean: '7501234567890',
    codigosAlternos: ['ALT-999'],
  }]);
  eq((await d.buscarPorCodigo('2h0-525345')).sku, '2H0525345', 'por SKU sucio');
  eq((await d.buscarPorCodigo('7501234567890')).sku, '2H0525345', 'por EAN');
  eq((await d.buscarPorCodigo('ALT999')).sku, '2H0525345', 'por código alterno');
  eq(await d.buscarPorCodigo('NOEXISTE'), null);
});

await test('la consulta en lote devuelve nulos para los que faltan', async () => {
  const d = new MockDepotAdapter([{ sku: 'A1', descripcion: 'Uno' }]);
  const m = await d.buscarLote(['A1', 'B2', 'a1']);
  eq(m.size, 2, 'deduplica');
  eq(m.get('A1').descripcion, 'Uno');
  eq(m.get('B2'), null);
});

await test('mapearProducto tolera distintos nombres de campo del WMS', async () => {
  eq(mapearProducto({ producto_id: '  X1 ', descripcion: 'Uno', codigo_barra: '123' }).sku, 'X1');
  eq(mapearProducto({ data: { sku: 'X2', description: 'Dos' } }).sku, 'X2');
  eq(mapearProducto({ itemCode: 'X3', nombre: 'Tres', barcode: 'DEFAULT' }).ean, null,
     'DEFAULT no es un EAN');
  eq(mapearProducto({ sinCodigo: 1 }), null);
});

await test('sin baseUrl se usa el mock, así se construye sin la API real', async () => {
  const a = crearAdaptador(null);
  eq(a.constructor.name, 'MockDepotAdapter');
});

console.log(`\n${pasadas} pasadas, ${falladas} falladas`);
process.exit(falladas ? 1 : 0);
})();
