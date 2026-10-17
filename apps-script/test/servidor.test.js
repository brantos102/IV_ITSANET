#!/usr/bin/env node
// Ejecuta el puente real con servicios simulados: ninguna entrega ni correo real.
const fs = require('fs'), vm = require('vm'), crypto = require('crypto'), path = require('path');
let pasadas = 0, falladas = 0;
const test = (nombre, fn) => { try { fn(); pasadas++; } catch (e) { falladas++; console.log('FALLA '+nombre+': '+e.message); } };
const ok = (cond, msg='Condicion falsa') => { if (!cond) throw new Error(msg); };
const secreto = 'secreto-prueba-'.repeat(4);
function entorno() {
  let correos = 0, creados = 0, falloCorreo = false, sheets = 0,cuenta='supervisor@gmail.com';
  const archivos = new Map(), blobs = new Map(), propiedades=new Map(), registros=[];
  const carpeta = { getName:()=> 'Evidencias',getFilesByName(nombre) { const lista = archivos.has(nombre) ? [archivos.get(nombre)] : []; return { hasNext: () => !!lista.length, next: () => lista.shift() }; },
    createFile(blob) { creados++; const f = { getId: () => 'archivo-'+creados, getUrl: () => 'https://drive.google.com/file', setDescription() {},
      getBlob: () => ({ getDataAsString: () => String(blobs.get(f)), getBytes: () => Buffer.from(String(blobs.get(f))) }),
      setContent: (s) => blobs.set(f, s) };
      blobs.set(f, blob.datos); archivos.set(blob.nombre, f); return f; },
    getUrl: () => 'https://drive.google.com/folders/prueba'
  };
  const g = {
    ScriptApp:{AuthMode:{FULL:'FULL'},requireAllScopes(){}},
    Logger: {log:valor=>registros.push(String(valor))},
    Session:{getEffectiveUser:()=>({getEmail:()=>cuenta})},
    PROPS: { getProperty: (k) => k === 'SERVIDOR_HMAC' ? secreto : propiedades.get(k)||'', setProperty:(k,v)=>propiedades.set(k,v) },
    Utilities: { computeHmacSha256Signature: (p,s) => [...crypto.createHmac('sha256',s).update(p).digest()],
      newBlob: (datos,tipo,nombre) => ({datos,tipo,nombre}), base64Decode: s => Buffer.from(s,'base64'), base64Encode: b => Buffer.from(b).toString('base64') },
    LockService: { getScriptLock: () => ({waitLock(){},releaseLock(){}}) },
    DriveApp: { getFolderById: () => carpeta, getFileById: () => ({ moveTo() {}, getBlob: () => ({getBytes: () => Buffer.from('informe-prueba')}) }) },
    exigirCarpeta_: () => 'carpeta', carpetaDeRecepcion_: () => carpeta, carpetaDe_: () => carpeta,
    limpiarNombre_: s => s,
    MailApp: { getRemainingDailyQuota: () => 100,sendEmail(){correos++;if(falloCorreo)throw Error('Confirmación interrumpida');} },
    SpreadsheetApp: { create() { sheets++; const hoja = {clearContents(){},getMaxRows:()=>1000,getMaxColumns:()=>26,getRange:()=>({setValues(){}}),setFrozenRows(){}}; return {getId:()=> 'sheet-nuevo',getUrl:()=> 'https://docs.google.com/spreadsheets/d/nuevo',getSheetByName:()=>hoja,insertSheet:()=>hoja}; } },
    accionEnviarInforme_(_p, _u, antes) { if(antes)antes(); correos++; if (falloCorreo) throw new Error('Confirmacion interrumpida'); return {exito:true}; }
  };
  g.accionEnviarInforme_.versionServidor=2;
  g.PropertiesService={getScriptProperties:()=>g.PROPS};
  vm.createContext(g); vm.runInContext(fs.readFileSync(path.join(__dirname,'../proxy/Servidor.gs'),'utf8'),g);
  function peticion(operacion,clave,datos,fecha=Math.floor(Date.now()/1000)) {
    const payload=JSON.stringify({operacion,clave,datos:{usuario:'supervisor@gmail.com',...datos},fecha});
    return {payload,firma:crypto.createHmac('sha256',secreto).update(payload).digest('hex')};
  }
  return { g, peticion, registros:()=>registros.join('\n'), cambiarCuenta:v=>{cuenta=v;}, correos:()=>correos, creados:()=>creados, sheets:()=>sheets, romperCorreo:()=>{falloCorreo=true;} };
}
const id='a'.repeat(32), clave=id+':'+ 'b'.repeat(32);
test('rechaza firma falsa antes de escribir',()=>{ const e=entorno(); const p=e.peticion('archivo',clave,{}); p.firma='0'.repeat(64); let fallo=false; try {e.g.entregaServidor_(p);}catch{fallo=true;} ok(fallo);ok(e.creados()===0); });
test('rechaza cambios del payload',()=>{ const e=entorno(); const p=e.peticion('archivo',clave,{}); p.payload+=' '; let fallo=false; try {e.g.entregaServidor_(p);}catch{fallo=true;} ok(fallo); });
test('rechaza solicitudes caducadas',()=>{ const e=entorno(); let fallo=false;try {e.g.entregaServidor_(e.peticion('archivo',clave,{},1));}catch{fallo=true;}ok(fallo); });
test('firma no da acceso a otras acciones del WMS',()=>{ const e=entorno();let fallo=false;try{e.g.entregaServidor_(e.peticion('guardarCliente',id,{}));}catch{fallo=true;}ok(fallo); });
test('archivo repetido no crea dos copias',()=>{const e=entorno();const p=e.peticion('archivo',clave,{tipoArchivo:'foto',base64:'aG9sYQ==',nombre:'SKU.png',tipo:'image/png'});const a=e.g.entregaServidor_(p),b=e.g.entregaServidor_(p);ok(a.fileId===b.fileId);ok(e.creados()===1);});
test('correo confirmado no se repite y no usa Sheets',()=>{const e=entorno();const p=e.peticion('finalizar',id,{codigo:'PRUEBA',destinatarios:'ejecutivo@example.test',archivos:[]});ok(e.g.entregaServidor_(p).exito);ok(e.g.entregaServidor_(p).exito);ok(e.correos()===1);ok(e.sheets()===0);});
test('Proxy anterior bloquea correo y no anuncia capacidad verificada',()=>{const e=entorno();delete e.g.accionEnviarInforme_.versionServidor;const estado=e.g.entregaServidor_(e.peticion('estado',id,{}));ok(!estado.capacidades.includes('correoVerificado'));let fallo='';try{e.g.entregaServidor_(e.peticion('finalizar',id,{codigo:'PRUEBA',destinatarios:'destino@example.test',archivos:[]}));}catch(err){fallo=err.message;}ok(fallo.includes('Proxy.gs y Servidor.gs'));ok(e.correos()===0);});
test('confirmacion interrumpida requiere revision, no reenvio ciego',()=>{const e=entorno();e.romperCorreo();const p=e.peticion('finalizar',id,{codigo:'PRUEBA',destinatarios:'ejecutivo@example.test',archivos:[]});try{e.g.entregaServidor_(p);}catch{} const r=e.g.entregaServidor_(p);ok(r.revision);ok(e.correos()===1);});
test('sin destinatarios archiva sin correo ni Sheets',()=>{const e=entorno();ok(e.g.entregaServidor_(e.peticion('finalizar',id,{codigo:'PRUEBA',archivos:[]})).exito);ok(e.correos()===0);ok(e.sheets()===0);});
test('exportar texto no ejecuta formulas de hoja',()=>{const e=entorno();ok(e.g.celdaServidor_('=IMPORTXML("x")').startsWith("'="));ok(e.g.celdaServidor_(3)===3);});
test('Sheets solo se crea si se pide una exportacion expresa',()=>{const e=entorno(); const r=e.g.entregaServidor_(e.peticion('finalizar',id,{codigo:'PRUEBA',archivos:[],exportarSheet:true,skus:[{sku:'SKU1',contado:3}]}));ok(r.exito);ok(e.sheets()===1);ok(r.sheet.includes('nuevo'));ok(e.correos()===0);});
test('cuenta distinta del supervisor no escribe ni envia',()=>{const e=entorno();e.cambiarCuenta('otra@gmail.com');let fallo=false;try{e.g.entregaServidor_(e.peticion('finalizar',id,{destinatarios:'ejecutivo@example.test',archivos:[]}));}catch{fallo=true;}ok(fallo);ok(e.creados()===0);ok(e.correos()===0);});
test('probar puente verifica remitente y Drive sin crear ni enviar',()=>{const e=entorno();const r=e.g.entregaServidor_(e.peticion('estado',id,{}));ok(r.remitente==='supervisor@gmail.com');ok(e.creados()===0);ok(e.correos()===0);});
test('crear carpeta es una operación firmada independiente del correo',()=>{
  const e=entorno(),p=e.peticion('prepararCarpeta',id,{cliente:'VENTURA',marca:'VW',carpetaRecepcion:'PRUEBA'});
  const r=e.g.entregaServidor_(p);ok(r.exito && r.carpeta.includes('drive.google.com'));ok(r.remitente==='supervisor@gmail.com');
  ok(e.g.entregaServidor_(p).carpeta===r.carpeta);ok(e.correos()===0);
  const estado=e.g.entregaServidor_(e.peticion('estado',id,{}));ok(estado.capacidades.includes('prepararCarpeta'));
});
test('preparar recepción crea solo cliente, marca y recepción, sin categorías vacías',()=>{
 const e=entorno(),nombres=[];const anterior=e.g.carpetaDe_;
 e.g.carpetaDe_=(padre,n)=>{nombres.push(n);return anterior(padre,n);};
 const r=e.g.entregaServidor_(e.peticion('prepararCarpeta',id,{cliente:'VENTURA',marca:'VW',carpetaRecepcion:'REC'}));
 ok(r.exito);ok(JSON.stringify(nombres)===JSON.stringify(['VENTURA','VW','REC']));ok(e.correos()===0);
});
test('miniaturas priorizan panorámicas y estado final y acotan el peso',()=>{
  const e=entorno();e.g.DriveApp.getFileById=()=>({getThumbnail:()=>({getBytes:()=>Buffer.alloc(1024),getContentType:()=> 'image/jpeg'})});
  const fotos=e.g.fotosCorreoServidor_([{fileId:'detalle',tipoArchivo:'foto'},{fileId:'final',tipoArchivo:'foto'},{fileId:'panorama',tipoArchivo:'foto'}],
    [{fileId:'final',ruta:['RECEPCION','ESTADO_FINAL']},{fileId:'panorama',ruta:['RECEPCION','PANORAMICA']}]);
  ok(fotos[0].etiqueta==='PANORAMICA' && fotos[1].etiqueta==='ESTADO FINAL');ok(fotos.every(f=>!!f.blob));
  e.g.DriveApp.getFileById=()=>({getThumbnail:()=>({getBytes:()=>Buffer.alloc(300000),getContentType:()=> 'image/jpeg'})});
  ok(!e.g.fotosCorreoServidor_([{fileId:'grande',tipoArchivo:'foto'}],[])[0].blob);
});
test('prueba de correo autorizada se envía una vez por referencia',()=>{const e=entorno(),p=e.peticion('pruebaCorreo',id,{destinatario:'destino@example.test'});ok(e.g.entregaServidor_(p).remitente==='supervisor@gmail.com');ok(e.g.entregaServidor_(p).exito);ok(e.correos()===1);});
test('prueba interrumpida no reenvía sin revisión',()=>{const e=entorno();e.romperCorreo();const p=e.peticion('pruebaCorreo',id,{destinatario:'destino@example.test'});try{e.g.entregaServidor_(p);}catch{}ok(e.g.entregaServidor_(p).revision);ok(e.correos()===1);});
test('reutilizar referencia para otro correo se rechaza',()=>{const e=entorno();e.g.entregaServidor_(e.peticion('pruebaCorreo',id,{destinatario:'uno@example.test'}));let fallo=false;try{e.g.entregaServidor_(e.peticion('pruebaCorreo',id,{destinatario:'dos@example.test'}));}catch{fallo=true;}ok(fallo);ok(e.correos()===1);});
test('diagnóstico del editor comprueba cuenta, carpeta y correo sin revelar HMAC ni escribir',()=>{
  const e=entorno();e.g.PROPS.setProperty('CARPETA_EVIDENCIAS','https://drive.google.com/drive/folders/carpeta-prueba-1234567890?usp=sharing');
  const abrir=e.g.DriveApp.getFolderById;let consultada='';e.g.DriveApp.getFolderById=id=>{consultada=id;return abrir(id);};
  e.g.verificarGoogleServidor();ok(consultada==='carpeta-prueba-1234567890');ok(e.registros().includes('supervisor@gmail.com'));
  ok(e.registros().includes('CUOTA DE CORREO DISPONIBLE: 100'));ok(!e.registros().includes(secreto));ok(e.correos()===0);ok(e.creados()===0);ok(e.sheets()===0);
});
test('diagnóstico solicita consentimiento completo antes de consultar cuenta o secretos',()=>{
  const e=entorno();let llamadas=0,modo='';
  e.g.ScriptApp.requireAllScopes=m=>{modo=m;throw Error('Consentimiento pendiente');};
  e.g.Session.getEffectiveUser=()=>{llamadas++;throw Error('No debe consultar identidad');};
  e.g.PropertiesService.getScriptProperties=()=>{llamadas++;throw Error('No debe leer propiedades');};
  let fallo='';try{e.g.verificarGoogleServidor();}catch(err){fallo=err.message;}
  ok(fallo==='Consentimiento pendiente');ok(modo==='FULL');ok(llamadas===0);ok(e.correos()===0);ok(e.creados()===0);
});
test('diagnóstico identifica la falta de carpeta antes de consultar Drive',()=>{
  const e=entorno();let fallo='';e.g.DriveApp.getFolderById=()=>{throw Error('No debería llamarse');};
  try{e.g.verificarGoogleServidor();}catch(err){fallo=err.message;}ok(fallo.startsWith('CARPETA DRIVE: configura CARPETA_EVIDENCIAS'));
});
test('diagnóstico conserva la causa de acceso a Drive sin enviar correos',()=>{
  const e=entorno();e.g.PROPS.setProperty('CARPETA_EVIDENCIAS','carpeta-prueba-1234567890');e.g.DriveApp.getFolderById=()=>{throw Error('Authorization required');};
  let fallo='';try{e.g.verificarGoogleServidor();}catch(err){fallo=err.message;}ok(fallo==='CARPETA DRIVE: Authorization required');ok(e.correos()===0);
});
test('diagnóstico distingue permiso de correo y cuenta no disponible',()=>{
  const e=entorno();e.g.PROPS.setProperty('CARPETA_EVIDENCIAS','carpeta-prueba-1234567890');e.g.MailApp.getRemainingDailyQuota=()=>{throw Error('Authorization required');};
  let fallo='';try{e.g.verificarGoogleServidor();}catch(err){fallo=err.message;}ok(fallo==='PERMISO DE CORREO: Authorization required');
  e.cambiarCuenta('');try{e.g.verificarGoogleServidor();}catch(err){fallo=err.message;}ok(fallo.startsWith('CUENTA GOOGLE:'));ok(e.correos()===0);
});
console.log(`${pasadas} pasadas, ${falladas} falladas`); process.exitCode=falladas?1:0;
