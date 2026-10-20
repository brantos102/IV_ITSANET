import {pedir,modoLocal} from './local.js?v=20261019-56';
import {abrirEntregas} from './entregas-supervisor.js?v=20261019-56';
import {agregarAccionAviso} from './notificaciones.js?v=20261019-56';
let timer=null,cuenta='',ocupado=false,generacion=0;
export function iniciarAvisosEntregas({usuario,perfil,aviso}){
 const correo=String(perfil?.email||usuario?.email||'').toLowerCase();
 if(!modoLocal()||!usuario||!['SUPERVISOR','ADMIN'].includes(perfil?.rol)||!perfil?.permisos?.cerrarRecepciones){clearInterval(timer);timer=null;cuenta='';generacion++;return;}
 if(cuenta===correo&&timer)return;clearInterval(timer);cuenta=correo;const turno=++generacion;
 const leer=k=>{try{return sessionStorage.getItem(k);}catch{return null;}};
 const guardar=(k,v)=>{try{sessionStorage.setItem(k,v);}catch{}};
 async function revisar(){if(ocupado||document.hidden)return;ocupado=true;try{
   const filas=await pedir('/entregas');if(turno!==generacion)return;document.dispatchEvent(new CustomEvent('itsanet:entregas',{detail:filas}));const vistos=new Set();
   for(const e of filas){if((e.remitente?.toLowerCase()!==correo&&e.confirmarConCuenta!==correo)||vistos.has(e.recepcion))continue;vistos.add(e.recepcion);
    const clave='itsanet:entrega:'+correo+':'+e.id,previo=leer(clave);guardar(clave,e.estado);
    if(e.confirmacionDisponible&&leer(clave+':aviso')!==e.confirmacionDisponible){
     guardar(clave+':aviso',e.confirmacionDisponible);
     const n=aviso(`${e.recepcion}: tu conexión está verificada. Revisa los documentos finales y confirma el envío a ${e.destinatarios||'los destinatarios elegidos'}. Todavía no se envió correo.`,'info','Informe pendiente de tu confirmación');
     agregarAccionAviso(n,'Revisar y confirmar envío',()=>abrirEntregas(aviso,e.recepcion).catch(err=>aviso(err.message,'err')));
    }else if(e.estado==='ENTREGADA'&&e.destinatarios&&previo&&previo!=='ENTREGADA'){
     aviso(`${e.recepcion}: Google confirmó el envío de los documentos finales desde ${e.remitente} a ${e.destinatarios}.`,'ok','Correo enviado y confirmado');
    }
   }
  }catch{/* La pantalla de entregas conserva el detalle; el aviso no interrumpe el conteo. */}finally{ocupado=false;}}
 revisar();timer=setInterval(revisar,30000);window.addEventListener('pagehide',()=>clearInterval(timer),{once:true});
}
