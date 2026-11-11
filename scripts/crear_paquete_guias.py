"""Empaqueta guías privadas en una descarga HTML cifrada, sin publicarlas abiertas."""
import argparse
import base64
import gzip
import hashlib
from html import escape
import json
from pathlib import Path
import secrets
from zipfile import ZipFile, ZIP_DEFLATED
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DOMINIO='IV-ITSANET-GUIAS-1'
HTML='''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Guías de usuario · IV ITSANET</title><style>body{max-width:980px;margin:35px auto;padding:0 18px;background:#f3f6fa;color:#17324d;font:16px/1.6 system-ui}main,article{padding:22px;border:1px solid #dce5ef;border-radius:12px;background:#fff;margin:14px 0}h1{line-height:1.2}input,button{font:inherit;padding:11px;border:1px solid #aabacf;border-radius:8px}button{cursor:pointer;background:#225de2;color:#fff;font-weight:650}input{max-width:100%}small{display:block;color:#526781;overflow-wrap:anywhere}.nota{background:#edf4ff;padding:15px;border-radius:8px}button:focus-visible,input:focus-visible{outline:3px solid #daa500}article strong{display:block}article button{margin-top:12px}</style></head><body><main><h1>Guías de usuario · IV ITSANET</h1><p>Guía rápida, guía del operador, guía del supervisor, ayuda, glosario y manual completo.</p><p class="nota">Usa la clave documental de la entrega. Después descarga el documento que necesites. El manual HTML contiene sus imágenes y funciona sin descargar recursos adicionales.</p><form id="acceso"><label for="clave">Clave documental</label><div><input id="clave" type="password" autocomplete="off" required><button id="abrir">Mostrar documentos</button></div></form><p id="estado" role="status"></p></main><section id="archivos"></section><script>
const datos=__PAYLOAD__,de64=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
document.querySelector('#acceso').onsubmit=async e=>{e.preventDefault();const b=document.querySelector('#abrir'),estado=document.querySelector('#estado');b.disabled=true;estado.textContent='Verificando la entrega…';
try{const material=await crypto.subtle.importKey('raw',new TextEncoder().encode(document.querySelector('#clave').value),'PBKDF2',false,['deriveKey']);
 const key=await crypto.subtle.deriveKey({name:'PBKDF2',salt:de64(datos.salt),iterations:310000,hash:'SHA-256'},material,{name:'AES-GCM',length:256},false,['decrypt']);
 const bruto=await crypto.subtle.decrypt({name:'AES-GCM',iv:de64(datos.iv),additionalData:new TextEncoder().encode('IV-ITSANET-GUIAS-1')},key,de64(datos.contenido));
 const gzip=new Blob([bruto]).stream().pipeThrough(new DecompressionStream('gzip'));const entrega=JSON.parse(await new Response(gzip).text());
 if(entrega.formato!=='IV-ITSANET-GUIAS-1')throw Error('Formato documental desconocido.');
 const raiz=document.querySelector('#archivos');raiz.replaceChildren();
 for(const f of entrega.archivos){const a=document.createElement('article'),t=document.createElement('strong'),p=document.createElement('small'),b=document.createElement('button');t.textContent=f.nombre;p.textContent=(f.bytes/1024/1024).toFixed(2)+' MB';b.textContent='Descargar '+f.nombre;
 b.onclick=async()=>{b.disabled=true;try{const bytes=de64(f.base64),hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');if(hash!==f.sha256)throw Error('El documento no coincide con la entrega.');const u=URL.createObjectURL(new Blob([bytes],{type:f.tipo})),enlace=document.createElement('a');enlace.href=u;enlace.download=f.nombre;enlace.click();setTimeout(()=>URL.revokeObjectURL(u),30000);estado.textContent='Descarga iniciada. Revisa Descargas de tu equipo.';}catch(error){estado.textContent=error.message;}finally{b.disabled=false;}};
 a.append(t,p,b);raiz.append(a);}
 document.querySelector('#clave').value='';estado.textContent='Documentos disponibles. Empieza por Manual-usuario-IV-ITSANET.html o por la guía de tu función.';
}catch(error){estado.textContent=error.name==='OperationError'?'La clave no coincide o el paquete está incompleto.':error.message;}finally{b.disabled=false;}};
</script></body></html>'''


def crear(carpeta,clave,salida,extension):
    orden=['Manual-usuario','Guia-rapida','Guia-operador','Guia-supervisor','Guia-ayuda','Glosario']
    archivos=[Path(carpeta)/(n+'-IV-ITSANET.'+extension) for n in orden]
    if not all(p.is_file() for p in archivos):raise ValueError('La entrega debe contener los seis documentos del formato seleccionado.')
    secreto=json.loads(Path(clave).read_text())['clave']
    docs=[]
    for p in archivos:
        b=p.read_bytes();docs.append({'nombre':p.name,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),
            'tipo':'text/html;charset=utf-8' if extension=='html' else 'application/pdf','base64':base64.b64encode(b).decode()})
    contenido=json.dumps({'formato':DOMINIO,'archivos':docs},ensure_ascii=False).encode()
    salt=secrets.token_bytes(16);iv=secrets.token_bytes(12)
    key=PBKDF2HMAC(algorithm=hashes.SHA256(),length=32,salt=salt,iterations=310000).derive(secreto.encode())
    cifrado=AESGCM(key).encrypt(iv,gzip.compress(contenido,compresslevel=9),DOMINIO.encode())
    payload={k:base64.b64encode(v).decode() for k,v in [('salt',salt),('iv',iv),('contenido',cifrado)]}
    pagina=HTML.replace('__PAYLOAD__',json.dumps(payload,separators=(',',':')))
    salida=Path(salida);salida.parent.mkdir(parents=True,exist_ok=True)
    nombre='Descargar-guias-'+extension.upper()+'.html'
    with ZipFile(salida,'w',ZIP_DEFLATED,compresslevel=7) as z:z.writestr(nombre,pagina)
    # Descifrar y verificar también en Python antes de entregar el archivo.
    verificado=json.loads(gzip.decompress(AESGCM(key).decrypt(iv,cifrado,DOMINIO.encode())))
    assert [d['sha256'] for d in verificado['archivos']]==[d['sha256'] for d in docs]
    informe={'paquete':salida.name,'bytes':salida.stat().st_size,'sha256':hashlib.sha256(salida.read_bytes()).hexdigest(),
        'archivos':[{'nombre':d['nombre'],'sha256':d['sha256'],'bytes':d['bytes']} for d in docs]}
    return informe


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--carpeta',type=Path,required=True);p.add_argument('--clave',type=Path,required=True);p.add_argument('--salida',type=Path,required=True);p.add_argument('--extension',choices=['html','pdf'],required=True);a=p.parse_args()
    print(json.dumps(crear(a.carpeta,a.clave,a.salida,a.extension),ensure_ascii=False))
