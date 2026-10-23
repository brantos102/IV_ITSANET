"""Avisos de operación reales, propios por usuario y sin alterar cantidades."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from fastapi.testclient import TestClient
from app.main import app
from app.models import AppArchivo,AppEvidencia,AppCopiaDrive,AppConfig,AppEvento,Producto
from app.services import app_modelo as m
from app.services.avisos_operativos import catalogo,registrar_catalogo
from tests.test_mejoras_operativas import preparar


def test_no_avisa_faltantes_de_skus_sin_revisar_y_marca_diferencia_provisional(cliente,db):
    c=preparar(db);ruta='/api/operacion/notificaciones'
    assert cliente.get(ruta).json()['avisos']==[]
    m.registrar_conteo(db,c,'op1',{'id':'aviso-parcial','sku':'SKU1','cantidad':2,'pallet':'A01'})
    d=cliente.get(ruta).json()['avisos'];assert len(d)==1 and d[0]['tipo']=='FALTANTE' and d[0]['cantidad']==4
    assert d[0]['provisional'] and d[0]['evidencias']['sinEvidencia']
    antes=m.leer_coleccion(db,c,'eventos')
    for _ in range(3):assert cliente.get(ruta).status_code==200
    assert m.leer_coleccion(db,c,'eventos')==antes


def test_pnc_distingue_imagen_generica_registrada_y_confirmada_en_drive(cliente,db):
    c=preparar(db);m.registrar_conteo(db,c,'op1',{'id':'aviso-pnc','sku':'SKU1','cantidad':6,'pallet':'A01','incidencias':[{'tipo':'MAL_ESTADO','cantidad':2}]})
    a=AppArchivo(id='a'*32,recepcion=c,tipo='foto',nombre='demo.jpg',mime='image/jpeg',sha256='1'*64,bytes=3)
    db.add(a);db.flush()
    e=AppEvidencia(id='b'*32,archivo_id=a.id,recepcion=c,sku='SKU1',categoria='VALIDACION',tipo='DETALLE_PRODUCTO',protocolo='RECEPCION',usuario='op1')
    db.add(e);db.commit()
    ruta='/api/operacion/notificaciones';n=cliente.get(ruta).json()['avisos'][0]
    assert n['tipo']=='PNC' and n['cantidad']==2 and n['evidencias']['sinEvidencia']
    e.categoria='PNC';db.commit();n=cliente.get(ruta).json()['avisos'][0]
    assert n['evidencias']=={'registradas':1,'confirmadasDrive':0,'pendientesDrive':1,'sinEvidencia':False}
    a.drive_id='imagen-demo';a.drive_url='https://drive.google.com/file/d/imagen-demo/view'
    db.add(AppCopiaDrive(archivo_id=a.id,recepcion=c,estado='COPIADA',datos={},usuario='op1'));db.commit()
    n=cliente.get(ruta).json()['avisos'][0];assert n['evidencias']['confirmadasDrive']==1 and not n['evidencias']['pendientesDrive']
    e.eliminado_en=datetime.now(timezone.utc);db.commit()
    assert cliente.get(ruta).json()['avisos'][0]['evidencias']['sinEvidencia']


def test_lectura_es_individual_y_cambio_real_vuelve_a_avisar(cliente,db):
    c=preparar(db);m.registrar_conteo(db,c,'op1',{'id':'aviso-sobra','sku':'SKU1','cantidad':7,'pallet':'A01','confirmarSobrante':True})
    ruta='/api/operacion/notificaciones';aviso=cliente.get(ruta).json()['avisos'][0]
    assert cliente.post(ruta+'/leidas',json={'avisos':[aviso]}).status_code==200
    assert cliente.get(ruta).json()['avisos'][0]['leido']
    op=TestClient(app);op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    assert not op.get(ruta,params={'recepcion':c}).json()['avisos'][0]['leido']
    assert op.get(ruta).json()['avisos']==[]
    m.registrar_conteo(db,c,'op2',{'id':'aviso-sobra2','sku':'SKU1','cantidad':1,'pallet':'A02','confirmarSobrante':True})
    assert not cliente.get(ruta).json()['avisos'][0]['leido']
    assert cliente.post(ruta+'/leidas',json={'avisos':[{'id':'x','revision':'y'}]}).status_code==422


def test_catalogo_exige_carga_completa_de_jornada_ecuador_no_lookup_reciente(cliente,db):
    preparar(db);ahora=datetime(2026,10,23,5,20,tzinfo=timezone.utc)
    db.add(Producto(sku='BUSCADO',cliente='VENTURA',origen='API',actualizado_en=ahora));db.commit()
    assert catalogo(db,ahora)['requiereActualizacion']
    registrar_catalogo(db,['VENTURA'],'API',{'VENTURA':300},ahora);db.commit()
    assert not catalogo(db,ahora)['requiereActualizacion']
    assert catalogo(db,ahora+timedelta(days=1))['requiereActualizacion']
    assert not catalogo(db,ahora+timedelta(hours=3))['requiereActualizacion']
    assert catalogo(db,ahora)['dia']=='2026-10-23'


def test_catalogo_no_oculta_que_otro_cliente_sigue_desactualizado(cliente,db):
    preparar(db);m.crear_recepcion(db,{'codigo':'AVISO-OTRO','cliente':'OTRO'},'sup')
    ahora=datetime.now(timezone.utc);registrar_catalogo(db,['VENTURA'],'MAESTRO',{'VENTURA':10},ahora);db.commit()
    r=catalogo(db,ahora);assert r['requiereActualizacion'] and r['clientesPendientes']==['OTRO']


def test_sin_sesion_no_se_ven_avisos_ni_se_marcan(cliente,db):
    no=TestClient(app)
    assert no.get('/api/operacion/notificaciones').status_code==401
    assert no.post('/api/operacion/notificaciones/leidas',json={'avisos':[]}).status_code==401


def test_confirmacion_global_no_oculta_cliente_especifico_sin_actualizar(cliente,db):
    preparar(db);m.crear_recepcion(db,{'codigo':'AVISO-B','cliente':'OTRO'},'sup')
    ahora=datetime.now(timezone.utc)
    registrar_catalogo(db,['VENTURA'],'API',{'VENTURA':10},ahora)
    registrar_catalogo(db,['OTRO'],'API',{'OTRO':10},ahora-timedelta(days=1))
    db.add(AppConfig(clave='catalogo:actualizacion-compartida',datos={'alcanceVigente':'TODOS',
        'actualizadoEn':ahora.isoformat(),'resultado':{'productos':10,'errores':[]}}));db.commit()
    assert catalogo(db,ahora)['clientesPendientes']==['OTRO']


def test_adicional_fuera_de_packing_no_se_notifica_como_sobrante(cliente,db):
    c=preparar(db);m.registrar_conteo(db,c,'op1',{'id':'aviso-extra','sku':'EXTRA65','cantidad':3,'pallet':'A02','motivo':'Producto fuera del documento','confirmarSobrante':True})
    avisos=cliente.get('/api/operacion/notificaciones').json()['avisos']
    assert len(avisos)==1 and avisos[0]['tipo']=='ADICIONAL' and avisos[0]['cantidad']==3


def test_filtro_pnc_antes_del_limite_no_oculta_incidencia_antigua(cliente,db):
    from app.models import AppSku
    c=preparar(db);m.registrar_conteo(db,c,'op1',{'id':'pnc-antigua65','sku':'SKU1','cantidad':6,'pallet':'A01','incidencias':[{'tipo':'MAL_ESTADO','cantidad':1}]})
    ahora=datetime.now(timezone.utc)
    for i in range(6):
        db.add(AppSku(recepcion=c,sku='RECIENTE'+str(i),esperado=10,contado=2,verificado=True,estado='FALTANTE',actualizado_en=ahora+timedelta(seconds=i)))
    db.commit()
    ruta='/api/operacion/notificaciones'
    assert len(cliente.get(ruta,params={'limite':2}).json()['avisos'])==2
    filtrado=cliente.get(ruta,params={'limite':2,'tipo':'PNC'}).json()
    assert len(filtrado['avisos'])==1 and filtrado['avisos'][0]['sku']=='SKU1'
    sin_foto=cliente.get(ruta,params={'tipo':'SIN_FOTO'}).json()['avisos']
    assert all(a['evidencias']['sinEvidencia'] for a in sin_foto)
    assert cliente.get(ruta,params={'tipo':'INVALIDO'}).status_code==422
