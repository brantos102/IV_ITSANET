import {operacion,esc} from './evidencias.js?v=20261018-41';
import {pedirDatos,elegir,confirmar} from './modal.js?v=20261018-41';
export async function editarRecepcion(codigo){
 const ruta='/recepciones/'+encodeURIComponent(codigo),r=await operacion(ruta+'/edicion');
 const accion=await elegir({titulo:codigo,texto:'Edita los datos de recepción o retira un embarque añadido por error. Se conserva la auditoría.',opciones:[
 {valor:'datos',titulo:'Datos de recepción',detalle:'Descripción, embarques y total de bultos'},
 ...(r.origenes.length?[{valor:'retirar',titulo:'Retirar / separar un embarque',detalle:'Puedes crear otra recepción con sus filas de origen. Primero deben resolverse los conteos y evidencias vinculadas.'}]:[])]});
 if(!accion)return false;
 if(accion==='datos'){
  const d=await pedirDatos({titulo:'Editar recepción',texto:esc(codigo)+' · Cliente '+esc(r.cliente)+'. El código y el cliente identifican los registros existentes.',campos:[
   {clave:'descripcion',etiqueta:'Descripción',valor:r.descripcion},
   {clave:'embarques',etiqueta:'Embarques (separados por coma)',valor:r.embarques.join(', ')},
   {clave:'bultos',etiqueta:'Total de bultos',valor:r.bultos||0,obligatorio:true}]});
  if(!d)return false;
  await operacion(ruta+'/edicion',{metodo:'PUT',cuerpo:{...d,bultos:Number(d.bultos),embarques:d.embarques.split(',').map(s=>s.trim()).filter(Boolean),version:r.versionEdicion}});return true;
 }
 const d=await pedirDatos({titulo:'Retirar embarque',campos:[{clave:'origen',etiqueta:'Embarque / packing list',tipo:'lista',valor:r.origenes[0],opciones:r.origenes.map(o=>({valor:o,titulo:o}))},
 {clave:'motivo',etiqueta:'Motivo',obligatorio:true}]});if(!d)return false;
 const destino=await elegir({titulo:'¿Crear otra recepción con este embarque?',texto:'Sus filas y columnas originales se conservan en la nueva recepción. Los conteos vigentes o evidencias con vínculo a este embarque deben resolverse primero.',opciones:[{valor:'nueva',titulo:'Sí, separar en una recepción nueva',detalle:'Conservar el embarque para validarlo aparte'},{valor:'retirar',titulo:'Solo retirar de esta recepción',detalle:'Se conserva copia de sus filas y formato en la auditoría'}]});if(!destino)return false;
 let nuevaRecepcion='';if(destino==='nueva'){const n=await pedirDatos({titulo:'Nueva recepción del embarque',campos:[{clave:'codigo',etiqueta:'Código nuevo',valor:(codigo+'-SEPARADA').slice(0,100),obligatorio:true}]});if(!n)return false;nuevaRecepcion=n.codigo;}
 if(!await confirmar({titulo:'Confirmar retirada de '+d.origen,texto:nuevaRecepcion?'Se separará a '+esc(nuevaRecepcion):'Se retirará de la recepción. Sus filas originales quedan en la auditoría.',aceptar:'Confirmar cambio'}))return false;
 await operacion(ruta+'/embarques/'+encodeURIComponent(d.origen)+'/retirar',{cuerpo:{motivo:d.motivo,nuevaRecepcion,version:r.versionEdicion}});return true;
}
