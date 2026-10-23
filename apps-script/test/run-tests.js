#!/usr/bin/env node
/**
 * Pruebas de la logica Apps Script, ejecutando los .gs reales sobre el
 * simulador de servicios.   node test/run-tests.js
 */
'use strict';
const path = require('path');
const stub = require('./gas-stub.js');

const SRC = path.join(__dirname, '..', 'src');
const FUENTES = ['Config.gs', 'Util.gs', 'Eventos.gs', 'Depot.gs', 'Codigo.gs', 'Cierre.gs', 'Kpi.gs'];

let pasadas = 0, falladas = 0;
const fallos = [];

function test(nombre, fn) {
  try { fn(); pasadas++; console.log(`  ok   ${nombre}`); }
  catch (e) { falladas++; fallos.push({ nombre, e }); console.log(`  FALLA ${nombre}\n       ${e.message}`); }
}
function eq(a, b, msg) {
  const x = JSON.stringify(a), y = JSON.stringify(b);
  if (x !== y) throw new Error(`${msg || 'esperado'}: ${y}, obtenido: ${x}`);
}
function ok(c, msg) { if (!c) throw new Error(msg || 'condicion falsa'); }

stub.cargarFuentes(SRC, FUENTES);

const ID_BASE = CFG.LIBRO_BASE;
const ID_PL = 'PL-VW-TEST';

const CAB_PL = ['ITEM', 'Descripción', 'ReferenciaPedido', 'Factura', 'Cantidad', 'PrecioUnit',
  'PrecioTotal', 'Numerodepiezareemplazo', 'Embarque', 'Cantidad Física', 'Validación',
  'PALLET', 'CODIGO BARRA', 'COD/PROD', 'OBSERVACION', 'ok'];

/** Packing list con los casos reales: SKU repetido, faltante y cantidad 0. */
function nuevoPackingList() {
  return new stub.Sheet('REV', [
    CAB_PL.slice(),
    ['2H0525345', 'WASHER', 'RABR260402', '5025609525', 1, 34.8, 34.8, ' ', 'RB48529'],
    ['6Q09598589B9', 'INTERRUPTOR', 'RABR260402', '5025609525', 2, 5.2, 10.4, ' ', 'RB48529'],
    ['6Q09598589B9', 'INTERRUPTOR', 'RABR260402', '5025609525', 1, 5.2, 5.2, ' ', 'RB48529'],
    ['6Q09598589B9', 'INTERRUPTOR', 'RABR260402', '5025609525', 1, 5.2, 5.2, ' ', 'RB48529'],
    ['6EA839885A', 'SOPORTE MANIJA', 'RABR260601', '5025619645', 1, 6.53, 6.53, ' ', 'RB48688'],
    ['6EA853651H9B9', 'CALANDRA DEL', 'RABR260215', '5025609525', 5, 34.56, 172.8, ' ', 'RB48529'],
  ]);
}

function entorno() {
  stub.reset();
  _maestroCache = null;
  if (typeof _esperadoCache !== 'undefined') for (const k in _esperadoCache) delete _esperadoCache[k];

  stub.registrarLibro(ID_BASE, [
    new stub.Sheet('Historial', [
      ['id', 'fecha', 'nombre', 'estado', 'url', 'fileId'],
      ['CONT-1', new Date('2026-06-29T08:00:00'), '29-06-2026 VW.xlsx', 'Pendiente Validación',
       'http://drive/' + ID_PL, ID_PL],
    ]),
    new stub.Sheet('MAESTRO', [
      ['cliente_id', 'producto_id', 'codigo_producto', 'descripcion', 'codigo_barra', 'unidad_id'],
      ['VENTURA', '2H0525345', '', 'WASHER', '', 'CS'],
      ['VENTURA', ' 6Q09598589B9', '', 'INTERRUPTOR ELEVAVIDRIOS', '', 'CS'],
      ['VENTURA', '6EA839885A', '', 'SOPORTE MANIJA', '', 'CS'],
      ['VENTURA', '6EA853651H9B9', '', 'CALANDRA DEL', '', 'CS'],
      ['VENTURA', '6EA853651XXXX', '', 'CALANDRA VARIANTE', '', 'CS'],
    ]),
  ]);
  stub.registrarLibro(ID_PL, [nuevoPackingList()]);
}

// ==========================================================================
console.log('\nNormalizacion');
entorno();
test('normalizarSku quita el \\xa0 del maestro real', () => {
  eq(normalizarSku_(' 6Q09598589B9'), '6Q09598589B9');
  eq(normalizarSku_(' 2h0-525345 '), '2H0525345');
});
test('pallets alfanumericos y subpallets', () => {
  ok(palletValido_('A1') && palletValido_('B04.3'), 'deben ser validos');
  ok(!palletValido_('B 04..3') && !palletValido_(''), 'deben ser invalidos');
  eq(palletPadre_('B04.3'), 'B04');
});
test('sanearCelda quita acentos y simbolos', () => {
  eq(sanearCelda_('Descripción ñandú — ok!'), 'DESCRIPCION NANDU OK');
});

// ==========================================================================
console.log('\nValidacion contra Depot (requerimiento 2, 3 y 4)');
entorno();
test('SKU existente devuelve OK', () => {
  const r = resolverCodigo_('2H0525345');
  ok(r.existe, 'debe existir'); eq(r.accion, ACCION_OK);
});
test('SKU del maestro con \\xa0 igual se encuentra', () => {
  ok(resolverCodigo_('6Q09598589B9').existe, 'el \\xa0 no debe impedir el cruce');
});
test('SKU inexistente con parecidos pide validar a profundidad', () => {
  const r = resolverCodigo_('6EA853651ZZZZ');
  ok(!r.existe, 'no debe existir');
  eq(r.accion, ACCION_REVISAR);
  ok(r.candidatos.length > 0, 'debe proponer candidatos');
});
test('SKU inexistente sin parecidos pide crearlo', () => {
  const r = resolverCodigo_('ZZZZ999999');
  eq(r.accion, ACCION_CREAR);
  ok(/EAN/.test(r.mensaje), 'debe pedir el EAN');
});

// ==========================================================================
console.log('\nConteo y concurrencia (requerimiento 8)');
entorno();
test('dos operadores suman sin pisarse', () => {
  const a = registrarConteo({ fileId: ID_PL, codigo: '6Q09598589B9', cantidad: 2,
    pallet: 'B04', operador: 'Juan' });
  ok(a.exito, a.mensaje);
  const b = registrarConteo({ fileId: ID_PL, codigo: '6Q09598589B9', cantidad: 2,
    pallet: 'B04.1', operador: 'Maria' });
  ok(b.exito, b.mensaje);
  eq(contadoDeSku_(ID_PL, '6Q09598589B9'), 4, 'total del SKU');
  eq(eventosDe_(ID_PL).length, 2, 'un evento por conteo');
});
test('el candado se libera siempre', () => {
  ok(!LockService._estaTomado(), 'quedo tomado tras los conteos');
  registrarConteo({ fileId: ID_PL, codigo: 'NOEXISTE', cantidad: 0, pallet: 'A1' });
  ok(!LockService._estaTomado(), 'quedo tomado tras un error');
});

entorno();
test('idempotencia: el doble disparo del lector no suma dos veces', () => {
  const p = { fileId: ID_PL, codigo: '2H0525345', cantidad: 1, pallet: 'B04', idem: 'k-1' };
  const a = registrarConteo(p), b = registrarConteo(p);
  ok(a.exito && b.exito, 'ambas deben responder bien');
  ok(b.datos.duplicado, 'la segunda debe marcarse duplicada');
  eq(contadoDeSku_(ID_PL, '2H0525345'), 1, 'solo debe contar una vez');
});

entorno();
test('sobrante exige confirmacion explicita', () => {
  const r = registrarConteo({ fileId: ID_PL, codigo: '2H0525345', cantidad: 3, pallet: 'B04' });
  ok(!r.exito, 'debe rechazarse'); eq(r.codigo, 'CONFIRMAR_SOBRANTE');
  eq(contadoDeSku_(ID_PL, '2H0525345'), 0, 'no debe registrar nada');
  const r2 = registrarConteo({ fileId: ID_PL, codigo: '2H0525345', cantidad: 3,
    pallet: 'B04', confirmarSobrante: true });
  ok(r2.exito, 'confirmado debe pasar');
  eq(contadoDeSku_(ID_PL, '2H0525345'), 3);
});

entorno();
test('pallet invalido se rechaza', () => {
  const r = registrarConteo({ fileId: ID_PL, codigo: '2H0525345', cantidad: 1, pallet: 'A 1..2' });
  eq(r.codigo, 'PALLET_INVALIDO');
});
test('mal estado fisico exige observacion', () => {
  const r = registrarConteo({ fileId: ID_PL, codigo: '2H0525345', cantidad: 1,
    pallet: 'B01', estadoFisico: 'MALO' });
  eq(r.codigo, 'OBSERVACION_REQUERIDA');
  const r2 = registrarConteo({ fileId: ID_PL, codigo: '2H0525345', cantidad: 1, pallet: 'B01',
    estadoFisico: 'MALO', observacion: 'P.N.C. PRODUCTO DOBLADO' });
  ok(r2.exito, r2.mensaje);
});

entorno();
test('anulacion es evento compensatorio, no borrado', () => {
  const a = registrarConteo({ fileId: ID_PL, codigo: '2H0525345', cantidad: 1, pallet: 'B04' });
  const r = anularConteo(ID_PL, a.datos.eventoId, 'conteo erroneo', 'Supervisor');
  ok(r.exito, r.mensaje);
  eq(contadoDeSku_(ID_PL, '2H0525345'), 0, 'el total vuelve a 0');
  eq(eventosDe_(ID_PL).length, 2, 'el evento original sigue ahi');
  eq(anularConteo(ID_PL, a.datos.eventoId, 'otra vez', 'Sup').codigo, 'YA_ANULADO');
});

// ==========================================================================
console.log('\nPallets y sugerencia (requerimientos 6 y 7)');
entorno();
test('un SKU puede quedar en varios pallets', () => {
  registrarConteo({ fileId: ID_PL, codigo: '6EA853651H9B9', cantidad: 3, pallet: 'B03', operador: 'Juan' });
  registrarConteo({ fileId: ID_PL, codigo: '6EA853651H9B9', cantidad: 2, pallet: 'B03.1', operador: 'Maria' });
  const u = ubicacionesDeSku_(ID_PL, '6EA853651H9B9');
  eq(u.map((x) => x.pallet), ['B03', 'B03.1'], 'mayor cantidad primero');
  eq(u.map((x) => x.cantidad), [3, 2]);
});
test('el lookup sugiere donde ya se guardo ESE SKU', () => {
  const r = lookupCodigo(ID_PL, '6EA853651H9B9');
  ok(r.exito, r.mensaje);
  eq(r.datos.palletSugerido, 'B03');
  ok(r.datos.avisos.some((a) => /ya fue guardado en/.test(a)), 'debe avisar donde esta');
});

// ==========================================================================
console.log('\nSobrante fuera del packing list (el caso real de VW)');
entorno();
test('SKU ausente del packing list se puede registrar', () => {
  const r = lookupCodigo(ID_PL, '6EA837885A');
  ok(r.exito, r.mensaje);
  ok(!r.datos.enPackingList, 'no esta en la lista');
  ok(r.datos.avisos.some((a) => /SOBRANTE/.test(a)), 'debe advertir sobrante');
  const c = registrarConteo({ fileId: ID_PL, codigo: '6EA837885A', cantidad: 1, pallet: 'B04.3',
    observacion: 'SOBRANTE CONFIRMADO', confirmarSobrante: true, operador: 'Supervisor' });
  ok(c.exito, c.mensaje);
  eq(contadoDeSku_(ID_PL, '6EA837885A'), 1);
});
test('queda registrado como pendiente de crear en Depot', () => {
  const p = skusPendientesDepot();
  ok(p.exito && p.datos.some((x) => x.sku === '6EA837885A'), 'debe aparecer en PENDIENTES');
});

// ==========================================================================
console.log('\nCierre y packing list final');
entorno();
test('reproduce el resultado de la recepcion real', () => {
  // Todo correcto salvo 6EA839885A (faltante) y un sobrante fuera de lista.
  registrarConteo({ fileId: ID_PL, codigo: '2H0525345', cantidad: 1, pallet: 'B04.1', operador: 'Juan' });
  registrarConteo({ fileId: ID_PL, codigo: '6Q09598589B9', cantidad: 4, pallet: 'B04.1', operador: 'Juan' });
  registrarConteo({ fileId: ID_PL, codigo: '6EA853651H9B9', cantidad: 3, pallet: 'B03', operador: 'Maria' });
  registrarConteo({ fileId: ID_PL, codigo: '6EA853651H9B9', cantidad: 2, pallet: 'B03.1', operador: 'Maria' });
  registrarConteo({ fileId: ID_PL, codigo: '6EA837885A', cantidad: 1, pallet: 'B04.3',
    observacion: 'SOBRANTE CONFIRMADO', confirmarSobrante: true, operador: 'Supervisor' });

  const r = finalizarRecepcionConfirmada(ID_PL, null, '1h 20m', 'Supervisor');
  ok(r.exito, r.mensaje);
  eq(r.datos.faltante, 1, 'un faltante');
  eq(r.datos.sobrante, 1, 'un sobrante');
  eq(r.datos.ok, 3, 'tres SKU correctos');
  // El packing list declara 11 unidades (1+2+1+1+1+5).
  eq(r.datos.unidadesEsperadas, 11);
  // 11 - 1 del faltante + 1 del sobrante = 11.
  eq(r.datos.unidadesFisicas, 11);
  eq(r.datos.diferencia, 0, 'el faltante y el sobrante se compensan');
});

test('regla "no anadir filas": una fila por linea original', () => {
  const hoja = SpreadsheetApp.openById(ID_PL).getSheets()[0];
  // 6 lineas originales + 1 sobrante fuera de lista, al final.
  eq(hoja.getLastRow(), 8, 'filas totales (cabecera + 6 + 1 sobrante)');
  eq(hoja.getRange(8, CFG.COL_SKU).getValue(), '6EA837885A', 'el sobrante va al final');
  eq(hoja.getRange(8, CFG.COL_CANTIDAD).getValue(), 0, 'con cantidad 0');
});

test('regla "1 SKU en dos pallets, misma celda"', () => {
  const hoja = SpreadsheetApp.openById(ID_PL).getSheets()[0];
  eq(hoja.getRange(7, CFG.COL_PALLET).getValue(), 'B03 / B03.1');
  ok(/SKU EN 2 PALLETS/.test(hoja.getRange(7, CFG.COL_OBSERVACION).getValue()),
     'debe desglosar los pallets en la observacion');
});

test('faltante confirmado se distingue de no contado', () => {
  const hoja = SpreadsheetApp.openById(ID_PL).getSheets()[0];
  eq(hoja.getRange(6, CFG.COL_VALIDACION).getValue(), 'Faltante');
  ok(/FALTANTE CONFIRMADO/.test(hoja.getRange(6, CFG.COL_OBSERVACION).getValue()));
});

test('columna ok refleja la existencia en Depot', () => {
  const hoja = SpreadsheetApp.openById(ID_PL).getSheets()[0];
  eq(hoja.getRange(2, CFG.COL_OK).getValue(), 'ok', 'SKU en el maestro');
  eq(hoja.getRange(8, CFG.COL_OK).getValue(), '#N/A', 'SKU ausente del maestro');
});

test('cierre sin recepcion en el Historial no envia correo ni cierra', () => {
  entorno();
  const r = finalizarRecepcionConfirmada('OTRO-ID-QUE-NO-ESTA', null, '1m', 'X');
  ok(!r.exito, 'debe fallar');
  eq(stub.correosEnviados.length, 0, 'no debe enviar reporte');
});

// ==========================================================================
console.log('\nKPIs historicos (requerimiento 9)');
entorno();
test('agrega por recepcion, operador y SKU', () => {
  registrarConteo({ fileId: ID_PL, codigo: '2H0525345', cantidad: 1, pallet: 'B01', operador: 'Juan' });
  registrarConteo({ fileId: ID_PL, codigo: '6Q09598589B9', cantidad: 3, pallet: 'B01', operador: 'Maria' });

  const g = kpisGlobales();
  ok(g.exito, g.mensaje);
  eq(g.datos.recepciones, 1);
  ok(g.datos.porRecepcion[0].operadores === 2, 'dos operadores');

  const o = kpisPorOperador();
  ok(o.exito && o.datos.length === 2, 'un registro por operador');
  const juan = o.datos.find((x) => x.nombre === 'Juan');
  eq(juan.unidades, 1); eq(juan.eventos, 1);

  const s = kpisPorSku(50, true);
  ok(s.exito, s.mensaje);
  ok(s.datos.some((x) => x.sku === '6Q09598589B9' && x.faltante === 1),
     '6Q09598589B9 debe figurar con faltante (3 de 4)');
});

// ==========================================================================
console.log(`\n${pasadas} pasadas, ${falladas} falladas`);
process.exit(falladas ? 1 : 0);
