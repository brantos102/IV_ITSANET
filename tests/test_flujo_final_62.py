"""Cambios de la revisión 62: datos reales, redacción libre y envío sin duplicados."""
import base64
import io
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import select
from app.main import app
from app.models import AppArchivo,AppConfig,AppCopiaDrive,AppEntrega,AppRecepcion,AppEvento,AppIngreso
from app.services import app_modelo as m,correo_redactado as correo,entregas,carpetas_recepcion as carpetas
from app.services.correo_cuerpo import limpiar,aplicar
from tests.test_remitente_responsable import correo as cuenta_correo
from tests.test_correo_y_bitacora_61 import configurar,imagen
from tests.test_fotos_embarques_54 import preparar


def test_cuerpo_libre_con_bloques_calculados_sin_ejecucion_ni_cantidades_inventadas():
    base='<div data-correo-bloque="tabla:PNC"><table><tr><td>3 reales</td></tr></table></div>'
    cuerpo='<h3>Informe revisado</h3><p style="color:red;background:url(https://ajeno)">Observación <b>validada</b></p><div data-correo-bloque="tabla:PNC">900 falsas</div><script>alert(1)</script><a href="javascript:alert(1)" onclick="x()">enlace</a>'
    guardado=limpiar(cuerpo,base);final=aplicar(guardado,base)
    assert '<b>validada</b>' in final and '3 reales' in final
    assert all(x not in final for x in ('900 falsas','script','onclick','javascript:','url('))
    assert 'data-correo-bloque="tabla:PNC"></div>' in guardado
    with pytest.raises(Exception):limpiar('<img src="https://ajeno/foto">',base)


def test_cuerpo_editado_se_conserva_con_fotos_nuevas_y_no_se_guarda_binario(cliente,db):
    c,ruta=configurar(cliente,db);v=cliente.get(ruta).json()
    datos={'version':v['version'],'campos':{**v['campos'],'cuerpoHtml':'<p>Redacción completamente libre</p><div data-correo-bloque="tabla:FALTANTE"></div>'}}
    r=cliente.put(ruta,json=datos);assert r.status_code==200,r.text
    assert 'Redacción completamente libre' in r.json()['texto'] and '<table' in r.json()['html']
    f=imagen(cliente,c,'PRERECEPCION','red');v=cliente.get(ruta).json()
    r=cliente.put(ruta,json={'version':v['version'],'campos':v['campos'],'presentacion':{'mostrarTotales':False,'fotosModo':'ELEGIDAS','fotosIds':[f]}})
    assert r.status_code==200,r.text
    assert 'Redacción completamente libre' in r.json()['html'] and 'data-archivo="'+f+'"' in r.json()['html']
    v=r.json();r=cliente.put(ruta,json={'version':v['version'],'campos':v['campos'],'presentacion':{'mostrarTotales':False,'fotosModo':'NINGUNA','fotosIds':[]}})
    assert r.status_code==200 and 'data-archivo=' not in r.json()['html']
    db.rollback();assert 'base64' not in str(db.get(AppConfig,correo.clave_config(c)).datos)


def test_cuerpo_y_presentacion_invalidos_no_generan_error_500(cliente,db):
    c,ruta=configurar(cliente,db);v=cliente.get(ruta).json()
    for d in ({'cuerpoHtml':14},{'cuerpoHtml':'<p>hola</p>','fechaOperacion':'no-fecha'}):
        assert cliente.put(ruta,json={'version':v['version'],'campos':{**v['campos'],**d}}).status_code==422
    assert cliente.put(ruta,json={'version':v['version'],'campos':{**v['campos'],'cuerpoHtml':'<p>hola</p>'},'presentacion':{'fotosModo':'AJENA'}}).status_code==422


def test_marca_y_avisos_depot_separados_del_correo_externo(cliente,db):
    c,ruta=configurar(cliente,db);db.add(AppIngreso(recepcion=c,datos={'marca':'VW'}));db.commit()
    v=cliente.get(ruta).json();assert 'VENTURA–VW' in v['html'] and v['marca']=='VW'
    assert v['validacionDepot'] and 'Productos por verificar en Depot' not in v['html']


def test_carpetas_se_encolan_al_crear_y_al_cargar_embarques_sin_google(cliente,db):
    c=preparar(cliente,db);f=db.get(AppConfig,carpetas.clave(c))
    assert f.datos['estado']=='BAJO_DEMANDA' and f.datos['embarques']==['RB-A','RB-B']
    assert db.query(AppArchivo).count()==0 and db.query(AppEntrega).count()==0


def test_preparaciones_antiguas_no_crean_carpetas_sin_fotos_ni_correo(cliente,db,monkeypatch):
    c=preparar(cliente,db);llamadas=[]
    f=db.get(AppConfig,carpetas.clave(c));f.datos={**f.datos,'estado':'PENDIENTE'};db.commit()
    def google(op,k,p):
        llamadas.append((op,p));assert p['embarques']==['RB-A','RB-B']
        return {'capacidades':['carpetasRecepcion62']} if op=='estado' else {'carpeta':'https://drive.google.com/drive/folders/recepcion62'}
    monkeypatch.setattr(entregas,'llamar',google)
    assert carpetas.procesar_uno(db);assert not carpetas.procesar_uno(db)
    assert llamadas==[]
    assert db.get(AppConfig,carpetas.clave(c)).datos['estado']=='BAJO_DEMANDA'
    assert db.query(AppArchivo).count()==0


def test_buzon_y_carpeta_fallidos_conservan_tarea_y_registros(cliente,db,monkeypatch):
    c=preparar(cliente,db);monkeypatch.setattr(entregas,'configurado',lambda *a:False)
    assert not carpetas.procesar_uno(db);f=db.get(AppConfig,carpetas.clave(c));assert f.datos['estado']=='BAJO_DEMANDA'
    assert m.obtener(db,c).estado=='ABIERTA' and not carpetas.procesar_uno(db)


def documento(cliente,c):
    ruta='/api/operacion/recepciones/'+c
    f=cliente.post(ruta+'/informes',json={'clave':uuid4().hex,'tipo':'DESCARGA','formato':'envio-ampliado','ultimoVisto':None})
    assert f.status_code==200,f.text
    f=f.json();libro=Workbook();libro.active.append(['SKU','Contado']);libro.active.append(['SKU1',2]);b=io.BytesIO();libro.save(b)
    origenes=cliente.get('/api/app/recepciones/'+c).json()['origenes']
    adjuntos=[]
    for origen in origenes:
        libro.properties.subject=origen;contenido=io.BytesIO();libro.save(contenido)
        adjuntos.append({'nombre':'Validacion_'+origen+f['sufijo']+'.xlsx','origen':origen,'base64':base64.b64encode(contenido.getvalue()).decode()})
    r=cliente.put(ruta+'/informes/'+f['id'],json={'adjuntos':adjuntos})
    assert r.status_code==200,r.text
    return f['id']


def listo(cliente,db,cuenta_correo):
    c,_=cuenta_correo;ident=documento(cliente,c);ruta='/api/operacion/recepciones/'+c+'/correo'
    v=cliente.get(ruta).json();v=cliente.put(ruta,json={'version':v['version'],'campos':{**v['campos'],'destinatarios':'ejecutivo@example.test'}}).json()
    return c,ruta,{'version':v['version'],'informeId':ident,'confirmar':True,'remitenteConfirmado':'personal@example.test'}


def test_enviar_revisado_es_idempotente_y_no_cambia_cantidades_ni_estado(cliente,db,cuenta_correo):
    c,ruta,d=listo(cliente,db,cuenta_correo);antes=cliente.get('/api/app/recepciones/'+c+'/skus').json();estado=m.obtener(db,c).estado
    a=cliente.post(ruta+'/enviar',json=d);assert a.status_code==201,a.text
    b=cliente.post(ruta+'/enviar',json=d);assert b.status_code==201 and a.json()['id']==b.json()['id'],b.text
    assert cliente.get('/api/app/recepciones/'+c+'/skus').json()==antes
    db.rollback();assert m.obtener(db,c).estado==estado and db.query(AppEntrega).count()==1
    e=db.get(AppEntrega,a.json()['id']);assert e.datos['correosPorOrigen'][0]['destinatarios']=='ejecutivo@example.test'
    assert e.datos['reporteSinCierre'] and e.datos['remitente']=='personal@example.test'


def test_enviar_bloquea_cambios_de_conteo_documentos_y_usuario(cliente,db,cuenta_correo):
    c,ruta,d=listo(cliente,db,cuenta_correo)
    op=TestClient(app);op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    assert op.post(ruta+'/enviar',json=d).status_code==403
    assert cliente.post(ruta+'/enviar',json={**d,'remitenteConfirmado':'ajeno@example.test'}).status_code==409
    assert cliente.post(ruta+'/enviar',json={**d,'informeId':'no-existe'}).status_code==409
    m.registrar_conteo(db,c,'sup',{'id':'otro62','sku':'SKU1','cantidad':1,'pallet':'E99','confirmarSobrante':True})
    assert cliente.post(ruta+'/enviar',json=d).status_code==409
    db.rollback();assert db.query(AppEntrega).count()==0


def test_entrega_revisada_confirma_documento_cuenta_y_hilo_sin_envio_real(cliente,db,cuenta_correo,monkeypatch):
    c,ruta,d=listo(cliente,db,cuenta_correo);r=cliente.post(ruta+'/enviar',json=d);assert r.status_code==201,r.text
    llamadas=[]
    def google(op,k,p):
        llamadas.append((op,p));assert p['usuario']=='personal@example.test'
        if op=='estado':return {'remitente':p['usuario'],'capacidades':['correoEditable']}
        if op=='archivo':return {'fileId':'documento-confirmado-62','nombre':p['nombre']}
        assert op=='finalizar' and len(p['archivos'])==1
        assert p['correoFinal']['campos']['destinatarios']=='ejecutivo@example.test'
        return {'enviadoA':p['destinatarios'],'remitente':p['usuario']}
    monkeypatch.setattr(entregas,'llamar',google)
    assert entregas.procesar_uno();db.rollback();db.expire_all();e=db.get(AppEntrega,r.json()['id']);assert e.estado=='ENTREGADA',e.error
    assert [op for op,_ in llamadas]==['estado','archivo','finalizar']
    assert not entregas.procesar_uno()


def test_historial_resuelve_nombre_del_operario_sin_cambiar_autoria(cliente,db):
    c,ruta=configurar(cliente,db);es=cliente.get('/api/app/recepciones/'+c+'/eventos').json();e=next(e for e in es if e['tipo']=='CONTEO')
    assert e['operadorNombre'] and '@' not in e['operadorNombre'] and e['operadorEmail']=='op1'
    db.rollback();assert db.get(AppEvento,e['id']).usuario=='op1'


def test_recuperacion_de_reporte_sin_cierre_valida_snapshot_y_conserva_estado(cliente,db,cuenta_correo,monkeypatch):
    from app.services import recuperar_entrega
    c,ruta,d=listo(cliente,db,cuenta_correo);r=cliente.post(ruta+'/enviar',json=d);assert r.status_code==201,r.text
    ident=r.json()['id'];db.rollback();e=db.get(AppEntrega,ident);e.estado='CANCELADA';db.commit()
    v=recuperar_entrega.vista(db,ident,'personal@example.test','PERSONAL')
    assert v['entrega']['reporteSinCierre'] and m.obtener(db,c).estado!='CERRADA'
    # El fixture tiene otra conexión: liberar sus bloqueos antes de usar HTTP.
    db.rollback()
    archivado=cliente.get(ruta,params={'entregaId':ident}).json()
    assert archivado['origenes']==['LISTA']
    correo_archivado=cliente.get(ruta,params={'entregaId':ident,'origen':'LISTA'}).json()
    assert correo_archivado['archivos']
    monkeypatch.setattr(entregas,'llamar',lambda *args:{'remitente':'personal@example.test','versionPuente':2,'capacidades':['correoEditable','correoVerificado']})
    nuevo=cliente.post('/api/app/entregas/'+ident+'/solicitar',json={'confirmarNoEnviado':True,'motivo':'Conexión corregida y enviado no confirmado',
        'remitenteConfirmado':'personal@example.test','correos':[{'origen':'LISTA','correoVersion':correo_archivado['version'],'destinatarios':correo_archivado['campos']['destinatarios']}]})
    assert nuevo.status_code==200,nuevo.text
    db.rollback();assert db.get(AppEntrega,ident).estado=='PENDIENTE' and m.obtener(db,c).estado!='CERRADA'


def test_tablas_y_documentos_del_cuerpo_se_actualizan_sin_conservar_diferencias_falsas(cliente,db):
    from app.services.correo_cuerpo import bloques
    c,ruta=configurar(cliente,db);v=cliente.get(ruta).json()
    cuerpo='<p>Texto libre conservado</p>'+''.join('<div data-correo-bloque="'+k+'"></div>' for k in bloques(v['html']))
    r=cliente.put(ruta,json={'version':v['version'],'campos':{**v['campos'],'cuerpoHtml':cuerpo}});assert r.status_code==200,r.text
    assert 'Faltantes' in r.json()['html']
    m.registrar_conteo(db,c,'op1',{'id':'completar62','sku':'SKU1','cantidad':2,'pallet':'E02'})
    v=cliente.get(ruta);assert v.status_code==200,v.text
    assert 'Texto libre conservado' in v.json()['html'] and 'Faltantes' not in v.json()['html']
    assert 'Producto no conforme' in v.json()['html']


def test_dos_confirmaciones_concurrentes_mysql_crean_una_sola_entrega(cliente,db,cuenta_correo):
    from concurrent.futures import ThreadPoolExecutor
    if db.bind.dialect.name!='mysql':pytest.skip('Concurrencia InnoDB en base exclusiva de revisión')
    c,ruta,d=listo(cliente,db,cuenta_correo);db.rollback()
    def enviar(_):
        sesion=TestClient(app)  # Sin lifespan: los workers Google no se inician.
        try:
            assert sesion.post('/api/auth/login',json={'usuario':'sup','pin':'1111'}).status_code==200
            r=sesion.post(ruta+'/enviar',json=d);return r.status_code,r.json()
        finally:sesion.close()
    with ThreadPoolExecutor(max_workers=2) as executor:res=list(executor.map(enviar,range(2)))
    assert all(estado==201 for estado,_ in res),res
    assert res[0][1]['id']==res[1][1]['id']
    db.rollback();assert db.query(AppEntrega).filter_by(recepcion=c).count()==1


def test_gmail_busca_y_comprueba_su_buzon_sin_depender_del_acceso_drive(cliente,db,cuenta_correo,monkeypatch):
    llamadas=[]
    def puente(op,k,d,conexion):
        llamadas.append(op)
        if op=='estado':pytest.fail('Gmail no debe abrir ni verificar carpetas Drive para buscar')
        assert d['usuario']=='personal@example.test'
        if op=='gmailEstado':return {'cuentaGmail':'personal@example.test','lecturaConfirmada':True}
        return {'cuentaGmail':'personal@example.test','mensajes':[],'hayMas':False}
    monkeypatch.setattr(entregas,'llamar_conexion',puente)
    r=cliente.get('/api/app/integraciones/mi-google/gmail',params={'busqueda':'CARGA ENTREGADA after:2026/10/01'})
    assert r.status_code==200 and llamadas==['gmailEstado','gmailBuscar'],r.text
    llamadas.clear();r=cliente.get('/api/app/integraciones/mi-google/gmail/estado')
    assert r.status_code==200 and r.json()['lecturaConfirmada'] and llamadas==['gmailEstado']


def test_correo_separado_no_convierte_conteo_historico_sin_lista_en_faltante_falso(cliente,db,cuenta_correo):
    c,_=cuenta_correo
    m.guardar_packing_list(db,c,{'lineas':[{'linea':1,'sku':'SKU1','cantidad':1}],'porSku':{'SKU1':1},'unidades':1},'B')
    m.registrar_conteo(db,c,'op1',{'id':'otra-lista62','sku':'SKU1','cantidad':1,'pallet':'E02','origen':'B'})
    # Simula un registro histórico, anterior al vínculo obligatorio de packing list.
    db.get(AppEvento,'conteo-1').origen=None;db.commit()
    ident=documento(cliente,c);ruta='/api/operacion/recepciones/'+c+'/correo'
    v=cliente.get(ruta,params={'origen':'LISTA'}).json()
    v=cliente.put(ruta,json={'origen':'LISTA','version':v['version'],'campos':{**v['campos'],'destinatarios':'ejecutivo@example.test'}}).json()
    r=cliente.post(ruta+'/enviar',json={'origen':'LISTA','version':v['version'],'informeId':ident,'confirmar':True,'remitenteConfirmado':'personal@example.test'})
    assert r.status_code==409 and 'packing list' in r.json()['detail'],r.text
    db.rollback();assert db.query(AppEntrega).count()==0
