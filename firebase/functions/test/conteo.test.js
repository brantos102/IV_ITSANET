#!/usr/bin/env node
/**
 * Pruebas del registro de conteos sobre el simulador de Firestore.
 *   node test/conteo.test.js
 */
'use strict';
const { FirestoreStub, FieldValueStub } = require('./firestore-stub');
const conteo = require('../src/conteo');
const { registrarConteo, anularConteo, registrarAdicional, ErrorConteo } = conteo;

const FV = { FieldValue: FieldValueStub, Timestamp: null };
let pasadas = 0, falladas = 0;

function test(nombre, fn) {
  return Promise.resolve()
    .then(fn)
    .then(() => { pasadas++; console.log('  ok    ' + nombre); })
    .catch((e) => { falladas++; console.log('  FALLA ' + nombre + '\n        ' + e.message); });
}
function eq(a, b, msg) {
  if (JSON.stringify(a) !== JSON.stringify(b)) {
    throw new Error(`${msg || 'esperado'} ${JSON.stringify(b)}, obtenido ${JSON.stringify(a)}`);
  }
}
function ok(c, msg) { if (!c) throw new Error(msg || 'condición falsa'); }
async function lanza(fn, codigo) {
  try { await fn(); } catch (e) {
    if (codigo && e.codigo !== codigo) throw new Error(`esperaba ${codigo}, obtuvo ${e.codigo}: ${e.message}`);
    return e;
  }
  throw new Error('se esperaba un error' + (codigo ? ' ' + codigo : ''));
}

const REC = 'rec-vw';
function nuevaDb(skus = [{ sku: '6Q09598589B9', esperado: 4 }, { sku: '2H0525345', esperado: 1 }]) {
  const db = new FirestoreStub();
  db._escribir(`recepciones/${REC}`, { codigo: 'VW-29-06', estado: 'ABIERTA' }, false);
  for (const s of skus) {
    db._escribir(`recepciones/${REC}/skus/${s.sku}`,
      { sku: s.sku, esperado: s.esperado, contado: 0, pallets: {}, enPackingList: true }, false);
  }
  return db;
}
const ctx = (n) => ({ recepcionId: REC, uid: 'uid-' + n, email: n + '@itsanet.com', nombre: n });
let seq = 0;
const base = (extra) => ({ sku: '6Q09598589B9', cantidad: 1, pallet: 'B04',
  idempotencyKey: 'k' + (++seq), ...extra });

(async () => {
console.log('\nRegistro básico');
await test('un escaneo registra 1 unidad', async () => {
  const db = nuevaDb();
  const r = await registrarConteo(db, ctx('juan'), base(), FV);
  eq(r.contado, 1); eq(r.pendiente, 3); eq(r.estado, 'FALTANTE');
});

await test('cantidad pre-digitada registra de golpe', async () => {
  const db = nuevaDb();
  // El operario contó 4 físicamente, digitó 4 y escaneó una vez.
  const r = await registrarConteo(db, ctx('juan'), base({ cantidad: 4 }), FV);
  eq(r.contado, 4); eq(r.estado, 'OK'); eq(r.pendiente, 0);
  const evs = await db.collection(`recepciones/${REC}/eventos`).get();
  eq(evs.size, 1, 'un solo evento para');
});

await test('escaneos sucesivos acumulan', async () => {
  const db = nuevaDb();
  for (let i = 0; i < 4; i++) await registrarConteo(db, ctx('juan'), base(), FV);
  const s = await db.doc(`recepciones/${REC}/skus/6Q09598589B9`).get();
  eq(s.get('contado'), 4); eq(s.get('estado'), 'OK');
});

console.log('\nConcurrencia (requerimiento: sin cruces de datos)');
await test('dos operarios en el MISMO SKU suman sin perder conteos', async () => {
  const db = nuevaDb();
  await Promise.all([
    registrarConteo(db, ctx('juan'), base({ cantidad: 2, pallet: 'B04' }), FV),
    registrarConteo(db, ctx('maria'), base({ cantidad: 2, pallet: 'B04.1' }), FV),
  ]);
  const s = await db.doc(`recepciones/${REC}/skus/6Q09598589B9`).get();
  eq(s.get('contado'), 4, 'total del SKU');
  eq(conteo.decodificarPallets(s.get('pallets')), { B04: 2, 'B04.1': 2 }, 'desglose por pallet');
});

await test('20 escaneos simultáneos no pierden ninguno', async () => {
  const db = nuevaDb([{ sku: 'MASIVO', esperado: 20 }]);
  await Promise.all(Array.from({ length: 20 }, (_, i) =>
    registrarConteo(db, ctx('op' + (i % 4)),
      { sku: 'MASIVO', cantidad: 1, pallet: 'A' + (i % 3 + 1), idempotencyKey: 'm' + i }, FV)));
  const s = await db.doc(`recepciones/${REC}/skus/MASIVO`).get();
  eq(s.get('contado'), 20);
  const evs = await db.collection(`recepciones/${REC}/eventos`).get();
  eq(evs.size, 20, 'un evento por escaneo');
});

await test('una escritura concurrente fuerza el reintento, no la pérdida', async () => {
  const db = nuevaDb();
  // Simula que otro operario escribe justo entre la lectura y el commit.
  db.alLeerEnTransaccion = async () => {
    db._escribir(`recepciones/${REC}/skus/6Q09598589B9`,
      { contado: FieldValueStub.increment(1) }, true);
  };
  await registrarConteo(db, ctx('juan'), base({ cantidad: 1 }), FV);
  ok(db.transaccionesReintentadas > 0, 'debió reintentar');
  const s = await db.doc(`recepciones/${REC}/skus/6Q09598589B9`).get();
  eq(s.get('contado'), 2, 'el conteo del otro operario + el propio');
});

console.log('\nIdempotencia (doble disparo del lector)');
await test('la misma clave no suma dos veces', async () => {
  const db = nuevaDb();
  const p = base({ cantidad: 2, idempotencyKey: 'fija' });
  const a = await registrarConteo(db, ctx('juan'), p, FV);
  const b = await registrarConteo(db, ctx('juan'), p, FV);
  ok(!a.duplicado && b.duplicado, 'la segunda debe marcarse duplicada');
  const s = await db.doc(`recepciones/${REC}/skus/6Q09598589B9`).get();
  eq(s.get('contado'), 2);
});

await test('sin clave de idempotencia se rechaza', async () => {
  const db = nuevaDb();
  await lanza(() => registrarConteo(db, ctx('juan'),
    { sku: '2H0525345', cantidad: 1, pallet: 'A1' }, FV), 'IDEM_REQUERIDA');
});

console.log('\nValidaciones del flujo');
await test('sobrante exige confirmación explícita', async () => {
  const db = nuevaDb();
  await lanza(() => registrarConteo(db, ctx('juan'),
    base({ sku: '2H0525345', cantidad: 3 }), FV), 'CONFIRMAR_SOBRANTE');
  const s = await db.doc(`recepciones/${REC}/skus/2H0525345`).get();
  eq(s.get('contado'), 0, 'no debe registrar nada');
  const r = await registrarConteo(db, ctx('juan'),
    base({ sku: '2H0525345', cantidad: 3, confirmarSobrante: true }), FV);
  eq(r.estado, 'SOBRANTE'); eq(r.contado, 3);
});

await test('pallet inválido se rechaza', async () => {
  const db = nuevaDb();
  await lanza(() => registrarConteo(db, ctx('juan'), base({ pallet: 'A 1..2' }), FV), 'PALLET_INVALIDO');
});

await test('subpallet guarda su padre', async () => {
  const db = nuevaDb();
  await registrarConteo(db, ctx('juan'), base({ pallet: 'b04.3' }), FV);
  const evs = await db.collection(`recepciones/${REC}/eventos`).get();
  eq(evs.docs[0].get('pallet'), 'B04.3');
  eq(evs.docs[0].get('palletPadre'), 'B04');
});

await test('PNC exige foto y observación', async () => {
  const db = nuevaDb();
  await lanza(() => registrarConteo(db, ctx('juan'),
    base({ estadoFisico: 'PNC' }), FV), 'FOTO_REQUERIDA');
  await lanza(() => registrarConteo(db, ctx('juan'),
    base({ estadoFisico: 'PNC', fotos: ['evidencias/a.jpg'] }), FV), 'OBSERVACION_REQUERIDA');
  const r = await registrarConteo(db, ctx('juan'), base({
    estadoFisico: 'PNC', fotos: ['evidencias/a.jpg'], observacion: 'PRODUCTO DOBLADO' }), FV);
  eq(r.contado, 1);
  const s = await db.doc(`recepciones/${REC}/skus/6Q09598589B9`).get();
  eq(s.get('tienePnc'), true, 'el SKU queda marcado con PNC');
});

await test('cantidad absurda se rechaza (escaneo fuera del campo)', async () => {
  const db = nuevaDb();
  await lanza(() => registrarConteo(db, ctx('juan'),
    base({ cantidad: 6901234567890 }), FV), 'CANTIDAD_INVALIDA');
});

await test('recepción cerrada no admite conteos', async () => {
  const db = nuevaDb();
  db._escribir(`recepciones/${REC}`, { estado: 'CERRADA' }, true);
  await lanza(() => registrarConteo(db, ctx('juan'), base(), FV), 'RECEPCION_CERRADA');
});

await test('el primer conteo pasa la recepción a EN_VALIDACION', async () => {
  const db = nuevaDb();
  await registrarConteo(db, ctx('juan'), base(), FV);
  const r = await db.doc(`recepciones/${REC}`).get();
  eq(r.get('estado'), 'EN_VALIDACION');
});

console.log('\nIdentidad del operario');
await test('cada evento queda firmado con el uid y el correo del servidor', async () => {
  const db = nuevaDb();
  await registrarConteo(db, ctx('maria'), base(), FV);
  const evs = await db.collection(`recepciones/${REC}/eventos`).get();
  eq(evs.docs[0].get('operadorUid'), 'uid-maria');
  eq(evs.docs[0].get('operadorEmail'), 'maria@itsanet.com');
});

console.log('\nAnulación');
await test('es evento compensatorio, no borrado', async () => {
  const db = nuevaDb();
  const r = await registrarConteo(db, ctx('juan'), base({ cantidad: 3, idempotencyKey: 'anu' }), FV);
  await anularConteo(db, ctx('sup'), { eventoId: r.eventoId, motivo: 'conteo erróneo' }, FV);
  const s = await db.doc(`recepciones/${REC}/skus/6Q09598589B9`).get();
  eq(s.get('contado'), 0, 'el total vuelve a 0');
  eq(conteo.decodificarPallets(s.get('pallets')), { B04: 0 });
  const evs = await db.collection(`recepciones/${REC}/eventos`).get();
  eq(evs.size, 2, 'el evento original sigue ahí');
  await lanza(() => anularConteo(db, ctx('sup'),
    { eventoId: r.eventoId, motivo: 'otra vez' }, FV), 'YA_ANULADO');
});

await test('anular exige motivo', async () => {
  const db = nuevaDb();
  const r = await registrarConteo(db, ctx('juan'), base({ idempotencyKey: 'sm' }), FV);
  await lanza(() => anularConteo(db, ctx('sup'),
    { eventoId: r.eventoId, motivo: '  ' }, FV), 'MOTIVO_REQUERIDO');
});

console.log('\nAdicionales (regla: nunca una fila nueva)');
await test('un SKU fuera de la lista va a su propia colección', async () => {
  const db = nuevaDb();
  await registrarAdicional(db, ctx('sup'), {
    sku: '6EA837885A', descripcion: 'SOPORTE MANIJA', cantidad: 1, pallet: 'B04.3',
    motivo: 'Llegó físicamente sin estar en el packing list',
    idempotencyKey: 'adic-1',
  }, FV);

  const adic = await db.collection(`recepciones/${REC}/adicionales`).get();
  eq(adic.size, 1, 'un adicional');
  eq(adic.docs[0].get('motivo'), 'Llegó físicamente sin estar en el packing list');
  eq(adic.docs[0].get('detectadoPorEmail'), 'sup@itsanet.com');

  const s = await db.doc(`recepciones/${REC}/skus/6EA837885A`).get();
  eq(s.get('contado'), 1);
  eq(s.get('estado'), 'SOBRANTE');

  // Lo esencial: las líneas del packing list no se tocaron.
  const lineas = await db.collection(`recepciones/${REC}/skus`).get();
  const enLista = lineas.docs.filter((d) => d.get('enPackingList') === true);
  eq(enLista.length, 2, 'las líneas originales siguen siendo');
});

await test('un SKU que sí está en la lista no puede ser adicional', async () => {
  const db = nuevaDb();
  await lanza(() => registrarAdicional(db, ctx('sup'), {
    sku: '2H0525345', cantidad: 1, pallet: 'A1', motivo: 'x', idempotencyKey: 'ya',
  }, FV), 'YA_EN_LISTA');
});

await test('el adicional exige motivo', async () => {
  const db = nuevaDb();
  await lanza(() => registrarAdicional(db, ctx('sup'), {
    sku: 'NUEVO123', cantidad: 1, pallet: 'A1', idempotencyKey: 'sm2',
  }, FV), 'MOTIVO_REQUERIDO');
});

console.log(`\n${pasadas} pasadas, ${falladas} falladas`);
process.exit(falladas ? 1 : 0);
})();
