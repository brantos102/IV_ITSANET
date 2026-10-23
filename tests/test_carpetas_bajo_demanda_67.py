"""Consultar o registrar recepciones no materializa directorios sin archivos."""
from app.models import AppConfig,AppArchivo,AppEvento
from app.services import google_drive_api as drive,entregas,carpetas_recepcion as carpetas
from tests.test_fotos_embarques_54 import preparar
from tests.test_correo_y_bitacora_61 import configurar


def test_preparar_drive_solo_busca_sin_crear_categorias(monkeypatch):
    llamadas=[]
    def buscar(cuenta,padre,nombre):
        llamadas.append((padre,nombre))
        return {'VENTURA':'cliente67','VW':'marca67','R67':'recepcion67'}.get(nombre)
    monkeypatch.setattr(drive,'buscar_carpeta',buscar)
    monkeypatch.setattr(drive,'carpeta',lambda *_: (_ for _ in ()).throw(AssertionError('No crear carpetas')))
    p={'carpetaRaiz':'matriz67','cliente':'VENTURA','marca':'VW','recepcion':'R67','embarques':['RB-A','RB-B']}
    assert drive.preparar('drive@example.test',p)['carpeta'].endswith('/recepcion67')
    assert [n for _,n in llamadas]==['VENTURA','VW','R67']
    assert drive.preparar('drive@example.test',{**p,'recepcion':'NO_EXISTE'})=={'exito':True,'carpeta':'','sinCarpeta':True}


def test_al_crear_y_agregar_embarques_no_se_llama_google(cliente,db,monkeypatch):
    monkeypatch.setattr(entregas,'llamar',lambda *_: (_ for _ in ()).throw(AssertionError('No llamar Google')))
    codigo=preparar(cliente,db)
    assert not carpetas.procesar_uno(db)
    assert db.get(AppConfig,carpetas.clave(codigo)).datos['estado']=='BAJO_DEMANDA'
    assert not db.query(AppArchivo).count()


def test_puente_anterior_no_recibe_orden_de_crear_carpetas(cliente,db,monkeypatch):
    codigo,_=configurar(cliente,db);llamadas=[]
    db.add(AppConfig(clave='google_api',datos={'activo':True,'driveCuenta':'drive@example.test'}));db.commit()
    def google(accion,clave,datos):
        llamadas.append(accion)
        assert accion=='estado'
        return {'remitente':datos['usuario'],'carpetaId':datos.get('carpetaRaiz',''),'capacidades':['carpetasRecepcion62','prepararCarpeta']}
    monkeypatch.setattr(entregas,'llamar',google)
    r=cliente.post('/api/operacion/recepciones/'+codigo+'/drive/preparar',json={})
    assert r.status_code==200,r.text
    assert r.json()['carpeta']=='' and r.json()['bajoDemanda']
    assert 'primera foto o informe' in r.json()['mensaje'] and llamadas==['estado']
    assert not db.query(AppEvento).filter(AppEvento.motivo=='CARPETA_DRIVE_VERIFICADA').count()


def test_preparador_nuevo_sin_carpeta_no_inventa_enlace(cliente,db,monkeypatch):
    codigo,_=configurar(cliente,db);llamadas=[]
    db.add(AppConfig(clave='google_api',datos={'activo':True,'driveCuenta':'drive@example.test'}));db.commit()
    def google(accion,clave,datos):
        llamadas.append(accion)
        if accion=='estado':return {'remitente':datos['usuario'],'carpetaId':datos.get('carpetaRaiz',''),'capacidades':['carpetasBajoDemanda67']}
        assert accion=='prepararCarpeta'
        return {'exito':True,'carpeta':'','sinCarpeta':True}
    monkeypatch.setattr(entregas,'llamar',google)
    r=cliente.post('/api/operacion/recepciones/'+codigo+'/drive/preparar',json={})
    assert r.status_code==200,r.text
    assert llamadas==['estado','prepararCarpeta'] and r.json()['carpeta']==''
    assert not cliente.get('/api/operacion/recepciones/'+codigo+'/drive').json()['carpetas']


def test_primera_copia_fija_carpeta_madre_ante_cambio_de_marca(cliente,db):
    from app.models import AppCopiaDrive,AppIngreso
    from app.services.operacion import destino_drive
    from tests.test_correo_y_bitacora_61 import imagen
    codigo,_=configurar(cliente,db);ident=imagen(cliente,codigo,'PRERECEPCION','red')
    db.rollback();j=db.get(AppCopiaDrive,ident);j.estado='COPIADA'
    j.datos={**j.datos,'carpetaRecepcionUrl':'https://drive.google.com/drive/folders/madre-fija67'}
    db.add(AppIngreso(recepcion=codigo,datos={'marca':'OTRA-MARCA'}));db.commit()
    assert destino_drive(db,codigo)['carpetaRecepcionId']=='madre-fija67'
    carpetas.encolar(db,codigo);db.commit()
    assert db.get(AppConfig,carpetas.clave(codigo)).datos['carpeta'].endswith('/madre-fija67')


def test_enlace_historico_de_puente_antiguo_no_se_audita_como_verificacion_nueva(cliente,db,monkeypatch):
    from app.services.operacion import auditoria
    codigo,_=configurar(cliente,db)
    db.add(AppConfig(clave='google_api',datos={'activo':True,'driveCuenta':'drive@example.test'}))
    auditoria(db,codigo,'sup','CARPETA_DRIVE_VERIFICADA',{'carpeta':'https://drive.google.com/drive/folders/historica67'});db.commit()
    monkeypatch.setattr(entregas,'llamar',lambda accion,clave,p:{'remitente':p['usuario'],'carpetaId':p.get('carpetaRaiz',''),'capacidades':['prepararCarpeta']})
    antes=db.query(AppEvento).filter(AppEvento.motivo=='CARPETA_DRIVE_VERIFICADA').count()
    r=cliente.post('/api/operacion/recepciones/'+codigo+'/drive/preparar',json={})
    assert r.status_code==200,r.text
    assert r.json()['carpeta'].endswith('/historica67') and not r.json()['verificada']
    assert db.query(AppEvento).filter(AppEvento.motivo=='CARPETA_DRIVE_VERIFICADA').count()==antes
