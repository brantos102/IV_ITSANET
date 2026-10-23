import {createRequire} from 'node:module';
import {cargar,test,eq,ok,resumen} from './cargador.mjs';
const require=createRequire(import.meta.url);globalThis.XLSX=require('xlsx');
const informe=await cargar('informe.js'),datos=await cargar('datos.js'),csv=await cargar('csv.js'),excel=await cargar('excel-formato.js');
const base=(detalle,formato)=>({recepcion:{codigo:'PRUEBA65',cliente:'PRUEBA'},detalle,porOrigen:[{origen:'PL',detalle,formato}],adicionales:[],eventos:[]});
const libro=(d,f,version='envio')=>XLSX.read(informe.construirLibro(base(d,f),{version}).base64,{type:'base64',cellNF:true,bookFiles:true});
const lanza=(fn,texto)=>{let e;try{fn();}catch(x){e=x;}ok(e&&e.message.includes(texto),'Debe detener con diagnóstico: '+texto);};

await test('65: cantidades e importes de registros existentes son números; identificadores conservan ceros',()=>{
 const formato={hoja:'REV',encabezados:['ITEM','Factura','Cantidad','PrecioUnit','PrecioTotal','Cantidad Física','Diferencia','PALLET','CODIGO DE BARRAS'],columnas:{sku:0,cantidad:2,fisica:5,desface:6,pallet:7,codigoBarra:8}};
 const filas=[{sku:'00001234',cantidad:12.5,precioUnit:3.9,precioTotal:48.75,fisica:12,diferencia:-0.5,palletsSimple:'001',codigoBarra:'000123456789',cruda:['00001234','00000999','12.5','3.9','48.75','','','','']}],antes=JSON.stringify(filas);
 const sh=libro(filas,formato).Sheets.REV;
 for(const [dir,n] of [['C2',12.5],['D2',3.9],['E2',48.75],['F2',12],['G2',-0.5]]){eq(sh[dir].t,'n');eq(sh[dir].v,n);ok(sh[dir].z!=='@');}
 for(const [dir,s] of [['A2','00001234'],['B2','00000999'],['H2','001'],['I2','000123456789']]){eq(sh[dir].t,'s');eq(sh[dir].v,s);}
 eq(sh.C2.v+sh.G2.v,sh.F2.v);eq(JSON.stringify(filas),antes);eq(XLSX.SSF.format(sh.D2.z,sh.D2.v),'3.90');
});

await test('65: lectura nueva conserva tipos y formatos de fecha, importes y números desconocidos',()=>{
 const w=XLSX.utils.book_new(),sh=XLSX.utils.aoa_to_sheet([['SKU','Cantidad','PrecioUnit','PrecioTotal','Peso','Fecha','Factura'],[1234,2.125,1.234,0,0.625,46317,999]]);
 sh.A2.z='000000';sh.C2.z='0.000';sh.D2.z='0.00';sh.E2.z='0.000';sh.F2.z='dd/mm/yyyy';XLSX.utils.book_append_sheet(w,sh,'PL');
 const entrada=datos.leerPackingList(XLSX.write(w,{type:'array',bookType:'xlsx'})),linea=entrada.lineas[0];
 eq(linea.sku,'001234');eq(linea.tiposCelda[4],'n');eq(linea.formatosCelda[5],'dd/mm/yyyy');
 const detalle=[{...linea,fisica:2.125,diferencia:0,estado:'OK'}],salida=libro(detalle,{hoja:'REV',encabezados:entrada.encabezados,columnas:entrada.columnas}).Sheets.REV;
 eq(salida.A2.v,'001234');eq(salida.A2.t,'s');eq(salida.G2.v,'999');eq(salida.G2.t,'s');
 for(const [dir,n] of [['B2',2.125],['C2',1.234],['D2',0],['E2',0.625],['F2',46317]]){eq(salida[dir].t,'n');eq(salida[dir].v,n);}
 eq(salida.C2.z,'0.000');eq(salida.F2.z,'dd/mm/yyyy');
});

await test('65: valores localizados se convierten completos y no se extraen dígitos de texto libre',()=>{
 for(const [v,n] of [['1.234,50',1234.5],['$ 1,234.50',1234.5],['(USD 12.50)',-12.5],['-2,50',-2.5],['1,234,567',1234567]])eq(excel.numeroParaExcel(v),n);
 for(const v of ['SKU12','2 cajas','12.3.45','1,23,456','NaN','Infinity'])ok(Number.isNaN(excel.numeroParaExcel(v)));
 eq(excel.numeroParaExcel('1.234',{originalNumerico:true}),1.234);
 for(const n of [0,4,0.125,1.234,1234.56])ok(!XLSX.SSF.format(excel.formatoDeNumero(n),n).endsWith('.'));
});

await test('65: fórmula financiera conserva fórmula y caché numérica calculable',()=>{
 const f={hoja:'REV',encabezados:['SKU','Cantidad','PrecioUnit','PrecioTotal'],columnas:{sku:0,cantidad:1}};
 const d=[{sku:'S',cantidad:2,precioUnit:1.234,precioTotal:2.468,fisica:2,diferencia:0,cruda:['S','2','1.234','2.468'],formulas:{3:'B2*C2'}}];
 const sh=libro(d,f).Sheets.REV;eq(sh.D2.t,'n');eq(sh.D2.v,2.468);eq(sh.D2.f,'B2*C2');eq(sh.C2.v,1.234);
});

await test('65: bloquea NaN y caracteres XML ilegales antes de emitir un libro reparable',()=>{
 const f={hoja:'REV',encabezados:['SKU','Cantidad','Cantidad Física'],columnas:{sku:0,cantidad:1,fisica:2}};
 const d={sku:'S',cantidad:2,fisica:NaN,diferencia:0,cruda:['S','2','']};
 lanza(()=>libro([d],f),'número inválido');
 lanza(()=>libro([{...d,fisica:2,cruda:['S\uffff','2','']}],f),'carácter no válido');
 lanza(()=>informe.construirLibro({...base([{...d,fisica:2}],f),recepcion:{codigo:'R\uffff'}},{version:'envio'}),'carácter no válido');
 const valido=libro([{...d,fisica:2,cruda:['S🙂','2','']}],f);eq(valido.Sheets.REV.A2.v,'S🙂');
});

await test('65: hojas distinguidas solo por mayúsculas y títulos largos salen con nombres Excel únicos',()=>{
 const detalle=[{sku:'S',cantidad:1,fisica:1,diferencia:0,cruda:['S','1']}],f={encabezados:['SKU','Cantidad'],columnas:{sku:0,cantidad:1}};
 const origenes=['Lista','LISTA','BITACORA','RESUMEN','ADICIONALES','1234567890123456789012345678901A','1234567890123456789012345678901B'];
 const r=informe.construirLibro({...base(detalle,f),porOrigen:origenes.map(origen=>({origen,formato:f,detalle}))},{version:'auditable'});
 const w=XLSX.read(r.base64,{type:'base64',bookFiles:true});eq(new Set(w.SheetNames.map(n=>n.toUpperCase())).size,w.SheetNames.length);ok(w.SheetNames.every(n=>n.length<=31));
 ok(w.SheetNames.includes('LISTA 2'));ok(w.SheetNames.includes('BITACORA 2'));
});

await test('65: apóstrofo de nombre de hoja no rompe la referencia OOXML del autofiltro',()=>{
 const f={hoja:"O'Brien",encabezados:['SKU','Cantidad'],columnas:{sku:0,cantidad:1}},d=[{sku:'S',cantidad:2,fisica:2,diferencia:0,cruda:['S','2']}];
 const w=libro(d,f);eq(w.SheetNames[0],'O’Brien');
 const xml=Buffer.from(w.files['xl/workbook.xml'].content).toString();ok(xml.includes('O’Brien'));ok(!xml.includes("'O'Brien'!"));
 const refs=w.Workbook.Names.filter(n=>n.Name==='_xlnm._FilterDatabase');ok(refs.some(n=>n.Ref==="'O’Brien'!A1:B2"));
});

await test('65: modelo Excel de Depot tipa cantidad y mantiene códigos, posiciones y fechas como texto',()=>{
 const f={archivo:'modelo65',separador:',',columnas:[{encabezado:'SKU',campo:'sku',tipo:'Alfanumérico'},{encabezado:'Cantidad',campo:'cantidad',tipo:'Numérico'},{encabezado:'Fecha',campo:'fecha',tipo:'Date'},{encabezado:'Columna',campo:'columna',tipo:'Numerico'}]};
 const r=csv.resultadoModelo(f,[['00001234','2.125','01012027','010']],'R'),antes=JSON.stringify(r);
 const sh=csv.libroModelo(r).Sheets['Modelo a Utilizar'];eq(sh.B2.t,'n');eq(sh.B2.v,2.125);eq(sh.A2.v,'00001234');eq(sh.C2.v,'01012027');eq(sh.D2.v,'010');eq(sh.D2.t,'s');eq(JSON.stringify(r),antes);
});

resumen();
