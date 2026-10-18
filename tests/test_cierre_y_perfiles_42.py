"""Resolución manual auditable, revisión por actor y fotografías privadas."""
import base64
import io
import os
from copy import deepcopy
from datetime import timedelta

from fastapi.testclient import TestClient
from PIL import Image
import pytest
from sqlalchemy import select

from app.main import app
from app.models import AppArchivo, AppAuditoriaGeneral, AppConfig, AppEntrega, AppRecepcion, utcnow
from app.services import entregas
from tests.test_integraciones_ui import admin
from tests.test_recuperar_entrega import pendiente
from tests.test_remitente_responsable import correo


def revisado(cliente, codigo, datos, ident=None):
    ruta=f'/api/operacion/recepciones/{codigo}/correo'
    if ident:
        return cliente.get(ruta+'?entregaId='+ident).json()
    v=cliente.get(ruta).json()
    r=cliente.put(ruta,json={'version':v['version'],'campos':{**v['campos'],'destinatarios':datos['destinatarios']}})
    assert r.status_code==200,r.text
    return r.json()


def declarar(cliente,codigo,ident):
    e=next(e for e in cliente.get('/api/app/entregas').json() if e['id']==ident)
    v=revisado(cliente,codigo,{},ident)
    return {'versionGestion':e['versionGestion'],'correoVersion':v['version'],
        'confirmarEnviado':True,'motivo':'Revisé el mensaje y sus adjuntos en Enviados.'}


def test_declarar_historico_detiene_reintentos_y_archiva_sin_borrar(cliente,db,pendiente,monkeypatch):
    codigo,ident=pendiente
    body=declarar(cliente,codigo,ident)
    monkeypatch.setattr(entregas,'llamar',lambda *a:pytest.fail('No debe enviar a Google'))
    r=cliente.post(f'/api/app/entregas/{ident}/manual-confirmado',json=body)
    assert r.status_code==200,r.text
    e=r.json()
    assert e['estado']=='CANCELADA' and e['correoManual']['estado']=='DECLARADO_ENVIADO'
    assert not entregas.procesar_uno()
    assert cliente.post(f'/api/app/entregas/{ident}/manual-confirmado',json=body).status_code==409
    ruta=f'/api/app/entregas/{ident}/historial'
    datos={'versionGestion':e['versionGestion'],'archivar':True,'motivo':'Retirar del listado visible una entrega ya resuelta'}
    r=cliente.post(ruta,json=datos);assert r.status_code==200,r.text
    assert r.json()['archivado']
    assert cliente.get('/api/app/entregas').json()==[]
    todos=cliente.get('/api/app/entregas?archivadas=true').json()
    assert len(todos)==1 and todos[0]['archivado']
    assert cliente.post(ruta,json=datos).status_code==409
    r=cliente.post(ruta,json={**datos,'archivar':False,'versionGestion':todos[0]['versionGestion']})
    assert r.status_code==200 and not r.json()['archivado'],r.text
    db.rollback();db.expire_all()
    assert db.get(AppRecepcion,codigo).estado=='CERRADA'
    assert db.query(AppArchivo).count()==1 and db.query(AppEntrega).count()==1
    assert db.scalar(select(AppAuditoriaGeneral).where(AppAuditoriaGeneral.accion=='ENVIO_MANUAL_HISTORICO_DECLARADO'))


@pytest.mark.parametrize('cambio',['procesando','reabierta','revision-ajena','sin-confirmar','version-antigua'])
def test_declaracion_no_acepta_estado_cambiado_o_revision_de_otro_actor(cliente,admin,db,pendiente,cambio):
    codigo,ident=pendiente
    body=declarar(cliente,codigo,ident)
    if cambio=='procesando':
        db.rollback();db.get(AppEntrega,ident).estado='PROCESANDO';db.commit()
        body['versionGestion']=next(e for e in cliente.get('/api/app/entregas').json() if e['id']==ident)['versionGestion']
    elif cambio=='reabierta':
        db.rollback();db.get(AppRecepcion,codigo).estado='EN_VALIDACION';db.commit()
    elif cambio=='revision-ajena':body['correoVersion']=revisado(admin,codigo,{},ident)['version']
    elif cambio=='sin-confirmar':body['confirmarEnviado']=False
    else:body['versionGestion']='obsoleta'
    r=cliente.post(f'/api/app/entregas/{ident}/manual-confirmado',json=body)
    assert r.status_code in (409,422),r.text
    db.rollback();db.expire_all()
    assert not db.get(AppEntrega,ident).datos.get('correoManual')


def test_no_retirar_del_historial_una_entrega_activa(cliente,pendiente):
    _,ident=pendiente;e=cliente.get('/api/app/entregas').json()[0]
    r=cliente.post(f'/api/app/entregas/{ident}/historial',json={'versionGestion':e['versionGestion'],
        'archivar':True,'motivo':'No esconder trabajos que todavía esperan entrega'})
    assert r.status_code==409,r.text


def test_ultima_entrega_se_calcula_incluso_si_la_mas_reciente_fue_archivada(cliente,db,pendiente):
    codigo,ident=pendiente;db.rollback();anterior=db.get(AppEntrega,ident)
    nueva=AppEntrega(id='d'*32,clave='e'*64,recepcion=codigo,usuario=anterior.usuario,
        datos={**deepcopy(anterior.datos),'historialOculto':True},estado='CANCELADA',creado_en=utcnow()+timedelta(seconds=1))
    db.add(nueva);db.add(AppConfig(clave='he:'+nueva.id,datos={'entregaId':nueva.id},usuario='sup'));db.commit()
    visible=cliente.get('/api/app/entregas').json()
    assert len(visible)==1 and not visible[0]['esUltima']
    todos=cliente.get('/api/app/entregas?archivadas=true').json()
    assert next(e for e in todos if e['id']==nueva.id)['esUltima']


def test_reutilizar_informe_exige_datos_actuales_y_mismo_autor(cliente,admin,db,correo):
    from app.services import app_modelo as m
    codigo,datos=correo;ruta=f'/api/operacion/recepciones/{codigo}/informes'
    r=cliente.post(ruta,json={'clave':'crear-reutilizable42','tipo':'DESCARGA','ultimoVisto':None});assert r.status_code==200,r.text
    ident=r.json()['id'];sufijo=r.json()['sufijo']
    adjuntos=[{**a,'nombre':'reutilizable'+sufijo+'.xlsx'} for a in datos['adjuntos']]
    r=cliente.put(ruta+'/'+ident,json={'adjuntos':adjuntos});assert r.status_code==200,r.text
    cuerpo={'clave':'reutilizar-sin-version42','tipo':'DESCARGA','ultimoVisto':ident,'reutilizarId':ident}
    r=cliente.post(ruta,json=cuerpo);assert r.status_code==200 and r.json()['id']==ident,r.text
    assert len(cliente.get(ruta).json())==1
    assert admin.post(ruta,json=cuerpo).status_code==409
    m.registrar_conteo(db,codigo,'op1',{'id':'cambio-informe42','sku':'SKU1','cantidad':1,'pallet':'A2','confirmarSobrante':True})
    assert cliente.post(ruta,json=cuerpo).status_code==409


def test_cerrar_ya_enviado_manualmente_requiere_confirmacion_y_retry_es_del_mismo_actor(cliente,admin,db,correo,monkeypatch):
    codigo,datos=correo;v=revisado(cliente,codigo,datos)
    body={**datos,'modoEntrega':'MANUAL_ENVIADO','correoVersion':v['version'],
        'confirmarEnviadoManual':False,'motivoManual':'Revisé el correo y adjuntos enviados desde Gmail.'}
    ruta=f'/api/app/recepciones/{codigo}/entrega'
    assert cliente.post(ruta,json=body).status_code==422
    body['confirmarEnviadoManual']=True
    monkeypatch.setattr(entregas,'llamar',lambda *a:pytest.fail('No debe enviar a Google'))
    r=cliente.post(ruta,json=body);assert r.status_code==201,r.text
    ident=r.json()['id']
    assert r.json()['correoManual']['estado']=='DECLARADO_ENVIADO'
    assert cliente.post(ruta,json=body).json()['id']==ident
    assert admin.post(ruta,json=body).status_code==409
    assert not entregas.procesar_uno()
    db.rollback();db.expire_all()
    assert db.get(AppRecepcion,codigo).estado=='CERRADA' and db.query(AppEntrega).count()==1


def test_foto_propia_se_sanea_y_no_permite_suplantar_otro_usuario(cliente,operadores):
    bruto=io.BytesIO();Image.new('RGBA',(400,300),'blue').save(bruto,'PNG')
    r=cliente.put('/api/auth/perfil/foto',json={'operador_id':operadores['op1'].id,'base64':base64.b64encode(bruto.getvalue()).decode()})
    assert r.status_code==200,r.text
    ruta=r.json()['photoURL'];assert ruta.startswith(f'/api/auth/operadores/{operadores["sup"].id}/foto?')
    foto=cliente.get(ruta);assert foto.status_code==200 and foto.headers['content-type']=='image/jpeg'
    with Image.open(io.BytesIO(foto.content)) as imagen:
        assert imagen.size==(256,256) and not imagen.getexif()
    assert cliente.get(f'/api/auth/operadores/{operadores["op1"].id}/foto').status_code==404
    assert cliente.get('/api/auth/yo').json()['photoURL']==ruta
    anonimo=TestClient(app)
    assert anonimo.get(ruta).status_code==401
    assert anonimo.put('/api/auth/perfil/foto',json={}).status_code==401


@pytest.mark.parametrize('datos,status',[({'base64':base64.b64encode(b'<svg></svg>').decode()},422),({'base64':'@no-es-base64'},422),({'base64':'A'*3_000_001},413)])
def test_foto_invalida_no_se_guarda(cliente,datos,status):
    assert cliente.put('/api/auth/perfil/foto',json=datos).status_code==status
    assert cliente.get('/api/auth/yo').json()['photoURL']==''


def test_secretos_de_pruebas_reutilizan_archivos_privados_sin_imprimir(tmp_path,capsys):
    from scripts.preparar_pruebas_publicas import preparar
    preparar(tmp_path);ruta=tmp_path/'entorno.env';original=ruta.read_bytes()
    preparar(tmp_path)
    assert ruta.read_bytes()==original and capsys.readouterr().out==''
    assert os.stat(ruta).st_mode&0o777==0o600
    assert os.stat(tmp_path).st_mode&0o777==0o700
    assert 'supervisor.prueba' in (tmp_path/'accesos-iniciales.txt').read_text()
