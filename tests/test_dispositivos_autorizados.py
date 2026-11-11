"""Control optativo: preparación, dos tipos de equipo, sesión única y revocación."""
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.models import AppConfig, DispositivoUsuario, Operador, Rol, Sesion
from app.services.dispositivos import cookie


def solicitud(c,usuario='op1',tipo='MOVIL',nombre='Handheld de prueba'):
    return c.post('/api/auth/dispositivos/solicitar',json={
        'usuario':usuario,'pin':'1111' if usuario=='sup' else '2222','tipo':tipo,'nombre':nombre})


def aprobar(admin,ident,**datos):
    return admin.post('/api/auth/dispositivos/admin/'+ident+'/aprobar',json={'presencial':True,**datos})


def preparar_admin(cliente,db,activar=True):
    op=db.scalar(select(Operador).where(Operador.usuario=='sup'));op.rol=Rol.ADMIN;db.commit()
    r=solicitud(cliente,'sup','LAPTOP','Laptop de ADMIN');assert r.status_code==200,r.text
    assert aprobar(cliente,r.json()['equipo']['id']).status_code==200
    if activar:
        r=cliente.put('/api/auth/dispositivos/admin/politica',json={'activo':True});assert r.status_code==200,r.text
    return op


def entrar(c,usuario='op1'):
    return c.post('/api/auth/login',json={'usuario':usuario,'pin':'2222' if usuario=='op1' else '1111'})


def registrar_y_entrar(admin,c,tipo='MOVIL'):
    r=solicitud(c,tipo=tipo);assert r.status_code==200,r.text
    ident=r.json()['equipo']['id'];assert aprobar(admin,ident).status_code==200
    assert entrar(c).status_code==200
    return ident


def test_control_no_cambia_acceso_antes_de_activarlo(cliente,db):
    c=TestClient(app);assert entrar(c).status_code==200
    otro=TestClient(app);assert entrar(otro).status_code==200
    assert c.get('/api/auth/yo').status_code==otro.get('/api/auth/yo').status_code==200


def test_no_activa_sin_equipo_aprobado_del_admin(cliente,db):
    op=db.scalar(select(Operador).where(Operador.usuario=='sup'));op.rol=Rol.ADMIN;db.commit()
    r=cliente.put('/api/auth/dispositivos/admin/politica',json={'activo':True})
    assert r.status_code==409 and cliente.get('/api/auth/yo').status_code==200
    assert db.get(AppConfig,'seguridad_dispositivos') is None


def test_pendiente_no_autoriza_y_aprobacion_es_presencial(cliente,db):
    preparar_admin(cliente,db);c=TestClient(app)
    r=entrar(c);assert r.status_code==403 and r.json()['detail']['codigo']=='EQUIPO_NO_AUTORIZADO'
    r=solicitud(c);ident=r.json()['equipo']['id']
    assert entrar(c).status_code==403
    assert cliente.post('/api/auth/dispositivos/admin/'+ident+'/aprobar',json={}).status_code==422
    assert aprobar(cliente,ident).status_code==200
    r=entrar(c);assert r.status_code==200 and 'token' not in r.json()
    assert c.get('/api/auth/yo').status_code==200
    assert 'token_hash' not in str(cliente.get('/api/auth/dispositivos/admin').json())


def test_un_movil_y_una_laptop_con_una_sola_sesion(cliente,db):
    preparar_admin(cliente,db);movil=TestClient(app);laptop=TestClient(app)
    registrar_y_entrar(cliente,movil,'MOVIL');assert movil.get('/api/auth/yo').status_code==200
    registrar_y_entrar(cliente,laptop,'LAPTOP')
    assert laptop.get('/api/auth/yo').status_code==200
    assert movil.get('/api/auth/yo').status_code==401
    assert entrar(movil).status_code==200
    assert laptop.get('/api/auth/yo').status_code==401
    op=db.scalar(select(Operador).where(Operador.usuario=='op1'))
    assert len(list(db.scalars(select(Sesion).where(Sesion.operador_id==op.id))))==1


def test_tercer_equipo_no_se_aprueba_sin_reemplazo_explicito(cliente,db):
    preparar_admin(cliente,db);viejo=TestClient(app);nuevo=TestClient(app)
    anterior=registrar_y_entrar(cliente,viejo)
    ident=solicitud(nuevo).json()['equipo']['id']
    r=aprobar(cliente,ident);assert r.status_code==409
    assert viejo.get('/api/auth/yo').status_code==200 and entrar(nuevo).status_code==403
    assert aprobar(cliente,ident,reemplaza=anterior).status_code==200
    assert viejo.get('/api/auth/yo').status_code==401 and entrar(viejo).status_code==403
    assert entrar(nuevo).status_code==200
    db.expire_all();assert db.get(DispositivoUsuario,anterior).estado=='REVOCADO'


def test_copiar_solo_sesion_o_usarla_con_otro_equipo_no_da_acceso(cliente,db):
    preparar_admin(cliente,db);movil=TestClient(app);ident=registrar_y_entrar(cliente,movil)
    token=movil.cookies.get('val_session');ajeno=TestClient(app)
    ajeno.cookies.set('val_session',token)
    assert ajeno.get('/api/auth/yo').status_code==401
    ajeno.cookies.set(cookie(db.get(DispositivoUsuario,ident).operador_id),ident)
    assert ajeno.get('/api/auth/yo').status_code==401
    assert movil.get('/api/auth/yo').status_code==200


def test_revocacion_cierra_acceso_y_login_del_equipo(cliente,db):
    preparar_admin(cliente,db);c=TestClient(app);ident=registrar_y_entrar(cliente,c)
    r=cliente.post('/api/auth/dispositivos/admin/'+ident+'/revocar',json={'motivo':'Equipo extraviado'})
    assert r.status_code==200 and r.json()['sesionesCerradas']==1
    assert c.get('/api/auth/yo').status_code==401 and entrar(c).status_code==403


def test_no_revoca_equipo_actual_admin_ni_aprueba_un_operador(cliente,db):
    preparar_admin(cliente,db);c=TestClient(app);ident=registrar_y_entrar(cliente,c)
    assert c.get('/api/auth/dispositivos/admin').status_code==403
    assert aprobar(c,ident).status_code==403
    propios=cliente.get('/api/auth/dispositivos/admin').json()['equipos']
    admin_id=next(d['id'] for d in propios if d['operadorId']!=db.get(DispositivoUsuario,ident).operador_id)
    assert cliente.post('/api/auth/dispositivos/admin/'+admin_id+'/revocar',json={'motivo':'Prueba de revocacion'}).status_code==409
    assert cliente.get('/api/auth/yo').status_code==200


def test_solicitud_repetida_no_crea_otros_equipos_y_requiere_clave(cliente,db):
    preparar_admin(cliente,db);c=TestClient(app)
    a=solicitud(c);b=solicitud(c)
    assert a.json()['equipo']['id']==b.json()['equipo']['id']
    assert c.post('/api/auth/dispositivos/solicitar',json={'usuario':'op1','pin':'mala','tipo':'MOVIL','nombre':'Otro equipo'}).status_code==401


def test_cookies_seguras_y_no_publica_credencial_del_equipo(cliente,db):
    preparar_admin(cliente,db);c=TestClient(app,base_url='https://testserver')
    r=solicitud(c)
    encabezado=r.headers['set-cookie'].lower()
    assert 'httponly' in encabezado and 'secure' in encabezado and 'samesite=lax' in encabezado
    assert 'token_hash' not in r.text and 'token' not in r.json()['equipo']


def test_desactivar_no_reactiva_sesiones_anteriores(cliente,db):
    preparar_admin(cliente,db);c=TestClient(app);registrar_y_entrar(cliente,c)
    assert cliente.put('/api/auth/dispositivos/admin/politica',json={'activo':False}).status_code==422
    assert cliente.put('/api/auth/dispositivos/admin/politica',json={'activo':False,'motivo':'Mantenimiento programado'}).status_code==200
    assert c.get('/api/auth/yo').status_code==401 and cliente.get('/api/auth/yo').status_code==200


def test_canal_abierto_termina_antes_de_publicar_si_sesion_fue_revocada(cliente,db,monkeypatch):
    import asyncio
    from app.routers import cambios_recepcion as r
    preparar_admin(cliente,db);op=db.scalar(select(Operador).where(Operador.usuario=='sup'))
    class Request:
        async def is_disconnected(self):return False
    monkeypatch.setattr(r,'sesion_vigente',lambda request:False)
    async def probar():
        respuesta=await r.escuchar(Request(),'',db,op)
        return [x async for x in respuesta.body_iterator]
    mensajes=asyncio.run(probar())
    assert mensajes==['retry: 1000\n\n']


def test_google_tambien_exige_equipo_aprobado(cliente,db,monkeypatch):
    from urllib.parse import urlparse,parse_qs
    from app.routers import google_auth
    from app.services import integraciones
    preparar_admin(cliente,db)
    op=db.scalar(select(Operador).where(Operador.usuario=='op1'));op.email='op1@example.test';db.commit()
    integraciones._cifrador(crear=True)
    c={'activo':True,'clientId':'prueba.apps.googleusercontent.com','clientSecret':'ficticio','redirectUri':'https://testserver/api/auth/google/callback'}
    monkeypatch.setattr(google_auth.svc,'oauth',lambda db:c)
    monkeypatch.setattr(google_auth,'identidad',lambda *a:{'sub':'sub-prueba','email':'op1@example.test','email_verified':True})
    movil=TestClient(app,base_url='https://testserver')
    def volver():
        inicio=movil.get('/api/auth/google/iniciar',follow_redirects=False)
        estado=parse_qs(urlparse(inicio.headers['location']).query)['state'][0]
        return movil.get('/api/auth/google/callback',params={'state':estado,'code':'prueba'},follow_redirects=False)
    assert volver().headers['location']=='/app/?google=equipo'
    assert movil.get('/api/auth/yo').status_code==401
    ident=solicitud(movil).json()['equipo']['id'];assert aprobar(cliente,ident).status_code==200
    assert volver().headers['location']=='/app/'
    assert movil.get('/api/auth/yo').status_code==200


def test_relevo_en_un_navegador_no_deja_viva_la_sesion_del_usuario_anterior(cliente,db):
    preparar_admin(cliente,db);c=TestClient(app);ident=registrar_y_entrar(cliente,c)
    anterior=c.cookies.get('val_session')
    r=c.post('/api/auth/dispositivos/solicitar',json={'usuario':'op2','pin':'3333','tipo':'MOVIL','nombre':'Handheld compartido turno'})
    assert aprobar(cliente,r.json()['equipo']['id']).status_code==200
    assert c.post('/api/auth/login',json={'usuario':'op2','pin':'3333'}).status_code==200
    assert c.get('/api/auth/yo').json()['usuario']=='op2'
    db.expire_all();assert db.get(Sesion,anterior) is None
