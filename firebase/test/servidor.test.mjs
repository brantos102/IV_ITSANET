#!/usr/bin/env node
/**
 * La capa de datos local contra el servidor DE VERDAD.
 *
 *     bash scripts/probar-extremo-a-extremo.sh
 *
 * Las demás pruebas del navegador usan un SDK de mentira, y las del servidor
 * llaman a Python directamente. Entre las dos queda un hueco: que las rutas, los
 * verbos y los nombres de campo coincidan. Un `/conteos` donde el servidor espera
 * `/conteo`, o un `porOrigen` que allí se llama `por_origen`, pasa las dos
 * suites y falla en el almacén.
 *
 * Esto levanta el servidor de verdad, con una base de pruebas, y ejecuta el
 * mismo `js/local.js` que corre en el handheld, con el `fetch` del navegador.
 *
 * Si no hay servidor levantado, se salta: no puede ser un requisito para poder
 * tocar una pantalla.
 */
import { test, eq, ok, resumen } from './cargador.mjs';

const BASE = process.env.SERVIDOR || 'http://127.0.0.1:8099';
const USUARIO = process.env.USUARIO_PRUEBA || 'sup';
const CLAVE = process.env.CLAVE_PRUEBA || '1111';

// El módulo decide el destino por la ruta de la página; aquí se fuerza, y se le
// da un `fetch` que apunta al servidor en vez de a un origen relativo.
globalThis.location = { pathname: '/app/validar.html', host: '127.0.0.1:8099' };
globalThis.document = { addEventListener() {}, removeEventListener() {},
                        visibilityState: 'visible' };
globalThis.localStorage = { getItem: () => 'local', setItem() {} };

const fetchReal = globalThis.fetch;
globalThis.fetch = (ruta, opciones) => fetchReal(BASE + ruta, opciones);

const vivo = await fetchReal(BASE + '/health').then((r) => r.ok).catch(() => false);
if (!vivo) {
  console.log(`  (saltada: no hay servidor en ${BASE})`);
  console.log('\n  0 pasadas, 0 falladas');
  process.exit(0);
}

const local = await import('../public/js/local.js');

// La sesión es una cookie; node no la guarda sola.
let galleta = '';
globalThis.fetch = async (ruta, opciones = {}) => {
  const r = await fetchReal(BASE + ruta, {
    ...opciones,
    headers: { ...(opciones.headers || {}), ...(galleta ? { Cookie: galleta } : {}) },
  });
  const puesta = r.headers.get('set-cookie');
  if (puesta) galleta = puesta.split(';')[0];
  return r;
};

const REC = 'REC' + Date.now().toString().slice(-7);
const LINEAS = Array.from({ length: 22 }, (_, i) => ({
  linea: i + 1, sku: `SKU${String(i + 1).padStart(3, '0')}`,
  descripcion: `PIEZA ${i + 1}`, cantidad: 10,
}));
const RESULTADO = {
  lineas: LINEAS,
  porSku: Object.fromEntries(LINEAS.map((l) => [l.sku, l.cantidad])),
  unidades: 220,
  encabezados: ['ITEM', 'COD. PRODUCTO', 'DESCRIPCION', 'CANTIDAD'],
  columnas: { sku: 1, cantidad: 3 },
  hoja: 'PACKING',
  embarques: ['RB48529'],
};

await test('se entra con usuario y contraseña, sin Firebase', async () => {
  eq(await local.entrarConClave(USUARIO, CLAVE), USUARIO);
  const yo = await local.sesionLocal();
  ok(yo, 'sin sesión no hay nada que probar');
  ok(yo.rol, 'el perfil trae el rol: es lo que decide qué ve cada pantalla');
});

await test('una contraseña mal puesta se distingue de una sesión caducada', async () => {
  const guardada = galleta;
  galleta = '';
  let codigo = null;
  try { await local.entrarConClave(USUARIO, 'noesesta'); }
  catch (e) { codigo = e.codigo; }
  eq(codigo, 'CREDENCIALES');
  galleta = guardada;
});

await test('se crea una recepción y se lee por su código', async () => {
  eq(await local.crearRecepcion({ codigo: REC, cliente: 'VENTURA' }), REC);
  const doc = await local.obtenerRecepcion(REC);
  eq(doc.id, REC);
  eq(doc.estado, 'ABIERTA');
});

await test('22 filas entran como 22 filas', async () => {
  const r = await local.guardarPackingList(REC, RESULTADO, null, {
    origen: 'PRINCIPAL', archivo: 'PACKING.xlsx',
    resumen: { huella: 'abc123', lineas: 22, skus: 22, unidades: 220,
               archivo: 'PACKING.xlsx' },
  });
  eq(r.lineas, 22);
  eq((await local.leerColeccion(REC, 'lineas')).length, 22);
  eq((await local.leerColeccion(REC, 'skus')).length, 22);
});

await test('el conteo vuelve con los nombres de campo que lee la pantalla', async () => {
  const r = await local.registrarConteo(REC, null, {
    idempotencyKey: 'ev1', sku: 'SKU001', cantidad: 6,
    pallet: 'A1-B04-C1', origen: 'PRINCIPAL', estadoFisico: 'OK',
  });
  eq(r.duplicado, false);
  eq(r.contado, 6);
  eq(r.pendiente, 4);
  eq(r.estado, 'FALTANTE');

  const s = (await local.leerColeccion(REC, 'skus')).find((x) => x.sku === 'SKU001');
  eq(s.pallets, { A1B04C1: 6 }, 'el mapa de pallets, con la misma codificación');
  eq(s.porOrigen, { PRINCIPAL: { A1B04C1: 6 } }, 'y el reparto por lista');
});

await test('repetir el envío no cuenta dos veces', async () => {
  const r = await local.registrarConteo(REC, null, {
    idempotencyKey: 'ev1', sku: 'SKU001', cantidad: 6, pallet: 'A1-B04-C1',
  });
  eq(r.duplicado, true);
  eq(r.contado, 6);
});

await test('un sobrante llega con el código que abre el diálogo', async () => {
  let e = null;
  try {
    await local.registrarConteo(REC, null, {
      idempotencyKey: 'ev2', sku: 'SKU002', cantidad: 99, pallet: 'A1',
    });
  } catch (err) { e = err; }
  ok(e, 'tiene que parar');
  eq(e.codigo, 'CONFIRMAR_SOBRANTE');
  ok(/declara 10/.test(e.message), e.message);
});

await test('anular escribe lo contrario en vez de borrar', async () => {
  const r = await local.anularConteo(REC, null, 'ev1', 'se contó dos veces');
  eq(r.contado, 0);
  const eventos = await local.leerBitacora(REC);
  eq(eventos.length, 2, 'el original sigue ahí');
});

await test('el duplicado de un packing list se reconoce por su contenido', async () => {
  const hallados = await local.buscarPackingListParecido(
    { huella: 'abc123', lineas: 22, skus: 22, unidades: 220, archivo: 'OTRO.xlsx' });
  ok(hallados.some((h) => h.recepcion === REC), 'cambiar el nombre no lo disfraza');
});

await test('escucharSkus avisa, aunque aquí haya que preguntar', async () => {
  const vistos = [];
  const parar = local.escucharSkus(REC, (skus) => vistos.push(skus.length), null, 50);
  await new Promise((r) => setTimeout(r, 200));
  parar();
  eq(vistos[0], 22, 'avisa una vez al empezar');
  eq(vistos.length, 1, 'y no vuelve a avisar si nada cambió');
});

await test('se cierra y queda el rastro', async () => {
  eq((await local.cerrarRecepcion(REC)).estado, 'CERRADA');
  const tipos = (await local.leerAuditoria(REC)).map((e) => e.tipo);
  ok(tipos.includes('CIERRE') && tipos.includes('ANULACION'), tipos.join(','));
});

await test('y una recepción cerrada no admite más conteos', async () => {
  let e = null;
  try {
    await local.registrarConteo(REC, null, {
      idempotencyKey: 'ev9', sku: 'SKU003', cantidad: 1, pallet: 'A1' });
  } catch (err) { e = err; }
  eq(e?.codigo, 'RECEPCION_CERRADA');
});

resumen();
