"""Recuperar las fotos guardadas antes de entregar, sin duplicarlas."""
import pytest
from sqlalchemy import select

from app.models import AppArchivo, AppCopiaDrive, AppEntrega, AppRecepcion, Operador, Rol
from app.security import hash_pin
from app.services import archivos, drive, entregas, integraciones, operacion
from tests.test_cierre_guiado import preparar
from tests.test_operacion_desarrollo import foto
from tests.test_integraciones_ui import admin


def puente(db):
    db.add(Operador(usuario='responsable-fotos',email='responsable@example.test',nombre='Responsable',
        rol=Rol.SUPERVISOR,pin_hash=hash_pin('prueba-responsable')));db.commit()
    integraciones.guardar_google(db,{'supervisor':'responsable@example.test',
        'url':'https://script.google.com/macros/s/puente-actual/exec','secreto':'prueba-no-real-'*3},'admin')
    operacion.guardar_config(db,{'correo':{'responsable':'responsable@example.test','permitirPersonal':True}},'admin')


def test_foto_pendiente_adopta_responsable_al_reintentar_sin_perder_autor(cliente,db,monkeypatch,tmp_path):
    from app import config
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path);monkeypatch.setattr(config,'DATA_DIR',tmp_path)
    drive._verificados.clear();ruta=preparar(db)
    f=foto(cliente,'CIERRE',sku='SKU1').json()
    db.rollback();db.expire_all();assert db.get(AppCopiaDrive,f['id']).usuario=='sup'
    puente(db);acciones=[]
    def llamar(accion,clave,datos):
        assert datos['usuario']=='responsable@example.test'
        acciones.append((accion,clave))
        if accion=='estado':return {'versionPuente':2,'remitente':'responsable@example.test'}
        return {'fileId':'foto-confirmada-drive','carpetaSkuUrl':'https://drive.google.com/drive/folders/sku'}
    monkeypatch.setattr(entregas,'llamar',llamar)
    assert cliente.post(ruta+'/drive/reintentar',json={}).status_code==200
    assert drive.procesar_uno()
    db.rollback();db.expire_all()
    assert db.query(AppArchivo).count()==1 and db.query(AppCopiaDrive).count()==1
    assert db.get(AppArchivo,f['id']).usuario=='sup'
    assert db.get(AppCopiaDrive,f['id']).usuario=='responsable@example.test'
    assert [a for a,_ in acciones]==['estado','archivo']
    assert len({clave for _,clave in acciones})==1
    assert cliente.get(ruta+'/pendientes-cierre').json()['sincronizacion']=={
        'guardadas':1,'copiadas':1,'pendientes':0,'procesando':0,'requierenAyuda':0}
    assert not (tmp_path/'app_archivos'/f['id']).exists()
    assert not db.query(AppEntrega).count()


def test_resumen_incluye_fotos_generales_finales_y_excluye_retiradas(cliente,db,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path);ruta=preparar(db)
    a=foto(cliente,'CIERRE',sku='SKU1',variante=1).json()
    b=foto(cliente,'CIERRE',tipoEvidencia='PANORAMICA',variante=2).json()
    c=foto(cliente,'CIERRE',tipoEvidencia='ESTADO_FINAL',categoria='RECEPCION',variante=3).json()
    retirada=foto(cliente,'CIERRE',variante=4).json()
    cliente.delete('/api/operacion/evidencias/'+retirada['id'])
    db.rollback();db.expire_all()
    db.get(AppArchivo,a['id']).drive_id='foto-confirmada'
    j=db.get(AppCopiaDrive,a['id']);j.estado='COPIADA';j.datos={**j.datos,'carpetaSkuUrl':'https://drive.google.com/drive/folders/sku'}
    db.get(AppCopiaDrive,b['id']).estado='PROCESANDO'
    db.get(AppCopiaDrive,c['id']).error='dato-tecnico-no-publico';db.commit()
    r=cliente.get(ruta+'/pendientes-cierre');s=r.json()['sincronizacion']
    assert s=={'guardadas':3,'copiadas':1,'pendientes':2,'procesando':1,'requierenAyuda':1}
    assert not r.json()['bloqueaCierre'] and r.json()['total']==0
    assert 'dato-tecnico' not in r.text
    assert cliente.get('/api/operacion/recepciones/cierre/drive').json()['sincronizacion']==s


def test_reintento_de_fotos_finales_no_reabre_recepcion_ni_envia(cliente,db,monkeypatch,tmp_path):
    from app.services import app_modelo as m
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path);ruta=preparar(db)
    m.cerrar_recepcion(db,'CIERRE','sup')
    f=foto(cliente,'CIERRE',tipoEvidencia='ESTADO_FINAL',categoria='RECEPCION').json()
    antes=cliente.get('/api/app/recepciones/CIERRE').json()
    r=cliente.post(ruta+'/drive/reintentar',json={});assert r.status_code==200,r.text
    assert r.json()['programadas']==1
    assert cliente.get('/api/app/recepciones/CIERRE').json()==antes
    db.rollback();db.expire_all()
    assert db.get(AppRecepcion,'CIERRE').estado=='CERRADA'
    assert db.get(AppCopiaDrive,f['id']).estado=='PENDIENTE'
    assert not db.query(AppEntrega).count()


def test_comprobar_url_editada_no_prueba_otro_despliegue(admin,db,monkeypatch):
    integraciones.guardar_google(db,{'supervisor':'responsable@example.test',
        'url':'https://script.google.com/macros/s/anterior/exec','secreto':'secreto-prueba-'*3},'admin')
    def prohibido(*a):pytest.fail('No debe consultar Google con una URL anterior')
    monkeypatch.setattr(entregas,'llamar',prohibido)
    datos={'supervisor':'responsable@example.test','url':'https://script.google.com/macros/s/nueva/exec'}
    for accion in ['probar','correo-prueba']:
        r=admin.post('/api/app/integraciones/google/'+accion,json=datos)
        assert r.status_code==409 and r.json()['detail']['codigo']=='PUENTE_SIN_GUARDAR'
    datos['url']='https://drive.google.com/drive/folders/carpeta-evidencias'
    assert admin.post('/api/app/integraciones/google/probar',json=datos).status_code==422


def test_google_404_indica_url_del_despliegue_sin_exponer_su_respuesta(db,monkeypatch):
    from app import config
    monkeypatch.setattr(config,'VAL_GOOGLE_PROXY_URL','https://script.google.com/macros/s/inactivo/exec')
    monkeypatch.setattr(config,'VAL_GOOGLE_PROXY_SECRET','clave-prueba-'*3)
    class Respuesta:
        status_code=404
        def json(self):pytest.fail('No interpretar como JSON una página de error')
    class Cliente:
        def __init__(self,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def post(self,*a,**kw):return Respuesta()
    monkeypatch.setattr(entregas.httpx,'Client',Cliente)
    with pytest.raises(RuntimeError,match='HTTP 404.*Guardar puente'):
        entregas.llamar('estado','a'*32,{'usuario':'responsable@example.test'})
