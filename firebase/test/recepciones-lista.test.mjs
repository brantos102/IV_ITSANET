import {cargar,test,eq,ok,resumen} from './cargador.mjs';
const {registroRecepcion,filtrarRecepciones}=await cargar('recepciones-lista.js');
const filas=[
 {codigo:'R2',cliente:'VENTURA',estado:'CERRADA',creadoEn:'2026-10-23T04:59:59Z',descripcion:'Consolidación VW',origenes:['RB63196']},
 {codigo:'R1',cliente:'GAC',estado:'EN_VALIDACION',creadoEn:'2026-10-23T05:00:00Z'},
 {codigo:'R3',cliente:'VENTURA',estado:'ABIERTA',creadoEn:{seconds:Date.parse('2026-10-24T04:59:59Z')/1000}},
 {codigo:'R0',cliente:'VENTURA',estado:'ABIERTA',creadoEn:null},
];
await test('registro usa Ecuador aunque cambie la zona del dispositivo',()=>{
 eq(registroRecepcion(filas[0].creadoEn).dia,'2026-10-22');
 eq(registroRecepcion(filas[1].creadoEn).dia,'2026-10-23');
 eq(registroRecepcion(filas[1].creadoEn).hora,'00:00');
 eq(registroRecepcion(filas[3].creadoEn).iso,'');
 eq(registroRecepcion('no-fecha').fecha,'Sin fecha registrada');
});
await test('rango incluye la jornada completa y admite Timestamp de Firestore',()=>{
 eq(filtrarRecepciones(filas,{desde:'2026-10-23',hasta:'2026-10-23'}).map(r=>r.codigo),['R3','R1']);
 eq(filtrarRecepciones(filas,{hasta:'2026-10-22'}).map(r=>r.codigo),['R2']);
});
await test('nombre, estado y fechas se combinan sin alterar registros',()=>{
 const copia=JSON.stringify(filas);
 eq(filtrarRecepciones(filas,{texto:'ventura',estado:'ABIERTA',desde:'2026-10-23'}).map(r=>r.codigo),['R3']);
 eq(filtrarRecepciones(filas,{texto:'consolidacion'}).map(r=>r.codigo),['R2']);
 eq(filtrarRecepciones(filas,{texto:'rb63196'}).map(r=>r.codigo),['R2']);
 eq(JSON.stringify(filas),copia);
});
await test('ordenar conserva los registros sin fecha al final y rechaza rangos invertidos',()=>{
 eq(filtrarRecepciones(filas,{orden:'ANTIGUAS'}).map(r=>r.codigo),['R2','R1','R3','R0']);
 eq(filtrarRecepciones(filas,{orden:'CODIGO'}).map(r=>r.codigo),['R0','R1','R2','R3']);
 let fallo=false;try{filtrarRecepciones(filas,{desde:'2026-10-24',hasta:'2026-10-23'});}catch(e){fallo=e.message.includes('Desde');}ok(fallo);
});
resumen();
