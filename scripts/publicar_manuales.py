"""Publica el par HTML/PDF del usuario; conserva el técnico solo en disco."""
from pathlib import Path
from datetime import datetime, timezone
from html.parser import HTMLParser
from uuid import uuid4
import argparse
import hashlib
import json
import os
import re

ROOT=Path(__file__).resolve().parents[1]

class Pasos(HTMLParser):
    def __init__(self):super().__init__();self.ids=[]
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if tag=='section' and 'step' in d.get('class','').split():self.ids.append(d.get('id'))

def comprobar_usuario(html,pdf):
    h=Path(html).read_text(encoding='utf-8');p=Path(pdf).read_bytes()
    parser=Pasos();parser.feed(h)
    if parser.ids!=['paso-'+str(i) for i in range(1,39)]:
        raise ValueError('El HTML de usuario debe contener exactamente los pasos 1 a 38. No publiques una copia antigua de 40 pasos.')
    if not p.startswith(b'%PDF-') or b'%%EOF' not in p[-4096:]:raise ValueError('El PDF de usuario no es válido o está incompleto.')
    return h,p

def escribir(path,contenido,modo=0o640):
    with path.open('xb') as f:
        os.chmod(path,modo);f.write(contenido);f.flush();os.fsync(f.fileno())

def sincronizar_directorio(path):
    if hasattr(os,'O_DIRECTORY'):
        fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)

def apuntar(raiz,version,modo):
    temporal=raiz/('.actual-'+uuid4().hex+'.json')
    escribir(temporal,json.dumps({'version':version}).encode(),modo)
    os.replace(temporal,raiz/'actual.json');sincronizar_directorio(raiz)

def instalar(raiz,version,archivos,revision,privado=False):
    modo_dir=0o700 if privado else 0o750;modo=0o600 if privado else 0o640
    versiones=raiz/'versiones';versiones.mkdir(parents=True,exist_ok=True,mode=modo_dir)
    raiz.chmod(modo_dir);versiones.chmod(modo_dir)
    temporal=versiones/('.preparando-'+uuid4().hex);temporal.mkdir(mode=modo_dir)
    for nombre,contenido in archivos.items():escribir(temporal/nombre,contenido,modo)
    meta={'version':version,'revision':revision,'sha256':{n:hashlib.sha256(c).hexdigest() for n,c in archivos.items()}}
    escribir(temporal/'publicacion.json',json.dumps(meta,ensure_ascii=False,indent=2).encode(),modo)
    sincronizar_directorio(temporal);os.replace(temporal,versiones/version);sincronizar_directorio(versiones)
    return meta

def publicar(html,pdf,destino,revision='',tecnico_html=None,tecnico_pdf=None):
    # Revisar todos los archivos antes de cambiar cualquier versión activa.
    texto,bruto=comprobar_usuario(html,pdf)
    if bool(tecnico_html)!=bool(tecnico_pdf):raise ValueError('El manual técnico requiere su HTML y PDF juntos.')
    tecnico=None
    if tecnico_html:
        th=Path(tecnico_html).read_bytes();tp=Path(tecnico_pdf).read_bytes()
        if b'<html' not in th.lower() or not tp.startswith(b'%PDF-') or b'%%EOF' not in tp[-4096:]:raise ValueError('El manual técnico HTML/PDF no es válido.')
        tecnico={'Manual-tecnico-IV-ITSANET.html':th,'Manual-tecnico-IV-ITSANET.pdf':tp}
    version=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-')+uuid4().hex[:12]
    enlace='/api/app/manuales/usuario/pdf?descargar=true&amp;version='+version
    texto=re.sub(r'<a\b[^>]*\bdata-pdf-publicado[^>]*>.*?</a>','',texto,flags=re.I|re.S)
    texto=texto.replace('</header>','<p class="edit"><a href="'+enlace+'" data-pdf-publicado>Descargar PDF de esta versión</a></p></header>',1)
    destino=Path(destino);destino.mkdir(parents=True,exist_ok=True,mode=0o750)
    usuario=instalar(destino/'usuario',version,{'Manual-usuario-IV-ITSANET.html':texto.encode('utf-8'),'Manual-usuario-IV-ITSANET.pdf':bruto},revision)
    if tecnico:instalar(destino/'tecnico',version,tecnico,revision,privado=True)
    # Cada puntero cambia cuando su par completo ya existe. Se conserva el historial.
    if tecnico:apuntar(destino/'tecnico',version,0o600)
    apuntar(destino/'usuario',version,0o640)
    return usuario

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--usuario-html',type=Path,required=True);p.add_argument('--usuario-pdf',type=Path,required=True)
    p.add_argument('--tecnico-html',type=Path);p.add_argument('--tecnico-pdf',type=Path)
    p.add_argument('--destino',type=Path,default=ROOT/'documentacion/manuales');p.add_argument('--revision',default='')
    a=p.parse_args()
    try:r=publicar(a.usuario_html,a.usuario_pdf,a.destino,a.revision,a.tecnico_html,a.tecnico_pdf)
    except (OSError,ValueError) as e:p.exit(1,'No se publicó: '+str(e)+'\nLa versión activa anterior se conserva si no se completó el par de documentos.\n')
    print('Manual de usuario publicado. Versión:',r['version'])
    print('Acceso con sesión: https://apps.flexnetuio.com:8443/api/app/manuales/usuario/html')
    print('Documentos técnicos: solo en disco, dentro de',a.destino/'tecnico/versiones'/r['version'])
    print('No se reiniciaron servicios ni se modificaron registros operativos.')

if __name__=='__main__':main()
