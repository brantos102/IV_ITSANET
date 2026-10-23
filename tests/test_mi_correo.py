"""Autorizar la conexión propia antes de reemplazarla; ningún correo real."""
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.models import AppConfig,AppEntrega,Operador,Rol
from app import config
from app.services import entregas,integraciones
from tests.test_remitente_responsable import correo

URL='https://script.google.com/macros/s/mi-puente-propio/exec'
CLAVE='clave-prueba-conexion-propia-'*2
RUTA='/api/app/integraciones/mi-google'

@pytest.fixture
def propia(cliente,db,monkeypatch,tmp_path):
    monkeypatch.setattr(config,'DATA_DIR',tmp_path)
    op=db.scalar(select(Operador).where(Operador.usuario=='sup'));op.email='fmorales@example.test';db.commit()
    return op


def prueba_google(accion,clave,datos,conexion):
    assert accion=='estado' and datos=={'usuario':'fmorales@example.test'}
    assert conexion['url']==URL and conexion['secreto']==CLAVE
    return {'exito':True,'remitente':'fmorales@example.test','capacidades':['correoVerificado'],'carpeta':'https://drive.google.com/drive/folders/pruebas'}


def test_supervisor_guarda_y_reutiliza_su_clave_sin_ver_ni_modificar_otros(cliente,db,propia,monkeypatch):
    integraciones.guardar_google(db,{'supervisor':'otro@example.test','url':'https://script.google.com/macros/s/otro/exec','secreto':'otra-clave-privada-'*3},'admin')
    assert cliente.get(RUTA).json()['correo']=='fmorales@example.test'
    monkeypatch.setattr(entregas,'llamar_conexion',prueba_google)
    for secreto in (CLAVE,''):
        r=cliente.put(RUTA,json={'url':URL,'secreto':secreto});assert r.status_code==200,r.text
        assert r.json()['verificadoEn'] and CLAVE not in r.text and 'otra-clave' not in r.text
    db.rollback();db.expire_all();f=db.get(AppConfig,integraciones._clave_google(propia.email))
    assert CLAVE not in json.dumps(f.datos)
    assert integraciones.google(db,propia.email)['secreto']==CLAVE
    assert integraciones.google(db,'otro@example.test')['url'].endswith('/otro/exec')
    assert cliente.get('/api/app/integraciones').status_code==403
    assert cliente.put(RUTA,json={'supervisor':'otro@example.test','url':URL,'secreto':CLAVE}).status_code==422


def test_cuenta_google_distinta_no_reemplaza_la_conexion(cliente,db,propia,monkeypatch):
    integraciones.guardar_google(db,{'supervisor':propia.email,'url':'https://script.google.com/macros/s/anterior/exec','secreto':CLAVE},'admin')
    monkeypatch.setattr(entregas,'llamar_conexion',lambda *a:{'exito':True,'remitente':'otra@example.test','capacidades':['correoVerificado']})
    r=cliente.put(RUTA,json={'url':URL,'secreto':CLAVE});assert r.status_code==502 and 'Ejecutar como' in r.text
    db.rollback();assert integraciones.google(db,propia.email)['url'].endswith('/anterior/exec')
    assert db.query(AppEntrega).count()==0


def test_hmac_incorrecta_no_se_guarda(cliente,db,propia,monkeypatch):
    def falla(*a):raise RuntimeError('La clave compartida no coincide con SERVIDOR_HMAC de este Apps Script.')
    monkeypatch.setattr(entregas,'llamar_conexion',falla)
    r=cliente.put(RUTA,json={'url':URL,'secreto':CLAVE});assert r.status_code==502 and 'No se guardó' in r.text
    db.rollback();assert db.get(AppConfig,integraciones._clave_google(propia.email)) is None


def test_no_hereda_clave_general_ni_reutiliza_exec_de_otro(cliente,db,propia,monkeypatch):
    integraciones.guardar_google(db,{'supervisor':'','url':URL,'secreto':CLAVE},'admin')
    assert not cliente.get(RUTA).json()['secretoConfigurado']
    assert cliente.put(RUTA,json={'url':URL,'secreto':''}).status_code==422
    integraciones.guardar_google(db,{'supervisor':'otro@example.test','url':URL,'secreto':CLAVE},'admin')
    monkeypatch.setattr(entregas,'llamar_conexion',lambda *a:pytest.fail('No debe invocar un puente ajeno'))
    assert cliente.put(RUTA,json={'url':URL,'secreto':CLAVE}).status_code==409


def test_operador_y_anonimo_no_pueden_autorizar_correos(cliente,db,propia):
    anon=TestClient(app);assert anon.get(RUTA).status_code==401
    op=TestClient(app);assert op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'}).status_code==200
    assert op.get(RUTA).status_code==403 and op.put(RUTA,json={'url':URL,'secreto':CLAVE}).status_code==403


def test_fallo_conexion_se_pausa_y_solo_envia_tras_confirmar(cliente,db,correo,monkeypatch):
    c,d=correo
    r=cliente.post(f'/api/app/recepciones/{c}/entrega',json=d);assert r.status_code==201
    ident=r.json()['id']
    def falla(*a):raise RuntimeError('La clave compartida no coincide con SERVIDOR_HMAC de este Apps Script.')
    monkeypatch.setattr(entregas,'llamar',falla)
    assert entregas.procesar_uno() and not entregas.procesar_uno()
    db.rollback();db.expire_all();e=db.get(AppEntrega,ident)
    assert e.estado=='REVISION' and e.datos['revisionMotivo']=='CONEXION_RECHAZADA'
    assert cliente.post(f'/api/app/entregas/{ident}/reintentar').status_code==409
    def verificada(*a):return {'remitente':'personal@example.test','capacidades':['correoVerificado'],'exito':True}
    monkeypatch.setattr(entregas,'llamar_conexion',verificada)
    assert cliente.put(RUTA,json={'url':URL,'secreto':CLAVE}).status_code==200
    listado=cliente.get('/api/app/entregas').json();assert listado[0]['confirmacionDisponible']
    db.rollback();db.expire_all();assert db.get(AppEntrega,ident).estado=='REVISION'
    acciones=[]
    def google(accion,clave,datos):
        acciones.append(accion)
        return {'exito':True,'versionPuente':2,'remitente':'personal@example.test','capacidades':['correoVerificado'],
            'enviadoA':datos.get('destinatarios',''),'fileId':'archivo-confirmado'}
    monkeypatch.setattr(entregas,'llamar',google)
    ruta=f'/api/app/entregas/{ident}/solicitar'
    v=cliente.get(ruta);assert v.status_code==200 and v.json()['conexionVerificada'],v.text
    assert acciones==['estado']
    assert cliente.post(ruta,json={}).status_code==422
    r=cliente.post(ruta,json={'motivo':'Confirmar documentos finales revisados','confirmarNoEnviado':True,'remitenteConfirmado':'personal@example.test'})
    assert r.status_code==200,r.text
    assert entregas.procesar_uno() and not entregas.procesar_uno()
    assert acciones.count('finalizar')==1


def test_puente_antiguo_y_email_duplicado_impiden_autorizar(cliente,db,propia,monkeypatch):
    monkeypatch.setattr(entregas,'llamar_conexion',lambda *a:{'exito':True,'remitente':propia.email,'capacidades':[]})
    assert cliente.put(RUTA,json={'url':URL,'secreto':CLAVE}).status_code==409
    db.add(Operador(usuario='duplicado',email=propia.email,nombre='Duplicado',rol=Rol.SUPERVISOR,pin_hash='no-se-usa'));db.commit()
    assert cliente.get(RUTA).status_code==409
