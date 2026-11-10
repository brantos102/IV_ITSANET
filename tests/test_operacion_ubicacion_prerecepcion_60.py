"""Ubicación, pallet físico y prerecepción sin alterar cantidades ni originales."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.models import AppEvento,AppArchivoIdentidad,AppRecepcion
from app.services import app_modelo as m, informes
from tests.test_mejoras_operativas import preparar
from tests.test_operacion_desarrollo import foto


def conteo(db,codigo,**campos):
    return m.registrar_conteo(db,codigo,'op1',{'id':'conteo-60','sku':'SKU1','cantidad':4,'pallet':'B04',**campos})


def test_operario_asigna_posicion_sin_contar_y_con_historia_e_informe_vigente(cliente,db):
    c=preparar(db);conteo(db,c);r=db.get(AppRecepcion,c);antes=informes.huella_contenido(db,r);db.rollback()
    op=TestClient(app);op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    ruta=f'/api/app/recepciones/{c}/eventos/conteo-60/posicion'
    d={'posicionAnterior':'','posicionReal':'callekl'}
    res=op.put(ruta,json=d);assert res.status_code==200,res.text
    assert res.json()['posicionReal']=='CALLEKL'
    assert op.put(ruta,json=d).json()['sinCambios']
    assert op.put(ruta,json={**d,'posicionReal':'PISO2'}).status_code==409
    db.rollback();db.expire_all()
    e=db.get(AppEvento,'conteo-60');assert float(e.cantidad)==4 and e.usuario=='op1' and e.pallet=='B04'
    assert m.leer_coleccion(db,c,'skus')[0]['contado']==4
    assert db.query(AppEvento).filter_by(recepcion=c,motivo='POSICION_FINAL_ASIGNADA').count()==1
    assert informes.huella_contenido(db,db.get(AppRecepcion,c))!=antes


@pytest.mark.parametrize('caso',['ajeno','cerrado','anulado','sin-pallet','sin-unidades'])
def test_ubicacion_rechaza_conteos_no_vigentes(cliente,db,caso):
    c=preparar(db)
    if caso=='sin-pallet':
        e=AppEvento(id='conteo-60',recepcion=c,tipo='CONTEO',sku='SKU1',cantidad=4,pallet=None,usuario='op1');db.add(e);db.commit()
    else:conteo(db,c,cantidad=0 if caso=='sin-unidades' else 4)
    if caso=='cerrado':db.get(AppRecepcion,c).estado='CERRADA';db.commit()
    if caso=='anulado':m.anular_conteo(db,c,'sup','conteo-60','Revisión física')
    q=f'/api/app/recepciones/{c if caso!="ajeno" else "OTRA"}/eventos/conteo-60/posicion'
    assert cliente.put(q,json={'posicionReal':'A-01','posicionAnterior':''}).status_code in (404,409,422)


def test_novedad_con_pallet_y_foto_mantiene_unidades_y_clasificacion(cliente,db):
    c=preparar(db)
    r=cliente.post(f'/api/app/recepciones/{c}/conteos',json={'id':'conteo-60','sku':'SKU1','cantidad':4,'pallet':'B04',
        'incidencias':[{'tipo':'MAL_ESTADO','cantidad':1,'pallet':'B04'}]})
    assert r.status_code==200,r.text
    assert r.json()['cantidadPnc']==1 and r.json()['contado']==4
    assert r.json()['incidencias'][0]['pallets']=={'B04':1}
    a=foto(cliente,c,sku='SKU1',desdeSku=True,palletEvidencia='B04').json()
    b=foto(cliente,c,sku='SKU1',desdeSku=True,palletEvidencia='B04').json();assert a['id']==b['id']
    imgs=cliente.get(f'/api/app/recepciones/{c}/imagenes?sku=SKU1').json()['archivos']
    assert len(imgs)==1 and imgs[0]['evidencias'][0]['pallet']=='B04' and imgs[0]['evidencias'][0]['categoria']=='PNC'
    correo=cliente.get(f'/api/operacion/recepciones/{c}/correo').json();assert 'Pallet B04' in correo['html']
    por_lista=cliente.get(f'/api/operacion/recepciones/{c}/correo?origen=A');assert por_lista.status_code==200,por_lista.text
    assert 'Pallet B04' in por_lista.json()['html']


@pytest.mark.parametrize('pallet',['B05','B04-B05','<B04>'])
def test_pallet_de_incidencia_no_se_cruza_con_otro_conteo(cliente,db,pallet):
    c=preparar(db);r=cliente.post(f'/api/app/recepciones/{c}/conteos',json={'id':'conteo-60','sku':'SKU1','cantidad':4,'pallet':'B04','incidencias':[{'tipo':'MAL_ESTADO','cantidad':1,'pallet':pallet}]})
    assert r.status_code==422,r.text
    assert cliente.get(f'/api/app/recepciones/{c}/skus').json()[0]['contado']==0


def test_incidencia_identifica_pallet_individual_dentro_de_conteo_agrupado(cliente,db):
    c=preparar(db);r=cliente.post(f'/api/app/recepciones/{c}/conteos',json={'id':'conteo-60','sku':'SKU1','cantidad':4,'pallet':'B04-B05','incidencias':[{'tipo':'MAL_ESTADO','cantidad':1,'pallet':'B05'}]})
    assert r.status_code==200,r.text
    assert r.json()['incidencias'][0]['pallets']=={'B05':1}


def test_prerecepcion_sin_sku_ni_bulto_aparece_en_correo_y_galeria(cliente,db):
    c=preparar(db)
    r=foto(cliente,c,tipoEvidencia='PRERECEPCION',categoria='RECEPCION');assert r.status_code==201,r.text
    f=cliente.get(f'/api/app/recepciones/{c}/imagenes?tipoEvidencia=PRERECEPCION').json()['archivos'][0]
    assert f['evidencias'][0]['tipo']=='PRERECEPCION' and f['evidencias'][0]['unidadId'] is None
    v=cliente.get(f'/api/operacion/recepciones/{c}/correo').json()
    assert r.json()['id'] in v['fotosSeleccionadas'] and 'Prerecepción · descarga del contenedor' in v['html']
    assert next(a for a in v['fotos'] if a['id']==r.json()['id'])['tipoEvidencia']=='PRERECEPCION'


def test_prerecepcion_no_se_registra_como_foto_sku(cliente,db):
    c=preparar(db);r=foto(cliente,c,sku='SKU1',tipoEvidencia='PRERECEPCION',categoria='RECEPCION')
    assert r.status_code==422


def test_posicion_simultanea_no_sobrescribe_otra_persona(cliente,db):
    if db.bind.dialect.name!='mysql':pytest.skip('Bloqueo real de producción: requiere MySQL de pruebas.')
    import threading
    from app.db import SessionLocal
    from app.services.ubicacion_final import asignar
    from fastapi import HTTPException
    c=preparar(db);conteo(db,c);barrera=threading.Barrier(2);salidas=[]
    def escribir(posicion):
        with SessionLocal() as s:
            barrera.wait(timeout=10)
            try:salidas.append(asignar(s,c,'conteo-60',{'posicionReal':posicion,'posicionAnterior':''},posicion))
            except HTTPException as e:s.rollback();salidas.append(e.status_code)
    hs=[threading.Thread(target=escribir,args=(p,)) for p in ('CALLEKL','PISO2')]
    for h in hs:h.start()
    for h in hs:h.join(timeout=15)
    assert not any(h.is_alive() for h in hs)
    assert len([x for x in salidas if isinstance(x,dict)])==1 and 409 in salidas
    db.expire_all();assert db.get(AppEvento,'conteo-60').cantidad==4
    assert db.query(AppEvento).filter_by(recepcion=c,motivo='POSICION_FINAL_ASIGNADA').count()==1


def test_misma_foto_en_dos_pallets_conserva_ambos_vinculos_sin_duplicar_archivo(cliente,db):
    from app.services import drive
    from app.models import AppArchivo
    c=preparar(db)
    for pallet in ('B01','B02'):
        conteo(db,c,id='conteo-'+pallet,cantidad=2,pallet=pallet,incidencias=[{'tipo':'MAL_ESTADO','cantidad':1,'pallet':pallet}])
    a=foto(cliente,c,sku='SKU1',desdeSku=True,palletEvidencia='B01').json()
    b=foto(cliente,c,sku='SKU1',desdeSku=True,palletEvidencia='B02').json()
    assert a['id']==b['id']
    vistas=cliente.get(f'/api/app/recepciones/{c}/imagenes?sku=SKU1').json()['archivos']
    assert len(vistas)==1 and {e['pallet'] for e in vistas[0]['evidencias']}=={'B01','B02'}
    db.rollback();db.expire_all()
    descripcion=drive.descripcion(db,db.get(AppArchivo,a['id']))
    assert {v['pallet'] for v in descripcion['rutasVinculadas']}=={'B01','B02'}
