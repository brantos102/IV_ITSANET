"""El listado busca todo el histórico y pagina sin mezclar la fecha del código."""
from datetime import datetime,timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.models import AppRecepcion,AppIngreso,AppEvento


def sembrar(db):
    for i in range(65):
        db.add(AppRecepcion(codigo=f'REC-{i:03d}',cliente='VENTURA',descripcion='Consolidación' if i==0 else '',
            creado_por='sup',creado_en=datetime(2026,9,1)+timedelta(days=i),estado='CERRADA' if i%2 else 'ABIERTA'))
    db.flush();db.add(AppIngreso(recepcion='REC-000',datos={'marca':'VOLKSWAGEN'}));db.commit()


def test_busqueda_historica_pagina_y_no_cambia_fecha(cliente,db):
    sembrar(db)
    r=cliente.get('/api/app/recepciones-listado').json()
    assert r['total']==65 and len(r['recepciones'])==50 and r['recepciones'][0]['codigo']=='REC-064'
    siguiente=cliente.get('/api/app/recepciones-listado?offset=50').json()
    assert len(siguiente['recepciones'])==15
    assert len({r['codigo'] for r in r['recepciones']+siguiente['recepciones']})==65
    for texto in ['rec-000','consolidacion','volkswagen']:
        j=cliente.get('/api/app/recepciones-listado',params={'texto':texto}).json()
        assert j['total']==1 and j['recepciones'][0]['codigo']=='REC-000'
        assert j['recepciones'][0]['creadoEn']=='2026-09-01T00:00:00.000Z'


def test_fechas_ecuador_inclusivas_y_estado_cliente(cliente,db):
    for i,fecha in enumerate([datetime(2026,10,23,4,59,59),datetime(2026,10,23,5),datetime(2026,10,24,4,59,59),datetime(2026,10,24,5)]):
        db.add(AppRecepcion(codigo='NO-FECHA-'+str(i),cliente='VENTURA',creado_por='sup',creado_en=fecha,estado='CERRADA' if i==2 else 'ABIERTA'))
    db.commit()
    params={'desde':'2026-10-23','hasta':'2026-10-23','texto':'ventura'}
    r=cliente.get('/api/app/recepciones-listado',params=params);assert r.status_code==200,r.text
    assert [r['codigo'] for r in r.json()['recepciones']]==['NO-FECHA-2','NO-FECHA-1']
    j=cliente.get('/api/app/recepciones-listado',params={**params,'estado':'ABIERTA'}).json()
    assert [r['codigo'] for r in j['recepciones']]==['NO-FECHA-1']


def test_solo_mias_y_autenticacion(cliente,db,operadores):
    sembrar(db)
    db.add(AppEvento(id='evento67',recepcion='REC-000',tipo='AUDITORIA',sku=None,cantidad=0,usuario='op1',datos={}));db.commit()
    anonimo=TestClient(app);assert anonimo.get('/api/app/recepciones-listado').status_code==401
    anonimo.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    j=anonimo.get('/api/app/recepciones-listado?mias=true').json()
    assert j['total']==1 and j['recepciones'][0]['codigo']=='REC-000'


def test_orden_validacion_y_offset_fuera_de_limite(cliente,db):
    sembrar(db)
    for orden in ['ANTIGUAS','CODIGO']:
        assert cliente.get('/api/app/recepciones-listado',params={'orden':orden}).json()['recepciones'][0]['codigo']=='REC-000'
    j=cliente.get('/api/app/recepciones-listado?offset=500').json()
    assert j['offset']==50 and len(j['recepciones'])==15
    for params in [{'desde':'2026-10-24','hasta':'2026-10-23'},{'estado':'AJENO'},{'desde':'sin-fecha'},{'orden':'OTRO'},{'limite':0}]:
        assert cliente.get('/api/app/recepciones-listado',params=params).status_code==422
