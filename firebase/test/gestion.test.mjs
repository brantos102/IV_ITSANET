import {createRequire} from 'node:module';
import {cargar,test,eq,ok,resumen} from './cargador.mjs';
const require=createRequire(import.meta.url);globalThis.XLSX=require('xlsx');
const informe=await cargar('informe.js'),csv=await cargar('csv.js');
const organizacion=await cargar('orden-informe.js');
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
 eq(tabla.length,2);eq(tabla[0],encabezados);eq(tabla[1][0],'original');eq(tabla[1][12],'00001234');eq(tabla[1][15],2);eq(tabla[1][16],'MAL ESTADO');eq(tabla[1][18],'https://drive.google.com/drive/folders/sku');eq(tabla[1][4],'original');eq(w.Props.Author,'sup@itsanet.com');
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
 for(let i=0;i<libros.length;i++){const w=XLSX.read(libros[i].base64,{type:'base64'});eq(w.SheetNames.length,1);const sh=w.Sheets[w.SheetNames[0]],rs=XLSX.utils.sheet_to_json(sh,{header:1});eq(rs.length,2);eq(rs[0].slice(0,2),['MARCA','CLIENTE']);eq(rs[1][rs[0].indexOf('SKU')],'S'+i);eq(rs[1][rs[0].indexOf('ok')],'ok');ok(rs[1].includes('Solo '+ls[i].origen));ok(!rs[1].includes('Solo '+ls[1-i].origen));const j=rs[0].indexOf('Carpeta Drive del SKU');eq(sh[XLSX.utils.encode_cell({r:1,c:j})].l.Target,'https://drive.google.com/drive/folders/sku'+i);}
 const original=informe.construirLibros(datos,{version:'envio'});const w=XLSX.read(original[0].base64,{type:'base64'});eq(XLSX.utils.sheet_to_json(w.Sheets[w.SheetNames[0]],{header:1})[0],['SKU','Cantidad','ok']);
});
await test('ampliado inicia con marca y cliente y conserva cada dato del origen',()=>{
 const formato={encabezados:['ITEM','Descripción','Cantidad'],columnas:{sku:0,descripcion:1,cantidad:2}};
 const detalle=[{sku:'S01',descripcion:'Producto original',cantidad:8,fisica:6,estado:'FALTANTE',diferencia:-2,posicionReal:'A-01-02-1',codigoBarra:'00001234',cliente:'CLIENTE',marca:'MARCA',cruda:['S01','Producto original',8]}];
 const datos={recepcion:{codigo:'R'},detalle,porOrigen:[{origen:'EMB',formato,detalle}],adicionales:[],eventos:[],auditoria:[]};
 const leer=version=>{const libro=informe.construirLibro(datos,{version}),w=XLSX.read(libro.base64,{type:'base64'});return XLSX.utils.sheet_to_json(w.Sheets[w.SheetNames[0]],{header:1,defval:''});};
 const original=leer('envio'),ampliado=leer('envio-ampliado');
 eq(original,[formato.encabezados,detalle[0].cruda]);eq(ampliado[0].slice(0,2),['MARCA','CLIENTE']);eq(ampliado[0].slice(2,5),formato.encabezados);eq(ampliado[1].slice(2,5),detalle[0].cruda);
 for(const [campo,valor] of [['Posición','A-01-02-1'],['Código de barras','00001234'],['CLIENTE','CLIENTE'],['MARCA','MARCA']]){const i=ampliado[0].indexOf(campo);ok(i>=0);eq(ampliado[1][i],valor);}
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
 const vista=informe.previsualizarLista(lista,lista.formato.columnas,{ampliado:true,offset:12});eq(vista.total,14);eq(vista.filas.length,2);eq(vista.filas[0].celdas[vista.encabezados.indexOf('SKU')].texto,'S12');ok(vista.encabezados.includes('Cantidad Física'));ok(!vista.ejemplo);
 const vacia=informe.previsualizarLista({...lista,detalle:[]},lista.formato.columnas);ok(vacia.ejemplo);eq(vacia.filas[0].celdas[0].texto,'EJEMPLO001');eq(lista.detalle.length,14);
});
await test('formato ampliado protege ITEM, antepone cliente sin duplicar marca y elimina solo rótulos de muestra',()=>{
 const encabezados=['MARCA','ITEM','Descripción','ReferenciaPedido','Factura','Cantidad','PrecioUnit','PrecioTotal','Numero de pieza reemplazo','Embarque','Cantidad Física','PALLET','CODIGO BARRA','COD/PROD','ok','Cant. Con incidencia','Tipo de incidencia','OBSERVACION','Evidencia fotografica : Dir, Url (Drive)'];
 const cruda=['ISUZU','3QF615301F','BRAKE DISC','RAISZ260926','ECUAD03658','255','4.66','466','','RB654123','','','','','','','','',''];
 const columnas={sku:1,descripcion:2,cantidad:5,depot:1,marca:1,cliente:2,fisica:10,pallet:11,codigoBarra:12,incidencia:14,observacion:17};
 const lista={origen:'RB654123',formato:{encabezados,columnas,prefijo:[{celdas:['Espacio que llenan opertivos','Espacio que llena el ejecutivo']} ]},detalle:[{sku:'3QF615301F',fisica:255,diferencia:0,estado:'OK',depot:'N/D',marca:'VENTURA',cliente:'VENTURA',cantidadIncidencia:2,incidencia:'ROTULADO ERRONEO',observacion:'Revisado',cruda}]};
 const vista=informe.previsualizarLista(lista,columnas,{ampliado:true});
 eq(vista.encabezados.slice(0,2),['MARCA','CLIENTE']);eq(vista.encabezados.filter(v=>v!=='CLIENTE').slice(0,encabezados.length),encabezados);eq(vista.filas[0].numero,2);
 eq(vista.filas[0].celdas.filter((_,i)=>vista.encabezados[i]!=='CLIENTE').slice(0,10).map(c=>c.texto),cruda.slice(0,10));
 eq(vista.filas[0].celdas[vista.encabezados.indexOf('ok')].texto,'N/D');eq(vista.filas[0].celdas[vista.encabezados.indexOf('Cant. Con incidencia')].texto,'2');eq(vista.filas[0].celdas[vista.encabezados.indexOf('Tipo de incidencia')].texto,'ROTULADO ERRONEO');
 eq(vista.encabezados.filter(v=>/incidencia/i.test(v)).length,2);eq(vista.encabezados.filter(v=>/drive/i.test(v)).length,1);
});
await test('categoría NUV DEV o SCRAP y posición viajan en el modelo de cantidades',()=>{
 for(const categoria of ['NUV','DEV','SCRAP']){
  const r=csv.csvDeCantidades(csv.FORMATOS_BASE[0],{categoriaLogica:categoria,eventos:[{id:'e',sku:'S',cantidad:2,pallet:'B02',posicionReal:'BM-A1-02-3'}],catalogo:{S:{unidad:'CS'}}});
  eq(r.tabla[1][7],categoria);eq(r.tabla[1][5],'B02');ok(r.tabla[1].includes('BM'));eq(r.filas,1);
 }
});
await test('BM-A-10-1 sale en columnas separadas con pallet y cantidad conservados',()=>{
 const r=csv.csvDeCantidades(csv.FORMATOS_BASE[0],{categoriaLogica:'NUV',eventos:[{id:'e61',tipo:'CONTEO',sku:'S61',cantidad:3,pallet:'Q04.1',posicionReal:'BM-A-10-1'}],catalogo:{S61:{unidad:'CS'}}});
 const fila=Object.fromEntries(r.tabla[0].map((h,i)=>[h,r.tabla[1][i]]));eq(fila.NAVE,'BM');eq(fila.CALLE,'A');eq(fila.COLUMNA,'10');eq(fila.NIVEL,'1');eq(fila['NRO PALLET'],'Q04.1');eq(fila.CANTIDAD,3);
});
await test('posición con etiquetas y ceros conserva nave literal columna y nivel',()=>{
 eq(csv.partesDePosicion('NAVE: BM, LITERAL: A, COLUMNA: 010, NIVEL: 01'),{nave:'BM',calle:'A',columna:'010',nivel:'01',profundidad:''});
});
await test('el CSV posterior a corrección usa únicamente posición y cantidad vigentes',()=>{
 const r=csv.csvDeCantidades(csv.FORMATOS_BASE[0],{categoriaLogica:'NUV',eventos:[{id:'antes',tipo:'CONTEO',sku:'S61',cantidad:8,pallet:'Q04.1',posicionReal:'BM-X-20-3'},{id:'anular',tipo:'ANULACION',anulaA:'antes',cantidad:-8,sku:'S61'},{id:'nuevo',tipo:'CONTEO',sku:'S61',cantidad:3,pallet:'Q04.1',posicionReal:'BM-A-10-1'}],catalogo:{S61:{unidad:'CS'}}});
 eq(r.filas,1);const f=Object.fromEntries(r.tabla[0].map((h,i)=>[h,r.tabla[1][i]]));eq(f.CANTIDAD,3);eq(f.CALLE,'A');eq(f.COLUMNA,'10');eq(f.NIVEL,'1');
});
const bultos=await cargar('etiquetas-bultos.js');
await test('etiqueta compacta imprime solo literal y código de barras del mismo dato',()=>{
 const dibujados=[];const html=bultos.htmlEtiquetasBultos({formato:'100x50',recepcion:'R',lote:1,etiquetas:[{rotulo:'B02',serie:'LB-identificador-interno',numero:2,total:8,unidadId:'interno'}]},codigo=>{dibujados.push(codigo);return '<svg/>';});
 eq(dibujados,['B02']);ok(html.includes('B02'));ok(!html.includes('LB-identificador-interno'));ok(!html.includes('BULTO 2 DE 8'));ok(!html.includes('ID interno'));
});
await test('NUV del ingreso no vuelve conformes a los PNC sin una categoría autorizada',()=>{
 const datos={categoriaLogica:'NUV',eventos:[{id:'pnc',sku:'S',cantidad:1,pallet:'B02',estadoFisico:'PNC'}],catalogo:{S:{unidad:'CS'}}};
 let r=csv.csvDeCantidades(csv.FORMATOS_BASE[0],datos);eq(r.tabla[1][7],'');ok(r.incidencias.some(i=>i.encabezado==='CODIGO CATEGORIA LÓGICA'));
 r=csv.csvDeCantidades(csv.FORMATOS_BASE[0],{...datos,categoriaLogicaPnc:'DEV'});eq(r.tabla[1][7],'DEV');
});
await test('orden por embarque conserva celdas, enlaces, ceros y la misma vista previa que Excel',()=>{
 const formato={hoja:'FINAL',encabezados:['ITEM','Cantidad','Total'],columnas:{sku:0,cantidad:1},prefijo:[{celdas:['Cabecera original']}]};
 const ids=organizacion.columnasDeSalida(formato).map(c=>c.id);
 const primero=['resultado:cliente','original:1','resultado:marca','original:0'];
 formato.ordenSalida=[...primero,...ids.filter(id=>!primero.includes(id))];
 const detalle=[{sku:'0001',cantidad:3,fisica:2,diferencia:-1,estado:'FALTANTE',marca:'ISUZU',cliente:'VENTURA',codigoBarra:'00001234',evidencia:'https://drive.google.com/drive/folders/uno',cruda:['0001',3,6],formulas:{2:'B3*2'},filaOriginal:3}];
 const lista={origen:'EMB-A',formato,detalle},antes=JSON.stringify(lista),vista=informe.previsualizarLista(lista,formato.columnas,{ampliado:true});
 const datos={recepcion:{codigo:'R'},detalle,porOrigen:[lista],adicionales:[],eventos:[],auditoria:[]};
 const x=informe.construirLibros(datos,{version:'envio-ampliado'})[0],w=XLSX.read(x.base64,{type:'base64'}),sh=w.Sheets.FINAL;
 eq(vista.encabezados.slice(0,4),['CLIENTE','Cantidad','MARCA','ITEM']);eq(vista.filas[0].celdas.slice(0,4).map(c=>c.texto),['VENTURA','3','ISUZU','0001']);
 eq(vista.filas[0].celdas.map(c=>c.texto),vista.encabezados.map((_,c)=>String(sh[XLSX.utils.encode_cell({r:2,c})]?.v??'')));
 const total=vista.encabezados.indexOf('Total');eq(sh[XLSX.utils.encode_cell({r:2,c:total})].f,'B3*2');
 eq(sh[XLSX.utils.encode_cell({r:2,c:vista.encabezados.indexOf('Carpeta Drive del SKU')})].l.Target,detalle[0].evidencia);
 eq(JSON.stringify(lista),antes);eq(XLSX.utils.sheet_to_json(sh,{header:1}).length,3);
 const original=informe.construirLibros(datos,{version:'envio'})[0],wo=XLSX.read(original.base64,{type:'base64'});eq(wo.Sheets.FINAL.C3.f,'B3*2');eq(wo.Sheets.FINAL.A3.v,'0001');
});
await test('el orden de una lista no se aplica a otra y se puede conservar el bloque original',()=>{
 const detalle=[{sku:'S',cantidad:2,fisica:2,estado:'OK',cruda:['S',2]}],formato={encabezados:['ITEM','Cantidad'],columnas:{sku:0,cantidad:1}};
 const ids=organizacion.columnasDeSalida(formato).sort((a,b)=>a.indice-b.indice).map(c=>c.id);
 const datos={recepcion:{codigo:'R'},detalle:detalle.concat(detalle),porOrigen:[{origen:'A',detalle,formato:{...formato,ordenSalida:ids}},{origen:'B',detalle,formato}],adicionales:[],eventos:[],auditoria:[]};
 const libros=informe.construirLibros(datos,{version:'envio-ampliado'}).map(l=>{const w=XLSX.read(l.base64,{type:'base64'});return XLSX.utils.sheet_to_json(w.Sheets[w.SheetNames[0]],{header:1})[0];});
 eq(libros[0].slice(0,2),['ITEM','Cantidad']);eq(libros[1].slice(0,2),['MARCA','CLIENTE']);
});
await test('mover columnas ajusta referencias absolutas, relativas y rangos sin tocar textos ni funciones',()=>{
 const sh=XLSX.utils.aoa_to_sheet([['Cantidad','Precio','Total'],[2,3,6]]);sh.C2.f='IF(A2="A2",$A2*B$2+$A$2+sum(a2:b2)+LOG10(A2),0)';
 const orden=[{indice:2},{indice:0},{indice:1}],nuevo=organizacion.organizarHojaInforme(sh,orden);
 eq(nuevo.A2.f,'IF(B2="A2",$B2*C$2+$B$2+sum(B2:C2)+LOG10(B2),0)');eq(nuevo.B2.v,2);eq(nuevo.C2.v,3);eq(sh.C2.v,6);
});
await test('un rango que perdería sus columnas o una referencia dinámica bloquea el archivo organizado',()=>{
 const sh=XLSX.utils.aoa_to_sheet([['A','B','C'],[2,3,6]]),orden=[{indice:0},{indice:2},{indice:1}];
 for(const f of ['SUM(A2:B2)','SUM(A:B)','INDIRECT("A2")','OFFSET(A2,0,1)','Otra!A2']){sh.C2.f=f;let mensaje='';try{organizacion.organizarHojaInforme(sh,orden);}catch(e){mensaje=e.message;}ok(mensaje.includes('fórmula')||mensaje.includes('referencias'));}
});
await test('el orden rechaza columnas repetidas, omitidas o desconocidas sin mutar el packing list',()=>{
 const f={encabezados:['ITEM','Cantidad'],columnas:{sku:0,cantidad:1}},orden=organizacion.columnasDeSalida(f).map(c=>c.id),antes=JSON.stringify(f);
 for(const ids of [orden.slice(1),[orden[0],...orden.slice(0,-1)],orden.map((v,i)=>i===0?'original:999':v)]){let fallo=false;try{organizacion.columnasDeSalida({...f,ordenSalida:ids});}catch{fallo=true;}ok(fallo);}
 eq(organizacion.columnasDeSalida({...f,ordenSalida:['invalido']},{ampliado:false}).map(c=>c.titulo),f.encabezados);eq(JSON.stringify(f),antes);
});
await test('OK Depot mantiene valor sin comentarios técnicos ni contaminar observaciones',()=>{
 const validacionDepot={notaMaestro:'No se adjunta la hoja MAESTRO.',metodo:'Catálogo sincronizado mediante la API de stock de Depot.',actualizadoEn:'2026-10-19T08:00:00Z',porSku:{
  S:{estado:'NO_ENCONTRADO',valor:'N/D',observacion:'Verificar en Depot; solicitar creación si corresponde antes de cargar cantidades.',nota:'No encontrado en catálogo; ausencia en stock no prueba inexistencia.',fuente:'CATALOGO',actualizadoEn:'2026-10-19T08:00:00Z'}}};
 const formato={hoja:'PACKING',encabezados:['ITEM','Cantidad','ok','OBSERVACION'],columnas:{sku:0,cantidad:1,depot:2,observacion:3}};
 const detalle=informe.completarIncidencias([{sku:'S',cantidad:2,fisica:2,diferencia:0,estado:'OK',observacion:'Nota del operario',cruda:['S',2,'#N/A','']}],[],{validacionDepot});
 const x=informe.construirLibro({recepcion:{codigo:'R'},validacionDepot,detalle,porOrigen:[{origen:'A',detalle,formato}],adicionales:[],eventos:[],auditoria:[]},{version:'envio-ampliado'}),w=XLSX.read(x.base64,{type:'base64'}),sh=w.Sheets.PACKING;
 eq(w.SheetNames,['PACKING']);ok(!w.SheetNames.includes('MAESTRO'));ok(!w.Props.Comments);
 const vista=informe.previsualizarLista({detalle,formato,validacionDepot},formato.columnas,{ampliado:true}),j=vista.encabezados.indexOf('ok'),obs=vista.encabezados.indexOf('OBSERVACION');
 eq(vista.filas[0].celdas[j].texto,'N/D');eq(vista.filas[0].celdas[j].comentario,'');
 ok(vista.filas[0].celdas[obs].texto.includes('Nota del operario'));ok(!vista.filas[0].celdas[obs].texto.includes('solicitar creación'));
 ok(!sh[XLSX.utils.encode_cell({r:0,c:j})].c);ok(!sh[XLSX.utils.encode_cell({r:1,c:j})].f);
});
await test('guardar destinos de salida no elimina la protección de las columnas de origen',async()=>{
 const anterior=globalThis.__coleccion;
 globalThis.__coleccion={'recepciones/R51/lineas':[{id:'l',linea:1,sku:'S',cantidad:2,cruda:['S',2]}],
  'recepciones/R51/skus':[{sku:'S',contado:2,esperado:2,pallets:{P01:2}}]};
 try{
  const datos=await informe.reunirInforme('R51',{codigo:'R51',formatos:{PRINCIPAL:{encabezados:['CLIENTE','Cantidad'],columnas:{sku:0,cantidad:1},salida:{}}}});
  const f=datos.porOrigen[0].formato;eq(f.columnas.sku,0);eq(f.columnas.cantidad,1);
  ok(organizacion.columnasDeSalida(f).some(c=>c.id==='resultado:cliente'));
  const vista=informe.previsualizarLista(datos.porOrigen[0],f.columnas,{ampliado:true});
  const origen=vista.columnas.findIndex(c=>c.id==='original:0');eq(vista.filas[0].celdas[origen].texto,'S');
 }finally{globalThis.__coleccion=anterior;}
});

await test('un packing list con dos embarques conserva sus filas y reparto revisado en dos Excel',async()=>{
 const antes={location:globalThis.location,fetch:globalThis.fetch};
 const lineas=[{id:'PRINCIPAL-1',linea:1,origen:'PRINCIPAL',sku:'S53',cantidad:3,embarque:'EMB-A',cruda:['S53',3,'EMB-A','',6],formulas:{4:'B2*2'}},{id:'PRINCIPAL-2',linea:2,origen:'PRINCIPAL',sku:'S53',cantidad:5,embarque:'EMB-B',cruda:['S53',5,'EMB-B','',10],formulas:{4:'B3*2'}}];
 const formato={encabezados:['ITEM','Cantidad','Embarque','Cantidad Física','Total'],columnas:{sku:0,cantidad:1,embarque:2,fisica:3}};
 const grupos=[{id:'GA',nombre:'EMB-A',packingLists:['PRINCIPAL']},{id:'GB',nombre:'EMB-B',packingLists:['PRINCIPAL']}];
 const meta={columnas:{},formatos:{PRINCIPAL:formato},agrupacionCorreos:{modo:'EMBARQUE',configuracion:{embarquesPorLinea:{}},grupos,resultados:grupos.map(g=>({grupo:g.id,origen:'PRINCIPAL',sku:'S53',contado:4,pallets:'B01',observacion:'De '+g.nombre,incidencias:[{tipo:'MAL_ESTADO',nombre:'Mal estado',cantidad:1,pnc:true}]}))}};
 globalThis.location={pathname:'/app/validar.html'};
 globalThis.fetch=async url=>{const k=String(url).split('/').at(-1),d=k==='informe-metadatos'?meta:k==='lineas'?lineas:k==='skus'?[{sku:'S53',contado:8,esperado:8,pallets:{B01:8},tienePnc:true,cantidadPnc:2}]:[];return new Response(JSON.stringify(d),{status:200});};
 try{
  const datos=await informe.reunirInforme('REVISION53',{codigo:'REVISION53',cliente:'VENTURA',creadoEn:'2026-10-16T12:00:00Z',formatos:{PRINCIPAL:formato}});
  const libros=informe.construirLibros(datos,{version:'envio-ampliado'});eq(libros.length,2);eq(libros.map(l=>l.grupo),['GA','GB']);eq(libros.map(l=>l.origen),['PRINCIPAL','PRINCIPAL']);
  for(let i=0;i<2;i++){const w=XLSX.read(libros[i].base64,{type:'base64'}),sh=w.Sheets[w.SheetNames[0]],t=XLSX.utils.sheet_to_json(sh,{header:1});eq(t.length,2);eq(t[1][t[0].indexOf('Cantidad Física')],4);eq(t[1][t[0].indexOf('Embarque')],grupos[i].nombre);eq(t[1][t[0].indexOf('Total')],i===0?6:10);ok(!Object.values(sh).some(c=>c&&c.f));ok(w.Props.Subject.includes(grupos[i].nombre));eq(datos.porGrupo[i].porOrigen[0].detalle[0].cantidadPnc,1);}
  eq(lineas[0].formulas[4],'B2*2');eq(lineas[1].cantidad,5);
 }finally{if(antes.location===undefined)delete globalThis.location;else globalThis.location=antes.location;globalThis.fetch=antes.fetch;}
});
await test('bitácora ISO y Firestore conserva fecha Ecuador; auditable no agrega AUDITORIA',()=>{
 const datos={recepcion:{codigo:'R55'},detalle:[],adicionales:[],eventos:[
  {sku:'S',cantidad:1,creadoEn:'2026-01-26T14:00:00Z'},
  {sku:'T',cantidad:1,creadoEn:{seconds:1769436000}},
  {sku:'U',cantidad:0}],auditoria:[{tipo:'NO_BORRAR_HISTORIAL'}]};
 const libro=informe.construirLibro(datos),w=XLSX.read(libro.base64,{type:'base64'});
 ok(!w.SheetNames.includes('AUDITORIA'));const rs=XLSX.utils.sheet_to_json(w.Sheets.BITACORA);
 ok(rs[0].FECHA.includes('2026')&&rs[0].FECHA.includes('9:00:00'));ok(rs[1].FECHA!=='');eq(rs[2].FECHA,'Fecha no registrada');eq(datos.auditoria.length,1);
});
await test('ADICIONALES excluye el sobrante ya declarado y conserva el enlace del adicional',()=>{
 const url='https://drive.google.com/drive/folders/adicional55',detalle=[{sku:'SKU',cantidad:3,fisica:4,diferencia:1,estado:'SOBRANTE',evidencia:'https://drive.google.com/drive/folders/pnc55',evidenciaSobrante:url,cruda:['SKU',3]}];
 for(const version of ['envio','envio-ampliado']){
  const f=informe.construirLibro({recepcion:{codigo:'R'},detalle,adicionales:[{sku:'EXTRA',descripcion:'No declarado',fisica:2,evidencia:url}],eventos:[]},{version});
  const w=XLSX.read(f.base64,{type:'base64'});eq(w.SheetNames,['VALIDADA','ADICIONALES']);const sh=w.Sheets.ADICIONALES,rs=XLSX.utils.sheet_to_json(sh);
  eq(rs.map(r=>r.TIPO),['ADICIONAL NO DECLARADO']);eq(rs.length,1);eq(rs[0].ITEM,'EXTRA');eq(rs[0]['CANTIDAD FISICA'],2);eq(rs[0].EVIDENCIAS,url);
  const cols=XLSX.utils.sheet_to_json(sh,{header:1})[0];eq(sh[XLSX.utils.encode_cell({r:1,c:cols.indexOf('EVIDENCIAS')})].l.Target,url);
 }
});
await test('dos embarques del mismo packing no cruzan enlaces ni adicional asignado',async()=>{
 const antes={location:globalThis.location,fetch:globalThis.fetch};
 const formato={encabezados:['ITEM','Cantidad','Embarque'],columnas:{sku:0,cantidad:1,embarque:2}},urls={A:'https://drive.google.com/drive/folders/embA',B:'https://drive.google.com/drive/folders/embB',X:'https://drive.google.com/drive/folders/extraA'};
 const lineas=['A','B'].map((e,i)=>({id:'PRINCIPAL-'+(i+1),linea:i+1,sku:'S',origen:'PRINCIPAL',cantidad:3,embarque:e,cruda:['S',3,e]}));
 const grupos=['A','B'].map(e=>({id:'G'+e,nombre:e,tipo:'EMBARQUE',packingLists:['PRINCIPAL']}));
 const meta={columnas:{},carpetas:{S:[urls.A,urls.B],X:[urls.X]},carpetasPorEmbarque:{A:{carpetas:{S:[urls.A],X:[urls.X]}},B:{carpetas:{S:[urls.B]}}},agrupacionCorreos:{modo:'EMBARQUE',configuracion:{embarquesPorLinea:{},asignaciones:{X:'GA'}},grupos,resultados:grupos.map(g=>({grupo:g.id,origen:'PRINCIPAL',sku:'S',contado:3,incidencias:[],observacion:'Solo '+g.nombre}))}};
 globalThis.location={pathname:'/app/validar.html'};
 globalThis.fetch=async url=>{const k=String(url).split('/').at(-1),d=k==='informe-metadatos'?meta:k==='lineas'?lineas:k==='skus'?[{sku:'S',contado:6,pallets:{}},{sku:'X',contado:2,porOrigen:{PRINCIPAL:{A01:2}},pallets:{A01:2}}]:k==='adicionales'?[{sku:'X',descripcion:'Adicional A',motivo:'Fuera de lista'}]:[];return new Response(JSON.stringify(d),{status:200});};
 try{
  const d=await informe.reunirInforme('R55',{codigo:'R55',formatos:{PRINCIPAL:formato}}),ls=informe.construirLibros(d,{version:'envio-ampliado'});
  const a=XLSX.read(ls[0].base64,{type:'base64'}),b=XLSX.read(ls[1].base64,{type:'base64'});
  const texto=w=>JSON.stringify(w.Sheets);ok(texto(a).includes(urls.A));ok(!texto(a).includes(urls.B));ok(texto(b).includes(urls.B));ok(!texto(b).includes(urls.A));ok(!texto(b).includes(urls.X));
  eq(XLSX.utils.sheet_to_json(a.Sheets.ADICIONALES)[0].ITEM,'X');ok(!b.SheetNames.includes('ADICIONALES'));
 }finally{if(antes.location===undefined)delete globalThis.location;else globalThis.location=antes.location;globalThis.fetch=antes.fetch;}
});

await test('un adicional contado en dos packing lists del mismo embarque se entrega una sola vez por cantidad',async()=>{
 const prev={location:globalThis.location,fetch:globalThis.fetch};
 const lineas=['P1','P2'].map(origen=>({id:origen+'-1',linea:1,origen,sku:origen,cantidad:1,embarque:'E',cruda:[origen,1]}));
 const formato={encabezados:['ITEM','Cantidad'],columnas:{sku:0,cantidad:1}};
 const eventos=[{id:'x1',tipo:'CONTEO',sku:'EXTRA',cantidad:2,origen:'P1',observacion:'Solo P1'},{id:'x2',tipo:'CONTEO',sku:'EXTRA',cantidad:3,origen:'P2',observacion:'Solo P2'}];
 const meta={columnas:{},agrupacionCorreos:{modo:'EMBARQUE',configuracion:{embarquesPorLinea:{},asignaciones:{EXTRA:'GE'}},grupos:[{id:'GE',tipo:'EMBARQUE',nombre:'E',packingLists:['P1','P2']}],resultados:lineas.map(l=>({grupo:'GE',origen:l.origen,sku:l.sku,contado:1,incidencias:[]}))}};
 globalThis.location={pathname:'/app/validar.html'};
 globalThis.fetch=async url=>{const k=String(url).split('/').at(-1),d=k==='informe-metadatos'?meta:k==='lineas'?lineas:k==='eventos'?eventos:k==='adicionales'?[{sku:'EXTRA'}]:k==='skus'?[...lineas.map(l=>({sku:l.sku,contado:1,pallets:{}})),{sku:'EXTRA',contado:5,pallets:{}}]:[];return new Response(JSON.stringify(d),{status:200});};
 try{const d=await informe.reunirInforme('R',{codigo:'R',formatos:{P1:formato,P2:formato}}),ls=informe.construirLibros(d,{version:'envio'});eq(ls.length,2);const rs=ls.map(l=>XLSX.utils.sheet_to_json(XLSX.read(l.base64,{type:'base64'}).Sheets.ADICIONALES)[0]);eq(rs.map(r=>r['CANTIDAD FISICA']),[2,3]);eq(rs.map(r=>r.OBSERVACION),['Solo P1','Solo P2']);}
 finally{if(prev.location===undefined)delete globalThis.location;else globalThis.location=prev.location;globalThis.fetch=prev.fetch;}
});

await test('recepción consolidada reúne dos packing lists y adicionales con su enlace en un solo libro',()=>{
 const url='https://drive.google.com/drive/folders/extra56';
 const listas=['P1','P2'].map((origen,i)=>({origen,detalle:[{sku:'SKU'+i,cantidad:2,fisica:2,diferencia:0,estado:'OK',origen,evidencia:'https://drive.google.com/drive/folders/'+origen}]}));
 const datos={recepcion:{codigo:'R56'},modoAgrupacion:'RECEPCION',porOrigen:listas,detalle:listas.flatMap(l=>l.detalle),adicionales:[{sku:'EXTRA56',fisica:3,grupo:'RECEPCION',evidencia:url}],eventos:[]};
 const libros=informe.construirLibros(datos,{version:'envio-ampliado'});eq(libros.length,1);eq(libros[0].grupo,'RECEPCION');
 const w=XLSX.read(libros[0].base64,{type:'base64'});eq(w.SheetNames,['P1','P2','ADICIONALES']);
 eq(XLSX.utils.sheet_to_json(w.Sheets.ADICIONALES)[0].EVIDENCIAS,url);ok(JSON.stringify(w.Sheets.P1).includes('SKU0'));ok(JSON.stringify(w.Sheets.P2).includes('SKU1'));ok(!JSON.stringify(w).includes('No se adjunta'));
});
await test('auditable muestra resumen de ambas listas y enlaces de adicionales sin hoja AUDITORIA',()=>{
 const listas=['PRINCIPAL','OTRA'].map((origen,i)=>({origen,detalle:[{sku:'S'+i,cantidad:i+1,fisica:i+1,diferencia:0,origen}]})),url='https://drive.google.com/drive/folders/adicional56';
 const w=XLSX.read(informe.construirLibro({recepcion:{codigo:'R',nombresListas:{PRINCIPAL:'PRINCIPAL - RAISZ04453'}},porOrigen:listas,detalle:listas.flatMap(l=>l.detalle),adicionales:[{sku:'X',fisica:1,evidencia:url}],eventos:[]},{version:'auditable'}).base64,{type:'base64'});
 ok(!w.SheetNames.includes('AUDITORIA'));eq(XLSX.utils.sheet_to_json(w.Sheets.RESUMEN).map(r=>r['PACKING LIST']),['PRINCIPAL - RAISZ04453','OTRA']);
 eq(XLSX.utils.sheet_to_json(w.Sheets.RESUMEN).map(r=>r.CONTADO),[1,2]);eq(XLSX.utils.sheet_to_json(w.Sheets.ADICIONALES)[0].EVIDENCIAS,url);
});

await test('cada archivo por embarque incluye solo sus contenedores y rangos',()=>{
 const contenedores=[{id:'C1',numero:'ABCU1234567',desde:'E01',hasta:'E60',total:60,posicion:'CALLEKL',embarques:['EMB-A']},{id:'C2',numero:'DEFU7654321',desde:'E61',hasta:'E96',total:36,posicion:'PISO',embarques:['EMB-B']}];
 const porGrupo=['EMB-A','EMB-B'].map((nombre,i)=>({id:'g'+i,nombre,porOrigen:[{origen:'PRINCIPAL',detalle:[{sku:'SKU'+i,cantidad:1,fisica:1,diferencia:0,embarque:nombre}]}]}));
 const libros=informe.construirLibros({recepcion:{codigo:'RECEPCION-57',cliente:'PRUEBA',informe:{sufijo:'_R0001'}},porGrupo,detalle:porGrupo.flatMap(g=>g.porOrigen[0].detalle),adicionales:[],eventos:[],contenedores},{version:'envio'});
 eq(libros.length,2);for(const [i,l] of libros.entries()){const w=XLSX.read(l.base64,{type:'base64'});const filas=XLSX.utils.sheet_to_json(w.Sheets.CONTENEDORES);eq(filas.length,1);eq(filas[0].CONTENEDOR,contenedores[i].numero);ok(l.nombre.startsWith('Validacion_PRUEBA_'));ok(l.nombre.endsWith('_R0001.xlsx'));}ok(libros[0].nombre!==libros[1].nombre);
});
await test('dos packing lists del mismo embarque conservan nombres distintos aunque el código se repita',()=>{
 const porOrigen=['PRINCIPAL','EMB-A'].map(origen=>({origen,detalle:[{sku:'X',cantidad:1,fisica:1,diferencia:0,embarque:'EMB-A'}]}));
 const libros=informe.construirLibros({recepcion:{codigo:'CLIENTE-EMB-A-19-10-2026',cliente:'PRUEBA',informe:{sufijo:'_R0001'}},porGrupo:[{id:'grupo',nombre:'EMB-A',porOrigen}],detalle:porOrigen.flatMap(l=>l.detalle),adicionales:[],eventos:[]},{version:'envio'});
 eq(new Set(libros.map(l=>l.nombre)).size,2);ok(libros.every(l=>l.nombre.length<100));ok(libros[0].nombre.includes('_PL01_'));
});
await test('REV incluye posición final sin mover columnas ni filas originales',()=>{
 const detalle=[{sku:'S1',cantidad:3,fisica:3,diferencia:0,estado:'OK',posicionReal:'BM-A-010-01',cruda:['S1',3]}];
 const f=informe.construirLibro({recepcion:{codigo:'R62'},detalle,porOrigen:[{origen:'PL',formato:{hoja:'REV',encabezados:['SKU','Cantidad'],columnas:{sku:0,cantidad:1}},detalle}],adicionales:[],eventos:[]},{version:'envio'});
 const w=XLSX.read(f.base64,{type:'base64'}),filas=XLSX.utils.sheet_to_json(w.Sheets.REV,{header:1});
 eq(filas,[['SKU','Cantidad','POSICION FINAL SUGERIDA'],['S1',3,'BM-A-010-01']]);
});
await test('CSV no interpreta como posición válida seis segmentos ni omite el último',()=>{
 const vacia={nave:'',calle:'',columna:'',nivel:'',profundidad:''};eq(csv.partesDePosicion('BM-A-10-1-X-Y'),vacia);
 eq(csv.partesDePosicion('BM-A-010-01'),{nave:'BM',calle:'A',columna:'010',nivel:'01',profundidad:''});
});
resumen();
