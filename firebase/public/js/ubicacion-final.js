import {pedir} from './local.js?v=20261022-63';
import {pedirDatos,elegir} from './modal.js?v=20261022-63';
import {eventosActivos} from './conteo.js?v=20261022-63';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export async function asignarUbicacionFinal({recepcion,sku,eventoId,alGuardar}){
 const ruta='/recepciones/'+encodeURIComponent(recepcion),eventos=await pedir(ruta+'/eventos');
 const activos=eventosActivos(eventos).filter(e=>e.sku===sku&&e.tipo==='CONTEO'&&Number(e.cantidad)>0&&e.pallet);
 if(!activos.length)throw Error('Este SKU todavía no tiene un conteo con pallet para asignar su posición final.');
 const id=eventoId&&activos.some(e=>e.id===eventoId)?eventoId:activos.length===1?activos[0].id:await elegir({titulo:'Seleccionar conteo y pallet · '+sku,opciones:activos.map(e=>({valor:e.id,titulo:e.pallet+' · '+e.cantidad+' unidades · '+(e.origen||'Sin lista'),detalle:'Posición: '+(e.posicionReal||'Pendiente')+' · '+(e.operadorEmail||'')}))});
 if(!id)return;const e=activos.find(e=>e.id===id);
 const d=await pedirDatos({titulo:'Posición final · '+sku,texto:'Pallet '+esc(e.pallet)+' · '+e.cantidad+' unidades · '+esc(e.origen||'Sin lista')+'. Se conserva el conteo y queda registrado quién asignó la posición.',campos:[{clave:'posicionReal',etiqueta:'Posición final',valor:e.posicionReal||'',obligatorio:true,desglosarPosicion:true}],aceptar:'Guardar posición'});
 if(!d)return;const r=await pedir(ruta+'/eventos/'+encodeURIComponent(id)+'/posicion',{metodo:'PUT',cuerpo:{...d,posicionAnterior:e.posicionReal||''}});await alGuardar?.(r);return r;
}
