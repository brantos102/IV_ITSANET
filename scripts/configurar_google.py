#!/usr/bin/env python3
"""Configura solo el puente de IV_ITSANET; no modifica otros servicios."""
import argparse
import os
from pathlib import Path
import re
import secrets
import tempfile

URL = 'https://script.google.com/macros/s/AKfycbzFIs_s0B83ZqmayIVoOXi1SEJox_McRxHSmFEDcWHGy3kG5C6Rs20qRKD5MASZjEoG/exec'


def configurar(ruta, url):
    if not re.fullmatch(r'https://script\.google\.com/macros/s/[A-Za-z0-9_-]+/exec', url):
        raise ValueError('Se requiere la URL /exec de Apps Script')
    anterior = ruta.read_text()
    lineas = anterior.splitlines(keepends=True)
    valor = next((l.split('=', 1)[1].strip().strip('"\'') for l in lineas
        if l.startswith('VAL_GOOGLE_PROXY_SECRET=')), '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', valor):
        valor = secrets.token_hex(32)
    nuevas = {'VAL_GOOGLE_PROXY_URL': url, 'VAL_GOOGLE_PROXY_SECRET': valor}
    # Conservar sin interpretar todos los valores ajenos, incluidas las credenciales MySQL.
    salida = ''.join(l for l in lineas if not any(l.startswith(k + '=') for k in nuevas))
    if salida and not salida.endswith('\n'):
        salida += '\n'
    salida += ''.join(f'{k}={v}\n' for k, v in nuevas.items())
    fd, temporal = tempfile.mkstemp(prefix='.iv-itsanet-', dir=ruta.parent)
    try:
        stat = ruta.stat()
        with os.fdopen(fd, 'w') as f:
            f.write(salida)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temporal, 0o600)
        if os.geteuid() == 0:
            os.chown(temporal, stat.st_uid, stat.st_gid)
        os.replace(temporal, ruta)
    finally:
        Path(temporal).unlink(missing_ok=True)
    return valor


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default=URL)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Ejecuta con sudo: configura /etc/iv-itsanet.env sin hacerlo legible a otros usuarios')
    clave = configurar(Path('/etc/iv-itsanet.env'), args.url)
    print('Configuracion guardada. En las propiedades del Apps Script, configura SERVIDOR_HMAC con:')
    print(clave)
    print('Copia esta clave solo en Apps Script. No la pegues en chats ni en GitHub.')
    print('No se ha reiniciado ningun servicio. Actualiza el despliegue del script antes del reinicio de IV_ITSANET.')
