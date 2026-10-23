import {cargar,test,eq,ok,resumen} from './cargador.mjs';
const {numerosDeEtiquetas,htmlEtiquetasBultos}=await cargar('etiquetas-bultos.js');
await test('65: rangos seleccionan números originales y deduplican sin copias extra',()=>{
 eq(numerosDeEtiquetas('02-05, 15, 4, 68–70',70),[2,3,4,5,15,68,69,70]);
 eq(numerosDeEtiquetas('70',70),[70]);
});
await test('65: selección fuera del total o ambigua se rechaza',()=>{
 for(const txt of ['', '0','71','8-2','1,,3','B01-B03','1.5','1/3','1-1001']){let fallo=false;try{numerosDeEtiquetas(txt,70);}catch{fallo=true;}ok(fallo,txt);}
});
await test('65: 100x150 añade contexto y cantidad física sin cambiar el código de barras',()=>{
 const barras=[],html=htmlEtiquetasBultos({formato:'100x150',recepcion:'R-65',cliente:'VENTURA',marca:'VW',lote:1,etiquetas:[{rotulo:'P51',numero:51,total:70,codigoMadre:'MADRE-0051'}]},s=>{barras.push(s);return '<svg></svg>';});
 eq(barras,['P51']);for(const s of ['size:100mm 150mm','etiqueta-grande','VENTURA','R-65','VW','BULTO 51 DE 70','MADRE-0051','grid-template-rows:18mm 14mm 34mm 48mm 16mm'])ok(html.includes(s),s);
});
await test('65: 100x50 conserva solo rótulo y barras y no expone identificadores internos',()=>{
 const html=htmlEtiquetasBultos({formato:'100x50',recepcion:'R',lote:1,cliente:'NO EN COMPACTA',etiquetas:[{rotulo:'P51',numero:51,total:70,unidadId:'NO-ID',serie:'NO-SERIE'}]},()=>'<svg></svg>');
 for(const s of ['size:100mm 50mm','P51'])ok(html.includes(s),s);
 for(const s of ['NO EN COMPACTA','BULTO 51 DE 70','NO-ID','NO-SERIE'])ok(!html.includes(s),s);
});
resumen();
