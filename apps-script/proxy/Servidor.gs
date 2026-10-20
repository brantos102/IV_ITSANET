/** Puente adicional para MySQL. No modifica la autenticacion Firebase existente.
 * Propiedad: SERVIDOR_HMAC (min. 32 caracteres). MySQL conserva la trazabilidad.
 * Copiar este archivo al MISMO proyecto y actualizar su despliegue /exec.
 */
/** Ejecutar desde el editor para autorizar y diagnosticar Google sin enviar correo. */
function verificarGoogleServidor() {
  // En el editor, Google solicita los permisos pendientes antes de consultar
  // la identidad. Declarar los scopes en el manifiesto no concede autorización.
  ScriptApp.requireAllScopes(ScriptApp.AuthMode.FULL);
  var props = PropertiesService.getScriptProperties();
  var cuenta;
  try {
    cuenta = String(Session.getEffectiveUser().getEmail() || '').trim().toLowerCase();
    if (!cuenta) throw new Error('Google no devolvió el correo de la cuenta ejecutora.');
  } catch (error) {
    throw new Error('CUENTA GOOGLE: ' + String(error.message || error));
  }
  Logger.log('CUENTA GOOGLE: ' + cuenta);
  Logger.log('CLAVE CONFIGURADA: ' + ((props.getProperty('SERVIDOR_HMAC') || '').length >= 32));
  var valor = String(props.getProperty('CARPETA_EVIDENCIAS') || '').trim();
  var enlace = valor.match(/\/folders\/([A-Za-z0-9_-]+)/);
  var id = enlace ? enlace[1] : valor;
  if (!/^[A-Za-z0-9_-]{10,128}$/.test(id)) {
    throw new Error('CARPETA DRIVE: configura CARPETA_EVIDENCIAS con el ID o enlace de una carpeta.');
  }
  try {
    var carpeta = DriveApp.getFolderById(id);
    Logger.log('CARPETA DRIVE: ' + carpeta.getName());
    Logger.log('ENLACE DRIVE: ' + carpeta.getUrl());
  } catch (error) {
    throw new Error('CARPETA DRIVE: ' + String(error.message || error));
  }
  try {
    Logger.log('CUOTA DE CORREO DISPONIBLE: ' + MailApp.getRemainingDailyQuota());
  } catch (error) {
    throw new Error('PERMISO DE CORREO: ' + String(error.message || error));
  }
  Logger.log('COMPROBACIÓN TERMINADA: no se enviaron correos ni se modificaron archivos.');
}

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
    var raiz = raizServidor_(p.datos || {});
    return { exito: true, versionPuente: 2, remitente: remitente, carpeta: raiz.getUrl(), nombreCarpeta: raiz.getName(),
      carpetaId: typeof raiz.getId === 'function' ? raiz.getId() : '', capacidades: ['rutasEvidencias','papelera','manifiesto','carpetaSku','pruebaCorreo','prepararCarpeta','vinculosSku','fotosSkuSimples','fotosAuditables'].concat(typeof gmailConsultarServidor_==='function'&&typeof accionEnviarInforme_==='function'&&accionEnviarInforme_.versionServidor>=4?['gmailHilos']:[]).concat(
        typeof accionEnviarInforme_==='function' && accionEnviarInforme_.versionServidor>=2 ? ['correoVerificado'].concat(accionEnviarInforme_.versionServidor>=3?['correoEditable']:[]) : []) };
  }
  if(p.operacion==='gmailBuscar'||p.operacion==='gmailMensaje') {
    if(typeof gmailConsultarServidor_!=='function')throw new Error('Publica Gmail.gs antes de consultar el buzón.');
    return gmailConsultarServidor_(p.operacion,p.datos||{});
  }
  if(p.operacion==='miniatura'){
    if(!/^[A-Za-z0-9_-]{5,128}$/.test(p.datos.fileId||''))throw new Error('Imagen no válida.');
    var foto=DriveApp.getFileById(p.datos.fileId),blob=foto.getThumbnail();
    if(!blob&&foto.getSize()<=262144)blob=foto.getBlob();
    if(!blob||blob.getBytes().length>300000)throw new Error('Vista previa no disponible; abre la imagen en Drive.');
    return {exito:true,base64:Utilities.base64Encode(blob.getBytes()),tipo:blob.getContentType()};
  }
  var lock = LockService.getScriptLock();
  lock.waitLock(15000);
  try {
    if (p.operacion === 'prepararCarpeta') {
      var recepcion = carpetaRecepcionServidor_(p.datos);
      return {exito:true,remitente:remitente,carpeta:recepcion.getUrl()};
    }
    if (p.operacion === 'pruebaCorreo') {
      var destinatario = String(p.datos.destinatario || '').trim();
      if (!/^[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+$/.test(destinatario)) throw new Error('Destinatario de prueba inválido.');
      var llave = 'SERVIDOR_PRUEBA_' + p.clave;
      var anterior = PROPS.getProperty(llave);
      if (anterior && anterior.split('|')[1] !== destinatario) throw new Error('Esta referencia corresponde a otro destinatario.');
      if (anterior === 'ENVIADO|'+destinatario) return {exito:true,remitente:remitente,destinatario:destinatario};
      if (anterior) return {exito:false,revision:true};
      PROPS.setProperty(llave,'ENVIANDO|'+destinatario);
      MailApp.sendEmail({to:destinatario,subject:'ITSANET · prueba de conexión de recepción',
        body:'Prueba autorizada de conexión de Drive y correo. Remitente responsable: '+remitente+'. Referencia: '+p.clave+'. No corresponde a un informe final de recepción.'});
      PROPS.setProperty(llave,'ENVIADO|'+destinatario);
      return {exito:true,remitente:remitente,destinatario:destinatario};
    }
    if (p.operacion === 'archivo') return archivoServidor_(p.clave, p.datos);
    if (p.operacion === 'papelera') {
      if (!/^[A-Za-z0-9_-]{5,128}$/.test(String(p.datos.fileId || ''))) throw new Error('Archivo no valido.');
      DriveApp.getFileById(p.datos.fileId).setTrashed(true);
      return {exito:true};
    }
    if (p.operacion === 'finalizar') return finalizarServidor_(p.clave, p.datos);
    throw new Error('Operacion de servidor no permitida.');
  } finally { lock.releaseLock(); }
}

function raizServidor_(p) {
  var id = p.carpetaRaiz || exigirCarpeta_();
  if (p.carpetaRaiz && !/^[A-Za-z0-9_-]{10,128}$/.test(id)) throw new Error('Repositorio invalido.');
  return DriveApp.getFolderById(id);
}

function carpetaRecepcionServidor_(p) {
  var raiz = raizServidor_(p);
  if (!p.cliente) return carpetaDeRecepcion_(raiz, p); // Entregas antiguas conservan su destino.
  var cliente = carpetaDe_(raiz, limpiarNombre_(p.cliente));
  var marca = p.marca ? carpetaDe_(cliente, limpiarNombre_(p.marca)) : cliente;
  var r = carpetaDe_(marca, limpiarNombre_(p.carpetaRecepcion || p.recepcion || p.codigo));
  return r;
}

function carpetaEvidenciaServidor_(recepcion, p) {
  if (!p.ruta) return carpetaDe_(recepcion, 'imagenes');
  if (!Array.isArray(p.ruta) || p.ruta.length > 8) throw new Error('Ruta de evidencia invalida.');
  return p.ruta.reduce(function(c, n) {
    if (typeof n !== 'string' || n.length > 180 || !n.trim()) throw new Error('Carpeta de evidencia invalida.');
    return carpetaDe_(c, limpiarNombre_(n));
  }, recepcion);
}

/** Consultar rutas anteriores nunca crea carpetas vacías ni sale de la recepción. */
function buscarCarpetaEvidenciaServidor_(recepcion, ruta) {
  if(!Array.isArray(ruta)||!ruta.length||ruta.length>8)return null;
  var carpeta=recepcion;
  for(var i=0;i<ruta.length;i++){
    if(typeof ruta[i]!=='string'||!ruta[i].trim()||ruta[i].length>180)throw new Error('Ruta anterior no válida.');
    var encontradas=carpeta.getFoldersByName(limpiarNombre_(ruta[i]));
    if(!encontradas.hasNext())return null;
    carpeta=encontradas.next();
  }
  return carpeta;
}

function buscarFotoServidor_(carpeta,clave) {
  var fotos=carpeta.getFiles(),marca='ITSANET '+clave+' |',sufijo='__'+clave.split(':')[1];
  while(fotos.hasNext()){
    var f=fotos.next();
    if(f.getTargetId&&f.getTargetId())continue;
    if(f.getDescription&&String(f.getDescription()).indexOf(marca)===0 ||
       f.getName&&f.getName().indexOf(sufijo)>=0)return f;
  }
  return null;
}

/** Retira solo accesos directos a ESTA imagen en rutas conocidas. El binario no se toca. */
function limpiarAccesosFotoServidor_(recepcion,archivo,carpeta,p) {
  var permitidas={},retirados=0;
  (p.rutasVinculadas||[]).forEach(function(v){var c=carpetaEvidenciaServidor_(recepcion,v);permitidas[c.getId()]=true;});
  var revisar=[carpeta].concat((p.rutasAnteriores||[]).map(function(r){return buscarCarpetaEvidenciaServidor_(recepcion,r);}).filter(Boolean)),vistos={};
  revisar.forEach(function(c){
    if(vistos[c.getId()])return;vistos[c.getId()]=true;
    var fotos=c.getFiles(),conservado=false;
    while(fotos.hasNext()){
      var f=fotos.next();
      if(!f.getTargetId||f.getTargetId()!==archivo.getId())continue;
      if(c.getId()!==carpeta.getId()&&permitidas[c.getId()]&&!conservado){conservado=true;continue;}
      f.setTrashed(true);retirados++;
    }
  });
  return retirados;
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
  if (p.fileId && (!/^[A-Za-z0-9_-]{5,128}$/.test(p.fileId) || p.tipoArchivo !== 'foto')) throw new Error('Archivo de evidencia invalido.');
  if (!p.fileId && (!p.base64 || p.base64.length > 16777220)) throw new Error('Archivo demasiado grande o vacio.');
  var recepcion = carpetaRecepcionServidor_(p);
  var carpeta = p.tipoArchivo === 'foto' ? carpetaEvidenciaServidor_(recepcion,p)
    : p.cliente ? carpetaDe_(recepcion, 'INFORMES') : recepcion;
  var original = limpiarNombre_(p.nombre) || 'archivo';
  var punto = original.lastIndexOf('.');
  var nombre = (punto < 0 ? original : original.slice(0, punto)) + '__' + clave.split(':')[1]
    + (punto < 0 ? '' : original.slice(punto));
  var existentes = carpeta.getFilesByName(nombre);
  var archivo = p.fileId ? DriveApp.getFileById(p.fileId) : existentes.hasNext() ? existentes.next() : null;
  // El identificador técnico queda en la descripción, no en el nombre visible.
  // Buscarlo conserva la idempotencia aunque se pierda la respuesta tras renombrar.
  if(!archivo && p.tipoArchivo==='foto')archivo=buscarFotoServidor_(carpeta,clave);
  if(!archivo && p.tipoArchivo==='foto' && p.versionFotos===2){
    (p.rutasAnteriores||[]).some(function(r){var anterior=buscarCarpetaEvidenciaServidor_(recepcion,r);if(anterior)archivo=buscarFotoServidor_(anterior,clave);return !!archivo;});
  }
  if(!archivo)archivo=carpeta.createFile(Utilities.newBlob(Utilities.base64Decode(p.base64),p.tipo,nombre));
  if (p.fileId || p.versionFotos===2) {
    // Los informes anteriores pueden enlazar la ubicación antigua: conservar un acceso directo.
    if(p.conservarAccesosPrevios!==false&&archivo.getParents){var padres=archivo.getParents();while(padres.hasNext()){var padre=padres.next();if(padre.getId()!==carpeta.getId()){
      var refs=padre.getFiles(),hay=false;while(refs.hasNext()){var ref=refs.next();if(ref.getTargetId&&ref.getTargetId()===archivo.getId())hay=true;}
      if(!hay){var previo=DriveApp.createShortcut(archivo.getId());previo.moveTo(padre);previo.setName(original);}
    }}}
    archivo.moveTo(carpeta);archivo.setName(nombre);
  }
  archivo.setDescription('ITSANET ' + clave + ' | Recepcion ' + p.recepcion + ' | ' + p.usuario+
    (p.versionFotos===2?' | Secuencia '+p.secuencia+' | Original '+p.nombreOriginal+' | Embarques '+(p.embarques||[]).join(', '):''));
  if(p.tipoArchivo==='foto'){nombre=original;archivo.setName(nombre);}
  var vinculos = {};
  (p.rutasVinculadas || []).forEach(function(v) {
    var destino=carpetaEvidenciaServidor_(recepcion,v);
    if(destino.getUrl()!==carpeta.getUrl()) {
      var nombreEnlace=(p.versionFotos===2?'ACCESO__':'')+limpiarNombre_(v.nombre||nombre),existentes=destino.getFiles(),encontrado=false;
      while(existentes.hasNext()){var f=existentes.next();if(f.getId()===archivo.getId() || f.getTargetId&&f.getTargetId()===archivo.getId()){encontrado=true;f.setName(nombreEnlace);}}
      if(!encontrado){var enlace=DriveApp.createShortcut(archivo.getId());enlace.moveTo(destino);enlace.setName(nombreEnlace);enlace.setDescription('ITSANET ACCESO '+clave);}
    }
    vinculos[v.categoria+'|'+v.sku]={carpeta:destino.getUrl(),carpetaSkuUrl:v.sku?carpetaEvidenciaServidor_(recepcion,{ruta:v.rutaSku && v.rutaSku.length ? v.rutaSku : v.ruta.slice(0,-1)}).getUrl():''};
  });
  var retirados=p.versionFotos===2&&p.conservarAccesosPrevios===false?limpiarAccesosFotoServidor_(recepcion,archivo,carpeta,p):0;
  return { exito: true, fileId: archivo.getId(), nombre: original, tipoArchivo: p.tipoArchivo,accesosRetirados:retirados,
    enlace: archivo.getUrl(), url: 'https://drive.google.com/uc?id=' + archivo.getId(),
    carpeta: carpeta.getUrl(), carpetaRecepcionUrl: recepcion.getUrl(),vinculosDrive:vinculos,
    carpetaSkuUrl: p.sku && p.ruta && p.ruta.length
      ? carpetaEvidenciaServidor_(recepcion, {ruta:p.rutaSku && p.rutaSku.length ? p.rutaSku : p.ruta.slice(0,-1)}).getUrl() : '' };
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
  var carpeta = carpetaRecepcionServidor_(p);
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
  var ids = {};
  (p.archivos || []).forEach(function(a) { ids[a.fileId] = true; });
  var colocados = {};
  (p.manifiesto || []).forEach(function(f) {
    if (!ids[f.fileId]) throw new Error('La evidencia no pertenece a la entrega.');
    var archivoFoto = DriveApp.getFileById(f.fileId);
    var destino = carpetaEvidenciaServidor_(carpeta,f), nombreFoto = limpiarNombre_(f.nombreFinal);
    if (!colocados[f.fileId]) {
      archivoFoto.moveTo(destino); archivoFoto.setName(nombreFoto); colocados[f.fileId] = true;
    } else {
      var enlaces = destino.getFiles(), existe = false;
      while(enlaces.hasNext()) { var enlace = enlaces.next(); if(enlace.getId() === f.fileId || (enlace.getTargetId && enlace.getTargetId() === f.fileId)) {existe = true;enlace.setName(nombreFoto);} }
      if(!existe) {var acceso = DriveApp.createShortcut(f.fileId);acceso.moveTo(destino);acceso.setName(nombreFoto);}
    }
  });
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
  var resultadoCorreo=null;
  if (p.destinatarios) {
    if(typeof accionEnviarInforme_!=='function' || !(accionEnviarInforme_.versionServidor>=2))throw new Error('Actualiza Proxy.gs y Servidor.gs juntos y publica una nueva version del despliegue /exec.');
    var destinatarios = p.destinatarios.split(',');
    if (destinatarios.length > 20 || destinatarios.some(function(c) { return !/^[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+$/.test(c); })) throw new Error('Destinatarios no validos.');
    if (MailApp.getRemainingDailyQuota() < destinatarios.length) throw new Error('Cuota de correo insuficiente.');
    var adjuntos = (p.archivos || []).filter(function(a) { return a.tipoArchivo === 'informe'; }).map(function(a) {
      return { nombre: a.nombre.replace(/\.xlsx$/i, ''), base64: Utilities.base64Encode(DriveApp.getFileById(a.fileId).getBlob().getBytes()) };
    });
    var fotos = fotosCorreoServidor_(p.archivos || [], p.manifiesto || [], p.correoFinal&&p.correoFinal.imagenesDrive);
    resultadoCorreo=accionEnviarInforme_({ recepcion: p.codigo, destinatarios: p.destinatarios,
      duracion: p.duracion, resumen: p.resumen, adjuntos: adjuntos, informe: p.informe,
      cliente:p.cliente, marca:p.marca, cerradoPor:p.solicitadoPor, entregaId:id,
      carpetaUrl: carpeta.getUrl(), sheetUrl: sheet,
      fotos: fotos, correoFinal:p.correoFinal
    }, { email: p.usuario }, function() {
      // Persistir justo ANTES de MailApp, después de preparar y validar el correo.
      archivo.setContent(JSON.stringify({ estado: 'CORREO_EN_CURSO', id: id }));
    });
  }
  acuse = { exito: true, id: id, carpeta: carpeta.getUrl(), sheet: sheet,
    carpetaFotos: (p.archivos || []).some(function(a) { return a.tipoArchivo === 'foto'; }) ? (p.cliente ? carpeta.getUrl() : carpetaDe_(carpeta, 'imagenes').getUrl()) : '',
    enviadoA: p.destinatarios || '', remitente: remitente, gmail:resultadoCorreo?resultadoCorreo.gmail||null:null, estado: 'ENTREGADA', confirmadoEn: new Date().toISOString() };
  archivo.setContent(JSON.stringify(acuse));
  return acuse;
}

function fotosCorreoServidor_(archivos, manifiesto, seleccion) {
  var tipos = {};
  manifiesto.forEach(function(f) {
    var ruta = f.ruta || [];
    var tipo = f.tipoEvidencia || ruta[ruta.length-1] || '';
    if (!tipos[f.fileId] || tipo === 'PANORAMICA' || tipo === 'ESTADO_FINAL') tipos[f.fileId] = tipo;
  });
  var fotos = archivos.filter(function(a){return a.tipoArchivo === 'foto';});
  var prioridad = function(a){var t=tipos[a.fileId];return t==='PANORAMICA'?0:t==='ESTADO_FINAL'?1:2;};
  fotos.sort(function(a,b){return prioridad(a)-prioridad(b);});
  if(Array.isArray(seleccion)){
    fotos=fotos.filter(function(a){return seleccion.indexOf(a.fileId)!==-1;});
    fotos.sort(function(a,b){return seleccion.indexOf(a.fileId)-seleccion.indexOf(b.fileId);});
  }
  var bytes = 0;
  return fotos.slice(0,12).map(function(a) {
    var foto = {fileId:a.fileId,enlace:a.enlace, nombre:a.nombre, etiqueta:(tipos[a.fileId] || 'Evidencia').replace(/_/g,' ')};
    try {
      var archivo = DriveApp.getFileById(a.fileId);
      var blob = archivo.getThumbnail();
      if (!blob && archivo.getSize() <= 262144) blob = archivo.getBlob();
      if (blob && /^image\//.test(blob.getContentType())) {
        var cantidad = blob.getBytes().length;
        if (cantidad <= 262144 && bytes+cantidad <= 2097152) {foto.blob=blob;bytes+=cantidad;}
      }
    } catch (e) { /* La foto completa permanece enlazada en Drive. */ }
    return foto;
  });
}
