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
resumen();
