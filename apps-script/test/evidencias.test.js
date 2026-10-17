// Prueba la jerarquía real del puente con un Drive simulado; no envía correo.
const fs=require('fs'),vm=require('vm'),path=require('path'),assert=require('node:assert/strict');
let pasadas=0,falladas=0;
function test(n,f){try{f();pasadas++;}catch(e){falladas++;console.log('FALLA '+n+': '+e.message);}}
function entorno(){
  let sec=0;const archivos=new Map(),carpetas=new Map();
  const iter=a=>({hasNext:()=>a.length>0,next:()=>a.shift()});
  function carpeta(nombre,padre=null){const c={id:'carpeta-'+(++sec),nombre,padre,hijos:[],ficheros:[],getId(){return this.id;},getName(){return this.nombre;},getUrl(){return 'https://drive.google.com/drive/folders/'+this.id;},getFiles(){return iter(this.ficheros.filter(f=>!f.trashed));},getFilesByName(n){return iter(this.ficheros.filter(f=>f.nombre===n&&!f.trashed));},createFile(b){return archivo(b.nombre,b.datos,this);}};carpetas.set(c.id,c);if(padre)padre.hijos.push(c);return c;}
  function archivo(nombre,contenido,padre,target=null){const f={id:'archivo-'+(++sec),nombre,contenido,padre,target,trashed:false,getId(){return this.id;},getTargetId(){return this.target;},getUrl(){return 'https://drive.google.com/file/d/'+this.id;},getBlob(){return {getDataAsString:()=>String(this.contenido),getBytes:()=>Buffer.from(String(this.contenido))};},setDescription(){},setName(n){this.nombre=n;},setContent(s){this.contenido=s;},setTrashed(v){this.trashed=v;},moveTo(c){if(this.padre)this.padre.ficheros=this.padre.ficheros.filter(a=>a!==this);this.padre=c;c.ficheros.push(this);}};archivos.set(f.id,f);if(padre)padre.ficheros.push(f);return f;}
  const raiz=carpeta('Repositorio');raiz.id='repositorio-pruebas';carpetas.set(raiz.id,raiz);
  const g={PROPS:{getProperty:()=>''},Session:{getEffectiveUser:()=>({getEmail:()=> 'sup@example.test'})},exigirCarpeta_:()=>raiz.id,
    limpiarNombre_:s=>String(s||'').replace(/[\\/]/g,'_'),
    carpetaDe_:(p,n)=>p.hijos.find(c=>c.nombre===n)||carpeta(n,p),
    Utilities:{newBlob:(datos,tipo,nombre)=>({datos,tipo,nombre}),base64Decode:s=>Buffer.from(s,'base64')},
    DriveApp:{getFolderById:id=>{if(!carpetas.has(id))throw Error('Sin permiso');return carpetas.get(id);},getFileById:id=>{assert(archivos.has(id));return archivos.get(id);},createShortcut:id=>archivo('',null,null,id)},
  };
  vm.createContext(g);vm.runInContext(fs.readFileSync(path.join(__dirname,'../proxy/Servidor.gs'),'utf8'),g);
  const datos={usuario:'sup@example.test',carpetaRaiz:raiz.id,cliente:'VENTURA',marca:'ISUZU',recepcion:'REC-1',codigo:'REC-1',tipoArchivo:'foto',nombre:'SKU1.jpg',tipo:'image/jpeg',base64:'aG9sYQ==',sku:'SKU1',ruta:['PNC','SKU1','ITEM_NOVEDAD']};
  return {g,raiz,archivos,carpetas,datos};
}
const id='a'.repeat(32),clave=id+':'+ 'b'.repeat(32);
test('cliente, marca, recepción y solo categorías con contenido',()=>{const e=entorno();const r=e.g.archivoServidor_(clave,e.datos);const rec=e.raiz.hijos[0].hijos[0].hijos[0];assert.equal(rec.nombre,'REC-1');assert.deepEqual(rec.hijos.map(c=>c.nombre),['PNC']);const f=e.archivos.get(r.fileId);assert.equal(f.padre.nombre,'ITEM_NOVEDAD');assert.equal(f.padre.padre.nombre,'SKU1');assert.equal(r.carpetaRecepcionUrl,rec.getUrl());});
test('reintentar copia conserva archivo único',()=>{const e=entorno();const a=e.g.archivoServidor_(clave,e.datos),b=e.g.archivoServidor_(clave,e.datos);assert.equal(a.fileId,b.fileId);assert.equal(e.archivos.size,1);});
test('una imagen vinculada a dos listas usa acceso directo sin duplicar binario',()=>{const e=entorno();const r=e.g.archivoServidor_(clave,e.datos);const manifiesto=[{fileId:r.fileId,ruta:e.datos.ruta,nombreFinal:'SKU1_01_de_01.jpg'},{fileId:r.fileId,ruta:['PNC','SKU2','ITEM_NOVEDAD'],nombreFinal:'SKU1_01_de_01.jpg'}];const d={...e.datos,archivos:[{fileId:r.fileId,tipoArchivo:'foto'}],manifiesto};const a=e.g.finalizarServidor_(id,d),b=e.g.finalizarServidor_(id,d);assert(a.exito&&b.exito);assert.equal([...e.archivos.values()].filter(f=>f.target===r.fileId).length,1);assert.equal([...e.archivos.values()].filter(f=>f.contenido?.length&&f.nombre.endsWith('.jpg')).length,1);assert.equal(e.archivos.get(r.fileId).nombre,'SKU1_01_de_01.jpg');});
test('vínculo compartido apunta a cada SKU y reubicar conserva el binario',()=>{const e=entorno();const p={...e.datos,rutasVinculadas:[{categoria:'PNC',sku:'SKU1',ruta:['PNC','SKU1','ITEM_NOVEDAD']},{categoria:'PNC',sku:'SKU2',ruta:['PNC','SKU2','ITEM_NOVEDAD']}]};const a=e.g.archivoServidor_(clave,p);assert.notEqual(a.vinculosDrive['PNC|SKU1'].carpetaSkuUrl,a.vinculosDrive['PNC|SKU2'].carpetaSkuUrl);const b=e.g.archivoServidor_(clave,{...p,fileId:a.fileId,base64:undefined,ruta:['VALIDACION','SKU1','ITEM_NOVEDAD']});assert.equal(a.fileId,b.fileId);assert.equal([...e.archivos.values()].filter(f=>f.contenido?.length).length,1);});
test('manifiesto rechaza un archivo ajeno a la entrega',()=>{const e=entorno();assert.throws(()=>e.g.finalizarServidor_(id,{...e.datos,archivos:[],manifiesto:[{fileId:'otro',ruta:['PNC'],nombreFinal:'SKU.jpg'}]}),/no pertenece/);});
test('repositorio inválido o inaccesible no crea archivos',()=>{const e=entorno();assert.throws(()=>e.g.archivoServidor_(clave,{...e.datos,carpetaRaiz:'../x'}),/invalido/);assert.throws(()=>e.g.archivoServidor_(clave,{...e.datos,carpetaRaiz:'sin-permiso-real'}),/permiso/);assert.equal(e.archivos.size,0);});
test('papelera conserva el identificador del archivo',()=>{const e=entorno();const r=e.g.archivoServidor_(clave,e.datos);e.g.DriveApp.getFileById(r.fileId).setTrashed(true);assert(e.archivos.get(r.fileId).trashed);assert.equal(e.archivos.get(r.fileId).getId(),r.fileId);});
console.log(`${pasadas} pasadas, ${falladas} falladas`);process.exitCode=falladas?1:0;
