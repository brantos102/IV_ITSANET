"""Dos cierres históricos pendientes no deben enviar dos informes al cliente."""
from copy import deepcopy
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import AppArchivo, AppAuditoriaGeneral, AppEntrega, AppRecepcion, utcnow
from app.services import archivos, entregas
from app.services import app_modelo as m
from tests.test_entregas import preparar
from tests.test_integraciones_ui import admin


@pytest.fixture
def duplicadas(cliente, db, monkeypatch, tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    codigo,datos=preparar(cliente,db)
    r=cliente.post(f'/api/app/recepciones/{codigo}/entrega',json=datos);assert r.status_code==201,r.text
    db.rollback();db.expire_all();primera=db.get(AppEntrega,r.json()['id'])
    segunda=AppEntrega(id='b'*32,recepcion=codigo,clave='c'*64,usuario=primera.usuario,
        datos=deepcopy(primera.datos),estado='PENDIENTE',creado_en=utcnow()+timedelta(seconds=1))
    db.add(segunda);db.commit()
    return codigo,primera.id,segunda.id


def test_detiene_dos_entregas_antes_de_google_y_conserva_archivos(cliente,db,duplicadas,monkeypatch):
    codigo,a,b=duplicadas
    monkeypatch.setattr(entregas,'configurado',lambda *a:True)
    def prohibido(*a):pytest.fail('No contactar Google antes de resolver entregas duplicadas')
    monkeypatch.setattr(entregas,'llamar',prohibido)
    assert entregas.procesar_uno()
    db.rollback();db.expire_all()
    for ident in [a,b]:
        e=db.get(AppEntrega,ident);assert e.estado=='REVISION' and e.datos['revisionMotivo']=='ENTREGAS_MULTIPLES'
    assert db.query(AppArchivo).count()==1
    assert db.get(AppRecepcion,codigo).estado=='CERRADA'
    assert cliente.post(f'/api/app/entregas/{b}/reintentar',json={}).status_code==409


def test_admin_anula_solo_envio_antiguo_y_reintenta_el_mismo_elegido(admin,cliente,db,duplicadas,monkeypatch):
    codigo,a,b=duplicadas
    monkeypatch.setattr(entregas,'configurado',lambda *a:True)
    assert entregas.procesar_uno()
    assert cliente.post(f'/api/app/entregas/{a}/cancelar',json={'motivo':'Se conserva el informe más reciente'}).status_code==403
    r=admin.post(f'/api/app/entregas/{a}/cancelar',json={'motivo':'Se conserva el informe más reciente'})
    assert r.status_code==200 and r.json()['estado']=='CANCELADA'
    r=cliente.post(f'/api/app/entregas/{b}/reintentar',json={})
    assert r.status_code==200 and r.json()['id']==b and r.json()['estado']=='PENDIENTE'
    llamadas=[]
    def llamar(accion,clave,datos):
        llamadas.append((accion,clave))
        return {'exito':True,'remitente':'sup','fileId':'informe-confirmado'}
    monkeypatch.setattr(entregas,'llamar',llamar)
    assert entregas.procesar_uno() and not entregas.procesar_uno()
    db.rollback();db.expire_all()
    assert db.get(AppEntrega,a).estado=='CANCELADA' and db.get(AppEntrega,b).estado=='ENTREGADA'
    assert db.query(AppEntrega).count()==2 and db.query(AppArchivo).count()==1
    assert [x[0] for x in llamadas]==['estado','archivo','finalizar']
    assert llamadas[-1][1]==b
    assert db.scalar(select(AppAuditoriaGeneral).where(AppAuditoriaGeneral.accion=='ENVIO_ANULADO')).datos['entregaId']==a


def test_no_crea_otra_entrega_al_reabrir_con_una_sin_resolver(cliente,db,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    codigo,datos=preparar(cliente,db)
    assert cliente.post(f'/api/app/recepciones/{codigo}/entrega',json=datos).status_code==201
    m.reabrir_recepcion(db,codigo,'sup','Corrección de prueba')
    r=cliente.post(f'/api/app/recepciones/{codigo}/entrega',json=datos)
    assert r.status_code==409 and 'sin resolver' in r.text
    db.rollback();assert db.query(AppEntrega).count()==1


def test_procesando_no_se_reintenta_ni_se_anula_ni_cambia_su_reserva(admin,cliente,db,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    codigo,datos=preparar(cliente,db)
    ident=cliente.post(f'/api/app/recepciones/{codigo}/entrega',json=datos).json()['id']
    db.rollback();db.expire_all();e=db.get(AppEntrega,ident);e.estado='PROCESANDO';e.proximo_en=utcnow()+timedelta(minutes=10);db.commit();db.refresh(e);reserva=e.proximo_en
    r=cliente.post(f'/api/app/entregas/{ident}/reintentar',json={});assert r.status_code==409 and 'ya se está procesando' in r.text
    assert admin.post(f'/api/app/entregas/{ident}/cancelar',json={'motivo':'Motivo de prueba suficientemente largo'}).status_code==409
    db.rollback();db.expire_all();assert db.get(AppEntrega,ident).proximo_en==reserva


def test_reserva_vencida_con_otras_versiones_no_se_reenvia_sin_revisar(cliente,db,duplicadas,monkeypatch):
    _,a,b=duplicadas
    e=db.get(AppEntrega,a);e.estado='PROCESANDO';e.proximo_en=utcnow()-timedelta(minutes=1);db.commit()
    monkeypatch.setattr(entregas,'configurado',lambda *a:True)
    assert entregas.procesar_uno()
    db.rollback();db.expire_all();e=db.get(AppEntrega,a)
    assert e.estado=='REVISION' and e.datos['revisionMotivo']=='ENTREGA_INTERRUMPIDA'
    assert not entregas.procesar_uno()
