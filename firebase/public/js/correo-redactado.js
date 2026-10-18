import {verImagen} from './visor-imagen.js?v=20261018-40';
import {pedir} from './local.js?v=20261018-40';
import {confirmar,pedirDatos} from './modal.js?v=20261018-40';
const api=(ruta,op={})=>pedir(ruta,{...op,base:'/api/operacion'});
const campos={asunto:'Asunto',destinatarios:'Para · correos separados por coma',saludo:'Saludo',introduccion:'Presentación',notas:'Notas y ubicación de la mercadería',despedida:'Despedida',firma:'Firma'};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export async function abrirCorreo(recepcion,{entregaId='',confirmarEnvio=false,alEnviar=null}={}){
 const ruta='/recepciones/'+encodeURIComponent(recepcion)+'/correo',query=entregaId?'?entregaId='+encodeURIComponent(entregaId):'';
 let v=await api(ruta+query),sucio=false,ocupado=false;
 if(!entregaId&&!confirmarEnvio&&v.entregaDisponible)return abrirCorreo(recepcion,{entregaId:v.entregaDisponible,alEnviar});
 const d=document.createElement('dialog');d.className='modal-operativa correo-dialogo';
 d.innerHTML=`<header class="acciones"><div><h2>Correo final · ${esc(recepcion)}</h2><p class="mini" data-conexion></p></div><button class="b-sec" data-cerrar>Cerrar</button></header>
 <details data-edicion><summary>Editar redacción y destinatarios</summary><form class="rejilla">${Object.entries(campos).map(([k,t])=>`<label class="campo"><span>${t}</span>${['asunto','destinatarios'].includes(k)?`<input data-campo="${k}">`:`<textarea rows="3" data-campo="${k}"></textarea>`}</label>`).join('')}</form></details>
 <div class="acciones"><button class="b-sec" data-actualizar>Actualizar datos</button><button class="b-sec" data-guardar>Guardar y actualizar vista</button><button class="b-sec" data-copiar>Copiar correo completo</button><button class="b-sec" data-datos>Copiar asunto y destinatarios</button><button class="b-sec" data-descargar>Descargar correo HTML</button><a class="b-sec" data-gmail target="_blank" rel="noopener">Abrir Gmail</a></div>
 <p class="mini">La copia incluye tablas y enlaces. En Gmail u Outlook pega el contenido y adjunta los documentos descargados debajo. Las imágenes y carpetas conservan sus permisos de Google. Copiar o abrir Gmail no confirma un envío.</p>
 <p data-estado role="status"></p><div data-sobre class="correo-sobre"></div><div class="correo-vista" data-vista></div>
 <details open><summary>Documentos finales para revisar y adjuntar</summary><div data-archivos></div></details>
 <details><summary>Vista previa de fotografías registradas</summary><div class="galeria-imagenes" data-fotos></div></details>
 <div class="acciones"><button class="b-sec" data-manual>Ya lo envié desde mi correo · registrar</button><button class="b-primario" data-enviar>${confirmarEnvio?'Usar este correo y continuar':'Revisar y enviar desde la aplicación'}</button></div>`;
 document.body.append(d);d.showModal();const $=s=>d.querySelector(s);
 function pintar(){
  for(const [k,t] of Object.entries(campos)){const input=$(`[data-campo="${k}"]`);input.value=v.campos[k]||'';input.disabled=v.soloLectura;input.setAttribute('aria-label',t);}
  $('[data-conexion]').textContent=`De: ${v.remitente} · ${v.conexionConfigurada?'Conexión guardada; se comprobará al enviar.':'Sin conexión Google guardada. Puedes copiar el correo y enviarlo manualmente.'}`;
  $('[data-sobre]').innerHTML='<p><b>Para:</b> '+esc(v.campos.destinatarios||'Sin destinatarios')+'</p><p><b>Asunto:</b> '+esc(v.asunto)+'</p>';
  const vista=new DOMParser().parseFromString(v.html,'text/html');vista.querySelectorAll('img[data-archivo]').forEach(img=>{img.src='/api/app/archivos/'+img.dataset.archivo+'?miniatura=1';img.onclick=()=>verImagen({url:'/api/app/archivos/'+img.dataset.archivo,nombre:img.alt});});$('[data-vista]').replaceChildren(...[...vista.body.children].map(e=>document.importNode(e,true)));$('[data-vista]').querySelectorAll('img[data-archivo]').forEach(img=>img.onclick=()=>verImagen({url:'/api/app/archivos/'+img.dataset.archivo,nombre:img.alt}));
  $('[data-gmail]').href='https://mail.google.com/mail/?view=cm&fs=1&to='+encodeURIComponent(v.campos.destinatarios)+'&su='+encodeURIComponent(v.asunto);
  $('[data-archivos]').innerHTML=v.archivos.length?v.archivos.map(a=>`<p><a class="b-sec" href="${esc(a.url)}" download>${esc(a.nombre)}</a></p>`).join(''):'<p>Genera el informe desde Informes → Descargar informe para revisar sus archivos. No se adjuntan archivos automáticamente al copiar el correo.</p>';
  $('[data-fotos]').innerHTML=v.fotos.map(f=>`<a href="${esc(f.url)}" target="_blank"><img src="${esc(f.url)}?miniatura=1" alt="${esc(f.nombre)}" loading="lazy"></a>`).join('');
  $('[data-fotos]').querySelectorAll('a').forEach((a,i)=>a.onclick=ev=>{ev.preventDefault();verImagen(v.fotos[i]);});
  $('[data-guardar]').hidden=v.soloLectura;$('[data-edicion]').open=!v.campos.destinatarios&&!v.soloLectura;
  $('[data-manual]').hidden=v.soloLectura||v.manual?.estado!=='PREPARADO';
  $('[data-enviar]').hidden=v.soloLectura||!confirmarEnvio&&!alEnviar&&!entregaId;
  if(!confirmarEnvio&&!entregaId&&!alEnviar){const a=document.createElement('p');a.className='mini';a.dataset.ayudaCierre='';d.querySelector('[data-ayuda-cierre]')?.remove();a.textContent='Para cerrar y enviar desde ITSANET, usa Finalizar en la recepción. Este borrador quedará disponible en la revisión final.';$('[data-enviar]').after(a);}
  sucio=false;
 }
 pintar();d.addEventListener('input',()=>{sucio=true;$('[data-estado]').textContent='Hay cambios sin guardar. Guarda para actualizar el correo completo.';});
 async function guardar(){if(!sucio)return;const valores=Object.fromEntries(Object.keys(campos).map(k=>[k,$(`[data-campo="${k}"]`).value]));v=await api(ruta,{metodo:'PUT',cuerpo:{version:v.version,campos:valores,entregaId}});pintar();$('[data-estado]').textContent='Borrador guardado; tablas actualizadas con los datos reales.';}
 async function prepararManual(){
  if(v.soloLectura)return;
  if(v.manual?.estado==='PREPARADO'&&v.manual.version===v.version)return;
  if(!await confirmar({titulo:'Preparar envío manual',texto:'Se detendrán los envíos automáticos pendientes de esta recepción para evitar duplicados. Copiar no envía el correo. Revisa los destinatarios y adjunta los documentos finales al enviarlo desde tu cuenta.',aceptar:'Preparar copia manual'}))throw new Error('Copia manual cancelada.');
  const r=await api(ruta+'/manual',{cuerpo:{entregaId,correoVersion:v.version,accion:'PREPARAR',confirmar:true}});v.manual=r.manual;$('[data-manual]').hidden=false;
 }
 async function ejecutar(fn){if(ocupado)return;ocupado=true;try{await fn();}catch(e){$('[data-estado]').textContent=e.message;}finally{ocupado=false;}}
 $('[data-actualizar]').onclick=()=>ejecutar(async()=>{if(sucio&&!await confirmar({titulo:'Actualizar datos',texto:'Se descartarán los cambios de redacción que aún no guardaste.',aceptar:'Actualizar'}))return;v=await api(ruta+query);pintar();$('[data-estado]').textContent='Vista actualizada con los datos y el estado actual de las fotografías.';});
 $('[data-guardar]').onclick=()=>ejecutar(guardar);
 $('[data-copiar]').onclick=()=>ejecutar(async()=>{await guardar();await prepararManual();let copiado=false;try{if(navigator.clipboard?.write&&globalThis.ClipboardItem){await navigator.clipboard.write([new ClipboardItem({'text/html':new Blob([v.html],{type:'text/html'}),'text/plain':new Blob([v.texto],{type:'text/plain'})})]);copiado=true;}}catch{/* HTTP de red local: usar selección compatible. */}if(!copiado){const copia=document.createElement('div');copia.style.cssText='position:fixed;left:-20000px;top:0;width:1100px';copia.innerHTML=v.html;d.append(copia);const seleccion=getSelection(),rango=document.createRange();rango.selectNodeContents(copia);seleccion.removeAllRanges();seleccion.addRange(rango);try{copiado=document.execCommand('copy');}catch{}if(copiado){seleccion.removeAllRanges();copia.remove();}else{copia.remove();rango.selectNodeContents($('[data-vista]'));seleccion.removeAllRanges();seleccion.addRange(rango);}}$('[data-estado]').textContent=copiado?'Correo copiado con sus tablas. Pégalo en tu correo y adjunta los documentos finales.':'Contenido seleccionado: pulsa Ctrl+C para copiarlo y pégalo en tu correo.';});
 $('[data-datos]').onclick=()=>ejecutar(async()=>{await guardar();const t=document.createElement('textarea');t.value='Para: '+v.campos.destinatarios+'\nAsunto: '+v.asunto;d.append(t);t.select();const ok=document.execCommand('copy');t.remove();$('[data-estado]').textContent=ok?'Asunto y destinatarios copiados.':'No se pudo copiar; selecciona los campos de la redacción.';});
 $('[data-manual]').onclick=()=>ejecutar(async()=>{await guardar();if(!await confirmar({titulo:'¿Ya enviaste este correo?',texto:'Confirma solo después de verificar el mensaje y sus documentos en Enviados de tu cuenta. Quedará registrado como declaración del supervisor; no como confirmación de Google.',aceptar:'Sí, ya envié el correo con los documentos'}))return;const r=await api(ruta+'/manual',{cuerpo:{entregaId,correoVersion:v.version,accion:'CONFIRMAR',confirmar:true}});v.manual=r.manual;$('[data-estado]').textContent=r.mensaje;$('[data-manual]').hidden=true;$('[data-enviar]').hidden=true;});
 $('[data-descargar]').onclick=()=>ejecutar(async()=>{await guardar();await prepararManual();const u=URL.createObjectURL(new Blob(['<!doctype html><meta charset="utf-8"><title>'+esc(v.asunto)+'</title>'+v.html],{type:'text/html;charset=utf-8'}));const a=document.createElement('a');a.href=u;a.download='Correo_'+recepcion.replace(/[^A-Za-z0-9_-]/g,'_')+'.html';a.click();setTimeout(()=>URL.revokeObjectURL(u),5000);});
 let resolver;const resultado=new Promise(r=>resolver=r);
 $('[data-enviar]').onclick=()=>ejecutar(async()=>{
  await guardar();
  if(confirmarEnvio){resolver({correoVersion:v.version,destinatarios:v.campos.destinatarios});d.close();return;}
  if(alEnviar){await alEnviar(v);return;}
  if(!v.campos.destinatarios.trim())throw new Error('Completa los destinatarios en Editar redacción y destinatarios.');
  const comprobacion=await pedir('/entregas/'+entregaId+'/solicitar');
  const datos=await pedirDatos({titulo:'Confirmar envío del correo revisado',texto:'Revisa Enviados para evitar duplicados. Se utilizarán los documentos archivados de esta entrega y el correo mostrado.',campos:[{clave:'motivo',etiqueta:'Motivo del envío / recuperación (10–300 caracteres)',obligatorio:true},{clave:'confirmarNoEnviado',etiqueta:'Revisé Enviados: este informe todavía no se envió',tipo:'interruptor',valor:false}],aceptar:'Confirmar envío'});
  if(!datos)return;await pedir('/entregas/'+entregaId+'/solicitar',{cuerpo:{...datos,destinatarios:v.campos.destinatarios,correoVersion:v.version,remitenteConfirmado:comprobacion.responsable.correo}});$('[data-estado]').textContent='Envío programado. Espera la confirmación de Google en Entregas.';$('[data-enviar]').disabled=true;
 });
 $('[data-cerrar]').onclick=async()=>{if(sucio&&!await confirmar({titulo:'¿Cerrar sin guardar?',texto:'Los cambios de redacción no guardados se perderán.',aceptar:'Cerrar sin guardar'}))return;d.close();};
 d.addEventListener('cancel',ev=>{if(sucio||ocupado){ev.preventDefault();if(!ocupado)$('[data-cerrar]').click();}});
 d.addEventListener('close',()=>{resolver(null);d.remove();},{once:true});
 return confirmarEnvio?resultado:d;
}
