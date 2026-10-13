#!/usr/bin/env node
/**
 * Pruebas del proxy de Depot, ejecutando Proxy.gs real sobre un simulador de
 * los servicios de Apps Script.   node test/proxy.test.js
 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

let pasadas = 0, falladas = 0;
const test = (n, fn) => { try { fn(); pasadas++; console.log('  ok    ' + n); }
  catch (e) { falladas++; console.log('  FALLA ' + n + '\n        ' + e.message); } };
function eq(a, b, m) { if (JSON.stringify(a) !== JSON.stringify(b))
  throw new Error(`${m || 'esperado'} ${JSON.stringify(b)}, obtenido ${JSON.stringify(a)}`); }
function ok(c, m) { if (!c) throw new Error(m || 'condición falsa'); }

/** Simulador de los servicios que usa el proxy. */
function entorno(opciones = {}) {
  const props = new Map(Object.entries({
    DEPOT_BASE_URL: 'http://dominio.com/apidepot',
    FIREBASE_API_KEY: 'AIza-demo',
    DOMINIO_PERMITIDO: 'itsanet.com',
    CARPETA_EVIDENCIAS: 'folder-123',
    ...(opciones.props || {}),
  }));
  const cache = new Map();
  const estado = {
    gettoken: 0, getstock: 0, lookups: 0, correos: [], archivos: [],
    tokenActual: null, revocado: false,
    formatoToken: opciones.formatoToken || 'json',
    catalogo: opciones.catalogo || [
      { codigo_producto: '2H0525345', descripcion: 'WASHER', codigo_barra: '7501234567890', stock: 12 },
      { codigo_producto: '6Q09598589B9', descripcion: 'INTERRUPTOR', codigo_barra: 'DEFAULT', stock: 4 },
    ],
    usuarioValido: opciones.usuarioValido !== false,
    correoUsuario: opciones.correoUsuario || 'juan@itsanet.com',
  };

  const resp = (codigo, texto) => ({
    getResponseCode: () => codigo, getContentText: () => texto,
  });

  const g = {
    PropertiesService: { getScriptProperties: () => ({
      getProperty: (k) => (props.has(k) ? props.get(k) : null),
      setProperty: (k, v) => props.set(k, v),
      deleteProperty: (k) => props.delete(k),
    }) },
    CacheService: { getScriptCache: () => ({
      get: (k) => (cache.has(k) ? cache.get(k) : null),
      put: (k, v) => cache.set(k, v),
      remove: (k) => cache.delete(k),
    }) },
    Utilities: {
      base64EncodeWebSafe: (b) => Buffer.from(b).toString('base64url'),
      computeDigest: (_a, s) => Buffer.from(require('crypto').createHash('sha256').update(s).digest()),
      DigestAlgorithm: { SHA_256: 1 },
      base64Decode: (s) => Buffer.from(s, 'base64'),
      newBlob: (d, t, n) => ({ datos: d, tipo: t, nombre: n }),
    },
    Logger: { log: () => {} },
    ContentService: {
      createTextOutput: (t) => ({ _t: t, setMimeType() { return this; }, getContent() { return this._t; } }),
      MimeType: { JSON: 'json' },
    },
    MailApp: {
      sendEmail: (o) => estado.correos.push(o),
      getRemainingDailyQuota: () => 1400,
    },
    DriveApp: {
      getFolderById: () => ({
        getFoldersByName: () => ({ hasNext: () => false }),
        createFolder: () => ({
          createFile: (b) => { estado.archivos.push(b); return {
            getId: () => 'file-1', getUrl: () => 'https://drive/file-1', setDescription() {},
          }; },
        }),
      }),
    },
    UrlFetchApp: {
      fetch(url, opts = {}) {
        // Verificación de sesión contra Firebase
        if (url.includes('identitytoolkit')) {
          estado.lookups += 1;
          return estado.usuarioValido
            ? resp(200, JSON.stringify({ users: [{ localId: 'uid-1',
                email: estado.correoUsuario, displayName: 'Juan Pérez' }] }))
            : resp(400, '{"error":"invalid"}');
        }
        const cab = opts.headers || {};
        if (url.includes('/gettoken/')) {
          estado.gettoken += 1;
          estado.tokenActual = 'TK-' + estado.gettoken;
          estado.revocado = false;
          const cuerpos = {
            json: JSON.stringify({ token: estado.tokenActual }),
            plano: estado.tokenActual,
            vacio: '',
          };
          return resp(200, cuerpos[estado.formatoToken]);
        }
        if (estado.revocado || cab.token !== estado.tokenActual) return resp(401, '');
        estado.getstock += 1;
        const m = url.match(/\/getstock\/(.*)$/);
        const codigo = m && m[1] ? decodeURIComponent(m[1]) : '';
        if (!codigo) return resp(200, JSON.stringify(estado.catalogo));
        const fila = estado.catalogo.find((f) => f.codigo_producto === codigo);
        return resp(200, JSON.stringify(fila ? [fila] : []));
      },
    },
  };

  const ctx = vm.createContext(g);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'proxy', 'Proxy.gs'), 'utf8'),
                  ctx, { filename: 'Proxy.gs' });
  return { ctx, estado, props, cache };
}

const peticion = (obj) => ({ postData: { contents: JSON.stringify({ idToken: 'tok', ...obj }) } });
const leer = (salida) => JSON.parse(salida.getContent());

console.log('\nSeguridad');
test('sin token de sesión no hace nada', () => {
  const { ctx, estado } = entorno();
  const r = leer(ctx.doPost({ postData: { contents: JSON.stringify({ accion: 'catalogo' }) } }));
  ok(!r.exito, 'debe fallar');
  ok(/token de sesión/i.test(r.mensaje), r.mensaje);
  eq(estado.gettoken, 0, 'no debe tocar Depot');
});

test('rechaza un correo fuera del dominio corporativo', () => {
  const { ctx, estado } = entorno({ correoUsuario: 'ajeno@gmail.com' });
  const r = leer(ctx.doPost(peticion({ accion: 'catalogo' })));
  ok(!r.exito);
  ok(/itsanet\.com/.test(r.mensaje), r.mensaje);
  eq(estado.getstock, 0, 'la API del WMS no debe quedar expuesta');
});

test('rechaza una sesión inválida', () => {
  const { ctx } = entorno({ usuarioValido: false });
  const r = leer(ctx.doPost(peticion({ accion: 'catalogo' })));
  ok(!r.exito);
  ok(/sesión/i.test(r.mensaje), r.mensaje);
});

test('la verificación de sesión se cachea', () => {
  const { ctx, estado } = entorno();
  for (let i = 0; i < 5; i++) ctx.doPost(peticion({ accion: 'catalogo' }));
  eq(estado.lookups, 1, 'verificaciones contra Google');
});

console.log('\nToken de Depot');
test('un solo gettoken para muchas llamadas', () => {
  const { ctx, estado } = entorno();
  for (let i = 0; i < 20; i++) ctx.doPost(peticion({ accion: 'producto', codigo: '2H0525345' }));
  eq(estado.gettoken, 1, 'llamadas a gettoken');
  eq(estado.getstock, 20);
});

test('el token sobrevive al caché usando las propiedades', () => {
  const { ctx, estado, cache } = entorno();
  ctx.doPost(peticion({ accion: 'catalogo' }));
  eq(estado.gettoken, 1);
  cache.clear();                       // el caché de Apps Script expira a las 6 h
  ctx.doPost(peticion({ accion: 'catalogo' }));
  eq(estado.gettoken, 1, 'debe salir de las propiedades, sin pedir otro');
});

test('un token revocado se renueva y la llamada se reintenta sola', () => {
  const { ctx, estado } = entorno();
  ctx.doPost(peticion({ accion: 'producto', codigo: '2H0525345' }));
  estado.revocado = true;
  const r = leer(ctx.doPost(peticion({ accion: 'producto', codigo: '2H0525345' })));
  eq(estado.gettoken, 2, 'debe pedir un token nuevo');
  ok(r.exito && r.producto && r.producto.sku === '2H0525345', 'y acabar funcionando');
});

test('respuesta sin token reconocible dice qué revisar', () => {
  const { ctx } = entorno({ formatoToken: 'vacio' });
  const r = leer(ctx.doPost(peticion({ accion: 'catalogo' })));
  ok(!r.exito);
  ok(/formato/.test(r.mensaje), r.mensaje);
});

test('el valor del token nunca sale en la respuesta', () => {
  const { ctx } = entorno();
  ctx.doPost(peticion({ accion: 'catalogo' }));
  const r = leer(ctx.doPost(peticion({ accion: 'estadoToken' })));
  ok(r.hayToken && r.vigente, 'debe informar que hay token');
  ok(!JSON.stringify(r).includes('TK-'), 'pero NO su valor');
  ok(r.minutosRestantes > 0);
});

console.log('\nCatálogo y producto');
test('el catálogo completo viene en una sola llamada', () => {
  const { ctx, estado } = entorno();
  const r = leer(ctx.doPost(peticion({ accion: 'catalogo' })));
  ok(r.exito);
  eq(r.productos.length, 2);
  eq(estado.getstock, 1, 'una sola llamada a getstock');
  eq(r.productos[0].descripcion, 'WASHER');
});

test('DEFAULT no se toma como código de barras', () => {
  const { ctx } = entorno();
  const r = leer(ctx.doPost(peticion({ accion: 'catalogo' })));
  eq(r.productos[1].ean, null);
});

test('normaliza el SKU con basura invisible', () => {
  const { ctx } = entorno({ catalogo: [
    { codigo_producto: '  2h0-525345 ', descripcion: 'Washer', stock: 1 } ] });
  const r = leer(ctx.doPost(peticion({ accion: 'catalogo' })));
  eq(r.productos[0].sku, '2H0525345');
});

test('un código inexistente devuelve producto null, no error', () => {
  const { ctx } = entorno();
  const r = leer(ctx.doPost(peticion({ accion: 'producto', codigo: 'NOEXISTE' })));
  ok(r.exito); eq(r.producto, null);
});

test('acción desconocida se rechaza', () => {
  const { ctx } = entorno();
  const r = leer(ctx.doPost(peticion({ accion: 'borrarTodo' })));
  ok(!r.exito); ok(/desconocida/.test(r.mensaje));
});

console.log('\nFotos e informe');
test('la foto va a Drive y devuelve enlace', () => {
  const { ctx, estado } = entorno();
  const r = leer(ctx.doPost(peticion({ accion: 'subirFoto', base64: 'QUJD',
    sku: '2H0525345', recepcion: 'VW-29-06', tipo: 'image/jpeg' })));
  ok(r.exito && r.fileId === 'file-1', 'debe crear el archivo');
  eq(estado.archivos.length, 1);
  ok(/\.jpg$/.test(estado.archivos[0].nombre), 'extensión según el tipo');
});

test('el informe se envía con las discrepancias', () => {
  const { ctx, estado } = entorno();
  const r = leer(ctx.doPost(peticion({ accion: 'enviarInforme',
    destinatarios: 'gerencia@itsanet.com', recepcion: 'VW-29-06', duracion: '1h 20m',
    resumen: { unidadesEsperadas: 103, unidadesFisicas: 103, exactitud: 97,
               ok: 65, faltante: 1, sobrante: 1,
               discrepancias: [{ sku: '6EA839885A', esperado: 1, fisico: 0,
                                 diferencia: -1, estado: 'Faltante' }] } })));
  ok(r.exito);
  eq(estado.correos.length, 1);
  const c = estado.correos[0];
  ok(c.htmlBody.includes('6EA839885A'), 'el SKU faltante debe aparecer');
  ok(c.htmlBody.includes('VW-29-06'));
  ok(c.subject.includes('VW-29-06'));
});

test('sin discrepancias el informe lo dice explícitamente', () => {
  const { ctx, estado } = entorno();
  ctx.doPost(peticion({ accion: 'enviarInforme', destinatarios: 'g@itsanet.com',
    resumen: { discrepancias: [] } }));
  ok(estado.correos[0].htmlBody.includes('cuadrado'), 'debe decir que cuadró');
});

test('verificarConfiguracion detecta lo que falta', () => {
  const { ctx } = entorno({ props: { DEPOT_BASE_URL: '', FIREBASE_API_KEY: '' } });
  const faltan = ctx.verificarConfiguracion();
  ok(faltan.includes('DEPOT_BASE_URL') && faltan.includes('FIREBASE_API_KEY'), faltan.join(','));
});

console.log(`\n${pasadas} pasadas, ${falladas} falladas`);
process.exit(falladas ? 1 : 0);
