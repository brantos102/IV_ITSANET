#!/usr/bin/env node
/**
 * Pruebas del panel multi-cliente: credenciales separadas, un token por
 * cliente, y consultas que recorren varios.    node test/clientes.test.js
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

const BASE = 'https://ec.itsanet.com/q_apidepot';

/** WMS simulado con varios clientes, cada uno con su usuario y su catálogo. */
function entorno(opciones = {}) {
  const props = new Map(Object.entries({
    DEPOT_BASE_URL: BASE,
    FIREBASE_API_KEY: 'AIza-demo',
    FIREBASE_PROJECT_ID: 'iv-itsanet',
    FIREBASE_DATABASE_ID: 'bd-iv-itsanet',
    DOMINIO_PERMITIDO: 'itsanet.com',
    CARPETA_EVIDENCIAS: 'folder-1',
  }));
  const cache = new Map();

  // Campos tal como los devuelve el WMS real (según el Centro de Mando).
  const cuentas = opciones.cuentas || {
    VENTURA: { usuario: 'u_ventura', clave: 'p_ventura', catalogo: [
      { 'COD. PRODUCTO': '2H0525345', 'DESCRIPCION': 'WASHER', 'CANTIDAD': '12',
        'UNIDAD': 'CS', 'COD. CLIENTE': 'VENTURA', 'NAVE': 'A', 'CALLE': '01',
        'COLUMNA': '03', 'NIVEL': '2', 'NRO. LOTE': 'L1', 'FAMILIA': 'REPUESTOS' },
      { 'COD. PRODUCTO': 'COMPARTIDO', 'DESCRIPCION': 'DESDE VENTURA',
        'CANTIDAD': '1', 'COD. CLIENTE': 'VENTURA' },
    ] },
    BELIA: { usuario: 'u_belia', clave: 'p_belia', catalogo: [
      { 'COD. PRODUCTO': '9XX111', 'DESCRIPCION': 'PIEZA BELIA', 'CANTIDAD': '7',
        'COD. CLIENTE': 'BELIA' },
      { 'COD. PRODUCTO': 'COMPARTIDO', 'DESCRIPCION': 'DESDE BELIA',
        'CANTIDAD': '3', 'COD. CLIENTE': 'BELIA' },
    ] },
  };

  const estado = {
    gettoken: {}, getstock: {}, tokens: {}, caidos: new Set(),
    rol: opciones.rol || 'ADMIN', correoUsuario: opciones.correo || 'bryan@itsanet.com',
  };
  const resp = (c, t) => ({ getResponseCode: () => c, getContentText: () => t });

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
      // Lo necesita la lógica de token por día natural (hora de Ecuador).
      formatDate: (d, tz, fmt) => {
        const p = (n) => String(n).padStart(2, '0');
        const ec = new Date(d.getTime() - 5 * 3600 * 1000);   // GMT-5
        return fmt === 'yyyy-MM-dd'
          ? `${ec.getUTCFullYear()}-${p(ec.getUTCMonth() + 1)}-${p(ec.getUTCDate())}`
          : `${p(ec.getUTCHours())}:${p(ec.getUTCMinutes())}:${p(ec.getUTCSeconds())}`;
      },
    },
    Logger: { log: () => {} },
    ContentService: {
      createTextOutput: (t) => ({ _t: t, setMimeType() { return this; }, getContent() { return this._t; } }),
      MimeType: { JSON: 'json' },
    },
    MailApp: { sendEmail: () => {}, getRemainingDailyQuota: () => 100 },
    DriveApp: { getFolderById: () => ({
      getFoldersByName: () => ({ hasNext: () => false }),
      createFolder: () => ({ createFile: () => ({
        getId: () => 'f1', getUrl: () => 'u', setDescription() {} }) }),
    }) },
    UrlFetchApp: {
      fetch(url, opts = {}) {
        const cab = opts.headers || {};

        if (url.includes('identitytoolkit')) {
          return resp(200, JSON.stringify({ users: [{ localId: 'uid-1',
            email: estado.correoUsuario, displayName: 'Bryan' }] }));
        }
        if (url.includes('firestore.googleapis.com')) {
          return resp(200, JSON.stringify({ fields: { rol: { stringValue: estado.rol } } }));
        }

        if (url.includes('/gettoken')) {
          // El WMS espera las credenciales en `userid` y `password`.
          const id = Object.keys(cuentas).find((k) =>
            cuentas[k].usuario === cab.userid && cuentas[k].clave === cab.password);
          if (!id) return resp(401, 'credenciales invalidas');
          if (estado.caidos.has(id)) return resp(500, 'caido');
          estado.gettoken[id] = (estado.gettoken[id] || 0) + 1;
          estado.tokens[id] = `TK-${id}-${estado.gettoken[id]}`;
          // El WMS puede devolverlo en Result; el Centro de Mando lo contempla.
          return resp(200, JSON.stringify({ Result: estado.tokens[id] }));
        }

        // getstock: el token identifica de qué cliente es la consulta.
        const id = Object.keys(estado.tokens).find((k) => estado.tokens[k] === cab.token);
        if (!id) return resp(401, '');
        if (estado.caidos.has(id)) return resp(500, 'caido');
        estado.getstock[id] = (estado.getstock[id] || 0) + 1;

        const m = url.match(/\/getstock\/(.+)$/);
        const codigo = m ? decodeURIComponent(m[1]) : '';
        const cat = cuentas[id].catalogo;
        // El WMS envuelve las filas en Result.
        if (!codigo) return resp(200, JSON.stringify({ Result: cat }));
        const fila = cat.find((f) => f['COD. PRODUCTO'] === codigo);
        return resp(200, JSON.stringify({ Result: fila ? [fila] : [] }));
      },
    },
  };

  const ctx = vm.createContext(g);
  for (const a of ['Proxy.gs', 'Clientes.gs']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'proxy', a), 'utf8'),
                    ctx, { filename: a });
  }
  return { ctx, estado, props, cache, cuentas };
}

const pedir = (ctx, obj) => JSON.parse(
  ctx.doPost({ postData: { contents: JSON.stringify({ idToken: 'tok', ...obj }) } }).getContent());

function conDosClientes(opciones) {
  const e = entorno(opciones);
  pedir(e.ctx, { accion: 'guardarCliente', id: 'VENTURA', nombre: 'Impoventura',
                 usuario: 'u_ventura', clave: 'p_ventura' });
  pedir(e.ctx, { accion: 'guardarCliente', id: 'BELIA', nombre: 'Belia',
                 usuario: 'u_belia', clave: 'p_belia' });
  return e;
}

console.log('\nPanel de administración');
test('guarda un cliente y lo lista sin revelar la contraseña', () => {
  const e = entorno();
  const r = pedir(e.ctx, { accion: 'guardarCliente', id: 'ventura', nombre: 'Impoventura',
                           usuario: 'u_ventura', clave: 'p_ventura' });
  ok(r.exito); eq(r.id, 'VENTURA', 'el id se normaliza a');

  const l = pedir(e.ctx, { accion: 'listarClientes' });
  eq(l.clientes.length, 1);
  const c = l.clientes[0];
  eq(c.nombre, 'Impoventura');
  eq(c.clave, '********', 'la contraseña nunca viaja');
  ok(!JSON.stringify(l).includes('p_ventura'), 'la contraseña NO debe aparecer');
  ok(c.usuario.includes('****'), 'el usuario va enmascarado: ' + c.usuario);
  ok(c.tieneCredenciales);
});

test('solo un ADMIN toca las credenciales', () => {
  const e = entorno({ rol: 'SUPERVISOR' });
  // doPost devuelve el error en la respuesta, no lo lanza: el cliente web
  // necesita un JSON, no una excepción.
  const g = pedir(e.ctx, { accion: 'guardarCliente', id: 'X', usuario: 'u', clave: 'p' });
  ok(!g.exito && /ADMIN/.test(g.mensaje), 'guardar debe exigir ADMIN: ' + g.mensaje);
  const l = pedir(e.ctx, { accion: 'listarClientes' });
  ok(!l.exito && /ADMIN/.test(l.mensaje), 'listar también exige ADMIN');
  const b = pedir(e.ctx, { accion: 'borrarCliente', id: 'X' });
  ok(!b.exito && /ADMIN/.test(b.mensaje), 'borrar también exige ADMIN');
  const t = pedir(e.ctx, { accion: 'probarCliente', id: 'X' });
  ok(!t.exito && /ADMIN/.test(t.mensaje), 'probar también exige ADMIN');
});

test('el rol sale de Firestore, no de lo que diga el cliente', () => {
  const e = entorno({ rol: 'OPERADOR' });
  const r = pedir(e.ctx, { accion: 'guardarCliente', id: 'X', usuario: 'u', clave: 'p',
                           rol: 'ADMIN' });   // intento de colarse
  ok(!r.exito && /ADMIN/.test(r.mensaje), 'no debe aceptar el rol del payload');
});

test('rechaza http y exige usuario', () => {
  const e = entorno();
  let r = pedir(e.ctx, { accion: 'guardarCliente', id: 'X', usuario: 'u', clave: 'p',
                         baseUrl: 'http://inseguro.com/api' });
  ok(!r.exito && /https/.test(r.mensaje), r.mensaje);
  r = pedir(e.ctx, { accion: 'guardarCliente', id: 'X', clave: 'p' });
  ok(!r.exito && /usuario/i.test(r.mensaje), r.mensaje);
});

// Es lo que paso de verdad: en el formulario se pego la URL del endpoint, no la
// raiz, y el 404 que salia despues parecia un problema de credenciales.
test('recorta el endpoint pegado en la URL base', () => {
  const e = entorno();
  const r = pedir(e.ctx, { accion: 'guardarCliente', id: 'X', usuario: 'u', clave: 'p',
                           baseUrl: 'https://ec.itsanet.com/q_apidepot/getstock/' });
  ok(r.exito, r.mensaje);
  const guardada = JSON.parse(e.props.get('CRED_X')).baseUrl;
  eq(guardada, 'https://ec.itsanet.com/q_apidepot');
});

test('no toca una URL base que ya es la raiz', () => {
  const e = entorno();
  const r = pedir(e.ctx, { accion: 'guardarCliente', id: 'Y', usuario: 'u', clave: 'p',
                           baseUrl: 'https://otro.itsanet.com/api' });
  ok(r.exito, r.mensaje);
  eq(JSON.parse(e.props.get('CRED_Y')).baseUrl, 'https://otro.itsanet.com/api');
});

test('editar sin reescribir la contraseña la conserva', () => {
  const e = entorno();
  pedir(e.ctx, { accion: 'guardarCliente', id: 'V', usuario: 'u_ventura', clave: 'p_ventura' });
  const r = pedir(e.ctx, { accion: 'guardarCliente', id: 'V', nombre: 'Nuevo nombre',
                           usuario: 'u_ventura', clave: '' });
  ok(r.exito, r.mensaje);
  const p = pedir(e.ctx, { accion: 'probarCliente', id: 'V' });
  ok(p.exito, 'la contraseña anterior debe seguir sirviendo');
});

test('borrar un cliente lo quita de la lista', () => {
  const e = conDosClientes();
  pedir(e.ctx, { accion: 'borrarCliente', id: 'BELIA' });
  const l = pedir(e.ctx, { accion: 'listarClientes' });
  eq(l.clientes.map((c) => c.id), ['VENTURA']);
});

console.log('\nUn token por cliente');
test('cada cliente pide su propio token, y solo uno', () => {
  const e = conDosClientes();
  for (let i = 0; i < 10; i++) {
    pedir(e.ctx, { accion: 'producto', codigo: '2H0525345' });
    pedir(e.ctx, { accion: 'producto', codigo: '9XX111' });
  }
  eq(e.estado.gettoken.VENTURA, 1, 'gettoken de VENTURA');
  eq(e.estado.gettoken.BELIA, 1, 'gettoken de BELIA');
});

test('los tokens no se mezclan entre clientes', () => {
  const e = conDosClientes();
  pedir(e.ctx, { accion: 'producto', codigo: '2H0525345' });
  pedir(e.ctx, { accion: 'producto', codigo: '9XX111' });
  ok(e.estado.tokens.VENTURA !== e.estado.tokens.BELIA, 'deben ser distintos');
  const l = pedir(e.ctx, { accion: 'listarClientes' });
  ok(l.clientes.every((c) => c.tokenVigente), 'ambos deben tener token vigente');
  ok(!JSON.stringify(l).includes('TK-'), 'el token NO debe salir en la respuesta');
});

test('cambiar las credenciales invalida el token anterior', () => {
  const e = conDosClientes();
  pedir(e.ctx, { accion: 'producto', codigo: '2H0525345' });
  eq(e.estado.gettoken.VENTURA, 1);
  pedir(e.ctx, { accion: 'guardarCliente', id: 'VENTURA', usuario: 'u_ventura',
                 clave: 'p_ventura' });
  pedir(e.ctx, { accion: 'producto', codigo: '2H0525345' });
  eq(e.estado.gettoken.VENTURA, 2, 'debe pedir un token nuevo');
});

console.log('\nConsulta en varios clientes');
test('encuentra el producto y dice de qué cliente es', () => {
  const e = conDosClientes();
  const r = pedir(e.ctx, { accion: 'producto', codigo: '9XX111' });
  ok(r.exito && r.producto, 'debe encontrarlo');
  eq(r.producto.cliente, 'BELIA');
  eq(r.producto.descripcion, 'PIEZA BELIA');
});

test('un SKU en dos clientes resuelve al primero, de forma estable', () => {
  const e = conDosClientes();
  const a = pedir(e.ctx, { accion: 'producto', codigo: 'COMPARTIDO' });
  const b = pedir(e.ctx, { accion: 'producto', codigo: 'COMPARTIDO' });
  eq(a.producto.cliente, 'VENTURA');
  eq(b.producto.cliente, a.producto.cliente, 'no debe cambiar entre llamadas');
});

test('se puede limitar la consulta a ciertos clientes', () => {
  const e = conDosClientes();
  const r = pedir(e.ctx, { accion: 'producto', codigo: 'COMPARTIDO', clientes: ['BELIA'] });
  eq(r.producto.cliente, 'BELIA');
  eq(e.estado.getstock.VENTURA, undefined, 'no debe consultar al otro');
});

test('un código inexistente devuelve null tras consultar a todos', () => {
  const e = conDosClientes();
  const r = pedir(e.ctx, { accion: 'producto', codigo: 'NOEXISTE' });
  ok(r.exito); eq(r.producto, null);
  eq(r.consultados, ['VENTURA', 'BELIA']);
});

test('si un cliente se cae, los demás siguen sirviendo', () => {
  const e = conDosClientes();
  e.estado.caidos.add('VENTURA');
  const r = pedir(e.ctx, { accion: 'producto', codigo: '9XX111' });
  ok(r.exito && r.producto, 'debe encontrarlo en el que sí responde');
  eq(r.producto.cliente, 'BELIA');
  eq(r.errores.length, 1, 'y dejar constancia del que falló');
  eq(r.errores[0].cliente, 'VENTURA');
});

console.log('\nCatálogo combinado');
test('junta los catálogos y marca el origen de cada producto', () => {
  const e = conDosClientes();
  const r = pedir(e.ctx, { accion: 'catalogo' });
  ok(r.exito);
  eq(r.total, 3, 'dos de VENTURA + dos de BELIA, menos uno repetido');
  eq(e.estado.getstock.VENTURA, 1, 'una llamada por cliente, no por SKU');
  eq(e.estado.getstock.BELIA, 1);
  const porCliente = {};
  r.productos.forEach((p) => { porCliente[p.sku] = p.cliente; });
  eq(porCliente['2H0525345'], 'VENTURA');
  eq(porCliente['9XX111'], 'BELIA');
});

test('los SKU repetidos entre clientes quedan señalados', () => {
  const e = conDosClientes();
  const r = pedir(e.ctx, { accion: 'catalogo' });
  eq(r.ambiguos.length, 1, 'debe avisar del repetido');
  eq(r.ambiguos[0].sku, 'COMPARTIDO');
  eq(r.ambiguos[0].clientes, ['VENTURA', 'BELIA']);
});

test('un cliente caído no impide traer el catálogo de los demás', () => {
  const e = conDosClientes();
  e.estado.caidos.add('BELIA');
  const r = pedir(e.ctx, { accion: 'catalogo' });
  ok(r.exito);
  eq(r.total, 2, 'solo los de VENTURA');
  eq(r.errores[0].cliente, 'BELIA');
  eq(r.porCliente.VENTURA.productos, 2);
});

console.log('\nDiagnóstico por cliente');
test('probar informa cada paso y los campos reales del WMS', () => {
  const e = conDosClientes();
  const r = pedir(e.ctx, { accion: 'probarCliente', id: 'VENTURA' });
  ok(r.exito);
  eq(r.pasos.map((p) => p.paso), ['gettoken', 'getstock']);
  // Los nombres reales del WMS, en mayúsculas y con puntos.
  ok(r.pasos[1].camposCrudos.includes('COD. PRODUCTO'), r.pasos[1].camposCrudos.join(','));
  ok(r.pasos[1].camposCrudos.includes('DESCRIPCION'));
  ok(r.pasos[1].camposCrudos.includes('CANTIDAD'));
  ok(!JSON.stringify(r).includes('TK-'), 'el token no debe aparecer');
});

test('credenciales malas fallan en gettoken y no siguen', () => {
  const e = entorno();
  pedir(e.ctx, { accion: 'guardarCliente', id: 'MAL', usuario: 'u_malo', clave: 'p_malo' });
  const r = pedir(e.ctx, { accion: 'probarCliente', id: 'MAL' });
  ok(!r.exito);
  eq(r.pasos.length, 1, 'no debe intentar getstock');
  ok(/usuario o la contraseña/.test(r.pasos[0].mensaje), r.pasos[0].mensaje);
});

test('el último error queda visible en el panel', () => {
  const e = entorno();
  pedir(e.ctx, { accion: 'guardarCliente', id: 'MAL', usuario: 'u_malo', clave: 'p_malo' });
  pedir(e.ctx, { accion: 'probarCliente', id: 'MAL' });
  const l = pedir(e.ctx, { accion: 'listarClientes' });
  ok(l.clientes[0].ultimoError, 'debe registrar el último error');
});

test('una conexión correcta registra la fecha', () => {
  const e = conDosClientes();
  pedir(e.ctx, { accion: 'probarCliente', id: 'VENTURA' });
  const l = pedir(e.ctx, { accion: 'listarClientes' });
  const c = l.clientes.find((x) => x.id === 'VENTURA');
  ok(c.ultimaConexion, 'debe registrar la última conexión');
  ok(!c.ultimoError, 'y limpiar el error anterior');
});

console.log('\nSupervivencia del token');
test('el token sobrevive a la expiración del caché usando las propiedades', () => {
  const e = conDosClientes();
  pedir(e.ctx, { accion: 'producto', codigo: '2H0525345' });
  eq(e.estado.gettoken.VENTURA, 1);
  e.cache.clear();                       // el caché de Apps Script expira a las 6 h
  pedir(e.ctx, { accion: 'producto', codigo: '2H0525345' });
  eq(e.estado.gettoken.VENTURA, 1, 'debe salir de las propiedades, sin pedir otro');
});

test('un token revocado se renueva y la llamada se reintenta sola', () => {
  const e = conDosClientes();
  pedir(e.ctx, { accion: 'producto', codigo: '2H0525345' });
  eq(e.estado.gettoken.VENTURA, 1);
  e.estado.tokens.VENTURA = 'TK-REVOCADO';   // el WMS lo invalidó antes de tiempo
  const r = pedir(e.ctx, { accion: 'producto', codigo: '2H0525345' });
  eq(e.estado.gettoken.VENTURA, 2, 'debe pedir un token nuevo');
  ok(r.exito && r.producto && r.producto.sku === '2H0525345', 'y acabar funcionando');
});

test('una respuesta sin token reconocible dice qué revisar', () => {
  const e = entorno();
  // El WMS responde 200 pero sin token en ningún campo conocido.
  const original = e.ctx.UrlFetchApp.fetch;
  e.ctx.UrlFetchApp.fetch = (url, opts) => (url.includes('/gettoken')
    ? { getResponseCode: () => 200, getContentText: () => '{"sesion":"abc"}' }
    : original(url, opts));
  pedir(e.ctx, { accion: 'guardarCliente', id: 'V', usuario: 'u_ventura', clave: 'p_ventura' });
  const r = pedir(e.ctx, { accion: 'probarCliente', id: 'V' });
  ok(!r.exito);
  ok(/token reconocible/.test(r.pasos[0].mensaje), r.pasos[0].mensaje);
});

console.log('\nMapeo de campos');
test('DEFAULT no se toma como código de barras', () => {
  const e = entorno({ cuentas: { V: { usuario: 'u_ventura', clave: 'p_ventura', catalogo: [
    { codigo_producto: 'A1', descripcion: 'Uno', codigo_barra: 'DEFAULT', stock: 1 } ] } } });
  pedir(e.ctx, { accion: 'guardarCliente', id: 'V', usuario: 'u_ventura', clave: 'p_ventura' });
  const r = pedir(e.ctx, { accion: 'catalogo' });
  eq(r.productos[0].ean, null);
});

test('normaliza el SKU con basura invisible', () => {
  const e = entorno({ cuentas: { V: { usuario: 'u_ventura', clave: 'p_ventura', catalogo: [
    { codigo_producto: '\u00a0 2h0-525345 ', descripcion: 'Washer', stock: 1 } ] } } });
  pedir(e.ctx, { accion: 'guardarCliente', id: 'V', usuario: 'u_ventura', clave: 'p_ventura' });
  const r = pedir(e.ctx, { accion: 'catalogo' });
  eq(r.productos[0].sku, '2H0525345');
});

console.log('\nContrato real del WMS');
test('las credenciales viajan en userid y password', () => {
  const e = entorno();
  let cabVistas = null;
  const original = e.ctx.UrlFetchApp.fetch;
  e.ctx.UrlFetchApp.fetch = (url, opts) => {
    if (url.includes('/gettoken')) cabVistas = opts.headers;
    return original(url, opts);
  };
  pedir(e.ctx, { accion: 'guardarCliente', id: 'V', usuario: 'u_ventura', clave: 'p_ventura' });
  pedir(e.ctx, { accion: 'probarCliente', id: 'V' });
  eq(cabVistas.userid, 'u_ventura');
  eq(cabVistas.password, 'p_ventura');
  ok(!cabVistas.usuario && !cabVistas.clave, 'los nombres antiguos darían 401');
});

test('las rutas van sin barra final', () => {
  const e = conDosClientes();
  const urls = [];
  const original = e.ctx.UrlFetchApp.fetch;
  e.ctx.UrlFetchApp.fetch = (url, opts) => { urls.push(url); return original(url, opts); };
  pedir(e.ctx, { accion: 'catalogo', clientes: ['VENTURA'] });
  ok(urls.some((u) => u.endsWith('/gettoken')), 'gettoken sin barra: ' + urls.join(' '));
  ok(urls.some((u) => u.endsWith('/getstock')), 'getstock sin barra');
});

test('un código concreto va como /getstock/CODIGO', () => {
  const e = conDosClientes();
  const urls = [];
  const original = e.ctx.UrlFetchApp.fetch;
  e.ctx.UrlFetchApp.fetch = (url, opts) => { urls.push(url); return original(url, opts); };
  pedir(e.ctx, { accion: 'producto', codigo: '2H0525345', clientes: ['VENTURA'] });
  ok(urls.some((u) => u.endsWith('/getstock/2H0525345')), urls.join(' '));
});

test('lee el token aunque venga en Result', () => {
  const e = conDosClientes();
  const r = pedir(e.ctx, { accion: 'producto', codigo: '2H0525345' });
  ok(r.exito && r.producto, 'debe funcionar con el token en Result');
});

test('mapea los campos reales del WMS', () => {
  const e = conDosClientes();
  const r = pedir(e.ctx, { accion: 'producto', codigo: '2H0525345' });
  const p = r.producto;
  eq(p.sku, '2H0525345');
  eq(p.descripcion, 'WASHER');
  eq(p.stock, 12, 'CANTIDAD viene como texto y debe quedar numérica');
  eq(p.unidad, 'CS');
  eq(p.posicion, 'A-01-03-2', 'NAVE-CALLE-COLUMNA-NIVEL');
  eq(p.lote, 'L1');
  eq(p.familia, 'REPUESTOS');
  eq(p.codCliente, 'VENTURA');
  eq(p.ean, null, '/getstock no devuelve código de barras');
});

console.log('\nSin clientes configurados');
test('lo dice claro en vez de fallar raro', () => {
  const e = entorno();
  const r = pedir(e.ctx, { accion: 'producto', codigo: 'X' });
  ok(!r.exito && /clientes configurados/.test(r.mensaje), r.mensaje);
});

console.log(`\n${pasadas} pasadas, ${falladas} falladas`);
process.exit(falladas ? 1 : 0);
