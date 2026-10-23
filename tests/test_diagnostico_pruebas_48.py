"""El diagnóstico no muta datos ni revela credenciales; las consultas fallan pronto."""
import json

import httpx
import pytest

from app import config
from app.models import AppConfig, AppEntrega, Operador, Rol
from app.services import entregas, integraciones
from scripts import diagnosticar_google_pruebas as diagnostico

CLAVE = 'secreto-sintetico-no-publicar-' * 2
URL = 'https://script.google.com/macros/s/despliegue-reservado/exec'


def configurar(db, monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'DATA_DIR', tmp_path)
    db.add(Operador(usuario='supervisor.prueba', nombre='Supervisor de pruebas',
        email='sup@example.test', rol=Rol.SUPERVISOR, pin_hash='no-autenticado'))
    db.commit()
    integraciones.guardar_google(db, {'supervisor': 'sup@example.test', 'url': URL, 'secreto': CLAVE}, 'admin')


def test_rechaza_fuera_de_pruebas_antes_de_abrir_base(monkeypatch, capsys):
    monkeypatch.delenv('ITSANET_PRUEBAS_PUBLICAS', raising=False)
    assert diagnostico.main() == 2
    assert 'solo se permite' in capsys.readouterr().err


def test_sin_configuracion_identifica_ficha_sin_correo_y_no_llama_google(db, monkeypatch):
    db.add(Operador(usuario='supervisor.prueba', nombre='Prueba', rol=Rol.SUPERVISOR, pin_hash='no'))
    db.commit()
    monkeypatch.setattr(entregas, 'llamar_conexion', lambda *a: pytest.fail('No debe contactar Google'))
    r = diagnostico.diagnosticar(db)
    assert r['perfiles'][0]['correoRegistrado'] is False
    assert r['conexionesRegistradas'] == 0 and 'no tiene un puente' in r['accion']
    assert db.query(AppEntrega).count() == 0


def test_estado_firmado_sin_exponer_secretos_ni_escribir(db, monkeypatch, tmp_path):
    configurar(db, monkeypatch, tmp_path)
    antes = [(f.clave, json.dumps(f.datos, sort_keys=True)) for f in db.query(AppConfig).all()]
    acciones = []
    def google(accion, clave, datos, conexion):
        acciones.append(accion)
        assert datos == {'usuario': 'sup@example.test'} and conexion['secreto'] == CLAVE
        return {'remitente': 'sup@example.test', 'carpeta': 'https://drive.google.com/drive/folders/privada',
                'capacidades': ['fotosAuditables']}
    monkeypatch.setattr(entregas, 'llamar_conexion', google)
    r = diagnostico.diagnosticar(db)
    assert acciones == ['estado'] and r['conexiones'][0]['verificacion'] == 'Confirmada'
    assert r['conexiones'][0]['fotosAuditables'] and r['conexiones'][0]['carpetaConfirmada']
    texto = json.dumps(r)
    for secreto in (CLAVE, URL, '/folders/privada', 'credencial'):
        assert secreto not in texto
    assert antes == [(f.clave, json.dumps(f.datos, sort_keys=True)) for f in db.query(AppConfig).all()]
    assert db.query(AppEntrega).count() == 0


def test_sin_red_y_correo_duplicado_no_consultan_google(db, monkeypatch, tmp_path):
    configurar(db, monkeypatch, tmp_path)
    monkeypatch.setattr(entregas, 'llamar_conexion', lambda *a: pytest.fail('Sin conexión externa'))
    assert 'Omitida' in diagnostico.diagnosticar(db, red=False)['conexiones'][0]['verificacion']
    db.add(Operador(usuario='duplicado', email='sup@example.test', nombre='Duplicado', rol=Rol.OPERADOR, pin_hash='no'))
    db.commit()
    r = diagnostico.diagnosticar(db)
    assert not r['conexiones'][0]['fichaActivaCoincide']
    assert r['perfiles'][0]['correoRepetido']


@pytest.mark.parametrize('error,fragmento', [(httpx.ReadTimeout, 'tiempo de espera'), (httpx.ConnectError, 'no pudo conectar')])
def test_verificacion_google_limita_espera_y_no_filtra_error_externo(monkeypatch, error, fragmento):
    original = httpx.Client
    tiempos = []
    def solicitud(req): raise error(CLAVE, request=req)
    def cliente(**kwargs):
        tiempos.append(kwargs['timeout'])
        return original(**kwargs, transport=httpx.MockTransport(solicitud))
    monkeypatch.setattr(httpx, 'Client', cliente)
    with pytest.raises(RuntimeError) as e:
        entregas.llamar_conexion('estado', 'a' * 32, {'usuario': 'sup@example.test'}, {'url': URL, 'secreto': CLAVE})
    assert fragmento in str(e.value) and CLAVE not in str(e.value)
    assert tiempos[0].read == 25 and tiempos[0].connect == 8


def test_transferencias_conservan_timeout_y_error_original(monkeypatch):
    original = httpx.Client
    tiempos = []
    def solicitud(req): raise httpx.ReadTimeout('resultado incierto', request=req)
    def cliente(**kwargs):
        tiempos.append(kwargs['timeout'])
        return original(**kwargs, transport=httpx.MockTransport(solicitud))
    monkeypatch.setattr(httpx, 'Client', cliente)
    with pytest.raises(httpx.ReadTimeout):
        entregas.llamar_conexion('finalizar', 'a' * 32, {}, {'url': URL, 'secreto': CLAVE})
    assert tiempos == [120]


def test_error_interno_del_diagnostico_no_filtra_valores(db, monkeypatch, tmp_path):
    configurar(db, monkeypatch, tmp_path)
    def falla(*a): raise ValueError(CLAVE)
    monkeypatch.setattr(entregas, 'llamar_conexion', falla)
    r = diagnostico.diagnosticar(db)
    assert 'ValueError' in r['conexiones'][0]['verificacion']
    assert CLAVE not in json.dumps(r)


def test_redacta_url_y_clave_si_un_error_futuro_las_incluye(db, monkeypatch, tmp_path):
    configurar(db, monkeypatch, tmp_path)
    def falla(*a): raise RuntimeError('Error con ' + URL + ' ' + CLAVE)
    monkeypatch.setattr(entregas, 'llamar_conexion', falla)
    r = diagnostico.diagnosticar(db)
    assert '[reservado]' in r['conexiones'][0]['verificacion']
    assert CLAVE not in json.dumps(r) and URL not in json.dumps(r)
