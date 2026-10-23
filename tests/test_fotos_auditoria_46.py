"""Identidad estable de fotos y clasificación histórica al corregir cantidades."""
import re
from datetime import datetime,timezone
from sqlalchemy import select
from fastapi.testclient import TestClient
import pytest
from app.main import app
from app.db import engine,SessionLocal
from app.models import AppArchivo,AppArchivoIdentidad,AppCopiaDrive,AppEvidencia,AppEvento,AppRecepcion,AppEntrega,AppSku
from app.services import app_modelo as m,archivos,drive,fotos_identidad,operacion
from tests.test_operacion_desarrollo import foto
from tests.test_archivos_locales import PNG
import base64


def preparar(cliente,db,codigo='FOTOS46'):
    assert cliente.post('/api/app/recepciones',json={'codigo':codigo,'cliente':'VENTURA','bultos':2}).status_code==201
    m.guardar_packing_list(db,codigo,{'lineas':[{'linea':1,'sku':'030145933AC','cantidad':356}],
        'porSku':{'030145933AC':356},'unidades':356,'embarques':['RB654123','RB999']},'LISTA1')
    return codigo


def tomar(cliente,c,**datos):
    r=foto(cliente,c,sku='030145933AC',desdeSku=True,**datos)
    assert r.status_code==201,r.text
    return r.json()


def contar(db,c,n,ident,**datos):
    return m.registrar_conteo(db,c,'sup',{'id':ident,'sku':'030145933AC','cantidad':n,'pallet':'B01',**datos})


def test_nombre_tiene_recepcion_embarques_fecha_y_secuencia_y_guarda_original(cliente,db):
    c=preparar(cliente,db)
    uno=tomar(cliente,c,nombre='WhatsApp prueba.jpg',variante=1)
    dos=tomar(cliente,c,nombre='bulto-uuid.png',variante=2)
    assert re.fullmatch(r'FOTOS46_RB654123-RB999_\d{8}_00001.png',uno['nombre'])
    assert dos['nombre'].endswith('_00002.png')
    meta=db.get(AppArchivoIdentidad,uno['id']);assert meta.nombre_original=='WhatsApp prueba.jpg.png'
    assert meta.datos['embarques']==['RB654123','RB999']
    a=db.get(AppArchivo,uno['id']);a.creado_en=datetime(2026,10,19,2,tzinfo=timezone.utc)
    assert fotos_identidad.nombre(db,a)=='FOTOS46_RB654123-RB999_20261018_00001.png'
    repetida=tomar(cliente,c,nombre='otro-nombre.png',variante=1)
    assert repetida['id']==uno['id'] and db.query(AppArchivo).count()==2
    assert db.get(AppArchivoIdentidad,uno['id']).secuencia==1


def test_faltante_historico_no_se_reclasifica_al_corregir_356_con_una_pnc(cliente,db):
    c=preparar(cliente,db)
    antigua=tomar(cliente,c,variante=1,conteoPendiente=True)
    contar(db,c,355,'conteo-faltante-46',fotos=[antigua['url']])
    # La corrección hereda las fotos originales del evento compensado.
    from app.services.correcciones import corregir
    corregir(db,c,'conteo-faltante-46',{'id':'conteo-completo-pnc-46','contadoEsperado':355,'cantidad':356,
        'motivo':'Se encontró la unidad faltante con una unidad en mal estado',
        'incidencias':[{'tipo':'MAL_ESTADO','cantidad':1}]},'sup')
    nueva=tomar(cliente,c,variante=2)
    es={e.archivo_id:e.categoria for e in db.scalars(select(AppEvidencia).where(AppEvidencia.eliminado_en.is_(None)))}
    assert es=={antigua['id']:'FALTANTE',nueva['id']:'PNC'}
    s=db.scalar(select(AppSku));assert s.contado==356 and s.tiene_pnc
    assert db.query(AppArchivo).count()==2
    # Volver a seleccionar el archivo antiguo reutiliza su registro original.
    repetida=tomar(cliente,c,variante=1,conteoPendiente=True)
    assert repetida['id']==antigua['id'] and db.query(AppEvidencia).count()==2
    assert db.scalar(select(AppEvidencia).where(AppEvidencia.archivo_id==antigua['id'])).categoria=='FALTANTE'


def test_solo_foto_nueva_del_conteo_se_clasifica_una_vez(cliente,db):
    c=preparar(cliente,db);contar(db,c,355,'primer-conteo-46')
    nueva=tomar(cliente,c,variante=1,conteoPendiente=True)
    contar(db,c,1,'foto-nueva-pnc-46',fotos=[nueva['url']],incidencias=[{'tipo':'MAL_ESTADO','cantidad':1}])
    e=db.scalar(select(AppEvidencia));assert e.categoria=='PNC'
    meta=db.get(AppArchivoIdentidad,nueva['id']);assert not meta.datos['pendientesConteo']
    assert meta.datos['conteos'][e.id]=='foto-nueva-pnc-46'
    # Otro registro con el mismo enlace no vuelve a cambiar su contexto.
    operacion.actualizar_fotos_conteo(db,type('SKU',(),{'recepcion':c,'sku':'030145933AC','tiene_pnc':False,'estado':'COMPLETO','en_packing_list':True})(),[nueva['url']],'sup','otro-conteo-46')
    assert e.categoria=='PNC'


def test_pendiente_de_otro_autor_no_cambia_de_clasificacion(cliente,db):
    c=preparar(cliente,db);nueva=tomar(cliente,c,variante=1,conteoPendiente=True)
    contar(db,c,356,'conteo-otro-autor-46')
    s=db.scalar(select(AppSku));operacion.actualizar_fotos_conteo(db,s,[nueva['url']],'otro-usuario','evento-otro-46')
    e=db.scalar(select(AppEvidencia));assert e.categoria=='VALIDACION'
    assert db.get(AppArchivoIdentidad,nueva['id']).datos['pendientesConteo'][e.id]=='sup'


def test_bultos_y_cajas_tienen_carpetas_propias_con_recepcion_y_embarques(cliente,db):
    c=preparar(cliente,db);ruta='/api/operacion/recepciones/'+c
    unidades=cliente.post(ruta+'/bultos',json={'cantidad':2}).json()['unidades'];b=unidades[0]
    r=foto(cliente,c,unidadId=b['id'],categoria='RECEPCION',tipoEvidencia='EXTERIOR_BULTO');assert r.status_code==201,r.text
    j=db.get(AppCopiaDrive,r.json()['id']);assert j.datos['ruta']==['POR-ASIGNAR','BULTOS','Bulto01_FOTOS46_RB654123-RB999']
    caja=cliente.post(ruta+'/unidades',json={'tipo':'CAJA_MADRE','padreId':b['id'],'codigo':'CAJA-ABC'}).json()['unidades'][-1]
    f=foto(cliente,c,unidadId=caja['id'],categoria='RECEPCION',variante=2);assert f.status_code==201,f.text
    db.rollback();db.expire_all()
    assert db.get(AppCopiaDrive,f.json()['id']).datos['ruta']==['POR-ASIGNAR','BULTOS','Bulto01_FOTOS46_RB654123-RB999','Caja01_CAJA-ABC']


def test_organizar_es_previo_confirmado_idempotente_y_no_envia_correo(cliente,db):
    c=preparar(cliente,db);f=tomar(cliente,c,variante=1)
    a=db.get(AppArchivo,f['id']);a.drive_id='drive-imagen-original';j=db.get(AppCopiaDrive,a.id)
    j.estado='COPIADA';j.datos={**j.datos,'ruta':['GENERAL','030145933AC'],'rutasVinculadas':[]};db.commit()
    ruta='/api/operacion/recepciones/'+c+'/fotos'
    antes=db.query(AppArchivoIdentidad).count();p=cliente.get(ruta+'/organizacion');assert p.status_code==200,p.text
    assert db.query(AppArchivoIdentidad).count()==antes and p.json()['total']==1
    assert cliente.post(ruta+'/organizar',json={'confirmar':True,'huella':'obsoleta'}).status_code==409
    r=cliente.post(ruta+'/organizar',json={'confirmar':True,'huella':p.json()['huella']});assert r.status_code==200,r.text
    db.rollback();db.expire_all();assert db.get(AppArchivo,a.id).drive_id=='drive-imagen-original'
    # El nuevo nivel de embarque conserva el acceso a la carpeta del informe anterior.
    assert db.get(AppCopiaDrive,a.id).estado=='PENDIENTE' and db.get(AppCopiaDrive,a.id).datos['conservarAccesosPrevios'] is True
    assert db.query(AppArchivo).count()==1 and db.query(AppEntrega).count()==0
    assert db.scalar(select(AppRecepcion)).estado=='ABIERTA'


def test_organizar_rechaza_copia_activa_y_permisos_de_operario(cliente,db):
    c=preparar(cliente,db);f=tomar(cliente,c,variante=1);j=db.get(AppCopiaDrive,f['id']);j.estado='PROCESANDO';db.commit()
    ruta='/api/operacion/recepciones/'+c+'/fotos';p=cliente.get(ruta+'/organizacion').json()
    assert cliente.post(ruta+'/organizar',json={'confirmar':True,'huella':p['huella']}).status_code==409
    op=TestClient(app);op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    assert op.get(ruta+'/organizacion').status_code==403
    assert op.post(ruta+'/organizar',json={'confirmar':True,'huella':p['huella']}).status_code==403


def test_embarque_recien_cargado_actualiza_nombre_sin_cambiar_secuencia(cliente,db):
    c='ANTES-PACKING';assert cliente.post('/api/app/recepciones',json={'codigo':c}).status_code==201
    r=foto(cliente,c,categoria='RECEPCION',tipoEvidencia='PANORAMICA');assert r.status_code==201,r.text
    a=db.get(AppArchivo,r.json()['id']);assert '_SIN-EMBARQUE_' in a.nombre
    m.guardar_packing_list(db,c,{'lineas':[{'linea':1,'sku':'SKU1','cantidad':1}],'porSku':{'SKU1':1},'unidades':1,'embarques':['RB654123']},'LISTA')
    assert a.nombre.startswith('ANTES-PACKING_RB654123_') and a.nombre.endswith('_00001.png')
    assert db.get(AppArchivoIdentidad,a.id).datos['nombresAnteriores']


def test_nombres_largos_son_seguros_y_se_conserva_el_embarque_completo(cliente,db):
    c=preparar(cliente,db);r=db.get(AppRecepcion,c);r.embarques=['EMBARQUE/'+str(i)+' X'*35 for i in range(20)];db.commit()
    f=tomar(cliente,c,variante=1);assert len(f['nombre'])<190 and '/' not in f['nombre']
    assert len(db.get(AppArchivoIdentidad,f['id']).datos['embarques'])==20


@pytest.mark.skipif(engine.dialect.name!='mysql',reason='La secuencia simultánea necesita bloqueo real MySQL')
def test_cuatro_operarios_asignan_secuencias_distintas_sin_cruce(cliente,db):
    from concurrent.futures import ThreadPoolExecutor
    c=preparar(cliente,db)
    def subir(i):
        with SessionLocal() as s:
            s.scalar(select(AppRecepcion).where(AppRecepcion.codigo==c))  # lectura previa como autenticación HTTP
            m.obtener(s,c,bloquear=True)
            p={'base64':base64.b64encode(PNG+str(i).encode()).decode(),'nombre':'misma-foto.png','categoria':'RECEPCION','tipoEvidencia':'PANORAMICA'}
            a=archivos.guardar(s,c,'foto',p,'op'+str(i),confirmar=False)
            fotos_identidad.asegurar_archivo(s,a);operacion.vincular_evidencia(s,a,p,'op'+str(i),confirmar=False);drive.encolar(s,a);s.commit()
            return a.id
    with ThreadPoolExecutor(max_workers=4) as pool:ids=list(pool.map(subir,range(4)))
    db.expire_all();metas=list(db.scalars(select(AppArchivoIdentidad)))
    assert len(set(ids))==4 and sorted(x.secuencia for x in metas)==[1,2,3,4]


def test_puente_sin_nueva_capacidad_conserva_archivo_y_no_intenta_subir(cliente,db,monkeypatch):
    from app.services import entregas
    c=preparar(cliente,db);f=tomar(cliente,c,variante=1);drive._verificados.clear()
    monkeypatch.setattr(entregas,'configurado',lambda *a:True)
    acciones=[]
    def antiguo(accion,clave,datos):
        acciones.append(accion);return {'versionPuente':2,'capacidades':['fotosSkuSimples'],'remitente':'sup'}
    monkeypatch.setattr(entregas,'llamar',antiguo)
    assert drive.procesar_uno()
    db.expire_all();a=db.get(AppArchivo,f['id']);j=db.get(AppCopiaDrive,a.id)
    assert acciones==['estado'] and not a.drive_id and archivos.ruta(a).is_file()
    assert 'Servidor.gs' in j.error


def test_renombrar_legacy_conserva_id_fecha_original_y_secuencia_tras_reintento(cliente,db):
    c=preparar(cliente,db);f=tomar(cliente,c,variante=1)
    a=db.get(AppArchivo,f['id']);db.delete(db.get(AppArchivoIdentidad,a.id));a.nombre='IMG_20240705_151813.jpg';db.commit()
    ruta='/api/operacion/recepciones/'+c+'/fotos';p=cliente.get(ruta+'/organizacion').json()
    assert db.query(AppArchivoIdentidad).count()==0
    assert p['archivos'][0]['actual']=='IMG_20240705_151813.jpg'
    assert cliente.post(ruta+'/organizar',json={'confirmar':True,'huella':p['huella']}).status_code==200
    db.rollback();db.expire_all();meta=db.get(AppArchivoIdentidad,a.id);assert meta.nombre_original=='IMG_20240705_151813.jpg' and meta.secuencia==1
    p=cliente.get(ruta+'/organizacion').json()
    assert cliente.post(ruta+'/organizar',json={'confirmar':True,'huella':p['huella']}).status_code==200
    assert db.get(AppArchivoIdentidad,a.id).secuencia==1 and db.query(AppArchivo).count()==1


def test_editar_clasificacion_es_explicito_conserva_archivo_y_audita(cliente,db):
    c=preparar(cliente,db);contar(db,c,355,'conteo-falta-explicita-46');f=tomar(cliente,c,variante=1)
    e=db.scalar(select(AppEvidencia));ident=e.id
    r=cliente.put('/api/operacion/evidencias/'+f['id'],json={'evidenciaId':ident,'sku':'030145933AC',
        'categoria':'PNC','tipoEvidencia':'ITEM_NOVEDAD','protocolo':'GENERAL'})
    assert r.status_code==200,r.text
    db.rollback();db.expire_all();assert db.get(AppEvidencia,ident).eliminado_en
    assert db.scalar(select(AppEvidencia).where(AppEvidencia.eliminado_en.is_(None))).categoria=='PNC'
    assert db.query(AppArchivo).count()==1 and db.scalar(select(AppSku)).contado==355
    assert db.query(AppEvento).filter(AppEvento.motivo=='EVIDENCIA_CORREGIDA').count()==1


def test_foto_de_adicional_guardada_sin_conteo_no_queda_provisional(cliente,db):
    c=preparar(cliente,db)
    r=foto(cliente,c,sku='ADICIONAL46',desdeSku=True,registroAdicional=True,variante=9)
    assert r.status_code==201,r.text
    meta=db.get(AppArchivoIdentidad,r.json()['id'])
    assert not meta.datos.get('pendientesConteo')
    assert db.scalar(select(AppEvidencia)).categoria=='SOBRANTE'
    assert db.query(AppEvento).filter(AppEvento.tipo=='CONTEO').count()==0
