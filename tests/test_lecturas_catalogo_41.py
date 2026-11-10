"""Lectores con distinto teclado: el catálogo decide; el conteo no cambia."""
import pytest
from sqlalchemy import select
from app.models import AppEvento, Producto, ProductoCodigo
from app.services.lecturas import resolver


@pytest.fixture
def catalogo(db):
    for sku, cliente in [('2GJ805901C','VENTURA'),('2GJ941113','OTRO CLIENTE'),
                          ('06J103600AM','VENTURA'),('ABC12300000','VENTURA')]:
        db.add(Producto(sku=sku,cliente=cliente,descripcion='Producto '+sku,existe_depot=True))
    db.commit()
    return db


@pytest.mark.parametrize('raw,sku',[
    ("2GJ'805'901'C '04100000",'2GJ805901C'),
    ('2GJ-941-113       00000','2GJ941113'),
    ('2GJ“805”901“C 04100000','2GJ805901C'),
    ('2GJ—941—113 00000','2GJ941113'),
    ('2GJ 805 901 C 00000','2GJ805901C'),
    ('2 GJ 941 113 00000','2GJ941113'),
    ('06J103600AM','06J103600AM'),
    ('ABC12300000','ABC12300000'),
])
def test_reconoce_solo_codigo_existente_sin_recepcion(catalogo,raw,sku):
    r=resolver(catalogo,raw)
    assert r['resuelto'] and r['sku']==sku and not r['confirmar']


@pytest.mark.parametrize('raw,sku',[
    ('2GJ9411113','2GJ941113'),  # dígito repetido, no es equivalencia
    ('2GJ80590C','2GJ805901C'),  # omisión
    ('2GJ805901X','2GJ805901C'), # sustitución
    ('9GJ805901C','2GJ805901C'), # diferencia en el primer carácter
    ('2GJ805901C04100000','2GJ805901C'),
    ('2GJ94111300000','2GJ941113'),
])
def test_sugiere_catalogo_completo_con_cliente_y_confirmacion(catalogo,raw,sku):
    r=resolver(catalogo,raw)
    assert not r['resuelto'] and r['confirmar'] and sku in r['candidatos']
    detalle=next(p for p in r['detallesCandidatos'] if p['sku']==sku)
    assert detalle['enCatalogo'] and detalle['existeDepot'] and not detalle['enPackingList']
    assert detalle['cliente']==('OTRO CLIENTE' if sku=='2GJ941113' else 'VENTURA')
    assert list(catalogo.scalars(select(AppEvento)))==[]
    assert list(catalogo.scalars(select(ProductoCodigo)))==[]


def test_codigo_con_digito_repetido_si_existe_es_producto_distinto(catalogo):
    catalogo.add(Producto(sku='2GJ9411113',cliente='VENTURA'));catalogo.commit()
    r=resolver(catalogo,'2GJ9411113')
    assert r['resuelto'] and r['sku']=='2GJ9411113' and not r['confirmar']


def test_no_omite_ceros_internos_ni_inventa_codigos(catalogo):
    r=resolver(catalogo,'6J136AM')
    assert not r['resuelto'] and not r['confirmar']
    r=resolver(catalogo,'XXX999999999')
    assert not r['resuelto'] and r['candidatos']==[]


def test_api_propone_sin_crear_registro(cliente,catalogo):
    r=cliente.post('/api/operacion/lecturas/resolver',json={'lectura':'2GJ9411113'})
    assert r.status_code==200 and r.json()['candidatos']==['2GJ941113']
    assert r.json()['detallesCandidatos'][0]['cliente']=='OTRO CLIENTE'
    assert list(catalogo.scalars(select(AppEvento)))==[]
