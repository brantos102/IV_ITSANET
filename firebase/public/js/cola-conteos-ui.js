import {crearColaConteos} from './conteos-pendientes.js?v=20261111-76';
import {pedir} from './local.js?v=20261111-76';
import {comprimir} from './imagen.js?v=20261111-76';
import {confirmar,pedirDatos} from './modal.js?v=20261111-76';

const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function solicitud(ruta,opciones={}){
 const c=new AbortController(),t=setTimeout(()=>c.abort(),30000);
 try{return await pedir(ruta,{...opciones,signal:c.signal});}finally{clearTimeout(t);}
}
export function transporteConteos(actor){return async(j,{vigente,actualizar})=>{
 vigente();const yo=await solicitud('/yo',{base:'/api/auth'});
 if(String(yo?.uid)!==String(actor))throw Object.assign(new Error('Entra con la cuenta que capturó este pendiente. No se enviará con otro usuario.'),{codigo:'CUENTA_CAMBIADA'});
 let datos={...j.datosFotos};
 if(j.fotos.some(f=>!f.url)&&!Object.hasOwn(datos,'embarqueFoto')){
  const p=await solicitud('/recepciones/'+encodeURIComponent(j.recepcion)+'/fotos/embarques?'+new URLSearchParams({sku:j.cuerpo.sku,origen:datos.origen||''}),{base:'/api/operacion'});
  if(p.sugerido)datos.embarqueFoto=p.sugerido;
  else if(p.embarques.length)throw Object.assign(new Error('Selecciona el embarque de las fotos en Revisar pendientes. Se conservan el conteo y las imágenes.'),{codigo:'ELEGIR_EMBARQUE'});
  await actualizar({datosFotos:datos});
 }
 for(let i=0;i<j.fotos.length;i++){
  if(j.fotos[i].url)continue;vigente();const f=j.fotos[i],img=await comprimir(f.blob);
  vigente();const r=await solicitud('/recepciones/'+encodeURIComponent(j.recepcion)+'/archivos/foto',{
   cuerpo:{...datos,operadorOrigen:String(yo.id),nombre:f.nombre,tipo:img.tipo,base64:img.base64}});
  if(!r?.url)throw Object.assign(new Error('La foto no recibió un enlace confirmado. Se conserva su copia local.'),{codigo:'SIN_RESPUESTA_APP'});
  j.fotos[i]={...f,url:r.url};await actualizar({fotos:j.fotos});
 }
 const cuerpo={...j.cuerpo,fotos:[...new Set([...(j.cuerpo.fotos||[]),...j.fotos.map(f=>f.url)])]};
 await actualizar({cuerpo});vigente();
 const sufijo=j.tipo==='CERO'?'no-encontrado':j.tipo==='REPARTO'?'conteos-repartidos':'conteos';
 const r=await solicitud('/recepciones/'+encodeURIComponent(j.recepcion)+'/'+sufijo,{base:j.tipo==='REPARTO'?'/api/operacion':'/api/app',cuerpo});
 if(!r?.sku||!Number.isFinite(Number(r.contado)))throw Object.assign(new Error('No llegó la confirmación del conteo. Se comprobará el mismo identificador al reintentar.'),{codigo:'SIN_RESPUESTA_APP'});
 return r;
};}

function descargar(nombre,contenido,tipo='application/json'){
 const url=URL.createObjectURL(new Blob([contenido],{type:tipo})),a=document.createElement('a');a.href=url;a.download=nombre;a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);
}
const base64=blob=>new Promise((ok,no)=>{const r=new FileReader();r.onload=()=>ok(String(r.result).split(',')[1]);r.onerror=()=>no(new Error('No se pudo exportar una foto; el pendiente sigue guardado.'));r.readAsDataURL(blob);});

export function iniciarColaConteos({actor,recepcion,contenedor,alConfirmar=()=>{}}){
 const d=document.createElement('dialog');d.className='modal-operativa';let filas=[],dialogoOcupado=false;
 contenedor.hidden=false;contenedor.innerHTML='<strong>Respaldo de conteos en este dispositivo</strong><p data-resumen role="status">Revisando pendientes…</p><div class="acciones"><button class="b-sec" data-ver>Revisar pendientes</button><button class="b-sec" data-sync>Sincronizar ahora</button><button class="b-sec" data-exportar>Descargar respaldo</button><button class="b-sec" data-restaurar>Restaurar respaldo</button><input data-archivo type="file" accept="application/json,.json" hidden></div><p class="mini">Los indicadores muestran únicamente datos confirmados en el servidor. Los pendientes locales se conservan por cuenta hasta recibir confirmación. Mantén este navegador y sus datos.</p>';
 const cola=crearColaConteos({actor,transportar:transporteConteos(actor),alConfirmar,alCambiar:async lista=>{
  filas=lista;const pendientes=lista.filter(j=>j.estado!=='CONFIRMADO'),local=pendientes.filter(j=>j.recepcion===recepcion),revision=pendientes.filter(j=>j.estado==='REVISION');
  contenedor.querySelector('[data-resumen]').textContent=pendientes.length?`${local.length} pendientes de esta recepción · ${pendientes.length} de tu cuenta en este dispositivo · ${revision.length} requieren revisión. Sincronización automática al volver la conexión.`:'Sin conteos pendientes en este dispositivo para tu cuenta.';
  if(d.open&&!dialogoOcupado)pintar();
 }});
 async function pintar(){
  const pendientes=filas.filter(j=>j.estado!=='CONFIRMADO');
  d.innerHTML='<header class="acciones"><h2>Conteos pendientes del dispositivo</h2><button class="b-sec" data-cerrar>Cerrar</button></header><p>Se conservan usuario, recepción, cantidad, pallet, observación y fotos. Un rechazo del servidor requiere revisión; nunca se fuerza ni se descarta automáticamente.</p><div data-lista></div><p data-error role="status"></p>';
  d.querySelector('[data-cerrar]').onclick=()=>d.close();
  const lista=d.querySelector('[data-lista]');
  if(!pendientes.length)lista.textContent='No hay conteos pendientes para tu cuenta.';
  for(const j of pendientes){
   const a=document.createElement('article');a.style.cssText='border:1px solid var(--line);border-radius:10px;padding:12px;margin:12px 0;overflow-wrap:anywhere';
   a.innerHTML=`<b>${esc(j.recepcion)} · ${esc(j.cuerpo.sku)} · ${esc(j.cuerpo.cantidad)} unidades</b><p>${esc(j.cuerpo.pallet||'Cero confirmado')} · ${esc(j.cuerpo.origen||'Lista única')} · ${esc(j.fecha)} · ${j.fotos.length} foto(s)</p><p>${esc(j.cuerpo.observacion||'')}</p><p><b>${esc(j.estado)}</b> · ${esc(j.error?.mensaje||'Esperando confirmación del servidor')}</p><small>ID: ${esc(j.id)}</small>`;
   const b=document.createElement('button');b.className='b-sec';b.textContent=j.error?.codigo==='CONFIRMAR_SOBRANTE'?'Revisar sobrante':j.error?.codigo==='ELEGIR_EMBARQUE'?'Elegir destino de las fotos':'Revisar y reintentar';b.disabled=j.estado==='ENVIANDO';
   b.onclick=async()=>{if(dialogoOcupado)return;dialogoOcupado=true;b.disabled=true;
    try{
     if(j.estado!=='REVISION'){await cola.sincronizar(true);return;}
     let opciones={};
     if(j.error?.codigo==='CONFIRMAR_SOBRANTE'){
      if(!await confirmar({titulo:'Confirmar sobrante pendiente',texto:esc(j.error.mensaje)+'<p>Verifica que esta cantidad corresponde a otro conteo físico y no a las mismas unidades revisadas por otro operario.</p>',aceptar:'Confirmar sobrante'}))return;
      opciones.confirmarSobrante=true;
     }else if(j.error?.codigo==='ELEGIR_EMBARQUE'){
      const p=await solicitud('/recepciones/'+encodeURIComponent(j.recepcion)+'/fotos/embarques?'+new URLSearchParams({sku:j.cuerpo.sku,origen:j.datosFotos.origen||''}),{base:'/api/operacion'});
      const eleccion=await pedirDatos({titulo:'Embarque de las evidencias pendientes',campos:[{clave:'embarque',etiqueta:'Destino',tipo:'lista',valor:p.sugerido||'',opciones:[{valor:'',titulo:'Compartidas entre embarques'},...p.candidatos.map(v=>({valor:v,titulo:v}))]}],aceptar:'Guardar destino y reintentar'});
      if(!eleccion)return;opciones.embarqueFoto=eleccion.embarque;
     }else if(j.tipo==='REPARTO'){
      const p=await solicitud('/recepciones/'+encodeURIComponent(j.recepcion)+'/estado-sku/'+encodeURIComponent(j.cuerpo.sku));
      if(!await confirmar({titulo:'Revisar reparto pendiente',texto:esc(j.error.mensaje)+'<p>Total actual: '+esc(p.contado)+'. El reparto propuesto se conserva: '+esc(j.cuerpo.reparto.map(x=>x.origen+': '+x.cantidad).join(' · '))+'. Comprueba que sigue correspondiendo a estas unidades físicas.</p>',aceptar:'Revalidar este mismo reparto'}))return;
      opciones.repartoVigente=p.contado;
     }else if(!await confirmar({titulo:'Reintentar pendiente conservado',texto:esc(j.error?.mensaje||'El servidor volverá a validar este registro.'),aceptar:'Reintentar sin cambiar datos'}))return;
     await cola.reintentar(j.id,opciones);
    }catch(e){d.querySelector('[data-error]').textContent=e.message;}finally{dialogoOcupado=false;await cola.notificar();}
   };a.append(b);lista.append(a);
  }
 }
 contenedor.querySelector('[data-ver]').onclick=async()=>{await cola.notificar();await pintar();if(!d.isConnected)document.body.append(d);d.showModal();};
 contenedor.querySelector('[data-sync]').onclick=()=>cola.sincronizar(true).catch(e=>{contenedor.querySelector('[data-resumen]').textContent=e.message;});
 contenedor.querySelector('[data-exportar]').onclick=async()=>{
  try{
   const trabajos=[];for(const j of await cola.listar())if(j.estado!=='CONFIRMADO'){
    const fotos=[];for(const f of j.fotos)fotos.push({nombre:f.nombre,tipo:f.tipo,url:f.url,base64:await base64(f.blob)});
    trabajos.push({...j,dueno:null,hasta:0,fotos});
   }
   descargar('IV-ITSANET-pendientes-'+new Date().toISOString().slice(0,10)+'.json',JSON.stringify({formato:'IV-ITSANET-PENDIENTES-1',actor,trabajos}));
  }catch(e){contenedor.querySelector('[data-resumen]').textContent=e.message;}
 };
 contenedor.querySelector('[data-restaurar]').onclick=()=>contenedor.querySelector('[data-archivo]').click();
 contenedor.querySelector('[data-archivo]').onchange=async e=>{
  const archivo=e.target.files[0];e.target.value='';if(!archivo)return;
  try{
   const b=JSON.parse(await archivo.text());if(b.formato!=='IV-ITSANET-PENDIENTES-1'||b.actor!==actor||!Array.isArray(b.trabajos))throw new Error('El respaldo no corresponde a tu cuenta o su formato no es válido.');
   const trabajos=[];
   for(const j of b.trabajos){if(!Array.isArray(j.fotos))throw new Error('El respaldo no incluye la lista de fotos.');
    const fotos=[];for(const f of j.fotos){if(typeof f.base64!=='string')throw new Error('Una foto del respaldo no es válida.');const bin=atob(f.base64),bytes=Uint8Array.from(bin,c=>c.charCodeAt(0));fotos.push({...f,base64:undefined,blob:new Blob([bytes],{type:f.tipo||'image/jpeg'})});}
    trabajos.push({...j,fotos});
   }
   if(!await confirmar({titulo:'Restaurar pendientes de tu cuenta',texto:trabajos.length+' registros del respaldo. Se conservarán sus identificadores originales para evitar duplicados; el servidor volverá a validar cada movimiento.',aceptar:'Restaurar y sincronizar'}))return;
   const n=await cola.restaurar(trabajos);contenedor.querySelector('[data-resumen]').textContent=n+' pendientes restaurados. Los identificadores existentes se conservaron.';
   cola.sincronizar(true).catch(()=>{});
  }catch(err){contenedor.querySelector('[data-resumen]').textContent=err.message;}
 };
 d.addEventListener('cancel',e=>{if(dialogoOcupado)e.preventDefault();});
 cola.notificar();cola.iniciar();return cola;
}
