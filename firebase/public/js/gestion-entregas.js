import {pedir} from './local.js?v=20261019-56';
import {pedirDatos} from './modal.js?v=20261019-56';
export async function declararEnviadoManual(e){
 const v=await pedir('/recepciones/'+encodeURIComponent(e.recepcion)+'/correo?entregaId='+encodeURIComponent(e.id),{base:'/api/operacion'});
 const pendientes=(e.correos||[]).filter(c=>c.estado!=='ENTREGADA');
 const revisados=await Promise.all(pendientes.map(c=>pedir('/recepciones/'+encodeURIComponent(e.recepcion)+'/correo?entregaId='+encodeURIComponent(e.id)+'&origen='+encodeURIComponent(c.origen),{base:'/api/operacion'})));
 const datos=await pedirDatos({titulo:'Registrar correo ya enviado · '+e.recepcion,
  texto:'Verifica en Enviados el destinatario y los documentos de esta entrega. Se detendrán los envíos automáticos pendientes. Se conserva la auditoría y no se registra como confirmación de Google.',
  campos:[{clave:'motivo',etiqueta:'Cómo y cuándo se envió (10–300 caracteres)',obligatorio:true},
    {clave:'confirmarEnviado',etiqueta:'Revisé Enviados y los documentos finales ya se enviaron',tipo:'interruptor',valor:false},
    ...pendientes.map((c,i)=>({clave:'embarque'+i,etiqueta:'Enviado: '+(c.nombre||c.origen)+' → '+revisados[i].campos.destinatarios,tipo:'interruptor',valor:false}))],aceptar:'Registrar envío manual y resolver pendiente'});
 if(!datos)return null;
 return pedir('/entregas/'+e.id+'/manual-confirmado',{cuerpo:{...datos,versionGestion:e.versionGestion,correoVersion:v.version,
  correos:pendientes.map((c,i)=>({origen:c.origen,correoVersion:revisados[i].version,confirmarEnviado:datos['embarque'+i]===true}))}});
}
export async function cambiarArchivoHistorial(e){
 const datos=await pedirDatos({titulo:e.archivado?'Restaurar en el historial':'Retirar del historial visible',
  texto:'Se conservan la recepción, los documentos y el registro de quién realizó esta acción. Puedes consultar y restaurar los registros archivados.',
  campos:[{clave:'motivo',etiqueta:'Motivo (10–300 caracteres)',obligatorio:true}],aceptar:e.archivado?'Restaurar registro':'Retirar del historial'});
 if(!datos)return null;
 return pedir('/entregas/'+e.id+'/historial',{cuerpo:{...datos,versionGestion:e.versionGestion,archivar:!e.archivado}});
}
