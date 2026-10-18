"""Carga de SKU sin menús de bultos, nombres cortos y destinatarios editables."""
import pytest
from sqlalchemy import select
from app.models import AppArchivo,AppCopiaDrive,AppEvidencia,AppEntrega
from app.services import app_modelo as m,archivos,drive,entregas
from app.services.instantaneas import expandir
from tests.test_operacion_desarrollo import foto
from tests.test_mejoras_operativas import preparar
from tests.test_recuperar_entrega import pendiente
from tests.test_remitente_responsable import correo

@pytest.mark.parametrize('cantidad,pnc,categoria',[(6,0,'VALIDACION'),(6,1,'PNC'),(5,0,'FALTANTE'),(7,0,'SOBRANTE')])
def test_fotos_sku_solo_en_su_carpeta_segun_estado(cliente,db,monkeypatch,tmp_path,cantidad,pnc,categoria):
    c=preparar(db);monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    m.registrar_conteo(db,c,'sup',{'id':'conteo-estado-sku','sku':'SKU1','cantidad':cantidad,'pallet':'P01','confirmarSobrante':True,
        'incidencias':[{'tipo':'MAL_ESTADO','cantidad':pnc}] if pnc else []})
    for i in range(2):
        r=foto(cliente,c,sku='SKU1',desdeSku=True,categoria='GENERAL',tipoEvidencia='EXTERIOR_BULTO',variante=i);assert r.status_code==201,r.text
        db.rollback();db.expire_all();j=db.get(AppCopiaDrive,r.json()['id'])
        assert j.datos['ruta']==(['SKU1'] if categoria=='VALIDACION' else [categoria,'SKU1'])
        assert j.datos['rutaSku']==j.datos['ruta'] and j.datos['nombre'].startswith('MEJORAS_SIN-EMBARQUE_') and j.datos['nombre'].endswith(f'_{i+1:05d}.png')
        e=db.scalar(select(AppEvidencia).where(AppEvidencia.archivo_id==r.json()['id']))
        assert e.categoria==categoria and e.tipo==('ADICIONAL' if categoria=='VALIDACION' else 'ITEM_NOVEDAD')
    manifest=drive.manifiesto(db,c)
    assert [f['nombreFinal'] for f in manifest]==[f['nombre'] for f in manifest]
    assert [f['nombreFinal'].rsplit('_',1)[1] for f in manifest]==['00001.png','00002.png']
    assert all('_de_' not in f['nombreFinal'] and '__' not in f['nombreFinal'] for f in manifest)


def test_sku_inexistente_no_carga_foto(cliente,db,monkeypatch,tmp_path):
    c=preparar(db);monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    assert foto(cliente,c,sku='NOEXISTE',desdeSku=True).status_code==422
    assert db.query(AppArchivo).count()==0


def test_reubicar_foto_antigua_renombra_sin_subir_otro_binario(cliente,db,monkeypatch,tmp_path):
    c=preparar(db);monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    r=foto(cliente,c,sku='SKU1',categoria='PNC');ident=r.json()['id']
    db.rollback();db.expire_all();a=db.get(AppArchivo,ident);j=db.get(AppCopiaDrive,ident)
    a.drive_id='foto-antigua-confirmada';j.estado='COPIADA';j.datos={**j.datos,'ruta':['PNC','SKU1','ADICIONAL'],'rutasVinculadas':[]};db.commit()
    archivos.ruta(a).unlink()
    assert drive.reintentar_pendientes(db,c,'sup')['programadas']==1
    monkeypatch.setattr(entregas,'configurado',lambda *a:True);monkeypatch.setattr(drive,'verificar_puente',lambda *a:None)
    llamadas=[]
    def google(accion,clave,d):
        assert accion=='archivo' and d['fileId']=='foto-antigua-confirmada' and 'base64' not in d
        assert d['nombre'].startswith('MEJORAS_SIN-EMBARQUE_') and d['nombre'].endswith('_00001.png') and d['ruta']==['PNC','SKU1'];llamadas.append(accion)
        return {'fileId':d['fileId'],'nombre':d['nombre'],'carpetaSkuUrl':'https://drive.google.com/drive/folders/sku1'}
    monkeypatch.setattr(entregas,'llamar',google)
    assert drive.procesar_uno();db.rollback();db.expire_all()
    assert db.get(AppArchivo,ident).drive_id=='foto-antigua-confirmada' and db.get(AppArchivo,ident).nombre.endswith('_00001.png')
    assert llamadas==['archivo']


def test_reenvio_permite_destinatarios_nuevos_con_mismos_documentos(cliente,db,pendiente,monkeypatch):
    db.rollback();db.expire_all();c,ident=pendiente;original=db.get(AppEntrega,ident);adjuntos=list(original.datos['informes']);skus=expandir(original.datos)['skus']
    anteriores=original.datos['destinatarios'];llamadas=[]
    def google(accion,clave,d):
        llamadas.append((accion,d));return {'exito':True,'versionPuente':2,'capacidades':['correoVerificado'],
            'remitente':'personal@example.test','fileId':'archivo-confirmado','enviadoA':d.get('destinatarios','')}
    monkeypatch.setattr(entregas,'llamar',google)
    r=cliente.post(f'/api/app/entregas/{ident}/solicitar',json={'motivo':'Supervisor corrigió destinatarios finales','confirmarNoEnviado':True,
        'remitenteConfirmado':'personal@example.test','destinatarios':'NUEVO@example.test, segundo@example.test, nuevo@example.test'})
    assert r.status_code==200,r.text
    assert r.json()['destinatarios']=='nuevo@example.test,segundo@example.test'
    db.rollback();db.expire_all();e=db.get(AppEntrega,ident)
    assert e.datos['informes']==adjuntos and expandir(e.datos)['skus']==skus
    assert e.datos['recuperaciones'][-1]['destinatariosAnteriores']==anteriores
    assert db.query(AppEntrega).count()==1
    assert entregas.procesar_uno() and not entregas.procesar_uno()
    assert [d['destinatarios'] for a,d in llamadas if a=='finalizar']==['nuevo@example.test,segundo@example.test']


@pytest.mark.parametrize('destinatarios',['','sin-correo','uno@example.test;otro@example.test'])
def test_destinatarios_invalidos_no_modifican_ni_envian(cliente,db,pendiente,monkeypatch,destinatarios):
    db.rollback();db.expire_all();_,ident=pendiente;antes=db.get(AppEntrega,ident).datos['destinatarios']
    monkeypatch.setattr(entregas,'llamar',lambda *a:pytest.fail('No debe enviar ni verificar con destinos inválidos'))
    r=cliente.post(f'/api/app/entregas/{ident}/solicitar',json={'motivo':'Revisar destinatarios de este informe','confirmarNoEnviado':True,
        'remitenteConfirmado':'personal@example.test','destinatarios':destinatarios})
    assert r.status_code==422
    db.rollback();db.expire_all();assert db.get(AppEntrega,ident).datos['destinatarios']==antes


def test_secuencia_del_sku_no_se_repite_al_cambiar_clasificacion(cliente,db,monkeypatch,tmp_path):
    c=preparar(db);monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    uno=foto(cliente,c,sku='SKU1',categoria='GENERAL',variante=1).json()
    dos=foto(cliente,c,sku='SKU1',desdeSku=True,variante=2).json()
    db.rollback();db.expire_all();a,b=[db.get(AppCopiaDrive,r['id']) for r in (uno,dos)]
    assert a.datos['ruta']==b.datos['ruta']==['SKU1']
    assert [j.datos['nombre'].rsplit('_',1)[1] for j in (a,b)]==['00001.png','00002.png']


def test_recuperar_fotos_con_cuenta_propia_pausa_correo_y_avisa_al_confirmarse(cliente,db,pendiente,monkeypatch):
    from app.services import integraciones
    from app.models import AppConfig,utcnow
    c,ident=pendiente
    f=foto(cliente,c,categoria='RECEPCION',tipoEvidencia='ESTADO_FINAL').json()
    db.rollback();db.expire_all();j=db.get(AppCopiaDrive,f['id']);j.estado='REVISION';j.usuario='responsable@example.test';j.error='SERVIDOR_HMAC no coincide'
    g=db.get(AppConfig,integraciones._clave_google('personal@example.test'));g.datos={**g.datos,'verificadoEn':m._iso(utcnow())};db.commit()
    llamadas=[]
    def verificar(accion,clave,d,conexion):
        llamadas.append(accion);assert accion=='estado' and d['usuario']=='personal@example.test'
        return {'remitente':d['usuario'],'versionPuente':2,'capacidades':['fotosSkuSimples','fotosAuditables']}
    monkeypatch.setattr(entregas,'llamar_conexion',verificar)
    res=cliente.post(f'/api/operacion/recepciones/{c}/drive/desde-mi-cuenta',json={})
    assert res.status_code==200 and res.json()['programadas']==1,res.text
    db.rollback();db.expire_all();e=db.get(AppEntrega,ident);a=db.get(AppArchivo,f['id'])
    assert e.estado=='REVISION' and e.datos['revisionMotivo']=='FOTOS_RECUPERADAS'
    assert drive.descripcion(db,a)['usuario']=='personal@example.test'
    assert not next(e for e in cliente.get('/api/app/entregas').json() if e['id']==ident)['confirmacionDisponible']
    def copiar(accion,clave,d):
        llamadas.append(accion);assert d['usuario']=='personal@example.test'
        if accion=='estado':return {'versionPuente':2,'remitente':d['usuario'],'capacidades':['fotosSkuSimples','fotosAuditables']}
        assert accion=='archivo'
        return {'fileId':'fotos-cuenta-propia','tipoArchivo':'foto','carpetaRecepcionUrl':'https://drive.google.com/drive/folders/recepcion'}
    monkeypatch.setattr(entregas,'llamar',copiar)
    assert drive.procesar_uno()
    fila=next(e for e in cliente.get('/api/app/entregas').json() if e['id']==ident)
    assert fila['confirmacionDisponible'] and fila['confirmarConCuenta']=='personal@example.test'
    assert not entregas.procesar_uno()  # No se envía hasta una confirmación nueva.
    assert set(llamadas)<= {'estado','archivo'}
