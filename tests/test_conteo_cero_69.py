"""El mismo registro operativo permite declarar cero sin alterar unidades previas."""
import pytest
from app.models import AppEvento
from app.services import app_modelo as m
from tests.test_app_modelo import packing


@pytest.fixture
def recepcion_cero(cliente, db):
    codigo = 'CERO-69'
    m.crear_recepcion(db, {'codigo': codigo, 'cliente': 'PRUEBA'}, 'sup')
    m.guardar_packing_list(db, codigo, packing([{'linea': 1, 'sku': 'SKU69', 'cantidad': 10}]), 'PL-A')
    return codigo


def cero(cliente, codigo, ident='cero-69-uno', origen='PL-A'):
    return cliente.post('/api/app/recepciones/' + codigo + '/no-encontrado', json={
        'id': ident, 'sku': 'SKU69', 'observacion': 'Se verificó la descarga y el área de recepción.',
        'origen': origen, 'estadoFisico': 'BUENO', 'incidencias': [], 'fotos': []})


def sku(cliente, codigo):
    return cliente.get('/api/app/recepciones/' + codigo + '/skus').json()[0]


def test_cero_se_guarda_se_verifica_y_el_reintento_no_duplica(cliente, db, recepcion_cero):
    codigo = recepcion_cero
    r = cero(cliente, codigo)
    assert r.status_code == 200, r.text
    assert r.json()['cantidadRegistrada'] == 0
    assert sku(cliente, codigo)['verificado'] and sku(cliente, codigo)['contado'] == 0
    assert sku(cliente, codigo)['estado'] == 'FALTANTE'
    assert sku(cliente, codigo)['pallets'] == {}
    repetido = cero(cliente, codigo)
    assert repetido.status_code == 200 and repetido.json()['duplicado']
    eventos = cliente.get('/api/app/recepciones/' + codigo + '/eventos').json()
    filas = [e for e in eventos if e['id'] == 'cero-69-uno']
    assert len(filas) == 1 and filas[0]['tipo'] == 'CERO' and filas[0]['origen'] == 'PL-A'
    assert filas[0]['observacion'] and filas[0]['operadorEmail']


def test_cero_conserva_cantidad_pallet_posicion_y_pnc_previos(cliente, db, recepcion_cero):
    codigo = recepcion_cero
    m.registrar_conteo(db, codigo, 'op1', {'id': 'fisico-69', 'sku': 'SKU69', 'cantidad': 6,
        'pallet': 'G04.1', 'posicionReal': 'BM-A-10-1', 'origen': 'PL-A',
        'incidencias': [{'tipo': 'MAL_ESTADO', 'cantidad': 2, 'pnc': True}]})
    antes = sku(cliente, codigo)
    r = cero(cliente, codigo)
    assert r.status_code == 200, r.text
    despues = sku(cliente, codigo)
    for campo in ['contado', 'pallets', 'porOrigen', 'cantidadPnc', 'cantidadConforme']:
        assert despues[campo] == antes[campo]
    assert despues['contado'] == 6 and despues['cantidadPnc'] == 2
    db.rollback()
    assert db.get(AppEvento, 'fisico-69').posicion == 'BM-A-10-1'
    m.anular_conteo(db, codigo, 'sup', 'cero-69-uno', 'Se retira la declaración adicional de cero.')
    vigente = sku(cliente, codigo)
    assert vigente['verificado'] and vigente['contado'] == 6
    assert vigente['cantidadPnc'] == 2 and vigente['pallets'] == antes['pallets']


def test_cero_puede_corregirse_a_cantidad_fisica_con_auditoria(cliente, db, recepcion_cero):
    codigo = recepcion_cero
    assert cero(cliente, codigo).status_code == 200
    ruta = '/api/operacion/recepciones/' + codigo + '/eventos/cero-69-uno/corregir'
    datos = {'id': 'correccion-cero-69', 'cantidad': 3, 'pallet': 'G01', 'posicionReal': 'BM-A-10-1',
        'origen': 'PL-A', 'contadoEsperado': 0, 'motivo': 'Se localizó el producto después de validar cero.'}
    r = cliente.post(ruta, json=datos)
    assert r.status_code == 200, r.text
    assert sku(cliente, codigo)['contado'] == 3
    assert sku(cliente, codigo)['pallets'] == {'G01': 3}
    assert cliente.post(ruta, json=datos).json()['duplicado']
    db.rollback()
    assert db.get(AppEvento, 'cero-69-uno').cantidad == 0
    assert db.get(AppEvento, 'anu_cero-69-uno').anula_a == 'cero-69-uno'
    assert db.get(AppEvento, 'correccion-cero-69').datos['corrigeA'] == 'cero-69-uno'


def test_anular_el_unico_cero_devuelve_pendiente_sin_borrar_historial(cliente, db, recepcion_cero):
    codigo = recepcion_cero
    assert cero(cliente, codigo).status_code == 200
    r = cliente.post('/api/app/recepciones/' + codigo + '/conteos/cero-69-uno/anular',
        json={'motivo': 'Declaración ingresada en el SKU incorrecto.'})
    assert r.status_code == 200, r.text
    actual = sku(cliente, codigo)
    assert actual['contado'] == 0 and actual['verificado'] is False and actual['estado'] == 'PENDIENTE'
    db.rollback()
    assert db.get(AppEvento, 'cero-69-uno') is not None


def test_anular_un_cero_conserva_otra_validacion_vigente(cliente, db, recepcion_cero):
    codigo = recepcion_cero
    assert cero(cliente, codigo).status_code == 200
    assert cero(cliente, codigo, 'cero-69-dos').status_code == 200
    m.anular_conteo(db, codigo, 'sup', 'cero-69-uno', 'Duplicidad de verificación física.')
    actual = sku(cliente, codigo)
    assert actual['contado'] == 0 and actual['verificado'] and actual['estado'] == 'FALTANTE'


def test_cero_de_sku_compartido_exige_lista_y_no_toca_otro_origen(cliente, db, recepcion_cero):
    codigo = recepcion_cero
    m.guardar_packing_list(db, codigo, packing([{'linea': 1, 'sku': 'SKU69', 'cantidad': 5}]), 'PL-B')
    assert cero(cliente, codigo, origen='').status_code == 422
    assert cero(cliente, codigo, origen='__REPARTIR__').status_code == 422
    assert cero(cliente, codigo, origen='PL-B').status_code == 200
    eventos = cliente.get('/api/app/recepciones/' + codigo + '/eventos').json()
    assert [(e['tipo'], e['origen']) for e in eventos if e['tipo'] == 'CERO'] == [('CERO', 'PL-B')]
