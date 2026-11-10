"""Etiquetas nuevas del mismo SKU; importación atómica y cantidades físicas."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Producto, ProductoCodigo, AppEvento, AppSku
from app.services import app_modelo as m, codigos
from app.routers.catalogo import _upsert


@pytest.fixture
def recepcion(cliente, db):
    db.add_all([Producto(sku='SKU1', cliente='PRUEBA', ean='001111', codigo_alternativo='OLD1', descripcion='Pieza'),
                Producto(sku='SKU2', cliente='PRUEBA', ean='002222')]); db.commit()
    m.crear_recepcion(db, {'codigo':'BARRAS-PRUEBA','cliente':'PRUEBA'}, 'sup')
    m.guardar_packing_list(db, 'BARRAS-PRUEBA', {'lineas':[{'linea':1,'sku':'SKU1','cantidad':5}],
        'porSku':{'SKU1':5},'unidades':5},'LISTA')
    return 'BARRAS-PRUEBA'


def test_varias_etiquetas_resuelven_mismo_sku_y_conservan_maestro(cliente, db, recepcion):
    for codigo in ['0000123','0000456']:
        r=cliente.post(f'/api/app/catalogo/{codigo}/equivalencia',json={'sku':'SKU1'})
        assert r.status_code == 200, r.text
    for codigo in ['0000123','0000456','001111','OLD1','SKU1']:
        assert cliente.get(f'/api/app/catalogo/{codigo}').json()['sku'] == 'SKU1'
        assert cliente.get(f'/api/app/recepciones-abiertas/por-codigo/{codigo}').json()['recepciones'][0]['codigo'] == recepcion
    db.expire_all(); p=db.get(Producto,'SKU1')
    assert p.ean=='001111' and p.codigo_alternativo=='OLD1'
    assert db.query(Producto).count()==2 and db.query(AppEvento).count()==0
    filas=cliente.get(f'/api/app/recepciones/{recepcion}/codigos-barras').json()
    assert [f['codigoBarras'] for f in filas]==['0000123','0000456']
    assert all(f['registradoPor']=='sup' for f in filas)
    assert cliente.get(f'/api/app/recepciones/{recepcion}/catalogo-exportacion').json()['SKU1']['existe'] is True


def test_no_reasigna_etiquetas_ni_crea_sku_inexistente(cliente,db,recepcion):
    assert cliente.post('/api/app/catalogo/0000123/equivalencia',json={'sku':'SKU1'}).status_code==200
    for codigo in ['0000123','001111','OLD1','SKU1']:
        assert cliente.post(f'/api/app/catalogo/{codigo}/equivalencia',json={'sku':'SKU2'}).status_code==409
    assert cliente.post('/api/app/catalogo/9999/equivalencia',json={'sku':'NO-EXISTE'}).status_code==404
    assert db.query(Producto).count()==2


def test_importacion_atomica_con_fila_invalida_y_repeticion_segura(cliente,db,recepcion):
    ruta='/api/app/catalogo/codigos/importar'
    filas=[{'sku':'SKU1','codigoBarras':'000123'},{'sku':'SKU2','codigoBarras':'000123'}]
    r=cliente.post(ruta,json={'filas':filas}); assert r.status_code==409 and 'Fila 3' in r.text
    db.expire_all(); assert db.query(ProductoCodigo).count()==0
    filas[1]['codigoBarras']='000456'
    for _ in range(2):
        assert cliente.post(ruta,json={'filas':filas}).status_code==200
    db.expire_all(); assert db.query(ProductoCodigo).count()==2
    op=TestClient(app);op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    assert op.post(ruta,json={'filas':filas}).status_code==403
    assert op.get(f'/api/app/recepciones/{recepcion}/codigos-barras').status_code==403


def test_maestro_vacio_no_borra_ean_y_reemplazo_conserva_lectura_anterior(cliente,db,recepcion):
    _upsert(db,[{'sku':'SKU1','descripcion':'Nueva descripción','ean':None,'codigo_alternativo':None}]);db.commit();db.expire_all()
    assert db.get(Producto,'SKU1').ean=='001111'
    _upsert(db,[{'sku':'SKU1','ean':'003333','codigo_alternativo':'OLD2'}]);db.commit();db.expire_all()
    for codigo in ['001111','003333','OLD1','OLD2']:
        assert codigos.buscar(db,codigo).sku=='SKU1'
    assert cliente.get(f'/api/app/recepciones/{recepcion}/codigos-barras').json()==[]  # respaldo del maestro, no actualización pendiente


@pytest.mark.parametrize('cantidad',[-1,-2,-3,-999])
def test_no_admite_negativos_aunque_el_total_siga_positivo(cliente,db,recepcion,cantidad):
    ruta=f'/api/app/recepciones/{recepcion}/conteos'
    base={'sku':'SKU1','pallet':'F1','cantidad':4,'id':'positivo'}
    assert cliente.post(ruta,json=base).status_code==200
    r=cliente.post(ruta,json={**base,'id':'negativo','cantidad':cantidad})
    assert r.status_code==422 and r.json()['detail']['codigo']=='CANTIDAD_INVALIDA'
    db.expire_all(); assert db.query(AppEvento).count()==1
    assert db.scalar(select(AppSku).where(AppSku.recepcion==recepcion)).contado==4
    assert cliente.post(ruta+'/positivo/anular',json={'motivo':'Cantidad corregida'}).status_code==200
    db.expire_all(); assert db.scalar(select(AppSku).where(AppSku.recepcion==recepcion)).contado==0


def test_importacion_packing_negativo_no_altera_recepcion(cliente, db):
    m.crear_recepcion(db, {'codigo':'NO-NEGATIVOS','cliente':'PRUEBA'}, 'sup')
    r=cliente.post('/api/app/recepciones/NO-NEGATIVOS/packing-list',json={'resultado':{
        'lineas':[{'linea':1,'sku':'SKU1','cantidad':-2}], 'porSku':{'SKU1':-2},'unidades':-2}})
    assert r.status_code==422 and r.json()['detail']['codigo']=='CANTIDAD_INVALIDA'
    assert cliente.get('/api/app/recepciones/NO-NEGATIVOS/skus').json()==[]
