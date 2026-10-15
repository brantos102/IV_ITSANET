/** Puente adicional para MySQL. No modifica la autenticacion Firebase existente.
 * Propiedad: SERVIDOR_HMAC (min. 32 caracteres). MySQL conserva la trazabilidad.
 * Copiar este archivo al MISMO proyecto y actualizar su despliegue /exec.
 */
function entregaServidor_(peticion) {
  var secreto = PROPS.getProperty('SERVIDOR_HMAC') || '';
  if (secreto.length < 32 || typeof peticion.payload !== 'string') throw new Error('Puente de servidor no configurado.');
  var firma = Utilities.computeHmacSha256Signature(peticion.payload, secreto)
    .map(function(b) { return ('0' + ((b + 256) % 256).toString(16)).slice(-2); }).join('');
  var recibida = String(peticion.firma || '');
  var diferencia = firma.length ^ recibida.length;
  for (var i = 0; i < firma.length; i++) diferencia |= firma.charCodeAt(i) ^ (recibida.charCodeAt(i) || 0);
  if (diferencia) throw new Error('Firma de servidor no valida.');
  var p = JSON.parse(peticion.payload);
  if (!Number.isFinite(p.fecha) || Math.abs(Date.now() / 1000 - p.fecha) > 300) throw new Error('Solicitud expirada.');
  if (!/^[a-f0-9]{32}(:[a-f0-9]{32})?$/.test(p.clave || '')) throw new Error('Identificador no valido.');
  var remitente = cuentaServidor_(p.datos && p.datos.usuario);
  if (p.operacion === 'estado') {
    var raiz = DriveApp.getFolderById(exigirCarpeta_());
    return { exito: true, remitente: remitente, carpeta: raiz.getUrl(), nombreCarpeta: raiz.getName() };
  }
  var lock = LockService.getScriptLock();
  lock.waitLock(15000);
  try {
    if (p.operacion === 'archivo') return archivoServidor_(p.clave, p.datos);
    if (p.operacion === 'finalizar') return finalizarServidor_(p.clave, p.datos);
    throw new Error('Operacion de servidor no permitida.');
  } finally { lock.releaseLock(); }
}

/** MailApp envia como el ejecutor del despliegue; replyTo no cambia el From. */
function cuentaServidor_(supervisor) {
  var real = String(Session.getEffectiveUser().getEmail() || '').trim().toLowerCase();
  var esperado = String(supervisor || '').trim().toLowerCase();
  if (!esperado || real !== esperado) throw new Error('El despliegue debe ejecutarse como el supervisor responsable.');
  return real;
}

function archivoServidor_(clave, p) {
  if (p.tipoArchivo !== 'foto' && p.tipoArchivo !== 'informe') throw new Error('Tipo no permitido.');
  if (!p.base64 || p.base64.length > 16777220) throw new Error('Archivo demasiado grande o vacio.');
  var carpeta = carpetaDeRecepcion_(DriveApp.getFolderById(exigirCarpeta_()), p);
  if (p.tipoArchivo === 'foto') carpeta = carpetaDe_(carpeta, 'imagenes');
  var original = limpiarNombre_(p.nombre) || 'archivo';
  var punto = original.lastIndexOf('.');
  var nombre = (punto < 0 ? original : original.slice(0, punto)) + '__' + clave.split(':')[1]
    + (punto < 0 ? '' : original.slice(punto));
  var existentes = carpeta.getFilesByName(nombre);
  var archivo = existentes.hasNext() ? existentes.next() : carpeta.createFile(
    Utilities.newBlob(Utilities.base64Decode(p.base64), p.tipo, nombre));
  archivo.setDescription('ITSANET ' + clave + ' | Recepcion ' + p.recepcion + ' | ' + p.usuario);
  return { exito: true, fileId: archivo.getId(), nombre: original, tipoArchivo: p.tipoArchivo,
    enlace: archivo.getUrl(), url: 'https://drive.google.com/uc?id=' + archivo.getId() };
}

function celdaServidor_(valor) {
  if (typeof valor === 'number' || typeof valor === 'boolean') return valor;
  var texto = String(valor === null || valor === undefined ? '' : valor).slice(0, 45000);
  return /^[=+@-]/.test(texto) ? "'" + texto : texto;
}

function tablaServidor_(libro, nombre, columnas, datos) {
  var hoja = libro.getSheetByName(nombre) || libro.insertSheet(nombre);
  // Solo se reemplazan hojas de este libro exclusivo de la entrega, nunca el historico.
  hoja.clearContents();
  var filas = [columnas].concat(datos.map(function(d) {
    return columnas.map(function(c) {
      var v = d[c];
      return celdaServidor_(v && typeof v === 'object' ? JSON.stringify(v) : v);
    });
  }));
  if (hoja.getMaxRows() < filas.length) hoja.insertRowsAfter(hoja.getMaxRows(), filas.length - hoja.getMaxRows());
  if (hoja.getMaxColumns() < columnas.length) hoja.insertColumnsAfter(hoja.getMaxColumns(), columnas.length - hoja.getMaxColumns());
  hoja.getRange(1, 1, filas.length, columnas.length).setValues(filas);
  hoja.setFrozenRows(1);
}

function finalizarServidor_(id, p) {
  var remitente = cuentaServidor_(p.usuario);
  var carpeta = carpetaDeRecepcion_(DriveApp.getFolderById(exigirCarpeta_()), p);
  // Solo el acuse de entrega vive aqui: no se registran conteos ni historico en Sheets.
  var control = carpetaDe_(carpeta, 'entregas');
  var nombre = 'entrega_' + id + '.json';
  var existentes = control.getFilesByName(nombre);
  var archivo = existentes.hasNext() ? existentes.next() : control.createFile(
    Utilities.newBlob(JSON.stringify({ estado: 'ARCHIVADA' }), 'application/json', nombre));
  var acuse = JSON.parse(archivo.getBlob().getDataAsString());
  if (acuse.estado === 'ENTREGADA') return acuse;
  if (acuse.estado === 'CORREO_EN_CURSO') return {
    exito: false, revision: true, mensaje: 'Comprueba el correo enviado antes de repetir: confirmacion interrumpida.' };
  var sheet = '';
  // Solo una exportacion solicitada expresamente crea un Sheet nuevo.
  if (p.exportarSheet) {
    var nombreSheet = 'Validacion_' + id;
    var libros = carpeta.getFilesByName(nombreSheet);
    var libro;
    if (libros.hasNext()) libro = SpreadsheetApp.openById(libros.next().getId());
    else {
      libro = SpreadsheetApp.create(nombreSheet);
      DriveApp.getFileById(libro.getId()).moveTo(carpeta);
    }
    tablaServidor_(libro, 'VALIDADOS', ['sku', 'descripcion', 'esperado', 'contado', 'estado', 'verificado', 'pallets'], p.skus || []);
    tablaServidor_(libro, 'LINEAS_ORIGINALES', ['origen', 'linea', 'sku', 'descripcion', 'cantidad', 'cruda'], p.lineas || []);
    tablaServidor_(libro, 'BITACORA', ['id', 'tipo', 'sku', 'cantidad', 'pallet', 'posicionReal', 'origen', 'operadorEmail', 'creadoEn', 'observacion', 'fotos'], p.eventos || []);
    sheet = libro.getUrl();
  }
  if (p.destinatarios) {
    var destinatarios = p.destinatarios.split(',');
    if (destinatarios.length > 20 || destinatarios.some(function(c) { return !/^[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+$/.test(c); })) throw new Error('Destinatarios no validos.');
    if (MailApp.getRemainingDailyQuota() < destinatarios.length) throw new Error('Cuota de correo insuficiente.');
    var adjuntos = (p.archivos || []).filter(function(a) { return a.tipoArchivo === 'informe'; }).map(function(a) {
      return { nombre: a.nombre.replace(/\.xlsx$/i, ''), base64: Utilities.base64Encode(DriveApp.getFileById(a.fileId).getBlob().getBytes()) };
    });
    // Persistir ANTES de enviar: si se interrumpe la respuesta, no reenviar a ciegas.
    archivo.setContent(JSON.stringify({ estado: 'CORREO_EN_CURSO', id: id }));
    accionEnviarInforme_({ recepcion: p.codigo, destinatarios: p.destinatarios,
      duracion: p.duracion, resumen: p.resumen, adjuntos: adjuntos,
      carpetaUrl: carpeta.getUrl(), sheetUrl: sheet,
      fotos: (p.archivos || []).filter(function(a) { return a.tipoArchivo === 'foto'; }).slice(0, 12)
    }, { email: p.usuario });
  }
  acuse = { exito: true, id: id, carpeta: carpeta.getUrl(), sheet: sheet,
    carpetaFotos: (p.archivos || []).some(function(a) { return a.tipoArchivo === 'foto'; }) ? carpetaDe_(carpeta, 'imagenes').getUrl() : '',
    enviadoA: p.destinatarios || '', remitente: remitente, estado: 'ENTREGADA' };
  archivo.setContent(JSON.stringify(acuse));
  return acuse;
}
