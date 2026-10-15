"""Consultas de recepciones, marca Excel y filtros sin mutar conteos."""
import io
import zipfile
from datetime import datetime

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import func, select

from app.main import app
from app.models import AppEvento, AppRecepcion, Producto
from app.services import app_modelo as m


def crear(db, codigo, cliente='VENTURA'):
    m.crear_recepcion(db, {'codigo': codigo, 'cliente': cliente}, 'sup')
    m.guardar_packing_list(db, codigo, {'lineas': [{'linea': 1, 'sku': '04E133366BT', 'cantidad': 3}],
        'porSku': {'04E133366BT': 3}, 'unidades': 3})


def test_busqueda_en_recepciones_abiertas_por_sku_y_ean_sin_conteo(cliente,db):
    for codigo in ['VW001', 'VW002', 'CERRADA']:
        crear(db,codigo)
    db.get(AppRecepcion,'CERRADA').estado='CERRADA'
    db.add(Producto(sku='04E133366BT',cliente='VENTURA',ean='7891234567890',unidad='CS'))
    db.commit()
    for codigo in ['04E133366BT','7891234567890']:
        r=cliente.get('/api/app/recepciones-abiertas/por-codigo/'+codigo)
        assert r.status_code==200
        assert {r['codigo'] for r in r.json()['recepciones']}=={'VW001','VW002'}
        assert r.json()['sku']=='04E133366BT'
    assert cliente.get('/api/app/recepciones-abiertas/por-codigo/OTRO').json()['recepciones']==[]
    assert db.scalar(select(func.count()).select_from(AppEvento))==0
    assert cliente.get('/api/app/recepciones/VW001/catalogo-exportacion').json()=={'04E133366BT':{'unidad':'CS','familia':''}}


def test_unidad_no_se_toma_del_catalogo_de_otro_cliente(cliente,db):
    crear(db,'OTRO','FACTOR')
    db.add(Producto(sku='04E133366BT',cliente='VENTURA',unidad='CS'));db.commit()
    assert cliente.get('/api/app/recepciones/OTRO/catalogo-exportacion').json()=={}


def test_periodo_horario_ecuador_y_paginacion(cliente,db):
    for codigo,fecha in [('ANTERIOR',datetime(2026,10,15,4,59)),('UNO',datetime(2026,10,15,5)),('DOS',datetime(2026,10,16,4,59))]:
        crear(db,codigo);db.get(AppRecepcion,codigo).creado_en=fecha
    db.commit()
    params={'desde':'2026-10-15','hasta':'2026-10-15','limite':1}
    a=cliente.get('/api/app/reportes/recepciones',params=params).json()
    b=cliente.get('/api/app/reportes/recepciones',params={**params,'offset':1}).json()
    assert a['total']==b['total']==2
    assert {a['recepciones'][0]['codigo'],b['recepciones'][0]['codigo']}=={'UNO','DOS'}
    assert cliente.get('/api/app/reportes/recepciones',params={'desde':'2026-10-16','hasta':'2026-10-15'}).status_code==422


def test_excel_contiene_imagen_filtros_y_datos_sin_formulas(cliente):
    r=cliente.post('/api/app/reportes/excel',json={'titulo':'Recepciones filtradas','filtros':'Producto: 001 · PNC',
        'resumen':'1 referencia · 4 unidades','columnas':['SKU','Contado'],'filas':[['001',4],['=1+1',2]]})
    assert r.status_code==200,r.text
    libro=load_workbook(io.BytesIO(r.content));s=libro.active
    assert s['A5'].value=='Producto: 001 · PNC'
    assert s['A8'].value=='001' and s['B8'].value==4
    assert s['A9'].value=='=1+1' and s['A9'].data_type=='s'
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert 'xl/media/image1.png' in z.namelist()
    anon=TestClient(app)
    assert anon.get('/api/app/reportes/recepciones').status_code==401
    op=TestClient(app);op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    assert op.get('/api/app/reportes/recepciones').status_code==403
    assert op.post('/api/app/reportes/excel',json={'titulo':'x','columnas':['x'],'filas':[]}).status_code==403
