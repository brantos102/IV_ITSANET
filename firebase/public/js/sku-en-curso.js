import {pedir} from './local.js?v=20261023-68';
import {escucharCambiosRecepcion} from './cambios-recepcion.js?v=20261023-68';
/** Aviso con todo el equipo de este SKU; conserva conteos y borradores. */
export function coordinarSku({recepcion,obtenerSku,contando,contenedor}){
 const aviso=document.createElement('p');aviso.className='sku-coordinacion';aviso.setAttribute('role','alert');aviso.hidden=true;contenedor.prepend(aviso);
 const dispositivo=crypto.randomUUID?.()||'sku-'+Date.now()+'-'+Math.random().toString(36).slice(2),ruta='/recepciones/'+encodeURIComponent(recepcion)+'/sku-en-curso';
 let ocupado=false,ultimo='',momento=0,otros=[],equipo=[],operadorId=null,vivo=true;
 function pintar(){
  const sku=obtenerSku()||'';if(equipo.length)otros=equipo.filter(e=>e.sku===sku&&e.dispositivo!==dispositivo).map(e=>({...e,mismoUsuario:e.operadorId===operadorId}));
  aviso.hidden=!sku||!otros.length;
  aviso.textContent=otros.length?'Atención: '+otros.map(x=>x.nombre+(x.mismoUsuario?' en otro dispositivo':'')+' está '+(x.actividad==='CONTANDO'?'contando':'revisando')).join(' · ')+' este SKU. Coordinen las unidades y los pallets antes de registrar para evitar contar la misma mercadería dos veces.':'';
  aviso.classList.remove('sku-coordinacion-error');
 }
 async function comprobar(){
  if(!vivo||ocupado||document.hidden)return otros;const sku=obtenerSku()||'',actividad=contando()?'CONTANDO':'REVISANDO';ocupado=true;
  try{const r=await pedir(ruta,{base:'/api/operacion',metodo:'PUT',cuerpo:{dispositivo,sku,actividad}});if(sku!==(obtenerSku()||''))return [];ultimo=sku+'|'+actividad;momento=Date.now();otros=r.otros;operadorId=r.operadorId;pintar();return otros;
  }catch(e){if(sku){aviso.hidden=false;aviso.classList.add('sku-coordinacion-error');aviso.textContent='No se pudo consultar quién valida este SKU. Coordina con el equipo antes de registrar. '+e.message;}return [];}finally{ocupado=false;}
 }
 const parar=escucharCambiosRecepcion(recepcion,e=>{if(!e.secciones.includes('presencia')||!Array.isArray(e.equipoSku))return;equipo=e.equipoSku;otros=[];pintar();});
 const timer=setInterval(()=>{const clave=(obtenerSku()||'')+'|'+(contando()?'CONTANDO':'REVISANDO');if(clave!==ultimo){otros=[];pintar();comprobar();}else if(Date.now()-momento>15000)comprobar();},500);
 const liberar=()=>{if(!vivo)return;vivo=false;clearInterval(timer);parar();fetch('/api/operacion'+ruta,{method:'PUT',credentials:'same-origin',keepalive:true,headers:{'Content-Type':'application/json'},body:JSON.stringify({dispositivo,sku:'',actividad:'REVISANDO'})}).catch(()=>{});};
 window.addEventListener('pagehide',e=>{if(e.persisted){fetch('/api/operacion'+ruta,{method:'PUT',credentials:'same-origin',keepalive:true,headers:{'Content-Type':'application/json'},body:JSON.stringify({dispositivo,sku:'',actividad:'REVISANDO'})}).catch(()=>{});}else liberar();});
 window.addEventListener('pageshow',e=>{if(e.persisted){momento=0;comprobar();}});comprobar();return {comprobar,parar:liberar};
}
