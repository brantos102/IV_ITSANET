"""Consolidar totales preserva identidades, etiquetas y evidencia del ingreso."""
import pytest
from sqlalchemy import select

from app.models import AppArchivo, AppEvento, AppImpresion, AppUnidadLogistica
from app.services import archivos
from tests.test_etiquetas_bultos_finales import crear, solicitud
from tests.test_operacion_desarrollo import foto


def preparar_etiquetados(cliente, cantidad=70):
    ruta=crear(cliente,cantidad=cantidad)
    lote=cliente.post(ruta,json=solicitud(cliente,ruta)).json()
    assert len(lote['etiquetas'])==cantidad
    return '/api/operacion/recepciones/BULTOS',lote


def test_consolidar_70_a_50_archiva_etiquetas_vacias_sin_borrar_historial(cliente,db):
    ruta,lote=preparar_etiquetados(cliente)
    antes=cliente.get(ruta+'/ingreso').json()
    assert cliente.post(ruta+'/bultos',json={'cantidad':50,'cantidadAnterior':70}).status_code==409
    r=cliente.post(ruta+'/bultos',json={'cantidad':50,'cantidadAnterior':70,'consolidar':True,'motivo':'Consolidación física en 50 bultos'})
    assert r.status_code==200,r.text
    actual=r.json();assert actual['totalBultos']==50 and actual['bultosDeclaradosIniciales']==70
    assert len(actual['unidades'])==50 and len(actual['bultosArchivados'])==20
    assert [u['id'] for u in actual['unidades']]==[u['id'] for u in antes['unidades'][:50]]
    assert [u['id'] for u in actual['bultosArchivados']]==[u['id'] for u in antes['unidades'][50:]]
    assert all(u['etiquetaEmitida'] and u['rotulo']==f"P{u['numero']:02d}" for u in actual['bultosArchivados'])
    db.rollback();assert db.query(AppUnidadLogistica).count()==70
    historial=db.get(AppImpresion,lote['id']);assert len(historial.datos['etiquetas'])==70
    audit=db.scalar(select(AppEvento).where(AppEvento.motivo=='BULTOS_RECIBIDOS').order_by(AppEvento.creado_en.desc(),AppEvento.id.desc()))
    assert audit.datos['cantidadAnterior']==70 and len(audit.datos['archivados'])==20
    assert cliente.get('/api/app/recepciones/BULTOS').json()['bultos']==50


@pytest.mark.parametrize('cambio',[{'codigo':'MADRE70'},{'observacion':'Pendiente de revisar'},{'pallet':'A01'},{'concluido':True},{'origenes':['RB-DEMO']}])
def test_consolidacion_no_oculta_unidades_con_datos(cliente,cambio):
    ruta,_=preparar_etiquetados(cliente)
    u=cliente.get(ruta+'/ingreso').json()['unidades'][-1]
    edit=cliente.post(ruta+'/unidades',json={'id':u['id'],'version':u['version'],**cambio})
    assert edit.status_code==200,edit.text
    r=cliente.post(ruta+'/bultos',json={'cantidad':50,'cantidadAnterior':70,'consolidar':True,'motivo':'Consolidación física'})
    assert r.status_code==409 and '70' in r.text
    actual=cliente.get(ruta+'/ingreso').json();assert actual['totalBultos']==70 and len(actual['unidades'])==70 and not actual['bultosArchivados']


def test_no_consolidar_bulto_con_foto_o_caja(cliente,db,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    ruta,_=preparar_etiquetados(cliente)
    u=cliente.get(ruta+'/ingreso').json()['unidades'][-1]
    assert foto(cliente,'BULTOS',unidadId=u['id']).status_code==201
    assert cliente.post(ruta+'/bultos',json={'cantidad':50,'cantidadAnterior':70,'consolidar':True,'motivo':'Consolidación física'}).status_code==409
    assert len(cliente.get(ruta+'/ingreso').json()['unidades'])==70
    assert db.query(AppArchivo).count()==1


def test_bulto_archivado_rechaza_edicion_caja_y_foto_y_reactivar_conserva_id(cliente,db,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    ruta,lote=preparar_etiquetados(cliente)
    id_70=lote['etiquetas'][-1]['unidadId']
    a=cliente.post(ruta+'/bultos',json={'cantidad':50,'cantidadAnterior':70,'consolidar':True,'motivo':'Consolidación física'});assert a.status_code==200
    assert cliente.post(ruta+'/unidades',json={'id':id_70,'version':0,'codigo':'NO-USAR'}).status_code==409
    assert cliente.post(ruta+'/unidades',json={'tipo':'CAJA_MADRE','padreId':id_70,'codigo':'CAJA'}).status_code==409
    assert foto(cliente,'BULTOS',unidadId=id_70).status_code==409
    assert db.query(AppArchivo).count()==0
    r=cliente.post(ruta+'/bultos',json={'cantidad':70,'cantidadAnterior':50});assert r.status_code==200,r.text
    actual=r.json();assert actual['totalBultos']==70 and not actual['bultosArchivados']
    assert actual['unidades'][-1]['id']==id_70 and actual['unidades'][-1]['rotulo']=='P70'
    db.rollback();assert db.query(AppUnidadLogistica).count()==70 and db.query(AppImpresion).count()==1


def test_consolidacion_no_oculta_bulto_con_caja_interior(cliente):
    ruta,_=preparar_etiquetados(cliente,cantidad=3)
    u=cliente.get(ruta+'/ingreso').json()['unidades'][-1]
    assert cliente.post(ruta+'/unidades',json={'tipo':'CAJA_MADRE','padreId':u['id'],'codigo':'CAJA-3'}).status_code==200
    r=cliente.post(ruta+'/bultos',json={'cantidad':2,'cantidadAnterior':3,'consolidar':True,'motivo':'Consolidación física'})
    assert r.status_code==409
    actual=cliente.get(ruta+'/ingreso').json();assert actual['totalBultos']==3 and len(actual['unidades'])==4
    assert not actual['bultosArchivados']


def test_consolidacion_exige_motivo_y_control_de_revision(cliente):
    ruta,_=preparar_etiquetados(cliente)
    assert cliente.post(ruta+'/bultos',json={'cantidad':50,'cantidadAnterior':70,'consolidar':True}).status_code==422
    assert cliente.post(ruta+'/bultos',json={'cantidad':50,'cantidadAnterior':69,'consolidar':True,'motivo':'Consolidación física'}).status_code==409
    assert len(cliente.get(ruta+'/ingreso').json()['unidades'])==70


@pytest.mark.parametrize('estado',['PENDIENTE','RESERVADA','ENVIANDO','IMPRIMIENDO'])
def test_no_consolidar_si_cola_puede_imprimir_bultos_sobrantes(cliente,db,estado):
    ruta,lote=preparar_etiquetados(cliente)
    db.rollback();trabajo=db.get(AppImpresion,lote['id']);snapshot=dict(trabajo.datos);trabajo.estado=estado;db.commit()
    r=cliente.post(ruta+'/bultos',json={'cantidad':50,'cantidadAnterior':70,'consolidar':True,'motivo':'Consolidación física'})
    assert r.status_code==409 and 'cola' in r.text and estado in r.text
    ingreso=cliente.get(ruta+'/ingreso').json();assert ingreso['totalBultos']==70 and len(ingreso['unidades'])==70 and not ingreso['bultosArchivados']
    db.rollback();trabajo=db.get(AppImpresion,lote['id']);assert trabajo.estado==estado and trabajo.datos==snapshot


@pytest.mark.parametrize('estado',['ENVIADA','REVISION'])
def test_lote_terminal_no_se_reenvia_y_permite_consolidar_sin_cambiar_historial(cliente,db,estado):
    ruta,lote=preparar_etiquetados(cliente)
    db.rollback();trabajo=db.get(AppImpresion,lote['id']);snapshot=dict(trabajo.datos);trabajo.estado=estado;db.commit()
    r=cliente.post(ruta+'/bultos',json={'cantidad':50,'cantidadAnterior':70,'consolidar':True,'motivo':'Consolidación física'})
    assert r.status_code==200,r.text
    assert r.json()['totalBultos']==50 and len(r.json()['bultosArchivados'])==20
    db.rollback();trabajo=db.get(AppImpresion,lote['id']);assert trabajo.estado==estado and trabajo.datos==snapshot


def test_lote_pendiente_solo_de_bultos_vigentes_no_impide_corregir_otros(cliente,db):
    ruta,lote=preparar_etiquetados(cliente)
    db.rollback();trabajo=db.get(AppImpresion,lote['id']);trabajo.estado='PENDIENTE'
    trabajo.datos={**trabajo.datos,'etiquetas':trabajo.datos['etiquetas'][:10],'copias':10};db.commit()
    r=cliente.post(ruta+'/bultos',json={'cantidad':50,'cantidadAnterior':70,'consolidar':True,'motivo':'Consolidación física'})
    assert r.status_code==200,r.text
    db.rollback();assert db.get(AppImpresion,lote['id']).estado=='PENDIENTE'
