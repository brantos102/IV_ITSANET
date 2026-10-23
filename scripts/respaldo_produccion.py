#!/usr/bin/env python3
"""Respaldo MySQL y archivos antes del pase. No importa ni migra la aplicación."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

from sqlalchemy.engine import make_url


def opcion(valor):
    return '"' + str(valor).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r') + '"'


def parametros(repo, salida):
    u = make_url(os.environ.get('VAL_DATABASE_URL', ''))
    if not u.drivername.startswith(('mysql', 'mariadb')) or not u.database:
        raise ValueError('Se requiere la conexión MySQL del servicio de producción')
    if not u.username:
        raise ValueError('La conexión MySQL no identifica al usuario')
    ejecutable = shutil.which('mysqldump') or shutil.which('mariadb-dump')
    if not ejecutable:
        raise ValueError('Falta mysqldump o mariadb-dump en el servidor; no se ha detenido el servicio')
    datos = Path(os.environ.get('VAL_DATA_DIR', str(repo / 'data'))).resolve()
    if not datos.is_dir():
        raise ValueError('No se encuentra VAL_DATA_DIR; no se puede respaldar la evidencia')
    if salida == datos or datos in salida.parents:
        raise ValueError('El respaldo debe estar fuera de VAL_DATA_DIR')
    # No degradar una conexión que requiere TLS ni omitir opciones desconocidas.
    if set(u.query) - {'charset', 'unix_socket'}:
        raise ValueError('La conexión usa opciones especiales; preparar un respaldo compatible antes del pase')
    opciones = {'user': u.username, 'password': u.password or '', 'host': u.host or 'localhost',
        'port': u.port or 3306, 'default-character-set': u.query.get('charset', 'utf8mb4')}
    if u.query.get('unix_socket'): opciones['socket'] = u.query['unix_socket']
    return ejecutable, u.database, opciones, datos


def respaldar(repo, salida, revision):
    ejecutable, base, opciones, datos = parametros(repo, salida)
    salida.mkdir(mode=0o700, parents=True, exist_ok=True)
    if any((salida / n).exists() for n in ('mysql.sql.gz', 'archivos.tar.gz', 'respaldo.json')):
        raise ValueError('El destino ya contiene un respaldo; no se sobrescribe')
    with tempfile.TemporaryDirectory(prefix='.conexion-', dir=salida) as t:
        privado = Path(t) / 'mysql.cnf'
        privado.write_text('[client]\n' + '\n'.join(k + '=' + opcion(v) for k, v in opciones.items()) + '\n')
        privado.chmod(0o600)
        with (salida / 'mysql-error.log').open('wb') as errores, gzip.open(salida / 'mysql.sql.gz', 'wb') as destino:
            p = subprocess.Popen([ejecutable, '--defaults-extra-file=' + str(privado), '--single-transaction',
                '--quick', '--skip-lock-tables', '--no-tablespaces', '--hex-blob', '--databases', base],
                stdout=subprocess.PIPE, stderr=errores)
            try:
                shutil.copyfileobj(p.stdout, destino)
            finally:
                p.stdout.close()
            if p.wait() != 0:
                raise RuntimeError('Falló el respaldo MySQL; el detalle queda en mysql-error.log privado. No actualizar el código.')
    # Leer hasta el final verifica también el CRC del gzip antes del pase.
    with gzip.open(salida / 'mysql.sql.gz', 'rb') as f:
        contenido = 0
        while bloque := f.read(1024 * 1024): contenido += len(bloque)
    if contenido < 100: raise RuntimeError('El respaldo MySQL está vacío o incompleto')
    with tarfile.open(salida / 'archivos.tar.gz', 'w:gz') as t:
        t.add(datos, arcname='datos', recursive=True)
    with tarfile.open(salida / 'archivos.tar.gz', 'r:gz') as t:
        for miembro in t:
            if miembro.isfile():
                with t.extractfile(miembro) as f:
                    while f.read(1024 * 1024): pass
    sumas = {}
    for nombre in ('mysql.sql.gz', 'archivos.tar.gz'):
        with (salida / nombre).open('rb') as f:
            sumas[nombre] = hashlib.file_digest(f, 'sha256').hexdigest()
    (salida / 'respaldo.json').write_text(json.dumps({'revisionAnterior': revision,
        'dataDir': str(datos), 'sha256': sumas}, indent=2) + '\n')
    print('Respaldo verificado: ' + str(salida))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--salida', type=Path, required=True)
    p.add_argument('--revision', required=True)
    p.add_argument('--comprobar', action='store_true')
    args = p.parse_args()
    os.umask(0o077)
    try:
        if args.comprobar:
            parametros(args.repo.resolve(), args.salida.resolve())
            print('Requisitos del respaldo comprobados; no se modificaron datos')
        else:
            respaldar(args.repo.resolve(), args.salida.resolve(), args.revision)
    except Exception as e:
        # Las excepciones de parseo podrían contener una URL con contraseña.
        mensaje = str(e) if isinstance(e, (RuntimeError, ValueError)) and '://' not in str(e) else type(e).__name__
        raise SystemExit('No se completó el respaldo: ' + mensaje) from None


if __name__ == '__main__': main()
