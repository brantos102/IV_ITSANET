/** Gmail opcional. Solo lectura y envío; nunca borra, archiva ni marca mensajes. */
function gmailApiServidor_(ruta, opciones) {
  var respuesta = UrlFetchApp.fetch('https://gmail.googleapis.com/gmail/v1/users/me/' + ruta,
    Object.assign({headers:{Authorization:'Bearer '+ScriptApp.getOAuthToken()},muteHttpExceptions:true}, opciones||{}));
  if(respuesta.getResponseCode()>=300)throw new Error('Gmail no autorizó esta operación. Reautoriza los permisos de Gmail y comprueba que Gmail API esté habilitada en el proyecto Google. No repitas un envío sin revisar Enviados.');
  return JSON.parse(respuesta.getContentText());
}

function verificarGmailServidor() {
  ScriptApp.requireAllScopes(ScriptApp.AuthMode.FULL);
  var perfil=gmailApiServidor_('profile');
  Logger.log('Gmail autorizado para: '+perfil.emailAddress+'. No se enviaron ni modificaron correos.');
}

function gmailCabecera_(mensaje, nombre) {
  return String(((mensaje.payload||{}).headers||[]).filter(function(h){return h.name.toLowerCase()===nombre.toLowerCase();})[0]?.value||'').replace(/[\r\n]/g,' ').slice(0,3000);
}
function gmailId_(id) {
  if(!/^[a-f0-9]{8,64}$/.test(String(id||'')))throw new Error('Identificador de Gmail no válido.');
  return id;
}
function gmailFicha_(m) {
  return {id:m.id,threadId:m.threadId,asunto:gmailCabecera_(m,'Subject'),de:gmailCabecera_(m,'From'),
    para:gmailCabecera_(m,'To'),cc:gmailCabecera_(m,'Cc'),replyTo:gmailCabecera_(m,'Reply-To'),fecha:gmailCabecera_(m,'Date'),
    messageId:gmailCabecera_(m,'Message-ID'),references:gmailCabecera_(m,'References'),resumen:String(m.snippet||'').slice(0,500)};
}
function gmailConsultarServidor_(operacion, datos) {
  if(operacion==='gmailBuscar') {
    var q=String(datos.busqueda||'').trim();
    if(!q||q.length>250)throw new Error('Escribe una búsqueda de hasta 250 caracteres.');
    var lista=gmailApiServidor_('messages?maxResults=15&q='+encodeURIComponent(q+' -in:trash -in:spam'));
    return {exito:true,mensajes:(lista.messages||[]).map(function(m){return gmailFicha_(gmailApiServidor_('messages/'+gmailId_(m.id)+'?format=metadata'));}),hayMas:!!lista.nextPageToken};
  }
  var m=gmailApiServidor_('messages/'+gmailId_(datos.mensajeId)+'?format=full'),ficha=gmailFicha_(m),textos=[];
  function partes(p){
    if(p.mimeType==='text/plain'&&p.body&&p.body.data&&textos.join('').length<60000){
      textos.push(Utilities.newBlob(Utilities.base64DecodeWebSafe(p.body.data)).getDataAsString('UTF-8').slice(0,60000));
    }
    (p.parts||[]).slice(0,30).forEach(partes);
  }
  partes(m.payload||{});
  ficha.texto=textos.join('\n').slice(0,60000)||ficha.resumen+'\n\nEste mensaje usa formato HTML. Abre el correo original en Gmail para consultar su contenido y adjuntos completos.';
  ficha.adjuntos=[];
  function adjuntos(p){if(p.filename)ficha.adjuntos.push(String(p.filename).slice(0,200));(p.parts||[]).slice(0,30).forEach(adjuntos);}
  adjuntos(m.payload||{});
  return {exito:true,mensaje:ficha};
}

/** Genera MIME manteniendo el hilo y los documentos de ESTA entrega. */
function gmailPrepararRespuesta_(seleccion, opciones, remitente) {
  if(!seleccion||seleccion.cuenta!==remitente)throw new Error('El hilo seleccionado pertenece a otra cuenta.');
  var original=gmailFicha_(gmailApiServidor_('messages/'+gmailId_(seleccion.id)+'?format=metadata'));
  if(original.threadId!==seleccion.threadId||!/^<[^<>\s]+>$/.test(original.messageId))throw new Error('No se pudo confirmar el mensaje original del hilo.');
  var asunto=original.asunto.replace(/^(re:\s*)+/i,'');
  if(opciones.subject!=='Re: '+asunto)throw new Error('La respuesta debe conservar el asunto original de Gmail.');
  var b='itsanet_'+Utilities.getUuid().replace(/-/g,''),alt=b+'_texto',rel=b+'_imagenes';
  var codificar=function(v){return Utilities.base64Encode(String(v),Utilities.Charset.UTF_8);};
  var bloque=function(blob,tipo,nombre,cid){
    var nombreSeguro=String(nombre||'adjunto').replace(/["\r\n\\]/g,'_');
    return 'Content-Type: '+tipo+'\r\nContent-Transfer-Encoding: base64\r\nContent-Disposition: '+(cid?'inline':'attachment')+'; filename="'+nombreSeguro+'"\r\n'+(cid?'Content-ID: <'+cid+'>\r\n':'')+'\r\n'+Utilities.base64Encode(blob.getBytes())+'\r\n';
  };
  var caracteres=Array.from(opciones.subject),palabras=[];
  while(caracteres.length)palabras.push('=?UTF-8?B?'+codificar(caracteres.splice(0,10).join(''))+'?=');
  var referencias=(original.references.match(/<[^<>\s]{1,200}>/g)||[]).slice(-10).concat([original.messageId]);
  var mime='MIME-Version: 1.0\r\nFrom: '+remitente+'\r\nTo: '+opciones.to.split(',').join(',\r\n ')+'\r\nSubject: '+palabras.join('\r\n ')+'\r\nIn-Reply-To: '+original.messageId+'\r\nReferences: '+referencias.join('\r\n ')+'\r\nContent-Type: multipart/mixed; boundary="'+b+'"\r\n\r\n';
  mime+='--'+b+'\r\nContent-Type: multipart/related; boundary="'+rel+'"\r\n\r\n--'+rel+'\r\nContent-Type: multipart/alternative; boundary="'+alt+'"\r\n\r\n';
  mime+='--'+alt+'\r\nContent-Type: text/plain; charset=UTF-8\r\nContent-Transfer-Encoding: base64\r\n\r\n'+codificar(opciones.body)+'\r\n--'+alt+'\r\nContent-Type: text/html; charset=UTF-8\r\nContent-Transfer-Encoding: base64\r\n\r\n'+codificar(opciones.htmlBody)+'\r\n--'+alt+'--\r\n';
  Object.keys(opciones.inlineImages||{}).forEach(function(cid){var blob=opciones.inlineImages[cid];mime+='--'+rel+'\r\n'+bloque(blob,blob.getContentType(),cid,cid);});
  mime+='--'+rel+'--\r\n';
  (opciones.attachments||[]).forEach(function(blob){mime+='--'+b+'\r\n'+bloque(blob,blob.getContentType(),blob.getName());});
  mime+='--'+b+'--\r\n';
  return {threadId:original.threadId,raw:Utilities.base64EncodeWebSafe(mime,Utilities.Charset.UTF_8).replace(/=+$/,'')};
}
