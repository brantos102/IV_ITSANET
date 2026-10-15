"""Entrada exclusiva del contenedor local; comprueba destino antes de importar app."""
import os
from pathlib import Path
import sys

from sqlalchemy.engine import make_url


def comprobar_destino(entorno):
    url = make_url(entorno.get('VAL_DATABASE_URL', ''))
    if (entorno.get('ITSANET_LOCAL') != '1' or url.drivername != 'mysql+pymysql'
            or url.host != 'mysql' or url.port != 3306
            or url.database != 'itsanet_desarrollo' or url.username != 'itsanet_dev'
            or entorno.get('VAL_DATA_DIR') != '/var/lib/itsanet'
            or len(entorno.get('ITSANET_LOCAL_ADMIN_PASSWORD', '')) < 12):
        raise ValueError('Arranque local rechazado: requiere base, usuario y archivos de desarrollo')


def main():
    comprobar_destino(os.environ)
    # Al invocarse como archivo, Python incluye scripts/ y no el repositorio.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from sqlalchemy import select
    from app.db import SessionLocal, init_db
    from app.models import Operador, Rol
    from app.security import hash_pin

    init_db()
    with SessionLocal() as db:
        if db.scalar(select(Operador).limit(1)) is None:
            db.add(Operador(usuario='admin', nombre='Administrador de pruebas',
                pin_hash=hash_pin(os.environ['ITSANET_LOCAL_ADMIN_PASSWORD']), rol=Rol.ADMIN))
            db.commit()
    print('Desarrollo local: MySQL y archivos independientes; interfaces en /app/.', flush=True)
    os.execvp('uvicorn', ['uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '3002',
                         '--reload', '--reload-dir', '/opt/itsanet/app'])


if __name__ == '__main__':
    main()
