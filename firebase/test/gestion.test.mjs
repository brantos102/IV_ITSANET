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
 const rs=conteo.registrosDe([{id:'a',sku:'S',tipo:'CONTEO',cantidad:1,creadoEn:'2026-10-16T13:00:00Z'},{id:'b',sku:'S',tipo:'CONTEO',cantidad:1,creadoEn:'2026-10-16T15:00:00Z'}],'S');
 eq(rs.map(r=>r.id),['b','a']);eq(rs[0].cuando.toISOString(),'2026-10-16T15:00:00.000Z');
});
await test('el historial operativo oculta originales anulados de MySQL y su reversa',()=>{
 const es=[{id:'a',sku:'S',tipo:'CONTEO',cantidad:25},{id:'anu',tipo:'ANULACION',anulaA:'a',sku:'S',cantidad:-25},{id:'b',tipo:'CONTEO',sku:'S',cantidad:20}];
 eq(conteo.registrosDe(es,'S').map(e=>[e.id,e.cantidad]),[['b',20]]);
});
await test('el reparto de un conteo sin origen se consume una sola vez',()=>{
 const ls=[{sku:'S',linea:1,origen:'A',cantidad:3},{sku:'S',linea:1,origen:'B',cantidad:3}];
 eq(informe.repartirPorListas(ls,{S:4}).map(l=>l.fisica),[3,1]);
 eq(informe.repartirPorListas(ls,{S:5},{A:{S:2},B:{S:3}}).map(l=>l.fisica),[2,3]);
});
await test('las cantidades por lista suman los pallets del origen',()=>eq(conteo.porOrigenDe({porOrigen:{A:{P01:2,P02:3},B:{P01:1}}}),{A:5,B:1}));
await test('la columna ok de Depot no confunde un conteo completo con un código existente',()=>{
 const d=informe.completarIncidencias([{sku:'S',fisica:6,diferencia:0}],[],{depot:{S:false}})[0];
 eq(d.depot,'N/D');eq(d.incidencia,'OK');
});
await test('cliente ampliado genera un archivo por lista y enlaces del SKU sin hoja MAESTRO',()=>{
 const ls=['A','B'].map((origen,i)=>({origen,formato:{encabezados:['SKU','Cantidad','ok'],columnas:{depot:2}},detalle:[{sku:'S'+i,cantidad:3,fisica:3,diferencia:0,estado:'OK',depot:'ok',observacion:'Solo '+origen,evidencia:'https://drive.google.com/drive/folders/sku'+i,cruda:['S'+i,3,'anterior']}]}));
 const datos={recepcion:{codigo:'PRUEBA'},detalle:ls.flatMap(l=>l.detalle),porOrigen:ls,eventos:[],adicionales:[],auditoria:[]};
 const libros=informe.construirLibros(datos,{version:'envio-ampliado'});eq(libros.length,2);
 for(let i=0;i<libros.length;i++){const w=XLSX.read(libros[i].base64,{type:'base64'});eq(w.SheetNames.length,1);const sh=w.Sheets[w.SheetNames[0]],rs=XLSX.utils.sheet_to_json(sh,{header:1});eq(rs.length,2);eq(rs[1][0],'S'+i);eq(rs[1][2],'ok');ok(rs[1].includes('Solo '+ls[i].origen));ok(!rs[1].includes('Solo '+ls[1-i].origen));const j=rs[0].indexOf('Carpeta Drive del SKU');eq(sh[XLSX.utils.encode_cell({r:1,c:j})].l.Target,'https://drive.google.com/drive/folders/sku'+i);}
 const original=informe.construirLibros(datos,{version:'envio'});const w=XLSX.read(original[0].base64,{type:'base64'});eq(XLSX.utils.sheet_to_json(w.Sheets[w.SheetNames[0]],{header:1})[0],['SKU','Cantidad','ok']);
});
await test('dos listas de contenido idéntico conservan identificadores distintos en sus archivos',()=>{
 const detalle=[{sku:'S',cantidad:3,fisica:3,estado:'OK',cruda:['S',3]}];
 const datos={recepcion:{codigo:'R'},detalle,porOrigen:['A','B'].map(origen=>({origen,formato:{encabezados:['SKU','Cantidad'],columnas:{}},detalle})),eventos:[],adicionales:[],auditoria:[]};
 const libros=informe.construirLibros(datos,{version:'envio'});eq(libros.length,2);ok(libros[0].base64!==libros[1].base64);ok(libros[0].nombre!==libros[1].nombre);
 eq(XLSX.read(libros[0].base64,{type:'base64'}).Props.Subject,'Validación de recepción · Listas: A');
});
await test('una lista sin conteos no hereda observación ni pallet de otra',()=>{
 const filas=[{sku:'S',origen:'A',pallets:'P01',palletsSimple:'P01',observacion:'De A'},{sku:'S',origen:'B',pallets:'P01',palletsSimple:'P01',observacion:'De A'}];
 const eventos=[{id:'a',sku:'S',tipo:'CONTEO',origen:'A',cantidad:1,pallet:'P01',observacion:'De A'}];
 const d=informe.completarRegistrosPorLista(filas,eventos);eq(d[0].observacion,'De A');eq(d[1].observacion,'');eq(d[1].pallets,'');eq(d[1].palletsSimple,'');
 const faltante=informe.completarRegistrosPorLista(filas,[...eventos,{id:'b',sku:'S',tipo:'NO_ENCONTRADO',origen:'B',cantidad:0,observacion:'No llegó la lista B'}]);eq(faltante[1].observacion,'No llegó la lista B');eq(faltante[1].pallets,'');
});
await test('vista previa usa las mismas celdas y enlaces que el Excel final, sin mezclar listas',()=>{
 const columnas={sku:0,cantidad:1,fisica:2,observacion:3,evidencia:4};
 const lista={origen:'A',formato:{hoja:'REV',encabezados:['SKU','Declarado','Contado','Nota','Drive'],prefijo:[{celdas:['Cabecera A']}],columnas},detalle:[{sku:'S1',cantidad:10,fisica:8,estado:'FALTANTE',diferencia:-2,observacion:'Solo lista A',evidencia:'https://drive.google.com/drive/folders/sku1',cruda:['S1',10,0,'','']}]};
 const antes=JSON.stringify(lista),vista=informe.previsualizarLista(lista,columnas);
 const base={recepcion:{codigo:'R'},detalle:lista.detalle,porOrigen:[lista],eventos:[],adicionales:[],auditoria:[]};
 const x=informe.construirLibros(base,{version:'envio'})[0],w=XLSX.read(x.base64,{type:'base64'}),sh=w.Sheets.REV;
 eq(vista.filas[0].numero,3);eq(vista.filas[0].celdas.map(c=>c.texto),['S1','10','8','Solo lista A','https://drive.google.com/drive/folders/sku1']);
 eq(vista.filas[0].celdas.map(c=>c.texto),[0,1,2,3,4].map(c=>String(sh[XLSX.utils.encode_cell({r:2,c})].v)));
 eq(vista.filas[0].celdas[4].url,sh.E3.l.Target);eq(JSON.stringify(lista),antes);
 const cambio=informe.previsualizarLista(lista,{sku:0,cantidad:1,fisica:3});eq(cambio.filas[0].celdas[2].texto,'0');eq(cambio.filas[0].celdas[3].texto,'8');
});
await test('vista ampliada y paginada conserva las filas reales; ejemplos solo si no hay filas',()=>{
 const lista={origen:'A',formato:{encabezados:['SKU','Cantidad'],columnas:{sku:0,cantidad:1}},detalle:Array.from({length:14},(_,i)=>({sku:'S'+i,cantidad:2,fisica:1,estado:'FALTANTE',diferencia:-1,cruda:['S'+i,2]}))};
 const vista=informe.previsualizarLista(lista,lista.formato.columnas,{ampliado:true,offset:12});eq(vista.total,14);eq(vista.filas.length,2);eq(vista.filas[0].celdas[0].texto,'S12');ok(vista.encabezados.includes('Cantidad Física'));ok(!vista.ejemplo);
 const vacia=informe.previsualizarLista({...lista,detalle:[]},lista.formato.columnas);ok(vacia.ejemplo);eq(vacia.filas[0].celdas[0].texto,'EJEMPLO001');eq(lista.detalle.length,14);
});
resumen();
