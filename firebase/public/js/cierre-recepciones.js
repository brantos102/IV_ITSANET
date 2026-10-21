import {pedir} from './local.js?v=20261021-61';
import {pedirDatos} from './modal.js?v=20261021-61';
export async function cerrarDesdeRecepciones(codigo){
 const ruta='/recepciones/'+encodeURIComponent(codigo)+'/cierre-externo',p=await pedir(ruta,{base:'/api/operacion'});
 if(p.estado==='CERRADA')throw Error('Esta recepción ya está cerrada. Actualiza el listado.');
 if(p.sinVerificar)throw Error('Quedan '+p.sinVerificar+' referencias sin validar. Completa la validación antes de cerrar.');
 const datos=await pedirDatos({titulo:'Cerrar recepción · '+codigo,texto:'Úsalo si los correos y archivos ya fueron enviados fuera de ITSANET. Comprueba cada embarque en Enviados. Esta acción registra el cierre y detiene entregas automáticas aún pendientes; no manda otro correo.',campos:[
 ...p.grupos.flatMap((g,i)=>[{clave:'correo'+i,etiqueta:'Correo enviado · '+g.nombre,tipo:'interruptor',valor:false},{clave:'validacion'+i,etiqueta:'Incluí recepción y validación · '+g.nombre,tipo:'interruptor',valor:false}]),
 {clave:'motivo',etiqueta:'Cómo y cuándo se enviaron (10–300 caracteres)',obligatorio:true}],aceptar:'Confirmar envío externo y cerrar'});
 if(!datos)return false;
 const confirmaciones=Object.fromEntries(p.grupos.map((g,i)=>[g.id,{correo:datos['correo'+i],validacion:datos['validacion'+i]}]));
 return pedir(ruta,{base:'/api/operacion',cuerpo:{version:p.version,confirmaciones,motivo:datos.motivo}});
}
