/** Imprime los HTML completos con un navegador local; no contacta al aplicativo. */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
let chromium;
try{({chromium}=await import('playwright-core'));}catch{process.stderr.write('Falta playwright-core. Ejecuta npm ci en esta copia del código, o usa Imprimir / PDF desde el HTML en tu computador.\n');process.exit(1);}
const args=process.argv.slice(2),carpeta=path.resolve(args[0]||''),chrome=args[1],sinSandbox=args.includes('--sin-sandbox');
if(!args[0]||!chrome)throw new Error('Indica carpeta y ejecutable de Chrome/Chromium/Edge.');
const nombres=['Manual-usuario-final-IV-ITSANET.html','Manual-tecnico-final-IV-ITSANET.html','Manual-usuario-completo-IV-ITSANET.html'];
const archivos=new Map();for(const n of nombres)try{archivos.set(n,await fs.readFile(path.join(carpeta,n)));}catch(e){if(e.code!=='ENOENT')throw e;}
if(!archivos.size)throw new Error('No hay HTML finales en la carpeta indicada.');
const browser=await chromium.launch({executablePath:chrome,headless:true,chromiumSandbox:!sinSandbox}),recibo={};
try{
 const contexto=await browser.newContext();
 await contexto.route('http://127.0.0.1:19872/**',r=>{const n=new URL(r.request().url()).pathname.slice(1);return r.fulfill(archivos.has(n)?{contentType:'text/html;charset=utf-8',body:archivos.get(n)}:{status:404,body:'No disponible'});});
 for(const [nombre,html] of archivos){
  const p=await contexto.newPage();p.setDefaultTimeout(60000);const errores=[];p.on('pageerror',e=>errores.push(String(e)));
  await p.goto('http://127.0.0.1:19872/'+nombre);
  await p.waitForFunction(()=>[...document.images].filter(i=>i.getAttribute('src')).every(i=>i.complete&&i.naturalWidth>0));
  if(nombre.includes('usuario')){const n=await p.locator('.step').count();if(n!==38||await p.locator('#paso-39,#paso-40').count())throw new Error('El manual de usuario no contiene los 38 pasos esperados.');}
  if(errores.length)throw new Error('No se imprimió un HTML con errores: '+errores.join(' · '));
  const pdf=await p.pdf({format:'A4',preferCSSPageSize:true,printBackground:true,tagged:true,outline:true});
  const final=nombre.replace(/\.html$/,'.pdf'),temporal=path.join(carpeta,'.'+crypto.randomUUID()+'.pdf');
  const f=await fs.open(temporal,'wx',0o600);try{await f.writeFile(pdf);await f.sync();}finally{await f.close();}
  await fs.rename(temporal,path.join(carpeta,final));
  recibo[final]={html:nombre,sha256Html:crypto.createHash('sha256').update(html).digest('hex'),sha256Pdf:crypto.createHash('sha256').update(pdf).digest('hex')};
  process.stdout.write('PDF creado: '+path.join(carpeta,final)+'\n');await p.close();
 }
 await fs.writeFile(path.join(carpeta,'Exportacion-PDF.json'),JSON.stringify(recibo,null,2));
}finally{await browser.close();}
