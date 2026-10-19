"""Revisión de correo, delegación administrativa y validación en todas las rutas."""
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.models import AppAuditoriaGeneral, AppConfig, AppEntrega, AppRecepcion, Operador, Rol, Sesion
from app.security import hash_pin, verify_pin
from app.services import app_modelo as m, entregas, integraciones
from app.services.instantaneas import expandir
from tests.test_remitente_responsable import correo


def api_correo(c):return f'/api/operacion/recepciones/{c}/correo'


def test_borrador_sin_google_edicion_escape_y_conflicto(cliente,db,correo):
    codigo,_=correo
    r=cliente.get(api_correo(codigo));assert r.status_code==200,r.text
    v=r.json();assert 'Sin diferencias' in v['html']
    assert 'SKU1' in v['html'] and v['validacionDepot']['porSku']['SKU1']['estado']=='SIN_VALIDAR'
    campos={**v['campos'],'asunto':'Informe revisado','notas':'<img src=x onerror=alert(1)>','destinatarios':'otro@example.test'}
    g=cliente.put(api_correo(codigo),json={'version':v['version'],'campos':campos})
    assert g.status_code==200,g.text
    assert '&lt;img' in g.json()['html'] and '<img src=x' not in g.json()['html']
    assert cliente.put(api_correo(codigo),json={'version':v['version'],'campos':campos}).status_code==409
    for email in ('personal@example.test','responsable@example.test'):
        f=db.get(AppConfig,integraciones._clave_google(email))
        if f:db.delete(f)
    db.commit()
    sin_google=cliente.get(api_correo(codigo))
    assert sin_google.status_code==200 and not sin_google.json()['conexionConfigurada']
    op=TestClient(app);op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    assert op.get(api_correo(codigo)).status_code==403


def test_correo_final_congelado_y_cambio_de_recepcion_no_cierra(cliente,db,correo,monkeypatch):
    codigo,datos=correo
    v=cliente.get(api_correo(codigo)).json()
    campos={**v['campos'],'asunto':'Recepción revisada por el supervisor','destinatarios':datos['destinatarios']}
    v=cliente.put(api_correo(codigo),json={'version':v['version'],'campos':campos}).json()
    datos.update(correoVersion=v['version'],remitenteConfirmado='personal@example.test',modoRemitente='PERSONAL')
    r=cliente.post(f'/api/app/recepciones/{codigo}/entrega',json=datos)
    assert r.status_code==201,r.text
    db.rollback();db.expire_all();e=db.get(AppEntrega,r.json()['id'])
    assert expandir(e.datos)['correoFinal']['asunto']==campos['asunto']
    llamadas=[]
    def google(accion,clave,payload):
        llamadas.append((accion,payload))
        return {'exito':True,'remitente':'personal@example.test','capacidades':['correoEditable'],
                'fileId':'archivo-prueba-confirmado','enviadoA':datos['destinatarios']}
    monkeypatch.setattr(entregas,'llamar',google)
    assert entregas.procesar_uno()
    final=[p for a,p in llamadas if a=='finalizar'][0]
    assert final['correoFinal']['asunto']==campos['asunto'] and final['correoFinal']['html']==v['html']


def test_correo_obsoleto_no_cierra(cliente,db,correo):
    codigo,datos=correo
    v=cliente.get(api_correo(codigo)).json()
    v=cliente.put(api_correo(codigo),json={'version':v['version'],'campos':{**v['campos'],'destinatarios':datos['destinatarios']}}).json()
    m.registrar_conteo(db,codigo,'sup',{'id':'nuevo-conteo-40','sku':'SKU1','cantidad':1,'pallet':'A02','confirmarSobrante':True})
    datos.update(correoVersion=v['version'],remitenteConfirmado='personal@example.test',eventos=[e['id'] for e in cliente.get(f'/api/app/recepciones/{codigo}/eventos').json()])
    r=cliente.post(f'/api/app/recepciones/{codigo}/entrega',json=datos)
    assert r.status_code==409 and 'correo' in r.text
    db.rollback();db.expire_all();assert db.get(AppRecepcion,codigo).estado!='CERRADA'


def test_admin_configura_google_del_perfil_sin_exponer_claves(cliente,db,monkeypatch,tmp_path):
    from app import config
    monkeypatch.setattr(config,'DATA_DIR',tmp_path)
    sup=db.scalar(select(Operador).where(Operador.usuario=='sup'));sup.email='sup@example.test';db.commit()
    ruta=f'/api/app/integraciones/usuarios/{sup.id}/google'
    assert cliente.get(ruta).status_code==403
    admin=Operador(usuario='admin40',nombre='Admin',rol=Rol.ADMIN,pin_hash=hash_pin('secretoadmin'),activo=True);db.add(admin);db.commit()
    c=TestClient(app);c.post('/api/auth/login',json={'usuario':'admin40','pin':'secretoadmin'})
    monkeypatch.setattr(entregas,'llamar_conexion',lambda *args:{'remitente':sup.email,'capacidades':['correoVerificado']})
    clave='clave-prueba-configurar-perfil-'*2
    for secreto in (clave,''):
        r=c.put(ruta,json={'url':'https://script.google.com/macros/s/perfil40/exec','secreto':secreto})
        assert r.status_code==200,r.text
        assert clave not in r.text and 'credencial' not in r.text
    db.rollback();db.expire_all()
    a=db.scalar(select(AppAuditoriaGeneral).where(AppAuditoriaGeneral.accion=='CORREO_PROPIO_AUTORIZADO'))
    assert a.usuario=='admin40' and a.datos['configuradoPorAdmin']


def test_reset_admin_revoca_sesiones_y_no_guarda_clave_en_auditoria(cliente,db):
    op=db.scalar(select(Operador).where(Operador.usuario=='op1'))
    ruta=f'/api/auth/operadores/{op.id}/restablecer-clave'
    assert cliente.post(ruta,json={'nueva':'nueva-segura-40'}).status_code==403
    db.add(Operador(usuario='admin40',nombre='Admin',rol=Rol.ADMIN,pin_hash=hash_pin('secretoadmin')));db.commit()
    usuario=TestClient(app);usuario.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    c=TestClient(app);c.post('/api/auth/login',json={'usuario':'admin40','pin':'secretoadmin'})
    r=c.post(ruta,json={'nueva':'nueva-segura-40'});assert r.status_code==200,r.text
    assert usuario.get('/api/auth/yo').status_code==401
    assert 'nueva-segura-40' not in c.get('/api/auth/operadores').text
    db.rollback();db.expire_all();assert verify_pin('nueva-segura-40',db.get(Operador,op.id).pin_hash)
    assert 'nueva-segura-40' not in json.dumps([a.datos for a in db.scalars(select(AppAuditoriaGeneral))])


def test_cliente_nombre_y_unificacion_no_modifican_historicos(cliente,db,correo):
    codigo,_=correo
    from app.services import ajustes
    ajustes.guardar(db,{'clientes':{'PRUEBA':{},'OTRO':{}}},'sup')
    r=cliente.put('/api/operacion/clientes-fichas',json={'id':'PRUEBA','nombre':'Cliente corregido','unificarCon':'OTRO','version':0})
    assert r.status_code==200,r.text
    db.rollback();db.expire_all();assert db.get(AppRecepcion,codigo).cliente=='PRUEBA'
    fichas=cliente.get('/api/operacion/clientes-operacion').json()
    assert next(c for c in fichas if c['id']=='PRUEBA')['nombre']=='Cliente corregido'
    assert cliente.put('/api/operacion/clientes-fichas',json={'id':'OTRO','nombre':'Otro','unificarCon':'PRUEBA','version':0}).status_code in (409,422)


@pytest.mark.parametrize('codigo',['PO"','A/B','B_01','A..1','A--B','A#1','A-'])
def test_pallet_invalido_en_conteo_y_unidad(cliente,db,correo,codigo):
    recepcion,_=correo
    r=cliente.post(f'/api/app/recepciones/{recepcion}/conteos',json={'id':'conteo-invalido-40','sku':'SKU1','cantidad':1,'pallet':codigo,'confirmarSobrante':True})
    assert r.status_code==422,r.text
    r=cliente.post(f'/api/operacion/recepciones/{recepcion}/unidades',json={'tipo':'BULTO','pallet':codigo})
    assert r.status_code==422,r.text


@pytest.mark.parametrize('pallet',['A01','DP','B02.1','A01-B02.3'])
def test_regla_pallet_compartida(pallet):
    from app.services.normalize import pallet_valido,normalizar_pallet
    assert normalizar_pallet(pallet)==pallet and pallet_valido(pallet)


def test_impresion_cantidad_editable_y_validada():
    from app.routers.impresion import zpl
    from fastapi import HTTPException
    assert '\\32\\35' in zpl({'sku':'SKU40','cantidad':25},3)
    for cantidad in (0,-1,True,float('nan'),1000001):
        with pytest.raises(HTTPException):zpl({'sku':'SKU40','cantidad':cantidad},1)


def test_manual_pausa_cola_declara_envio_y_no_inventa_acuse(cliente,db,correo,monkeypatch):
    codigo,datos=correo
    v=cliente.get(api_correo(codigo)).json()
    cliente.put(api_correo(codigo),json={'version':v['version'],'campos':{**v['campos'],'destinatarios':datos['destinatarios']}})
    r=cliente.post(f'/api/app/recepciones/{codigo}/entrega',json={**datos,'remitenteConfirmado':'personal@example.test'})
    assert r.status_code==201,r.text
    ident=r.json()['id'];v=cliente.get(api_correo(codigo)+'?entregaId='+ident).json()
    body={'entregaId':ident,'correoVersion':v['version'],'accion':'PREPARAR','confirmar':True}
    r=cliente.post(api_correo(codigo)+'/manual',json=body);assert r.status_code==200,r.text
    monkeypatch.setattr(entregas,'llamar',lambda *a:pytest.fail('Manual nunca debe llamar a Google'))
    assert not entregas.procesar_uno()
    assert cliente.post(api_correo(codigo)+'/manual',json={**body,'accion':'CONFIRMAR'}).status_code==200
    v=cliente.get(api_correo(codigo)+'?entregaId='+ident).json()
    assert v['manual']['estado']=='DECLARADO_ENVIADO' and v['soloLectura']
    db.rollback();db.expire_all();e=db.get(AppEntrega,ident)
    assert e.estado=='CANCELADA' and not e.resultado
    assert e.datos['correoManual']['estado']=='DECLARADO_ENVIADO'


def test_cierre_manual_sin_google_guarda_documentos_no_programa_envio(cliente,db,correo):
    codigo,datos=correo
    # Se puede preparar el cierre manual aunque no haya conexiones utilizables.
    v=cliente.get(api_correo(codigo)).json()
    v=cliente.put(api_correo(codigo),json={'version':v['version'],'campos':{**v['campos'],'destinatarios':datos['destinatarios']}}).json()
    r=cliente.post(f'/api/app/recepciones/{codigo}/entrega',json={**datos,'modoEntrega':'MANUAL','correoVersion':v['version']})
    assert r.status_code==201,r.text
    assert r.json()['estado']=='CANCELADA' and r.json()['correoManual']['estado']=='PREPARADO'
    db.rollback();db.expire_all();assert db.get(AppRecepcion,codigo).estado=='CERRADA'
    assert not entregas.procesar_uno()


def test_codigo_de_recepcion_largo_cabe_en_config_sin_cambiar_identidad(cliente,db):
    codigo='RECEPCION-'+('X'*50)
    assert len(codigo)==60
    m.crear_recepcion(db,{'codigo':codigo,'cliente':'PRUEBA'},'sup')
    v=cliente.get(api_correo(codigo)).json()
    r=cliente.put(api_correo(codigo),json={'version':v['version'],'campos':{**v['campos'],'destinatarios':'destino@example.test'}})
    assert r.status_code==200,r.text
    from app.services.correo_redactado import clave_config
    assert len(clave_config(codigo))<=40 and len(clave_config(codigo,manual=True))<=40
    assert cliente.get(api_correo(codigo)).json()['campos']['destinatarios']=='destino@example.test'
    assert db.get(AppRecepcion,codigo)


def test_foto_pendiente_permite_manual_y_evitar_correo_automatico_obsoleto(cliente,db,correo):
    import base64,io
    from PIL import Image
    codigo,datos=correo
    contenido=io.BytesIO();Image.new('RGB',(8,8),'blue').save(contenido,format='PNG')
    r=cliente.post(f'/api/app/recepciones/{codigo}/archivos/foto',json={'nombre':'SKU1.png','tipo':'image/png',
        'base64':base64.b64encode(contenido.getvalue()).decode(),'sku':'SKU1','desdeSku':True,'tipoEvidencia':'ADICIONAL'})
    assert r.status_code==201,r.text
    v=cliente.get(api_correo(codigo)).json()
    v=cliente.put(api_correo(codigo),json={'version':v['version'],'campos':{**v['campos'],'destinatarios':datos['destinatarios']}}).json()
    assert cliente.post(f'/api/app/recepciones/{codigo}/comprobar-envio',json={'correoEditable':True}).status_code==409
    datos.update(correoVersion=v['version'],remitenteConfirmado='personal@example.test',eventos=[e['id'] for e in cliente.get(f'/api/app/recepciones/{codigo}/eventos').json()])
    r=cliente.post(f'/api/app/recepciones/{codigo}/entrega',json=datos)
    assert r.status_code==409 and 'fotos' in r.text
    r=cliente.post(f'/api/app/recepciones/{codigo}/entrega',json={**datos,'modoEntrega':'MANUAL'})
    assert r.status_code==201,r.text
    assert r.json()['correoManual']['estado']=='PREPARADO'
