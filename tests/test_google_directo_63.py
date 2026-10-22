"""APIs simuladas: aislamiento de cuentas, integridad, reintentos y acuses reales de contrato."""
import base64
import hashlib
import json
import time
from email import policy
from email.parser import BytesParser
from urllib.parse import urlparse,parse_qs
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.models import AppConfig,Operador,AppArchivo,AppCopiaDrive,AppAuditoriaGeneral
from app.services import google_cuentas as g, google_drive_api as d, google_gmail_api as gmail
from app.services import integraciones,correo_redactado as correo,app_modelo as m
from tests.test_correo_y_bitacora_61 import configurar,imagen
from tests.test_remitente_responsable import correo as cuenta_correo


def oauth(db):
    integraciones.guardar_oauth(db,{'clientId':'prueba.apps.googleusercontent.com','clientSecret':'secreto-ficticio',
        'redirectUri':'https://testserver/api/auth/google/callback'},'admin')


def token(db,email,scopes):
    g.guardar_tokens(db,email,{'access_token':'access-ficticio','refresh_token':'refresh-ficticio',
        'expires_in':3600,'scope':' '.join(scopes)},email)


def test_conexion_central_drive_no_concede_buzon_ajeno(cliente,db):
    oauth(db);token(db,'drive@example.test',[g.DRIVE]);token(db,'supervisor@example.test',[g.LECTURA,g.ENVIO])
    db.add(AppConfig(clave='google_api',datos={'activo':True,'driveCuenta':'drive@example.test'}));db.commit()
    c=integraciones.google(db,'supervisor@example.test')
    assert c['tipo']=='GOOGLE_API' and c['driveCuenta']=='drive@example.test' and c['supervisor']=='supervisor@example.test'
    assert g.acceso('supervisor@example.test',[g.LECTURA])=='access-ficticio'
    with pytest.raises(RuntimeError,match='GOOGLE_AUTORIZACION'):g.acceso('ajeno@example.test',[g.LECTURA])
    with pytest.raises(RuntimeError,match='GOOGLE_PERMISOS'):g.acceso('supervisor@example.test',[g.DRIVE])
    assert 'access-ficticio' not in str(db.get(AppConfig,g.clave('supervisor@example.test')).datos)


def test_oauth_pkce_cuenta_exacta_y_estado_un_solo_uso(cliente,db,monkeypatch):
    oauth(db);op=db.scalar(select(Operador).where(Operador.usuario=='sup'));op.email='supervisor@example.test';db.commit()
    c=TestClient(app,base_url='https://testserver');c.post('/api/auth/login',json={'usuario':'sup','pin':'1111'})
    inicio=c.get('/api/auth/google/operacion/iniciar',follow_redirects=False)
    assert inicio.status_code==307
    args=parse_qs(urlparse(inicio.headers['location']).query)
    assert args['access_type']==['offline'] and args['code_challenge_method']==['S256']
    assert g.LECTURA in args['scope'][0] and g.ENVIO in args['scope'][0] and g.DRIVE not in args['scope'][0]
    assert c.get('/api/auth/google/operacion/iniciar?tipo=DRIVE').status_code==403
    llamadas=[]
    class Google:
        def __init__(self,**k):pass
        def __enter__(self):return self
        def __exit__(self,*k):pass
        def post(self,url,**k):
            llamadas.append(url)
            return httpx.Response(200,json={'access_token':'token-ficticio','refresh_token':'refresh-ficticio','expires_in':3600,
                'scope':g.LECTURA+' '+g.ENVIO},request=httpx.Request('POST',url))
        def get(self,url,**k):
            return httpx.Response(200,json={'email_verified':True,'email':'supervisor@example.test'},request=httpx.Request('GET',url))
    monkeypatch.setattr('app.routers.google_operacion.httpx.Client',Google)
    state=args['state'][0];cookie=c.cookies.get('iv_google_operacion')
    # Estado erróneo no toca el token remoto ni consume la reserva correcta.
    assert 'error' in c.get('/api/auth/google/callback?state=incorrecto&code=ficticio',follow_redirects=False).headers['location']
    c.cookies.set('iv_google_operacion',cookie)
    r=c.get('/api/auth/google/callback?state='+state+'&code=ficticio',follow_redirects=False)
    assert r.headers['location']=='/app/cuenta.html?googleOperacion=ok'
    db.expire_all();assert g.estado(db,'supervisor@example.test')['gmail']
    c.cookies.set('iv_google_operacion',cookie)
    assert 'error' in c.get('/api/auth/google/callback?state='+state+'&code=ficticio',follow_redirects=False).headers['location']
    assert len(llamadas)==1


def test_drive_reintento_tras_respuesta_perdida_reutiliza_id_y_checksum(cliente,db,monkeypatch):
    remoto={};ids=[];subidas=[];perder=[True]
    monkeypatch.setattr(d,'recepcion',lambda *_:'recepcion12345')
    monkeypatch.setattr(d,'ruta',lambda *_args,**_kw:'destino12345')
    def api(cuenta,servicio,metodo,ruta,**kw):
        if ruta=='files/generateIds':
            ident='reservado'+str(len(ids));ids.append(ident);return httpx.Response(200,json={'ids':[ident]})
        if servicio=='upload':
            bruto=kw['content'];meta=json.loads(bruto.split(b'\r\n\r\n',1)[1].split(b'\r\n--',1)[0]);contenido=bruto.split(b'\r\n\r\n',2)[2].rsplit(b'\r\n--',1)[0]
            remoto[meta['id']]={**meta,'md5Checksum':hashlib.md5(contenido).hexdigest()};subidas.append(meta['id'])
            if perder.pop():raise RuntimeError('GOOGLE_RED: Confirmación perdida')
            return httpx.Response(200,json={'id':meta['id']})
        ident=ruta.split('/')[-1]
        if metodo=='PATCH':remoto[ident].update(kw['json']);return httpx.Response(200,json=remoto[ident])
        if ident not in remoto:raise RuntimeError('GOOGLE_NO_ENCONTRADO: No existe')
        return httpx.Response(200,json=remoto[ident])
    monkeypatch.setattr(g,'peticion',api)
    p={'tipoArchivo':'foto','ruta':['RB63','PRE-INGRESO'],'nombre':'Foto_001.jpg','tipo':'image/jpeg',
        'base64':base64.b64encode(b'imagen-prueba').decode(),'recepcion':'R63'}
    with pytest.raises(RuntimeError,match='GOOGLE_RED'):d.subir('drive@example.test','archivo63:archivo63',p)
    r=d.subir('drive@example.test','archivo63:archivo63',p)
    assert subidas==ids==['reservado0'] and r['fileId']=='reservado0' and r['carpetaRecepcionUrl'].endswith('recepcion12345')
    assert not any('base64' in str(f.datos) for f in db.scalars(select(AppConfig)))


def test_sincronizacion_drive_no_pierde_edicion_ni_permite_sobrescribir_otro_borrador(cliente,db):
    c,ruta=configurar(cliente,db);a=imagen(cliente,c,'PRERECEPCION','blue');b=imagen(cliente,c,'PRERECEPCION','red')
    v=cliente.get(ruta).json();db.rollback();archivo=db.get(AppArchivo,a);archivo.drive_id='drive-foto-63';archivo.drive_url='https://drive.google.com/file/d/drive-foto-63/view'
    j=db.get(AppCopiaDrive,a);j.estado='COPIADA';db.commit()
    nueva=cliente.get(ruta).json()
    assert nueva['version']!=v['version'] and nueva['versionEdicion']==v['versionEdicion']
    datos={'version':v['version'],'versionEdicion':v['versionEdicion'],'campos':{**v['campos'],'notas':'Mi texto se conserva'},
        'presentacion':{'mostrarTotales':False,'fotosModo':'ELEGIDAS','fotosIds':[a]}}
    r=cliente.put(ruta,json=datos);assert r.status_code==200,r.text
    assert r.json()['fotosSeleccionadas']==[a] and 'Mi texto se conserva' in r.json()['html'] and b not in r.json()['fotosSeleccionadas']
    assert cliente.put(ruta,json=datos).status_code==409


def test_cambios_en_cantidades_siguen_bloqueando_borrador_antiguo(cliente,db):
    c,ruta=configurar(cliente,db);v=cliente.get(ruta).json()
    m.registrar_conteo(db,c,'op1',{'id':'otro-conteo-63','sku':'SKU1','cantidad':1,'pallet':'E02'})
    r=cliente.put(ruta,json={'version':v['version'],'versionEdicion':v['versionEdicion'],'campos':v['campos']})
    assert r.status_code==409


def test_log_solo_admin_y_estado_fotos_disponible_al_operario(cliente,db):
    from app.services.procesos import registrar
    c,_=configurar(cliente,db);registrar(db,'FOTO','ERROR','ficticio','op1',recepcion=c,codigo='GOOGLE_PERMISOS',secreto='nunca-guardar');db.commit()
    assert cliente.get('/api/operacion/procesos').status_code==403
    op=db.scalar(select(Operador).where(Operador.usuario=='sup'));op.rol=__import__('app.models',fromlist=['Rol']).Rol.ADMIN;db.commit()
    r=cliente.get('/api/operacion/procesos?recepcion='+c).json()
    assert r['eventos'][0]['codigo']=='GOOGLE_PERMISOS' and 'nunca-guardar' not in str(r)
    operario=TestClient(app);operario.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    estado=operario.get('/api/operacion/recepciones/'+c+'/drive')
    assert estado.status_code==200 and 'destino' not in estado.json()


def test_mime_contiene_imagen_embebida_enlace_real_varios_adjuntos_y_hilo(monkeypatch):
    monkeypatch.setattr(gmail,'mensaje',lambda *_: {'id':'abcdef123456','threadId':'abcdef654321','payload':{'headers':[
        {'name':'Subject','value':'Packing RB63'},{'name':'Message-ID','value':'<original@example.test>'}]}})
    monkeypatch.setattr(d,'miniatura',lambda *_:b'jpeg-ficticio')
    monkeypatch.setattr(d,'contenido',lambda *_:b'excel-ficticio')
    p={'codigo':'R63','destinatarios':'ejecutivo@example.test','correoFinal':{'asunto':'Re: Packing RB63','html':'<p>Revisión</p><img data-archivo="foto63" src="https://drive.google.com/thumbnail?id=file63">',
        'respuestaGmail':{'cuenta':'sup@example.test','id':'abcdef123456','threadId':'abcdef654321'}},
        'archivos':[{'fileId':'file63','tipoArchivo':'foto','nombre':'foto.jpg'},
            {'fileId':'excel63a','tipoArchivo':'informe','nombre':'Validacion.xlsx'},{'fileId':'excel63b','tipoArchivo':'informe','nombre':'Auditoria.xlsx'}],
        'manifiesto':[{'archivoId':'foto63','fileId':'file63'}]}
    m,original,mid=gmail.preparar_mime('sup@example.test','drive@example.test','envio63',p)
    mensaje=BytesParser(policy=policy.default).parsebytes(m.as_bytes())
    assert mensaje['In-Reply-To']=='<original@example.test>' and original['threadId']=='abcdef654321'
    html=mensaje.get_body(preferencelist=('html',)).get_content()
    assert 'cid:foto_foto63' in html and 'https://drive.google.com/file/d/file63/view' in html
    assert sorted(a.get_filename() for a in mensaje.iter_attachments())==['Auditoria.xlsx','Validacion.xlsx']
    assert any(a.get_content_type()=='image/jpeg' and a['Content-ID']=='<foto_foto63>' for a in mensaje.walk())


def test_envio_sin_confirmacion_no_se_repite(monkeypatch,cliente,db):
    from app.services.entregas import RevisionEntrega
    monkeypatch.setattr(gmail,'perfil',lambda *_:{'emailAddress':'sup@example.test'})
    monkeypatch.setattr(d,'recepcion',lambda *_:'recepcion63')
    monkeypatch.setattr(gmail,'preparar_mime',lambda *_:(__import__('email.message',fromlist=['EmailMessage']).EmailMessage(),None,'<prueba@example.test>'))
    llamadas=[]
    def perder(*a,**kw):llamadas.append(a);raise RuntimeError('GOOGLE_RED: Sin acuse')
    monkeypatch.setattr(g,'peticion',perder)
    p={'destinatarios':'ejecutivo@example.test'}
    with pytest.raises(RevisionEntrega):gmail.finalizar('sup@example.test','drive@example.test','envio63',p)
    with pytest.raises(RevisionEntrega):gmail.finalizar('sup@example.test','drive@example.test','envio63',p)
    assert len(llamadas)==1


def test_varios_informes_nombres_editables_y_rechazo_de_adjuntos_ajenos(cliente,db,cuenta_correo):
    from uuid import uuid4
    from app.models import AppInforme,AppEntrega
    from app.services import archivos,informes
    from tests.test_flujo_final_62 import documento
    c,_=cuenta_correo;fid=documento(cliente,c);db.rollback();f=db.get(AppInforme,fid)
    primero=f.datos['archivos'][0];a=db.get(AppArchivo,primero['id'])
    from openpyxl import Workbook
    import io
    libro=Workbook();libro.active.append(['Registro','Auditoría']);salida=io.BytesIO();libro.save(salida)
    segundo=archivos.guardar(db,c,'informe',{'nombre':'Auditoria.xlsx','base64':base64.b64encode(salida.getvalue()).decode()},'personal@example.test')
    f2=AppInforme(id=uuid4().hex,recepcion=c,numero=f.numero+1,clave=uuid4().hex,usuario=f.usuario,
        tipo='DESCARGA',estado='GENERADO',huella=f.huella,datos={**f.datos,'formato':'auditable','archivos':[{**primero,'id':segundo.id,'nombre':segundo.nombre}]})
    db.add(f2);db.commit()
    ruta='/api/operacion/recepciones/'+c+'/correo';v=cliente.get(ruta).json()
    elegidos=[{'id':a.id,'nombre':'Validacion_revisada.xlsx'},{'id':segundo.id,'nombre':'Bitacora_final.xlsx'}]
    datos={'version':v['version'],'campos':{**v['campos'],'destinatarios':'ejecutivo@example.test'},'adjuntos':elegidos}
    r=cliente.put(ruta,json={**datos,'adjuntos':[{'id':'ajeno','nombre':'Ajeno.xlsx'}]});assert r.status_code==409
    r=cliente.put(ruta,json={**datos,'adjuntos':[{'id':a.id,'nombre':'../../archivo.xlsx'}]});assert r.status_code==422
    r=cliente.put(ruta,json=datos);assert r.status_code==200,r.text
    v=r.json();assert len(v['archivos'])==2 and 'Validacion_revisada.xlsx' in v['html']
    e=cliente.post(ruta+'/enviar',json={'confirmar':True,'version':v['version'],'remitenteConfirmado':'personal@example.test'})
    assert e.status_code==201,e.text
    db.rollback();db.expire_all();envio=db.get(AppEntrega,e.json()['id'])
    assert set(envio.datos['informes'])=={a.id,segundo.id}
    assert envio.datos['nombresAdjuntos'][a.id]=='Validacion_revisada.xlsx'
    assert db.get(AppArchivo,a.id).nombre!='Validacion_revisada.xlsx'


def test_rechazo_explicito_gmail_permita_recuperar_sin_duplicar(monkeypatch,cliente,db):
    monkeypatch.setattr(gmail,'perfil',lambda *_:{'emailAddress':'sup@example.test'})
    monkeypatch.setattr(d,'recepcion',lambda *_:'recepcion63')
    from email.message import EmailMessage
    monkeypatch.setattr(gmail,'preparar_mime',lambda *_:(EmailMessage(),None,'<prueba@example.test>'))
    llamadas=[]
    def google(*a,**kw):
        llamadas.append(a)
        if len(llamadas)==1:raise RuntimeError('GOOGLE_PERMISOS: Google no confirmó la operación (HTTP 403).')
        return httpx.Response(200,json={'id':'abcdef123456','threadId':'abcdef654321'})
    monkeypatch.setattr(g,'peticion',google)
    p={'destinatarios':'ejecutivo@example.test'}
    with pytest.raises(RuntimeError,match='GOOGLE_PERMISOS'):gmail.finalizar('sup@example.test','drive@example.test','rechazo63',p)
    r=gmail.finalizar('sup@example.test','drive@example.test','rechazo63',p)
    assert r['gmail']['mensajeId']=='abcdef123456'
    assert gmail.finalizar('sup@example.test','drive@example.test','rechazo63',p)==r
    assert len(llamadas)==2


def test_preparar_carpetas_y_enlaces_usa_drive_central_sin_autorizar_gmail(cliente,db,monkeypatch):
    c,ruta=configurar(cliente,db);oauth(db);token(db,'drive@example.test',[g.DRIVE])
    db.add(AppConfig(clave='google_api',datos={'activo':True,'driveCuenta':'drive@example.test','carpetaRaiz':'raiz-operativa63'}));db.commit()
    cuentas=[]
    def ficha(cuenta,ident):cuentas.append(cuenta);return {'id':ident,'name':c,'mimeType':d.CARPETA}
    monkeypatch.setattr(d,'ficha',ficha)
    monkeypatch.setattr(d,'preparar',lambda cuenta,p:{'exito':True,'carpeta':'https://drive.google.com/drive/folders/recepcion-operativa63'})
    monkeypatch.setattr(d,'ruta',lambda cuenta,raiz,r,crear=True:raiz if not r else 'carpeta-'+hashlib.sha256(str(r).encode()).hexdigest()[:15])
    r=cliente.post('/api/operacion/recepciones/'+c+'/drive/preparar',json={});assert r.status_code==200,r.text
    r=cliente.post(ruta+'/enlaces-drive',json={});assert r.status_code==200,r.text
    assert cuentas and set(cuentas)=={'drive@example.test'}
    assert cliente.get(ruta).json()['html'].count('Carpeta de la recepción')==1
    db.rollback();f=db.get(AppConfig,g.clave('drive@example.test'));f.datos={**f.datos,'estado':'REAUTORIZAR'};db.commit()
    assert integraciones.google(db,'sup@example.test')['tipo']=='GOOGLE_API'  # No cambia de cuenta al fallar el permiso.
