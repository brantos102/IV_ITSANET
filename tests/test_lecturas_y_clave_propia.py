"""Lecturas reales con metadatos y cambio privado de contraseña."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from app.main import app
from app.models import AppAuditoriaGeneral, AppPresencia, AppSku, Operador, Producto, Rol
from app.security import hash_pin
from app.services import lecturas


@pytest.fixture
def piezas(cliente, db):
    assert cliente.post('/api/app/recepciones', json={'codigo': 'LECTURAS', 'cliente': 'VENTURA'}).status_code == 201
    for sku in ['2GJ805901C', '2GJ941113', '000123', 'P555', 'SKU12300000', '7610022DRS0200']:
        db.add(Producto(sku=sku, cliente='VENTURA'))
        db.add(AppSku(recepcion='LECTURAS', sku=sku, esperado=6, contado=0, estado='PENDIENTE'))
    db.commit()
    return db


@pytest.mark.parametrize('raw, esperado', [
    ("2GJ'805'901'C '04100000", '2GJ805901C'),
    ('2GJ-941-113       00000', '2GJ941113'),
    ('2GJ-941-113\t00000', '2GJ941113'),
    ('2GJ’805’901’C 04100000', '2GJ805901C'),
    (']C12GJ-941-113 00000', '2GJ941113'),
    ('SKU: 2GJ\'805\'901\'C; QTY: 6', '2GJ805901C'),
    ('000123', '000123'),
    ('P555', 'P555'),
    ('SKU12300000', 'SKU12300000'),
    (json.dumps({'partNumber': '7610022DRS0200', 'qty': 6, 'date': '2024-12-09'}), '7610022DRS0200'),
])
def test_lectura_contrastada_sin_registrar_ni_alterar_conteos(piezas, raw, esperado):
    r = lecturas.resolver(piezas, raw, 'LECTURAS')
    assert r['resuelto'] and not r['confirmar'] and r['sku'] == esperado
    assert piezas.scalar(select(AppSku.contado).where(AppSku.sku == esperado)) == 0


def test_sufijo_sin_limite_de_campo_exige_confirmacion(piezas):
    r = lecturas.resolver(piezas, '2GJ94111300000', 'LECTURAS')
    assert not r['resuelto'] and r['confirmar'] and r['candidatos'] == ['2GJ941113']


def test_dos_codigos_reales_no_se_eligen_en_silencio(piezas):
    r = lecturas.resolver(piezas, '2GJ-941-113 2GJ805901C', 'LECTURAS')
    assert not r['resuelto'] and r['confirmar']
    assert r['candidatos'] == ['2GJ805901C', '2GJ941113']


def test_codigo_completo_y_parcial_ambos_validos_se_consultan(piezas):
    piezas.add(Producto(sku='2GJ94111300000', cliente='VENTURA')); piezas.commit()
    r = lecturas.resolver(piezas, '2GJ-941-113 00000', 'LECTURAS')
    assert r['confirmar'] and set(r['candidatos']) == {'2GJ941113', '2GJ94111300000'}
    assert lecturas.resolver(piezas, '2GJ94111300000', 'LECTURAS')['sku'] == '2GJ94111300000'


@pytest.mark.parametrize('raw', [
    "ZZZ'999'998'A '04100000", 'ZZZ-999-998     00000',
    '{"qty":"000123","lot":"P555"}', 'https://ejemplo.test/?qty=000123&lot=P555', '??? 000123', 'https://[incompleto',
    json.dumps({'sku': '0' * 2000}),
])
def test_no_crear_adicional_con_metadatos_no_identificados(piezas, raw):
    r = lecturas.resolver(piezas, raw, 'LECTURAS')
    assert not r['resuelto'] and not r['confirmar'] and r['sku'] is None


def entrar(usuario='op1', pin='2222'):
    c = TestClient(app)
    r = c.post('/api/auth/login', json={'usuario': usuario, 'pin': pin})
    assert r.status_code == 200
    return c, r.json()['token']


def test_cambio_propio_cierra_solo_otras_sesiones_y_no_expone_claves(cliente, db, operadores):
    c, token = entrar(); otro, segundo = entrar(); ajeno, _ = entrar('op2', '3333')
    assert cliente.post('/api/app/recepciones', json={'codigo': 'PRESENCIAS'}).status_code == 201
    for dispositivo, t in [('actual', token), ('otra', segundo)]:
        db.add(AppPresencia(recepcion='PRESENCIAS', dispositivo=dispositivo,
            operador_id=operadores['op1'].id, sesion_hash=hashlib.sha256(t.encode()).hexdigest(), actividad='CONTANDO'))
    db.commit()
    anterior = operadores['op1'].pin_hash
    r = c.post('/api/auth/clave', json={'actual': '2222', 'nueva': 'Mi nueva clave 29'})
    assert r.status_code == 200 and r.json()['sesionesCerradas'] == 1
    assert c.get('/api/auth/yo').status_code == 200
    assert otro.get('/api/auth/yo').status_code == 401
    assert ajeno.get('/api/auth/yo').status_code == 200
    assert TestClient(app).post('/api/auth/login', json={'usuario':'op1','pin':'2222'}).status_code == 401
    assert entrar('op1', 'Mi nueva clave 29')
    db.rollback(); db.expire_all()
    assert db.scalars(select(AppPresencia.dispositivo)).all() == ['actual']
    audit = db.scalar(select(AppAuditoriaGeneral).where(AppAuditoriaGeneral.accion == 'CAMBIO_CLAVE_PROPIA'))
    assert audit.usuario == 'op1' and audit.datos == {'sesionesCerradas': 1}
    assert all(secreto not in json.dumps(audit.datos) for secreto in ['2222', 'Mi nueva clave 29', anterior])


@pytest.mark.parametrize('datos, estado', [
    ({'actual':'erronea','nueva':'nueva-valida'}, 401),
    ({'actual':'2222','nueva':'123'}, 422),
    ({'actual':'2222','nueva':'nueva-valida','usuario':'op2'}, 422),
    ({'actual':'2222','nueva':123456}, 422),
    ({'actual':'2222','nueva':'x'*129}, 422),
])
def test_cambio_rechazado_conserva_sesiones_y_clave(cliente, db, datos, estado):
    c, _ = entrar(); otro, _ = entrar()
    r = c.post('/api/auth/clave', json=datos)
    assert r.status_code == estado
    if estado == 401: assert r.json()['detail']['codigo'] == 'CLAVE_ACTUAL_INVALIDA'
    assert c.get('/api/auth/yo').status_code == otro.get('/api/auth/yo').status_code == 200
    assert not db.scalars(select(AppAuditoriaGeneral).where(AppAuditoriaGeneral.accion == 'CAMBIO_CLAVE_PROPIA')).all()
    assert entrar()


def test_cambio_exige_sesion_y_admite_bearer(cliente):
    assert TestClient(app).post('/api/auth/clave', json={'actual':'2222','nueva':'nueva-valida'}).status_code == 401
    _, token = entrar()
    c = TestClient(app)
    assert c.post('/api/auth/clave', headers={'Authorization':'Bearer '+token}, json={'actual':'2222','nueva':'nueva-valida'}).status_code == 200
    assert c.get('/api/auth/yo', headers={'Authorization':'Bearer '+token}).status_code == 200


@pytest.mark.parametrize('usuario, actual', [('sup', '1111'), ('admin-clave', 'admin-anterior')])
def test_todos_los_roles_cambian_su_propia_clave(cliente, db, usuario, actual):
    db.add(Operador(usuario='admin-clave', nombre='Admin', rol=Rol.ADMIN, pin_hash=hash_pin('admin-anterior')))
    db.commit()
    c, _ = entrar(usuario, actual)
    assert c.post('/api/auth/clave', json={'actual': actual, 'nueva': 'nueva-privada'}).status_code == 200
    assert entrar(usuario, 'nueva-privada')
    assert entrar('op2', '3333')


def test_dos_cambios_simultaneos_no_sobrescriben_clave(cliente, db):
    if db.bind.dialect.name != 'mysql':
        pytest.skip('Requiere bloqueo de filas real de MySQL')
    a, _ = entrar(); b, _ = entrar(); inicio = Barrier(2)
    def cambiar(c, nueva):
        inicio.wait(timeout=10)
        return nueva, c.post('/api/auth/clave', json={'actual': '2222', 'nueva': nueva}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = list(pool.map(lambda p: cambiar(*p), [(a, 'nueva-uno'), (b, 'nueva-dos')]))
    assert sorted(estado for _, estado in resultados) == [200, 401]
    ganadora = next(clave for clave, estado in resultados if estado == 200)
    assert entrar('op1', ganadora)
    db.rollback()
    assert len(db.scalars(select(AppAuditoriaGeneral).where(AppAuditoriaGeneral.accion == 'CAMBIO_CLAVE_PROPIA')).all()) == 1
