import {pedir} from './local.js?v=20261019-52';
import {elegir,pedirDatos} from './modal.js?v=20261019-52';
import {declararEnviadoManual} from './gestion-entregas.js?v=20261019-52';
const api=(ruta,op={})=>pedir(ruta,{...op,base:'/api/operacion'});
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export async function revisarPlanCorreos(codigo){
 const ruta='/recepciones/'+encodeURIComponent(codigo)+'/correos-embarques',p=await api(ruta);
 if(p.origenes.length<2)return true;
 const d=document.createElement('dialog');d.className='modal-operativa';
 d.innerHTML=`<h2>Finalizar recepción · correos por embarque</h2><p>Esta recepción contiene <b>${p.origenes.length} packing lists</b>. Se cerrará completa y se preparará <b>un correo independiente por cada embarque</b>. Revisarás destinatarios, novedades, fotos y un documento de cada uno antes de confirmar.</p><ol>${p.origenes.map(o=>`<li>${esc(o)}</li>`).join('')}</ol>${p.adicionales.length?'<h3>¿A qué embarque pertenece cada adicional?</h3><p>El adicional aparecerá únicamente en el correo del embarque elegido.</p>':''}<form>${p.adicionales.map((s,i)=>`<label class="campo"><span>${esc(s.sku)} · ${esc(s.descripcion)}</span><select data-sku="${i}" required><option value="">Selecciona su embarque</option>${p.origenes.map(o=>`<option value="${esc(o)}" ${p.asignaciones[s.sku]===o?'selected':''}>${esc(o)}</option>`).join('')}</select></label>`).join('')}<p data-error role="alert"></p><div class="acciones"><button type="button" class="b-sec" data-cancelar>Volver a la recepción</button><button type="submit" class="b-primario">Continuar y revisar los correos</button></div></form>`;
 document.body.append(d);d.showModal();let resolver,ocupado=false;const resultado=new Promise(r=>resolver=r);
 d.querySelector('[data-cancelar]').onclick=()=>{if(!ocupado)d.close();};
 d.querySelector('form').onsubmit=async ev=>{ev.preventDefault();if(ocupado)return;ocupado=true;const b=d.querySelector('[type=submit]');b.disabled=true;try{
  const asignaciones=Object.fromEntries(p.adicionales.map((s,i)=>[s.sku,d.querySelector(`[data-sku="${i}"]`).value]));
  if(p.adicionales.length)await api(ruta,{metodo:'PUT',cuerpo:{version:p.version,asignaciones}});
  resolver(true);d.close();
 }catch(e){d.querySelector('[data-error]').textContent=e.message;}finally{ocupado=false;b.disabled=false;}};
 d.oncancel=ev=>{if(ocupado)ev.preventDefault();};d.onclose=()=>{resolver(false);d.remove();};return resultado;
}

export async function abrirCorreosEmbarque(recepcion,v,{entregaId,confirmarEnvio,modoEntrega,alEnviar,abrirCorreo}){
 const confirmados=new Set(v.correos.filter(c=>['ENTREGADA','MANUAL_DECLARADO'].includes(c.estado)).map(c=>c.origen));
 if(confirmarEnvio){
  const modo=await elegir({titulo:'Un correo por cada packing list',texto:`${v.origenes.length} embarques. Revisa cada correo; no se envía nada hasta la confirmación final. Los correos ya confirmados se conservan.`,opciones:[
   ...(modoEntrega==='AUTOMATICO'?[{valor:'AUTOMATICO',titulo:'Enviar los correos desde ITSANET',detalle:'Cada embarque conserva sus destinatarios y su estado de confirmación.'}]:[]),
   {valor:'MANUAL',titulo:'Preparar los correos para envío manual',detalle:'Copiar o descargar cada correo y adjuntar su documento; registrar el envío después.'},
   ...(!entregaId?[{valor:'MANUAL_ENVIADO',titulo:'Todos estos correos ya se enviaron manualmente',detalle:'Requiere revisar Enviados y declarar el envío de cada embarque.'}]:[])]});
  if(!modo)return null;
  const correos=[];
  for(const origen of v.origenes){
   if(confirmados.has(origen)){correos.push({origen,confirmado:true});continue;}
   const c=await abrirCorreo(recepcion,{entregaId,origen,confirmarEnvio:true,revisionEmbarque:true,modoEntrega:modo});
   if(!c)return null;correos.push(c);
  }
  let declaracion={};
  if(modo==='MANUAL_ENVIADO'){
   const datos=await pedirDatos({titulo:'Declarar correos ya enviados',texto:'Confirma únicamente después de verificar cada embarque en Enviados, con su destinatario y documento.',campos:[
    {clave:'motivoManual',etiqueta:'Cómo y cuándo se enviaron (10–300 caracteres)',obligatorio:true},
    ...v.origenes.map((o,i)=>({clave:'embarque'+i,etiqueta:'Revisé Enviados: '+o,tipo:'interruptor',valor:false}))],aceptar:'Confirmar todos los envíos manuales'});
   if(!datos)return null;
   if(datos.motivoManual.length<10||v.origenes.some((_,i)=>datos['embarque'+i]!==true))throw new Error('Indica el motivo y confirma el envío de cada embarque.');
   declaracion={motivoManual:datos.motivoManual,confirmarEnviadoManual:true};
  }
  return {correos,correoVersion:v.version,destinatarios:[...new Set(correos.flatMap(c=>(c.destinatarios||v.correos.find(x=>x.origen===c.origen)?.destinatarios||'').split(',')).filter(Boolean))].join(','),modoEntrega:modo,...declaracion};
 }
 const d=document.createElement('dialog');d.className='modal-operativa';
 d.innerHTML=`<header class="acciones"><h2>Correos por embarque · ${esc(recepcion)}</h2><button class="b-sec" data-cerrar>Cerrar</button></header><p>Cada packing list tiene su propio correo, destinatarios, novedades y documento. Abre cada uno para editar, copiar o descargar.</p><div data-lista></div><p data-estado role="status"></p><div class="acciones">${entregaId&&!v.soloLectura?'<button class="b-sec" data-manual>Registrar todos los correos enviados manualmente</button><button class="b-primario" data-enviar>Revisar y enviar embarques pendientes</button>':''}</div>`;
 const lista=d.querySelector('[data-lista]');
 for(const origen of v.origenes){const c=v.correos.find(c=>c.origen===origen),fila=document.createElement('section');fila.className='guia-modal';fila.innerHTML=`<h3>${esc(origen)}</h3><p>${esc(c?.estado||'BORRADOR')} · ${esc(c?.destinatarios||'Destinatarios por revisar')}</p>`;const b=document.createElement('button');b.className='b-sec';b.textContent=confirmados.has(origen)?'Ver correo confirmado':'Revisar correo y su documento';b.onclick=async()=>{b.disabled=true;try{await abrirCorreo(recepcion,{entregaId,origen});}catch(e){d.querySelector('[data-estado]').textContent=e.message;}finally{b.disabled=false;}};fila.append(b);lista.append(fila);}
 document.body.append(d);d.showModal();d.querySelector('[data-cerrar]').onclick=()=>d.close();d.onclose=()=>d.remove();let ocupado=false;
 async function ejecutar(fn){if(ocupado)return;ocupado=true;try{await fn();}catch(e){d.querySelector('[data-estado]').textContent=e.message;}finally{ocupado=false;}}
 d.querySelector('[data-manual]')?.addEventListener('click',()=>ejecutar(async()=>{const es=await pedir('/recepciones/'+encodeURIComponent(recepcion)+'/entregas'),e=es.find(e=>e.id===entregaId);if(e&&await declararEnviadoManual(e)){d.close();await abrirCorreo(recepcion,{entregaId});}}));
 d.querySelector('[data-enviar]')?.addEventListener('click',()=>ejecutar(async()=>{
  const comprobacion=await pedir('/entregas/'+entregaId+'/solicitar');
  const actual=await api('/recepciones/'+encodeURIComponent(recepcion)+'/correo?entregaId='+encodeURIComponent(entregaId));
  const revisado=await abrirCorreosEmbarque(recepcion,actual,{entregaId,confirmarEnvio:true,modoEntrega:'AUTOMATICO',abrirCorreo});if(!revisado)return;
  if(revisado.modoEntrega!=='AUTOMATICO')throw new Error('Abre cada correo para preparar su copia manual; registra los envíos cuando estén realizados.');
  const datos=await pedirDatos({titulo:'Confirmar envío de embarques pendientes',texto:'Los embarques ya confirmados se omiten. Revisa Enviados antes de recuperar un correo pendiente.',campos:[{clave:'motivo',etiqueta:'Motivo (10–300 caracteres)',obligatorio:true},{clave:'confirmarNoEnviado',etiqueta:'Revisé Enviados: los embarques pendientes aún no se enviaron',tipo:'interruptor',valor:false}],aceptar:'Programar correos pendientes'});
  if(!datos)return;await pedir('/entregas/'+entregaId+'/solicitar',{cuerpo:{...datos,...revisado,remitenteConfirmado:comprobacion.responsable.correo}});d.querySelector('[data-estado]').textContent='Correos pendientes programados. Consulta las confirmaciones en Entregas.';d.querySelector('[data-enviar]').disabled=true;
 }));return d;
}
