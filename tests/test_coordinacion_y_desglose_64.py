"""Coordinación temporal aislada y calidad por conteo, sin modificar cantidades."""
import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.models import AppConfig, AppEvento
from app.services import app_modelo as m
from app.services.desglose_conteos import segmentos, texto_ubicaciones
from tests.test_mejoras_operativas import preparar
from tests.test_correo_y_bitacora_61 import configurar


def test_alerta_mismo_sku_otro_operario_y_dispositivo_no_cambia_conteos(cliente,db):
    c=preparar(db);ruta='/api/operacion/recepciones/'+c+'/sku-en-curso'
    op=TestClient(app);op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    antes=m.leer_coleccion(db,c,'skus')
    uno=cliente.put(ruta,json={'dispositivo':'supervisor-123','sku':'SKU1','actividad':'CONTANDO'})
    assert uno.status_code==200 and not uno.json()['compartido']
    dos=op.put(ruta,json={'dispositivo':'handheld-123','sku':'SKU1','actividad':'CONTANDO'})
    assert dos.status_code==200 and dos.json()['compartido'] and dos.json()['otros'][0]['nombre']=='Supervisora'
    assert 'sesion' not in str(dos.json()).lower() and '@' not in str(dos.json())
    assert not op.put(ruta,json={'dispositivo':'handheld-123','sku':'OTRO','actividad':'REVISANDO'}).json()['compartido']
    db.rollback();assert m.leer_coleccion(db,c,'skus')==antes and db.query(AppEvento).count()==0


def test_presencia_caduca_y_reanuda_sin_borrar_otra_sesion(cliente,db):
    c=preparar(db);ruta='/api/operacion/recepciones/'+c+'/sku-en-curso'
    datos={'dispositivo':'handheld-456','sku':'SKU1','actividad':'CONTANDO'}
    assert cliente.put(ruta,json=datos).status_code==200
    db.rollback();f=db.scalar(select(AppConfig).where(AppConfig.clave.like('sku:%')));f.datos={**f.datos,'vence':time.time()-1};db.commit()
    assert cliente.put(ruta,json=datos).status_code==200
    assert cliente.put(ruta,json={**datos,'sku':''}).status_code==200
    db.rollback();assert not db.scalar(select(AppConfig.clave).where(AppConfig.clave.like('sku:%')))


def test_desglose_10_unidades_sin_duplicar_pnc_en_pallet_distinto():
    es=[{'id':'e1','tipo':'CONTEO','sku':'S','cantidad':6,'pallet':'A01','posicionReal':'BM-A-10-1','incidencias':[{'tipo':'MAL_ESTADO','nombre':'Rotura','cantidad':2,'pnc':True,'pallet':'A01'}]},
        {'id':'e2','tipo':'CONTEO','sku':'S','cantidad':4,'pallet':'A02','posicionReal':'BM-B-20-2'}]
    r=segmentos(es,'S');assert [(p['cantidad'],p['estado'],p['pallet']) for p in r]==[(2,'PNC','A01'),(4,'CONFORME','A01'),(4,'CONFORME','A02')]
    assert sum(p['cantidad'] for p in r)==10 and '2 u. PNC · Pallet A01 · Posición BM-A-10-1' in texto_ubicaciones(es,'S')
    corregidos=es+[{'id':'q','tipo':'CALIDAD','eventoId':'e1','incidencias':[{'tipo':'MAL_ESTADO','cantidad':1,'pnc':True}]},{'id':'x','tipo':'ANULACION','anulaA':'e2'}]
    assert sum(p['cantidad'] for p in segmentos(corregidos,'S'))==6
    assert sum(p['cantidad'] for p in segmentos(corregidos,'S') if p['estado']=='PNC')==1


def test_correo_de_novedades_muestra_cantidad_condicion_y_posicion_por_conteo(cliente,db):
    c,ruta=configurar(cliente,db)
    m.registrar_conteo(db,c,'op1',{'id':'ubicacion64','sku':'SKU1','cantidad':2,'pallet':'A02','posicionReal':'BM-B-20-2'})
    html=cliente.get(ruta).json()['html']
    assert 'Unidades por condición, pallet y posición' in html
    assert '2 u. CONFORME · Pallet A02 · Posición BM-B-20-2' in html


def test_correo_por_embarque_conserva_ubicaciones_de_conteos_identificados():
    from app.services import agrupacion_correo as ag
    eventos=[{'id':'a','tipo':'CONTEO','sku':'S','origen':'P','cantidad':6,'pallet':'A01','posicionReal':'BM-A-10-1',
        'incidencias':[{'tipo':'MAL_ESTADO','nombre':'Rotura','cantidad':2,'pnc':True}]},
        {'id':'b','tipo':'CONTEO','sku':'S','origen':'P','cantidad':4,'pallet':'A02','posicionReal':'BM-B-20-2'}]
    f={'skus':[{'sku':'S','contado':10,'enPackingList':True}],'eventos':eventos,'fotos':[]}
    ls=[{'sku':'S','origen':'P','linea':1,'cantidad':10,'embarque':'EMB-A'}]
    filtrada=ag.filtrar(f,ls,ag.grupo_id('EMB-A'),{'modo':'EMBARQUE','asignaciones':{}})
    ps=segmentos(filtrada['eventosUbicacion'])
    assert [(p['cantidad'],p['estado'],p['pallet'],p['posicion']) for p in ps]==[(2,'PNC','A01','BM-A-10-1'),(4,'CONFORME','A01','BM-A-10-1'),(4,'CONFORME','A02','BM-B-20-2')]
    assert sum(s['contado'] for s in filtrada['skus'])==10
    assert f['eventos']==eventos and not any('sinDetalleUbicacion' in e for e in eventos)


def test_sku_compartido_entre_embarques_no_hereda_ubicacion_del_otro():
    from app.services import agrupacion_correo as ag
    f={'skus':[{'sku':'S','contado':10,'enPackingList':True}],
        'eventos':[{'id':'a','tipo':'CONTEO','sku':'S','origen':'P','cantidad':10,'pallet':'A01','posicionReal':'BM-A-10-1'}],'fotos':[]}
    ls=[{'sku':'S','origen':'P','linea':i+1,'cantidad':5,'embarque':e} for i,e in enumerate(['EMB-A','EMB-B'])]
    c={'modo':'EMBARQUE','asignaciones':{},'repartos':{}}
    _,pendientes=ag.proyecciones(f,ls,c)
    c['repartos']={r['id']:r['propuesta'] for r in pendientes}
    for emb in ['EMB-A','EMB-B']:
        fuente=ag.filtrar(f,ls,ag.grupo_id(emb),c)
        ps=segmentos(fuente['eventosUbicacion']);assert sum(p['cantidad'] for p in ps)==5
        assert all(p['sinDetalleUbicacion'] and not p['posicion'] for p in ps)
        assert 'BM-A-10-1' not in texto_ubicaciones(fuente['eventosUbicacion'],'S')
        assert 'por revisar' in texto_ubicaciones(fuente['eventosUbicacion'],'S')
