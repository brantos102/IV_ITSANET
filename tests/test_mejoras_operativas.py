"""Correcciones, repartos y conexiones sin mezclar usuarios o packing lists."""
import json
import pytest
from sqlalchemy import select
from app.models import AppEvento, AppSku, AppEntrega, AppRecepcion, Producto
from app.services import app_modelo as m, entregas, instantaneas, informes, archivos
from tests.test_integraciones_ui import admin
from tests.test_remitente_responsable import correo


def preparar(db,dos=False):
    codigo='MEJORAS'
    m.crear_recepcion(db,{'codigo':codigo,'cliente':'VENTURA'},'sup')
    for origen in (['A','B'] if dos else ['A']):
        m.guardar_packing_list(db,codigo,{'lineas':[{'linea':1,'sku':'SKU1','cantidad':3 if dos else 6}],
            'porSku':{'SKU1':3 if dos else 6},'unidades':3 if dos else 6,
            'encabezados':['SKU','Cantidad','ok'],'columnas':{'sku':0,'cantidad':1,'depot':2}},origen)
    return codigo


def test_corregir_es_atomico_idempotente_y_conserva_clasificacion(cliente,db):
    c=preparar(db)
    m.registrar_conteo(db,c,'op1',{'id':'conteo-original','sku':'SKU1','cantidad':6,'pallet':'P01',
        'incidencias':[{'tipo':'MAL_ESTADO','cantidad':2}]})
    d={'id':'correccion-segura','cantidad':5,'contadoEsperado':6,'motivo':'Se revisó el conteo físico'}
    ruta=f'/api/operacion/recepciones/{c}/eventos/conteo-original/corregir'
    r=cliente.post(ruta,json=d);assert r.status_code==200,r.text
    assert r.json()['contado']==5 and r.json()['cantidadPnc']==2 and r.json()['cantidadConforme']==3
    assert cliente.post(ruta,json=d).json()['duplicado']
    es=cliente.get(f'/api/app/recepciones/{c}/eventos').json()
    assert sum(e['cantidad'] for e in es)==5
    assert any(e['anulaA']=='conteo-original' for e in es)
    assert any(e.get('corrigeA')=='conteo-original' for e in es)


def test_correccion_invalida_y_concurrente_no_anula_original(cliente,db):
    c=preparar(db);m.registrar_conteo(db,c,'op1',{'id':'conteo-original','sku':'SKU1','cantidad':4,'pallet':'A1'})
    ruta=f'/api/operacion/recepciones/{c}/eventos/conteo-original/corregir'
    d={'id':'correccion-invalida','cantidad':-1,'contadoEsperado':4,'motivo':'Cantidad errónea'}
    assert cliente.post(ruta,json=d).status_code in (409,422)
    m.registrar_conteo(db,c,'op2',{'id':'otro-operario','sku':'SKU1','cantidad':1,'pallet':'B1'})
    assert cliente.post(ruta,json={**d,'cantidad':3}).status_code==409
    db.rollback();db.expire_all()
    assert db.scalar(select(AppEvento.id).where(AppEvento.anula_a=='conteo-original')) is None
    assert db.scalar(select(AppSku).where(AppSku.recepcion==c)).contado==5


def test_reparto_atomico_sin_sobrante_y_sin_duplicar_pnc(cliente,db):
    c=preparar(db,True)
    d={'idempotencyKey':'reparto-conjunto','sku':'SKU1','cantidad':4,'contadoEsperado':0,'pallet':'P01',
        'reparto':[{'origen':'A','cantidad':3},{'origen':'B','cantidad':1}],
        'incidencias':[{'tipo':'MAL_ESTADO','cantidad':1}]}
    ruta=f'/api/operacion/recepciones/{c}/conteos-repartidos'
    r=cliente.post(ruta,json=d);assert r.status_code==200,r.text
    assert r.json()['contado']==4 and r.json()['cantidadPnc']==1
    assert r.json()['porOrigen']=={'A':{'P01':3},'B':{'P01':1}}
    assert cliente.post(ruta,json=d).json()['duplicado']
    s=cliente.get(f'/api/app/recepciones/{c}/skus').json()[0]
    assert s['porOrigen']=={'A':{'P01':3},'B':{'P01':1}} and s['cantidadConforme']==3


def test_reparto_erroneo_revierte_todas_las_partes(cliente,db):
    c=preparar(db,True)
    d={'id':'reparto-incorrecto','sku':'SKU1','cantidad':6,'contadoEsperado':0,'pallet':'P01',
        'reparto':[{'origen':'A','cantidad':2},{'origen':'B','cantidad':4}]}
    r=cliente.post(f'/api/operacion/recepciones/{c}/conteos-repartidos',json=d)
    assert r.status_code==409,r.text
    assert cliente.get(f'/api/app/recepciones/{c}/skus').json()[0]['contado']==0
    db.rollback();assert not db.query(AppEvento).filter(AppEvento.tipo=='CONTEO').count()


def test_supervisor_gestiona_clientes_sin_acceso_a_conexiones(cliente):
    ruta='/api/operacion/clientes-operacion/CLIENTE%20NUEVO'
    r=cliente.put(ruta,json={'palletRequerido':False,'posicionRequerida':False});assert r.status_code==200,r.text
    assert any(c['id']=='CLIENTE NUEVO' for c in cliente.get('/api/operacion/clientes-operacion').json())
    assert cliente.put(ruta,json={'correo':{'responsable':'suplantacion@example.test'}}).status_code==422
    assert cliente.put('/api/operacion/config',json={'repositorios':[]}).status_code==403
    assert cliente.put('/api/app/integraciones/google',json={}).status_code==403


def test_instantanea_comprimida_reversible_y_corrupcion_detectada():
    d={'destinatarios':'cliente@example.test','skus':[{'sku':'SKU1','descripcion':'x'*300}]*2000,'lineas':[],'eventos':[]}
    c=instantaneas.compactar(d)
    assert 'skus' not in c and instantaneas.expandir(c)==d
    assert len(json.dumps(c))<len(json.dumps(d))/10
    c['instantaneaGzip']['sha256']='0'*64
    with pytest.raises(RuntimeError,match='dañada'):instantaneas.expandir(c)


def test_estado_depot_por_cliente_independiente_del_conteo(cliente,db):
    c=preparar(db)
    db.add(Producto(sku='SKU1',cliente='OTRO',existe_depot=True));db.commit()
    assert informes.metadatos(db,c)['depot']=={'SKU1':False}
    p=db.get(Producto,'SKU1');p.cliente='VENTURA';db.commit()
    assert informes.metadatos(db,c)['depot']=={'SKU1':True}


def test_comprobar_envio_personal_no_cierra_si_falla_la_clave(cliente,db,correo,monkeypatch):
    c,_=correo
    def falla(*a):raise RuntimeError('La clave compartida no coincide con SERVIDOR_HMAC de este Apps Script.')
    monkeypatch.setattr(entregas,'llamar',falla)
    r=cliente.post(f'/api/app/recepciones/{c}/comprobar-envio',json={'remitenteConfirmado':'personal@example.test'})
    assert r.status_code==502 and 'ADMIN' in r.text
    db.rollback();db.expire_all();assert db.get(AppRecepcion,c).estado!='CERRADA' and db.query(AppEntrega).count()==0


def test_correo_nuevo_usa_supervisor_y_guarda_una_sola_conexion(cliente,db,correo,monkeypatch):
    c,d=correo
    cuenta=cliente.get(f'/api/app/recepciones/{c}/remitentes').json()
    assert cuenta['predeterminado']=='PERSONAL'
    vistas=[]
    def puente(accion,clave,datos):
        vistas.append((accion,datos));assert datos['usuario']=='personal@example.test'
        return {'exito':True,'remitente':'personal@example.test','fileId':'archivo-confirmado','capacidades':['correoVerificado'],'enviadoA':datos.get('destinatarios','')}
    monkeypatch.setattr(entregas,'llamar',puente)
    r=cliente.post(f'/api/app/recepciones/{c}/comprobar-envio',json={'remitenteConfirmado':'personal@example.test'});assert r.status_code==200
    r=cliente.post(f'/api/app/recepciones/{c}/entrega',json=d);assert r.status_code==201 and r.json()['remitente']=='personal@example.test'
    assert entregas.procesar_uno() and not entregas.procesar_uno()
    assert [a for a,_ in vistas].count('finalizar')==1
    assert all('secreto' not in d and 'clave' not in d for _,d in vistas)


def test_no_se_confirma_correo_si_google_solo_confirma_drive(cliente,db,correo,monkeypatch):
    c,d=correo
    r=cliente.post(f'/api/app/recepciones/{c}/entrega',json=d);assert r.status_code==201
    def incompleto(accion,*args):return {'exito':True,'remitente':'personal@example.test','fileId':'archivo-confirmado'}
    monkeypatch.setattr(entregas,'llamar',incompleto)
    assert entregas.procesar_uno()
    db.rollback();db.expire_all();assert db.get(AppEntrega,r.json()['id']).estado=='REVISION'
    assert not entregas.procesar_uno()


def test_compactar_antiguos_conserva_informe_y_no_toca_reservas(admin,db):
    c=preparar(db)
    datos={'skus':[{'sku':'S','descripcion':'texto de recepción '*30}]*1000,'eventos':[],'lineas':[],
        'destinatarios':'cliente@example.test','informes':['informe-original']}
    for id,estado in [('a','CANCELADA'),('b','PROCESANDO')]:
        db.add(AppEntrega(id=id,clave=id*64,recepcion=c,usuario='sup',estado=estado,datos=datos))
    db.commit()
    r=admin.post('/api/operacion/almacenamiento/compactar',json={});assert r.status_code==200,r.text
    assert r.json()['compactadas']==1 and r.json()['bytesDespues']<r.json()['bytesAntes']/10
    db.rollback();db.expire_all()
    assert instantaneas.expandir(db.get(AppEntrega,'a').datos)==datos
    assert db.get(AppEntrega,'b').datos==datos and db.get(AppEntrega,'b').estado=='PROCESANDO'
    assert admin.get('/api/operacion/almacenamiento').status_code==200


def test_imagen_compartida_no_devuelve_carpeta_de_otro_sku(cliente,db,monkeypatch,tmp_path):
    from tests.test_operacion_desarrollo import foto
    from app.models import AppCopiaDrive
    c=preparar(db);monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    f=foto(cliente,c,sku='SKU1',categoria='PNC');assert f.status_code==201
    # Misma imagen vinculada a otro código: no se debe reutilizar su carpeta.
    f2=foto(cliente,c,sku='OTRO-SKU',categoria='PNC');assert f2.status_code==201
    j=db.get(AppCopiaDrive,f.json()['id']);j.estado='COPIADA';j.datos={**j.datos,
        'sku':'SKU1','ruta':['PNC','SKU1','ADICIONAL'],'carpetaSkuUrl':'https://drive.google.com/drive/folders/sku1'};db.commit()
    meta=informes.metadatos(db,c)
    assert meta['carpetas']['SKU1']==['https://drive.google.com/drive/folders/sku1']
    assert 'OTROSKU' not in meta['carpetas'] and meta['evidenciasPendientes']==1
    r=cliente.get(f'/api/app/recepciones/{c}/imagenes?categoriaEvidencia=PNC').json()
    assert r['total']==1
    assert next(e for e in r['archivos'][0]['evidencias'] if e['sku']=='SKU1')['carpetaDrive'].endswith('/sku1')
    assert next(e for e in r['archivos'][0]['evidencias'] if e['sku']=='OTROSKU')['carpetaDrive']==''
    assert cliente.get(f'/api/app/recepciones/{c}/imagenes?categoriaEvidencia=SOBRANTE').json()['total']==0


def test_puente_antiguo_no_permite_cierre_con_correo(cliente,db,correo,monkeypatch):
    c,_=correo
    monkeypatch.setattr(entregas,'llamar',lambda *args:{'exito':True,'remitente':'personal@example.test','capacidades':['prepararCarpeta']})
    r=cliente.post(f'/api/app/recepciones/{c}/comprobar-envio',json={'remitenteConfirmado':'personal@example.test'})
    assert r.status_code==502 and 'Proxy.gs' in r.text and 'Servidor.gs' in r.text
    assert db.query(AppEntrega).count()==0


def test_vincular_sku_a_foto_copiada_programa_ubicacion_sin_binario(cliente,db,monkeypatch,tmp_path):
    from tests.test_operacion_desarrollo import foto
    from app.models import AppCopiaDrive,AppArchivo
    from app.services import drive
    c=preparar(db);monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    f=foto(cliente,c,sku='SKU1',categoria='PNC');assert f.status_code==201
    a=db.get(AppArchivo,f.json()['id']);j=db.get(AppCopiaDrive,a.id)
    j.datos=drive.descripcion(db,a);j.estado='COPIADA';a.drive_id='foto-confirmada';db.commit()
    f2=foto(cliente,c,sku='OTRO-SKU',categoria='PNC');assert f2.status_code==201
    db.rollback();db.expire_all();j=db.get(AppCopiaDrive,a.id)
    assert j.estado=='PENDIENTE' and j.datos['accion']=='ubicar'
    assert len(j.datos['rutasVinculadas'])==2 and 'base64' not in j.datos
    assert db.get(AppArchivo,a.id).drive_id=='foto-confirmada'


def test_cliente_exige_un_archivo_identificado_por_cada_packing(cliente,db,monkeypatch,tmp_path):
    import base64,io
    from openpyxl import Workbook
    c=preparar(db,True);monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    ruta=f'/api/operacion/recepciones/{c}/informes'
    f=cliente.post(ruta,json={'clave':'formato-por-lista','tipo':'DESCARGA','formato':'envio','ultimoVisto':None}).json()
    def adjunto(origen):
        w=Workbook();w.active.append(['Lista',origen]);b=io.BytesIO();w.save(b)
        return {'nombre':origen+f['sufijo']+'.xlsx','origen':origen,'base64':base64.b64encode(b.getvalue()).decode()}
    a,b=adjunto('A'),adjunto('B')
    assert cliente.put(ruta+'/'+f['id'],json={'adjuntos':[a]}).status_code==422
    assert cliente.put(ruta+'/'+f['id'],json={'adjuntos':[a,a]}).status_code==422
    r=cliente.put(ruta+'/'+f['id'],json={'adjuntos':[a,b]});assert r.status_code==200,r.text
    assert [a['origen'] for a in r.json()['archivos']]==['A','B']


def test_formato_ampliado_espera_enlaces_aun_sin_columna_drive_original(cliente,db,monkeypatch,tmp_path):
    from tests.test_operacion_desarrollo import foto
    c=preparar(db);monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    assert foto(cliente,c,sku='SKU1',categoria='PNC').status_code==201
    r=cliente.post(f'/api/operacion/recepciones/{c}/informes',json={'clave':'ampliado-con-fotos','tipo':'CORREO','formato':'envio-ampliado','ultimoVisto':None})
    assert r.status_code==409 and r.json()['detail']['codigo']=='EVIDENCIAS_PENDIENTES'
