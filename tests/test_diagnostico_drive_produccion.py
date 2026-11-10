import hashlib
import json
import time

from cryptography.fernet import Fernet
import httpx
import pymysql
import pytest

from scripts import diagnosticar_drive_produccion as d
from app.services import google_cuentas as g, google_drive_api as drive


def test_sql_diagnostico_lectura_acotada_y_parametros(monkeypatch):
    ejecutadas = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, params=()):
            ejecutadas.append((sql, params))
            self.sql = sql
        def fetchone(self): return {'version': '8.0-prueba'}
        def fetchall(self):
            if 'COUNT(*)' in self.sql: return [{'estado': 'PENDIENTE', 'cantidad': 31}]
            return []
    class Conexion:
        rollback_hecho = cerrado = False
        def cursor(self): return Cursor()
        def rollback(self): self.rollback_hecho = True
        def close(self): self.cerrado = True
    con = Conexion()
    monkeypatch.setattr(pymysql, 'connect', lambda **kw: con)
    estados, *resto = d.leer_base('mysql+pymysql://test:no-imprimir@localhost/prueba', ["R'123"])
    assert estados == {'PENDIENTE': 31} and con.cerrado and con.rollback_hecho
    assert all(sql.startswith(('SELECT', 'SET SESSION', 'START TRANSACTION READ ONLY')) for sql, _ in ejecutadas)
    consulta, parametros = next((sql, p) for sql, p in ejecutadas if 'JOIN app_archivos' in sql)
    assert "R'123" not in consulta and parametros == ("R'123",)
    assert 'LIMIT 101' in consulta


def test_verifica_originales_y_no_expone_credenciales(tmp_path):
    bruto = b'foto-original-sintetica'
    carpeta = tmp_path / 'app_archivos'
    carpeta.mkdir()
    (carpeta / 'foto123').write_bytes(bruto)
    f = {'archivo_id': 'foto123', 'recepcion': 'RECEP123', 'estado': 'PENDIENTE',
         'intentos': 16, 'usuario': 'supervisor@example.test', 'nombre': 'foto.jpg',
         'drive_id': None, 'sha256': hashlib.sha256(bruto).hexdigest(), 'bytes': len(bruto),
         'error': 'GOOGLE_NO_ENCONTRADO: error', 'datos': {'cliente': 'CLIENTE', 'ruta': ['GENERAL']}}
    configs = {'google_api': {'driveCuenta': 'drive@example.test', 'carpetaRaiz': 'RAIZ123'},
               'oauth_google': {'credencial': 'NO-EXPOSICION'}}
    resultado = d.diagnosticar({'PENDIENTE': 1}, [f], configs, {}, tmp_path)
    assert resultado['originalesLocales'] == {'INTEGRO': 1}
    assert resultado['destinos'][0]['reservasRuta'][0]['nombre'] == 'CLIENTE'
    assert resultado['pendientes'][0]['destino'] == 1
    assert 'NO-EXPOSICION' not in json.dumps(resultado)
    assert (carpeta / 'foto123').read_bytes() == bruto
    (carpeta / 'foto123').write_bytes(b'otra-imagen')
    assert d.original_local(tmp_path, f)['estado'] == 'DIFIERE_DEL_REGISTRO'
    (carpeta / 'foto123').unlink()
    assert d.original_local(tmp_path, f)['estado'] == 'AUSENTE'


def test_consulta_google_renueva_solo_en_memoria_y_hace_get_drive(tmp_path, monkeypatch):
    key = Fernet.generate_key()
    cifrador = Fernet(key)
    (tmp_path / 'secretos').mkdir()
    (tmp_path / 'secretos' / 'integraciones.key').write_bytes(key)
    def cifrar(obj): return cifrador.encrypt(json.dumps(obj).encode()).decode()
    cuenta = 'drive@example.test'
    configs = {'oauth_google': {'clientId': 'cliente', 'credencial': cifrar({'clientSecret': 'NO-MOSTRAR'})},
        g.clave(cuenta): {'estado': 'AUTORIZADA', 'scopes': [d.DRIVE], 'clientId': 'cliente',
            'credencial': cifrar({'refresh_token': 'NO-MOSTRAR-REFRESH', 'vence': time.time() - 1})}}
    copia = json.dumps(configs)
    llamadas = []
    class HTTP:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kw):
            llamadas.append(('POST', url))
            assert url == 'https://oauth2.googleapis.com/token'
            return httpx.Response(200, json={'access_token': 'NO-MOSTRAR-ACCESO'})
        def get(self, url, **kw):
            llamadas.append(('GET', url))
            return httpx.Response(404, json={'error': {'errors': [{'reason': 'notFound'}],
                'message': 'NO-MOSTRAR-MENSAJE'}})
    monkeypatch.setattr(httpx, 'Client', HTTP)
    remoto = d.LecturaGoogle(configs, tmp_path)
    r = remoto.ficha(cuenta, 'RESERVADO123')
    assert r['http'] == 404 and r['motivo'] == 'notFound'
    assert remoto.ficha(cuenta, 'RESERVADO123') == r and len(llamadas) == 2
    assert all(metodo == 'GET' for metodo, url in llamadas if 'drive/v3' in url)
    assert json.dumps(configs) == copia and 'NO-MOSTRAR' not in json.dumps(r)


@pytest.mark.parametrize('atajo', [False, True])
def test_no_oculta_error_de_creacion_con_404_de_id_reservado(db, monkeypatch, atajo):
    monkeypatch.setattr(drive, 'listar', lambda *a: [])
    monkeypatch.setattr(drive, 'generar', lambda *a: 'IDRESERVADO123')
    def falta(*args): raise RuntimeError('GOOGLE_NO_ENCONTRADO: HTTP 404')
    def denegado(*args, **kw): raise RuntimeError('GOOGLE_PERMISOS: HTTP 403; motivo insufficientFilePermissions')
    monkeypatch.setattr(drive, 'ficha', falta)
    monkeypatch.setattr(g, 'peticion', denegado)
    with pytest.raises(RuntimeError, match='GOOGLE_PERMISOS: HTTP 403'):
        if atajo:
            drive.atajo('drive@example.test', 'PADRE123', 'ARCHIVO123', 'Foto', 'clave')
        else:
            drive.carpeta('drive@example.test', 'PADRE123', 'Carpeta')


def test_carpeta_nueva_se_crea_automaticamente_y_no_duplica_respuesta_perdida(db, monkeypatch):
    remotos, creadas = {}, []
    monkeypatch.setattr(drive, 'listar', lambda *a: [])
    monkeypatch.setattr(drive, 'generar', lambda *a: 'PREINGRESO123')
    def ficha(cuenta, ident):
        if ident not in remotos:
            raise RuntimeError('GOOGLE_NO_ENCONTRADO: HTTP 404')
        return remotos[ident]
    def crear(*args, **kw):
        datos = kw['json']
        remotos[datos['id']] = datos
        creadas.append(datos['id'])
        raise RuntimeError('GOOGLE_RED: se perdió la confirmación')
    monkeypatch.setattr(drive, 'ficha', ficha)
    monkeypatch.setattr(g, 'peticion', crear)
    for _ in range(2):
        assert drive.carpeta('drive@example.test', 'RECEPCION123', 'PRE-INGRESO') == 'PREINGRESO123'
    assert creadas == ['PREINGRESO123']
    assert remotos['PREINGRESO123']['parents'] == ['RECEPCION123']


def test_error_google_informa_operacion_y_motivo_sin_cuerpo(monkeypatch):
    monkeypatch.setattr(g, 'acceso', lambda *args: 'NO-MOSTRAR-TOKEN')
    class HTTP:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def request(self, *args, **kw):
            return httpx.Response(403, json={'error': {'message': 'NO-MOSTRAR-MENSAJE',
                'errors': [{'reason': 'insufficientFilePermissions'}, {'reason': 'https://privado/token'}]}})
    monkeypatch.setattr(g.httpx, 'Client', HTTP)
    with pytest.raises(RuntimeError) as error:
        g.peticion('drive@example.test', 'drive', 'POST', 'files')
    texto = str(error.value)
    assert texto.startswith('GOOGLE_PERMISOS: HTTP 403 en POST drive/files; motivo insufficientFilePermissions')
    assert 'NO-MOSTRAR' not in texto and 'privado' not in texto
