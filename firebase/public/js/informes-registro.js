import {pedir,nuevoIdentificador} from './local.js?v=20261023-67';
import {confirmar,elegir} from './modal.js?v=20261023-67';
const api=(ruta,opciones={})=>pedir(ruta,{...opciones,base:'/api/operacion'});
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const base=c=>'/recepciones/'+encodeURIComponent(c)+'/informes';
export const historialInformes=c=>api(base(c));
export const informeActual=(c,formato)=>api('/recepciones/'+encodeURIComponent(c)+'/informe-actual?formato='+encodeURIComponent(formato));
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
export async function archivarInforme(c,informe,libros){return api(base(c)+'/'+informe.id,{metodo:'PUT',cuerpo:{adjuntos:libros.map(l=>({nombre:l.nombre,base64:l.base64,origen:l.origen,...(l.grupo?{grupo:l.grupo}:{})}))}});}
/** Prepara una revisión descargable; conserva el cierre y no crea una entrega. */
export async function prepararDocumentosPorEmbarque(c){
 const plan=await api('/recepciones/'+encodeURIComponent(c)+'/correos-embarques');
 if(plan.embarques.length&&plan.modo==='PACKING_LIST'&&!plan.consolidadoConfirmado){
  const {revisarPlanCorreos}=await import('./correos-embarques.js?v=20261023-67');
  if(!await revisarPlanCorreos(c))return null;
 }
 const formato=await elegir({titulo:'Preparar documentos por packing list',texto:'Se conservan el cierre, los conteos y los documentos históricos. El correo descargará los documentos preparados para que puedas revisarlos antes de enviar.',opciones:[
  {valor:'envio-ampliado',titulo:'Informe ampliado y organizado',detalle:'Columnas configuradas y detalle de la validación.'},
  {valor:'envio',titulo:'Informe para el ejecutivo · packing list',detalle:'Conserva la estructura original del documento recibido.'},
  {valor:'auditable',titulo:'Informe de control y bitácora',detalle:'Resumen, registros y detalle para revisión interna.'}]});
 if(!formato)return null;
 const vigente=await informeActual(c,formato);if(vigente.actual)return vigente.informe;
 const f=await iniciarInforme(c,'DESCARGA',formato);if(!f)return null;if(f.estado==='GENERADO')return f;
 const [{reunirInforme,construirLibros},recepcion]=await Promise.all([import('./informe.js?v=20261023-67'),pedir('/recepciones/'+encodeURIComponent(c))]);
 const datos=await reunirInforme(c,recepcion);datos.recepcion={...datos.recepcion,informe:f};
 return archivarInforme(c,f,construirLibros(datos,{version:formato}));
}
const descargasEnCurso=new Set();
export async function descargarInforme(informe,{origen=null}={}){
 if(descargasEnCurso.has(informe.id))return;descargasEnCurso.add(informe.id);
 try{
  const fs=informe.archivos||[];if(!fs.length)throw Error('El informe aún no tiene documentos preparados.');
  if(origen===null&&fs.length>1){origen=await elegir({titulo:'Descargar documentos preparados',texto:'Se conserva esta versión. Elige un packing list o un solo ZIP con todos; no se envía correo.',opciones:[{valor:'',titulo:'Todos los packing lists · un ZIP'},...([...new Set(fs.map(f=>f.grupo||f.origen))].map(id=>({valor:id,titulo:informe.grupos?.find(g=>g.id===id)?.nombre||id||'Documento',detalle:fs.filter(f=>(f.grupo||f.origen)===id).map(f=>f.nombre).join(' · ')})))]});if(origen===null)return false;}
  const r=await fetch('/api/operacion/informes/'+informe.id+'/descarga'+(origen?'?origen='+encodeURIComponent(origen):''),{credentials:'same-origin'});
  if(!r.ok)throw Error('No se pudo descargar el informe ('+r.status+'). Revisa los documentos o genera su versión actualizada.');
  const cd=r.headers.get('Content-Disposition')||'',utf=cd.match(/filename\*=UTF-8''([^;]+)/i),simple=cd.match(/filename="?([^";]+)/i);
  const nombre=utf?decodeURIComponent(utf[1]):simple?.[1]||fs[0].nombre;
  const url=URL.createObjectURL(await r.blob()),a=document.createElement('a');a.href=url;a.download=nombre;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
  return true;
 }finally{descargasEnCurso.delete(informe.id);}
}
