"""Casos de cruce de datos, destinatarios y concurrencia. Google siempre simulado."""
import json
import pytest
from sqlalchemy import select, delete
from fastapi.testclient import TestClient
from app.main import app
from app.db import engine, SessionLocal
from app.models import AppAuditoriaGeneral, AppArchivoSku, AppEvidencia, AppEvento, AppEntrega, AppConfig, AppLinea, AppRecepcion
from app.services import app_modelo as m, entregas, informes, correo_redactado as cr, agrupacion_correo as ag
from tests.test_operacion_desarrollo import foto
from tests.test_remitente_responsable import correo


@pytest.fixture
def logistica(cliente, db):
    c='DOS-CONTENEDORES-57'
    m.crear_recepcion(db,{'codigo':c,'cliente':'PRUEBA'},'sup')
    lineas=[{'linea':1,'sku':'SKU-A','cantidad':3,'embarque':'EMB-A','contenedor':'ABCU1234567',
        'cruda':['SKU-A',3,'EMB-A','ABCU1234567']},
        {'linea':2,'sku':'SKU-B','cantidad':5,'embarque':'EMB-B','contenedor':'DEFU7654321',
        'cruda':['SKU-B',5,'EMB-B','DEFU7654321']}]
    m.guardar_packing_list(db,c,{'lineas':lineas,'porSku':{'SKU-A':3,'SKU-B':5},'unidades':8,
        'encabezados':['SKU','Cantidad','Embarque','Nombre Contenedor'],'columnas':{'sku':0,'cantidad':1,'embarque':2}},'PRINCIPAL')
    return c


def distribucion(cliente,c):
    ruta='/api/operacion/recepciones/'+c+'/contenedores'
    v=cliente.get(ruta).json()
    datos={'version':v['version'],'filas':[
        {'numero':'ABCU1234567','desde':'E01','hasta':'E60','posicion':'CALLEKL','embarques':['EMB-A']},
        {'numero':'DEFU7654321','desde':'E61','hasta':'E96','posicion':'PISO 2','embarques':['EMB-B']}]}
    return ruta,v,datos


def test_contenedores_rango_total_y_no_modifica_conteos_ni_agrega_tablas(cliente,db,logistica):
    ruta,v,d=distribucion(cliente,logistica)
    assert len(v['detectados'])==2
    antes=m.leer_coleccion(db,logistica,'skus');db.rollback()
    r=cliente.put(ruta,json=d);assert r.status_code==200,r.text
    assert [f['total'] for f in r.json()['filas']]==[60,36]
    assert [f['id'] for f in r.json()['filas']]==['C1','C2']
    db.rollback();db.expire_all();assert m.leer_coleccion(db,logistica,'skus')==antes
    assert informes.metadatos(db,logistica)['contenedores']==r.json()['filas']
    # Guardar de nuevo el mismo dato no genera otra fila de auditoría.
    d['version']=r.json()['version'];assert cliente.put(ruta,json=d).status_code==200
    db.rollback();db.expire_all()
    assert db.query(AppAuditoriaGeneral).filter_by(referencia=logistica,accion='DISTRIBUCION_CONTENEDORES').count()==1


@pytest.mark.parametrize('cambio',[
    {'desde':'E50','hasta':'E96'}, {'desde':'F61','hasta':'E96'}, {'desde':'E96','hasta':'E61'},
    {'numero':'INVALIDO'}, {'numero':'ABCU1234567'}, {'embarques':['EMB-A']}, {'embarques':['AJENO']},
])
def test_contenedores_rechaza_solapamiento_y_cruce_de_embarques(cliente,db,logistica,cambio):
    ruta,v,d=distribucion(cliente,logistica);d['filas'][1].update(cambio)
    assert cliente.put(ruta,json=d).status_code==422
    assert cliente.get(ruta).json()['filas']==[]


def test_contenedores_version_evitar_pisar_otro_supervisor_y_permiso(cliente,db,logistica):
    ruta,v,d=distribucion(cliente,logistica)
    assert cliente.put(ruta,json=d).status_code==200
    assert cliente.put(ruta,json={**d,'filas':[]}).status_code==409
    op=TestClient(app);op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    assert op.get(ruta).status_code==403
    assert op.put(ruta,json=d).status_code==403


def test_contenedores_correo_por_embarque_no_mezcla_distribuciones(cliente,db,logistica):
    ruta,_,d=distribucion(cliente,logistica);assert cliente.put(ruta,json=d).status_code==200
    p=ag.vista(db,logistica)
    ag.guardar(db,logistica,{'version':p['version'],'modo':'EMBARQUE','asignaciones':{},'repartos':{},'embarquesPorLinea':{}},'sup')
    for emb,numero,ajeno in [('EMB-A','ABCU1234567','DEFU7654321'),('EMB-B','DEFU7654321','ABCU1234567')]:
        v=cr.vista(db,logistica,'sup',origen=ag.grupo_id(emb))
        assert numero in v['html'] and ajeno not in v['html']


def test_fotos_sku_no_muestra_contexto_y_recupera_vinculo_activo_sin_indice(cliente,db,logistica):
    a=foto(cliente,logistica,sku='SKU-A',categoria='PNC').json()
    b=foto(cliente,logistica,sku='SKU-B',categoria='PNC').json()
    foto(cliente,logistica,categoria='RECEPCION',tipoEvidencia='PANORAMICA')
    db.rollback();db.execute(delete(AppArchivoSku).where(AppArchivoSku.archivo_id==a['id']));db.commit()
    r=cliente.get('/api/app/recepciones/'+logistica+'/imagenes',params={'sku':'SKU-A'}).json()
    assert [f['id'] for f in r['archivos']]==[a['id']]
    assert r['sincronizacion']['guardadas']==1
    assert cliente.get('/api/app/recepciones/'+logistica+'/imagenes',params={'sku':'NO-EXISTE'}).json()['total']==0
    db.rollback();e=db.scalar(select(AppEvidencia).where(AppEvidencia.archivo_id==a['id'],AppEvidencia.sku==m.normalizar_codigo('SKU-A')));e.sku=m.normalizar_codigo('SKU-B')
    # El enlace antiguo de bitácora no debe deshacer una reclasificación explícita.
    db.add(AppEvento(id='legacy57',recepcion=logistica,tipo='AUDITORIA',sku=m.normalizar_codigo('SKU-A'),datos={'fotos':['/api/app/archivos/'+a['id']]}));db.commit()
    assert cliente.get('/api/app/recepciones/'+logistica+'/imagenes',params={'sku':'SKU-A'}).json()['total']==0


def test_reparar_lectura_compara_fuente_y_conserva_todas_las_cantidades(cliente,db,logistica):
    db.rollback()
    for l in db.scalars(select(AppLinea).where(AppLinea.recepcion==logistica)):
        l.extra={**l.extra,'embarque':'BL-LATERAL','contenedor':'CONTENEDOR-ERRONEO'}
    db.get(AppRecepcion,logistica).embarques=['BL-LATERAL'];db.commit()
    ruta='/api/operacion/recepciones/'+logistica+'/revisar-packing'
    antes=m.leer_coleccion(db,logistica,'skus');db.rollback()
    v=cliente.get(ruta).json();assert v['puedeAplicar'] and v['lineasPorCorregir']==2
    assert cliente.put(ruta,json={'version':v['version']}).status_code==422
    r=cliente.put(ruta,json={'version':v['version'],'confirmar':True});assert r.status_code==200,r.text
    assert r.json()['embarques']==['EMB-A','EMB-B']
    db.rollback();db.expire_all();assert m.leer_coleccion(db,logistica,'skus')==antes
    assert len(m.leer_coleccion(db,logistica,'lineas'))==2
    assert not cliente.get(ruta).json()['puedeAplicar']
    assert cliente.put(ruta,json={'version':v['version'],'confirmar':True}).status_code==409


def test_revision_bloquea_si_sku_no_cuadra_con_fila_original(cliente,db,logistica):
    l=db.scalar(select(AppLinea).where(AppLinea.recepcion==logistica));l.extra={**l.extra,'cruda':['SKU-A',999,'EMB-A','ABCU1234567']};db.commit()
    r=cliente.get('/api/operacion/recepciones/'+logistica+'/revisar-packing').json()
    assert r['errores'] and not r['puedeAplicar']


def google_simulado(accion,clave,datos,conexion):
    assert datos['usuario']=='personal@example.test'
    if accion=='estado':return {'exito':True,'remitente':'personal@example.test','capacidades':['correoEditable','gmailHilos']}
    mensaje={'id':'abcdef0123456789','threadId':'fedcba9876543210','asunto':'Packing recibido',
        'de':'Cliente <ejecutivo@example.test>','para':'personal@example.test','cc':'','replyTo':'','fecha':'Hoy',
        'texto':'CUERPO QUE NO SE DEBE GUARDAR EN MYSQL','adjuntos':['packing.xlsx']}
    return {'exito':True,'mensajes':[mensaje],'hayMas':False} if accion=='gmailBuscar' else {'exito':True,'mensaje':mensaje}


def test_gmail_solo_cuenta_propia_no_persiste_buzon_y_hilo_se_guarda_verificado(cliente,db,correo,monkeypatch):
    c,_=correo;monkeypatch.setattr(entregas,'llamar_conexion',google_simulado)
    ruta='/api/app/integraciones/mi-google/gmail'
    r=cliente.get(ruta,params={'busqueda':'packing'});assert r.status_code==200,r.text
    assert r.json()['cuenta']=='personal@example.test'
    op=TestClient(app);op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    assert op.get(ruta,params={'busqueda':'packing'}).status_code==403
    ruta='/api/operacion/recepciones/'+c+'/correo';v=cliente.get(ruta).json()
    datos={'version':v['version'],'campos':{**v['campos'],'destinatarios':'ejecutivo@example.test'},'gmailMensajeId':'abcdef0123456789'}
    r=cliente.put(ruta,json=datos);assert r.status_code==200,r.text
    assert r.json()['asunto']=='Re: Packing recibido'
    assert r.json()['respuestaGmail']['cuenta']=='personal@example.test'
    db.rollback();db.expire_all()
    f=db.get(AppConfig,cr.clave_config(c));assert 'CUERPO QUE NO' not in json.dumps(f.datos)
    assert 'texto' not in f.datos['respuestaGmail'] and 'secreto' not in r.text
    # No se admite sustituir el asunto del hilo al guardar otros cambios.
    v=r.json();r=cliente.put(ruta,json={'version':v['version'],'campos':{**v['campos'],'asunto':'Otro'}})
    assert r.json()['asunto']=='Re: Packing recibido'
    v=r.json();r=cliente.put(ruta,json={'version':v['version'],'campos':v['campos'],'gmailMensajeId':''})
    assert r.status_code==200 and r.json()['respuestaGmail'] is None


def test_gmail_puente_antiguo_no_degrada_respuesta_a_correo_nuevo(cliente,db,correo,monkeypatch):
    monkeypatch.setattr(entregas,'llamar_conexion',lambda *a:{'exito':True,'remitente':'personal@example.test','capacidades':['correoEditable']})
    r=cliente.get('/api/app/integraciones/mi-google/gmail',params={'busqueda':'packing'})
    assert r.status_code==409 and 'Gmail.gs' in r.text


def test_gmail_fallo_de_cuenta_no_accede_al_buzon(cliente,db,correo,monkeypatch):
    acciones=[]
    def otro(accion,*args):acciones.append(accion);return {'exito':True,'remitente':'otro@example.test','capacidades':['gmailHilos']}
    monkeypatch.setattr(entregas,'llamar_conexion',otro)
    assert cliente.get('/api/app/integraciones/mi-google/gmail',params={'busqueda':'packing'}).status_code==409
    assert acciones==['estado']


def test_hilo_de_otro_supervisor_no_puede_congelarse_con_otra_identidad(cliente,db,correo,monkeypatch):
    c,_=correo;monkeypatch.setattr(entregas,'llamar_conexion',google_simulado)
    ruta='/api/operacion/recepciones/'+c+'/correo';v=cliente.get(ruta).json()
    assert cliente.put(ruta,json={'version':v['version'],'campos':{**v['campos'],'destinatarios':'ejecutivo@example.test'},'gmailMensajeId':'abcdef0123456789'}).status_code==200
    db.rollback();db.expire_all()
    v=cr.vista(db,c,'responsable@example.test');assert v['respuestaOtraCuenta'] and not v['respuestaGmail']
    with pytest.raises(Exception) as e:
        cr.congelar(db,c,{'correoVersion':v['version'],'destinatarios':'ejecutivo@example.test','modoEntrega':'MANUAL'},'responsable@example.test')
    assert getattr(e.value,'status_code',None)==409


def test_respuesta_congelada_no_se_envia_como_nueva_si_el_puente_perdio_capacidad(cliente,db,correo,monkeypatch):
    from app.services.instantaneas import expandir
    c,datos=correo;monkeypatch.setattr(entregas,'llamar_conexion',google_simulado)
    ruta='/api/operacion/recepciones/'+c+'/correo';v=cliente.get(ruta).json()
    v=cliente.put(ruta,json={'version':v['version'],'campos':{**v['campos'],'destinatarios':datos['destinatarios']},'gmailMensajeId':'abcdef0123456789'}).json()
    r=cliente.post('/api/app/recepciones/'+c+'/entrega',json={**datos,'correoVersion':v['version']});assert r.status_code==201,r.text
    db.rollback();e=db.get(AppEntrega,r.json()['id']);assert expandir(e.datos)['correoFinal']['respuestaGmail']['id']=='abcdef0123456789'
    db.rollback();acciones=[]
    def antiguo(accion,*args):acciones.append(accion);return {'exito':True,'remitente':'personal@example.test','capacidades':['correoEditable']}
    monkeypatch.setattr(entregas,'llamar',antiguo)
    assert entregas.procesar_uno()
    assert acciones==['estado']


def test_revision_bloquea_entrega_pendiente(cliente,db,logistica):
    from uuid import uuid4
    for l in db.scalars(select(AppLinea).where(AppLinea.recepcion==logistica)):
        l.extra={**l.extra,'embarque':'BL-LATERAL'}
    db.add(AppEntrega(id=uuid4().hex,clave=uuid4().hex,recepcion=logistica,usuario='sup',estado='PENDIENTE',datos={}));db.commit()
    ruta='/api/operacion/recepciones/'+logistica+'/revisar-packing';v=cliente.get(ruta).json()
    assert cliente.put(ruta,json={'version':v['version'],'confirmar':True}).status_code==409
    db.rollback();db.expire_all();assert all(l.extra['embarque']=='BL-LATERAL' for l in db.scalars(select(AppLinea).where(AppLinea.recepcion==logistica)))


@pytest.mark.skipif(engine.dialect.name!='mysql',reason='Verifica el snapshot real REPEATABLE READ de MySQL')
def test_guardar_correo_no_pisa_un_hilo_elegido_despues_de_abrir_snapshot(cliente,db,correo,monkeypatch):
    from fastapi import HTTPException
    c,_=correo;monkeypatch.setattr(entregas,'llamar_conexion',google_simulado)
    ruta='/api/operacion/recepciones/'+c+'/correo'
    viejo=cliente.get(ruta).json()
    with SessionLocal() as lector:
        assert lector.get(AppConfig,cr.clave_config(c)) is None  # Abre un snapshot sin bloquear el libro mayor.
        nuevo=cliente.get(ruta).json()
        assert cliente.put(ruta,json={'version':nuevo['version'],'campos':{**nuevo['campos'],'destinatarios':'ejecutivo@example.test'},'gmailMensajeId':'abcdef0123456789'}).status_code==200
        with pytest.raises(HTTPException) as e:
            cr.guardar(lector,c,{'version':viejo['version'],'campos':viejo['campos']},'personal@example.test')
        assert e.value.status_code==409
    assert cliente.get(ruta).json()['respuestaGmail']['id']=='abcdef0123456789'
