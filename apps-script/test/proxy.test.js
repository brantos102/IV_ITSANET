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
    DEPOT_BASE_URL: 'https://ec.itsanet.com/q_apidepot',
    FIREBASE_PROJECT_ID: 'iv-itsanet',
    FIREBASE_DATABASE_ID: 'bd-iv-itsanet',
    FIREBASE_API_KEY: 'AIza-demo',
    DOMINIO_PERMITIDO: 'itsanet.com',
    CARPETA_EVIDENCIAS: 'folder-123',
    ...(opciones.props || {}),
  }));
  const cache = new Map();
  const estado = {
    gettoken: 0, getstock: 0, lookups: 0, correos: [], archivos: [], existentes: [],
    tokenActual: null, revocado: false,
    perfil: opciones.perfil === null ? null
      : (opciones.perfil || { rol: opciones.rol || 'OPERADOR', activo: true }),
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
    MailApp: {
      sendEmail: (o) => estado.correos.push(o),
      getRemainingDailyQuota: () => 1400,
    },
    DriveApp: {
      getFolderById: () => ({
        getFoldersByName: () => ({ hasNext: () => false }),
        createFolder: () => ({
          // `estado.existentes` simula los archivos que ya hay en la carpeta.
          getFilesByName: (n) => ({ hasNext: () => estado.existentes.includes(n) }),
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
        // Perfil del operario en Firestore: es lo que autoriza, no el dominio.
        if (url.includes('firestore.googleapis.com')) {
          if (!estado.perfil) return resp(404, '{}');
          return resp(200, JSON.stringify({ fields: {
            rol: { stringValue: estado.perfil.rol },
            activo: { booleanValue: estado.perfil.activo },
            email: { stringValue: estado.correoUsuario },
          } }));
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
  for (const archivo of ['Proxy.gs', 'Clientes.gs']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'proxy', archivo), 'utf8'),
                    ctx, { filename: archivo });
  }
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

// El correo personal es legítimo desde que el registro lo acepta: lo que
// autoriza es tener perfil activo, no el dominio. Antes, un operario dado de
// alta con su gmail entraba en la app y el proxy le negaba subir la foto.
test('un correo personal con perfil activo sí pasa la autenticación', () => {
  const { ctx } = entorno({ correoUsuario: 'ajeno@gmail.com' });
  const r = leer(ctx.doPost(peticion({ accion: 'catalogo' })));
  // Llega hasta la falta de clientes, que es un problema de configuración, no
  // de identidad: el dominio del correo ya no le cierra la puerta.
  ok(!/dominio|itsanet|alta|desactivada/i.test(r.mensaje || ''), r.mensaje);
});

test('sin perfil en la aplicación no se pasa', () => {
  const { ctx, estado } = entorno({ perfil: null });
  const r = leer(ctx.doPost(peticion({ accion: 'catalogo' })));
  ok(!r.exito);
  ok(/alta/i.test(r.mensaje), r.mensaje);
  eq(estado.getstock, 0, 'la API del WMS no debe quedar expuesta');
});

// Más estrecho que el filtro del dominio: antes, una cuenta corporativa
// desactivada seguía llegando al WMS.
test('una cuenta desactivada no llega al WMS aunque sea del dominio', () => {
  const { ctx, estado } = entorno({ perfil: { rol: 'SUPERVISOR', activo: false } });
  const r = leer(ctx.doPost(peticion({ accion: 'catalogo' })));
  ok(!r.exito);
  ok(/desactivada/i.test(r.mensaje), r.mensaje);
  eq(estado.getstock, 0);
});

test('rechaza una sesión inválida', () => {
  const { ctx } = entorno({ usuarioValido: false });
  const r = leer(ctx.doPost(peticion({ accion: 'catalogo' })));
  ok(!r.exito);
  ok(/sesión/i.test(r.mensaje), r.mensaje);
});

test('la verificación de sesión se cachea', () => {
  const { ctx, estado } = entorno();
  for (let i = 0; i < 5; i++) ctx.doPost(peticion({ accion: 'estadoToken' }));
  eq(estado.lookups, 1, 'verificaciones contra Google');
});






console.log('\nAcciones');




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

// El correo se borra y la descarga se pierde con el equipo. Si mañana hay una
// reclamación, el archivo que se subió a Depot tiene que seguir en la empresa.
test('el informe final se archiva en Drive', () => {
  const { ctx, estado } = entorno();
  const r = leer(ctx.doPost(peticion({ accion: 'guardarInforme', base64: 'QUJD',
    nombre: 'validacion-VW-29-06-2026-10-13', recepcion: 'VW-29-06' })));
  ok(r.exito && r.fileId === 'file-1', r.mensaje);
  eq(estado.archivos.length, 1);
  eq(estado.archivos[0].nombre, 'validacion-VW-29-06-2026-10-13.xlsx');
});

test('cerrar dos veces no pisa el informe anterior', () => {
  const { ctx, estado } = entorno();
  estado.existentes.push('validacion-VW-29-06.xlsx');
  const r = leer(ctx.doPost(peticion({ accion: 'guardarInforme', base64: 'QUJD',
    nombre: 'validacion-VW-29-06', recepcion: 'VW-29-06' })));
  ok(r.exito, r.mensaje);
  eq(r.nombre, 'validacion-VW-29-06 (2).xlsx', 'debe numerar, no pisar');
});

// Lo natural es copiar la barra de direcciones de Drive y pegarla. Rechazar eso
// mandaba a buscar un error de configuracion donde solo habia un enlace.
test('la carpeta de evidencias admite el enlace de Drive, no solo el id', () => {
  const e = entorno({ props: { CARPETA_EVIDENCIAS:
    'https://drive.google.com/drive/folders/1spPbedhG4y5FfQso1yJTV_aixPv0KWAr?usp=sharing' } });
  const r = leer(e.ctx.doPost(peticion({ accion: 'subirFoto', base64: 'QUJD',
    sku: 'X1', recepcion: 'VW-29-06', tipo: 'image/jpeg' })));
  ok(r.exito, r.mensaje);
});

test('sin carpeta configurada, el mensaje dice donde ponerla', () => {
  const e = entorno({ props: { CARPETA_EVIDENCIAS: '' } });
  const r = leer(e.ctx.doPost(peticion({ accion: 'subirFoto', base64: 'QUJD',
    sku: 'X1', recepcion: 'VW-29-06' })));
  ok(!r.exito);
  ok(/Propiedades del script/i.test(r.mensaje), r.mensaje);
});

test('guardarInforme sin archivo se rechaza', () => {
  const { ctx } = entorno();
  const r = leer(ctx.doPost(peticion({ accion: 'guardarInforme', recepcion: 'X' })));
  ok(!r.exito && /archivo/i.test(r.mensaje), r.mensaje);
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
