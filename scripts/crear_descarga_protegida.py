"""Entrega descargable cifrada. Nunca publica documentos ni la clave en texto claro."""
from pathlib import Path
from html import escape
import argparse
import base64
import gzip
import hashlib
import json
import secrets
import re
import zipfile
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

DOMINIO='IV-ITSANET-DESCARGA-1'
ITERACIONES=310000

PAGINA=r'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src data: blob:; base-uri 'none'; form-action 'none'"><title>IV ITSANET · Descarga protegida</title><style>*{box-sizing:border-box}body{margin:0;background:#edf3f9;color:#14314d;font:16px/1.55 system-ui}main{max-width:980px;margin:32px auto;padding:24px;background:white;border-radius:16px}h1{font-size:30px;line-height:1.2}button,input{font:inherit;padding:12px;border:1px solid #b9cde2;border-radius:9px}input{width:100%;max-width:500px}button{cursor:pointer;background:#155ce7;color:white;margin:6px 8px 6px 0}button:disabled{opacity:.6;cursor:wait}article{border:1px solid #d5e0ec;border-radius:12px;padding:16px;margin:14px 0;overflow-wrap:anywhere}small{display:block;color:#526a82}.aviso{background:#eff8f7;padding:15px;border-left:4px solid #00989e}textarea{width:100%;min-height:310px;font:14px/1.5 system-ui}#estado{white-space:pre-wrap}#lista button{display:block}section[hidden]{display:none}code{overflow-wrap:anywhere}</style></head><body><main><small>IV ITSANET · Entrega documental · 38 pasos</small><h1>__TITULO__</h1><p>Introduce la clave facilitada junto al enlace de descarga. Los documentos se abren y descargan en este computador; esta página no envía la clave ni los archivos a ningún servidor.</p><label for="clave">Clave de descarga</label><br><input id="clave" type="password" autocomplete="off" spellcheck="false"><br><button id="abrir">Mostrar archivos</button><p id="estado" role="status"></p><section id="contenido" hidden><div class="aviso">El manual de usuario contiene 38 pasos. Los puntos 39 y 40 están eliminados. Las capturas de referencia están identificadas. La actualización del servidor requiere confirmar su pase.</div><h2>Descargar archivos</h2><div id="lista"></div><h2>Correo preparado</h2><p>Completa los destinatarios y tu firma. Este descargador no envía correos.</p><button id="copiar">Copiar texto del correo</button><button id="eml" hidden>Descargar correo con los dos PDF adjuntos (.eml)</button><textarea id="correo" readonly aria-label="Texto del correo"></textarea><p><small>En Gmail web: descarga los dos PDF, copia el texto y adjunta los archivos. El .eml es una alternativa para clientes de correo compatibles.</small></p></section><small>Conserva la clave de esta entrega y distribuye los documentos según sus destinatarios autorizados. El técnico contiene información de mantenimiento e infraestructura.</small></main><script id="cifrado" type="application/json">__CIFRADO__</script><script>
const datos=JSON.parse(document.querySelector('#cifrado').textContent),estado=document.querySelector('#estado');let entrega=null;
const de64=s=>{const b=atob(s),a=new Uint8Array(b.length);for(let i=0;i<b.length;i++)a[i]=b.charCodeAt(i);return a;};
function guardar(nombre,bytes,tipo){const u=URL.createObjectURL(new Blob([bytes],{type:tipo})),a=document.createElement('a');a.href=u;a.download=nombre;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),30000);}
document.querySelector('#abrir').onclick=async()=>{const b=document.querySelector('#abrir');b.disabled=true;estado.textContent='Abriendo el paquete protegido. Espera unos segundos…';
 try{if(!crypto.subtle||!globalThis.DecompressionStream)throw new Error('Abre este HTML en una versión reciente de Chrome o Edge.');
  const password=document.querySelector('#clave').value.trim(),base=await crypto.subtle.importKey('raw',new TextEncoder().encode(password),'PBKDF2',false,['deriveKey']);
  const key=await crypto.subtle.deriveKey({name:'PBKDF2',salt:de64(datos.salt),iterations:datos.iteraciones,hash:'SHA-256'},base,{name:'AES-GCM',length:256},false,['decrypt']);
  const bruto=await crypto.subtle.decrypt({name:'AES-GCM',iv:de64(datos.iv),additionalData:new TextEncoder().encode('IV-ITSANET-DESCARGA-1')},key,de64(datos.contenido));
  const stream=new Blob([bruto]).stream().pipeThrough(new DecompressionStream('gzip'));entrega=JSON.parse(await new Response(stream).text());
  if(entrega.formato!=='IV-ITSANET-DESCARGA-1')throw new Error('Formato de entrega no reconocido.');
  const lista=document.querySelector('#lista');lista.replaceChildren();for(const f of entrega.archivos){const a=document.createElement('article'),t=document.createElement('strong'),info=document.createElement('small'),boton=document.createElement('button');t.textContent=f.nombre;info.textContent=(f.bytes/1024/1024).toFixed(2)+' MB · SHA-256 '+f.sha256;boton.textContent='Descargar '+f.nombre;boton.onclick=async()=>{boton.disabled=true;try{const bytes=de64(f.base64),hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');if(hash!==f.sha256)throw new Error('No coincide la integridad del archivo. Vuelve a abrir el paquete.');guardar(f.nombre,bytes,f.tipo);estado.textContent='Descarga iniciada: '+f.nombre+'. Revisa Descargas del navegador.';}catch(e){estado.textContent=e.message;}finally{boton.disabled=false;}};a.append(t,info,boton);lista.append(a);}
  document.querySelector('#correo').value=entrega.correoTexto;document.querySelector('#contenido').hidden=false;document.querySelector('#clave').value='';
  document.querySelector('#eml').hidden=!entrega.archivos.some(f=>f.nombre==='Manual-usuario-final-IV-ITSANET.pdf')||!entrega.archivos.some(f=>f.nombre==='Manual-tecnico-final-IV-ITSANET.pdf');
  estado.textContent='Archivos verificados y disponibles. Pulsa Descargar en cada documento.';
 }catch(e){entrega=null;document.querySelector('#contenido').hidden=true;estado.textContent=e.name==='OperationError'?'La clave no coincide o el archivo está incompleto. Copia la clave completa y vuelve a intentar.':e.message;}finally{b.disabled=false;}
};
document.querySelector('#copiar').onclick=async()=>{const t=document.querySelector('#correo');try{await navigator.clipboard.writeText(t.value);estado.textContent='Texto copiado. Pégalo en un correo nuevo y adjunta los PDF.';}catch{t.select();estado.textContent='Seleccionado: pulsa Ctrl+C para copiar el correo.';}};
const cabecera=s=>(s.match(/.{1,10}/gu)||['']).map(t=>'=?UTF-8?B?'+b64texto(t)+'?=').join(String.fromCharCode(13,10)+' ');
function b64texto(t){const bytes=new TextEncoder().encode(t);let s='';for(const b of bytes)s+=String.fromCharCode(b);return btoa(s);}
const lineas=s=>s.match(/.{1,76}/g).join('\r\n');
document.querySelector('#eml').onclick=()=>{
 if(!entrega)return;const limite='ivitsanet-'+crypto.randomUUID(),alternativo=limite+'-alt';
 let mensaje='X-Unsent: 1\r\nMIME-Version: 1.0\r\nDate: '+new Date().toUTCString()+'\r\nSubject: '+cabecera(entrega.asunto)+'\r\nContent-Type: multipart/mixed; boundary="'+limite+'"\r\n\r\n';
 mensaje+='--'+limite+'\r\nContent-Type: multipart/alternative; boundary="'+alternativo+'"\r\n\r\n';
 for(const [tipo,texto] of [['text/plain',entrega.cuerpoTexto],['text/html',entrega.correoHtml]])mensaje+='--'+alternativo+'\r\nContent-Type: '+tipo+'; charset="utf-8"\r\nContent-Transfer-Encoding: base64\r\n\r\n'+lineas(b64texto(texto))+'\r\n';
 mensaje+='--'+alternativo+'--\r\n';
 for(const nombre of ['Manual-usuario-final-IV-ITSANET.pdf','Manual-tecnico-final-IV-ITSANET.pdf']){const f=entrega.archivos.find(f=>f.nombre===nombre);mensaje+='--'+limite+'\r\nContent-Type: application/pdf; name="'+nombre+'"\r\nContent-Disposition: attachment; filename="'+nombre+'"\r\nContent-Transfer-Encoding: base64\r\n\r\n'+lineas(f.base64)+'\r\n';}
 mensaje+='--'+limite+'--\r\n';guardar('Correo-entrega-IV-ITSANET.eml',mensaje,'message/rfc822');estado.textContent='Borrador .eml descargado con los dos PDF. Completa destinatarios y firma en tu cliente de correo. No se ha enviado.';
};
</script></body></html>'''.replace('\n+','\n')

def crear(archivos,correo,privado,salida,nombre,titulo):
    privado=Path(privado).resolve();repo=Path(__file__).resolve().parents[1]
    if privado==repo or repo in privado.parents:raise ValueError('La clave y las copias privadas deben quedar fuera del repositorio.')
    privado.mkdir(parents=True,exist_ok=True,mode=0o700);privado.chmod(0o700)
    clave=privado/'clave-descarga.json'
    if clave.exists():password=json.loads(clave.read_text())['clave']
    else:
        password=secrets.token_urlsafe(18);clave.write_text(json.dumps({'clave':password}));clave.chmod(0o600)
    texto=Path(correo).read_text();asunto,cuerpo=texto.split('\n\n',1);asunto=asunto.removeprefix('Asunto: ')
    html=Path(correo).with_suffix('.html').read_text()
    cuerpo_html=re.search(r'<article id="correo">(.*?)</article>',html,re.S).group(1)
    cuerpo_html='<html><body style="font:15px/1.6 Arial,sans-serif">'+cuerpo_html+'</body></html>'
    datos={'formato':DOMINIO,'asunto':asunto,'correoTexto':texto,'cuerpoTexto':cuerpo,'correoHtml':cuerpo_html,'archivos':[]}
    for path in archivos:
        path=Path(path);b=path.read_bytes();tipo={'.pdf':'application/pdf','.html':'text/html;charset=utf-8','.txt':'text/plain;charset=utf-8'}[path.suffix]
        datos['archivos'].append({'nombre':path.name,'tipo':tipo,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'base64':base64.b64encode(b).decode()})
    salt=secrets.token_bytes(16);iv=secrets.token_bytes(12)
    key=PBKDF2HMAC(algorithm=hashes.SHA256(),length=32,salt=salt,iterations=ITERACIONES).derive(password.encode())
    cifrado=AESGCM(key).encrypt(iv,gzip.compress(json.dumps(datos,ensure_ascii=False).encode(),compresslevel=9),DOMINIO.encode())
    payload={'salt':base64.b64encode(salt).decode(),'iv':base64.b64encode(iv).decode(),'iteraciones':ITERACIONES,'contenido':base64.b64encode(cifrado).decode()}
    pagina=PAGINA.replace('__TITULO__',escape(titulo)).replace('__CIFRADO__',json.dumps(payload,separators=(',',':')))
    salida=Path(salida);salida.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(salida,'w',zipfile.ZIP_DEFLATED,compresslevel=7) as z:z.writestr(nombre,pagina)
    (privado/nombre).write_text(pagina)
    with zipfile.ZipFile(salida) as z:assert z.testzip() is None
    return {'archivo':str(salida),'MB':round(salida.stat().st_size/1024**2,1),'sha256':hashlib.sha256(salida.read_bytes()).hexdigest(),'archivos':[f['nombre'] for f in datos['archivos']]}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archivos',nargs='+',type=Path,required=True);p.add_argument('--correo',type=Path,required=True);p.add_argument('--privado',type=Path,required=True);p.add_argument('--salida',type=Path,required=True);p.add_argument('--nombre-html',required=True);p.add_argument('--titulo',required=True);a=p.parse_args()
    print(json.dumps(crear(a.archivos,a.correo,a.privado,a.salida,a.nombre_html,a.titulo),ensure_ascii=False))
if __name__=='__main__':main()
