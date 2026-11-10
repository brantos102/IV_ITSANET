"""Permisos reales y contratos de integracion, sin contactar servicios empresariales."""
import json
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import config
from app.main import app
from app.models import AppConfig, Operador, Rol
from app.routers import google_auth
from app.security import hash_pin
from app.services import depot, integraciones


@pytest.fixture
def admin(cliente, db, monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'DATA_DIR', tmp_path)
    db.add(Operador(usuario='admin-api', nombre='Admin API', email='admin@example.test', rol=Rol.ADMIN, pin_hash=hash_pin('prueba123')))
    db.commit()
    c = TestClient(app)
    assert c.post('/api/auth/login', json={'usuario':'admin-api','pin':'prueba123'}).status_code == 200
    return c


def test_solo_admin_configura_o_prueba_credenciales(admin, cliente):
    anonimo = TestClient(app)
    assert anonimo.get('/api/app/integraciones').status_code == 401
    assert cliente.get('/api/app/integraciones').status_code == 403
    for ruta in ['/depot/VENTURA','/google','/oauth-google']:
        assert cliente.put('/api/app/integraciones'+ruta,json={}).status_code == 403
    assert cliente.post('/api/app/integraciones/depot/VENTURA/probar').status_code == 403
    assert cliente.post('/api/app/integraciones/google/probar', json={}).status_code == 403
    assert admin.get('/api/app/integraciones').status_code == 200


def test_claves_cifradas_no_regresan_y_el_vacio_conserva(admin, db, monkeypatch):
    ruta='/api/app/integraciones/depot/VENTURA'
    r=admin.put(ruta,json={'nombre':'Ventura','baseUrl':'https://wms.example.test/api','usuario':'usuario-reservado','clave':'clave-reservada'})
    assert r.status_code == 200,r.text
    assert 'clave-reservada' not in r.text and 'usuario-reservado' not in r.text
    guardada=db.get(AppConfig,'depot:VENTURA')
    assert 'clave-reservada' not in json.dumps(guardada.datos)
    assert admin.put(ruta,json={'nombre':'Ventura actualizada','clave':'','usuario':''}).status_code == 200
    db.rollback(); db.expire_all()
    api=depot.DepotAPI.desde_db(db,'VENTURA')
    assert api.usuario == 'usuario-reservado' and api.clave == 'clave-reservada'
    assert api.ruta_token == '/gettoken'
    monkeypatch.setattr(depot.DepotAPI,'token',lambda self,forzar=False:'token-nunca-publico')
    monkeypatch.setattr(depot.DepotAPI,'stock',lambda self:[])
    r=admin.post(ruta+'/probar'); assert r.status_code == 200
    assert 'token-nunca-publico' not in r.text
    assert 'credencial' not in admin.get('/api/app/integraciones').text


def test_dos_clientes_y_desactivacion_sin_borrar_catalogo(admin, db):
    for ident in ['VENTURA','GAC']:
        assert admin.put('/api/app/integraciones/depot/'+ident,json={'baseUrl':'https://wms.example.test','usuario':'usuario','clave':'clave'}).status_code == 200
    assert len(integraciones.credenciales(db)) == 2
    assert admin.put('/api/app/integraciones/depot/GAC',json={'activo':False}).status_code == 200
    db.rollback(); db.expire_all()
    assert [c['id'] for c in integraciones.credenciales(db)] == ['VENTURA']
    assert depot.DepotAPI.desde_db(db,'GAC') is None


def test_google_puente_editable_sin_exponer_secreto(admin, db):
    secreto='clave-compartida-prueba-' * 3
    assert admin.put('/api/app/integraciones/google',json={'url':'https://script.google.com/macros/s/test/exec','secreto':secreto}).status_code == 200
    assert secreto not in admin.get('/api/app/integraciones').text
    assert admin.put('/api/app/integraciones/google',json={'secreto':''}).status_code == 200
    db.rollback(); db.expire_all()
    assert integraciones.google(db)['secreto'] == secreto
    assert admin.put('/api/app/integraciones/google',json={'url':'http://otro-servidor/exec'}).status_code == 422


def configurar_oauth(admin, redirect='http://testserver/api/auth/google/callback'):
    # testserver no es un origen OAuth real permitido: usar localhost en el TestClient.
    return admin.put('/api/app/integraciones/oauth-google',json={'clientId':'prueba.apps.googleusercontent.com','clientSecret':'solo-prueba-secreta','redirectUri':redirect})


def test_oauth_google_requiere_origen_autorizado(admin):
    assert configurar_oauth(admin).status_code == 422
    assert configurar_oauth(admin,'http://localhost:3002/api/auth/google/callback').status_code == 200
    assert TestClient(app).get('/api/auth/metodos').json()['googleDisponible'] is False
    assert TestClient(app).get('/api/auth/google/iniciar',follow_redirects=False).status_code == 409
    assert 'solo-prueba-secreta' not in admin.get('/api/app/integraciones').text


@pytest.mark.parametrize('activo',[False,True])
def test_google_correo_verificado_conserva_aprobacion_y_sesion_local(admin, db, monkeypatch, activo):
    assert configurar_oauth(admin,'http://localhost/api/auth/google/callback').status_code == 200
    db.add(Operador(usuario='gmail-prueba',nombre='Gmail',email='gmail.prueba@gmail.com',activo=activo,rol=Rol.OPERADOR,pin_hash=hash_pin('contrasena-local'))); db.commit()
    monkeypatch.setattr(google_auth,'identidad',lambda *args:{'sub':'google-sub-prueba','email':'gmail.prueba@gmail.com','email_verified':True})
    c=TestClient(app,base_url='http://localhost')
    assert c.get('/api/auth/metodos').json()['googleDisponible'] is True
    inicio=c.get('/api/auth/google/iniciar',follow_redirects=False)
    args=parse_qs(urlparse(inicio.headers['location']).query)
    assert args['code_challenge_method'] == ['S256'] and 'client_secret' not in args
    r=c.get('/api/auth/google/callback',params={'state':args['state'][0],'code':'codigo-de-un-solo-uso'},follow_redirects=False)
    assert r.status_code == 303
    assert r.headers['location'] == ('/app/' if activo else '/app/?google=pendiente')
    assert c.get('/api/auth/yo').status_code == (200 if activo else 401)
    # Repetir callback sin cookie de flujo no abre una segunda sesion.
    assert c.get('/api/auth/google/callback',params={'state':args['state'][0],'code':'otro'},follow_redirects=False).headers['location'] == '/app/?google=error'


def test_google_nuevo_no_autoriza_ni_cambia_roles(admin, db, monkeypatch):
    assert configurar_oauth(admin,'http://localhost/api/auth/google/callback').status_code == 200
    monkeypatch.setattr(google_auth,'identidad',lambda *args:{'sub':'nuevo-sub','email':'nuevo@gmail.com','name':'Nuevo Google','email_verified':True})
    c=TestClient(app,base_url='http://localhost')
    inicio=c.get('/api/auth/google/iniciar',follow_redirects=False)
    estado=parse_qs(urlparse(inicio.headers['location']).query)['state'][0]
    assert c.get('/api/auth/google/callback',params={'state':'incorrecto','code':'x'},follow_redirects=False).headers['location'].endswith('error')
    inicio=c.get('/api/auth/google/iniciar',follow_redirects=False); estado=parse_qs(urlparse(inicio.headers['location']).query)['state'][0]
    r=c.get('/api/auth/google/callback',params={'state':estado,'code':'x'},follow_redirects=False)
    assert r.headers['location'].endswith('pendiente')
    db.rollback(); op=db.scalar(select(Operador).where(Operador.email=='nuevo@gmail.com'))
    assert op and op.activo is False and op.rol == Rol.OPERADOR


def test_catalogos_de_clientes_no_pisan_el_sku_de_otro_cliente(db):
    from app.models import Producto
    db.add(Producto(sku='SKUCOMPARTIDO',cliente='VENTURA',descripcion='Descripcion original'))
    db.commit()
    class Api:
        configurada=True
        cliente='GAC'
        def stock(self):
            return [depot.mapear_stock({'COD. PRODUCTO':'SKU-COMPARTIDO','COD. CLIENTE':'GAC','DESCRIPCION':'No reemplazar','CANTIDAD':3})]
    r=depot.sincronizar_maestro(db,api=Api(),evitar_conflictos=True)
    assert r['ambiguos'] == ['SKUCOMPARTIDO']
    assert db.get(Producto,'SKUCOMPARTIDO').descripcion == 'Descripcion original'



def test_caceria_consulta_el_total_actual_sin_crear_conteos(cliente, db):
    from app.services import app_modelo as m
    from app.models import AppEvento
    from sqlalchemy import func
    m.crear_recepcion(db, {'codigo':'CACERIA'}, 'sup')
    m.guardar_packing_list(db, 'CACERIA', {'lineas':[{'linea':1,'sku':'SKU1','cantidad':5}],'porSku':{'SKU1':5},'unidades':5})
    ruta='/api/app/recepciones/CACERIA/estado-sku/SKU1'
    for _ in range(3):
        r=cliente.get(ruta); assert r.status_code == 200 and r.json()['contado'] == 0
    assert db.scalar(select(func.count()).select_from(AppEvento)) == 0
    m.registrar_conteo(db,'CACERIA','op1',{'id':'evento-caceria','sku':'SKU1','cantidad':2,'pallet':'F1'})
    assert cliente.get(ruta).json()['contado'] == 2
    assert cliente.get(ruta).json()['verificado'] is True
    assert db.scalar(select(func.count()).select_from(AppEvento)) == 1


def test_intercambio_google_usa_pkce_y_rechaza_correo_sin_verificar(monkeypatch):
    import httpx
    from urllib.parse import parse_qs
    real = httpx.Client
    llamadas=[]
    def responder(request):
        llamadas.append(request)
        if request.url.path.endswith('/token'):
            cuerpo=parse_qs(request.content.decode())
            assert cuerpo['code_verifier'] == ['verificador-prueba']
            assert cuerpo['client_secret'] == ['secreto-prueba']
            return httpx.Response(200,json={'access_token':'token-prueba-no-real'})
        assert request.headers['Authorization'] == 'Bearer token-prueba-no-real'
        return httpx.Response(200,json={'sub':'sub-prueba','email':'correo@gmail.com','email_verified':False})
    monkeypatch.setattr(google_auth.httpx,'Client',lambda **kwargs:real(transport=httpx.MockTransport(responder),**kwargs))
    with pytest.raises(ValueError):
        google_auth.identidad({'clientId':'id','clientSecret':'secreto-prueba','redirectUri':'http://localhost/api/auth/google/callback'},'codigo','verificador-prueba')
    assert len(llamadas) == 2


def test_login_https_protege_la_cookie_y_no_publica_credenciales(cliente):
    c=TestClient(app,base_url='https://localhost')
    r=c.post('/api/auth/login',json={'usuario':'sup','pin':'1111'})
    assert r.status_code == 200
    cookie=r.headers['set-cookie'].lower()
    assert 'secure' in cookie and 'httponly' in cookie and 'samesite=lax' in cookie


def test_url_o_clave_con_saltos_no_se_guardan(admin):
    ruta='/api/app/integraciones/depot/TEST'
    assert admin.put(ruta,json={'baseUrl':'https://wms.example.test:puerto','usuario':'u','clave':'c'}).status_code == 422
    assert admin.put(ruta,json={'baseUrl':'https://wms.example.test','usuario':'u','clave':'c\nsecreto'}).status_code == 422


def test_puentes_por_supervisor_cifrados_y_sin_heredar_claves(admin,db,monkeypatch):
    ruta='/api/app/integraciones/google'
    for correo,ident in [('uno@gmail.com','uno'),('dos@gmail.com','dos')]:
        r=admin.put(ruta,json={'url':f'https://script.google.com/macros/s/{ident}/exec','secreto':ident*16,'supervisor':correo})
        assert r.status_code==200,r.text
    db.rollback();db.expire_all()
    assert integraciones.google(db,'uno@gmail.com')['url'].endswith('/uno/exec')
    assert integraciones.google(db,'dos@gmail.com')['secreto']=='dos'*16
    assert len(integraciones.puentes_publicos(db))==2
    assert 'uno'*16 not in admin.get('/api/app/integraciones').text
    assert admin.put(ruta,json={'supervisor':'otro@gmail.com','url':'https://script.google.com/macros/s/otro/exec'}).status_code==422
    from app.services import entregas
    llamadas=[]
    def probar(accion,clave,datos):
        llamadas.append(accion);return {'exito':True,'remitente':datos['usuario']}
    monkeypatch.setattr(entregas,'llamar',probar)
    assert admin.post(ruta+'/probar',json={'supervisor':'uno@gmail.com'}).status_code==200
    assert llamadas==['estado']


def test_diagnostico_api_identifica_token_o_stock_sin_secretos(admin,monkeypatch):
    ruta='/api/app/integraciones/depot/VENTURA'
    admin.put(ruta,json={'baseUrl':'https://wms.example.test','usuario':'u','clave':'c'})
    monkeypatch.setattr(depot.DepotAPI,'token',lambda self,forzar=False:'token-privado')
    monkeypatch.setattr(depot.DepotAPI,'stock',lambda self:[{'sku':'SKU1','cliente':'VENTURA'}])
    r=admin.post(ruta+'/probar');assert r.status_code==200
    assert r.json()['pasos']==['gettoken','getstock'] and r.json()['productos']==1
    assert 'token-privado' not in r.text
    def falla(self):raise depot.DepotNoDisponible('respuesta potencialmente privada')
    monkeypatch.setattr(depot.DepotAPI,'stock',falla)
    r=admin.post(ruta+'/probar');assert r.status_code==502
    assert 'gettoken correcto' in r.text and 'potencialmente privada' not in r.text


def test_diagnostico_500_tiene_referencia_sin_mensaje_ni_valores_privados(admin, monkeypatch, caplog):
    ruta = '/api/app/integraciones/depot/VENTURA'
    admin.put(ruta, json={'baseUrl': 'https://wms.example.test', 'usuario': 'u', 'clave': 'privada'})
    monkeypatch.setattr(depot.DepotAPI, 'token', lambda self, forzar=False: 'T')
    def falla(self):
        raise ValueError('no mostrar contraseña ni token-privado')
    monkeypatch.setattr(depot.DepotAPI, 'stock', falla)
    r = admin.post(ruta + '/probar')
    assert r.status_code == 500
    assert r.json()['detail']['codigo'] == 'DEPOT_INTERNO'
    assert 'getstock' in r.text and 'Referencia' in r.text
    assert 'ValueError' in caplog.text and 'ref=' in caplog.text
    assert 'token-privado' not in caplog.text + r.text
    assert 'no mostrar' not in caplog.text + r.text


def test_supervisor_ve_entrega_operativa_y_admin_ve_diagnostico(admin, cliente, db, monkeypatch, tmp_path):
    from app.services import archivos
    from app.models import AppEntrega
    from tests.test_entregas import preparar
    monkeypatch.setattr(archivos, 'DATA_DIR', tmp_path)
    codigo, datos = preparar(cliente, db)
    r = cliente.post(f'/api/app/recepciones/{codigo}/entrega', json=datos)
    ident = r.json()['id']
    db.rollback(); db.expire_all()
    e = db.get(AppEntrega, ident)
    e.error = 'Revisar SERVIDOR_HMAC y despliegue /exec'
    e.resultado = {'diagnostico': 'detalle-tecnico', 'carpeta': 'https://drive.google.com/folders/test'}
    db.commit()
    for ruta in ['/entregas', f'/recepciones/{codigo}/entregas']:
        r = cliente.get('/api/app' + ruta)
        assert r.status_code == 200
        assert 'SERVIDOR_HMAC' not in r.text and '/exec' not in r.text and 'detalle-tecnico' not in r.text
        assert r.json()[0]['resultado']['carpeta'].startswith('https://drive.google.com/')
    assert 'SERVIDOR_HMAC' in admin.get('/api/app/entregas').text
    assert cliente.get(f'/api/app/recepciones/{codigo.lower()}/entregas').json()[0]['id'] == ident
    assert 'correo_configurado' not in cliente.get('/api/app/estado').json()
    assert 'correo_configurado' in admin.get('/api/app/estado').json()
    assert cliente.get('/api/app/recepciones/NO-EXISTE/entregas').status_code == 404
