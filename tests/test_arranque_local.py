import importlib.util
from pathlib import Path

import pytest
from sqlalchemy.exc import ArgumentError

RUTA = Path(__file__).resolve().parents[1] / 'scripts' / 'iniciar_local.py'
spec = importlib.util.spec_from_file_location('iniciar_local', RUTA)
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)


def configuracion():
    return {'ITSANET_LOCAL': '1',
            'VAL_DATABASE_URL': 'mysql+pymysql://itsanet_dev:prueba@mysql:3306/itsanet_desarrollo?charset=utf8mb4',
            'VAL_DATA_DIR': '/var/lib/itsanet',
            'ITSANET_LOCAL_ADMIN_PASSWORD': 'solo-pruebas-1234'}


def test_arranque_acepta_solo_destino_mysql_local():
    local.comprobar_destino(configuracion())


@pytest.mark.parametrize('campo,valor', [
    ('ITSANET_LOCAL', ''),
    ('VAL_DATABASE_URL', 'mysql+pymysql://itsanet_dev:prueba@192.168.4.94:3306/itsanet_desarrollo'),
    ('VAL_DATABASE_URL', 'mysql+pymysql://itsanet_dev:prueba@mysql:3306/iv_itsanet'),
    ('VAL_DATABASE_URL', 'mysql+pymysql://root:prueba@mysql:3306/itsanet_desarrollo'),
    ('VAL_DATABASE_URL', 'sqlite:////tmp/local.db'),
    ('VAL_DATABASE_URL', ''),
    ('VAL_DATA_DIR', '/opt/itsanet/data'),
    ('ITSANET_LOCAL_ADMIN_PASSWORD', '1234'),
])
def test_rechaza_produccion_y_configuracion_incompleta_antes_de_importar_app(campo, valor):
    env = configuracion()
    env[campo] = valor
    with pytest.raises((ValueError, ArgumentError)):
        local.comprobar_destino(env)
