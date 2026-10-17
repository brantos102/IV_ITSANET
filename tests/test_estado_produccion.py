"""Diagnóstico separado de app.main y de cualquier migración de producción."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

RUTA = Path(__file__).resolve().parents[1] / 'scripts' / 'estado_produccion.py'
spec = importlib.util.spec_from_file_location('estado_produccion', RUTA)
estado = importlib.util.module_from_spec(spec)
spec.loader.exec_module(estado)


def captura():
    return {'formato': 1, 'capturado_utc': '2026-10-15T12:00:00+00:00',
        'capturado_ecuador': '2026-10-15T07:00:00-05:00',
        'mysql': {'identidad': 'base-uno', 'tablas': [
            {'nombre': 'app_eventos', 'filas_estimadas': 10, 'datos_bytes': 16384, 'indices_bytes': 0}],
            'archivos': [{'tipo': 'foto', 'destino': 'PENDIENTE', 'cantidad': 2, 'contenido_bytes': 300}],
            'entregas': [{'estado': 'PENDIENTE', 'cantidad': 1}], 'recepciones': []}}


def test_crecimiento_y_fotos_trasladadas_no_se_confunden_con_borrado():
    antes = captura()
    ahora = copy.deepcopy(antes)
    ahora.update(capturado_utc='2026-10-15T22:00:00+00:00', capturado_ecuador='2026-10-15T17:00:00-05:00')
    ahora['mysql']['tablas'][0]['filas_estimadas'] = 200
    ahora['mysql']['archivos'] = [{'tipo': 'foto', 'destino': 'DRIVE', 'cantidad': 2, 'contenido_bytes': 300}]
    cambio = estado.diferencia(ahora, antes)
    assert cambio['asignacion_mysql_bytes'] == 0
    assert cambio['tablas'][0]['filas_estimadas'] == 190
    assert cambio['segundos'] == 36000
    assert cambio['cambio_por_estado']['archivos'] == [
        {'tipo': 'foto', 'destino': 'DRIVE', 'cantidad': 2, 'contenido_bytes': 300},
        {'tipo': 'foto', 'destino': 'PENDIENTE', 'cantidad': -2, 'contenido_bytes': -300}]


def test_no_comparar_otra_base_captura_anterior_o_consulta_fallida():
    antes, ahora = captura(), captura()
    ahora['mysql']['identidad'] = 'otra'
    with pytest.raises(ValueError):
        estado.diferencia(ahora, antes)
    ahora = captura()
    with pytest.raises(ValueError):
        estado.diferencia(ahora, antes)
    ahora['mysql'] = None
    with pytest.raises(ValueError):
        estado.diferencia(ahora, antes)


def test_seccion_no_disponible_no_se_convierte_en_cero():
    antes, ahora = captura(), captura()
    ahora['capturado_utc'] = '2026-10-15T22:00:00+00:00'
    ahora['mysql']['archivos'] = None
    ahora['mysql']['tablas'][0]['datos_bytes'] = None
    cambio = estado.diferencia(ahora, antes)
    assert cambio['cambio_por_estado']['archivos'] is None
    assert cambio['asignacion_mysql_bytes'] is None


def test_disco_no_lee_contenido_ni_sigue_enlaces(tmp_path):
    carpeta = tmp_path / 'app_archivos'
    carpeta.mkdir()
    (carpeta / 'foto').write_bytes(b'abc')
    (carpeta / 'informe').write_bytes(b'12345')
    (carpeta / 'enlace').symlink_to('/etc/passwd')
    assert estado.disco(tmp_path) == {'estado': 'ok', 'archivos': 2, 'bytes': 8}
    assert estado.disco(tmp_path / 'ausente')['bytes'] is None


def test_fallo_no_filtra_claves_no_inicia_app_ni_crea_carpeta_de_datos(tmp_path):
    env = {**os.environ, 'VAL_DATABASE_URL': 'mysql+pymysql://persona:SECRETO@127.0.0.1:1/base',
           'VAL_DATA_DIR': str(tmp_path / 'datos-no-crear')}
    p = subprocess.run([sys.executable, str(RUTA), '--repo', str(RUTA.parents[1]),
                        '--salida', str(tmp_path / 'reportes')], env=env, capture_output=True, text=True)
    assert p.returncode == 2
    assert not (tmp_path / 'datos-no-crear').exists()
    reporte = next((tmp_path / 'reportes').glob('*.json'))
    datos = json.loads(reporte.read_text())
    assert datos['mysql'] is None
    assert 'SECRETO' not in reporte.read_text() + p.stdout + p.stderr
    assert reporte.stat().st_mode & 0o077 == 0


def test_consultas_reales_mysql_solo_lectura_y_cifras():
    url = os.environ.get('ITSANET_DIAGNOSTICO_MYSQL_URL')
    if not url:
        pytest.skip('Requiere MySQL aislado itsanet_diagnostico_test; no usa VAL_DATABASE_URL')
    import pymysql
    from sqlalchemy.engine import make_url
    u = make_url(url)
    assert u.database == 'itsanet_diagnostico_test', 'Nunca crear fixtures en otra base'
    con = pymysql.connect(host=u.host, port=u.port or 3306, user=u.username,
                          password=u.password, database=u.database, autocommit=True)
    creadas = []
    try:
        with con.cursor() as c:
            # Sin IF NOT EXISTS: si hay tablas previas se rechaza; no se reutilizan ni vacían.
            c.execute('CREATE TABLE app_archivos (tipo VARCHAR(20), drive_id VARCHAR(128), bytes INT)')
            creadas.append('app_archivos')
            c.execute('CREATE TABLE app_entregas (estado VARCHAR(20))')
            creadas.append('app_entregas')
            c.execute('CREATE TABLE app_recepciones (estado VARCHAR(20))')
            creadas.append('app_recepciones')
            c.execute("INSERT INTO app_archivos VALUES ('foto', NULL, 123), ('foto', 'id-drive', 456)")
            c.execute("INSERT INTO app_entregas VALUES ('PENDIENTE')")
            c.execute("INSERT INTO app_recepciones VALUES ('ABIERTA')")
        resultado = estado.base_mysql(url)
        assert not resultado['avisos']
        assert resultado['columnas_binarias'] == []
        assert sorted(resultado['archivos'], key=lambda f: f['destino']) == [
            {'tipo': 'foto', 'destino': 'DRIVE', 'cantidad': 1, 'contenido_bytes': 456},
            {'tipo': 'foto', 'destino': 'PENDIENTE', 'cantidad': 1, 'contenido_bytes': 123}]
        assert resultado['recepciones'] == [{'estado': 'ABIERTA', 'cantidad': 1}]
        with con.cursor() as c:
            c.execute('START TRANSACTION READ ONLY')
            with pytest.raises(pymysql.err.OperationalError) as error:
                c.execute("INSERT INTO app_entregas VALUES ('ENTREGADA')")
            assert error.value.args[0] == 1792
            con.rollback()
            c.execute('SELECT COUNT(*) FROM app_archivos')
            assert c.fetchone()[0] == 2
    finally:
        con.rollback()
        with con.cursor() as c:
            for tabla in reversed(creadas):
                c.execute('DROP TABLE ' + tabla)
        con.close()
