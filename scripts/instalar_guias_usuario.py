"""Publica el nuevo HTML/PDF de usuario sin actualizar el aplicativo ni reiniciarlo."""
import argparse
import base64
import getpass
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import tempfile
from zipfile import ZipFile
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def leer_paquete(bruto,clave):
    with ZipFile(io.BytesIO(bruto)) as z:
        if len(z.namelist())!=1:raise ValueError('Paquete documental inválido.')
        h=z.read(z.namelist()[0]).decode()
    inicio=h.index('const datos=')+len('const datos=');fin=h.index(',de64=',inicio)
    p=json.loads(h[inicio:fin]);de64=lambda s:base64.b64decode(s,validate=True)
    key=PBKDF2HMAC(algorithm=hashes.SHA256(),length=32,salt=de64(p['salt']),iterations=310000).derive(clave.encode())
    contenido=AESGCM(key).decrypt(de64(p['iv']),de64(p['contenido']),b'IV-ITSANET-GUIAS-1')
    d=json.loads(gzip.decompress(contenido))
    if d.get('formato')!='IV-ITSANET-GUIAS-1':raise ValueError('Formato documental inválido.')
    archivos={}
    for f in d['archivos']:
        b=de64(f['base64'])
        if hashlib.sha256(b).hexdigest()!=f['sha256']:raise ValueError('Documento incompleto.')
        archivos[f['nombre']]=b
    return archivos


def instalar(repo,revision,clave):
    repo=Path(repo).resolve()
    if not re.fullmatch(r'[a-f0-9]{40}',revision):raise ValueError('Utiliza la revisión completa de 40 caracteres.')
    archivos={}
    for tipo in ('HTML','PDF'):
        ruta='docs/descargas/IV-ITSANET-Guias-'+tipo+'-20261111.zip'
        bruto=subprocess.check_output(['git','show',revision+':'+ruta],cwd=repo)
        archivos.update(leer_paquete(bruto,clave))
    spec=importlib.util.spec_from_file_location('publicador_manual',repo/'scripts/publicar_manuales.py')
    modulo=importlib.util.module_from_spec(spec);spec.loader.exec_module(modulo)
    with tempfile.TemporaryDirectory(prefix='iv-guias-') as t:
        h=Path(t)/'usuario.html';p=Path(t)/'usuario.pdf'
        h.write_bytes(archivos['Manual-usuario-IV-ITSANET.html']);p.write_bytes(archivos['Manual-usuario-IV-ITSANET.pdf'])
        meta=modulo.publicar(h,p,repo/'documentacion/manuales',revision)
    return meta


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,required=True);p.add_argument('--revision',required=True);a=p.parse_args()
    try:
        clave=getpass.getpass('Clave documental de la entrega: ')
        meta=instalar(a.repo,a.revision,clave)
    except Exception as e:p.exit(1,'No se publicaron las guías ('+type(e).__name__+'). Comprueba la clave y la revisión; no se reiniciaron servicios.\n')
    print('Guías de usuario publicadas. Versión documental:',meta['version'])
    print('Ver en línea: https://apps.flexnetuio.com:8443/api/app/manuales/usuario/html')
    print('Descargar HTML: https://apps.flexnetuio.com:8443/api/app/manuales/usuario/html?descargar=true')
    print('No se modificaron recepciones, cuentas ni dispositivos. No se reiniciaron servicios.')


if __name__=='__main__':main()
