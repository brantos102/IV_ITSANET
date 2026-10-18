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
 * contra Google antes de hacer nada, y se exige que tenga un perfil ACTIVO en
 * la aplicación. Sin eso, publicar este script sería abrir la API del WMS a
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
//   FIREBASE_API_KEY      la "apiKey" de la configuración web de Firebase
//   FIREBASE_PROJECT_ID   iv-itsanet
//   FIREBASE_DATABASE_ID  bd-iv-itsanet
//   DOMINIO_PERMITIDO     itsanet.com
//   CARPETA_EVIDENCIAS    id de la carpeta de Drive para las fotos
//
// Las credenciales de cada cliente NO van aquí: se cargan desde el panel de
// administración de la app y se guardan en CRED_<ID>. Ver Clientes.gs.
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
  get carpeta() { return idDeCarpeta_(PROPS.getProperty('CARPETA_EVIDENCIAS')); },
  get rutaToken() { return PROPS.getProperty('DEPOT_RUTA_TOKEN') || '/gettoken'; },
  get rutaStock() { return PROPS.getProperty('DEPOT_RUTA_STOCK') || '/getstock'; },
  get cabeceraToken() { return PROPS.getProperty('DEPOT_CABECERA_TOKEN') || 'token'; }
};

var TTL_TOKEN_SEG = 6 * 60 * 60;    // tope del caché de Apps Script

/**
 * Admite el enlace de Drive, no solo el id.
 *
 * Lo natural es copiar la barra de direcciones y pegarla, y entonces la
 * propiedad guarda
 * `https://drive.google.com/drive/folders/1spP…?usp=sharing`.
 * Rechazar eso y responder «falta CARPETA_EVIDENCIAS» manda a buscar un error
 * de configuración donde solo hay un enlace en vez de un id.
 */
function idDeCarpeta_(valor) {
  var v = String(valor || '').trim();
  if (!v) return '';
  var m = v.match(/[-\w]{25,}/);        // el id de Drive dentro del enlace
  return m ? m[0] : v;
}

/** Mensaje único, para no repetirlo en cada acción que escribe en Drive. */
function exigirCarpeta_() {
  if (CFG.carpeta) return CFG.carpeta;
  throw new Error(
    'La carpeta de evidencias no está configurada. En el Apps Script: ' +
    'Configuración del proyecto → Propiedades del script → CARPETA_EVIDENCIAS, ' +
    'y pega ahí el enlace de la carpeta de Drive o su id.');
}

// ========================================================================== //
// Punto de entrada
// ========================================================================== //

function doPost(e) {
  try {
    var peticion = JSON.parse(e.postData.contents || '{}');
    if (peticion.accion === 'entregaServidor') return responder_(entregaServidor_(peticion));
    var usuario = verificarSesion_(peticion.idToken);

    var acciones = {
      // Multi-cliente: un packing list puede mezclar mercadería de varios.
      listarClientes: accionListarClientes_,
      guardarCliente: accionGuardarCliente_,
      borrarCliente: accionBorrarCliente_,
      probarCliente: accionProbarCliente_,
      catalogo: accionCatalogoMulti_,
      producto: accionProductoMulti_,
      // Resto
      subirFoto: accionSubirFoto_,
      guardarInforme: accionGuardarInforme_,
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

  /**
   * La frontera es el PERFIL, no el dominio del correo.
   *
   * Antes se exigía `@itsanet.com`. Desde que el registro acepta un correo real
   * —incluido uno personal— esa comprobación dejaba fuera a operarios legítimos:
   * entraban en la app y, al subir la foto de un producto no conforme, el proxy
   * les respondía que solo las cuentas del dominio pueden usar el servicio.
   *
   * El perfil es además una frontera más estrecha: una cuenta `@itsanet.com`
   * desactivada pasaba el filtro del dominio y llegaba igual al WMS.
   */
  var perfil = perfilDeUsuario_(u.localId, idToken);
  if (!perfil) {
    throw new Error('Tu cuenta no está dada de alta en la aplicación.');
  }
  if (!perfil.activo) {
    throw new Error('Tu cuenta está desactivada. Habla con tu supervisor.');
  }

  var usuario = {
    uid: u.localId,
    email: u.email,
    nombre: u.displayName || '',
    rol: perfil.rol || 'OPERADOR'
  };

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

/**
 * Lee el token de la respuesta de /gettoken.
 *
 * Los campos son los que usa el Centro de Mando en producción:
 * token, Token, Result o result. Se aceptan además texto plano y respuesta
 * entrecomillada, que no cuestan nada y evitan una sorpresa.
 */
function extraerToken_(texto) {
  var t = String(texto || '').trim();
  if (!t) return null;

  if (t.charAt(0) === '{' || t.charAt(0) === '[') {
    try {
      var j = JSON.parse(t);
      var d = Array.isArray(j) ? j[0] : j;
      var v = d && (d.token || d.Token || d.Result || d.result ||
                    d.TOKEN || d.access_token);
      // Result puede venir anidado en algunos despliegues.
      if (v && typeof v === 'object') v = v.token || v.Token || null;
      return v ? String(v).trim() : null;
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
  var carpeta = exigirCarpeta_();
  if (!p.base64) throw new Error('Falta la imagen.');

  var sub = carpetaDeImagenes_(DriveApp.getFolderById(carpeta), p);

  // El nombre lo decide el servidor y no el navegador: el numero depende de lo
  // que YA hay en la carpeta, y dos operarios fotografiando el mismo producto a
  // la vez elegirian los dos el mismo numero y uno pisaria al otro.
  var tipo = p.tipo || 'image/jpeg';
  var ext = tipo.indexOf('png') > -1 ? 'png' : 'jpg';
  var base = limpiarNombre_(p.sku) || 'SIN-CODIGO';
  var nombre = base + '-' + siguienteFoto_(sub, base) + '.' + ext;

  var blob = Utilities.newBlob(Utilities.base64Decode(p.base64), tipo, nombre);
  var archivo = sub.createFile(blob);
  archivo.setDescription('Recepción ' + p.recepcion + ' · SKU ' + p.sku +
                         ' · ' + usuario.email);

  return {
    exito: true,
    fileId: archivo.getId(),
    nombre: nombre,
    url: 'https://drive.google.com/uc?id=' + archivo.getId(),
    enlace: archivo.getUrl()
  };
}

/**
 * El siguiente numero libre para las fotos de un producto.
 *
 * Se mira el numero de cada archivo, no cuantos hay: si se borro la 1, la
 * siguiente tiene que ser la 3 y no otra 2, que pisaria a la que queda.
 */
function siguienteFoto_(carpeta, base) {
  var patron = new RegExp('^' + base.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') +
                          '-(\\d+)\\.', 'i');
  var mayor = 0;
  var it = carpeta.getFiles();
  while (it.hasNext()) {
    var m = patron.exec(it.next().getName());
    if (m && Number(m[1]) > mayor) mayor = Number(m[1]);
  }
  return mayor + 1;
}

/**
 * Archiva el informe final en Drive, junto a las evidencias de esa recepción.
 *
 * El correo puede borrarse y la descarga del navegador se pierde con el equipo.
 * Si mañana hay una reclamación, el archivo que se subió a Depot tiene que
 * seguir estando en algún sitio de la empresa, con su fecha.
 */
function accionGuardarInforme_(p, usuario) {
  var carpeta = exigirCarpeta_();
  if (!p.base64) throw new Error('Falta el archivo.');

  var sub = carpetaDeRecepcion_(DriveApp.getFolderById(carpeta), p);

  // Si la recepcion se reabre y se vuelve a cerrar, el informe anterior NO se
  // pisa: puede que ya se haya entregado. Se numera v2, v3... en vez de «(2)»,
  // que es lo que pone el explorador cuando algo se duplico sin querer.
  var base = limpiarNombre_(p.nombre) || 'validacion';
  var nombre = base + '.xlsx';
  for (var n = 2; n < 100 && sub.getFilesByName(nombre).hasNext(); n++) {
    nombre = base + '_v' + n + '.xlsx';
  }

  var archivo = sub.createFile(Utilities.newBlob(
    Utilities.base64Decode(p.base64),
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    nombre));
  archivo.setDescription('Informe de la recepción ' + p.recepcion +
                         ' · cerrada por ' + usuario.email);

  return { exito: true, fileId: archivo.getId(), nombre: nombre, enlace: archivo.getUrl() };
}

/**
 * La carpeta de una recepcion: CARPETA_EVIDENCIAS/AAAA-MM/AAAA-MM-DD_CLIENTE_CODIGO
 *
 * El nombre lo calcula el navegador (js/nombres.js, que es donde esta probado) y
 * aqui solo se limpia: una barra en un codigo de cliente no es un nombre, es una
 * ruta, y crearia carpetas que nadie busco.
 *
 * El nivel del mes existe porque sin el, al ano y medio hay trescientas carpetas
 * al mismo nivel y encontrar una es imposible.
 */
function carpetaDeRecepcion_(raiz, p) {
  var mes = limpiarNombre_(p.carpetaMes);
  var propia = limpiarNombre_(p.carpetaRecepcion) ||
               limpiarNombre_(p.recepcion) || 'sin-recepcion';
  var donde = mes ? carpetaDe_(raiz, mes) : raiz;
  return carpetaDe_(donde, propia);
}

/** Dentro de cada recepcion, las fotos aparte de los documentos. */
function carpetaDeImagenes_(raiz, p) {
  return carpetaDe_(carpetaDeRecepcion_(raiz, p), 'imagenes');
}

function carpetaDe_(padre, nombre) {
  var it = padre.getFoldersByName(nombre);
  return it.hasNext() ? it.next() : padre.createFolder(nombre);
}

/** Lo mismo que limpiarNombre de js/nombres.js. Sin barras ni comodines. */
function limpiarNombre_(v) {
  return String(v === null || v === undefined ? '' : v)
    .replace(/[\\\/:*?"<>|#%{}~\[\]]/g, '')
    .replace(/\s+/g, ' ')
    .replace(/^\s|\s$/g, '')
    .replace(/\s/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
}

/** Envía el informe final de la recepción. */
function accionEnviarInforme_(p, usuario, antesDeEnviar) {
  if (!p.destinatarios) throw new Error('Faltan los destinatarios.');
  var r = p.resumen || {};
  var esc = function(v) {return String(v === null || v === undefined ? '' : v).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});};
  var link = function(url, texto) {return /^https:\/\/(drive|docs)\.google\.com\//.test(url || '') ? '<a href="'+esc(url)+'">'+esc(texto)+'</a>' : '';};
  var tabla = function(titulo, filas, incidencia) {
    if (!filas.length) return '';
    return '<h3>'+esc(titulo)+'</h3><table style="width:100%;border-collapse:collapse;font-size:12px" border="1" cellpadding="6">'+
      '<thead style="background:#edf3ff"><tr><th>ITEM</th><th>Descripción</th><th>Declarado</th><th>Físico</th><th>Diferencia</th><th>Pallet</th>'+
      (incidencia ? '<th>Cant. con incidencia</th><th>Incidencia</th>' : '')+'<th>Observación</th></tr></thead><tbody>'+
      filas.map(function(d) {return '<tr>'+[d.sku,d.descripcion,d.esperado,d.fisico === undefined ? d.contado : d.fisico,d.diferencia,d.pallets].map(function(v){return '<td>'+esc(v)+'</td>';}).join('')+
        (incidencia ? '<td>'+esc((d.incidencias || []).reduce(function(n,i){return n+Number(i.cantidad || 0);},0))+'</td><td>'+(d.incidencias || []).map(function(i){return esc(i.nombre || i.tipo)+' ('+esc(i.cantidad)+')';}).join('<br>')+'<br>PNC: '+esc(d.cantidadPnc === null ? 'por revisar' : d.cantidadPnc || 0)+'</td>' : '')+
        '<td>'+esc(d.observacion)+'</td></tr>';}).join('')+'</tbody></table>';
  };
  var inlineImages = {}, fotos = '', bytes = 0;
  (p.fotos || []).slice(0,12).forEach(function(f,i) {
    var imagen = '', cid = 'evidencia'+i;
    if (f.blob && typeof f.blob.getBytes === 'function') {
      var cantidad = f.blob.getBytes().length;
      if (cantidad <= 262144 && bytes+cantidad <= 2097152) {
        inlineImages[cid] = f.blob; bytes+=cantidad;
        imagen='<img src="cid:'+cid+'" alt="'+esc(f.etiqueta || 'Evidencia de recepción')+'" style="max-width:150px;max-height:150px;border:1px solid #ddd">';
      }
    }
    var destino=link(f.enlace, f.etiqueta || f.nombre || 'Abrir evidencia');
    fotos+='<div style="display:inline-block;vertical-align:top;margin:4px;max-width:160px">'+imagen+'<br>'+destino+'</div>';
  });
  var adjuntos = p.adjuntos || [];
  if (!adjuntos.length && p.adjuntoBase64) adjuntos=[{base64:p.adjuntoBase64,nombre:p.nombreAdjunto || 'packing-list-final'}];
  var nombres = adjuntos.map(function(a){return limpiarNombre_(String(a.nombre || 'informe').replace(/\.xlsx$/i,''))+'.xlsx';});
  var informe = p.informe ? 'R'+String(p.informe.numero).padStart(4,'0') : '';
  var textoFecha = p.informe && p.informe.creadoEn || '';
  if (textoFecha && Number.isFinite(new Date(textoFecha).getTime())) textoFecha=Utilities.formatDate(new Date(textoFecha),'America/Guayaquil','yyyy-MM-dd HH:mm:ss')+' (Ecuador)';
  var discrepancias=r.discrepancias || [];
  var html='<div style="font-family:Arial,sans-serif;color:#172033;font-size:14px;max-width:1000px">'+
    '<p>Estimados,</p><p>Se comparte el informe de recepción <b>'+esc(p.recepcion)+'</b>'+
    (p.cliente ? ' del cliente <b>'+esc(p.cliente)+'</b>' : '')+(p.marca ? ' · '+esc(p.marca) : '')+'.</p>'+
    '<p><b>'+link(p.carpetaUrl,'Abrir carpeta de la recepción y todas sus fotografías')+'</b></p>'+
    (fotos ? '<h3>Evidencias de recepción</h3><div>'+fotos+'</div>' : '')+
    '<p><b>Resumen de validación:</b> '+esc(r.unidadesEsperadas || 0)+' unidades declaradas · '+esc(r.unidadesFisicas || 0)+' físicas · '+esc(r.unidadesPnc || 0)+' PNC.<br>'+esc(r.ok || 0)+' referencias sin diferencias de cantidad · '+esc(r.faltante || 0)+' con faltantes · '+esc(r.sobrante || 0)+' con sobrantes.</p>'+
    tabla('Novedades físicas detectadas',r.novedades || [],true)+
    tabla('Producto sobrante',discrepancias.filter(function(d){return d.diferencia>0;}),false)+
    tabla('Producto faltante',discrepancias.filter(function(d){return d.diferencia<0;}),false)+
    (!(r.novedades || []).length && !discrepancias.length ? '<p>Inventario cuadrado. Sin diferencias ni incidencias registradas.</p>' : '')+
    '<p>'+link(p.carpetaUrl,'Ver fotografías completas y estado final de la mercadería')+' '+link(p.sheetUrl,'Abrir validación en Sheets')+'</p>'+
    (adjuntos.length ? '<p><b>'+adjuntos.length+' packing list'+(adjuntos.length===1?' adjunto:':'s adjuntos:')+'</b></p><ul>'+nombres.map(function(n){return '<li>'+esc(n)+'</li>';}).join('')+'</ul>' : '')+
    '<p>Saludos cordiales,<br>'+esc(usuario.email)+'</p><hr><p style="font-size:11px;color:#586477">'+
    esc(informe)+' · '+esc(p.informe && p.informe.id || p.entregaId || '')+' · '+esc(textoFecha)+'<br>Responsable del cierre: '+esc(p.cerradoPor || usuario.email)+'<br>Enviado por: '+esc(usuario.email)+
    (p.duracion ? ' · Duración: '+esc(p.duracion) : '')+'</p></div>';
  var opciones={to:p.destinatarios,subject:'Informe de Recepción: '+(p.recepcion || '')+(informe ? ' · '+informe : '')+
    (adjuntos.length>1 ? ' ('+adjuntos.length+' packing lists)' : ''),
    body:'Informe de recepción '+(p.recepcion || '')+' '+informe+'. Carpeta Drive: '+(p.carpetaUrl || '')+'. Remitente: '+usuario.email+'. Consulte los informes adjuntos.',htmlBody:html};
  if(p.correoFinal){
    var final=p.correoFinal;
    if(typeof final.asunto!=='string'||!final.asunto.trim()||final.asunto.length>250||/[\r\n]/.test(final.asunto)||typeof final.html!=='string'||final.html.length>500000||typeof final.texto!=='string')throw new Error('Correo final no válido. Revisa el borrador.');
    if(String(final.remitente||'').toLowerCase()!==String(usuario.email||'').toLowerCase())throw new Error('El correo revisado pertenece a otro remitente.');
    opciones.subject=final.asunto;opciones.body=final.texto;
    opciones.htmlBody=final.html;
    (p.fotos||[]).slice(0,12).forEach(function(f,i){
      if(f.fileId&&inlineImages['evidencia'+i])opciones.htmlBody=opciones.htmlBody.split('https://drive.google.com/thumbnail?id='+f.fileId+'&amp;sz=w320').join('cid:evidencia'+i);
    });
  }
  if (Object.keys(inlineImages).length) opciones.inlineImages=inlineImages;
  if (adjuntos.length) opciones.attachments=adjuntos.map(function(a,i){
    var contenido=Utilities.base64Decode(a.base64);bytes+=contenido.length;
    return Utilities.newBlob(contenido,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',nombres[i]);
  });
  if (bytes>20971520) throw new Error('Los adjuntos superan 20 MB. Revisa los informes antes de enviar.');
  // Validar y preparar todo antes de registrar el intento irreversible de MailApp.
  if (antesDeEnviar) antesDeEnviar();
  MailApp.sendEmail(opciones);
  return {exito:true,enviadoA:p.destinatarios,adjuntos:nombres,cuotaRestante:MailApp.getRemainingDailyQuota()};
}

accionEnviarInforme_.versionServidor = 3;

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

/**
 * Saca la lista de filas de la respuesta de /getstock.
 *
 * El Centro de Mando acepta: array suelto, o dentro de Result, result o data.
 */
function filasDe_(cuerpo) {
  if (Array.isArray(cuerpo)) return cuerpo;
  if (!cuerpo || typeof cuerpo !== 'object') return [];
  var claves = ['Result', 'result', 'data', 'Data', 'stock', 'items', 'Table', 'rows'];
  for (var i = 0; i < claves.length; i++) {
    if (Array.isArray(cuerpo[claves[i]])) return cuerpo[claves[i]];
  }
  return [cuerpo];
}

/**
 * Traduce una fila de /getstock.
 *
 * Los nombres de campo son los reales del WMS, tomados del Centro de Mando:
 * van en mayúsculas, con espacios y puntos ("COD. PRODUCTO", "NRO. LOTE").
 * Se dejan unas pocas alternativas por si otro despliegue difiere, pero las
 * principales ya no son suposiciones.
 *
 * OJO: la respuesta NO trae código de barras. La validación por EAN no puede
 * salir de aquí; hay que resolverla por otra vía.
 */
function mapearStock_(fila) {
  if (!fila || typeof fila !== 'object') return null;

  var sku = fila['COD. PRODUCTO'] || fila['COD.PRODUCTO'] ||
            fila.codigo_producto || fila.CodProducto || fila.codigo || fila.sku;
  if (!sku) return null;

  // La posición en bodega se arma igual que en el Centro de Mando.
  var pos = [fila['NAVE'], fila['CALLE'], fila['COLUMNA'], fila['NIVEL']]
    .map(function (x) { return limpiarTexto_(x); })
    .filter(function (x) { return x !== ''; })
    .join('-');

  return {
    sku: normalizar_(sku),
    descripcion: limpiarTexto_(fila['DESCRIPCION'] || fila.descripcion || ''),
    unidad: limpiarTexto_(fila['UNIDAD'] || fila.unidad || '') || null,
    stock: Number(limpiarTexto_(fila['CANTIDAD'] || fila.cantidad || 0)) || 0,
    posicion: pos || null,
    lote: limpiarTexto_(fila['NRO. LOTE'] || '') || null,
    serie: limpiarTexto_(fila['NRO. SERIE'] || '') || null,
    partida: limpiarTexto_(fila['NRO. PARTIDA'] || '') || null,
    familia: limpiarTexto_(fila['FAMILIA'] || '') || null,
    estadoMercaderia: limpiarTexto_(fila['EST. MERC.'] || '') || null,
    // El WMS puede devolver, con una sola credencial, el stock de varios
    // clientes. Este campo dice de cuál es cada fila.
    codCliente: limpiarTexto_(fila['COD. CLIENTE'] || '').toUpperCase() || null,
    ean: null   // /getstock no devuelve código de barras
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
  if (!PROPS.getProperty('FIREBASE_PROJECT_ID')) faltan.push('FIREBASE_PROJECT_ID');
  if (!CFG.dominio) faltan.push('DOMINIO_PERMITIDO');
  if (!CFG.carpeta) faltan.push('CARPETA_EVIDENCIAS (solo si se usarán fotos)');

  Logger.log(faltan.length
    ? 'FALTAN propiedades: ' + faltan.join(', ')
    : 'Configuración completa.');
  Logger.log('URL base: ' + (CFG.baseUrl || '(sin configurar)'));
  Logger.log('Dominio permitido: ' + (CFG.dominio || '(sin restringir — PELIGROSO)'));

  var ids = listaIds_();
  Logger.log('Clientes configurados: ' + (ids.length ? ids.join(', ') : 'ninguno'));
  for (var i = 0; i < ids.length; i++) {
    var c = credencialesDe_(ids[i]);
    var t = estadoTokenCliente_(ids[i]);
    Logger.log('  ' + ids[i] + ': usuario ' + enmascarar_(c && c.usuario) +
               ' · token ' + (t.vigente ? t.minutosRestantes + ' min' : 'sin token') +
               (c && c.ultimoError ? ' · ÚLTIMO ERROR: ' + c.ultimoError : ''));
  }
  return faltan;
}

/**
 * Prueba todos los clientes desde el editor, sin pasar por la app.
 * Imprime los nombres de campo que devuelve el WMS: con eso se ajusta el mapeo.
 */
function probarTodosLosClientes() {
  var ids = listaIds_();
  if (!ids.length) { Logger.log('No hay clientes configurados.'); return; }

  for (var i = 0; i < ids.length; i++) {
    var id = ids[i];
    Logger.log('--- ' + id + ' ---');
    try {
      obtenerTokenCliente_(id, true);
      Logger.log('  gettoken OK');
      var cuerpo = pedirCliente_(id, CFG.rutaStock, false);
      var filas = filasDe_(cuerpo || []);
      Logger.log('  getstock OK: ' + filas.length + ' filas');
      if (filas.length) {
        Logger.log('  Campos que devuelve: ' + Object.keys(filas[0]).join(', '));
        Logger.log('  Primera fila mapeada: ' + JSON.stringify(mapearStock_(filas[0])));
      }
    } catch (e) {
      Logger.log('  ERROR: ' + e.message);
    }
  }
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
