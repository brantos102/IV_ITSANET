/** Prueba de navegador con fotos sintéticas y API simulada; no usa producción. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright-core';

const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const publico=path.join(repo,'firebase/public');
const salida=path.resolve(process.argv[2]||'/tmp/itsanet-prueba-guardado-fotos');
await fs.mkdir(salida,{recursive:true});
const browser=await chromium.launch({executablePath:process.env.IV_CHROMIUM||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1366,height:850}});
const errores=[],guardadas=new Set();let rechazo=422,peticiones=0;
page.on('pageerror',e=>errores.push(e.message));
const resumen=()=>({guardadas:59+guardadas.size,copiadas:59+guardadas.size,pendientes:0,procesando:0,requierenAyuda:0});
const html='<!doctype html><html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/app/css/app.css"><link rel="stylesheet" href="/app/css/marca.css"><link rel="stylesheet" href="/app/css/operacion.css"></head><body><main>Prueba de selección y guardado de fotografías</main></body></html>';
await page.route('**/*',async route=>{
  const req=route.request(),u=new URL(req.url());
  if(u.origin!=='http://127.0.0.1:5199')return route.abort();
  const json=(obj,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(obj)});
  if(u.pathname==='/app/prueba-fotos.html')return route.fulfill({contentType:'text/html',body:html});
  if(u.pathname==='/api/auth/yo')return json({id:21,usuario:'operario-prueba'});
  if(u.pathname.endsWith('/ingreso'))return json({unidades:[],protocolo:'GENERAL',recomendaciones:{exterioresMin:3,exterioresObjetivo:6,abiertosMin:2,packingMin:1}});
  if(u.pathname.endsWith('/fotos/embarques'))return json({candidatos:['RA26836','OTRO'],embarques:['RA26836','OTRO'],sugerido:'',permiteGeneral:true});
  if(u.pathname.endsWith('/drive'))return json({sincronizacion:resumen(),archivos:[],carpetas:[]});
  if(u.pathname.endsWith('/imagenes'))return json({archivos:[],total:0,sincronizacion:resumen()});
  if(u.pathname==='/api/app/recepciones/PRUEBA-FOTOS')return json({codigo:'PRUEBA-FOTOS',estado:'EN_VALIDACION',origenes:[]});
  if(u.pathname.endsWith('/archivos/foto')&&req.method()==='POST'){
    peticiones++;const p=req.postDataJSON();
    assert.equal(p.embarqueFoto,'RA26836');assert.equal(p.tipoEvidencia,'PRERECEPCION');
    assert.equal(p.categoria,'RECEPCION');assert.ok(p.base64);
    if(rechazo)return json({detail:'Aviso de prueba HTTP '+rechazo+': falta corregir el destino de la foto.'},rechazo);
    guardadas.add(p.nombre);return json({url:'/api/app/archivos/sintetica'+guardadas.size});
  }
  if(u.pathname.startsWith('/app/')){
    const f=path.resolve(publico,u.pathname.slice(5));
    if(!f.startsWith(publico+path.sep))return route.abort();
    try{return route.fulfill({contentType:f.endsWith('.js')?'text/javascript':f.endsWith('.css')?'text/css':'application/octet-stream',body:await fs.readFile(f)});}catch{return route.fulfill({status:404,body:'No existe'});}
  }
  return route.fulfill({status:404,body:'Ruta no simulada'});
});
try{
  await page.goto('http://127.0.0.1:5199/app/prueba-fotos.html');
  await page.evaluate(async()=>{const {abrirEvidencias}=await import('/app/js/evidencias.js');await abrirEvidencias({recepcion:'PRUEBA-FOTOS',categoria:'RECEPCION'});});
  const d=page.locator('dialog.evidencias-dialogo');
  await d.locator('[data-tipo]').selectOption('PRERECEPCION');
  await page.waitForFunction(()=>document.querySelector('[data-estado-drive]')?.textContent.includes('59 fotos registradas'));
  const imagenes=await page.evaluate(()=>Array.from({length:12},(_,i)=>{
    const c=document.createElement('canvas');c.width=400;c.height=300;const x=c.getContext('2d');
    x.fillStyle=`hsl(${i*29} 70% 60%)`;x.fillRect(0,0,400,300);x.fillStyle='#111';x.font='48px sans-serif';x.fillText('Prueba '+(i+1),35,150);
    return {name:'Sintetica-'+String(i+1).padStart(2,'0')+'.png',base64:c.toDataURL('image/png').split(',')[1]};
  }));
  const archivos=imagenes.map(x=>({name:x.name,mimeType:'image/png',buffer:Buffer.from(x.base64,'base64')}));
  await d.locator('[data-archivos]').setInputFiles(archivos);
  assert.equal(await d.locator('[data-seleccion] figure').count(),12);
  assert.match(await d.locator('[data-alerta-drive]').innerText(),/12 fotos seleccionadas por confirmar/);
  assert.equal(await d.locator('[data-progreso-fotos]').evaluate(el=>el.classList.contains('fotos-con-pendientes')),true);
  assert.match(await d.locator('[data-estado-drive]').innerText(),/59 fotos registradas/);
  await d.locator('[data-subir]').click();
  assert.match(await d.locator('[data-alerta-drive]').innerText(),/Selecciona el embarque/);
  assert.equal(peticiones,0);
  await d.locator('[data-embarque-fotos]').selectOption('RA26836');
  await d.locator('[data-subir]').click();
  await page.waitForFunction(()=>document.querySelector('[data-alerta-drive]').textContent.includes('Aviso de prueba HTTP 422'));
  assert.match(await d.locator('[data-alerta-drive]').innerText(),/Sintetica-01\.png/);
  assert.equal(await d.locator('[data-seleccion] figure').count(),12);
  assert.equal(await d.locator('[data-subir]').isEnabled(),true);
  // La siguiente consulta automática no puede borrar el error de guardado.
  await page.waitForTimeout(3200);
  assert.match(await d.locator('[data-alerta-drive]').innerText(),/Aviso de prueba HTTP 422/);
  rechazo=409;
  await d.locator('[data-subir]').click();
  await page.waitForFunction(()=>document.querySelector('[data-alerta-drive]').textContent.includes('Aviso de prueba HTTP 409'));
  assert.equal(await d.locator('[data-seleccion] figure').count(),12);
  await d.locator('[data-alerta-drive]').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(salida,'Error-visible-escritorio.png')});
  await page.setViewportSize({width:390,height:844});
  await d.locator('[data-alerta-drive]').scrollIntoViewIfNeeded();
  const caja=await d.locator('[data-alerta-drive]').boundingBox();
  assert.ok(caja.y>=0&&caja.y+caja.height<=844,'El aviso debe quedar visible en móvil');
  await page.screenshot({path:path.join(salida,'Error-visible-movil.png')});
  rechazo=0;
  await d.locator('[data-subir]').click();
  await page.waitForFunction(()=>document.querySelectorAll('[data-seleccion] figure').length===0);
  await page.waitForFunction(()=>document.querySelector('[data-estado-drive]').textContent.includes('71 fotos registradas'));
  assert.equal(guardadas.size,12);assert.equal(peticiones,14);
  assert.match(await d.locator('[data-alerta-drive]').innerText(),/fotografías registradas están confirmadas/);
  assert.equal(await d.locator('[data-progreso-fotos]').evaluate(el=>el.classList.contains('fotos-con-pendientes')),false);
  const temporales=await page.evaluate(()=>new Promise((resolve,reject)=>{const r=indexedDB.open('itsanet-fotos-pendientes',1);r.onsuccess=()=>{const q=r.result.transaction('fotos').objectStore('fotos').count();q.onsuccess=()=>resolve(q.result);q.onerror=()=>reject(q.error);};r.onerror=()=>reject(r.error);}));
  assert.equal(temporales,0);
  await d.locator('[data-archivos]').setInputFiles(archivos.slice(0,2));
  await d.getByRole('button',{name:'Quitar foto 1',exact:true}).click();
  assert.match(await d.locator('[data-alerta-drive]').innerText(),/1 fotos seleccionadas por confirmar/);
  await d.getByRole('button',{name:'Quitar foto 1',exact:true}).click();
  assert.match(await d.locator('[data-alerta-drive]').innerText(),/fotografías registradas están confirmadas/);
  assert.deepEqual(errores,[]);
  const resultado={api:'SIMULADA, sin conexión a producción',navegador:'Chromium',seleccionInicial:12,fotosPrevias:59,
    validaciones:['Selección separada de fotos registradas','Destino obligatorio visible antes de enviar','Errores 422 y 409 visibles en cabecera','Consulta automática conserva el error de guardado','Archivo rechazado identificado por nombre','Selección conservada al fallar','Reintento guarda el lote completo','Copia temporal retirada solo al confirmar','Quitar foto actualiza el estado','Cabecera visible en escritorio y móvil'],
    solicitudesPOST:peticiones,fotosRegistradasSimuladas:guardadas.size,temporalesTrasConfirmar:temporales,erroresJavaScript:errores};
  await fs.writeFile(path.join(salida,'Validacion-guardado-fotos.json'),JSON.stringify(resultado,null,2)+'\n');
  console.log(JSON.stringify(resultado,null,2));
}finally{await browser.close();}
