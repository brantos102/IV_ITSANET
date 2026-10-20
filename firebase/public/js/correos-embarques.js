import {pedir} from './local.js?v=20261020-60';
import {elegir,pedirDatos} from './modal.js?v=20261020-60';
import {declararEnviadoManual} from './gestion-entregas.js?v=20261020-60';
import {prepararDocumentosPorEmbarque} from './informes-registro.js?v=20261020-60';
const api=(ruta,op={})=>pedir(ruta,{...op,base:'/api/operacion'});
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export async function revisarPlanCorreos(codigo){
 const ruta='/recepciones/'+encodeURIComponent(codigo)+'/correos-embarques';let p=await api(ruta),ocupado=false;
 let c={modo:p.modo,asignaciones:{...p.asignaciones},embarquesPorLinea:{...p.embarquesPorLinea},repartos:Object.fromEntries(p.repartos.map(s=>[s.id,s.propuesta]))};
 if(p.embarques.length&&c.modo==='PACKING_LIST'&&!p.consolidadoConfirmado){c.modo='EMBARQUE';p=await api(ruta+'/vista',{cuerpo:c});c.repartos=Object.fromEntries(p.repartos.map(s=>[s.id,s.propuesta]));}
 const d=document.createElement('dialog');d.className='modal-operativa';let resolver;const resultado=new Promise(r=>resolver=r);
 function capturar(){
  d.querySelectorAll('[data-linea]').forEach(e=>c.embarquesPorLinea[e.dataset.linea]=e.value.trim());
  d.querySelectorAll('[data-extra]').forEach(e=>c.asignaciones[e.dataset.extra]=e.value);
  for(const s of p.repartos){c.repartos[s.id]??=structuredClone(s.propuesta);for(const g of s.grupos){const x=c.repartos[s.id][g.id];for(const e of d.querySelectorAll('[data-r="'+s.id+'"][data-g="'+g.id+'"]')){if(e.dataset.k==='cantidad')x.cantidad=Number(e.value);else if(['observacion','pallets'].includes(e.dataset.k))x[e.dataset.k]=e.value;else x[e.dataset.k][e.dataset.tipo]=Number(e.value);}}}
 }
 function pintar(){
  const porEmbarque=c.modo==='EMBARQUE';
  d.innerHTML=`<h2>Organizar correos de la recepción</h2><p>Un packing list es un archivo y puede contener varios embarques. Elige cómo desea el supervisor separar los correos. Se conserva el cierre completo de la recepción.</p><label class="campo"><span>Preparar y revisar</span><select data-modo><option value="PACKING_LIST">Un correo por cada packing list</option><option value="EMBARQUE">Un correo por cada embarque</option><option value="RECEPCION">Un correo consolidado de toda la recepción</option></select></label><p>${p.grupos.length} correos propuestos: ${p.grupos.map(g=>esc(g.nombre)).join(' · ')||'asigna primero los embarques'}</p><form>
   ${porEmbarque&&p.filasSinEmbarque.length?`<details open><summary>Filas sin embarque en el archivo · ${p.filasSinEmbarque.length}</summary><p>Indica el embarque de estas filas. La asignación se usa en esta revisión y conserva el packing list original.</p>${[...new Set(p.filasSinEmbarque.map(l=>l.origen))].map(o=>`<label class="campo"><span>Aplicar un embarque a las filas sin dato de ${esc(o)}</span><input data-todas="${esc(o)}" placeholder="Escribe el código y sal del campo"></label>`).join('')}${p.filasSinEmbarque.map(l=>`<label class="campo"><span>${esc(l.origen)} · fila ${l.linea} · ${esc(l.sku)}</span><input data-linea="${esc(l.id)}" value="${esc(c.embarquesPorLinea[l.id]||'')}" maxlength="80" required></label>`).join('')}<button type="button" class="b-sec" data-preview>Revisar embarques asignados</button></details>`:''}
   ${p.adicionales.length?'<h3>Productos adicionales</h3>':''}${p.adicionales.map(s=>`<label class="campo"><span>${esc(s.sku)} · ${esc(s.descripcion)}</span><select data-extra="${esc(s.sku)}" required><option value="">Selecciona su grupo</option>${p.grupos.map(g=>`<option value="${esc(g.id)}" ${c.asignaciones[s.sku]===g.id?'selected':''}>${esc(g.nombre)}</option>`).join('')}</select></label>`).join('')}
   ${porEmbarque&&p.repartos.length?`<h3>Revisa la distribución de SKU compartidos</h3><p>Son propuestas para el informe. Ajusta la cantidad, incidencias, pallets y observación de cada embarque. Las sumas deben conservar exactamente lo contado y su calidad; la bitácora permanece intacta.</p>${p.repartos.map(s=>`<details open><summary>${esc(s.origen)} · ${esc(s.sku)} · ${s.cantidad} unidades contadas</summary>${s.grupos.map(g=>{const x=c.repartos[s.id]?.[g.id]||s.propuesta[g.id],attrs=`data-r="${s.id}" data-g="${g.id}"`;return `<fieldset><legend>${esc(g.nombre)}</legend><label class="campo"><span>Cantidad física</span><input type="number" min="0" step="any" ${attrs} data-k="cantidad" value="${x.cantidad}" required></label>${s.incidencias.map(i=>`<div class="rejilla">${[['incidencias','Unidades con '+i.nombre],['pnc','De ellas PNC']].map(([k,t])=>`<label class="campo"><span>${esc(t)}</span><input type="number" min="0" step="any" ${attrs} data-k="${k}" data-tipo="${esc(i.tipo)}" value="${x[k][i.tipo]||0}" required></label>`).join('')}</div>`).join('')}<label class="campo"><span>Pallets de estas unidades</span><input ${attrs} data-k="pallets" value="${esc(x.pallets)}" maxlength="300"></label><label class="campo"><span>Observación de este embarque</span><input ${attrs} data-k="observacion" value="${esc(x.observacion)}" maxlength="300"></label></fieldset>`;}).join('')}</details>`).join('')}<label class="campo"><span><input type="checkbox" data-confirmar> Revisé y confirmo el reparto por embarque y las unidades PNC.</span></label>`:''}
   ${c.modo==='RECEPCION'||c.modo==='PACKING_LIST'&&p.embarques.length>1?'<label class="campo"><span><input type="checkbox" data-consolidado required> Confirmo el correo consolidado con todos los embarques y documentos indicados.</span></label>':''}<p data-error role="alert"></p><div class="acciones"><button type="button" class="b-sec" data-cancelar>Volver a la recepción</button><button type="submit" class="b-primario">Confirmar agrupación y continuar</button></div></form>`;
  d.querySelector('[data-modo]').value=c.modo;
  d.querySelector('[data-modo]').onchange=async ev=>{if(ev.target.value===c.modo)return;capturar();c.modo=ev.target.value;c.repartos={};await previa();};
  d.querySelectorAll('[data-todas]').forEach(e=>e.onchange=()=>{for(const l of p.filasSinEmbarque.filter(l=>l.origen===e.dataset.todas)){c.embarquesPorLinea[l.id]=e.value.trim();d.querySelector('[data-linea="'+CSS.escape(l.id)+'"]').value=e.value.trim();}});
  d.querySelector('[data-preview]')?.addEventListener('click',async()=>{capturar();await previa();});
  d.querySelector('[data-cancelar]').onclick=()=>{if(!ocupado)d.close();};
  d.querySelector('form').onsubmit=async ev=>{ev.preventDefault();if(ocupado)return;ocupado=true;capturar();try{
   const nuevo=await api(ruta,{metodo:'PUT',cuerpo:{...c,version:p.version,repartoConfirmado:!!d.querySelector('[data-confirmar]')?.checked,confirmarConsolidado:!!d.querySelector('[data-consolidado]')?.checked}});resolver(nuevo);d.close();
  }catch(e){d.querySelector('[data-error]').textContent=e.message;}finally{ocupado=false;}};
 }
 async function previa(){if(ocupado)return;ocupado=true;try{p=await api(ruta+'/vista',{cuerpo:c});c.repartos=Object.fromEntries(p.repartos.map(s=>[s.id,s.propuesta]));pintar();}catch(e){d.querySelector('[data-error]').textContent=e.message;}finally{ocupado=false;}}
 pintar();document.body.append(d);d.showModal();d.oncancel=ev=>{if(ocupado)ev.preventDefault();};d.onclose=()=>{resolver(null);d.remove();};return resultado;
}

export async function abrirCorreosEmbarque(recepcion,v,{entregaId,confirmarEnvio,modoEntrega,alEnviar,abrirCorreo,actual=false}){
 const unidad=v.modoAgrupacion==='RECEPCION'?'recepción':v.modoAgrupacion==='EMBARQUE'?'embarque':'packing list';
 const nombre=id=>v.grupos?.find(g=>g.id===id)?.nombre||id;
 const confirmados=new Set(v.correos.filter(c=>['ENTREGADA','MANUAL_DECLARADO'].includes(c.estado)).map(c=>c.origen));
 if(confirmarEnvio){
  const modo=await elegir({titulo:'Revisar los correos separados',texto:`${v.origenes.length} correos (${v.modoAgrupacion==='EMBARQUE'?'por embarque':'por packing list'}). Revisa cada correo; no se envía nada hasta la confirmación final. Los correos ya confirmados se conservan.`,opciones:[
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
    ...v.origenes.map((o,i)=>({clave:'embarque'+i,etiqueta:'Revisé Enviados: '+nombre(o),tipo:'interruptor',valor:false}))],aceptar:'Confirmar todos los envíos manuales'});
   if(!datos)return null;
   if(datos.motivoManual.length<10||v.origenes.some((_,i)=>datos['embarque'+i]!==true))throw new Error('Indica el motivo y confirma el envío de cada embarque.');
   declaracion={motivoManual:datos.motivoManual,confirmarEnviadoManual:true};
  }
  return {correos,correoVersion:v.version,destinatarios:[...new Set(correos.flatMap(c=>(c.destinatarios||v.correos.find(x=>x.origen===c.origen)?.destinatarios||'').split(',')).filter(Boolean))].join(','),modoEntrega:modo,...declaracion};
 }
 const d=document.createElement('dialog');d.className='modal-operativa';
 d.innerHTML=`<header class="acciones"><h2>Correos por ${unidad} · ${esc(recepcion)}</h2><button class="b-sec" data-cerrar>Cerrar</button></header><p>Cada ${unidad} tiene su propio correo, destinatarios, novedades y documentos. Abre cada uno para editar, copiar o descargar.</p>${actual&&v.estadoRecepcion==='CERRADA'?'<p class="guia-modal">Nueva revisión de una recepción cerrada. Se conservan el cierre, los conteos y el correo original. Los siguientes correos son borradores; no se programan envíos.</p>':''}${!entregaId?'<div class="acciones"><button class="b-sec" data-agrupacion>Elegir: por packing list o por embarque</button><button class="b-primario" data-documentos>Preparar documentos de esta revisión</button>'+(v.entregaHistoricaDisponible?'<button class="b-sec" data-historico>Ver el correo original archivado</button>':'')+'</div><p class="mini">Prepara los documentos para que cada borrador muestre su Excel correspondiente. Puedes repetir la consulta: los archivos vigentes se reutilizan.</p>':''}<div data-lista></div><p data-estado role="status"></p><div class="acciones">${entregaId&&!v.soloLectura?'<button class="b-sec" data-manual>Registrar todos los correos enviados manualmente</button><button class="b-primario" data-enviar>Revisar y enviar embarques pendientes</button>':''}</div>`;
 const lista=d.querySelector('[data-lista]');
 for(const origen of v.origenes){const c=v.correos.find(c=>c.origen===origen),fila=document.createElement('section');fila.className='guia-modal';fila.innerHTML=`<h3>${esc(nombre(origen))}</h3><p>${esc(c?.estado||'BORRADOR')} · ${esc(c?.destinatarios||'Destinatarios por revisar')}</p>`;const b=document.createElement('button');b.className='b-sec';b.textContent=confirmados.has(origen)?'Ver correo confirmado':'Revisar correo y su documento';b.onclick=async()=>{b.disabled=true;try{await abrirCorreo(recepcion,{entregaId,origen,actual});}catch(e){d.querySelector('[data-estado]').textContent=e.message;}finally{b.disabled=false;}};fila.append(b);lista.append(fila);}
 document.body.append(d);d.showModal();d.querySelector('[data-cerrar]').onclick=()=>d.close();d.onclose=()=>d.remove();let ocupado=false;
 async function ejecutar(fn){if(ocupado)return;ocupado=true;try{await fn();}catch(e){d.querySelector('[data-estado]').textContent=e.message;}finally{ocupado=false;}}
 d.querySelector('[data-agrupacion]')?.addEventListener('click',()=>ejecutar(async()=>{if(await revisarPlanCorreos(recepcion)){d.close();await abrirCorreo(recepcion,{actual:true});}}));
 d.querySelector('[data-documentos]')?.addEventListener('click',()=>ejecutar(async()=>{const f=await prepararDocumentosPorEmbarque(recepcion);if(!f)return;d.close();const nuevo=await abrirCorreo(recepcion,{actual:true});nuevo?.querySelector('[data-estado]')?.append(document.createTextNode(f.archivos.length+' documentos preparados. Abre cada packing list para revisar su correo y descargar su archivo.'));}));
 d.querySelector('[data-historico]')?.addEventListener('click',()=>ejecutar(()=>abrirCorreo(recepcion,{entregaId:v.entregaHistoricaDisponible})));
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
