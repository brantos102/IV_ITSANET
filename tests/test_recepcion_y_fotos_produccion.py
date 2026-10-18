"""Fallos observados en producción: formato protegido, archivos y recepción editable."""
import base64
import pytest
from sqlalchemy import select
from fastapi.testclient import TestClient
from app.main import app
from app.models import AppSku,AppLinea,AppArchivo,AppCopiaDrive,AppConfig,AppAuditoriaGeneral,Producto
from app.services import app_modelo as m,archivos,ajustes,entregas,drive
from tests.test_mejoras_operativas import preparar
from tests.test_operacion_desarrollo import foto
from tests.test_archivos_locales import PNG


def edicion(cliente,c):return cliente.get(f'/api/operacion/recepciones/{c}/edicion').json()


def test_edicion_concurrente_y_bultos_conservan_lineas(cliente,db):
    c=preparar(db);r=edicion(cliente,c)
    d={'version':r['versionEdicion'],'descripcion':'Revisión supervisor','embarques':['RB01','RB02'],'bultos':2}
    ruta=f'/api/operacion/recepciones/{c}/edicion'
    res=cliente.put(ruta,json=d);assert res.status_code==200,res.text
    assert res.json()['embarques']==['RB01','RB02'] and res.json()['bultos']==2
    assert cliente.put(ruta,json=d).status_code==409
    assert len(cliente.get(f'/api/app/recepciones/{c}/lineas').json())==1


@pytest.mark.parametrize('separar',[False,True])
def test_retirar_embarque_preserva_fuente_y_no_mezcla_otra_lista(cliente,db,separar):
    c=preparar(db,True);r=edicion(cliente,c)
    datos={'version':r['versionEdicion'],'motivo':'Embarque añadido por error','nuevaRecepcion':'SEPARADA' if separar else ''}
    res=cliente.post(f'/api/operacion/recepciones/{c}/embarques/A/retirar',json=datos);assert res.status_code==200,res.text
    actual=cliente.get(f'/api/app/recepciones/{c}').json();assert actual['origenes']==['B'] and actual['totales']['unidades']==3
    assert cliente.get(f'/api/app/recepciones/{c}/skus').json()[0]['esperado']==3
    if separar:
        nueva=cliente.get('/api/app/recepciones/SEPARADA').json();assert nueva['origenes']==['A'] and nueva['totales']['unidades']==3
        assert cliente.get('/api/app/recepciones/SEPARADA/lineas').json()[0]['sku']=='SKU1'
    db.rollback();db.expire_all()
    aud=db.scalar(select(AppAuditoriaGeneral).where(AppAuditoriaGeneral.accion.in_(['EMBARQUE_RETIRADO','EMBARQUE_SEPARADO'])))
    assert aud.datos['lineasOriginales'][0]['sku']=='SKU1'


def test_retirada_con_conteos_informa_sku_sin_borrar(cliente,db):
    c=preparar(db,True);m.registrar_conteo(db,c,'sup',{'id':'vigente','sku':'SKU1','origen':'A','cantidad':1,'pallet':'B01'})
    r=edicion(cliente,c)
    res=cliente.post(f'/api/operacion/recepciones/{c}/embarques/A/retirar',json={'version':r['versionEdicion'],'motivo':'Lista incorrecta'})
    assert res.status_code==409 and 'SKU1' in res.text and 'Bitácora' in res.text
    assert len(cliente.get(f'/api/app/recepciones/{c}/lineas').json())==2


def test_columnas_de_sku_no_se_pueden_sobrescribir_con_ok_depot(cliente,db):
    c=preparar(db);meta=cliente.get(f'/api/operacion/recepciones/{c}/informe-metadatos').json()
    ruta=f'/api/operacion/recepciones/{c}/columnas-informe'
    res=cliente.put(ruta,json={'origen':'A','version':meta['versionFormatos'],'columnas':{'depot':0}})
    assert res.status_code==422 and 'SKU' in res.text
    assert cliente.put(ruta,json={'origen':'A','version':meta['versionFormatos'],'columnas':{'depot':2}}).status_code==200


@pytest.mark.parametrize('pallet,estado',[('B02.1',200),('B02-B03',200),('B02.1-B03',200),('B02"',422),('B02/B03',422),('B_02',422)])
def test_validacion_pallet_preserva_guion_y_rechaza_caracteres(cliente,db,pallet,estado):
    c=preparar(db)
    res=cliente.post(f'/api/app/recepciones/{c}/conteos',json={'id':'pallet-regla','sku':'SKU1','cantidad':1,'pallet':pallet})
    assert res.status_code==estado,res.text
    if estado==200:assert res.json()['pallet']==pallet
    else:assert 'Pallet' in res.text


def test_foto_conteo_referencia_local_y_destino_pnc(cliente,db,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    c=preparar(db);f=foto(cliente,c,sku='SKU1',desdeSku=True).json()
    res=cliente.post(f'/api/app/recepciones/{c}/conteos',json={'id':'foto-conteo','sku':'SKU1','cantidad':6,'pallet':'B02','fotos':[f['url']],'incidencias':[{'tipo':'MAL_ESTADO','cantidad':1}]})
    assert res.status_code==200,res.text
    db.rollback();db.expire_all();j=db.get(AppCopiaDrive,f['id'])
    # Payload is rebuilt just before copying, so no stale pre-count classification.
    a=db.get(AppArchivo,f['id']);assert drive.descripcion(db,a)['ruta']==['PNC','SKU1']
    evento=next(e for e in cliente.get(f'/api/app/recepciones/{c}/eventos').json() if e['id']=='foto-conteo')
    assert evento['fotos']==[f['url']] and 'base64' not in str(evento)


def test_miniatura_privada_sin_google_publico_se_reutiliza_y_retirada_bloquea(cliente,db,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path);c=preparar(db);f=foto(cliente,c,sku='SKU1').json()
    db.rollback();db.expire_all();a=db.get(AppArchivo,f['id']);j=db.get(AppCopiaDrive,a.id)
    a.drive_id='foto-drive-123';j.estado='COPIADA';db.commit();archivos.ruta(a).unlink()
    llamadas=[]
    def puente(accion,clave,d):
        assert accion=='miniatura' and d['fileId']=='foto-drive-123';llamadas.append(accion)
        return {'base64':base64.b64encode(PNG).decode(),'tipo':'image/png'}
    monkeypatch.setattr(entregas,'llamar',puente)
    url=f['url']+'?miniatura=1'
    assert TestClient(app).get(url).status_code==401
    for _ in range(2):
        res=cliente.get(url);assert res.status_code==200 and res.content==PNG and 'private' in res.headers['cache-control']
    assert llamadas==['miniatura']
    assert cliente.delete('/api/operacion/evidencias/'+f['id']).status_code==200
    assert cliente.get(url).status_code==410


def test_catalogo_identifica_otro_cliente_sin_inventar_posiciones(cliente,db):
    db.add(Producto(sku='AJENO',cliente='OTRO CLIENTE',descripcion='De otro cliente',existe_depot=True));db.commit()
    r=cliente.get('/api/app/catalogo/AJENO?cliente=VENTURA');assert r.status_code==200,r.text
    d=r.json();assert d['cliente']=='OTRO CLIENTE' and d['otroCliente'] and d['existeDepot'] and not d['stockDisponible']


def test_permisos_supervisor_migran_una_vez_y_no_cambia_roles(db,operadores):
    f=AppConfig(clave='politicas',datos={'permisos':{'SUPERVISOR':{'asignarSupervisor':False}}});db.add(f);db.commit()
    ajustes.habilitar_supervision_inicial(db);assert all(ajustes.configuracion(db)['permisos']['SUPERVISOR'].values())
    d=dict(f.datos);d['permisos']={'SUPERVISOR':{'asignarSupervisor':False}};f.datos=d;db.commit()
    ajustes.habilitar_supervision_inicial(db);assert ajustes.configuracion(db)['permisos']['SUPERVISOR']['asignarSupervisor'] is False


def test_foto_adicional_previa_al_conteo_no_exige_crear_sku_ni_directorio_tipo(cliente,db,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path);c=preparar(db)
    res=foto(cliente,c,sku='NUEVO',desdeSku=True,conteoPendiente=True)
    assert res.status_code==201,res.text
    db.rollback();db.expire_all();a=db.get(AppArchivo,res.json()['id'])
    assert drive.descripcion(db,a)['ruta']==['SOBRANTE','NUEVO']
    assert not db.scalar(select(AppSku).where(AppSku.sku=='NUEVO'))


def test_editar_vinculo_resuelve_foto_de_embarque_exclusivo_sin_perder_archivo(cliente,db,monkeypatch,tmp_path):
    from app.models import AppEvidencia
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path);c=preparar(db,True)
    m.guardar_packing_list(db,c,{'lineas':[{'linea':1,'sku':'SKU2','cantidad':1}],'porSku':{'SKU2':1},'unidades':1},'C')
    f=foto(cliente,c,sku='SKU2',desdeSku=True).json();r=edicion(cliente,c)
    ruta=f'/api/operacion/recepciones/{c}/embarques/C/retirar'
    res=cliente.post(ruta,json={'version':r['versionEdicion'],'motivo':'Lista añadida por error'})
    assert res.status_code==409 and 'Editar vínculo' in res.text
    antes=cliente.get(f'/api/app/recepciones/{c}/imagenes?sku=SKU2').json()['archivos'][0]['evidencias'][0]
    res=cliente.put('/api/operacion/evidencias/'+f['id'],json={'evidenciaId':antes['id'],'sku':'SKU1','origen':'B','categoria':'VALIDACION','tipoEvidencia':'ADICIONAL','protocolo':'GENERAL'})
    assert res.status_code==200,res.text
    assert cliente.get(f'/api/app/recepciones/{c}/imagenes?sku=SKU2').json()['total']==0
    fotos=cliente.get(f'/api/app/recepciones/{c}/imagenes?sku=SKU1').json()['archivos'];assert fotos[0]['id']==f['id']
    db.rollback();db.expire_all()
    assert db.get(AppEvidencia,antes['id']).eliminado_en is not None
    assert db.query(AppArchivo).filter(AppArchivo.tipo=='foto').count()==1
    assert cliente.post(ruta,json={'version':r['versionEdicion'],'motivo':'Lista añadida por error'}).status_code==200
    assert cliente.get(f['url']).status_code==200


def test_editar_foto_copiada_reubica_mismo_id_y_rechaza_vinculo_viejo(cliente,db,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path);c=preparar(db);f=foto(cliente,c,sku='SKU1',desdeSku=True).json()
    meta=cliente.get(f'/api/app/recepciones/{c}/imagenes?sku=SKU1').json()['archivos'][0]['evidencias'][0]
    db.rollback();db.expire_all();a=db.get(AppArchivo,f['id']);j=db.get(AppCopiaDrive,a.id);a.drive_id='foto-id-original';j.estado='COPIADA';db.commit()
    cuerpo={'evidenciaId':meta['id'],'sku':'SKU1','categoria':'PNC','tipoEvidencia':'ITEM_NOVEDAD','protocolo':'GENERAL'}
    res=cliente.put('/api/operacion/evidencias/'+f['id'],json=cuerpo);assert res.status_code==200,res.text
    assert cliente.put('/api/operacion/evidencias/'+f['id'],json=cuerpo).status_code==409
    db.rollback();db.expire_all();assert db.get(AppArchivo,f['id']).drive_id=='foto-id-original'
    j=db.get(AppCopiaDrive,f['id']);assert j.estado=='PENDIENTE' and j.datos['accion']=='ubicar' and j.datos['ruta']==['PNC','SKU1']


def test_editar_foto_rechaza_sku_ajeno_y_operario(cliente,db,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path);c=preparar(db);f=foto(cliente,c,sku='SKU1').json()
    meta=cliente.get(f'/api/app/recepciones/{c}/imagenes?sku=SKU1').json()['archivos'][0]['evidencias'][0]
    cuerpo={'evidenciaId':meta['id'],'sku':'NO_EXISTE','categoria':'VALIDACION','tipoEvidencia':'ADICIONAL'}
    ruta='/api/operacion/evidencias/'+f['id'];res=cliente.put(ruta,json=cuerpo);assert res.status_code==422 and 'SKU' in res.text
    op=TestClient(app);op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'});assert op.put(ruta,json=cuerpo).status_code==403
    assert cliente.get(f'/api/app/recepciones/{c}/imagenes?sku=SKU1').json()['total']==1
