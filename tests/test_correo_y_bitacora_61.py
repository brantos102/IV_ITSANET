"""Correo en contexto, redacción operativa y conteos sin ubicación impuesta."""
import base64
import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.models import AppArchivo,AppConfig,AppEvento,AppRecepcion,AppAuditoriaGeneral
from app.services import app_modelo as m,correo_redactado as correo,ajustes
from tests.test_mejoras_operativas import preparar


def imagen(cliente,c,tipo,color,sku='',categoria='RECEPCION'):
    b=io.BytesIO();Image.new('RGB',(16,12),color).save(b,format='PNG')
    r=cliente.post(f'/api/app/recepciones/{c}/archivos/foto',json={'tipo':'image/png','base64':base64.b64encode(b.getvalue()).decode(),'tipoEvidencia':tipo,'categoria':categoria,'sku':sku})
    assert r.status_code==201,r.text
    return r.json()['id']


def configurar(cliente,db):
    c=preparar(db)
    m.registrar_conteo(db,c,'op1',{'id':'conteo-prueba-61','sku':'SKU1','cantidad':4,'pallet':'E01','posicionReal':'A-01','incidencias':[{'tipo':'MAL_ESTADO','cantidad':1,'pallet':'E01'}]})
    return c,f'/api/operacion/recepciones/{c}/correo'


def test_prerecepcion_ordenada_antes_de_observaciones_y_novedades_con_fotos_locales(cliente,db):
    c,ruta=configurar(cliente,db)
    a=imagen(cliente,c,'PRERECEPCION','red');b=imagen(cliente,c,'PRERECEPCION','blue');n=imagen(cliente,c,'ITEM_NOVEDAD','green','SKU1','PNC')
    v=cliente.get(ruta).json()
    r=cliente.put(ruta,json={'version':v['version'],'campos':{**v['campos'],'notas':'OBSERVACION DE PRUEBA\nCajas con daño visible'},'presentacion':{'mostrarTotales':False,'fotosModo':'ELEGIDAS','fotosIds':[n,b,a]}})
    assert r.status_code==200,r.text
    html=r.json()['html']
    assert html.index('data-archivo="'+b+'"')<html.index('data-archivo="'+a+'"')<html.index('OBSERVACION DE PRUEBA')<html.index('Faltantes')<html.index('data-archivo="'+n+'"')
    assert html.count('data-archivo="'+a+'"')==1
    assert '/api/app/archivos/'+b in html and 'Copia a Drive pendiente' in html
    assert r.json()['imagenesDrive']==[]
    db.rollback();guardado=db.get(AppConfig,correo.clave_config(c))
    assert 'base64' not in str(guardado.datos) and not any(k in guardado.datos for k in ('html','imagenes'))


def test_operario_redacta_y_elige_fotos_sin_cambiar_destinatarios_ni_enviar(cliente,db):
    c,ruta=configurar(cliente,db);a=imagen(cliente,c,'PRERECEPCION','yellow')
    op=TestClient(app);assert op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'}).status_code==200
    v=op.get(ruta).json();assert v['soloRedaccion'] and not v['soloLectura']
    datos={'version':v['version'],'campos':{**v['campos'],'notas':'Observado por el operario <img src=x onerror=alert(1)>'},'presentacion':{'mostrarTotales':False,'fotosModo':'ELEGIDAS','fotosIds':[a]}}
    r=op.put(ruta,json=datos);assert r.status_code==200,r.text
    assert '&lt;img' in r.json()['html'] and '<img src=x' not in r.json()['html']
    assert r.json()['fotosSeleccionadas']==[a]
    assert op.post(ruta+'/manual',json={}).status_code==403
    assert op.post(f'/api/app/recepciones/{c}/entrega',json={}).status_code==403
    assert op.get('/api/operacion/gmail/buscar?q=packing').status_code in (403,404,422)
    assert op.put(ruta,json={**datos,'version':r.json()['version'],'gmailMensajeId':'mensaje-ajeno'}).status_code==403
    assert op.put(ruta,json={**datos,'version':r.json()['version'],'campos':{**datos['campos'],'destinatarios':'ajeno@example.test'}}).status_code==403
    db.rollback();assert db.get(AppRecepcion,c).estado!='CERRADA'
    assert m.leer_coleccion(db,c,'skus')[0]['contado']==4


def test_operario_no_modifica_borrador_de_recepcion_cerrada(cliente,db):
    c,ruta=configurar(cliente,db);db.get(AppRecepcion,c).estado='CERRADA';db.commit()
    op=TestClient(app);op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    v=op.get(ruta).json();assert v['soloLectura']
    assert op.put(ruta,json={'version':v['version'],'campos':v['campos']}).status_code==409


def test_reglas_existentes_incorporan_redaccion_sin_habilitar_cierre(cliente,db):
    f=AppConfig(clave='politicas',datos={'permisos':{'OPERADOR':{'cerrarRecepciones':False},'SUPERVISOR':{'cerrarRecepciones':True}}});db.add(f);db.commit()
    op=TestClient(app);op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    permisos=op.get('/api/auth/yo').json()['permisos']
    assert permisos['redactarCorreo'] and not permisos['cerrarRecepciones']


def test_corregir_cantidad_y_posicion_conserva_pallet_y_anula_sin_doblar_unidades(cliente,db):
    c=preparar(db)
    m.registrar_conteo(db,c,'op1',{'id':'original-61','sku':'SKU1','cantidad':4,'pallet':'E01','posicionReal':'A-01'})
    datos={'id':'correccion-61','cantidad':3,'contadoEsperado':4,'pallet':'E01','posicionReal':'CALLEKL','motivo':'Verificación física y ubicación'}
    ruta=f'/api/operacion/recepciones/{c}/eventos/original-61/corregir'
    r=cliente.post(ruta,json=datos);assert r.status_code==200,r.text
    assert cliente.post(ruta,json=datos).json()['duplicado']
    es=cliente.get(f'/api/app/recepciones/{c}/eventos').json()
    nuevo=next(e for e in es if e['id']=='correccion-61')
    assert nuevo['posicionReal']=='CALLEKL' and nuevo['pallet']=='E01' and nuevo['cantidad']==3
    assert all(e['pallet']!='DP' for e in es)
    assert sum(e['cantidad'] for e in es)==3
    # Anular actualiza el agregado y la bitácora del mismo servidor inmediatamente.
    anular=cliente.post(f'/api/app/recepciones/{c}/conteos/correccion-61/anular',json={'motivo':'Se revisará otra vez'})
    assert anular.status_code==200,anular.text
    assert cliente.get(f'/api/app/recepciones/{c}/skus').json()[0]['contado']==0
    assert any(e['anulaA']=='correccion-61' for e in cliente.get(f'/api/app/recepciones/{c}/eventos').json())
