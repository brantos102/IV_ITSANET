/** Revisa navegación, búsqueda, descargas y PDF con el contenido privado local. */
import {chromium} from 'playwright-core';
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const carpeta=path.resolve(process.argv[2]);
const browser=await chromium.launch({executablePath:process.env.IV_CHROMIUM||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const contexto=await browser.newContext({acceptDownloads:true,viewport:{width:1366,height:900}});
const pagina=await contexto.newPage();const errores=[];
pagina.on('pageerror',e=>errores.push(e.message));
const csp="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; connect-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'; sandbox allow-scripts allow-modals allow-downloads allow-top-navigation-by-user-activation";
await contexto.route('**/*',async r=>{
 const u=new URL(r.request().url()),n=path.basename(u.pathname);
 if(u.origin!=='http://127.0.0.1:5299'||!n.endsWith('.html'))return r.abort();
 try{await r.fulfill({contentType:'text/html',headers:{'Content-Security-Policy':csp},body:await fs.readFile(path.join(carpeta,n))});}catch{await r.fulfill({status:404,body:'No existe'});}
});
const ir=nombre=>pagina.goto('http://127.0.0.1:5299/'+nombre);
const vista=async nombre=>{await pagina.locator('.menu [data-vista="'+nombre+'"]').click();};
const resultados={vistas:{},busqueda:false,descargaHTML:false,movil:false,erroresJavaScript:errores,pdfs:[]};
try{
 await ir('Manual-usuario-IV-ITSANET.html');
 assert.equal(await pagina.locator('.paso-detalle:visible').count(),0);
 assert.equal(await pagina.locator('.tarjetas .tarjeta:visible').count(),6);
 for(const [v,n] of [['operador',19],['supervisor',22],['ayuda',1],['completo',38]]){
  await vista(v);const visibles=await pagina.locator('.paso-detalle:visible').count();assert.equal(visibles,n);resultados.vistas[v]=visibles;
 }
 await vista('rapida');assert.equal(await pagina.locator('.flujo:visible').count(),2);
 assert.equal(await pagina.locator('.paso-detalle:visible').count(),0);
 await pagina.locator('[data-seccion="rapida"] [data-paso="paso-8"]').click();
 assert.equal(await pagina.locator('#paso-8').isVisible(),true);
 await vista('operador');await pagina.locator('#buscar').fill('cámara');
 assert.ok(await pagina.locator('.paso-detalle:visible').count()>0);
 assert.ok(await pagina.locator('.paso-detalle:visible').count()<19);resultados.busqueda=true;
 await vista('glosario');assert.equal(await pagina.locator('.termino:visible').count(),42);
 await pagina.locator('#buscar').fill('pnc');assert.equal(await pagina.locator('.termino:visible').count(),1);
 await vista('inicio');
 const [descarga]=await Promise.all([pagina.waitForEvent('download'),pagina.locator('#descargar').click()]);
 assert.equal(descarga.suggestedFilename(),'Manual-usuario-IV-ITSANET.html');
 const bajado=await fs.readFile(await descarga.path(),'utf8');assert.equal((bajado.match(/class="step"/g)||[]).length,38);resultados.descargaHTML=true;
 await pagina.screenshot({path:path.join(carpeta,'Vista-inicio-escritorio.png'),fullPage:true});
 await pagina.setViewportSize({width:390,height:844});await vista('operador');
 assert.ok(await pagina.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await pagina.screenshot({path:path.join(carpeta,'Vista-operador-movil.png'),fullPage:true});resultados.movil=true;
 await pagina.setViewportSize({width:1366,height:900});
 const nombres=['Guia-rapida-IV-ITSANET','Guia-operador-IV-ITSANET','Guia-supervisor-IV-ITSANET','Guia-ayuda-IV-ITSANET','Glosario-IV-ITSANET'];
 for(const n of nombres){
  await ir(n+'.html');await pagina.evaluate(()=>{prepararImpresion();document.querySelectorAll('img[src^="data:"]').forEach(i=>i.loading='eager');});
  await pagina.evaluate(async()=>{await document.fonts.ready;await Promise.all([...document.querySelectorAll('img[src^="data:"]')].map(i=>i.decode().catch(()=>{})));});
  await pagina.pdf({path:path.join(carpeta,n+'.pdf'),format:'A4',printBackground:true,margin:{top:'12mm',bottom:'12mm',left:'12mm',right:'12mm'}});
  resultados.pdfs.push(n+'.pdf');
 }
 await ir('Manual-usuario-IV-ITSANET.html');await vista('completo');
 await pagina.evaluate(()=>{prepararImpresion();document.querySelectorAll('img[src^="data:"]').forEach(i=>i.loading='eager');});
 await pagina.evaluate(async()=>{await document.fonts.ready;await Promise.all([...document.querySelectorAll('img[src^="data:"]')].map(i=>i.decode().catch(()=>{})));});
 await pagina.pdf({path:path.join(carpeta,'Manual-usuario-IV-ITSANET.pdf'),format:'A4',printBackground:true,margin:{top:'12mm',bottom:'12mm',left:'12mm',right:'12mm'}});
 resultados.pdfs.push('Manual-usuario-IV-ITSANET.pdf');
 assert.deepEqual(errores,[]);
 await fs.writeFile(path.join(carpeta,'Validacion-navegador.json'),JSON.stringify(resultados,null,2)+'\n');
 console.log(JSON.stringify(resultados,null,2));
}finally{await browser.close();}
