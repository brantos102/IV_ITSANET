/** Estado por archivo: el alias de salida no modifica el documento histórico. */
export const etiquetaFormato=f=>({'envio':'Informe para el ejecutivo','envio-ampliado':'Informe ampliado y organizado','auditable':'Informe de control y bitácora'}[f]||'Informe');
export function documentosDelCorreo(v){
 const seleccion=new Map((v.archivos||[]).map(a=>[a.id,a]));
 const disponibles=new Map((v.documentosDisponibles||[]).map(a=>[a.id,{...a}]));
 const idsVigentes=new Set(disponibles.keys());
 for(const a of seleccion.values())disponibles.set(a.id,{...disponibles.get(a.id),...a});
 return [...disponibles.values()].map(a=>({...a,nombre:seleccion.get(a.id)?.nombre||v.nombresDocumentos?.[a.id]||a.nombre,
  seleccionado:seleccion.has(a.id),vigente:!!v.vistaArchivada||idsVigentes.has(a.id)}));
}
/** Añadir un formato conserva los demás adjuntos vigentes y sus nombres. */
export function agregarDocumentos(actuales,nuevos,disponibles,nombres={}){
 const vigentes=new Set(disponibles.map(a=>a.id)),seleccion=new Map();
 const retirados=[];
 for(const a of actuales){if(vigentes.has(a.id))seleccion.set(a.id,{id:a.id,nombre:a.nombre});else retirados.push(a);}
 for(const a of nuevos){if(!vigentes.has(a.id))throw Error('El documento preparado cambió. Actualiza y vuelve a revisar sus archivos.');
  if(!seleccion.has(a.id))seleccion.set(a.id,{id:a.id,nombre:nombres[a.id]||a.nombre});
 }
 return {adjuntos:[...seleccion.values()],retirados};
}
