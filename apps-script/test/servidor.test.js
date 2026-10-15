#!/usr/bin/env node
// Ejecuta el puente real con servicios simulados: ninguna entrega ni correo real.
const fs = require('fs'), vm = require('vm'), crypto = require('crypto'), path = require('path');
let pasadas = 0, falladas = 0;
const test = (nombre, fn) => { try { fn(); pasadas++; } catch (e) { falladas++; console.log('FALLA '+nombre+': '+e.message); } };
const ok = (cond, msg='Condicion falsa') => { if (!cond) throw new Error(msg); };
const secreto = 'secreto-prueba-'.repeat(4);
function entorno() {
  let correos = 0, creados = 0, falloCorreo = false, sheets = 0,cuenta='supervisor@gmail.com';
  const archivos = new Map(), blobs = new Map();
  const carpeta = { getName:()=> 'Evidencias',getFilesByName(nombre) { const lista = archivos.has(nombre) ? [archivos.get(nombre)] : []; return { hasNext: () => !!lista.length, next: () => lista.shift() }; },
    createFile(blob) { creados++; const f = { getId: () => 'archivo-'+creados, getUrl: () => 'https://drive.google.com/file', setDescription() {},
      getBlob: () => ({ getDataAsString: () => String(blobs.get(f)), getBytes: () => Buffer.from(String(blobs.get(f))) }),
      setContent: (s) => blobs.set(f, s) };
      blobs.set(f, blob.datos); archivos.set(blob.nombre, f); return f; },
    getUrl: () => 'https://drive.google.com/folders/prueba'
  };
  const g = {
    Session:{getEffectiveUser:()=>({getEmail:()=>cuenta})},
    PROPS: { getProperty: (k) => k === 'SERVIDOR_HMAC' ? secreto : '' },
    Utilities: { computeHmacSha256Signature: (p,s) => [...crypto.createHmac('sha256',s).update(p).digest()],
      newBlob: (datos,tipo,nombre) => ({datos,tipo,nombre}), base64Decode: s => Buffer.from(s,'base64'), base64Encode: b => Buffer.from(b).toString('base64') },
    LockService: { getScriptLock: () => ({waitLock(){},releaseLock(){}}) },
    DriveApp: { getFolderById: () => carpeta, getFileById: () => ({ moveTo() {}, getBlob: () => ({getBytes: () => Buffer.from('informe-prueba')}) }) },
    exigirCarpeta_: () => 'carpeta', carpetaDeRecepcion_: () => carpeta, carpetaDe_: () => carpeta,
    limpiarNombre_: s => s,
    MailApp: { getRemainingDailyQuota: () => 100 },
    SpreadsheetApp: { create() { sheets++; const hoja = {clearContents(){},getMaxRows:()=>1000,getMaxColumns:()=>26,getRange:()=>({setValues(){}}),setFrozenRows(){}}; return {getId:()=> 'sheet-nuevo',getUrl:()=> 'https://docs.google.com/spreadsheets/d/nuevo',getSheetByName:()=>hoja,insertSheet:()=>hoja}; } },
    accionEnviarInforme_() { correos++; if (falloCorreo) throw new Error('Confirmacion interrumpida'); return {exito:true}; }
  };
  vm.createContext(g); vm.runInContext(fs.readFileSync(path.join(__dirname,'../proxy/Servidor.gs'),'utf8'),g);
  function peticion(operacion,clave,datos,fecha=Math.floor(Date.now()/1000)) {
    const payload=JSON.stringify({operacion,clave,datos:{usuario:'supervisor@gmail.com',...datos},fecha});
    return {payload,firma:crypto.createHmac('sha256',secreto).update(payload).digest('hex')};
  }
  return { g, peticion, cambiarCuenta:v=>{cuenta=v;}, correos:()=>correos, creados:()=>creados, sheets:()=>sheets, romperCorreo:()=>{falloCorreo=true;} };
}
const id='a'.repeat(32), clave=id+':'+ 'b'.repeat(32);
test('rechaza firma falsa antes de escribir',()=>{ const e=entorno(); const p=e.peticion('archivo',clave,{}); p.firma='0'.repeat(64); let fallo=false; try {e.g.entregaServidor_(p);}catch{fallo=true;} ok(fallo);ok(e.creados()===0); });
test('rechaza cambios del payload',()=>{ const e=entorno(); const p=e.peticion('archivo',clave,{}); p.payload+=' '; let fallo=false; try {e.g.entregaServidor_(p);}catch{fallo=true;} ok(fallo); });
test('rechaza solicitudes caducadas',()=>{ const e=entorno(); let fallo=false;try {e.g.entregaServidor_(e.peticion('archivo',clave,{},1));}catch{fallo=true;}ok(fallo); });
test('firma no da acceso a otras acciones del WMS',()=>{ const e=entorno();let fallo=false;try{e.g.entregaServidor_(e.peticion('guardarCliente',id,{}));}catch{fallo=true;}ok(fallo); });
test('archivo repetido no crea dos copias',()=>{const e=entorno();const p=e.peticion('archivo',clave,{tipoArchivo:'foto',base64:'aG9sYQ==',nombre:'SKU.png',tipo:'image/png'});const a=e.g.entregaServidor_(p),b=e.g.entregaServidor_(p);ok(a.fileId===b.fileId);ok(e.creados()===1);});
test('correo confirmado no se repite y no usa Sheets',()=>{const e=entorno();const p=e.peticion('finalizar',id,{codigo:'PRUEBA',destinatarios:'ejecutivo@example.test',archivos:[]});ok(e.g.entregaServidor_(p).exito);ok(e.g.entregaServidor_(p).exito);ok(e.correos()===1);ok(e.sheets()===0);});
test('confirmacion interrumpida requiere revision, no reenvio ciego',()=>{const e=entorno();e.romperCorreo();const p=e.peticion('finalizar',id,{codigo:'PRUEBA',destinatarios:'ejecutivo@example.test',archivos:[]});try{e.g.entregaServidor_(p);}catch{} const r=e.g.entregaServidor_(p);ok(r.revision);ok(e.correos()===1);});
test('sin destinatarios archiva sin correo ni Sheets',()=>{const e=entorno();ok(e.g.entregaServidor_(e.peticion('finalizar',id,{codigo:'PRUEBA',archivos:[]})).exito);ok(e.correos()===0);ok(e.sheets()===0);});
test('exportar texto no ejecuta formulas de hoja',()=>{const e=entorno();ok(e.g.celdaServidor_('=IMPORTXML("x")').startsWith("'="));ok(e.g.celdaServidor_(3)===3);});
test('Sheets solo se crea si se pide una exportacion expresa',()=>{const e=entorno(); const r=e.g.entregaServidor_(e.peticion('finalizar',id,{codigo:'PRUEBA',archivos:[],exportarSheet:true,skus:[{sku:'SKU1',contado:3}]}));ok(r.exito);ok(e.sheets()===1);ok(r.sheet.includes('nuevo'));ok(e.correos()===0);});
test('cuenta distinta del supervisor no escribe ni envia',()=>{const e=entorno();e.cambiarCuenta('otra@gmail.com');let fallo=false;try{e.g.entregaServidor_(e.peticion('finalizar',id,{destinatarios:'ejecutivo@example.test',archivos:[]}));}catch{fallo=true;}ok(fallo);ok(e.creados()===0);ok(e.correos()===0);});
test('probar puente verifica remitente y Drive sin crear ni enviar',()=>{const e=entorno();const r=e.g.entregaServidor_(e.peticion('estado',id,{}));ok(r.remitente==='supervisor@gmail.com');ok(e.creados()===0);ok(e.correos()===0);});
console.log(`${pasadas} pasadas, ${falladas} falladas`); process.exitCode=falladas?1:0;
