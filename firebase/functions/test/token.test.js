#!/usr/bin/env node
/** Pruebas de obtención y reutilización del token de Depot. */
'use strict';
const { FirestoreStub } = require('./firestore-stub');
const { TokenProvider, calcularVencimiento, extraerToken, RUTA_TOKEN } = require('../src/token');
const { HttpDepotAdapter } = require('../src/depot');

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

/** WMS simulado: cuenta logins y consultas, puede caducar o revocar el token. */
function nuevoWms(opciones = {}) {
  const estado = {
    logins: 0, consultas: 0, rechazos401: 0,
    tokenActual: null, revocado: false,
    expiresIn: opciones.expiresIn,            // segundos; undefined = no informa
    ...opciones,
  };
  const fetchFn = async (url, init = {}) => {
    if (url.includes('/auth/login')) {
      estado.logins += 1;
      const cuerpo = JSON.parse(init.body || '{}');
      if (cuerpo.usuario !== 'wms_user' || cuerpo.clave !== 'wms_pass') {
        return { ok: false, status: 401, json: async () => ({ error: 'bad creds' }) };
      }
      estado.tokenActual = 'tok-' + estado.logins;
      estado.revocado = false;
      const r = { access_token: estado.tokenActual };
      if (estado.expiresIn !== undefined) r.expires_in = estado.expiresIn;
      return { ok: true, status: 200, json: async () => r };
    }
    // Consulta de producto
    estado.consultas += 1;
    const auth = (init.headers || {}).Authorization || '';
    const tokenUsado = auth.replace(/^Bearer /, '');
    if (estado.revocado || tokenUsado !== estado.tokenActual) {
      estado.rechazos401 += 1;
      return { ok: false, status: 401, json: async () => ({}) };
    }
    return { ok: true, status: 200,
             json: async () => ({ producto_id: 'SKU1', descripcion: 'PIEZA UNO' }) };
  };
  return { estado, fetchFn };
}

const CFG = {
  baseUrl: 'https://wms.itsanet.com/api',
  rutaLogin: '/auth/login',
  usuario: 'wms_user', clave: 'wms_pass',
};

(async () => {
console.log('\nCálculo del vencimiento');
await test('respeta expires_in del WMS, con margen', () => {
  const ahora = 1000000;
  const v = calcularVencimiento({ expires_in: 3600 }, { ahora });
  eq(v, ahora + 3600000 - 5 * 60 * 1000, 'una hora menos 5 min de margen');
});
await test('sin expires_in usa el tope configurado', () => {
  const ahora = 1000000;
  const v = calcularVencimiento({}, { ahora, ttlMaxMs: 12 * 3600 * 1000 });
  eq(v, ahora + 12 * 3600 * 1000 - 5 * 60 * 1000);
});
await test('no excede el tope aunque el WMS prometa más', () => {
  const ahora = 1000000;
  const v = calcularVencimiento({ expires_in: 86400 }, { ahora, ttlMaxMs: 3600 * 1000 });
  eq(v, ahora + 3600 * 1000 - 5 * 60 * 1000, 'se recorta al tope');
});
await test('acepta fecha absoluta', () => {
  const ahora = Date.parse('2026-10-13T08:00:00Z');
  const v = calcularVencimiento({ expires_at: '2026-10-13T20:00:00Z' }, { ahora });
  eq(v, Date.parse('2026-10-13T20:00:00Z') - 5 * 60 * 1000);
});
await test('extraerToken tolera distintos nombres de campo', () => {
  eq(extraerToken({ access_token: 'a' }), 'a');
  eq(extraerToken({ data: { token: 'b' } }), 'b');
  eq(extraerToken({ result: { jwt: 'c' } }), 'c');
  eq(extraerToken({ nada: 1 }), null);
});

console.log('\nReutilización (el punto de todo esto)');
await test('un solo login para 50 consultas seguidas', async () => {
  const db = new FirestoreStub();
  const { estado, fetchFn } = nuevoWms({ expiresIn: 86400 });
  const tp = new TokenProvider({ db, cfg: CFG, fetchFn });
  const api = new HttpDepotAdapter(CFG, tp);
  // El adaptador prueba dos rutas por código, así que son 2 consultas por búsqueda.
  for (let i = 0; i < 50; i++) await api.buscarPorCodigo('SKU1');
  eq(estado.logins, 1, 'logins contra el WMS');
  eq(tp.metricas.l1, 49, 'aciertos de caché en memoria');
  ok(estado.consultas >= 50, 'las consultas sí se hicieron');
});

await test('una instancia nueva reutiliza el token de Firestore, sin login', async () => {
  const db = new FirestoreStub();
  const { estado, fetchFn } = nuevoWms({ expiresIn: 86400 });
  const tp1 = new TokenProvider({ db, cfg: CFG, fetchFn });
  await tp1.obtener();
  eq(estado.logins, 1);

  // Arranque en frío: otra instancia, memoria vacía, misma base.
  const tp2 = new TokenProvider({ db, cfg: CFG, fetchFn });
  const t = await tp2.obtener();
  eq(estado.logins, 1, 'no debe volver a hacer login');
  eq(tp2.metricas.l2, 1, 'debe salir de la caché compartida');
  eq(t, 'tok-1');
});

await test('diez instancias en frío a la vez hacen UN login, no diez', async () => {
  const db = new FirestoreStub();
  const { estado, fetchFn } = nuevoWms({ expiresIn: 86400 });
  const proveedores = Array.from({ length: 10 },
    () => new TokenProvider({ db, cfg: CFG, fetchFn }));
  const tokens = await Promise.all(proveedores.map((p) => p.obtener()));
  eq(estado.logins, 1, 'logins contra el WMS');
  eq(new Set(tokens).size, 1, 'todas deben usar el mismo token');
});

await test('un token vencido se renueva', async () => {
  const db = new FirestoreStub();
  const { estado, fetchFn } = nuevoWms({ expiresIn: 3600 });
  let reloj = Date.parse('2026-10-13T08:00:00Z');
  const tp = new TokenProvider({ db, cfg: CFG, fetchFn, ahora: () => reloj });
  eq(await tp.obtener(), 'tok-1');
  reloj += 2 * 3600 * 1000;               // dos horas después
  eq(await tp.obtener(), 'tok-2', 'debe renovarse');
  eq(estado.logins, 2);
});

await test('reutiliza durante toda la jornada sin expires_in', async () => {
  const db = new FirestoreStub();
  const { estado, fetchFn } = nuevoWms();          // el WMS no informa vencimiento
  let reloj = Date.parse('2026-10-13T07:00:00Z');
  const tp = new TokenProvider({ db, cfg: { ...CFG, ttlHoras: 12 }, fetchFn, ahora: () => reloj });
  await tp.obtener();
  for (const h of [9, 12, 15, 17]) {              // jornada completa
    reloj = Date.parse(`2026-10-13T${String(h).padStart(2, '0')}:00:00Z`);
    await tp.obtener();
  }
  eq(estado.logins, 1, 'un solo login en toda la jornada');
});

console.log('\nRevocación y errores');
await test('un 401 renueva el token y reintenta una vez', async () => {
  const db = new FirestoreStub();
  const { estado, fetchFn } = nuevoWms({ expiresIn: 86400 });
  const tp = new TokenProvider({ db, cfg: CFG, fetchFn });
  const api = new HttpDepotAdapter(CFG, tp);
  await api.buscarPorCodigo('SKU1');
  eq(estado.logins, 1);

  estado.revocado = true;                 // el WMS revoca antes del vencimiento
  const p = await api.buscarPorCodigo('SKU1');
  eq(estado.logins, 2, 'debe pedir un token nuevo');
  ok(p && p.sku === 'SKU1', 'y la consulta debe acabar funcionando');
});

await test('credenciales malas fallan claro, sin bucle', async () => {
  const db = new FirestoreStub();
  const { estado, fetchFn } = nuevoWms();
  const tp = new TokenProvider({ db, cfg: { ...CFG, clave: 'incorrecta' }, fetchFn });
  await lanza(() => tp.obtener(), 'CREDENCIAL_INVALIDA');
  eq(estado.logins, 1, 'un solo intento: reintentar no arregla una clave mala');
});

await test('respuesta sin token reconocible avisa qué revisar', async () => {
  const db = new FirestoreStub();
  const fetchFn = async () => ({ ok: true, status: 200, json: async () => ({ sesion: 'abc' }) });
  const tp = new TokenProvider({ db, cfg: CFG, fetchFn });
  const e = await lanza(() => tp.obtener(), 'RESPUESTA_INESPERADA');
  ok(/campo/.test(e.message), 'el mensaje debe orientar al administrador');
});

await test('WMS inalcanzable no se confunde con credencial mala', async () => {
  const db = new FirestoreStub();
  const fetchFn = async () => { throw new Error('ECONNREFUSED'); };
  const tp = new TokenProvider({ db, cfg: CFG, fetchFn });
  await lanza(() => tp.obtener(), 'NO_DISPONIBLE');
});

await test('token fijo del panel no dispara ningún login', async () => {
  const db = new FirestoreStub();
  const { estado, fetchFn } = nuevoWms();
  const tp = new TokenProvider({ db, cfg: { baseUrl: CFG.baseUrl, token: 'fijo-123' }, fetchFn });
  eq(await tp.obtener(), 'fijo-123');
  eq(estado.logins, 0);
});

console.log('\nSeguridad y diagnóstico');
await test('el token nunca sale en el estado del panel', async () => {
  const db = new FirestoreStub();
  const { fetchFn } = nuevoWms({ expiresIn: 3600 });
  const tp = new TokenProvider({ db, cfg: CFG, fetchFn });
  await tp.obtener();
  const e = await tp.estado();
  ok(e.hayToken && e.vigente, 'debe informar que hay token vigente');
  ok(!JSON.stringify(e).includes('tok-1'), 'el valor del token NO debe aparecer');
  ok(e.minutosRestantes > 0 && e.minutosRestantes <= 60, 'informa minutos restantes');
});

await test('el token se guarda en _internal, fuera del alcance del cliente', async () => {
  const db = new FirestoreStub();
  const { fetchFn } = nuevoWms({ expiresIn: 3600 });
  await new TokenProvider({ db, cfg: CFG, fetchFn }).obtener();
  ok(db.docs.has(RUTA_TOKEN), 'debe estar en ' + RUTA_TOKEN);
  ok(RUTA_TOKEN.startsWith('_internal/'), 'la ruta debe ser interna');
});

console.log(`\n${pasadas} pasadas, ${falladas} falladas`);
process.exit(falladas ? 1 : 0);
})();
