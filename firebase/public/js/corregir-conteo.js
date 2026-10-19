import {pedir,nuevoIdentificador} from './local.js?v=20261019-55';
import {pedirDatos,elegir,confirmar} from './modal.js?v=20261019-55';
import {eventosActivos} from './conteo.js?v=20261019-55';

export async function abrirCorreccion({recepcion,sku,contado,origenes=[],incidencias=[],alGuardar,eventoId}) {
  const eventos=await pedir(`/recepciones/${encodeURIComponent(recepcion)}/eventos`);
  const activos=eventosActivos(eventos).filter(e=>e.sku===sku&&['CONTEO','NO_ENCONTRADO'].includes(e.tipo));
  if(!activos.length)throw Error('Este SKU no tiene conteos activos para corregir.');
  const id=eventoId||(activos.length===1?activos[0].id:await elegir({titulo:'¿Qué registro corregir?',opciones:activos.map(e=>({valor:e.id,titulo:`${e.cantidad} u. · ${e.pallet||'Sin pallet'} · ${e.origen||'Sin lista'}`,detalle:`${e.operadorEmail||''} · ${new Date(e.creadoEn).toLocaleString('es-EC',{timeZone:'America/Guayaquil'})}`}))}));
  if(!id)return;const e=activos.find(e=>e.id===id);if(!e)throw Error('El registro cambió; actualiza la pantalla.');
  const d=await pedirDatos({titulo:'Corregir conteo · '+sku,texto:'Se sustituye este registro, no el total de todos los pallets. El original queda anulado solo en auditoría. Si otro usuario cambia el SKU, se pedirá actualizar.',campos:[
    {clave:'cantidad',etiqueta:'Cantidad correcta de este registro',valor:e.cantidad,obligatorio:true,tipo:'numero'},
    {clave:'pallet',etiqueta:'Pallet',valor:e.pallet||''},
    ...(origenes.length?[{clave:'origen',etiqueta:'Packing list',tipo:'lista',valor:e.origen||origenes[0],opciones:origenes.map(o=>({valor:o,titulo:o}))}]:[]),
    {clave:'observacion',etiqueta:'Observación',valor:e.observacion||''},
    {clave:'clasificacion',etiqueta:'Clasificación física',tipo:'lista',valor:'CONSERVAR',opciones:[{valor:'CONSERVAR',titulo:'Conservar clasificación actual'},{valor:'OK',titulo:'Todo conforme'},...incidencias.filter(i=>i.activo&&!['OK','FALTANTE','SOBRANTE'].includes(i.codigo)).map(i=>({valor:i.codigo,titulo:i.nombre}))]},
    {clave:'cantidadIncidencia',etiqueta:'Unidades afectadas si cambias la clasificación',valor:''},
    {clave:'motivo',etiqueta:'Motivo de corrección',obligatorio:true}],aceptar:'Guardar corrección'});
  if(!d)return;
  const datos={...d,cantidad:Number(d.cantidad),id:nuevoIdentificador(),contadoEsperado:contado};
  if(d.clasificacion!=='CONSERVAR')datos.incidencias=d.clasificacion==='OK'?[]:[{tipo:d.clasificacion,cantidad:Number(d.cantidadIncidencia)}];
  const ruta=`/recepciones/${encodeURIComponent(recepcion)}/eventos/${encodeURIComponent(id)}/corregir`;
  let resultado;
  try{resultado=await pedir(ruta,{base:'/api/operacion',cuerpo:datos});}
  catch(e){if(e.codigo!=='CONFIRMAR_SOBRANTE')throw e;
    if(!await confirmar({titulo:'Revisar sobrante',texto:e.message,aceptar:'Confirmar sobrante real',cancelar:'Volver a revisar'}))return;
    resultado=await pedir(ruta,{base:'/api/operacion',cuerpo:{...datos,confirmarSobrante:true}});
  }
  await alGuardar?.(resultado);return resultado;
}
