import {createRequire} from 'node:module';
import {cargar,test,eq,ok,resumen} from './cargador.mjs';
const require=createRequire(import.meta.url);globalThis.XLSX=require('xlsx');
const {leerPackingList}=await cargar('datos.js');
const {generarZpl}=await cargar('etiquetas.js');
const {interpretarEtiquetaMadre,interpretarEtiquetaDeBulto}=await cargar('bultos.js');
function libro(filas){const b=XLSX.utils.book_new();XLSX.utils.book_append_sheet(b,XLSX.utils.aoa_to_sheet(filas),'CLIENTE NUEVO');return b;}
function leer(b,o){return leerPackingList(XLSX.write(b,{type:'array',bookType:'xlsx'}),o);}
await test('mapea fila física 4, conserva encabezados y ceros de SKU',()=>{
  const b=libro([['Título'],[],[],['Pieza propia','Detalle','Volumen'],['00123','Producto',7]]);
  const r=leer(b,{hoja:'CLIENTE NUEVO',encabezado:4,columnas:{0:'sku',1:'descripcion',2:'cantidad'}});
  eq(r.filaEncabezado,4);eq(r.lineas[0].sku,'00123');eq(r.lineas[0].cantidad,7);eq(r.encabezados,['Pieza propia','Detalle','Volumen']);
});
await test('SKU numérico con formato 000000 conserva los ceros',()=>{
  const b=libro([['SKU','CANTIDAD'],[123,1]]);b.Sheets['CLIENTE NUEVO'].A2.z='000000';
  const r=leer(b);eq(r.lineas[0].sku,'000123');eq(r.lineas[0].cruda[0],'000123');
});
await test('rechaza cantidades negativas o texto; permite cero declarado',()=>{
  for(const n of [-1,-2,'sin dato']){let fallo=false;try{leer(libro([['SKU','CANTIDAD'],['A1',n]]));}catch(e){fallo=/cantidad/.test(e.message);}ok(fallo);}
  eq(leer(libro([['SKU','CANTIDAD'],['A1',0]])).lineas[0].cantidad,0);
});
await test('código numérico demasiado largo solicita texto sin redondearlo',()=>{
  let fallo=false;try{leer(libro([['SKU','CANTIDAD'],[1234567890123456,1]]));}catch(e){fallo=/texto/.test(e.message);}ok(fallo);
});
await test('siete copias unitarias incluyen cantidad 1 y ambos códigos de barras',()=>{
  const z=generarZpl({sku:'SKU1',serie:'SERIE1',cantidad:1,copias:7});ok(z.includes('^PQ7'));eq(z.match(/\^BCN/g).length,2);
  for(const copias of [0,-1,1.5,5001]){let fallo=false;try{generarZpl({sku:'SKU1',cantidad:1,copias});}catch{fallo=true;}ok(fallo,'copias '+copias);}
});
await test('etiqueta madre extrae código y pallet explícito, conservando ceros y separadores',()=>{
  eq(interpretarEtiquetaMadre('000123-ABC').codigo,'000123-ABC');
  const r=interpretarEtiquetaMadre('{"codigoMadre":"CAJA-001","pallet":"BM-A1"}');
  eq(r.codigo,'CAJA-001');eq(r.pallet,'BM-A1');eq(r.lecturaOriginal,'{"codigoMadre":"CAJA-001","pallet":"BM-A1"}');
  eq(interpretarEtiquetaMadre('https://proveedor.test/?sscc=000123&pallet=A1').pallet,'A1');
});
await test('no inventa pallet desde un SKU ni interpreta QR arbitrario como caja',()=>{
  eq(interpretarEtiquetaMadre('MADRE-12').pallet,'');
  for(const raw of ['{"sku":"SKU1","cantidad":2}', 'https://proveedor.test/datos', '']){
    let fallo=false;try{interpretarEtiquetaMadre(raw);}catch{fallo=true;}ok(fallo);
  }
});
await test('etiqueta interna no mezcla fotos de bultos ni reemplaza la etiqueta madre',()=>{
  const id='a'.repeat(32);eq(interpretarEtiquetaDeBulto('LB'+id,id),{interna:true});
  eq(interpretarEtiquetaDeBulto(']C1LB'+id,id),{interna:true});
  let fallo=false;try{interpretarEtiquetaDeBulto('LB'+'b'.repeat(32),id);}catch(e){fallo=e.message.includes('otro bulto');}ok(fallo);
  eq(interpretarEtiquetaDeBulto('MADRE-123',id).codigo,'MADRE-123');
});
await test('B02 conserva el bulto correcto y rechaza una etiqueta de otro bulto',()=>{
 const id='a'.repeat(32);eq(interpretarEtiquetaDeBulto(']C1B02',id,'B02',['B01','B02']),{interna:true,pallet:'B02'});
 let fallo=false;try{interpretarEtiquetaDeBulto('B01',id,'B02',['B01','B02']);}catch(e){fallo=e.message.includes('otro bulto');}ok(fallo);
});

await test('tabla lateral de facturas y BL no reemplaza las columnas de productos',()=>{
 const b=libro([['Numerodepieza','Descripción','ReferenciaPedido','Factura','Cantidad','PrecioUnit','PrecioTotal','Nombre Contenedor','Embarque','','FACTURA','NUMERO CONTENEDOR','BL','DETALLE'],
  ['00123','Producto A','PED',123,3,1,3,'ABCU1234567','EMB-A','',999,'AJENO0000000','BL-AJENO','RESUMEN AJENO'],
  ['00456','Producto B','PED',456,5,1,5,'DEFU7654321','EMB-B','',888,'OTRO0000000','BL-OTRO','RESUMEN OTRO']]);
 const r=leer(b);eq(r.embarques,['EMB-A','EMB-B']);eq(r.lineas.map(l=>[l.sku,l.factura,l.descripcion,l.contenedor]),[['00123','123','Producto A','ABCU1234567'],['00456','456','Producto B','DEFU7654321']]);eq(r.unidades,8);
 // Los perfiles anteriores podían contener dos índices para el mismo campo.
 const guardado=leer(b,{hoja:'CLIENTE NUEVO',encabezado:1,columnas:{0:'sku',1:'descripcion',3:'factura',4:'cantidad',8:'embarque',10:'factura',12:'embarque',13:'descripcion'}});
 eq(guardado.embarques,r.embarques);eq(guardado.lineas[0].contenedor,'ABCU1234567');eq(guardado.lineas[0].factura,'123');
});
await test('seleccionar contenedores recibidos recalcula cantidades sin duplicar líneas ni mutar el origen',async()=>{
 const {seleccionarContenedoresPacking}=await cargar('datos.js');
 const r=leer(libro([['SKU','Cantidad','Nombre Contenedor','Embarque'],['MISMO',3,'ABCU1234567','EMB-A'],['MISMO',5,'DEFU7654321','EMB-B']]));
 r.lineas[1].formulas={5:'SUM(B2:B3)'};
 const elegido=seleccionarContenedoresPacking(r,['DEFU7654321']);eq(elegido.lineas[0].formulas,{});eq(elegido.lineas[0].formulasOrigen,{5:'SUM(B2:B3)'});eq(r.lineas[1].formulas,{5:'SUM(B2:B3)'});eq(elegido.unidades,5);eq(elegido.porSku,{MISMO:5});eq(elegido.embarques,['EMB-B']);eq(elegido.lineas[0].filaOriginal,3);eq(r.lineas.length,2);eq(r.unidades,8);
 for(const ids of [[],['AJENO']]){let error=false;try{seleccionarContenedoresPacking(r,ids);}catch{error=true;}ok(error);}
});
resumen();
