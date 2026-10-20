"""Correo compacto: contenedores reales, ámbito correcto y caché acotada."""
import pytest
from app.models import AppConfig, AppEvento
from app.services import enlaces_correo as ec, entregas, operacion, app_modelo as m
from tests.test_agrupacion_embarques_53 import multi, plan
from tests.test_remitente_responsable import correo
from tests.test_correo_archivos_embarque_55 import guardar_plan

RAIZ='https://drive.google.com/drive/folders/recepcion59'

def confirmar(db,c):
    operacion.auditoria(db,c,'sup','CARPETA_DRIVE_VERIFICADA',{'carpeta':RAIZ});db.commit()

def puente(accion,clave,datos,conexion):
    assert accion=='carpetasCorreo'
    return {'exito':True,'carpeta':RAIZ,'carpetas':[{'ruta':r,'url':RAIZ if not r else 'https://drive.google.com/drive/folders/carpeta59-'+ '-'.join(r)} for r in datos['rutas']]}

def enlaces(h):
    from html.parser import HTMLParser
    class L(HTMLParser):
        def __init__(self):super().__init__();self.salida=[]
        def handle_starttag(self,t,a):
            if t=='a':self.salida.append(dict(a)['href'])
    l=L();l.feed(h);return l.salida


def test_correo_por_embarque_solo_raiz_y_tres_categorias(cliente,db,multi,monkeypatch):
    p=guardar_plan(cliente,multi);confirmar(db,multi)
    monkeypatch.setattr(entregas,'llamar_conexion',puente)
    url='/api/operacion/recepciones/'+multi
    assert cliente.post(url+'/correo/enlaces-drive',json={}).status_code==200
    for g in p['grupos']:
        v=cliente.get(url+'/correo',params={'origen':g['id']}).json();h=v['html'];ls=enlaces(h)
        assert len(ls)==4 and len(set(ls))==4
        assert all('EMBARQUES-'+g['nombre'] in u for u in ls)
        assert 'EMB-B' not in h if g['nombre']=='EMB-A' else 'EMB-A' not in h
        assert all(x in h for x in ('Carpeta del embarque '+g['nombre'],'Sobrantes y adicionales','Faltantes','PNC'))
        assert 'Consultar carpeta de evidencias' not in h
        assert all(u in v['texto'] for u in ls)


def test_una_lista_varios_embarques_o_consolidado_no_mezcla_etiquetas(cliente,db,multi,monkeypatch):
    confirmar(db,multi);monkeypatch.setattr(entregas,'llamar_conexion',puente)
    assert cliente.post('/api/operacion/recepciones/'+multi+'/correo/enlaces-drive',json={}).status_code==200
    v=cliente.get('/api/operacion/recepciones/'+multi+'/correo',params={'origen':'PRINCIPAL'}).json()
    assert 'Carpeta de la recepción '+multi in v['html']
    assert 'EMB-A · PNC' in v['html'] and 'EMB-B · PNC' in v['html']
    ls=enlaces(v['html']);assert len(ls)==10 and len(set(ls))==10


def test_sin_indice_antiguo_solo_raiz_y_sin_inventar_url_de_categoria(cliente,db,multi):
    confirmar(db,multi)
    v=cliente.get('/api/operacion/recepciones/'+multi+'/correo',params={'origen':'PRINCIPAL'}).json()
    assert enlaces(v['html'])==[RAIZ]
    assert 'Consultar carpeta de evidencias' not in v['html']


def test_carpeta_inexistente_no_muestra_link_y_actualizacion_no_crece_mysql(cliente,db,multi,monkeypatch):
    confirmar(db,multi);llamadas=[]
    def google(*a):
        llamadas.append(a);return {'exito':True,'carpeta':RAIZ,'carpetas':[{'ruta':[],'url':RAIZ}]}
    monkeypatch.setattr(entregas,'llamar_conexion',google)
    q='/api/operacion/recepciones/'+multi+'/correo/enlaces-drive'
    antes=db.query(AppEvento).count()
    for _ in range(3):assert cliente.post(q,json={}).status_code==200
    assert len(llamadas)==1
    db.rollback();db.expire_all()
    assert db.query(AppConfig).filter_by(clave=ec.clave(multi)).count()==1
    assert db.query(AppEvento).count()==antes
    assert enlaces(cliente.get(q.rsplit('/enlaces-drive',1)[0]).json()['html'])==[RAIZ]


@pytest.mark.parametrize('cambio',[
    {'carpeta':'https://drive.google.com/drive/folders/otra-recepcion'},
    {'carpetas':[{'ruta':['EMBARQUES','AJENO'],'url':'https://drive.google.com/drive/folders/ajeno'}]},
    {'carpetas':[{'ruta':[],'url':'javascript:alert(1)'}]},
    {'carpetas':[{'ruta':['PNC'],'url':'https://drive.google.com/file/d/foto59/view'}]},
])
def test_respuesta_incorrecta_no_reemplaza_indice(cliente,db,multi,monkeypatch,cambio):
    confirmar(db,multi);monkeypatch.setattr(entregas,'llamar_conexion',lambda *a:{'exito':True,'carpeta':RAIZ,'carpetas':[],**cambio})
    assert cliente.post('/api/operacion/recepciones/'+multi+'/correo/enlaces-drive',json={}).status_code==502
    db.rollback();assert db.get(AppConfig,ec.clave(multi)) is None


def test_operario_no_actualiza_enlaces_y_sin_raiz_no_contacta_google(cliente,db,multi,monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setattr(entregas,'llamar_conexion',lambda *a:pytest.fail('Sin raíz confirmada'))
    q='/api/operacion/recepciones/'+multi+'/correo/enlaces-drive'
    assert cliente.post(q,json={}).status_code==409
    op=TestClient(app);op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    assert op.post(q,json={}).status_code==403


def test_indice_no_se_reutiliza_si_cambia_raiz(cliente,db,multi):
    confirmar(db,multi)
    f=AppConfig(clave=ec.clave(multi),datos={'raiz':RAIZ,'carpetas':[{'ruta':['EMBARQUES','EMB-A'],'url':'https://drive.google.com/drive/folders/embarque-viejo'}]});db.add(f);db.commit()
    operacion.auditoria(db,multi,'sup','CARPETA_DRIVE_VERIFICADA',{'carpeta':'https://drive.google.com/drive/folders/recepcion-nueva59'});db.commit()
    h=cliente.get('/api/operacion/recepciones/'+multi+'/correo',params={'origen':'PRINCIPAL'}).json()['html']
    assert 'embarque-viejo' not in h and 'recepcion-nueva59' in h


def test_packing_parcial_no_incluye_categorias_globales_ni_otros_embarques(cliente,db,multi,monkeypatch):
    m.guardar_packing_list(db,multi,{'lineas':[{'linea':1,'sku':'OTRO59','cantidad':1,'embarque':'EMB-C'}],
        'porSku':{'OTRO59':1},'unidades':1},'OTRA')
    confirmar(db,multi);monkeypatch.setattr(entregas,'llamar_conexion',puente)
    q='/api/operacion/recepciones/'+multi+'/correo'
    assert cliente.post(q+'/enlaces-drive',json={}).status_code==200
    v=cliente.get(q,params={'origen':'PRINCIPAL'}).json();ls=enlaces(v['html'])
    assert len(ls)==7
    assert all('EMB-C' not in u and 'carpeta59-PNC' not in u and 'carpeta59-FALTANTE' not in u and 'carpeta59-SOBRANTE' not in u for u in ls)
