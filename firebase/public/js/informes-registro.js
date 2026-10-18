import {pedir,nuevoIdentificador} from './local.js?v=20261018-48';
import {confirmar,elegir} from './modal.js?v=20261018-48';
const api=(ruta,opciones={})=>pedir(ruta,{...opciones,base:'/api/operacion'});
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const base=c=>'/recepciones/'+encodeURIComponent(c)+'/informes';
export const historialInformes=c=>api(base(c));
export async function iniciarInforme(c,tipo,formato=null){
 const historial=await historialInformes(c),ultimo=historial[0];
 if(ultimo){const fecha=new Date(ultimo.creadoEn).toLocaleString('es-EC',{timeZone:'America/Guayaquil'}),descarga=ultimo.descargas?.at(-1);
  const uso=(descarga?' Última descarga solicitada por '+esc(descarga.usuario)+' · '+esc(new Date(descarga.fecha).toLocaleString('es-EC',{timeZone:'America/Guayaquil'}))+'.':'')+(ultimo.confirmadoEn?' Entrega confirmada: '+esc(new Date(ultimo.confirmadoEn).toLocaleString('es-EC',{timeZone:'America/Guayaquil'}))+'.':'');
  if(ultimo.estado==='GENERADO'&&ultimo.formato===formato&&(tipo==='DESCARGA'||ultimo.tipo==='CORREO')){
   const tomar=await elegir({titulo:'Ya hay un informe preparado',texto:`R${String(ultimo.numero).padStart(4,'0')} · ${esc(ultimo.usuario)} · ${esc(fecha)}. Se comprobará que corresponde a los datos actuales.`,opciones:[{valor:'usar',titulo:'Usar este informe y continuar',detalle:'Conserva los archivos preparados; no crea otra versión.'},{valor:'nuevo',titulo:'Generar una versión nueva',detalle:'Para un cambio de datos o presentación que debas revisar.'}]});
   if(!tomar)return null;if(tomar==='usar')return api(base(c),{cuerpo:{clave:nuevoIdentificador(),tipo,formato,ultimoVisto:ultimo.id,reutilizarId:ultimo.id}});
  }else if(!await confirmar({titulo:'Ya existe un informe de esta recepción',texto:`R${String(ultimo.numero).padStart(4,'0')} · ${esc(ultimo.estado)} · ${esc(ultimo.usuario)} · ${esc(fecha)}.${uso} Crear otra generación conserva la anterior y deja una nueva secuencia para auditoría.`,aceptar:'Generar nueva versión'}))return null;
 }
 return api(base(c),{cuerpo:{clave:nuevoIdentificador(),tipo,formato,ultimoVisto:ultimo?.id||null}});
}
export async function archivarInforme(c,informe,libros){return api(base(c)+'/'+informe.id,{metodo:'PUT',cuerpo:{adjuntos:libros.map(l=>({nombre:l.nombre,base64:l.base64,origen:l.origen}))}});}
export async function descargarInforme(informe){
 for(const f of informe.archivos){const r=await fetch(f.url,{credentials:'same-origin'});if(!r.ok)throw Error('No se pudo descargar '+f.nombre);const url=URL.createObjectURL(await r.blob()),a=document.createElement('a');a.href=url;a.download=f.nombre;a.click();setTimeout(()=>URL.revokeObjectURL(url),30000);}
}
