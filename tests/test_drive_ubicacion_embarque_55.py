"""Una foto copiada no acredita por sí sola la carpeta vigente del embarque."""
from sqlalchemy import select
from app.models import AppArchivo, AppCopiaDrive, AppEvidencia, AppEntrega, AppRecepcion
from app.services import drive, entregas, informes
from tests.test_fotos_embarques_54 import preparar
from tests.test_operacion_desarrollo import foto


def copiada(db,ident,*,antigua=False):
    db.rollback();db.expire_all()
    a=db.get(AppArchivo,ident);a.drive_id='misma-foto-55';a.drive_url='https://drive.google.com/file/d/misma-foto-55/view'
    j=db.get(AppCopiaDrive,ident);j.estado='COPIADA'
    e=db.scalar(select(AppEvidencia).where(AppEvidencia.archivo_id==ident))
    d={**j.datos,'vinculosPorEvidencia':{e.id:{'carpetaSkuUrl':'https://drive.google.com/drive/folders/anterior'}}}
    if antigua:
        d['ruta']=['PNC',e.sku]
        d['rutasVinculadas']=[{**v,'ruta':d['ruta'],'rutaSku':d['ruta']} for v in d['rutasVinculadas']]
    j.datos=d;db.commit()
    return e.id


def test_copiada_en_carpeta_anterior_pide_actualizar_y_no_publica_link_equivocado(cliente,db):
    c=preparar(cliente,db)
    f=foto(cliente,c,sku='SOLOA',categoria='PNC',origen='PRINCIPAL').json()
    copiada(db,f['id'],antigua=True)
    r=cliente.get('/api/operacion/recepciones/'+c+'/drive').json()
    assert r['sincronizacion']['copiadas']==0 and r['sincronizacion']['pendientes']==1
    assert r['organizacion']=={'sinEmbarque':0,'carpetasDesactualizadas':1}
    assert r['archivos'][0]['ubicaciones'][0]['rutaEsperada']==['RB-A','PNC','SOLOA']
    db.rollback()
    assert informes.metadatos(db,c)['carpetas']=={}
    db.rollback()
    p=cliente.get('/api/operacion/recepciones/'+c+'/pendientes-cierre').json()
    assert p['total']==1 and p['archivos'][0]['vinculos'][0]['estado']=='ACTUALIZAR_CARPETAS'
    p=cliente.get('/api/app/recepciones/'+c+'/imagenes').json()
    assert p['archivos'][0]['evidencias'][0]['carpetaDrive']==''


def test_actualizar_carpeta_cerrada_reusa_fileid_sin_binario_ni_correo(cliente,db,monkeypatch):
    c=preparar(cliente,db);drive._verificados.clear()
    f=foto(cliente,c,sku='SOLOA',categoria='PNC',origen='PRINCIPAL').json()
    copiada(db,f['id'],antigua=True)
    db.get(AppRecepcion,c).estado='CERRADA';db.commit()
    ruta='/api/operacion/recepciones/'+c
    p=cliente.get(ruta+'/fotos/organizacion').json()
    assert p['archivos'][0]['requiereActualizar'] is True
    r=cliente.post(ruta+'/fotos/organizar',json={'confirmar':True,'huella':p['huella'],'asignaciones':{}})
    assert r.status_code==200 and r.json()['programadas']==1,r.text
    llamadas=[]
    monkeypatch.setattr(entregas,'configurado',lambda *a:True)
    def google(accion,clave,d):
        if accion=='estado':return {'versionPuente':2,'capacidades':['fotosSkuSimples','fotosAuditables'],'remitente':d['usuario']}
        llamadas.append(d)
        assert d['fileId']=='misma-foto-55' and 'base64' not in d
        assert d['ruta']==['RB-A','PNC','SOLOA']
        return {'fileId':d['fileId'],'nombre':d['nombre'],
            'vinculosDrive':{'PNC|SOLOA':{'carpetaSkuUrl':'https://drive.google.com/drive/folders/RBA-SOLOA'}}}
    monkeypatch.setattr(entregas,'llamar',google)
    assert drive.procesar_uno() and len(llamadas)==1
    r=cliente.get(ruta+'/drive').json()
    assert r['sincronizacion']['copiadas']==1 and r['sincronizacion']['pendientes']==0
    assert r['organizacion']['carpetasDesactualizadas']==0
    db.rollback();db.expire_all()
    assert db.get(AppRecepcion,c).estado=='CERRADA'
    assert db.query(AppArchivo).count()==1 and db.query(AppEntrega).count()==0
    assert informes.metadatos(db,c)['carpetas']['SOLOA']==['https://drive.google.com/drive/folders/RBA-SOLOA']
    db.rollback()
    assert cliente.post(ruta+'/drive/reintentar',json={}).json()['programadas']==0
    assert not drive.procesar_uno()


def test_ambigua_no_se_confirma_por_estar_en_por_asignar_y_panoramica_general_si(cliente,db):
    c=preparar(cliente,db)
    f=foto(cliente,c,sku='COMUN',categoria='PNC',origen='PRINCIPAL').json()
    copiada(db,f['id'])
    general=foto(cliente,c,tipoEvidencia='PANORAMICA',categoria='RECEPCION',embarqueFoto='',variante=1).json()
    copiada(db,general['id'])
    r=cliente.get('/api/operacion/recepciones/'+c+'/drive').json()
    assert r['sincronizacion']['copiadas']==1 and r['sincronizacion']['pendientes']==1
    assert r['organizacion']['sinEmbarque']==1
    assert next(a for a in r['archivos'] if a['id']==f['id'])['ubicaciones'][0]['estado']=='ASIGNAR_EMBARQUE'
    db.rollback()
    assert informes.metadatos(db,c)['carpetas']=={}


def test_carpeta_de_otro_embarque_del_mismo_sku_no_se_acepta(cliente,db):
    c=preparar(cliente,db)
    f=foto(cliente,c,sku='COMUN',categoria='PNC',origen='PRINCIPAL',embarqueFoto='RB-A').json()
    copiada(db,f['id'])
    j=db.get(AppCopiaDrive,f['id']);j.datos={**j.datos,'ruta':['RB-B','PNC','COMUN'],
        'rutasVinculadas':[{**v,'ruta':['RB-B','PNC','COMUN']} for v in j.datos['rutasVinculadas']]};db.commit()
    r=cliente.get('/api/operacion/recepciones/'+c+'/drive').json()
    assert r['organizacion']['carpetasDesactualizadas']==1
    db.rollback()
    assert informes.metadatos(db,c)['carpetas']=={}


def test_entrega_anterior_espera_corregir_carpeta_antes_de_contactar_google(cliente,db,monkeypatch):
    from uuid import uuid4
    c=preparar(cliente,db)
    f=foto(cliente,c,sku='SOLOA',categoria='PNC',origen='PRINCIPAL').json()
    copiada(db,f['id'],antigua=True)
    e=AppEntrega(id=uuid4().hex,clave=uuid4().hex,recepcion=c,usuario='sup',estado='PENDIENTE',datos={'fotos':[f['id']],'informes':[]})
    db.add(e);db.get(AppRecepcion,c).estado='CERRADA';db.commit();ident=e.id
    def prohibido(*args,**kwargs):raise AssertionError('No debe enviar ni consultar Google antes de organizar el embarque')
    monkeypatch.setattr(entregas,'configurado',lambda *args:True)
    monkeypatch.setattr(entregas,'llamar',prohibido)
    assert entregas.procesar_uno()
    db.rollback();db.expire_all();e=db.get(AppEntrega,ident)
    assert e.estado=='PENDIENTE' and 'Organiza las fotos por embarque' in e.error
    assert db.get(AppRecepcion,c).estado=='CERRADA'
