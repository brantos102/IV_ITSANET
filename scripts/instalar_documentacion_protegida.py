"""Publica los manuales de una entrega cifrada de Git, sin tocar datos ni servicios."""
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
import zipfile
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

NOMBRES = {f'Manual-{tipo}-final-IV-ITSANET.{ext}'
           for tipo in ('usuario','tecnico') for ext in ('html','pdf')}


def descifrar(bruto, clave):
    with zipfile.ZipFile(io.BytesIO(bruto)) as z:
        entradas=z.infolist()
        if len(entradas)!=1 or entradas[0].file_size > 60*1024*1024:
            raise ValueError('Paquete no válido.')
        pagina=z.read(entradas[0]).decode('utf-8')
    coincidencia=re.search(r'<script id="cifrado" type="application/json">(.*?)</script>',pagina,re.S)
    if not coincidencia:
        raise ValueError('No se encontró la entrega cifrada.')
    d=json.loads(coincidencia[1]);n=d['iteraciones']
    if not 100000 <= n <= 1000000:
        raise ValueError('Parámetro de cifrado no válido.')
    salt=base64.b64decode(d['salt'],validate=True);iv=base64.b64decode(d['iv'],validate=True)
    key=PBKDF2HMAC(algorithm=hashes.SHA256(),length=32,salt=salt,iterations=n).derive(clave.encode())
    carga=AESGCM(key).decrypt(iv,base64.b64decode(d['contenido'],validate=True),b'IV-ITSANET-DESCARGA-1')
    datos=json.loads(gzip.decompress(carga))
    if datos['formato']!='IV-ITSANET-DESCARGA-1':
        raise ValueError('Formato de entrega no válido.')
    archivos={}
    for f in datos['archivos']:
        if f['nombre'] not in NOMBRES:
            continue
        contenido=base64.b64decode(f['base64'],validate=True)
        if len(contenido)!=f['bytes'] or hashlib.sha256(contenido).hexdigest()!=f['sha256']:
            raise ValueError('La integridad del documento no coincide.')
        if f['nombre'] in archivos:
            raise ValueError('Documento repetido en la entrega.')
        archivos[f['nombre']]=contenido
    return archivos


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,required=True)
    p.add_argument('--revision',required=True)
    a=p.parse_args();repo=a.repo.resolve()
    try:
        if not re.fullmatch('[a-f0-9]{40}',a.revision):
            raise ValueError('Usa la revisión completa de la entrega.')
        clave=getpass.getpass('Clave de descarga de los manuales: ').strip()
        archivos={}
        for nombre in ('IV-ITSANET-PDF-y-correo-38.zip','IV-ITSANET-HTML-38.zip'):
            bruto=subprocess.check_output(['git','show',a.revision+':docs/descargas/'+nombre],cwd=repo,stderr=subprocess.DEVNULL)
            for n,contenido in descifrar(bruto,clave).items():
                if n in archivos:
                    raise ValueError('Documento repetido entre paquetes.')
                archivos[n]=contenido
        if set(archivos)!=NOMBRES:
            raise ValueError('La entrega no contiene los cuatro documentos.')
        spec=importlib.util.spec_from_file_location('publicar',repo/'scripts/publicar_manuales.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        with tempfile.TemporaryDirectory(prefix='iv-manuales-') as temp:
            carpeta=Path(temp)
            for n,contenido in archivos.items():
                archivo=carpeta/n;archivo.write_bytes(contenido);archivo.chmod(0o600)
            meta=m.publicar(carpeta/'Manual-usuario-final-IV-ITSANET.html',
                carpeta/'Manual-usuario-final-IV-ITSANET.pdf',repo/'documentacion/manuales',a.revision,
                carpeta/'Manual-tecnico-final-IV-ITSANET.html',carpeta/'Manual-tecnico-final-IV-ITSANET.pdf')
        print('Manual de usuario publicado con autenticación:')
        print('https://apps.flexnetuio.com:8443/api/app/manuales/usuario/html')
        print('Manual técnico privado:',repo/'documentacion/manuales/tecnico/versiones'/meta['version'])
        print('No se modificaron registros ni se reiniciaron servicios.')
    except Exception as exc:
        p.exit(1,'No se completó la publicación. Tipo: '+type(exc).__name__+
               '. Revisa la clave, la revisión y los permisos de la carpeta.\n')


if __name__=='__main__':
    main()
