// Prueba la jerarquía real del puente con un Drive simulado; no envía correo.
const fs=require('fs'),vm=require('vm'),path=require('path'),assert=require('node:assert/strict');
let pasadas=0,falladas=0;
function test(n,f){try{f();pasadas++;}catch(e){falladas++;console.log('FALLA '+n+': '+e.message);}}
function entorno(){
  let sec=0;const archivos=new Map(),carpetas=new Map();
  const iter=a=>({hasNext:()=>a.length>0,next:()=>a.shift()});
  function carpeta(nombre,padre=null){const c={id:'carpeta-'+(++sec),nombre,padre,hijos:[],ficheros:[],getId(){return this.id;},getName(){return this.nombre;},getUrl(){return 'https://drive.google.com/drive/folders/'+this.id;},getFoldersByName(n){return iter(this.hijos.filter(c=>c.nombre===n));},getFiles(){return iter(this.ficheros.filter(f=>!f.trashed));},getFilesByName(n){return iter(this.ficheros.filter(f=>f.nombre===n&&!f.trashed));},createFile(b){return archivo(b.nombre,b.datos,this);}};carpetas.set(c.id,c);if(padre)padre.hijos.push(c);return c;}
  function archivo(nombre,contenido,padre,target=null){const f={id:'archivo-'+(++sec),nombre,contenido,padre,target,trashed:false,getId(){return this.id;},getName(){return this.nombre;},getTargetId(){return this.target;},getUrl(){return 'https://drive.google.com/file/d/'+this.id;},getBlob(){return {getDataAsString:()=>String(this.contenido),getBytes:()=>Buffer.from(String(this.contenido))};},setDescription(d){this.descripcion=d;},getDescription(){return this.descripcion||'';},getParents(){return iter(this.padre?[this.padre]:[]);},setName(n){this.nombre=n;},setContent(s){this.contenido=s;},setTrashed(v){this.trashed=v;},moveTo(c){if(this.padre)this.padre.ficheros=this.padre.ficheros.filter(a=>a!==this);this.padre=c;c.ficheros.push(this);}};archivos.set(f.id,f);if(padre)padre.ficheros.push(f);return f;}
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
test('foto del SKU usa carpeta directa y nombre corto; reintento tras renombrar no duplica',()=>{const e=entorno(),p={...e.datos,nombre:'SKU1_001.jpg',ruta:['SKU1'],rutaSku:['SKU1'],rutasVinculadas:[{sku:'SKU1',categoria:'VALIDACION',ruta:['SKU1'],rutaSku:['SKU1']}]};const a=e.g.archivoServidor_(clave,p),b=e.g.archivoServidor_(clave,p);assert.equal(a.fileId,b.fileId);const f=e.archivos.get(a.fileId);assert.equal(f.nombre,'SKU1_001.jpg');assert.equal(f.padre.nombre,'SKU1');assert.equal(f.padre.hijos.length,0);assert.equal(f.padre.padre.nombre,'REC-1');assert.equal(a.carpetaSkuUrl,f.padre.getUrl());assert.equal([...e.archivos.values()].filter(f=>f.contenido?.length).length,1);});
test('fotos con PNC usan categoría y SKU sin subcarpeta de tipo',()=>{const e=entorno(),p={...e.datos,nombre:'SKU1_001.jpg',ruta:['PNC','SKU1'],rutaSku:['PNC','SKU1']};const r=e.g.archivoServidor_(clave,p),f=e.archivos.get(r.fileId);assert.equal(f.padre.nombre,'SKU1');assert.equal(f.padre.padre.nombre,'PNC');assert.equal(f.padre.hijos.length,0);assert.equal(r.carpetaSkuUrl,f.padre.getUrl());assert.equal(f.nombre,'SKU1_001.jpg');});
test('reubicar foto conserva acceso desde la carpeta del informe anterior',()=>{const e=entorno(),p={...e.datos,nombre:'SKU1_001.jpg'};const a=e.g.archivoServidor_(clave,p),f=e.archivos.get(a.fileId),vieja=f.padre;const nuevo={...p,fileId:a.fileId,ruta:['PNC','SKU1'],rutaSku:['PNC','SKU1']};e.g.archivoServidor_(clave,nuevo);e.g.archivoServidor_(clave,nuevo);assert.equal(f.padre.nombre,'SKU1');assert.equal(vieja.ficheros.filter(x=>x.target===f.id).length,1);assert.equal([...e.archivos.values()].filter(x=>x.contenido?.length).length,1);assert.equal(f.nombre,'SKU1_001.jpg');});
test('manifiesto rechaza un archivo ajeno a la entrega',()=>{const e=entorno();assert.throws(()=>e.g.finalizarServidor_(id,{...e.datos,archivos:[],manifiesto:[{fileId:'otro',ruta:['PNC'],nombreFinal:'SKU.jpg'}]}),/no pertenece/);});
test('repositorio inválido o inaccesible no crea archivos',()=>{const e=entorno();assert.throws(()=>e.g.archivoServidor_(clave,{...e.datos,carpetaRaiz:'../x'}),/invalido/);assert.throws(()=>e.g.archivoServidor_(clave,{...e.datos,carpetaRaiz:'sin-permiso-real'}),/permiso/);assert.equal(e.archivos.size,0);});
test('papelera conserva el identificador del archivo',()=>{const e=entorno();const r=e.g.archivoServidor_(clave,e.datos);e.g.DriveApp.getFileById(r.fileId).setTrashed(true);assert(e.archivos.get(r.fileId).trashed);assert.equal(e.archivos.get(r.fileId).getId(),r.fileId);});
test('foto auditable usa nombre completo y descripción de procedencia',()=>{const e=entorno(),p={...e.datos,versionFotos:2,conservarAccesosPrevios:false,nombre:'REC-1_RB654123_20261018_00001.jpg',nombreOriginal:'WhatsApp.jpg',secuencia:1,embarques:['RB654123'],ruta:['BULTOS','Bulto01_REC-1_RB654123']};const r=e.g.archivoServidor_(clave,p),f=e.archivos.get(r.fileId);assert.equal(f.nombre,p.nombre);assert.equal(f.padre.nombre,'Bulto01_REC-1_RB654123');assert(f.descripcion.includes('Original WhatsApp.jpg'));assert.equal([...e.archivos.values()].filter(x=>x.contenido?.length).length,1);});
test('reclasificación explícita auditable mueve la misma foto sin atajo implícito',()=>{const e=entorno(),p={...e.datos,versionFotos:2,conservarAccesosPrevios:false,ruta:['FALTANTE','SKU1']};const a=e.g.archivoServidor_(clave,p),f=e.archivos.get(a.fileId),vieja=f.padre;const b=e.g.archivoServidor_(clave,{...p,fileId:a.fileId,base64:undefined,ruta:['PNC','SKU1'],rutasAnteriores:[p.ruta]});assert.equal(a.fileId,b.fileId);assert.equal(vieja.ficheros.filter(x=>!x.trashed).length,0);assert.equal([...e.archivos.values()].filter(x=>x.contenido?.length).length,1);});
test('respuesta perdida y ruta cambiada recupera el archivo original',()=>{const e=entorno(),p={...e.datos,versionFotos:2,conservarAccesosPrevios:false,ruta:['FALTANTE','SKU1']};const a=e.g.archivoServidor_(clave,p);const b=e.g.archivoServidor_(clave,{...p,ruta:['PNC','SKU1'],rutasAnteriores:[p.ruta],nombre:'REC-1_RB654123_20261018_00001.jpg'});assert.equal(a.fileId,b.fileId);assert.equal([...e.archivos.values()].filter(x=>x.contenido?.length).length,1);});
test('organización retira solo accesos antiguos al mismo archivo, conserva imágenes vecinas',()=>{const e=entorno(),p={...e.datos,ruta:['FALTANTE','SKU1']};const a=e.g.archivoServidor_(clave,p),f=e.archivos.get(a.fileId),vieja=f.padre;const vecina=e.g.archivoServidor_('c'.repeat(32)+':'+'d'.repeat(32),p);e.g.archivoServidor_(clave,{...p,fileId:a.fileId,ruta:['PNC','SKU1']});assert.equal(vieja.ficheros.filter(x=>x.target===f.id&&!x.trashed).length,1);const r=e.g.archivoServidor_(clave,{...p,fileId:a.fileId,versionFotos:2,conservarAccesosPrevios:false,ruta:['PNC','SKU1'],rutasAnteriores:[p.ruta]});assert.equal(r.accesosRetirados,1);assert.equal(vieja.ficheros.filter(x=>x.target===f.id&&!x.trashed).length,0);assert(!e.archivos.get(vecina.fileId).trashed);assert(!f.trashed);});
test('una foto compartida conserva un solo acceso intencional con nombre identificable',()=>{const e=entorno(),p={...e.datos,versionFotos:2,conservarAccesosPrevios:false,ruta:['BULTOS','Bulto01_REC-1_RB654123'],rutasVinculadas:[{categoria:'RECEPCION',sku:'',ruta:['BULTOS','Bulto01_REC-1_RB654123']},{categoria:'RECEPCION',sku:'',ruta:['BULTOS','Bulto02_REC-1_RB654123']}]};const a=e.g.archivoServidor_(clave,p);e.g.archivoServidor_(clave,{...p,fileId:a.fileId});const enlaces=[...e.archivos.values()].filter(x=>x.target===a.fileId&&!x.trashed);assert.equal(enlaces.length,1);assert(enlaces[0].nombre.startsWith('ACCESO__'));assert.equal([...e.archivos.values()].filter(x=>x.contenido?.length).length,1);});
test('rutas por embarque mantienen PNC, faltantes y sobrantes dentro de su carpeta',()=>{
 const e=entorno();let n=0;
 for(const emb of ['RB-A','RB-B'])for(const categoria of ['PNC','FALTANTE','SOBRANTE']){
  const ruta=['EMBARQUES',emb,categoria,'SKU1'],k=String(++n).padStart(32,'0'),p={...e.datos,versionFotos:2,conservarAccesosPrevios:false,ruta,rutaSku:ruta,nombre:emb+'_'+categoria+'.jpg'};
  const a=e.g.archivoServidor_(k+':'+k,p),b=e.g.archivoServidor_(k+':'+k,p),f=e.archivos.get(a.fileId);
  assert.equal(a.fileId,b.fileId);assert.equal(f.padre.nombre,'SKU1');assert.equal(f.padre.padre.nombre,categoria);assert.equal(f.padre.padre.padre.nombre,emb);
 }
 assert.equal([...e.archivos.values()].filter(f=>f.contenido?.length).length,6);
 const rec=e.raiz.hijos[0].hijos[0].hijos[0];assert.deepEqual(rec.hijos.map(f=>f.nombre),['EMBARQUES']);
});
test('una imagen compartida entre embarques confirma carpetas propias con el mismo fileId',()=>{
 const e=entorno(),a=['EMBARQUES','RB-A','PNC','SKU1'],b=['EMBARQUES','RB-B','PNC','SKU1'];
 const vs=[a,b].map(ruta=>({categoria:'PNC',sku:'SKU1',ruta,rutaSku:ruta})),p={...e.datos,versionFotos:2,conservarAccesosPrevios:false,ruta:a,rutaSku:a,rutasVinculadas:vs};
 const r=e.g.archivoServidor_(clave,p),urls=[];
 for(const v of vs){const s=e.g.archivoServidor_(clave,{...p,base64:undefined,fileId:r.fileId,rutasVinculadas:[v],conservarAccesosPrevios:true});urls.push(s.vinculosDrive['PNC|SKU1'].carpetaSkuUrl);assert.equal(s.fileId,r.fileId);}
 assert.notEqual(urls[0],urls[1]);assert.equal([...e.archivos.values()].filter(f=>f.contenido?.length).length,1);
 assert.equal([...e.archivos.values()].filter(f=>f.target===r.fileId&&!f.trashed).length,1);
});
test('índice de correo resuelve padres y categorías existentes sin crear ni mover fotos',()=>{
 const e=entorno(),p={...e.datos,ruta:['EMBARQUES','EMB-A','PNC','SKU1'],rutaSku:['EMBARQUES','EMB-A','PNC','SKU1']};
 const foto=e.g.archivoServidor_(clave,p),f=e.archivos.get(foto.fileId),padre=f.padre,n=e.archivos.size;
 const r=e.g.carpetasCorreoServidor_({carpetaRecepcionId:foto.carpetaRecepcionUrl.split('/').pop(),rutas:[[],['EMBARQUES','EMB-A'],['EMBARQUES','EMB-A','PNC'],['EMBARQUES','EMB-A','FALTANTE'],['EMBARQUES','EMB-B']]});
 assert.equal(r.carpetas.length,3);assert.equal(r.carpetas[1].url,padre.padre.padre.getUrl());assert.equal(r.carpetas[2].url,padre.padre.getUrl());assert.equal(f.padre,padre);assert.equal(e.archivos.size,n);assert.equal(padre.padre.padre.hijos.length,1);assert.equal(padre.padre.padre.padre.hijos.length,1);
 assert.throws(()=>e.g.carpetasCorreoServidor_({carpetaRecepcionId:foto.carpetaRecepcionUrl.split('/').pop(),rutas:[['PNC','SKU1']]}),/inválida/);
});
test('v67 verificar no crea recepción, embarques ni categorías vacías',()=>{
 const e=entorno(),p={...e.datos,embarques:['RB63196','RB56223']};const a=e.g.prepararCarpetasRecepcionServidor_(p),b=e.g.prepararCarpetasRecepcionServidor_(p);
 assert.equal(a,null);assert.equal(b,null);assert.deepEqual(e.raiz.hijos,[]);
 assert.equal(e.archivos.size,0);
});
test('v62 confirma carpetas del embarque directo y conserva accesos anteriores al reubicar',()=>{
 const e=entorno(),a=e.g.archivoServidor_(clave,e.datos),f=e.archivos.get(a.fileId),anterior=f.padre;
 const ruta=['RB63196','PNC','SKU1'],p={...e.datos,fileId:a.fileId,base64:undefined,ruta,rutaSku:ruta,versionFotos:2,conservarAccesosPrevios:true};
 e.g.archivoServidor_(clave,p);e.g.archivoServidor_(clave,p);
 assert.equal(f.padre.nombre,'SKU1');assert.equal(f.padre.padre.padre.nombre,'RB63196');
 assert.equal(anterior.ficheros.filter(x=>x.target===f.id).length,1);assert.equal([...e.archivos.values()].filter(x=>x.contenido?.length).length,1);
 const r=e.g.carpetasCorreoServidor_({carpetaRecepcionId:a.carpetaRecepcionUrl.split('/').pop(),rutas:[[],['RB63196'],['RB63196','PNC']]});assert.equal(r.carpetas.length,3);
});
test('la carpeta madre de v62 conserva su ID al cambiar marca y rechaza otro código',()=>{
 const e=entorno();e.g.archivoServidor_(clave,{...e.datos,ruta:['RB1','PNC','SKU1']});const rec=e.g.prepararCarpetasRecepcionServidor_({...e.datos,embarques:['RB1']});
 const misma=e.g.prepararCarpetasRecepcionServidor_({...e.datos,marca:'VW',carpetaRecepcionId:rec.getId(),embarques:['RB1','RB2']});
 assert.equal(misma,rec);assert.deepEqual(rec.hijos.map(c=>c.nombre),['RB1']);
 assert.throws(()=>e.g.carpetaRecepcionServidor_({...e.datos,carpetaRecepcion:'OTRA',carpetaRecepcionId:rec.getId()}),/no corresponde/);
});
console.log(`${pasadas} pasadas, ${falladas} falladas`);process.exitCode=falladas?1:0;
