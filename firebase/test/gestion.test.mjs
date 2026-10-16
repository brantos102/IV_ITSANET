import {createRequire} from 'node:module';
import {cargar,test,eq,ok,resumen} from './cargador.mjs';
const require=createRequire(import.meta.url);globalThis.XLSX=require('xlsx');
const informe=await cargar('informe.js'),csv=await cargar('csv.js');
await test('2 PNC de 6 mantienen 4 conformes y no se duplican en filas repetidas',()=>{
 const filas=[{sku:'S',origen:'PL',fisica:1,diferencia:0},{sku:'S',origen:'PL',fisica:5,diferencia:0}];
 const eventos=[{id:'a',sku:'S',origen:'PL',cantidad:6,incidencias:[{tipo:'MAL_ESTADO',nombre:'MAL ESTADO',cantidad:2,pnc:true}]}];
 const d=informe.completarIncidencias(filas,eventos);eq(d.map(f=>f.cantidadPnc),[1,1]);eq(d.map(f=>f.cantidadConforme),[0,4]);
 eq(csv.agruparConteos(eventos).map(f=>[f.estado,f.cantidad]).sort(),[['BUENO',4],['PNC',2]]);
});
await test('corrección de calidad y anulación respetan evento original',()=>{
 const e=[{id:'a',sku:'S',cantidad:6,estadoFisico:'PNC'}, {id:'q',tipo:'CALIDAD',eventoId:'a',cantidad:0,incidencias:[{tipo:'MAL_ESTADO',cantidad:2,pnc:true}]}];
 eq(informe.completarIncidencias([{sku:'S',fisica:6,diferencia:0}],e)[0].cantidadPnc,2);
 eq(csv.agruparConteos([...e,{id:'anu_a',tipo:'ANULACION',anulaA:'a',cantidad:-6}]),[]);
});
await test('incidencias se imputan únicamente a su packing list',()=>{
 const d=informe.completarIncidencias([{sku:'S',origen:'A',fisica:6},{sku:'S',origen:'B',fisica:6}],[{id:'b',sku:'S',origen:'B',cantidad:6,incidencias:[{tipo:'INCORRECTO',cantidad:2,pnc:true}]}]);
 eq(d.map(f=>f.cantidadPnc),[0,2]);
});
await test('A M P Q R S configurables conservan filas, cabeceras y código con ceros',()=>{
 const encabezados=Array.from({length:19},(_,i)=>'ENCABEZADO '+i),columnas={marca:0,codigoBarra:12,cantidadIncidencia:15,incidencia:16,observacion:17,evidencia:18};
 const detalle=informe.completarIncidencias([{sku:'S',origen:'PL',fisica:6,diferencia:0,observacion:'2 rotos',cruda:Array(19).fill('original')}],[{id:'a',sku:'S',origen:'PL',cantidad:6,incidencias:[{tipo:'MAL_ESTADO',nombre:'MAL ESTADO',cantidad:2,pnc:true}]}],{marca:'ISUZU',cliente:'VENTURA',barras:{S:'00001234'},carpetas:{S:['https://drive.google.com/drive/folders/sku']}});
 const f=informe.construirLibro({recepcion:{codigo:'R',informe:{id:'id-auditado',numero:1,sufijo:'_R0001_20261016-080000',usuario:'sup@itsanet.com'}},detalle,porOrigen:[{origen:'PL',formato:{encabezados,columnas},detalle}],adicionales:[],eventos:[],auditoria:[]},{version:'envio'});
 ok(f.nombre.endsWith('_R0001_20261016-080000.xlsx'));
 const w=XLSX.read(f.base64,{type:'base64'}),tabla=XLSX.utils.sheet_to_json(w.Sheets[w.SheetNames[0]],{header:1});
 eq(tabla.length,2);eq(tabla[0],encabezados);eq(tabla[1][0],'ISUZU');eq(tabla[1][12],'00001234');eq(tabla[1][15],2);eq(tabla[1][16],'MAL ESTADO (2)');eq(tabla[1][18],'https://drive.google.com/drive/folders/sku');eq(tabla[1][4],'original');eq(w.Props.Author,'sup@itsanet.com');
});
await test('los dos modelos de Depot no incluyen plantilla de barras inexistente',()=>eq(csv.FORMATOS_BASE.length,2));
await test('un PNC antiguo sin desglose no inventa unidades conformes',()=>{
 const d=informe.completarIncidencias([{sku:'S',fisica:6,diferencia:0,pnc:'PNC',calidadPorRevisar:true}],[])[0];
 eq(d.cantidadPnc,null);eq(d.cantidadConforme,null);ok(d.incidencia.includes('cantidad por revisar'));
});
const conteo=await cargar('conteo.js');
await test('el historial de MySQL interpreta fechas ISO y muestra primero la última',()=>{
 const rs=conteo.registrosDe([{id:'a',sku:'S',cantidad:1,creadoEn:'2026-10-16T13:00:00Z'},{id:'b',sku:'S',cantidad:1,creadoEn:'2026-10-16T15:00:00Z'}],'S');
 eq(rs.map(r=>r.id),['b','a']);eq(rs[0].cuando.toISOString(),'2026-10-16T15:00:00.000Z');
});
resumen();
