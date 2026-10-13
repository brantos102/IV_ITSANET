/**
 * Credenciales por cliente.
 *
 * Un packing list puede necesitar consultar varios clientes a la vez, y cada
 * uno tiene su propio usuario y contraseña en Depot. Por eso las credenciales
 * no son una sola configuración global sino un registro por cliente, cada uno
 * con su token independiente.
 *
 * DÓNDE VIVE CADA COSA
 * --------------------
 *   Credenciales   Propiedades del script  → solo el servidor las lee
 *   Token vigente  Caché del script        → uno por cliente
 *   Datos visibles Firestore               → nombre, estado, última conexión
 *
 * El navegador nunca recibe un usuario, una contraseña ni un token. El panel
 * de administración ve el nombre del cliente, si tiene credenciales guardadas
 * y cuándo se usó por última vez; nada más.
 */

/** Prefijo de la propiedad que guarda las credenciales de un cliente. */
var PREFIJO_CRED = 'CRED_';
/** Propiedad con la lista de ids, para poder enumerarlos. */
var LISTA_CLIENTES = 'CLIENTES';

/** Normaliza el id: mayúsculas y sin caracteres raros. */
function idCliente_(valor) {
  return String(valor || '').toUpperCase().replace(/[^A-Z0-9_-]/g, '').substring(0, 40);
}

function listaIds_() {
  try {
    var crudo = PROPS.getProperty(LISTA_CLIENTES);
    return crudo ? JSON.parse(crudo) : [];
  } catch (e) {
    return [];
  }
}

function guardarListaIds_(ids) {
  PROPS.setProperty(LISTA_CLIENTES, JSON.stringify(ids));
}

/** Credenciales completas de un cliente. Solo para uso interno del script. */
function credencialesDe_(id) {
  var crudo = PROPS.getProperty(PREFIJO_CRED + idCliente_(id));
  if (!crudo) return null;
  try {
    return JSON.parse(crudo);
  } catch (e) {
    return null;
  }
}

/** Oculta el valor dejando lo justo para reconocerlo. */
function enmascarar_(valor) {
  var v = String(valor || '');
  if (!v) return '';
  if (v.length <= 4) return '****';
  return v.substring(0, 2) + '****' + v.substring(v.length - 2);
}

// ========================================================================== //
// Acciones del panel de administración
// ========================================================================== //

/**
 * Lista los clientes configurados, SIN credenciales.
 *
 * Devuelve lo necesario para que el panel sea útil —si tiene credenciales, si
 * el token está vigente, cuándo se conectó por última vez— y nada que sirva
 * para suplantar al cliente.
 */
function accionListarClientes_(p, usuario) {
  exigirAdmin_(usuario);

  var ids = listaIds_();
  var salida = [];

  for (var i = 0; i < ids.length; i++) {
    var id = ids[i];
    var cred = credencialesDe_(id);
    var tok = estadoTokenCliente_(id);

    salida.push({
      id: id,
      nombre: (cred && cred.nombre) || id,
      baseUrl: (cred && cred.baseUrl) || CFG.baseUrl,
      usuario: cred ? enmascarar_(cred.usuario) : null,
      clave: cred && cred.clave ? '********' : null,
      tieneCredenciales: !!(cred && (cred.usuario || cred.clave)),
      activo: !cred || cred.activo !== false,
      tokenVigente: tok.vigente,
      minutosRestantes: tok.minutosRestantes,
      ultimaConexion: (cred && cred.ultimaConexion) || null,
      ultimoError: (cred && cred.ultimoError) || null
    });
  }
  return { exito: true, clientes: salida, baseUrlGlobal: CFG.baseUrl };
}

/**
 * Crea o actualiza un cliente.
 *
 * Si se envía la contraseña vacía se conserva la anterior: así se puede
 * corregir el nombre o el usuario sin tener que volver a teclear la clave.
 */
function accionGuardarCliente_(p, usuario) {
  exigirAdmin_(usuario);

  var id = idCliente_(p.id);
  if (!id) throw new Error('El identificador del cliente es obligatorio.');
  if (!p.usuario) throw new Error('El usuario de Depot es obligatorio.');

  var previo = credencialesDe_(id) || {};
  // Clave vacía = no se cambia. Evita tener que reescribirla en cada edición.
  var clave = p.clave ? String(p.clave) : (previo.clave || '');
  if (!clave) throw new Error('La contraseña de Depot es obligatoria la primera vez.');

  var baseUrl = String(p.baseUrl || '').replace(/\/+$/, '');
  if (baseUrl && !/^https:\/\//i.test(baseUrl)) {
    // Un http:// mandaría la credencial en claro por la red.
    throw new Error('La URL debe empezar por https://');
  }

  PROPS.setProperty(PREFIJO_CRED + id, JSON.stringify({
    nombre: String(p.nombre || id).substring(0, 80),
    usuario: String(p.usuario),
    clave: clave,
    baseUrl: baseUrl || null,
    activo: p.activo !== false,
    ultimaConexion: previo.ultimaConexion || null,
    ultimoError: null,
    modificadoPor: usuario.email,
    modificadoEn: new Date().toISOString()
  }));

  var ids = listaIds_();
  if (ids.indexOf(id) === -1) {
    ids.push(id);
    guardarListaIds_(ids);
  }

  // Credenciales nuevas: el token anterior ya no sirve.
  invalidarTokenCliente_(id);

  return { exito: true, id: id, mensaje: 'Cliente ' + id + ' guardado.' };
}

function accionBorrarCliente_(p, usuario) {
  exigirAdmin_(usuario);
  var id = idCliente_(p.id);

  PROPS.deleteProperty(PREFIJO_CRED + id);
  invalidarTokenCliente_(id);

  var ids = listaIds_();
  var pos = ids.indexOf(id);
  if (pos > -1) {
    ids.splice(pos, 1);
    guardarListaIds_(ids);
  }
  return { exito: true, mensaje: 'Cliente ' + id + ' eliminado.' };
}

/** Prueba gettoken y getstock de un cliente, informando cada paso aparte. */
function accionProbarCliente_(p, usuario) {
  exigirAdmin_(usuario);
  var id = idCliente_(p.id);
  if (!credencialesDe_(id)) throw new Error('El cliente ' + id + ' no tiene credenciales.');

  var pasos = [];
  var t0 = new Date().getTime();

  try {
    obtenerTokenCliente_(id, true);
    pasos.push({ paso: 'gettoken', ok: true, ms: new Date().getTime() - t0 });
  } catch (e) {
    pasos.push({ paso: 'gettoken', ok: false, ms: new Date().getTime() - t0,
                 mensaje: e.message });
    registrarResultado_(id, false, e.message);
    return { exito: false, id: id, pasos: pasos };
  }

  var t1 = new Date().getTime();
  try {
    var cuerpo = pedirCliente_(id, rutaStockDe_(id) + encodeURIComponent(p.codigo || ''), false);
    var filas = filasDe_(cuerpo || []);
    pasos.push({
      paso: 'getstock', ok: true, ms: new Date().getTime() - t1,
      filas: filas.length,
      muestra: filas.length ? mapearStock_(filas[0]) : null,
      // Los nombres reales de campo: con esto se ajusta el mapeo sin adivinar.
      camposCrudos: filas.length ? Object.keys(filas[0]) : []
    });
    registrarResultado_(id, true, null);
    return { exito: true, id: id, pasos: pasos };
  } catch (e) {
    pasos.push({ paso: 'getstock', ok: false, ms: new Date().getTime() - t1,
                 mensaje: e.message });
    registrarResultado_(id, false, e.message);
    return { exito: false, id: id, pasos: pasos };
  }
}

/** Deja constancia del último intento, para que el panel lo muestre. */
function registrarResultado_(id, ok, mensaje) {
  var cred = credencialesDe_(id);
  if (!cred) return;
  if (ok) {
    cred.ultimaConexion = new Date().toISOString();
    cred.ultimoError = null;
  } else {
    cred.ultimoError = String(mensaje || '').substring(0, 300);
  }
  PROPS.setProperty(PREFIJO_CRED + idCliente_(id), JSON.stringify(cred));
}

// ========================================================================== //
// Token por cliente
// ========================================================================== //

function claveTokenCache_(id) { return 'tok_' + idCliente_(id); }
function claveTokenProp_(id) { return 'TOKCACHE_' + idCliente_(id); }

function estadoTokenCliente_(id) {
  var crudo = PROPS.getProperty(claveTokenProp_(id));
  if (!crudo) return { vigente: false, minutosRestantes: 0 };
  try {
    var reg = JSON.parse(crudo);
    var restante = reg.venceEn - new Date().getTime();
    return {
      vigente: restante > 0,
      minutosRestantes: Math.max(Math.round(restante / 60000), 0)
    };
  } catch (e) {
    return { vigente: false, minutosRestantes: 0 };
  }
}

function invalidarTokenCliente_(id) {
  CACHE.remove(claveTokenCache_(id));
  PROPS.deleteProperty(claveTokenProp_(id));
}

function baseUrlDe_(id) {
  var cred = credencialesDe_(id);
  return (cred && cred.baseUrl) || CFG.baseUrl;
}

function rutaStockDe_(id) { return CFG.rutaStock; }

/**
 * Token de un cliente, reutilizado toda la jornada.
 *
 * Caché del script (6 h de tope) y, por encima, las propiedades. Un solo
 * gettoken por cliente y día.
 */
function obtenerTokenCliente_(id, forzar) {
  id = idCliente_(id);

  if (!forzar) {
    var enCache = CACHE.get(claveTokenCache_(id));
    if (enCache) return enCache;

    var guardado = PROPS.getProperty(claveTokenProp_(id));
    if (guardado) {
      try {
        var reg = JSON.parse(guardado);
        if (reg.token && reg.venceEn > new Date().getTime()) {
          CACHE.put(claveTokenCache_(id), reg.token, TTL_TOKEN_SEG);
          return reg.token;
        }
      } catch (e) { /* propiedad corrupta: se pide uno nuevo */ }
    }
  }

  var cred = credencialesDe_(id);
  if (!cred) throw new Error('El cliente ' + id + ' no tiene credenciales configuradas.');
  if (cred.activo === false) throw new Error('El cliente ' + id + ' está desactivado.');

  var base = baseUrlDe_(id);
  if (!base) throw new Error('No hay URL base para el cliente ' + id + '.');

  var cab = { Accept: 'application/json, text/plain, */*' };
  if (cred.usuario) cab.usuario = cred.usuario;
  if (cred.clave) cab.clave = cred.clave;
  cab.cliente = id;

  var r = UrlFetchApp.fetch(base + CFG.rutaToken, {
    method: 'get', headers: cab, muteHttpExceptions: true
  });

  var codigo = r.getResponseCode();
  if (codigo === 401 || codigo === 403) {
    throw new Error('Depot rechazó el usuario o la contraseña de ' + id + '.');
  }
  if (codigo !== 200) {
    throw new Error('Depot respondió ' + codigo + ' al pedir el token de ' + id + '.');
  }

  var token = extraerToken_(r.getContentText());
  if (!token) {
    throw new Error('Depot respondió sin un token reconocible para ' + id + ': ' +
                    r.getContentText().substring(0, 120));
  }

  var horas = Number(PROPS.getProperty('DEPOT_TTL_HORAS') || 12);
  CACHE.put(claveTokenCache_(id), token, TTL_TOKEN_SEG);
  PROPS.setProperty(claveTokenProp_(id), JSON.stringify({
    token: token,
    venceEn: new Date().getTime() + horas * 3600 * 1000,
    obtenidoEn: new Date().getTime()
  }));
  return token;
}

/** GET contra Depot con el token del cliente, reintentando una vez si lo revocaron. */
function pedirCliente_(id, ruta, yaReintento) {
  var cab = { Accept: 'application/json, text/plain, */*' };
  cab[CFG.cabeceraToken] = obtenerTokenCliente_(id, false);

  var r = UrlFetchApp.fetch(baseUrlDe_(id) + ruta, {
    method: 'get', headers: cab, muteHttpExceptions: true
  });

  var codigo = r.getResponseCode();
  if ((codigo === 401 || codigo === 403) && !yaReintento) {
    invalidarTokenCliente_(id);
    obtenerTokenCliente_(id, true);
    return pedirCliente_(id, ruta, true);
  }
  if (codigo === 404) return null;
  if (codigo !== 200) {
    throw new Error('Depot respondió ' + codigo + ' en ' + ruta + ' para ' + id);
  }

  var texto = r.getContentText();
  if (!texto || !texto.trim()) return null;
  try {
    return JSON.parse(texto);
  } catch (e) {
    throw new Error('Depot respondió algo que no es JSON: ' + texto.substring(0, 120));
  }
}

// ========================================================================== //
// Consultas multi-cliente
// ========================================================================== //

/** Clientes activos con credenciales, en orden. */
function clientesActivos_(filtro) {
  var ids = listaIds_();
  var salida = [];
  for (var i = 0; i < ids.length; i++) {
    var cred = credencialesDe_(ids[i]);
    if (!cred || cred.activo === false) continue;
    if (filtro && filtro.length && filtro.indexOf(ids[i]) === -1) continue;
    salida.push(ids[i]);
  }
  return salida;
}

/**
 * Busca un código en varios clientes.
 *
 * Devuelve el primero que lo tenga, indicando de qué cliente es: un mismo
 * packing list puede mezclar mercadería de varios, y el operario necesita
 * saber a cuál pertenece lo que escaneó.
 *
 * Si un cliente falla, se anota y se sigue con los demás: la caída de uno no
 * puede dejar al operario sin poder validar el resto.
 */
function accionProductoMulti_(p, usuario) {
  var codigo = normalizar_(p.codigo);
  if (!codigo) return { exito: false, mensaje: 'Código vacío.' };

  var ids = clientesActivos_(p.clientes);
  if (!ids.length) {
    return { exito: false, mensaje: 'No hay clientes configurados con credenciales.' };
  }

  var errores = [];
  for (var i = 0; i < ids.length; i++) {
    try {
      var cuerpo = pedirCliente_(ids[i], CFG.rutaStock + encodeURIComponent(codigo), false);
      var filas = filasDe_(cuerpo || []);
      for (var j = 0; j < filas.length; j++) {
        var m = mapearStock_(filas[j]);
        if (m && (m.sku === codigo || m.ean === codigo)) {
          m.cliente = ids[i];
          return { exito: true, producto: m, consultados: ids, errores: errores };
        }
      }
      if (filas.length) {
        var primero = mapearStock_(filas[0]);
        if (primero) {
          primero.cliente = ids[i];
          return { exito: true, producto: primero, consultados: ids, errores: errores };
        }
      }
    } catch (e) {
      errores.push({ cliente: ids[i], mensaje: e.message });
    }
  }

  return {
    exito: true, producto: null, consultados: ids, errores: errores,
    mensaje: errores.length
      ? 'No se encontró. ' + errores.length + ' cliente(s) no respondieron.'
      : 'El código no existe en ninguno de los clientes consultados.'
  };
}

/**
 * Descarga el catálogo de varios clientes y los junta.
 *
 * `getstock` sin código devuelve todo, así que son tantas llamadas como
 * clientes, no como SKU. Si un SKU aparece en dos clientes gana el primero,
 * y queda anotado como ambiguo para que el supervisor lo revise.
 */
function accionCatalogoMulti_(p, usuario) {
  var ids = clientesActivos_(p.clientes);
  if (!ids.length) {
    return { exito: false, mensaje: 'No hay clientes configurados con credenciales.' };
  }

  var productos = [];
  var porSku = {};
  var ambiguos = [];
  var errores = [];
  var porCliente = {};

  for (var i = 0; i < ids.length; i++) {
    var id = ids[i];
    try {
      var cuerpo = pedirCliente_(id, CFG.rutaStock, false);
      var filas = filasDe_(cuerpo || []);
      var n = 0;

      for (var j = 0; j < filas.length; j++) {
        var m = mapearStock_(filas[j]);
        if (!m || !m.sku) continue;

        if (porSku[m.sku]) {
          if (porSku[m.sku].cliente !== id && ambiguos.length < 200) {
            ambiguos.push({ sku: m.sku, clientes: [porSku[m.sku].cliente, id] });
          }
          continue;
        }
        m.cliente = id;
        porSku[m.sku] = m;
        productos.push(m);
        n++;
      }
      porCliente[id] = { filas: filas.length, productos: n };
      registrarResultado_(id, true, null);
    } catch (e) {
      errores.push({ cliente: id, mensaje: e.message });
      registrarResultado_(id, false, e.message);
    }
  }

  return {
    exito: true,
    productos: productos,
    total: productos.length,
    porCliente: porCliente,
    ambiguos: ambiguos,
    errores: errores
  };
}

// ========================================================================== //
// Autorización
// ========================================================================== //

/**
 * Exige rol ADMIN.
 *
 * El rol se lee de Firestore con el token del propio operario, así que las
 * reglas de seguridad se aplican igual que desde la app: el script no se cree
 * nada que el usuario diga de sí mismo.
 */
function exigirAdmin_(usuario) {
  if (!usuario || !usuario.uid) throw new Error('Sesión no válida.');
  if (usuario.rol !== 'ADMIN') {
    throw new Error('Esta acción requiere rol ADMIN. El tuyo es ' +
                    (usuario.rol || 'desconocido') + '.');
  }
}

/** Lee el perfil del operario en Firestore usando su propio token. */
function rolDeUsuario_(uid, idToken) {
  var proyecto = PROPS.getProperty('FIREBASE_PROJECT_ID');
  var baseDatos = PROPS.getProperty('FIREBASE_DATABASE_ID') || '(default)';
  if (!proyecto) return null;

  var url = 'https://firestore.googleapis.com/v1/projects/' + proyecto +
            '/databases/' + encodeURIComponent(baseDatos) +
            '/documents/usuarios/' + encodeURIComponent(uid);

  var r = UrlFetchApp.fetch(url, {
    method: 'get',
    headers: { Authorization: 'Bearer ' + idToken },
    muteHttpExceptions: true
  });
  if (r.getResponseCode() !== 200) return null;

  try {
    var d = JSON.parse(r.getContentText());
    return (d.fields && d.fields.rol && d.fields.rol.stringValue) || null;
  } catch (e) {
    return null;
  }
}
