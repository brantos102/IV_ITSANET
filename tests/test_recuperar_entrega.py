"""Recuperar el informe elegido y sus fotos sin repetir cierre, versión o correo."""
from copy import deepcopy
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import AppArchivo, AppAuditoriaGeneral, AppEntrega, AppRecepcion, utcnow
from app.services import entregas, integraciones
from tests.test_integraciones_ui import admin
from tests.test_remitente_responsable import correo


@pytest.fixture
def pendiente(cliente, db, correo):
    codigo, datos = correo
    datos['modoRemitente'] = 'PERSONAL'
    r = cliente.post(f'/api/app/recepciones/{codigo}/entrega', json=datos)
    assert r.status_code == 201, r.text
    return codigo, r.json()['id']


def confirmacion():
    return {'motivo': 'Recuperar informe no enviado con la cuenta responsable',
        'confirmarNoEnviado': True, 'remitenteConfirmado': 'responsable@example.test'}


def google(accion, clave, datos):
    assert datos['usuario'] == 'responsable@example.test'
    return {'exito': True, 'versionPuente': 2, 'remitente': datos['usuario'],
        'fileId': 'archivo-confirmado', 'enviadoA':datos.get('destinatarios',''), 'carpeta': 'https://drive.google.com/drive/folders/confirmada'}


def test_recupera_mismo_informe_con_responsable_y_conserva_autor(admin, cliente, db, pendiente, monkeypatch):
    codigo, ident = pendiente
    assert admin.post(f'/api/app/entregas/{ident}/cancelar', json={'motivo':'Anulación de prueba antes del envío'}).status_code == 200
    db.rollback(); db.expire_all()
    e = db.get(AppEntrega, ident); informes = e.datos['informes']; clave = e.clave
    r = admin.get(f'/api/app/entregas/{ident}/recuperar')
    assert r.status_code == 200 and r.json()['responsable']['correo'] == 'responsable@example.test', r.text
    llamadas = []
    def comprobar(accion, clave, datos):
        llamadas.append((accion, clave)); return google(accion, clave, datos)
    monkeypatch.setattr(entregas, 'llamar', comprobar)
    r = admin.post(f'/api/app/entregas/{ident}/recuperar', json=confirmacion())
    assert r.status_code == 200, r.text
    assert r.json()['remitente'] == 'responsable@example.test' and r.json()['supervisor'] == 'personal@example.test'
    assert [a for a, _ in llamadas] == ['estado']  # Recuperar no envía correo.
    db.rollback(); db.expire_all(); e = db.get(AppEntrega, ident)
    assert e.datos['informes'] == informes and e.clave == clave and e.estado == 'PENDIENTE'
    assert e.datos['anulacion'] and e.datos['recuperaciones'][0]['remitenteAnterior'] == 'personal@example.test'
    assert db.query(AppEntrega).count() == 1 and db.query(AppArchivo).count() == 1
    assert db.get(AppRecepcion, codigo).estado == 'CERRADA'
    assert db.scalar(select(AppAuditoriaGeneral).where(AppAuditoriaGeneral.accion == 'ENVIO_RECUPERADO'))
    assert entregas.procesar_uno() and not entregas.procesar_uno()
    assert [a for a, _ in llamadas].count('finalizar') == 1 and llamadas[-1] == ('finalizar', ident)


def test_hmac_incorrecta_no_recupera_ni_cambia_remitente(admin, db, pendiente, monkeypatch):
    _, ident = pendiente
    def falla(*args): raise RuntimeError('La clave compartida no coincide con SERVIDOR_HMAC de este Apps Script.')
    monkeypatch.setattr(entregas, 'llamar', falla)
    r = admin.post(f'/api/app/entregas/{ident}/recuperar', json=confirmacion())
    assert r.status_code == 502 and 'SERVIDOR_HMAC' in r.text and 'No se recuperó' in r.text
    db.rollback(); db.expire_all(); e = db.get(AppEntrega, ident)
    assert e.datos['remitente'] == 'personal@example.test' and not e.datos.get('recuperaciones')


def test_solo_recupera_ultima_y_anula_la_anterior_en_misma_transaccion(admin, db, pendiente, monkeypatch):
    codigo, ident = pendiente
    db.rollback(); db.expire_all(); e = db.get(AppEntrega, ident)
    nueva = AppEntrega(id='b'*32, clave='c'*64, recepcion=codigo, usuario=e.usuario,
        datos=deepcopy(e.datos), estado='CANCELADA', creado_en=utcnow()+timedelta(seconds=1))
    db.add(nueva); db.commit()
    monkeypatch.setattr(entregas, 'llamar', google)
    assert admin.get(f'/api/app/entregas/{ident}/recuperar').status_code == 409
    r = admin.post(f'/api/app/entregas/{nueva.id}/recuperar', json=confirmacion())
    assert r.status_code == 200, r.text
    db.rollback(); db.expire_all()
    assert db.get(AppEntrega, ident).estado == 'CANCELADA' and db.get(AppEntrega, nueva.id).estado == 'PENDIENTE'
    assert db.query(AppEntrega).count() == 2


@pytest.mark.parametrize('estado', ['PROCESANDO', 'ENTREGADA', 'REVISION'])
def test_no_recupera_envios_confirmados_en_curso_o_ambiguos(admin, db, pendiente, estado, monkeypatch):
    _, ident = pendiente
    db.rollback(); db.expire_all(); e = db.get(AppEntrega, ident); e.estado = estado; db.commit()
    monkeypatch.setattr(entregas, 'llamar', lambda *a: pytest.fail('No consultar Google'))
    assert admin.post(f'/api/app/entregas/{ident}/recuperar', json=confirmacion()).status_code == 409


def test_solo_admin_y_confirmacion_explicita_y_remitente_vigente(admin, cliente, db, pendiente, monkeypatch):
    _, ident = pendiente
    monkeypatch.setattr(entregas, 'llamar', lambda *a: pytest.fail('No consultar Google'))
    assert cliente.get(f'/api/app/entregas/{ident}/recuperar').status_code == 403
    assert cliente.post(f'/api/app/entregas/{ident}/recuperar', json=confirmacion()).status_code == 403
    assert admin.post(f'/api/app/entregas/{ident}/recuperar', json={**confirmacion(), 'confirmarNoEnviado':False}).status_code == 422
    assert admin.post(f'/api/app/entregas/{ident}/recuperar', json={**confirmacion(), 'remitenteConfirmado':'falso@example.test'}).status_code == 409


def test_revalida_si_worker_o_configuracion_cambian_durante_google(admin, db, pendiente, monkeypatch):
    _, ident = pendiente
    def carrera(*args):
        # Sesión independiente; la comprobación no puede retener un bloqueo de recepción.
        from app.db import SessionLocal
        with SessionLocal() as otro:
            e = otro.get(AppEntrega, ident); e.estado = 'PROCESANDO'; otro.commit()
        return google(*args)
    monkeypatch.setattr(entregas, 'llamar', carrera)
    assert admin.post(f'/api/app/entregas/{ident}/recuperar', json=confirmacion()).status_code == 409
    db.rollback(); db.expire_all(); assert db.get(AppEntrega, ident).estado == 'PROCESANDO'


def test_historial_anulado_no_muestra_error_como_actual(admin, db, pendiente):
    _, ident = pendiente
    db.rollback(); db.expire_all(); e = db.get(AppEntrega, ident); e.error = 'Error HMAC antiguo'; db.commit()
    r = admin.post(f'/api/app/entregas/{ident}/cancelar', json={'motivo':'Anulación de un envío antiguo'})
    assert 'anulado' in r.json()['mensaje'] and r.json()['errorAnterior'] == 'Error HMAC antiguo'


def test_drive_crea_carpeta_con_responsable_y_muestra_fotos_locales(admin, cliente, db, pendiente, monkeypatch):
    codigo, _ = pendiente
    from tests.test_operacion_desarrollo import foto
    f = foto(cliente, codigo, tipoEvidencia='ESTADO_FINAL', categoria='RECEPCION')
    assert f.status_code == 201, f.text
    llamadas=[]
    def puente(accion, clave, datos):
        llamadas.append(accion); return {**google(accion, clave, datos), 'capacidades':['prepararCarpeta']}
    monkeypatch.setattr(entregas, 'llamar', puente)
    ruta=f'/api/operacion/recepciones/{codigo}/drive'
    r=admin.get(ruta)
    assert r.json()['sincronizacion']['guardadas'] == 1 and r.json()['sincronizacion']['copiadas'] == 0
    assert r.json()['destino']['supervisor'] == 'responsable@example.test'
    assert r.json()['archivos'][0]['enlace'] is None
    r=admin.post(ruta+'/preparar',json={}); assert r.status_code == 200, r.text
    assert r.json()['programadas'] == 1 and r.json()['carpeta'].startswith('https://drive.google.com/')
    assert admin.get(ruta).json()['carpetas'] == [r.json()['carpeta']]
    assert llamadas == ['estado','prepararCarpeta']  # Nunca finalizar/correo.
    assert cliente.post(ruta+'/preparar',json={}).status_code == 403


def test_drive_fallo_hmac_no_inventa_carpeta_ni_envia(admin, pendiente, monkeypatch):
    codigo,_=pendiente
    def falla(*a):raise RuntimeError('La clave compartida no coincide con SERVIDOR_HMAC de este Apps Script.')
    monkeypatch.setattr(entregas,'llamar',falla)
    r=admin.post(f'/api/operacion/recepciones/{codigo}/drive/preparar',json={})
    assert r.status_code==502 and 'SERVIDOR_HMAC' in r.text
    assert not admin.get(f'/api/operacion/recepciones/{codigo}/drive').json()['carpetas']


def test_foto_final_agregada_despues_del_cierre_se_incluye_antes_de_enviar(cliente, db, pendiente, monkeypatch):
    from tests.test_operacion_desarrollo import foto
    from app.services import drive
    from app.models import AppCopiaDrive
    codigo, ident = pendiente
    # Recuperar aquí el mismo trabajo con el responsable, sin repetir el cierre.
    db.rollback(); db.expire_all(); e=db.get(AppEntrega,ident)
    e.datos={**e.datos,'remitente':'responsable@example.test','modoRemitente':'RESPONSABLE'};db.commit()
    f=foto(cliente,codigo,tipoEvidencia='ESTADO_FINAL',categoria='RECEPCION')
    assert f.status_code==201,f.text
    llamadas=[]
    def puente(accion,clave,datos):
        llamadas.append((accion,datos));return {**google(accion,clave,datos),'fileId':'confirmado-'+clave.split(':')[-1],
            'tipoArchivo':datos.get('tipoArchivo'), 'nombre':datos.get('nombre'),
            'enlace':'https://drive.google.com/file/d/confirmado/view'}
    monkeypatch.setattr(entregas,'llamar',puente)
    assert entregas.procesar_uno()  # Espera a la foto; todavía no finaliza.
    assert not any(a=='finalizar' for a,_ in llamadas)
    assert drive.procesar_uno()
    db.rollback();db.expire_all()
    assert db.get(AppCopiaDrive,f.json()['id']).estado=='COPIADA'
    assert cliente.post(f'/api/app/entregas/{ident}/reintentar').status_code==200
    assert entregas.procesar_uno() and not entregas.procesar_uno()
    payload=next(d for a,d in llamadas if a=='finalizar')
    assert payload['manifiesto'][0]['archivoId']==f.json()['id']
    assert any(a['tipoArchivo']=='foto' for a in payload['archivos'])
    assert payload['resumen']['unidadesFisicas']==3
    db.rollback();db.expire_all()
    assert db.get(AppEntrega,ident).estado=='ENTREGADA'
    assert db.get(AppRecepcion,codigo).estado=='CERRADA' and db.query(AppEntrega).count()==1


def test_rechaza_informe_obsoleto_tras_reabrir_y_corregir(admin, cliente, db, pendiente, monkeypatch):
    from app.services import app_modelo as m
    codigo,ident=pendiente
    m.reabrir_recepcion(db,codigo,'sup','Corrección real posterior al informe')
    m.registrar_conteo(db,codigo,'op1',{'id':'nuevo-conteo','sku':'SKU1','cantidad':1,'pallet':'A2','confirmarSobrante':True})
    m.cerrar_recepcion(db,codigo,'sup')
    monkeypatch.setattr(entregas,'llamar',lambda *a:pytest.fail('No enviar un informe anterior al conteo actual'))
    r=admin.post(f'/api/app/entregas/{ident}/recuperar',json=confirmacion())
    assert r.status_code==409 and 'conteo cambió' in r.text


def test_supervisor_solicita_ultimo_informe_siempre_desde_su_cuenta(cliente,db,pendiente,monkeypatch):
    codigo,ident=pendiente
    def verificar(accion,clave,datos):
        assert datos['usuario']=='personal@example.test'
        return {'exito':True,'versionPuente':2,'remitente':datos['usuario'],'capacidades':['correoVerificado'],
            'enviadoA':datos.get('destinatarios',''),'fileId':'archivo-confirmado'}
    monkeypatch.setattr(entregas,'llamar',verificar)
    ruta=f'/api/app/entregas/{ident}/solicitar'
    assert cliente.get(ruta).json()['responsable']['correo']=='personal@example.test'
    r=cliente.post(ruta,json={**confirmacion(),'remitenteConfirmado':'personal@example.test','modoRemitente':'RESPONSABLE'})
    assert r.status_code==200,r.text
    assert r.json()['remitente']=='personal@example.test'
    assert entregas.procesar_uno() and not entregas.procesar_uno()
    db.rollback();db.expire_all();assert db.get(AppEntrega,ident).estado=='ENTREGADA'
