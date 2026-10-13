/**
 * Proxy de Depot en Apps Script.
 *
 * POR QUÉ EXISTE
 * --------------
 * El plan Spark de Firebase no incluye Cloud Functions ni Cloud Storage, así
 * que no hay dónde poner código de servidor. Pero Apps Script sí es gratis con
 * Google Workspace, y hace justo lo que falta:
 *
 *   - Guarda las credenciales de Depot donde el navegador no las ve.
 *   - Llama a la API del WMS sin problemas de CORS ni de contenido mixto
 *     (la API es http:// y la app es https://; el navegador bloquearía la
 *     llamada directa, el servidor no).
 *   - Sube las fotos de PNC a Drive, que reemplaza a Cloud Storage.
 *   - Envía el informe final por correo.
 *
 * QUÉ NO HACE
 * -----------
 * No participa en el escaneo. Esa ruta es el navegador contra Firestore
 * directamente, y por eso sigue costando 50-150 ms. Aquí solo pasan el
 * precalentado (una vez por recepción), alguna consulta suelta y el cierre.
 *
 * SEGURIDAD
 * ---------
 * Cada petición trae el token de sesión de Firebase del operario. Se verifica
 * contra Google antes de hacer nada, y se exige que el correo sea del dominio
 * corporativo. Sin eso, publicar este script sería abrir la API del WMS a
 * internet.
 */

// ========================================================================== //
// Configuración  (Extensiones → Apps Script → Configuración → Propiedades)
// ========================================================================== //
//
//   DEPOT_BASE_URL     http://dominio.com/apidepot
//   DEPOT_USUARIO      (opcional) usuario del cliente para /gettoken/
//   DEPOT_CLAVE        (opcional) contraseña del cliente
//   DEPOT_CLIENTE      (opcional) p.ej. VENTURA
//   FIREBASE_API_KEY   la "apiKey" de la configuración web de Firebase
//   DOMINIO_PERMITIDO  itsanet.com
//   CARPETA_EVIDENCIAS id de la carpeta de Drive para las fotos
//
// Las credenciales NUNCA van en este archivo: van en las propiedades del
// script, que no se versionan y que solo ve el dueño del proyecto.

var PROPS = PropertiesService.getScriptProperties();
var CACHE = CacheService.getScriptCache();

var CFG = {
  get baseUrl() { return (PROPS.getProperty('DEPOT_BASE_URL') || '').replace(/\/+$/, ''); },
  get usuario() { return PROPS.getProperty('DEPOT_USUARIO') || ''; },
  get clave() { return PROPS.getProperty('DEPOT_CLAVE') || ''; },
  get cliente() { return PROPS.getProperty('DEPOT_CLIENTE') || ''; },
  get apiKey() { return PROPS.getProperty('FIREBASE_API_KEY') || ''; },
  get dominio() { return PROPS.getProperty('DOMINIO_PERMITIDO') || ''; },
  get carpeta() { return PROPS.getProperty('CARPETA_EVIDENCIAS') || ''; },
  get rutaToken() { return PROPS.getProperty('DEPOT_RUTA_TOKEN') || '/gettoken/'; },
  get rutaStock() { return PROPS.getProperty('DEPOT_RUTA_STOCK') || '/getstock/'; },
  get cabeceraToken() { return PROPS.getProperty('DEPOT_CABECERA_TOKEN') || 'token'; }
};

var TTL_TOKEN_SEG = 6 * 60 * 60;    // tope del caché de Apps Script

// ========================================================================== //
// Punto de entrada
// ========================================================================== //

function doPost(e) {
  try {
    var peticion = JSON.parse(e.postData.contents || '{}');
    var usuario = verificarSesion_(peticion.idToken);

    var acciones = {
      diagnostico: accionDiagnostico_,
      catalogo: accionCatalogo_,
      producto: accionProducto_,
      subirFoto: accionSubirFoto_,
      enviarInforme: accionEnviarInforme_,
      estadoToken: accionEstadoToken_
    };

    var fn = acciones[peticion.accion];
    if (!fn) return responder_({ exito: false, mensaje: 'Acción desconocida: ' + peticion.accion });

    return responder_(fn(peticion, usuario));
  } catch (err) {
    return responder_({ exito: false, mensaje: String(err && err.message || err) });
  }
}

/** Página de comprobación: confirma que el despliegue respondo. */
function doGet() {
  return ContentService
    .createTextOutput(JSON.stringify({ ok: true, servicio: 'proxy-depot', version: '1.0' }))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * Respuesta JSON.
 *
 * El navegador llama con Content-Type: text/plain para que no haya preflight:
 * Apps Script no permite responder cabeceras CORS propias, así que la petición
 * tiene que ser "simple".
 */
function responder_(objeto) {
  return ContentService
    .createTextOutput(JSON.stringify(objeto))
    .setMimeType(ContentService.MimeType.JSON);
}

// ========================================================================== //
// Seguridad
// ========================================================================== //

/**
 * Verifica el token de sesión de Firebase contra Google.
 *
 * Sin esto, el script publicado sería una puerta abierta a la API del WMS para
 * cualquiera que descubriera la URL.
 */
function verificarSesion_(idToken) {
  if (!idToken) throw new Error('Falta el token de sesión.');

  // El resultado se cachea un rato: verificar en cada llamada añadiría ~200 ms.
  var clave = 'ses_' + Utilities.base64EncodeWebSafe(
    Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, idToken));
  var guardado = CACHE.get(clave);
  if (guardado) return JSON.parse(guardado);

  if (!CFG.apiKey) throw new Error('Falta FIREBASE_API_KEY en las propiedades del script.');

  var r = UrlFetchApp.fetch(
    'https://identitytoolkit.googleapis.com/v1/accounts:lookup?key=' + encodeURIComponent(CFG.apiKey),
    {
      method: 'post',
      contentType: 'application/json',
      payload: JSON.stringify({ idToken: idToken }),
      muteHttpExceptions: true
    });

  if (r.getResponseCode() !== 200) {
    throw new Error('Sesión no válida o expirada. Vuelva a entrar a la aplicación.');
  }

  var datos = JSON.parse(r.getContentText());
  var u = datos.users && datos.users[0];
  if (!u || !u.email) throw new Error('Sesión sin correo asociado.');

  // El dominio corporativo es la frontera: nadie de fuera llega al WMS.
  if (CFG.dominio && u.email.toLowerCase().indexOf('@' + CFG.dominio.toLowerCase()) === -1) {
    throw new Error('Solo cuentas de ' + CFG.dominio + ' pueden usar este servicio.');
  }

  var usuario = { uid: u.localId, email: u.email, nombre: u.displayName || '' };
  CACHE.put(clave, JSON.stringify(usuario), 300);   // 5 minutos
  return usuario;
}

// ========================================================================== //
// Token de Depot
// ========================================================================== //

/**
 * Devuelve un token válido, pidiéndolo solo si hace falta.
 *
 * Dos niveles: el caché del script (compartido entre ejecuciones) y, por
 * encima del tope de 6 horas del caché, las propiedades del script.
 */
function obtenerTokenDepot_(forzar) {
  if (!forzar) {
    var enCache = CACHE.get('depot_token');
    if (enCache) return enCache;

    var guardado = PROPS.getProperty('DEPOT_TOKEN_CACHE');
    if (guardado) {
      try {
        var reg = JSON.parse(guardado);
        if (reg.token && reg.venceEn > Date.now()) {
          CACHE.put('depot_token', reg.token, TTL_TOKEN_SEG);
          return reg.token;
        }
      } catch (e) { /* propiedad corrupta: se pide uno nuevo */ }
    }
  }

  if (!CFG.baseUrl) throw new Error('Falta DEPOT_BASE_URL en las propiedades del script.');

  var cab = { Accept: 'application/json, text/plain, */*' };
  if (CFG.usuario) cab.usuario = CFG.usuario;
  if (CFG.clave) cab.clave = CFG.clave;
  if (CFG.cliente) cab.cliente = CFG.cliente;

  var r = UrlFetchApp.fetch(CFG.baseUrl + CFG.rutaToken, {
    method: 'get', headers: cab, muteHttpExceptions: true
  });

  var codigo = r.getResponseCode();
  if (codigo === 401 || codigo === 403) {
    throw new Error('Depot rechazó las credenciales al pedir el token.');
  }
  if (codigo !== 200) {
    throw new Error('Depot respondió ' + codigo + ' en ' + CFG.rutaToken);
  }

  var token = extraerToken_(r.getContentText());
  if (!token) {
    throw new Error('Depot respondió sin un token reconocible. Revise el formato de ' +
                    CFG.rutaToken + ': ' + r.getContentText().substring(0, 120));
  }

  var horas = Number(PROPS.getProperty('DEPOT_TTL_HORAS') || 12);
  CACHE.put('depot_token', token, TTL_TOKEN_SEG);
  PROPS.setProperty('DEPOT_TOKEN_CACHE', JSON.stringify({
    token: token, venceEn: Date.now() + horas * 3600 * 1000, obtenidoEn: Date.now()
  }));
  return token;
}

/** El formato de /gettoken/ no está documentado: se aceptan los tres usuales. */
function extraerToken_(texto) {
  var t = String(texto || '').trim();
  if (!t) return null;

  if (t.charAt(0) === '{' || t.charAt(0) === '[') {
    try {
      var j = JSON.parse(t);
      var d = Array.isArray(j) ? j[0] : (j.data || j.result || j);
      var v = d && (d.token || d.Token || d.token_id || d.tokenId || d.id ||
                    d.access_token || d.TOKEN);
      return v ? String(v) : null;
    } catch (e) { return null; }
  }
  return t.replace(/^"+|"+$/g, '') || null;
}

function invalidarTokenDepot_() {
  CACHE.remove('depot_token');
  PROPS.deleteProperty('DEPOT_TOKEN_CACHE');
}

/** GET contra Depot con el token puesto, reintentando una vez si lo revocaron. */
function pedirDepot_(ruta, yaReintento) {
  var cab = { Accept: 'application/json, text/plain, */*' };
  cab[CFG.cabeceraToken] = obtenerTokenDepot_(false);

  var r = UrlFetchApp.fetch(CFG.baseUrl + ruta, {
    method: 'get', headers: cab, muteHttpExceptions: true
  });

  var codigo = r.getResponseCode();
  if ((codigo === 401 || codigo === 403) && !yaReintento) {
    // El WMS puede revocar el token antes de su vencimiento.
    invalidarTokenDepot_();
    obtenerTokenDepot_(true);
    return pedirDepot_(ruta, true);
  }
  if (codigo === 404) return null;
  if (codigo !== 200) throw new Error('Depot respondió ' + codigo + ' en ' + ruta);

  var texto = r.getContentText();
  if (!texto || !texto.trim()) return null;
  try {
    return JSON.parse(texto);
  } catch (e) {
    throw new Error('Depot respondió algo que no es JSON: ' + texto.substring(0, 120));
  }
}

// ========================================================================== //
// Acciones
// ========================================================================== //

/** Prueba gettoken y getstock por separado, para saber cuál de los dos falla. */
function accionDiagnostico_(p) {
  var pasos = [];
  var t0 = Date.now();
  try {
    obtenerTokenDepot_(true);
    pasos.push({ paso: 'gettoken', ok: true, ms: Date.now() - t0 });
  } catch (e) {
    pasos.push({ paso: 'gettoken', ok: false, ms: Date.now() - t0, mensaje: e.message });
    return { exito: false, pasos: pasos };
  }

  var t1 = Date.now();
  try {
    var cuerpo = pedirDepot_(CFG.rutaStock + encodeURIComponent(p.codigo || ''), false);
    var filas = filasDe_(cuerpo || []);
    pasos.push({
      paso: 'getstock', ok: true, ms: Date.now() - t1,
      filas: filas.length,
      muestra: filas.length ? mapearStock_(filas[0]) : null,
      camposCrudos: filas.length ? Object.keys(filas[0]) : []
    });
    return { exito: true, pasos: pasos };
  } catch (e) {
    pasos.push({ paso: 'getstock', ok: false, ms: Date.now() - t1, mensaje: e.message });
    return { exito: false, pasos: pasos };
  }
}

/**
 * Descarga el catálogo completo.
 *
 * `getstock` sin código devuelve todo: el precalentado es UNA llamada, igual
 * que hace el Centro de Control con "Extraer Stock desde API".
 */
function accionCatalogo_() {
  var cuerpo = pedirDepot_(CFG.rutaStock, false);
  var filas = filasDe_(cuerpo || []);

  var productos = [];
  var vistos = {};
  for (var i = 0; i < filas.length; i++) {
    var p = mapearStock_(filas[i]);
    if (!p || !p.sku || vistos[p.sku]) continue;
    vistos[p.sku] = true;
    productos.push(p);
  }
  return { exito: true, productos: productos, filas: filas.length };
}

function accionProducto_(p) {
  var codigo = normalizar_(p.codigo);
  if (!codigo) return { exito: false, mensaje: 'Código vacío.' };

  var cuerpo = pedirDepot_(CFG.rutaStock + encodeURIComponent(codigo), false);
  var filas = filasDe_(cuerpo || []);
  if (!filas.length) return { exito: true, producto: null };

  // La API puede devolver varias filas del mismo producto (una por ubicación).
  for (var i = 0; i < filas.length; i++) {
    var m = mapearStock_(filas[i]);
    if (m && (m.sku === codigo || m.ean === codigo)) return { exito: true, producto: m };
  }
  return { exito: true, producto: mapearStock_(filas[0]) };
}

function accionEstadoToken_() {
  var guardado = PROPS.getProperty('DEPOT_TOKEN_CACHE');
  if (!guardado) return { exito: true, hayToken: false };
  try {
    var reg = JSON.parse(guardado);
    var restante = reg.venceEn - Date.now();
    return {
      exito: true, hayToken: true, vigente: restante > 0,
      minutosRestantes: Math.max(Math.round(restante / 60000), 0),
      obtenidoEn: new Date(reg.obtenidoEn).toISOString()
      // El valor del token no se devuelve nunca.
    };
  } catch (e) {
    return { exito: true, hayToken: false };
  }
}

/**
 * Guarda una foto de evidencia en Drive.
 *
 * Reemplaza a Cloud Storage, que desde febrero de 2026 exige el plan Blaze.
 */
function accionSubirFoto_(p, usuario) {
  if (!CFG.carpeta) throw new Error('Falta CARPETA_EVIDENCIAS en las propiedades del script.');
  if (!p.base64) throw new Error('Falta la imagen.');

  var raiz = DriveApp.getFolderById(CFG.carpeta);
  var sub = carpetaDe_(raiz, String(p.recepcion || 'sin-recepcion'));

  var tipo = p.tipo || 'image/jpeg';
  var ext = tipo.indexOf('png') > -1 ? 'png' : 'jpg';
  var nombre = [p.sku || 'sku', Date.now()].join('_') + '.' + ext;

  var blob = Utilities.newBlob(Utilities.base64Decode(p.base64), tipo, nombre);
  var archivo = sub.createFile(blob);
  archivo.setDescription('Recepción ' + p.recepcion + ' · SKU ' + p.sku +
                         ' · ' + usuario.email);

  return {
    exito: true,
    fileId: archivo.getId(),
    url: 'https://drive.google.com/uc?id=' + archivo.getId(),
    enlace: archivo.getUrl()
  };
}

function carpetaDe_(padre, nombre) {
  var it = padre.getFoldersByName(nombre);
  return it.hasNext() ? it.next() : padre.createFolder(nombre);
}

/** Envía el informe final de la recepción. */
function accionEnviarInforme_(p, usuario) {
  if (!p.destinatarios) throw new Error('Faltan los destinatarios.');
  var r = p.resumen || {};

  var filas = (r.discrepancias || []).map(function (d) {
    var color = d.estado === 'Sobrante' ? '#ef4444' : '#f59e0b';
    return '<tr>' +
      '<td style="padding:10px;border-bottom:1px solid #e2e8f0;font-family:monospace;font-weight:bold;">' + d.sku + '</td>' +
      '<td style="padding:10px;text-align:center;border-bottom:1px solid #e2e8f0;color:#64748b;">' + d.esperado + '</td>' +
      '<td style="padding:10px;text-align:center;border-bottom:1px solid #e2e8f0;font-weight:bold;">' + d.fisico + '</td>' +
      '<td style="padding:10px;text-align:center;color:' + color + ';font-weight:bold;border-bottom:1px solid #e2e8f0;">' +
        (d.diferencia > 0 ? '+' + d.diferencia : d.diferencia) + ' (' + d.estado + ')</td></tr>';
  }).join('');

  if (!filas) {
    filas = '<tr><td colspan="4" style="padding:20px;text-align:center;color:#10b981;' +
            'font-weight:bold;background:#ecfdf5;">Inventario cuadrado. Sin diferencias.</td></tr>';
  }

  var fotos = (p.fotos || []).map(function (f) {
    return '<a href="' + f.enlace + '" style="display:inline-block;margin:4px;">' +
           '<img src="' + f.url + '" style="max-width:150px;max-height:150px;border-radius:8px;' +
           'border:1px solid #cbd5e1;"></a>';
  }).join('');

  var html =
    '<div style="font-family:Segoe UI,sans-serif;max-width:680px;margin:0 auto;' +
    'border:1px solid #cbd5e1;border-radius:12px;overflow:hidden;">' +
      '<div style="background:#0f172a;color:#fff;padding:25px;text-align:center;">' +
        '<h2 style="margin:0;">ITSANET IMS — Informe de Recepción</h2>' +
        '<p style="margin:5px 0 0;color:#94a3b8;font-size:14px;">' + (p.recepcion || '') + '</p>' +
      '</div>' +
      '<div style="padding:30px;background:#f8fafc;">' +
        '<p><b>Cerrada por:</b> ' + usuario.email + ' &nbsp;|&nbsp; ' +
           '<b>Duración:</b> ' + (p.duracion || '—') + '</p>' +
        '<p><b>Unidades sistema:</b> ' + (r.unidadesEsperadas || 0) + ' &nbsp;|&nbsp; ' +
           '<b>Físicas:</b> ' + (r.unidadesFisicas || 0) + ' &nbsp;|&nbsp; ' +
           '<b>Exactitud:</b> ' + (r.exactitud || 0) + '%</p>' +
        '<p><b>SKU:</b> ' + (r.ok || 0) + ' Ok · ' + (r.faltante || 0) + ' Faltante · ' +
           (r.sobrante || 0) + ' Sobrante' +
           (r.adicionales ? ' · ' + r.adicionales + ' adicionales' : '') + '</p>' +
        '<h3 style="border-bottom:2px solid #2563eb;padding-bottom:8px;">Discrepancias</h3>' +
        '<table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #e2e8f0;">' +
          '<thead><tr style="background:#f1f5f9;text-align:left;font-size:12px;color:#475569;">' +
            '<th style="padding:12px;">Referencia</th>' +
            '<th style="padding:12px;text-align:center;">Esperado</th>' +
            '<th style="padding:12px;text-align:center;">Físico</th>' +
            '<th style="padding:12px;text-align:center;">Diferencia</th>' +
          '</tr></thead><tbody>' + filas + '</tbody></table>' +
        (fotos ? '<h3 style="border-bottom:2px solid #2563eb;padding-bottom:8px;margin-top:30px;">' +
                 'Evidencias</h3><div>' + fotos + '</div>' : '') +
      '</div></div>';

  var opciones = { to: p.destinatarios, subject: 'Informe de Recepción: ' + (p.recepcion || ''),
                   htmlBody: html };
  if (p.adjuntoBase64) {
    opciones.attachments = [Utilities.newBlob(
      Utilities.base64Decode(p.adjuntoBase64),
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      (p.nombreAdjunto || 'packing-list-final') + '.xlsx')];
  }
  MailApp.sendEmail(opciones);

  return { exito: true, enviadoA: p.destinatarios, cuotaRestante: MailApp.getRemainingDailyQuota() };
}

// ========================================================================== //
// Mapeo
// ========================================================================== //

function normalizar_(valor) {
  return String(valor === null || valor === undefined ? '' : valor)
    .replace(/[ ​﻿]/g, ' ')
    .toUpperCase()
    .replace(/[\s\-_.]/g, '');
}

function limpiarTexto_(valor) {
  return String(valor === null || valor === undefined ? '' : valor)
    .replace(/[ ​﻿]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function filasDe_(cuerpo) {
  if (Array.isArray(cuerpo)) return cuerpo;
  if (!cuerpo || typeof cuerpo !== 'object') return [];
  var claves = ['data', 'result', 'stock', 'productos', 'items', 'Table', 'rows'];
  for (var i = 0; i < claves.length; i++) {
    if (Array.isArray(cuerpo[claves[i]])) return cuerpo[claves[i]];
  }
  return [cuerpo];
}

/** Los nombres de campo no están documentados: se aceptan las variantes usuales. */
function mapearStock_(fila) {
  if (!fila || typeof fila !== 'object') return null;

  var sku = fila.codigo_producto || fila.CodProducto || fila.cod_producto ||
            fila.codProducto || fila.producto_id || fila.codigo || fila.sku ||
            fila.Codigo || fila.CODIGO;
  if (!sku) return null;

  var ean = fila.codigo_barra || fila.codigoBarra || fila.CodigoBarra ||
            fila.ean || fila.EAN || fila.barcode;
  if (ean && (String(ean).toUpperCase() === 'DEFAULT' || String(ean) === '0')) ean = null;

  var stock = fila.stock !== undefined ? fila.stock
            : fila.Stock !== undefined ? fila.Stock
            : fila.cantidad !== undefined ? fila.cantidad
            : fila.existencia !== undefined ? fila.existencia : 0;

  return {
    sku: normalizar_(sku),
    descripcion: limpiarTexto_(fila.descripcion || fila.Descripcion || fila.DESCRIPCION ||
                               fila.nombre || fila.detalle || ''),
    ean: ean ? normalizar_(ean) : null,
    unidad: limpiarTexto_(fila.unidad || fila.unidad_id || fila.Unidad || '') || null,
    stock: Number(stock) || 0
  };
}

// ========================================================================== //
// Utilidades para el administrador (ejecutar desde el editor)
// ========================================================================== //

/** Comprueba la configuración sin exponer ningún secreto. */
function verificarConfiguracion() {
  var faltan = [];
  if (!CFG.baseUrl) faltan.push('DEPOT_BASE_URL');
  if (!CFG.apiKey) faltan.push('FIREBASE_API_KEY');
  if (!CFG.dominio) faltan.push('DOMINIO_PERMITIDO');
  if (!CFG.carpeta) faltan.push('CARPETA_EVIDENCIAS (solo si se usarán fotos)');

  Logger.log(faltan.length
    ? 'FALTAN propiedades: ' + faltan.join(', ')
    : 'Configuración completa.');
  Logger.log('URL base: ' + (CFG.baseUrl || '(sin configurar)'));
  Logger.log('Dominio permitido: ' + (CFG.dominio || '(sin restringir — PELIGROSO)'));
  return faltan;
}

/** Prueba la conexión con Depot desde el editor, sin pasar por la app. */
function probarDepot() {
  try {
    var token = obtenerTokenDepot_(true);
    Logger.log('gettoken OK. Token de ' + token.length + ' caracteres.');
    var cuerpo = pedirDepot_(CFG.rutaStock, false);
    var filas = filasDe_(cuerpo || []);
    Logger.log('getstock OK. ' + filas.length + ' filas.');
    if (filas.length) {
      Logger.log('Campos que devuelve: ' + Object.keys(filas[0]).join(', '));
      Logger.log('Primera fila mapeada: ' + JSON.stringify(mapearStock_(filas[0])));
    }
  } catch (e) {
    Logger.log('ERROR: ' + e.message);
  }
}
