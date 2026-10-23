import {createRequire} from 'node:module';
import {cargar,test,eq,ok,resumen} from './cargador.mjs';
const require=createRequire(import.meta.url);globalThis.XLSX=require('xlsx');
const informe=await cargar('informe.js'),salida=await cargar('ubicaciones-informe.js'),orden=await cargar('orden-informe.js');
const titulo=salida.COLUMNA_DETALLE_UNIDADES;
const encabezados=['ITEM','Descripción','ReferenciaPedido','Factura','Cantidad','PrecioUnit','PrecioTotal','CONTENEDOR','Embarque','Cantidad Física','Validación','PALLET','CODIGO BARRA','COD/PROD','OBSERVACION','ok','POSICION FINAL SUGERIDA'];
const formato={hoja:'REV',encabezados,columnas:{sku:0,cantidad:4,fisica:9,validacion:10,pallet:11,observacion:14,posicion:16}};
const fila=(extra={})=>({sku:'00001234',origen:'PL',linea:128,filaOriginal:128,cantidad:50,fisica:30,diferencia:-20,estado:'FALTANTE',cruda:['00001234','Producto','REF001','00009',50,16.15,807.5,'HAMU1329459','RB56223','','','','','','','ok',''],...extra});
const eventos=[{id:'e64',tipo:'CONTEO',sku:'00001234',origen:'PL',cantidad:20,pallet:'G64',posicionReal:'BM-Q-10-5',incidencias:[{tipo:'MAL_ESTADO',nombre:'Rotura',cantidad:2,pnc:true}]},{id:'e68',tipo:'CONTEO',sku:'00001234',origen:'PL',cantidad:10,pallet:'G68',posicionReal:'BM-Q-10-6'}];
const base=(detalle,f=formato,es=eventos)=>({recepcion:{codigo:'DEMO68',cliente:'PRUEBA'},detalle,porOrigen:[{origen:'PL',formato:f,detalle}],eventos:es,adicionales:[]});
const generar=(b,version='envio')=>XLSX.read(informe.construirLibro(b,{version}).base64,{type:'base64',cellNF:true,bookFiles:true});
const detalle=informe.completarIncidencias(informe.completarRegistrosPorLista([fila()],eventos),eventos);

await test('68: caso G64-G68 mantiene A:Q y agrega una columna final sin cantidades en L/Q',()=>{
 const antes=JSON.stringify(detalle),w=generar(base(detalle)),sh=w.Sheets.REV,matriz=XLSX.utils.sheet_to_json(sh,{header:1,defval:''});
 eq(matriz[0],[...encabezados,titulo]);eq(matriz.length,2);eq(sh.L2.v,'G64-G68');eq(sh.Q2.v,'BM-Q-10-5-BM-Q-10-6');
 for(const dir of ['L2','Q2']){eq(sh[dir].t,'s');ok(/^[A-Za-z0-9.-]+$/.test(sh[dir].v));}
 eq(sh.E2.v,50);eq(sh.J2.v,30);eq(sh.F2.v,16.15);eq(sh.G2.v,807.5);eq(sh.A2.v,'00001234');eq(sh.D2.v,'00009');
 for(const dir of ['E2','F2','G2','J2'])eq(sh[dir].t,'n');
 ok(sh.R2.v.includes('Conformes: 28 u. · PNC: 2 u.'));
 for(const texto of ['2 u. PNC · Pallet G64 · Posición BM-Q-10-5 · Rotura','18 u. CONFORME · Pallet G64','10 u. CONFORME · Pallet G68'])ok(sh.R2.v.includes(texto),texto);
 eq(sh['!autofilter'].ref,'A1:R2');eq(JSON.stringify(detalle),antes);
 eq(XLSX.utils.sheet_to_json(w.Sheets.UBICACIONES).map(p=>p['CANTIDAD ASIGNADA']),[2,18,10]);
});

await test('68: auditoría conserva los desgloses y no recibe la nueva columna del ejecutivo',()=>{
 const w=generar(base(detalle),'auditable'),sh=w.Sheets.VALIDADA;
 eq(sh.L2.v,'G64 (20 u.) / G68 (10 u.)');eq(sh.Q2.v,'BM-Q-10-5 (20 u.) / BM-Q-10-6 (10 u.)');
 ok(!XLSX.utils.sheet_to_json(sh,{header:1})[0].includes(titulo));
 const det=XLSX.utils.sheet_to_json(w.Sheets['VALIDADA DET'])[0];eq(det['UNIDADES PNC'],2);ok(det['DESGLOSE PALLET → POSICION'].includes('20 u. · G64'));
});

await test('68: ampliado organizado mantiene el orden guardado y siempre agrega el detalle al final',()=>{
 const f={...formato},cols=orden.columnasDeSalida(f);f.ordenSalida=cols.map(c=>c.id).reverse();
 const w=generar(base(detalle,f),'envio-ampliado'),sh=w.Sheets.REV,t=XLSX.utils.sheet_to_json(sh,{header:1});
 eq(t[0].slice(0,-1),cols.map(c=>c.titulo).reverse());eq(t[0].at(-1),titulo);
 eq(t[1][t[0].indexOf('PALLET')],'G64-G68');eq(t[1][t[0].indexOf('POSICION FINAL SUGERIDA')],'BM-Q-10-5-BM-Q-10-6');
 eq(f.ordenSalida,cols.map(c=>c.id).reverse());
});

await test('68: filas repetidas y listas diferentes conservan sus propias cantidades y PNC',()=>{
 const es=[{id:'a',sku:'00001234',origen:'PL',cantidad:6,pallet:'A01',posicionReal:'BM-A-10-1',incidencias:[{tipo:'MAL_ESTADO',cantidad:2,pnc:true}]},{id:'b',sku:'00001234',origen:'PL',cantidad:4,pallet:'A02',posicionReal:'BM-B-20-2'},{id:'c',sku:'00001234',origen:'OTRA',cantidad:3,pallet:'Z09',posicionReal:'BM-Z-10-1',estadoFisico:'PNC'}];
 const d=informe.completarRegistrosPorLista([fila({linea:1,cantidad:6,fisica:6}),fila({linea:2,cantidad:4,fisica:4}),fila({linea:3,origen:'OTRA',cantidad:3,fisica:3})],es);
 const w=generar({...base(d,formato,es),porOrigen:[{origen:'PL',formato,detalle:d.slice(0,2)},{origen:'OTRA',formato:{...formato,hoja:'OTRA'},detalle:d.slice(2)}]});
 const a=XLSX.utils.sheet_to_json(w.Sheets.REV),b=XLSX.utils.sheet_to_json(w.Sheets.OTRA);
 eq(a.map(f=>f.PALLET),['A01','A02']);eq(b[0].PALLET,'Z09');ok(a[0][titulo].includes('PNC: 2 u.'));ok(a[1][titulo].includes('PNC: 0 u.'));
 ok(!a[0][titulo].includes('A02'));ok(!a[1][titulo].includes('A01'));ok(!a.some(f=>f[titulo].includes('Z09')));ok(b[0][titulo].includes('3 u. PNC · Pallet Z09'));
});

await test('68: ceros, puntos, guiones y pallets repetidos conservan identificadores sin duplicados',()=>{
 const registros=[{cantidad:2,pallet:'G04.1',posicionReal:'BM-A-010-01',estado:'PNC',pnc:true},{cantidad:3,pallet:'G04.1',posicionReal:'BM-A-010-01',estado:'CONFORME'},{cantidad:1,pallet:'G-05',posicionReal:'BM-A-011-01',estado:'CONFORME'}];
 const f=salida.filaParaEjecutivo(fila({fisica:6,registrosAsignados:registros}));eq(f.palletsSimple,'G04.1-G-05');eq(f.posicionReal,'BM-A-010-01-BM-A-011-01');ok(f.detalleUnidadesEjecutivo.includes('PNC: 2 u.'));
});

await test('68: IDs con caracteres inválidos detienen el ejecutivo con diagnóstico; auditoría sigue accesible',()=>{
 for(const campo of ['pallet','posicionReal'])for(const valor of ['G64/G68','G_64','G64:1','G64 (2 u.)','G64,','G64+1']){
  const d=informe.completarRegistrosPorLista([fila({fisica:1})],[{id:'malo',sku:'00001234',origen:'PL',cantidad:1,pallet:'G64',posicionReal:'BM-A-10-1',[campo]:valor}]);
  for(const version of ['envio','envio-ampliado']){let error;try{generar(base(d),version);}catch(e){error=e;}ok(error?.message.includes('00001234')&&error.message.includes('Corrige el registro'),valor);}
  ok(generar(base(d),'auditable').SheetNames.includes('BITACORA'));
 }
});

await test('68: compatibilidad con agregados antiguos limpia solo el formato conocido y no inventa PNC por pallet',()=>{
 const f=salida.filaParaEjecutivo(fila({palletsSimple:'G64 (20 u.) / G68 (10 u.)',posicionReal:'BM-Q-10-5 (20 u.) / BM-Q-10-6 (10 u.)',cantidadPnc:2}));
 eq(f.palletsSimple,'G64-G68');eq(f.posicionReal,'BM-Q-10-5-BM-Q-10-6');ok(f.detalleUnidadesEjecutivo.includes('PNC: 2 u.'));ok(f.detalleUnidadesEjecutivo.includes('por revisar'));ok(!f.detalleUnidadesEjecutivo.includes('PNC · Pallet G64'));
 eq(salida.filaParaEjecutivo(fila({pallets:'G01(2)-G02.1(3)'})).palletsSimple,'G01-G02.1');
});

await test('68: falta de registros vinculados no rellena otra fila con los pallets globales del SKU',()=>{
 const d=informe.completarRegistrosPorLista([fila()],[{id:'otro',sku:'00001234',origen:'OTRA',cantidad:30,pallet:'G99'}]);
 const w=generar(base(d)),r=XLSX.utils.sheet_to_json(w.Sheets.REV)[0];eq(r.PALLET,'');eq(r['POSICION FINAL SUGERIDA'],'');ok(r[titulo].includes('30 u. POR REVISAR'));ok(!r[titulo].includes('G99'));
});

await test('68: correcciones y anulaciones excluyen cantidades y destinos retirados del ejecutivo',()=>{
 const es=[...eventos,{id:'q',tipo:'CALIDAD',eventoId:'e64',incidencias:[{tipo:'MAL_ESTADO',cantidad:1,pnc:true}]},{id:'x',tipo:'ANULACION',anulaA:'e68'}];
 const d=informe.completarRegistrosPorLista([fila({fisica:20})],es),r=XLSX.utils.sheet_to_json(generar(base(d,formato,es)).Sheets.REV)[0];
 eq(r.PALLET,'G64');ok(r[titulo].includes('PNC: 1 u.'));ok(!r[titulo].includes('G68'));ok(!r[titulo].includes('BM-Q-10-6'));
});

await test('68: vista previa coincide con la hoja final, incluidos prefijo, posición añadida y columna final',()=>{
 for(const ampliado of [false,true]){
  const f={...formato,prefijo:[{celdas:['Recepción de prueba']}],encabezados:encabezados.slice(0,-1),columnas:{...formato.columnas}};delete f.columnas.posicion;
  const b=base(detalle,f),prev=informe.previsualizarLista(b.porOrigen[0],f.columnas,{ampliado}),w=generar(b,ampliado?'envio-ampliado':'envio'),sh=w.Sheets.REV;
  const t=XLSX.utils.sheet_to_json(sh,{header:1,defval:''});eq(prev.encabezados,t[1]);eq(prev.columnas.length,t[1].length);eq(prev.filas[0].numero,3);
  eq(prev.filas[0].celdas.map(c=>c.texto),t[2].map(v=>String(v)));eq(prev.encabezados.at(-1),titulo);
 }
});

await test('68: recepciones sin formato y adicionales mantienen pallets limpios y detalle de auditoría',()=>{
 const b={...base(detalle),porOrigen:[],adicionales:[{sku:'EXTRA',fisica:2,pallets:'G01(1)-G02.1(1)'}]};
 const w=generar(b),r=XLSX.utils.sheet_to_json(w.Sheets.VALIDADA)[0];eq(r.PALLET,'G64-G68');eq(r['POSICION REAL ASIGNADA'],'BM-Q-10-5-BM-Q-10-6');ok(r[titulo].includes('2 u. PNC'));
 eq(XLSX.utils.sheet_to_json(w.Sheets.ADICIONALES)[0].PALLET,'G01-G02.1');
 eq(XLSX.utils.sheet_to_json(generar(b,'auditable').Sheets.ADICIONALES)[0].PALLET,'G01(1)-G02.1(1)');
});

await test('68: PNC histórica sin cantidad no se presenta como cero ni como mercadería conforme',()=>{
 const d=informe.completarIncidencias(informe.completarRegistrosPorLista([fila({fisica:3,calidadPorRevisar:true})],[{id:'viejo',sku:'00001234',origen:'PL',cantidad:3,pallet:'G64'}]),[]);
 const r=XLSX.utils.sheet_to_json(generar(base(d)).Sheets.REV)[0];eq(r.PALLET,'G64');ok(r[titulo].includes('PNC y conformes: cantidades por revisar'));ok(r[titulo].includes('3 u. CONDICIÓN POR REVISAR'));ok(!r[titulo].includes('PNC: 0'));ok(!r[titulo].includes('3 u. CONFORME'));
});

await test('68: un desglose inconsistente no se publica como cantidad física válida',()=>{
 let error;try{salida.filaParaEjecutivo(fila({fisica:3,registrosAsignados:[{cantidad:2,pallet:'G64',estado:'CONFORME'}]}));}catch(e){error=e;}
 ok(error?.message.includes('no coincide con la cantidad física'));
});

resumen();
