"""El autor del cierre y el remitente autorizado son identidades distintas."""
import json

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from app import config
from app.main import app
from app.models import AppEntrega, AppRecepcion, Operador, Rol
from app.security import hash_pin
from app.services import archivos, entregas, integraciones, operacion
from tests.test_entregas import preparar


@pytest.fixture
def correo(cliente, db, monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(archivos, 'DATA_DIR', tmp_path)
    sup = db.scalar(select(Operador).where(Operador.usuario == 'sup'))
    sup.email = 'personal@example.test'
    db.add(Operador(usuario='responsable', email='responsable@example.test', nombre='Responsable',
        rol=Rol.SUPERVISOR, activo=True, pin_hash=hash_pin('prueba-responsable')))
    db.commit()
    for email in ['responsable@example.test', 'personal@example.test']:
        integraciones.guardar_google(db, {'supervisor':email,
            'url':'https://script.google.com/macros/s/puente-prueba/exec','secreto':'clave-de-prueba-'*3}, 'admin')
    operacion.guardar_config(db, {'correo':{'responsable':'responsable@example.test','permitirPersonal':True}}, 'admin')
    return preparar(cliente, db)


def test_opciones_correo_sin_secreto_y_responsable_predeterminado(cliente, correo):
    codigo, _ = correo
    r = cliente.get(f'/api/app/recepciones/{codigo}/remitentes')
    assert r.status_code == 200 and r.json()['predeterminado'] == 'PERSONAL'
    assert r.json()['opciones'] == [
        {'modo':'RESPONSABLE','correo':'responsable@example.test','disponible':True},
        {'modo':'PERSONAL','correo':'personal@example.test','disponible':True}]
    assert 'clave-de-prueba' not in r.text and 'script.google' not in r.text
    op=TestClient(app);op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    assert op.get(f'/api/app/recepciones/{codigo}/remitentes').status_code == 403


def test_unico_puente_configurado_se_propone_sin_necesitar_cambiar_codigo(cliente, db, correo):
    from app.models import AppConfig
    codigo,_=correo
    operacion.guardar_config(db, {'correo':{'responsable':'','permitirPersonal':True}}, 'admin')
    db.delete(db.get(AppConfig,integraciones._clave_google('personal@example.test')));db.commit()
    opcion=cliente.get(f'/api/app/recepciones/{codigo}/remitentes').json()['opciones'][0]
    assert opcion=={'modo':'RESPONSABLE','correo':'responsable@example.test','disponible':True}


def test_configuracion_de_correo_exclusiva_de_admin(cliente):
    assert cliente.put('/api/operacion/config',json={'correo':{'responsable':'falso@example.test'}}).status_code==403


@pytest.mark.parametrize('modo, remitente', [(None,'personal@example.test'),('PERSONAL','personal@example.test')])
def test_encola_remitente_correcto_conservando_autor_y_sin_suplantacion(cliente, db, correo, modo, remitente, monkeypatch):
    codigo, datos = correo
    if modo: datos['modoRemitente']=modo
    datos.update(remitente='falso@example.test',usuario='falso',remitenteConfirmado=remitente)
    r=cliente.post(f'/api/app/recepciones/{codigo}/entrega',json=datos)
    assert r.status_code == 201, r.text
    assert r.json()['remitente']==remitente and r.json()['supervisor']=='personal@example.test'
    llamadas=[]
    def google(accion, clave, payload):
        llamadas.append((accion,payload))
        assert payload['usuario']==remitente
        return {'exito':True,'remitente':remitente,'fileId':'archivo-prueba-confirmado','enviadoA':payload.get('destinatarios','')}
    monkeypatch.setattr(entregas,'llamar',google)
    assert entregas.procesar_uno()
    assert [a for a,_ in llamadas]==['estado','archivo','finalizar']
    assert llamadas[-1][1]['solicitadoPor']=='personal@example.test'
    db.rollback();db.expire_all();e=db.get(AppEntrega,r.json()['id'])
    assert e.estado=='ENTREGADA' and e.usuario=='personal@example.test'
    assert not entregas.procesar_uno()  # No vuelve a enviar.


@pytest.mark.parametrize('cambio, modo', [('sin-personal','PERSONAL'),('inactivo','RESPONSABLE'),('sin-puente','PERSONAL'),('cambio-remitente','RESPONSABLE'),('modo-invalido','OTRO')])
def test_cuenta_no_autorizada_no_cierra_ni_envia(cliente, db, correo, cambio, modo):
    codigo, datos=correo
    if cambio=='sin-personal':
        operacion.guardar_config(db, {'correo':{'responsable':'responsable@example.test','permitirPersonal':False}}, 'admin')
    if cambio=='inactivo':
        db.scalar(select(Operador).where(Operador.usuario=='responsable')).activo=False;db.commit()
    if cambio=='sin-puente':
        from app.models import AppConfig
        db.delete(db.get(AppConfig,integraciones._clave_google('personal@example.test')));db.commit()
    datos['modoRemitente']=modo
    if cambio=='cambio-remitente':datos['remitenteConfirmado']='otra-cuenta@example.test'
    r=cliente.post(f'/api/app/recepciones/{codigo}/entrega',json=datos)
    assert r.status_code in (409,422), r.text
    db.rollback();db.expire_all()
    assert db.get(AppRecepcion,codigo).estado!='CERRADA'
    assert db.query(AppEntrega).count()==0


def test_no_confirma_ni_reenvia_si_falta_acuse_del_remitente(cliente, db, correo, monkeypatch):
    codigo,datos=correo;datos['modoRemitente']='PERSONAL'
    r=cliente.post(f'/api/app/recepciones/{codigo}/entrega',json=datos);assert r.status_code==201
    def google(accion,*args):
        return {'exito':True,'remitente':'personal@example.test','fileId':'archivo-prueba-confirmado'} if accion!='finalizar' else {'exito':True,'remitente':'otra@example.test'}
    monkeypatch.setattr(entregas,'llamar',google)
    assert entregas.procesar_uno()
    db.rollback();db.expire_all();assert db.get(AppEntrega,r.json()['id']).estado=='REVISION'
    assert not entregas.procesar_uno()


@pytest.mark.parametrize('mensaje, pista', [
    ('Session.getEffectiveUser requires https://www.googleapis.com/auth/userinfo.email', 'leer la cuenta remitente'),
    ('MailApp: auth/script.send_mail required', 'Falta autorización para enviar correo'),
    ('DriveApp.getFolderById failed: no item with the given id', 'no puede abrir la carpeta'),
    ('CARPETA_EVIDENCIAS missing', 'carpeta raíz'),
    ('MailApp quota exceeded', 'cuota de correo'),
    ('El despliegue debe ejecutarse como el supervisor responsable', 'remitente seleccionado'),
    ('error desconocido token=secreto-sensible', 'verificarGoogleServidor'),
])
def test_diagnostico_google_especifico_sin_filtrar_secretos(mensaje,pista):
    texto=entregas._error_google({'mensaje':mensaje})
    assert pista in texto and 'secreto-sensible' not in texto
