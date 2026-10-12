/**
 * Módulo de administración: operarios y credenciales de Depot.
 *
 * Las credenciales del WMS NUNCA llegan al dispositivo. Viven en Secret Manager
 * y solo las leen las Cloud Functions. El panel de administración las escribe,
 * pero no puede volver a leerlas: muestra una máscara y la fecha del último
 * cambio. Así, un administrador con la sesión abierta en un teléfono perdido no
 * expone la credencial del WMS.
 */
'use strict';

const { limpiar } = require('./normalize');

const ROLES = ['OPERADOR', 'SUPERVISOR', 'ADMIN'];
const SECRETO_DEPOT = 'DEPOT_CREDENCIALES';

class ErrorAdmin extends Error {
  constructor(mensaje, codigo = 'ERROR') { super(mensaje); this.codigo = codigo; }
}

function exigirAdmin(ctx) {
  if (!ctx || !ctx.uid) throw new ErrorAdmin('Sesión no válida.', 'NO_AUTENTICADO');
  if (ctx.rol !== 'ADMIN') throw new ErrorAdmin('Requiere rol ADMIN.', 'NO_AUTORIZADO');
}

function exigirSupervisor(ctx) {
  if (!ctx || !ctx.uid) throw new ErrorAdmin('Sesión no válida.', 'NO_AUTENTICADO');
  if (ctx.rol !== 'ADMIN' && ctx.rol !== 'SUPERVISOR') {
    throw new ErrorAdmin('Requiere rol SUPERVISOR o ADMIN.', 'NO_AUTORIZADO');
  }
}

// ------------------------------------------------------------------------ //
// Operarios
// ------------------------------------------------------------------------ //

/**
 * Da de alta un operario.
 *
 * El rol viaja como custom claim del token, así las reglas de Firestore lo
 * verifican sin leer la base en cada operación.
 */
async function crearOperario(auth, db, ctx, { email, nombre, rol, clave }, { FieldValue }) {
  exigirAdmin(ctx);

  const correo = limpiar(email).toLowerCase();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(correo)) {
    throw new ErrorAdmin('Correo electrónico inválido.', 'EMAIL_INVALIDO');
  }
  if (limpiar(nombre).length < 3) {
    throw new ErrorAdmin('Indique el nombre completo del operario.', 'NOMBRE_INVALIDO');
  }
  if (!ROLES.includes(rol)) throw new ErrorAdmin('Rol inválido.', 'ROL_INVALIDO');
  if (!clave || String(clave).length < 8) {
    throw new ErrorAdmin('La contraseña debe tener al menos 8 caracteres.', 'CLAVE_DEBIL');
  }

  const usuario = await auth.createUser({
    email: correo,
    password: String(clave),
    displayName: limpiar(nombre),
    emailVerified: false,
  });

  await auth.setCustomUserClaims(usuario.uid, { rol, activo: true });

  await db.collection('usuarios').doc(usuario.uid).set({
    uid: usuario.uid,
    email: correo,
    nombre: limpiar(nombre),
    rol,
    activo: true,
    creadoPorUid: ctx.uid,
    creadoEn: FieldValue.serverTimestamp(),
  });

  return { uid: usuario.uid, email: correo, rol };
}

/**
 * Activa o desactiva un operario.
 *
 * Desactivar revoca los tokens vigentes: deja de poder escribir en el acto, no
 * cuando venza su sesión.
 */
async function cambiarEstadoOperario(auth, db, ctx, { uid, activo }, { FieldValue }) {
  exigirAdmin(ctx);
  if (uid === ctx.uid && activo === false) {
    throw new ErrorAdmin('No puede desactivar su propia cuenta.', 'AUTO_BLOQUEO');
  }

  const snap = await db.collection('usuarios').doc(uid).get();
  if (!snap.exists) throw new ErrorAdmin('Operario no encontrado.', 'NO_ENCONTRADO');

  await auth.setCustomUserClaims(uid, { rol: snap.get('rol'), activo: !!activo });
  await auth.updateUser(uid, { disabled: !activo });
  await auth.revokeRefreshTokens(uid);

  await db.collection('usuarios').doc(uid).update({
    activo: !!activo,
    modificadoPorUid: ctx.uid,
    modificadoEn: FieldValue.serverTimestamp(),
  });
  return { uid, activo: !!activo };
}

async function cambiarRol(auth, db, ctx, { uid, rol }, { FieldValue }) {
  exigirAdmin(ctx);
  if (!ROLES.includes(rol)) throw new ErrorAdmin('Rol inválido.', 'ROL_INVALIDO');
  if (uid === ctx.uid) throw new ErrorAdmin('No puede cambiar su propio rol.', 'AUTO_CAMBIO');

  const snap = await db.collection('usuarios').doc(uid).get();
  if (!snap.exists) throw new ErrorAdmin('Operario no encontrado.', 'NO_ENCONTRADO');

  await auth.setCustomUserClaims(uid, { rol, activo: snap.get('activo') !== false });
  await auth.revokeRefreshTokens(uid);   // el token viejo lleva el rol viejo
  await db.collection('usuarios').doc(uid).update({
    rol, modificadoPorUid: ctx.uid, modificadoEn: FieldValue.serverTimestamp(),
  });
  return { uid, rol };
}

// ------------------------------------------------------------------------ //
// Credenciales de Depot
// ------------------------------------------------------------------------ //

/**
 * Guarda la configuración de la API de Depot.
 *
 * Lo sensible (token, contraseña) va a Secret Manager. Lo no sensible (URL,
 * usuario, cliente) va a Firestore para que el panel lo muestre. La separación
 * importa: el panel necesita mostrar contra qué servidor apunta, sin exponer
 * con qué credencial entra.
 */
async function guardarConfigDepot(secretos, db, ctx, cfg, { FieldValue }) {
  exigirAdmin(ctx);

  const baseUrl = limpiar(cfg.baseUrl);
  if (!/^https:\/\/[^\s]+$/.test(baseUrl)) {
    // HTTP plano expondría la credencial en la red de la bodega.
    throw new ErrorAdmin('La URL debe ser https.', 'URL_INVALIDA');
  }

  const secreto = {
    token: cfg.token ? String(cfg.token) : null,
    usuario: cfg.usuario ? limpiar(cfg.usuario) : null,
    clave: cfg.clave ? String(cfg.clave) : null,
  };
  if (!secreto.token && !(secreto.usuario && secreto.clave)) {
    throw new ErrorAdmin('Indique un token, o usuario y contraseña.', 'SIN_CREDENCIAL');
  }

  await secretos.guardar(SECRETO_DEPOT, JSON.stringify(secreto));

  await db.collection('config').doc('depot').set({
    baseUrl,
    cliente: limpiar(cfg.cliente) || null,
    soportaLote: !!cfg.soportaLote,
    rutaProducto: limpiar(cfg.rutaProducto) || null,
    rutaEan: limpiar(cfg.rutaEan) || null,
    rutaLote: limpiar(cfg.rutaLote) || null,
    tipoAuth: secreto.token ? 'BEARER' : 'BASIC',
    // Nunca el valor: solo lo justo para reconocer cuál credencial está puesta.
    credencialMascara: enmascarar(secreto.token || secreto.usuario),
    actualizadoPorUid: ctx.uid,
    actualizadoEn: FieldValue.serverTimestamp(),
  }, { merge: true });

  return { baseUrl, tipoAuth: secreto.token ? 'BEARER' : 'BASIC' };
}

function enmascarar(valor) {
  const v = String(valor || '');
  if (v.length <= 4) return '****';
  return v.slice(0, 2) + '*'.repeat(Math.min(v.length - 4, 12)) + v.slice(-2);
}

/** Carga la configuración completa. Solo para uso del lado servidor. */
async function cargarConfigDepot(secretos, db) {
  const snap = await db.collection('config').doc('depot').get();
  if (!snap.exists) return null;
  const publico = snap.data();

  let secreto = {};
  try {
    const crudo = await secretos.leer(SECRETO_DEPOT);
    secreto = crudo ? JSON.parse(crudo) : {};
  } catch (e) {
    console.error('No se pudo leer la credencial de Depot:', e.message);
    return null;
  }

  return {
    baseUrl: publico.baseUrl,
    cliente: publico.cliente,
    soportaLote: publico.soportaLote,
    token: secreto.token || null,
    usuario: secreto.usuario || null,
    clave: secreto.clave || null,
  };
}

/**
 * Prueba la conexión con un código conocido, sin guardar nada.
 * Permite validar las credenciales antes de confiarles una recepción.
 */
async function probarConexionDepot(secretos, db, ctx, { codigoPrueba }, crearAdaptador) {
  exigirAdmin(ctx);
  const cfg = await cargarConfigDepot(secretos, db);
  if (!cfg) throw new ErrorAdmin('No hay configuración de Depot guardada.', 'SIN_CONFIG');

  const inicio = Date.now();
  try {
    const adaptador = crearAdaptador(cfg);
    const p = await adaptador.buscarPorCodigo(limpiar(codigoPrueba) || 'TEST');
    return {
      ok: true,
      ms: Date.now() - inicio,
      encontrado: !!p,
      producto: p ? { sku: p.sku, descripcion: p.descripcion, ean: p.ean } : null,
      mensaje: p ? 'Conexión correcta y producto encontrado.'
                 : 'Conexión correcta. Ese código no existe en Depot.',
    };
  } catch (e) {
    return { ok: false, ms: Date.now() - inicio, codigo: e.codigo || 'ERROR', mensaje: e.message };
  }
}

// ------------------------------------------------------------------------ //
// Adaptador de Secret Manager (inyectable para pruebas)
// ------------------------------------------------------------------------ //
class SecretManagerAdapter {
  constructor(cliente, proyecto) { this.cliente = cliente; this.proyecto = proyecto; }

  async guardar(nombre, valor) {
    const padre = `projects/${this.proyecto}`;
    try {
      await this.cliente.createSecret({
        parent: padre, secretId: nombre, secret: { replication: { automatic: {} } },
      });
    } catch (e) {
      if (e.code !== 6) throw e;   // 6 = ALREADY_EXISTS
    }
    await this.cliente.addSecretVersion({
      parent: `${padre}/secrets/${nombre}`,
      payload: { data: Buffer.from(valor, 'utf8') },
    });
  }

  async leer(nombre) {
    const [v] = await this.cliente.accessSecretVersion({
      name: `projects/${this.proyecto}/secrets/${nombre}/versions/latest`,
    });
    return v.payload.data.toString('utf8');
  }
}

/** Implementación en memoria para pruebas. */
class SecretMemoriaAdapter {
  constructor() { this.valores = new Map(); }
  async guardar(nombre, valor) { this.valores.set(nombre, valor); }
  async leer(nombre) { return this.valores.get(nombre) || null; }
}

module.exports = {
  crearOperario, cambiarEstadoOperario, cambiarRol,
  guardarConfigDepot, cargarConfigDepot, probarConexionDepot,
  exigirAdmin, exigirSupervisor, enmascarar,
  SecretManagerAdapter, SecretMemoriaAdapter,
  ErrorAdmin, ROLES, SECRETO_DEPOT,
};
