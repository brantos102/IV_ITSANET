import {pedir,nuevoIdentificador} from './local.js?v=20261017-39';
import {confirmar} from './modal.js?v=20261017-39';
const api=(ruta,opciones={})=>pedir(ruta,{...opciones,base:'/api/operacion'});
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const base=c=>'/recepciones/'+encodeURIComponent(c)+'/informes';
export const historialInformes=c=>api(base(c));
export async function iniciarInforme(c,tipo,formato=null){
 const historial=await historialInformes(c),ultimo=historial[0];
 if(ultimo){const fecha=new Date(ultimo.creadoEn).toLocaleString('es-EC',{timeZone:'America/Guayaquil'}),descarga=ultimo.descargas?.at(-1);
  const uso=(descarga?' Última descarga solicitada por '+esc(descarga.usuario)+' · '+esc(new Date(descarga.fecha).toLocaleString('es-EC',{timeZone:'America/Guayaquil'}))+'.':'')+(ultimo.confirmadoEn?' Entrega confirmada: '+esc(new Date(ultimo.confirmadoEn).toLocaleString('es-EC',{timeZone:'America/Guayaquil'}))+'.':'');
  if(!await confirmar({titulo:'Ya existe un informe de esta recepción',texto:`R${String(ultimo.numero).padStart(4,'0')} · ${esc(ultimo.estado)} · ${esc(ultimo.usuario)} · ${esc(fecha)}.${uso} Crear otra generación conserva la anterior y deja una nueva secuencia para auditoría.`,aceptar:'Generar nueva versión'}))return null;
 }
 return api(base(c),{cuerpo:{clave:nuevoIdentificador(),tipo,formato,ultimoVisto:ultimo?.id||null}});
}
export async function archivarInforme(c,informe,libros){return api(base(c)+'/'+informe.id,{metodo:'PUT',cuerpo:{adjuntos:libros.map(l=>({nombre:l.nombre,base64:l.base64,origen:l.origen}))}});}
export async function descargarInforme(informe){
 for(const f of informe.archivos){const r=await fetch(f.url,{credentials:'same-origin'});if(!r.ok)throw Error('No se pudo descargar '+f.nombre);const url=URL.createObjectURL(await r.blob()),a=document.createElement('a');a.href=url;a.download=f.nombre;a.click();setTimeout(()=>URL.revokeObjectURL(url),30000);}
}
