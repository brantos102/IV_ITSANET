"""Datos operativos y enlaces corresponden al embarque revisado, sin reenvíos."""
from sqlalchemy import select
from app.models import AppArchivo, AppCopiaDrive, AppEvidencia, AppEntrega
from app.services import app_modelo as m, informes
from tests.test_remitente_responsable import correo
from tests.test_agrupacion_embarques_53 import multi, plan
from tests.test_operacion_desarrollo import foto


def guardar_plan(cliente,c,**cambios):
    ruta,p,d=plan(cliente,c,**cambios)
    r=cliente.put(ruta,json=d);assert r.status_code==200,r.text
    return p


def test_correo_datos_contenedor_fecha_y_ubicacion_editables_por_embarque(cliente,db,multi):
    p=guardar_plan(cliente,multi);ga,gb=[g['id'] for g in p['grupos']]
    ruta='/api/operacion/recepciones/'+multi+'/correo'
    v=cliente.get(ruta,params={'origen':ga}).json()
    campos={**v['campos'],'contenedor':'C1','tipoContenedor':'1x40','fechaOperacion':'2026-01-26',
        'palletsTotal':'48','ubicacion':'CALLEKL','palletDesde':'A01','palletHasta':'A09',
        'condicionUbicacion':'Hasta finalizar el contenedor.'}
    r=cliente.put(ruta,json={'version':v['version'],'origen':ga,'campos':campos});assert r.status_code==200,r.text
    h=r.json()['html'];assert all(t in h for t in ('C1','Pallets: 48','1x40','lunes, 26 de enero de 2026','CALLEKL','A01','A09'))
    otro=cliente.get(ruta,params={'origen':gb}).json()
    assert 'CALLEKL' not in otro['html'] and 'C1' not in otro['html']
    for k,valor in (('fechaOperacion','2026-02-30'),('palletsTotal','-1'),('palletsTotal','²')):
        v=cliente.get(ruta,params={'origen':ga}).json()
        assert cliente.put(ruta,json={'version':v['version'],'origen':ga,'campos':{**v['campos'],k:valor}}).status_code==422
    assert db.query(AppEntrega).count()==0


def test_hojas_conservan_links_sku_y_correo_no_enumera_sus_carpetas(cliente,db,multi):
    m.registrar_conteo(db,multi,'sup',{'id':'extra55','sku':'EXTRA55','cantidad':2,'pallet':'A01',
        'origen':'PRINCIPAL','motivo':'Fuera de packing list','confirmarSobrante':True})
    ruta,p,d=plan(cliente,multi)
    ga,gb=[g['id'] for g in p['grupos']];d['asignaciones']={'EXTRA55':ga}
    assert cliente.put(ruta,json=d).status_code==200
    esperados={}
    for i,(sku,emb) in enumerate((('MISMO','EMB-A'),('MISMO','EMB-B'),('EXTRA55','EMB-A'))):
        db.rollback()
        f=foto(cliente,multi,sku=sku,origen='PRINCIPAL',embarqueFoto=emb,categoria='SOBRANTE',variante=i).json()
        db.rollback();db.expire_all()
        a=db.get(AppArchivo,f['id']);a.drive_id='drive55-'+str(i);a.drive_url='https://drive.google.com/file/d/'+a.drive_id+'/view'
        e=db.scalar(select(AppEvidencia).where(AppEvidencia.archivo_id==a.id))
        url='https://drive.google.com/drive/folders/'+emb+'-'+sku
        j=db.get(AppCopiaDrive,a.id);j.estado='COPIADA';j.datos={**j.datos,'vinculosPorEvidencia':{e.id:{'carpetaSkuUrl':url,'carpeta':url}}}
        db.commit();esperados[(sku,emb)]=url
    db.rollback();meta=informes.metadatos(db,multi)
    assert meta['carpetasPorEmbarque']['EMB-A']['carpetas']['EXTRA55']==[esperados['EXTRA55','EMB-A']]
    assert 'EXTRA55' not in meta['carpetasPorEmbarque']['EMB-B']['carpetas']
    db.rollback()
    q='/api/operacion/recepciones/'+multi+'/correo'
    a=cliente.get(q,params={'origen':ga}).json();b=cliente.get(q,params={'origen':gb}).json()
    # El correo usa carpetas contenedoras; el Excel conserva el enlace directo por SKU.
    assert all(url not in a['html'] for url in esperados.values())
    assert all(url not in b['html'] for url in esperados.values())
    assert 'EXTRA55' not in b['html']


def test_sku_compartido_no_copia_novedad_o_pallet_inicial_entre_embarques(cliente,db,multi):
    m.registrar_conteo(db,multi,'sup',{'id':'nota55','sku':'MISMO','cantidad':0,'pallet':'A01',
        'observacion':'ESTA NOTA REQUIERE ASIGNACION AL EMBARQUE CORRECTO'})
    _,p,d=plan(cliente,multi)
    for reparto in p['repartos']:
        assert all(x['observacion']=='' and x['pallets']=='' for x in reparto['propuesta'].values())
    ruta='/api/operacion/recepciones/'+multi+'/correos-embarques'
    actual=cliente.get(ruta).json()
    assert cliente.put(ruta,json={'version':actual['version'],'modo':'PACKING_LIST','asignaciones':{},'embarquesPorLinea':{},'repartos':{}}).status_code==422
