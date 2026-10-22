"""Secuencia física, reintentos, dos supervisores y evidencia final auditable."""
import base64
import io
from concurrent.futures import ThreadPoolExecutor
import threading
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from openpyxl import Workbook
from app.main import app
from app.models import AppImpresion, AppCopiaDrive, AppArchivo, AppInforme
from app.services import app_modelo as m, archivos
from tests.test_operacion_desarrollo import admin  # noqa: F401
from tests.test_archivos_locales import PNG


def crear(cliente, codigo='BULTOS', cantidad=3):
    r=cliente.post('/api/app/recepciones',json={'codigo':codigo,'cliente':'VENTURA/VW','bultos':cantidad})
    assert r.status_code==201,r.text
    return '/api/impresion/recepciones/'+codigo+'/bultos'


def solicitud(cliente,ruta,**extra):
    estado=cliente.get(ruta).json()
    return {'clave':uuid4().hex,'version':estado['version'],'cantidadAnterior':estado['total'],
        'total':estado['total'],'literal':'P','formato':'100x150','destino':'ZPL',**extra}


@pytest.mark.parametrize('formato,ll',[('100x150',1200),('100x50',400)])
def test_una_etiqueta_por_bulto_y_reintento_no_duplica(cliente,db,formato,ll):
    ruta=crear(cliente)
    cuerpo=solicitud(cliente,ruta,formato=formato)
    r=cliente.post(ruta,json=cuerpo);assert r.status_code==201,r.text
    lote=r.json();assert [e['rotulo'] for e in lote['etiquetas']]==['P01','P02','P03']
    assert [e['numero'] for e in lote['etiquetas']]==[1,2,3]
    assert [e['serie'] for e in lote['etiquetas']]==['P01','P02','P03']
    assert all('^FD'+e['rotulo']+'^FS' in lote['zpl'] for e in lote['etiquetas'])
    assert all(e['total']==3 for e in lote['etiquetas'])
    assert lote['zpl'].count('^XA')==lote['zpl'].count('^PQ1')==3
    assert lote['zpl'].count(f'^LL{ll}')==3 and '^PQ3' not in lote['zpl']
    assert cliente.post(ruta,json=cuerpo).json()==lote
    assert cliente.post(ruta,json={**cuerpo,'literal':'B'}).status_code==409
    assert cliente.get('/api/app/recepciones/BULTOS/skus').json()==[]
    db.rollback();assert len(list(db.scalars(select(AppImpresion))))==1


def test_ampliar_total_conserva_identidad_y_no_elimina_bultos_etiquetados(cliente):
    ruta=crear(cliente)
    assert cliente.put('/api/operacion/recepciones/BULTOS/ingreso',json={'protocolo':'SIN_FOTOS','marca':'ISUZU','embarque':'RB-ORIGINAL'}).status_code==200
    lote=cliente.post(ruta,json=solicitud(cliente,ruta)).json()
    nueva=cliente.post(ruta,json=solicitud(cliente,ruta,total=5));assert nueva.status_code==201,nueva.text
    nueva=nueva.json();assert nueva['lote']==2
    assert [e['unidadId'] for e in nueva['etiquetas'][:3]]==[e['unidadId'] for e in lote['etiquetas']]
    assert [e['numero'] for e in nueva['etiquetas']]==[1,2,3,4,5]
    assert all(e['total']==5 for e in nueva['etiquetas'])
    assert cliente.post(ruta,json=solicitud(cliente,ruta,total=4)).status_code==409
    assert cliente.post('/api/operacion/recepciones/BULTOS/bultos',json={'cantidad':4,'cantidadAnterior':5}).status_code==409
    assert cliente.get('/api/app/recepciones/BULTOS').json()['bultos']==5
    ingreso=cliente.get('/api/operacion/recepciones/BULTOS/ingreso').json()
    assert ingreso['protocolo']=='SIN_FOTOS' and ingreso['marca']=='ISUZU' and ingreso['embarque']=='RB-ORIGINAL'


@pytest.mark.parametrize('cambio',[{'total':-1},{'total':0},{'total':True},{'total':2.5},{'total':1001},
    {'literal':'^XA'},{'literal':''},{'formato':'otro'},{'destino':'OTRO'}])
def test_datos_invalidos_no_crean_unidades_ni_lotes(cliente,db,cambio):
    ruta=crear(cliente);r=cliente.post(ruta,json=solicitud(cliente,ruta,**cambio));assert r.status_code==422,r.text
    assert cliente.get('/api/operacion/recepciones/BULTOS/ingreso').json()['unidades']==[]
    db.rollback();assert not list(db.scalars(select(AppImpresion)))


def test_dos_supervisores_y_permiso_de_operador(cliente,admin):
    ruta=crear(cliente);cuerpo=solicitud(cliente,ruta)
    operador=TestClient(app);operador.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    assert operador.get(ruta).status_code==403
    assert operador.post(ruta,json=cuerpo).status_code==403
    barrera=threading.Barrier(2)
    def enviar(c):
        barrera.wait(timeout=5)
        return c.post(ruta,json={**cuerpo,'clave':uuid4().hex})
    with ThreadPoolExecutor(max_workers=2) as ex:
        respuestas=list(ex.map(enviar,[cliente,admin]))
    assert sorted(r.status_code for r in respuestas)==[201,409]
    assert len(cliente.get(ruta).json()['anteriores'])==1


def test_bultos_via_puente_no_repite_la_reserva_y_respeta_maximo(admin,cliente):
    config=admin.get('/api/operacion/config').json()
    config['impresoras']=[{'id':'MESA','nombre':'Mesa','host':'192.168.1.20','equipo':'PC','activo':True}]
    config['maxCopias']=4
    assert admin.put('/api/operacion/config',json=config).status_code==200
    token=admin.post('/api/impresion/estaciones/MESA/token').json()['token']
    ruta=crear(cliente)
    assert cliente.post(ruta,json=solicitud(cliente,ruta,total=5)).status_code==422
    cuerpo=solicitud(cliente,ruta,destino='ESTACION',estacion='MESA')
    r=cliente.post(ruta,json=cuerpo);assert r.status_code==201,r.text
    headers={'Authorization':'Bearer '+token}
    j=cliente.post('/api/impresion/agente/MESA/siguiente',headers=headers,json={'equipo':'PC'}).json()['trabajo']
    assert j['id']==r.json()['id'] and j['zpl'].count('^PQ1')==3
    assert cliente.post('/api/impresion/agente/MESA/siguiente',headers=headers,json={'equipo':'PC'}).json()['trabajo'] is None
    assert cliente.post(ruta,json=cuerpo).json()['id']==j['id']


def test_estado_final_despues_cierre_sin_alterar_conteos_ni_informes(cliente,db,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path);crear(cliente)
    m.guardar_packing_list(db,'BULTOS',{'lineas':[{'linea':1,'sku':'S','cantidad':2}],'porSku':{'S':2},'unidades':2},'PL')
    assert cliente.post('/api/app/recepciones/BULTOS/conteos',json={'sku':'S','cantidad':2,'pallet':'P1','idempotencyKey':uuid4().hex}).status_code==200
    reserva=cliente.post('/api/operacion/recepciones/BULTOS/informes',json={'clave':uuid4().hex,'tipo':'DESCARGA','ultimoVisto':None}).json()
    libro=Workbook();libro.active.append(['SKU','CONTADO']);libro.active.append(['S',2]);salida=io.BytesIO();libro.save(salida)
    archivado=cliente.put('/api/operacion/recepciones/BULTOS/informes/'+reserva['id'],json={'adjuntos':[
        {'nombre':'informe'+reserva['sufijo']+'.xlsx','base64':base64.b64encode(salida.getvalue()).decode()}]})
    assert archivado.status_code==200,archivado.text
    informes=cliente.get('/api/operacion/recepciones/BULTOS/informes').json()
    db.rollback();m.cerrar_recepcion(db,'BULTOS','sup')
    antes=cliente.get('/api/app/recepciones/BULTOS').json()
    skus=cliente.get('/api/app/recepciones/BULTOS/skus').json()
    datos={'base64':base64.b64encode(PNG).decode(),'tipoEvidencia':'ESTADO_FINAL','categoria':'RECEPCION','protocolo':'GENERAL'}
    operador=TestClient(app);operador.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    ruta='/api/app/recepciones/BULTOS/archivos/foto'
    assert operador.post(ruta,json=datos).status_code==403
    assert cliente.post(ruta,json={**datos,'tipoEvidencia':'ITEM_NOVEDAD'}).status_code==409
    assert cliente.post(ruta,json={**datos,'sku':'S'}).status_code==409
    r=cliente.post(ruta,json=datos);assert r.status_code==201,r.text
    assert cliente.post(ruta,json=datos).json()['id']==r.json()['id']
    assert cliente.get('/api/app/recepciones/BULTOS').json()==antes
    assert cliente.get('/api/app/recepciones/BULTOS/skus').json()==skus
    fotos=cliente.get('/api/app/recepciones/BULTOS/imagenes?tipoEvidencia=ESTADO_FINAL').json()
    assert fotos['total']==1 and fotos['archivos'][0]['evidencias'][0]['tipo']=='ESTADO_FINAL'
    assert cliente.get('/api/app/recepciones/BULTOS/imagenes?tipoEvidencia=EXTERIOR_BULTO').json()['total']==0
    eventos=cliente.get('/api/app/recepciones/BULTOS/eventos').json()
    assert len([e for e in eventos if e['motivo']=='EVIDENCIA_POSTCIERRE' and e['operadorEmail']=='sup'])==1
    assert cliente.get('/api/operacion/recepciones/BULTOS/informes').json()==informes
    db.rollback();assert len(list(db.scalars(select(AppInforme))))==1
    j=db.get(AppCopiaDrive,r.json()['id'])
    assert j.estado=='PENDIENTE' and j.datos['ruta']==['FOTOS-FINALES']
    assert db.get(AppArchivo,r.json()['id']).bytes==len(PNG)
