"""Casos operativos: códigos transpuestos, cierre externo y agrupación elegida."""
import base64
import io
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import select
from app.main import app
from app.db import engine,SessionLocal
from app.models import AppConfig,AppArchivo,AppCopiaDrive,AppEvidencia,AppEvento,AppEntrega,AppRecepcion,Producto
from app.services import app_modelo as m,lecturas,operacion,archivos,drive,informes,agrupacion_correo as ag
from tests.test_fotos_embarques_54 import preparar
from tests.test_operacion_desarrollo import foto
from tests.test_agrupacion_embarques_53 import multi
from tests.test_remitente_responsable import correo


def test_sugerencia_prioriza_transposicion_real_del_packing_sin_cambiar_codigo(cliente,db):
    m.crear_recepcion(db,{'codigo':'LECTURA56','cliente':'VENTURA'},'sup')
    m.guardar_packing_list(db,'LECTURA56',{'lineas':[{'linea':1,'sku':'2GP845025B','cantidad':7}], 'porSku':{'2GP845025B':7},'unidades':7})
    for sku in ('2GP845201B','2GP845202B'):db.add(Producto(sku=sku,cliente='VENTURA',origen='API',descripcion='Candidato de catálogo'))
    db.commit();r=lecturas.resolver(db,'2GP845205B','LECTURA56')
    assert r['confirmar'] and not r['resuelto'] and r['sku']=='2GP845205B'
    assert r['candidatos'][0]=='2GP845025B'
    assert r['detallesCandidatos'][0]['enPackingList']
    assert m.leer_coleccion(db,'LECTURA56','skus')[0]['contado']==0


def test_catalogo_compartido_reutiliza_e_impide_segunda_reserva(cliente,db,monkeypatch):
    from app.routers import catalogo
    from app.services import catalogo_actualizacion as ca
    llamadas=[]
    monkeypatch.setattr(catalogo,'_sincronizar_depot',lambda *a:(llamadas.append(1) or {'productos':8,'clientes':1,'errores':[]}))
    for _ in range(2):assert cliente.post('/api/catalogo/depot/sincronizar').status_code==200
    assert len(llamadas)==1
    db.rollback();db.expire_all();f=db.get(AppConfig,ca.CLAVE);f.datos={**f.datos,'vigenteHasta':''};db.commit()
    token,_=ca.reservar(db,'sup')
    with pytest.raises(HTTPException) as e:ca.reservar(db,'otro')
    assert e.value.status_code==409
    ca.terminar(db,token)
    assert operacion.DEFECTO['catalogo']['activo'] is False


def test_cliente_eliminado_sale_del_selector_conserva_recepcion_y_bloquea_nueva(cliente,db):
    m.crear_recepcion(db,{'codigo':'ANTIGUA56','cliente':'VENTURA/VW'},'sup')
    datos={'id':'VENTURA/VW','version':0,'confirmar':True}
    r=cliente.request('DELETE','/api/operacion/clientes-fichas',json=datos);assert r.status_code==200,r.text
    assert cliente.get('/api/app/recepciones/ANTIGUA56').json()['cliente']=='VENTURA/VW'
    assert next(c for c in cliente.get('/api/operacion/clientes-operacion').json() if c['id']=='VENTURA/VW')['eliminado']
    assert cliente.post('/api/app/recepciones',json={'codigo':'NUEVA56','cliente':'VENTURA/VW'}).status_code>=400
    op=TestClient(app);op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    assert op.request('DELETE','/api/operacion/clientes-fichas',json=datos).status_code==403


def test_cierre_desde_recepciones_exige_ambos_embarques_y_es_idempotente(cliente,db,multi):
    ruta='/api/operacion/recepciones/'+multi+'/cierre-externo'
    p=cliente.get(ruta).json();assert len(p['grupos'])==2 and p['sinVerificar']==0
    datos={'version':p['version'],'motivo':'Se enviaron ambos correos desde Gmail, con los documentos finales.','confirmaciones':{g['id']:{'correo':True,'validacion':True} for g in p['grupos']}}
    incompleta={**datos,'confirmaciones':{p['grupos'][0]['id']:{'correo':True,'validacion':True}}}
    assert cliente.post(ruta,json=incompleta).status_code==422
    r=cliente.post(ruta,json=datos);assert r.status_code==200,r.text
    assert r.json()['recepcion']['estado']=='CERRADA'
    assert cliente.post(ruta,json=datos).status_code==200
    db.rollback();db.expire_all()
    assert db.query(AppEvento).filter_by(recepcion=multi,tipo='CIERRE').count()==1
    assert db.query(AppEntrega).filter_by(recepcion=multi).count()==0


def test_cierre_rechaza_cambio_concurrente_y_correo_procesando(cliente,db,multi):
    from uuid import uuid4
    ruta='/api/operacion/recepciones/'+multi+'/cierre-externo';p=cliente.get(ruta).json()
    datos={'version':p['version'],'motivo':'Envío comprobado personalmente en Gmail.','confirmaciones':{g['id']:{'correo':True,'validacion':True} for g in p['grupos']}}
    m.registrar_conteo(db,multi,'sup',{'id':'cambio56','sku':'MISMO','cantidad':1,'pallet':'B02','confirmarSobrante':True})
    assert cliente.post(ruta,json=datos).status_code==409
    p=cliente.get(ruta).json();datos['version']=p['version']
    db.rollback();db.add(AppEntrega(id=uuid4().hex,clave=uuid4().hex,recepcion=multi,usuario='sup',estado='PROCESANDO',datos={}));db.commit()
    r=cliente.post(ruta,json=datos);assert r.status_code==409 and 'procesándose' in r.text
    db.rollback();db.expire_all();assert db.get(AppRecepcion,multi).estado!='CERRADA'


def test_general_explicita_de_sku_compartido_usa_generales_y_enlaces_en_ambos_embarques(cliente,db,multi):
    f=foto(cliente,multi,sku='MISMO',categoria='PNC',embarqueFoto='').json()
    db.rollback();db.expire_all();j=db.get(AppCopiaDrive,f['id']);assert j.datos['ruta']==['GENERALES','PNC','MISMO']
    a=db.get(AppArchivo,f['id']);a.drive_id='drive-general56';e=db.scalar(select(AppEvidencia).where(AppEvidencia.archivo_id==a.id))
    url='https://drive.google.com/drive/folders/general56';j.estado='COPIADA';j.datos={**j.datos,'vinculosPorEvidencia':{e.id:{'carpetaSkuUrl':url}}};db.commit()
    meta=informes.metadatos(db,multi)
    assert meta['carpetasPorEmbarque']['EMB-A']['carpetas']['MISMO']==[url]
    assert meta['carpetasPorEmbarque']['EMB-B']['carpetas']['MISMO']==[url]
    assert drive.resumen_fotos(db,multi)['pendientes']==0


def test_correo_sin_fotos_muestra_carpeta_verificada_y_no_nota_tecnica(cliente,db,correo):
    c,_=correo;operacion.auditoria(db,c,'sup','CARPETA_DRIVE_VERIFICADA',{'carpeta':'https://drive.google.com/drive/folders/recepcion56'});db.commit()
    r=cliente.get('/api/operacion/recepciones/'+c+'/correo');assert r.status_code==200,r.text
    assert 'https://drive.google.com/drive/folders/recepcion56' in r.json()['html']
    assert 'No se adjunta la hoja MAESTRO' not in r.json()['html']
    assert 'No es una consulta en vivo' not in r.json()['html']


def test_consolidado_requiere_confirmacion_archiva_un_libro_y_cierra_sin_enviar(cliente,db,multi):
    ruta='/api/operacion/recepciones/'+multi
    p=cliente.get(ruta+'/correos-embarques').json();datos={'version':p['version'],'modo':'RECEPCION','asignaciones':{},'repartos':{},'embarquesPorLinea':{}}
    assert cliente.put(ruta+'/correos-embarques',json=datos).status_code==422
    r=cliente.put(ruta+'/correos-embarques',json={**datos,'confirmarConsolidado':True});assert r.status_code==200,r.text
    f=cliente.post(ruta+'/informes',json={'tipo':'CORREO','formato':'envio-ampliado','clave':'consolidado-56','ultimoVisto':None});assert f.status_code==200,f.text
    f=f.json();w=Workbook();w.active.append(['SKU','Cantidad']);w.active.append(['MISMO',8]);b=io.BytesIO();w.save(b)
    adjunto={'nombre':'CONSOLIDADO'+f['sufijo']+'.xlsx','origen':'RECEPCION','grupo':'RECEPCION','base64':base64.b64encode(b.getvalue()).decode()}
    r=cliente.put(ruta+'/informes/'+f['id'],json={'adjuntos':[adjunto]});assert r.status_code==200,r.text
    v=cliente.get(ruta+'/correo',params={'origen':'RECEPCION'}).json()
    assert v['modoAgrupacion']=='RECEPCION' and v['correosSeparados'] and v['origenes']==['RECEPCION']
    v=cliente.put(ruta+'/correo',json={'origen':'RECEPCION','version':v['version'],'campos':{**v['campos'],'destinatarios':'ejecutivo@example.test'}}).json()
    db.rollback();eventos=[e['id'] for e in m.leer_coleccion(db,multi,'eventos')];db.rollback()
    r=cliente.post('/api/app/recepciones/'+multi+'/entrega',json={'modoEntrega':'MANUAL','informeId':f['id'],'correos':[{'origen':'RECEPCION','correoVersion':v['version'],'destinatarios':'ejecutivo@example.test'}],'destinatarios':'ejecutivo@example.test','eventos':eventos})
    assert r.status_code==201,r.text
    assert len(r.json()['correos'])==1


def test_miniatura_local_perdura_tras_liberar_original_sin_google(cliente,db,monkeypatch,tmp_path):
    from PIL import Image
    from uuid import uuid4
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    ident=uuid4().hex;a=AppArchivo(id=ident,recepcion='R',tipo='foto',nombre='foto.jpg',mime='image/jpeg',bytes=0,sha256='a'*64,usuario='sup')
    destino=archivos.ruta(a);destino.parent.mkdir(parents=True);Image.new('RGB',(1600,1200),'blue').save(destino,format='JPEG')
    archivos.conservar_miniatura(a);destino.unlink()
    mini=tmp_path/'app_miniaturas'/ident;assert mini.is_file()
    with Image.open(mini) as imagen:assert max(imagen.size)<=960
    assert mini.stat().st_size<300000


@pytest.mark.skipif(engine.dialect.name!='mysql',reason='Verifica reserva entre dos sesiones MySQL reales')
def test_dos_supervisores_no_actualizan_catalogo_al_mismo_tiempo(db):
    from threading import Barrier
    from app.services import catalogo_actualizacion as ca
    barrera=Barrier(2)
    def reservar(usuario):
        with SessionLocal() as s:
            barrera.wait()
            try:return ca.reservar(s,usuario)[0]
            except HTTPException as e:return e.status_code
    with ThreadPoolExecutor(max_workers=2) as ex:resultados=list(ex.map(reservar,['sup1','sup2']))
    assert resultados.count(409)==1 and sum(isinstance(x,str) for x in resultados)==1
    ca.terminar(db,next(x for x in resultados if isinstance(x,str)))


@pytest.mark.skipif(engine.dialect.name!='mysql',reason='Requiere snapshot REPEATABLE READ MySQL')
def test_plan_guardado_por_otro_supervisor_no_se_pierde_por_snapshot_antiguo(cliente,db,multi):
    anterior=cliente.get('/api/operacion/recepciones/'+multi+'/correos-embarques').json()
    with SessionLocal() as lector:
        assert ag.configuracion(lector,multi)['modo']=='PACKING_LIST'
        datos={'modo':'RECEPCION','version':anterior['version'],'asignaciones':{},'repartos':{},'embarquesPorLinea':{},'confirmarConsolidado':True}
        assert cliente.put('/api/operacion/recepciones/'+multi+'/correos-embarques',json=datos).status_code==200
        with pytest.raises(HTTPException) as e:ag.guardar(lector,multi,{**datos,'modo':'PACKING_LIST'},'otro')
        assert e.value.status_code==409
    db.rollback();db.expire_all();assert ag.configuracion(db,multi)['modo']=='RECEPCION'
