import {pedir} from './local.js?v=20261022-64';
/** Aviso de coordinación: se renueva, caduca y libera sin afectar el libro mayor. */
export function coordinarSku({recepcion,obtenerSku,contando,contenedor}){
 const aviso=document.createElement('p');aviso.className='sku-coordinacion';aviso.setAttribute('role','alert');aviso.hidden=true;contenedor.prepend(aviso);
 const dispositivo=crypto.randomUUID?.()||'sku-'+Date.now()+'-'+Math.random().toString(36).slice(2),ruta='/recepciones/'+encodeURIComponent(recepcion)+'/sku-en-curso';
 let ocupado=false,ultimo='',momento=0,otros=[];
 async function comprobar(){
  if(ocupado||document.hidden)return otros;const sku=obtenerSku()||'',actividad=contando()?'CONTANDO':'REVISANDO';ocupado=true;
  try{const r=await pedir(ruta,{base:'/api/operacion',metodo:'PUT',cuerpo:{dispositivo,sku,actividad}});if(sku!==(obtenerSku()||''))return [];ultimo=sku+'|'+actividad;momento=Date.now();otros=r.otros;
   aviso.hidden=!otros.length;aviso.textContent=otros.length?'Atención: '+otros.map(x=>x.nombre+(x.mismoUsuario?' en otro dispositivo':'')+' está '+(x.actividad==='CONTANDO'?'contando':'revisando')).join(' · ')+' este SKU. Coordinen las unidades y los pallets antes de registrar para evitar contar la misma mercadería dos veces.':'';
   aviso.classList.remove('sku-coordinacion-error');return otros;
  }catch(e){if(sku){aviso.hidden=false;aviso.classList.add('sku-coordinacion-error');aviso.textContent='No se pudo consultar quién valida este SKU. Coordina con el equipo antes de registrar. '+e.message;}return [];}finally{ocupado=false;}
 }
 const timer=setInterval(()=>{const clave=(obtenerSku()||'')+'|'+(contando()?'CONTANDO':'REVISANDO');if(clave!==ultimo||Date.now()-momento>15000)comprobar();},1000);
 const liberar=()=>{clearInterval(timer);fetch('/api/operacion'+ruta,{method:'PUT',credentials:'same-origin',keepalive:true,headers:{'Content-Type':'application/json'},body:JSON.stringify({dispositivo,sku:'',actividad:'REVISANDO'})}).catch(()=>{});};
 window.addEventListener('pagehide',liberar,{once:true});comprobar();return {comprobar};
}
