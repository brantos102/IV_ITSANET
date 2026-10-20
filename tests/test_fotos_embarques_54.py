"""Fotos separadas por embarque real, clasificación histórica y binario único."""
from sqlalchemy import select
import pytest
from app.db import engine, SessionLocal
from app.models import AppArchivo, AppArchivoIdentidad, AppCopiaDrive, AppEvidencia, AppEntrega, AppRecepcion
from app.services import app_modelo as m, drive, fotos_embarques, entregas
from tests.test_operacion_desarrollo import foto


def preparar(cliente, db, codigo='FOTOS54'):
    assert cliente.post('/api/app/recepciones', json={'codigo':codigo,'cliente':'VENTURA'}).status_code==201
    m.guardar_packing_list(db,codigo,{'lineas':[
        {'linea':1,'sku':'COMUN','cantidad':3,'embarque':'RB-A'},
        {'linea':2,'sku':'COMUN','cantidad':5,'embarque':'RB-B'},
        {'linea':3,'sku':'SOLOA','cantidad':1,'embarque':'RB-A'}],
        'porSku':{'COMUN':8,'SOLOA':1},'unidades':9,'embarques':['RB-A','RB-B']},'PRINCIPAL')
    return codigo


def test_un_packing_dos_embarques_separan_tres_categorias_y_no_alteran_conteos(cliente,db):
    c=preparar(cliente,db)
    p=cliente.get('/api/operacion/recepciones/'+c+'/fotos/embarques?sku=COMUN&origen=PRINCIPAL').json()
    assert p['candidatos']==['RB-A','RB-B'] and not p['sugerido'] and p['permiteGeneral']
    for n,(emb,cat) in enumerate((('RB-A','FALTANTE'),('RB-B','SOBRANTE'),('RB-B','PNC')),1):
        db.rollback()
        r=foto(cliente,c,variante=n,sku='COMUN',origen='PRINCIPAL',embarqueFoto=emb,categoria=cat,tipoEvidencia='ITEM_NOVEDAD')
        assert r.status_code==201,r.text
        db.rollback();db.expire_all()
        j=db.get(AppCopiaDrive,r.json()['id'])
        assert j.datos['ruta']==['EMBARQUES',emb,cat,'COMUN']
        assert j.datos['rutasVinculadas'][0]['embarque']==emb
    assert all(s['contado']==0 for s in m.leer_coleccion(db,c,'skus'))
    assert db.query(AppEntrega).count()==0


def test_destino_incompatible_no_guarda_y_foto_sin_destino_ambiguo_no_se_adivina(cliente,db):
    c=preparar(cliente,db)
    for emb in ('AJENO','RB-B','../RB-A'):
        r=foto(cliente,c,sku='SOLOA',embarqueFoto=emb)
        assert r.status_code==422,r.text
    assert db.query(AppArchivo).count()==0
    db.rollback()
    unica=foto(cliente,c,sku='SOLOA',categoria='PNC',variante=1);assert unica.status_code==201,unica.text
    db.rollback();db.expire_all()
    assert db.get(AppCopiaDrive,unica.json()['id']).datos['ruta']==['EMBARQUES','RB-A','PNC','SOLOA']
    db.rollback()
    antigua=foto(cliente,c,sku='COMUN',categoria='FALTANTE',variante=2);assert antigua.status_code==201,antigua.text
    db.rollback();db.expire_all()
    assert db.get(AppCopiaDrive,antigua.json()['id']).datos['ruta']==['EMBARQUES','POR-ASIGNAR','FALTANTE','COMUN']
    db.rollback()
    general=foto(cliente,c,categoria='RECEPCION',tipoEvidencia='PANORAMICA',embarqueFoto='',variante=3)
    assert general.status_code==201,general.text
    db.rollback();db.expire_all()
    assert db.get(AppCopiaDrive,general.json()['id']).datos['ruta']==['GENERALES','RECEPCION','PANORAMICA']


def test_reusar_la_misma_imagen_en_dos_embarques_guarda_dos_vinculos_un_binario(cliente,db):
    c=preparar(cliente,db)
    ids=[]
    for emb in ('RB-A','RB-B','RB-A','RB-B'):
        r=foto(cliente,c,sku='COMUN',desdeSku=True,embarqueFoto=emb,origen='PRINCIPAL',variante=1)
        assert r.status_code==201,r.text
        ids.append(r.json()['id'])
    assert len(set(ids))==1 and db.query(AppArchivo).count()==1 and db.query(AppEvidencia).count()==2
    es=list(db.scalars(select(AppEvidencia)))
    assert {fotos_embarques.asignado(db,e) for e in es}=={'RB-A','RB-B'}
    meta=db.get(AppArchivoIdentidad,ids[0]);assert len(meta.datos['embarquesPorEvidencia'])==2
    ingreso=cliente.get('/api/app/recepciones/'+c+'/imagenes').json()
    assert {e['embarque'] for e in ingreso['archivos'][0]['evidencias']}=={'RB-A','RB-B'}


def test_corregir_solo_embarque_audita_conserva_imagen_y_carpeta_anterior(cliente,db):
    c=preparar(cliente,db)
    f=foto(cliente,c,sku='COMUN',categoria='PNC',embarqueFoto='RB-A',origen='PRINCIPAL').json()
    e=db.scalar(select(AppEvidencia));vieja=e.id
    r=cliente.put('/api/operacion/evidencias/'+f['id'],json={'evidenciaId':e.id,'sku':'COMUN',
        'origen':'PRINCIPAL','embarqueFoto':'RB-B','categoria':'PNC','tipoEvidencia':'ADICIONAL','protocolo':'GENERAL'})
    assert r.status_code==200,r.text
    db.rollback();db.expire_all()
    assert db.get(AppEvidencia,vieja).eliminado_en
    actual=db.scalar(select(AppEvidencia).where(AppEvidencia.eliminado_en.is_(None)))
    assert fotos_embarques.asignado(db,actual)=='RB-B'
    assert db.get(AppArchivoIdentidad,f['id']).datos['embarquesPorEvidencia'][vieja]=='RB-A'
    assert db.query(AppArchivo).count()==1


def test_puente_instalado_confirma_carpeta_por_vinculo_sin_resubir_binario(cliente,db,monkeypatch):
    c=preparar(cliente,db);drive._verificados.clear()
    for emb in ('RB-A','RB-B'):
        f=foto(cliente,c,sku='COMUN',categoria='PNC',embarqueFoto=emb,origen='PRINCIPAL').json()
    llamadas=[]
    monkeypatch.setattr(entregas,'configurado',lambda *a:True)
    def google(accion,clave,p):
        llamadas.append((accion,p))
        if accion=='estado':return {'versionPuente':2,'capacidades':['fotosSkuSimples','fotosAuditables'],'remitente':p['usuario']}
        assert accion=='archivo'
        return {'fileId':'foto-original-drive','nombre':p['nombre'],'carpetaSkuUrl':'principal',
            'vinculosDrive':{v['categoria']+'|'+v['sku']:{'carpetaSkuUrl':'https://drive.google.com/'+v['embarque']} for v in p['rutasVinculadas']}}
    monkeypatch.setattr(entregas,'llamar',google)
    assert drive.procesar_uno()
    db.rollback();db.expire_all();j=db.get(AppCopiaDrive,f['id'])
    assert j.estado=='COPIADA' and db.get(AppArchivo,f['id']).drive_id=='foto-original-drive'
    assert sum('base64' in p for a,p in llamadas if a=='archivo')==1
    for e in db.scalars(select(AppEvidencia)):
        assert drive.carpeta_sku(j,e)=='https://drive.google.com/'+fotos_embarques.asignado(db,e)
    assert not drive.procesar_uno()


def test_foto_de_embarque_no_aparece_en_correo_del_otro_embarque(cliente,db):
    from app.services import agrupacion_correo as ag
    c=preparar(cliente,db)
    foto(cliente,c,sku='COMUN',categoria='FALTANTE',embarqueFoto='RB-A',origen='PRINCIPAL')
    fuente={k:m.leer_coleccion(db,c,k) for k in ('lineas','skus','eventos')}
    fuente['fotos']=drive.manifiesto(db,c)
    p=ag.vista(db,c,{'modo':'EMBARQUE'})
    config={'modo':'EMBARQUE','asignaciones':{},'repartos':{s['id']:s['propuesta'] for s in p['repartos']}}
    a=ag.filtrar(fuente,fuente['lineas'],ag.grupo_id('RB-A'),config)
    b=ag.filtrar(fuente,fuente['lineas'],ag.grupo_id('RB-B'),config)
    assert len(a['fotos'])==1 and not a['fotos'][0]['requiereRevision'] and b['fotos']==[]


def test_organizar_asigna_una_historica_cerrada_sin_reabrir_ni_reenviar(cliente,db):
    c=preparar(cliente,db)
    f=foto(cliente,c,sku='COMUN',categoria='FALTANTE',origen='PRINCIPAL').json()
    a=db.get(AppArchivo,f['id']);a.drive_id='drive-historica'
    j=db.get(AppCopiaDrive,f['id']);j.estado='COPIADA';j.datos={**j.datos,'ruta':['FALTANTE','COMUN']}
    db.get(AppRecepcion,c).estado='CERRADA';db.commit()
    ruta='/api/operacion/recepciones/'+c+'/fotos'
    p=cliente.get(ruta+'/organizacion').json();e=p['archivos'][0]['vinculos'][0]
    assert e['embarque'] is None
    assert cliente.post(ruta+'/organizar',json={'huella':p['huella'],'confirmar':True,'asignaciones':{e['id']:'AJENO'}}).status_code==422
    assert cliente.post(ruta+'/organizar',json={'huella':p['huella'],'confirmar':True,'asignaciones':{'evidencia-ajena':'RB-A'}}).status_code==422
    r=cliente.post(ruta+'/organizar',json={'huella':p['huella'],'confirmar':True,'asignaciones':{e['id']:'RB-B'}})
    assert r.status_code==200,r.text
    db.rollback();db.expire_all();j=db.get(AppCopiaDrive,f['id'])
    assert j.estado=='PENDIENTE' and j.datos['ruta']==['EMBARQUES','RB-B','FALTANTE','COMUN']
    assert j.datos['conservarAccesosPrevios'] is True
    assert db.get(AppArchivo,f['id']).drive_id=='drive-historica'
    assert db.get(AppRecepcion,c).estado=='CERRADA'
    assert db.query(AppArchivo).count()==1 and db.query(AppEvidencia).count()==1 and db.query(AppEntrega).count()==0
    assert cliente.post(ruta+'/organizar',json={'huella':p['huella'],'confirmar':True,'asignaciones':{e['id']:'RB-A'}}).status_code==409


def test_nombres_de_embarque_con_distintos_simbolos_no_comparten_carpeta(cliente,db):
    c=preparar(cliente,db);r=db.get(AppRecepcion,c);r.embarques=['RB/A','RB A'];db.commit()
    rutas=[]
    for i,emb in enumerate(r.embarques):
        db.rollback()
        f=foto(cliente,c,categoria='RECEPCION',tipoEvidencia='PANORAMICA',embarqueFoto=emb,variante=i).json()
        db.rollback();db.expire_all()
        ruta=db.get(AppCopiaDrive,f['id']).datos['ruta'];rutas.append(ruta)
        assert all('/' not in p for p in ruta)
    assert rutas[0]!=rutas[1]


def test_no_cambia_embarque_mientras_hay_un_correo_automatico_pendiente(cliente,db):
    from uuid import uuid4
    c=preparar(cliente,db)
    f=foto(cliente,c,sku='COMUN',categoria='PNC',origen='PRINCIPAL').json()
    db.add(AppEntrega(id=uuid4().hex,clave=uuid4().hex,recepcion=c,usuario='sup',estado='PENDIENTE',datos={}))
    db.get(AppRecepcion,c).estado='CERRADA';db.commit()
    ruta='/api/operacion/recepciones/'+c+'/fotos';p=cliente.get(ruta+'/organizacion').json()
    e=p['archivos'][0]['vinculos'][0]
    r=cliente.post(ruta+'/organizar',json={'huella':p['huella'],'confirmar':True,'asignaciones':{e['id']:'RB-A'}})
    assert r.status_code==409 and 'Entregas' in r.json()['detail']
    db.rollback();db.expire_all()
    assert fotos_embarques.asignado(db,db.get(AppEvidencia,e['id'])) is None


def test_otro_operario_agrega_destino_durante_copia_y_se_reprograma_con_su_embarque(cliente,db,monkeypatch):
    c=preparar(cliente,db);drive._verificados.clear()
    f=foto(cliente,c,sku='COMUN',categoria='PNC',embarqueFoto='RB-A',origen='PRINCIPAL').json()
    monkeypatch.setattr(entregas,'configurado',lambda *a:True)
    agregada=False
    def google(accion,clave,p):
        nonlocal agregada
        if accion=='estado':return {'versionPuente':2,'capacidades':['fotosSkuSimples','fotosAuditables'],'remitente':p['usuario']}
        if not agregada:
            agregada=True
            segunda=foto(cliente,c,sku='COMUN',categoria='PNC',embarqueFoto='RB-B',origen='PRINCIPAL')
            assert segunda.status_code==201 and segunda.json()['id']==f['id']
        return {'fileId':'foto-copia-concurrente','nombre':p['nombre'],'vinculosDrive':{}}
    monkeypatch.setattr(entregas,'llamar',google)
    assert drive.procesar_uno()
    db.rollback();db.expire_all();j=db.get(AppCopiaDrive,f['id'])
    assert j.estado=='PENDIENTE'
    assert {tuple(v['ruta']) for v in j.datos['rutasVinculadas']}=={
        ('EMBARQUES','RB-A','PNC','COMUN'),('EMBARQUES','RB-B','PNC','COMUN')}


@pytest.mark.skipif(engine.dialect.name!='mysql',reason='Requiere bloqueo real de recepción MySQL')
def test_dos_operarios_misma_foto_distinto_embarque_no_cruzan_sus_vinculos(cliente,db):
    import base64
    from concurrent.futures import ThreadPoolExecutor
    from app.services import archivos, operacion, fotos_identidad
    from tests.test_archivos_locales import PNG
    c=preparar(cliente,db)
    def subir(emb):
        with SessionLocal() as s:
            m.obtener(s,c,bloquear=True)
            datos={'base64':base64.b64encode(PNG).decode(),'nombre':'misma.png','sku':'COMUN',
                'origen':'PRINCIPAL','categoria':'PNC','embarqueFoto':emb}
            a=archivos.guardar(s,c,'foto',datos,emb,confirmar=False)
            fotos_identidad.asegurar_archivo(s,a)
            operacion.vincular_evidencia(s,a,datos,emb,confirmar=False)
            drive.encolar(s,a);s.commit();return a.id
    with ThreadPoolExecutor(max_workers=2) as ex:ids=list(ex.map(subir,['RB-A','RB-B']))
    db.rollback();db.expire_all()
    assert len(set(ids))==1 and db.query(AppArchivo).count()==1 and db.query(AppEvidencia).count()==2
    es=list(db.scalars(select(AppEvidencia)))
    assert {fotos_embarques.asignado(db,e) for e in es}=={'RB-A','RB-B'}


@pytest.mark.skipif(engine.dialect.name!='mysql',reason='Requiere snapshot REPEATABLE READ de MySQL')
def test_plan_confirmado_se_lee_actual_aunque_la_sesion_tenga_snapshot_previo(cliente,db):
    from app.models import AppConfig
    from app.services.correos_embarque import clave
    c=preparar(cliente,db)
    m.guardar_packing_list(db,c,{'lineas':[{'linea':1,'sku':'SINEMB','cantidad':1}],
        'porSku':{'SINEMB':1},'unidades':1},'OTRA')
    with SessionLocal() as lector:
        assert fotos_embarques.contexto(lector,c,'SINEMB')['candidatos']==['RB-A','RB-B']
        db.add(AppConfig(clave=clave(c),datos={'embarquesPorLinea':{'OTRA-1':'RB-C'}},usuario='sup'));db.commit()
        assert fotos_embarques.resolver(lector,c,{'sku':'SINEMB','origen':'OTRA','embarqueFoto':'RB-C'})=='RB-C'
