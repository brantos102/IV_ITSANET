import {TIPOS_FOTOGRAFIA} from './tipos-foto.js?v=20261021-61';
import {pedir} from './local.js?v=20261021-61';
import {pedirDatos} from './modal.js?v=20261021-61';
import {contextoFotos} from './fotos-embarques.js?v=20261021-61';

/** Elección explícita por imagen; los códigos originales se conservan. */
export async function elegirDestinoFoto(recepcion,actual={},nombre='Fotografía'){
 const [r,ingreso,p]=await Promise.all([pedir('/recepciones/'+encodeURIComponent(recepcion)),pedir('/recepciones/'+encodeURIComponent(recepcion)+'/ingreso',{base:'/api/operacion'}),contextoFotos(recepcion)]);
 const tipos=TIPOS_FOTOGRAFIA;
 const pendiente=pedirDatos({titulo:'Destino de la foto · '+nombre,texto:'Revisa la imagen antes de elegir. Puedes asignar embarque, packing list, producto y bulto. General comparte el contexto entre embarques; no lo atribuye a uno por intuición.',campos:[
  {clave:'embarqueFoto',etiqueta:'Embarque',tipo:'lista',valor:actual.embarqueFoto??'',opciones:[{valor:'',titulo:'General · compartida entre embarques'},...p.embarques.map(v=>({valor:v,titulo:v}))]},
  {clave:'origen',etiqueta:'Packing list',tipo:'lista',valor:actual.origen||'',opciones:[{valor:'',titulo:'Todos / sin vínculo de lista'},...(r.origenes||[]).map(v=>({valor:v,titulo:r.nombresListas?.[v]||v}))]},
  {clave:'sku',etiqueta:'SKU (vacío para foto de recepción)',valor:actual.sku||''},
  {clave:'unidadId',etiqueta:'Bulto o caja',tipo:'lista',valor:actual.unidadId||'',opciones:[{valor:'',titulo:'Sin bulto'},...ingreso.unidades.map(u=>({valor:u.id,titulo:(u.tipo==='BULTO'?'Bulto ':'Caja ')+u.numero+(u.codigo?' · '+u.codigo:'')}))]},
  {clave:'categoria',etiqueta:'Clasificación',tipo:'lista',valor:actual.categoria||'GENERAL',opciones:['RECEPCION','GENERAL','VALIDACION','SOBRANTE','FALTANTE','PNC'].map(v=>({valor:v,titulo:v}))},
  {clave:'tipoEvidencia',etiqueta:'Tipo de fotografía',tipo:'lista',valor:actual.tipoEvidencia||'PANORAMICA',opciones:Object.entries(tipos).map(([valor,titulo])=>({valor,titulo}))}],aceptar:'Usar este destino'});
 const d=document.getElementById('modal'),tipo=d.querySelector('[data-clave=tipoEvidencia]');
 const contexto=()=>{const previa=tipo.value==='PRERECEPCION';for(const k of ['sku','unidadId','categoria']){const e=d.querySelector('[data-clave="'+k+'"]');e.disabled=previa;if(previa)e.value=k==='categoria'?'RECEPCION':'';}};
 tipo.addEventListener('change',contexto);contexto();const resultado=await pendiente;return resultado?.tipoEvidencia==='PRERECEPCION'?{...resultado,sku:'',unidadId:'',categoria:'RECEPCION'}:resultado;
}
