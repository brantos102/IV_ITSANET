#!/usr/bin/env node
/**
 * Pruebas del adaptador contra el contrato real de la API de Depot:
 *   GET /gettoken/            -> token
 *   GET /getstock/{codigo}    -> un producto   (cabecera `token`)
 *   GET /getstock/            -> todo el stock
 */
'use strict';
const { ItsanetDepotAdapter, extraerTokenItsanet, mapearStock, filasDe } =
  require('../src/depot-itsanet');

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

const BASE = 'https://dominio.com/apidepot';

/** WMS simulado con el contrato de la captura. */
function nuevoWms(opciones = {}) {
  const estado = {
    gettoken: 0, getstock: 0, tokenActual: null, revocado: false,
    formatoToken: opciones.formatoToken || 'json',
    catalogo: opciones.catalogo || [
      { codigo_producto: '2H0525345', descripcion: 'WASHER', codigo_barra: '7501234567890', stock: 12 },
      { codigo_producto: '6Q09598589B9', descripcion: 'INTERRUPTOR', codigo_barra: 'DEFAULT', stock: 4 },
      { codigo_producto: '6EA853651H9B9', descripcion: 'CALANDRA DEL', stock: 0 },
    ],
  };

  const fetchFn = async (url, init = {}) => {
    const cab = init.headers || {};

    if (url.includes('/gettoken/')) {
      estado.gettoken += 1;
      estado.tokenActual = 'TK-' + estado.gettoken;
      estado.revocado = false;
      const cuerpos = {
        json: JSON.stringify({ token: estado.tokenActual }),
        plano: estado.tokenActual,
        comillas: `"${estado.tokenActual}"`,
        array: JSON.stringify([{ token_id: estado.tokenActual }]),
        vacio: '',
      };
      return { ok: true, status: 200, text: async () => cuerpos[estado.formatoToken] };
    }

    // getstock: el token va en la cabecera `token`, no en Authorization
    if (cab.Authorization) {
      return { ok: false, status: 401, text: async () => 'use la cabecera token' };
    }
    if (estado.revocado || cab.token !== estado.tokenActual) {
      return { ok: false, status: 401, text: async () => '' };
    }

    estado.getstock += 1;
    const m = url.match(/\/getstock\/(.*)$/);
    const codigo = m && m[1] ? decodeURIComponent(m[1]) : '';

    if (!codigo) {   // código opcional -> catálogo completo
      return { ok: true, status: 200, text: async () => JSON.stringify(estado.catalogo) };
    }
    const fila = estado.catalogo.find((f) => f.codigo_producto === codigo ||
                                             f.codigo_barra === codigo);
    return fila
      ? { ok: true, status: 200, text: async () => JSON.stringify([fila]) }
      : { ok: true, status: 200, text: async () => '[]' };
  };

  return { estado, fetchFn };
}

/** Almacén compartido del token, en memoria. */
function nuevoAlmacen() {
  let reg = null;
  return {
    async leer() { return reg; },
    async guardar(r) { reg = r; },
    async borrar() { reg = null; },
  };
}

(async () => {
console.log('\nLectura del token');
await test('acepta JSON, texto plano, entrecomillado y array', () => {
  eq(extraerTokenItsanet('{"token":"ABC"}'), 'ABC');
  eq(extraerTokenItsanet('ABC'), 'ABC');
  eq(extraerTokenItsanet('"ABC"'), 'ABC');
  eq(extraerTokenItsanet('[{"token_id":"ABC"}]'), 'ABC');
  eq(extraerTokenItsanet('  '), null);
});

for (const formato of ['json', 'plano', 'comillas', 'array']) {
  await test(`obtiene el token con respuesta en formato "${formato}"`, async () => {
    const { estado, fetchFn } = nuevoWms({ formatoToken: formato });
    const api = new ItsanetDepotAdapter({ baseUrl: BASE }, null, fetchFn);
    eq(await api.obtenerToken(), 'TK-1');
    eq(estado.gettoken, 1);
  });
}

await test('respuesta sin token reconocible avisa qué revisar', async () => {
  const { fetchFn } = nuevoWms({ formatoToken: 'vacio' });
  const api = new ItsanetDepotAdapter({ baseUrl: BASE }, null, fetchFn);
  const e = await lanza(() => api.obtenerToken(), 'RESPUESTA_INESPERADA');
  ok(/formato/.test(e.message), 'el mensaje debe orientar al administrador');
});

console.log('\nCabecera correcta');
await test('el token va en la cabecera `token`, no en Authorization', async () => {
  const { fetchFn } = nuevoWms();
  const api = new ItsanetDepotAdapter({ baseUrl: BASE }, null, fetchFn);
  const cab = await api.cabeceras();
  eq(cab.token, 'TK-1');
  ok(!cab.Authorization, 'mandarlo como Bearer daría 401 sin explicar por qué');
});

console.log('\nConsulta de producto');
await test('encuentra por código de producto', async () => {
  const { fetchFn } = nuevoWms();
  const api = new ItsanetDepotAdapter({ baseUrl: BASE }, null, fetchFn);
  const p = await api.buscarPorCodigo('2h0-525345');
  eq(p.sku, '2H0525345');
  eq(p.descripcion, 'WASHER');
  eq(p.ean, '7501234567890');
  eq(p.stock, 12);
});

await test('encuentra por código de barras', async () => {
  const { fetchFn } = nuevoWms();
  const api = new ItsanetDepotAdapter({ baseUrl: BASE }, null, fetchFn);
  eq((await api.buscarPorCodigo('7501234567890')).sku, '2H0525345');
});

await test('DEFAULT no se toma como código de barras', async () => {
  const { fetchFn } = nuevoWms();
  const api = new ItsanetDepotAdapter({ baseUrl: BASE }, null, fetchFn);
  eq((await api.buscarPorCodigo('6Q09598589B9')).ean, null);
});

await test('un código inexistente devuelve null, no error', async () => {
  const { fetchFn } = nuevoWms();
  const api = new ItsanetDepotAdapter({ baseUrl: BASE }, null, fetchFn);
  eq(await api.buscarPorCodigo('NOEXISTE999'), null);
});

console.log('\nCatálogo completo (el código es opcional)');
await test('getstock sin código trae todo el catálogo en una llamada', async () => {
  const { estado, fetchFn } = nuevoWms();
  const api = new ItsanetDepotAdapter({ baseUrl: BASE }, null, fetchFn);
  const cat = await api.descargarCatalogo();
  eq(cat.length, 3);
  eq(estado.getstock, 1, 'una sola llamada');
  eq(cat.map((p) => p.sku), ['2H0525345', '6Q09598589B9', '6EA853651H9B9']);
});

await test('con muchos códigos baja el catálogo en vez de pedir uno a uno', async () => {
  const catalogo = Array.from({ length: 300 }, (_, i) =>
    ({ codigo_producto: 'SKU' + i, descripcion: 'Pieza ' + i, stock: i }));
  const { estado, fetchFn } = nuevoWms({ catalogo });
  const api = new ItsanetDepotAdapter({ baseUrl: BASE }, null, fetchFn);

  const codigos = catalogo.slice(0, 67).map((f) => f.codigo_producto);
  const m = await api.buscarLote(codigos);
  eq(estado.getstock, 1, 'llamadas a getstock');
  eq(m.size, 67);
  eq(m.get('SKU5').descripcion, 'Pieza 5');
});

await test('con pocos códigos consulta uno a uno', async () => {
  const { estado, fetchFn } = nuevoWms();
  const api = new ItsanetDepotAdapter({ baseUrl: BASE }, null, fetchFn);
  await api.buscarLote(['2H0525345', '6Q09598589B9']);
  eq(estado.getstock, 2);
});

await test('el catálogo deduplica filas repetidas del mismo producto', async () => {
  const { fetchFn } = nuevoWms({ catalogo: [
    { codigo_producto: 'A1', descripcion: 'Uno', stock: 5 },
    { codigo_producto: 'A1', descripcion: 'Uno', stock: 3 },   // otra ubicación
  ] });
  const api = new ItsanetDepotAdapter({ baseUrl: BASE }, null, fetchFn);
  eq((await api.descargarCatalogo()).length, 1);
});

console.log('\nReutilización del token');
await test('un solo gettoken para 50 consultas', async () => {
  const { estado, fetchFn } = nuevoWms();
  const api = new ItsanetDepotAdapter({ baseUrl: BASE }, null, fetchFn);
  for (let i = 0; i < 50; i++) await api.buscarPorCodigo('2H0525345');
  eq(estado.gettoken, 1, 'llamadas a gettoken');
  eq(estado.getstock, 50);
  eq(api.metricas.aciertosCache, 49);
});

await test('otra instancia reutiliza el token del almacén compartido', async () => {
  const { estado, fetchFn } = nuevoWms();
  const almacen = nuevoAlmacen();
  await new ItsanetDepotAdapter({ baseUrl: BASE }, almacen, fetchFn).obtenerToken();
  eq(estado.gettoken, 1);
  const api2 = new ItsanetDepotAdapter({ baseUrl: BASE }, almacen, fetchFn);
  eq(await api2.obtenerToken(), 'TK-1');
  eq(estado.gettoken, 1, 'no debe pedir otro token');
});

await test('un token revocado se renueva y la consulta se reintenta sola', async () => {
  const { estado, fetchFn } = nuevoWms();
  const api = new ItsanetDepotAdapter({ baseUrl: BASE }, null, fetchFn);
  await api.buscarPorCodigo('2H0525345');
  eq(estado.gettoken, 1);

  estado.revocado = true;
  const p = await api.buscarPorCodigo('2H0525345');
  eq(estado.gettoken, 2, 'debe pedir un token nuevo');
  ok(p && p.sku === '2H0525345', 'y la consulta debe acabar funcionando');
  eq(api.metricas.reintentos401, 1);
});

await test('un token vencido se renueva', async () => {
  const { estado, fetchFn } = nuevoWms();
  const api = new ItsanetDepotAdapter({ baseUrl: BASE, ttlHoras: 12 }, null, fetchFn);
  await api.obtenerToken();
  api.tokenMemoria.venceEn = Date.now() - 1;
  await api.obtenerToken();
  eq(estado.gettoken, 2);
});

console.log('\nDiagnóstico para el panel');
await test('informa cada paso por separado', async () => {
  const { fetchFn } = nuevoWms();
  const api = new ItsanetDepotAdapter({ baseUrl: BASE }, null, fetchFn);
  const d = await api.diagnostico('2H0525345');
  ok(d.ok, 'debe salir bien');
  eq(d.pasos.map((p) => p.paso), ['gettoken', 'getstock']);
  eq(d.pasos[1].producto.descripcion, 'WASHER');
  ok(!JSON.stringify(d).includes('TK-'), 'el token NO debe aparecer en el diagnóstico');
});

await test('si falla gettoken no intenta getstock y lo dice', async () => {
  const fetchFn = async () => ({ ok: false, status: 401, text: async () => '' });
  const api = new ItsanetDepotAdapter({ baseUrl: BASE }, null, fetchFn);
  const d = await api.diagnostico('X');
  ok(!d.ok);
  eq(d.pasos.length, 1, 'no debe seguir al paso siguiente');
  eq(d.pasos[0].codigo, 'NO_AUTORIZADO');
});

await test('WMS inalcanzable no se confunde con credencial mala', async () => {
  const fetchFn = async () => { throw new Error('ECONNREFUSED'); };
  const api = new ItsanetDepotAdapter({ baseUrl: BASE }, null, fetchFn);
  await lanza(() => api.obtenerToken(), 'NO_DISPONIBLE');
});

console.log('\nMapeo de campos');
await test('tolera las variantes de nombre del WMS', () => {
  eq(mapearStock({ CodProducto: 'A1', Descripcion: 'Uno' }).sku, 'A1');
  eq(mapearStock({ codigo: 'A2', nombre: 'Dos' }).sku, 'A2');
  eq(mapearStock({ sku: '  A3 ', detalle: 'Tres' }).sku, 'A3');
  eq(mapearStock({ sinCodigo: 1 }), null);
});
await test('encuentra la lista venga como venga envuelta', () => {
  eq(filasDe([1, 2]).length, 2);
  eq(filasDe({ data: [1] }).length, 1);
  eq(filasDe({ Table: [1, 2, 3] }).length, 3);
  eq(filasDe({ codigo: 'A' }).length, 1, 'un objeto suelto es una fila');
});

console.log(`\n${pasadas} pasadas, ${falladas} falladas`);
process.exit(falladas ? 1 : 0);
})();
