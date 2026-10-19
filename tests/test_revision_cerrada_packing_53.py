"""Recepción histórica cerrada: borradores separados sin reabrir ni reenviar."""
import base64
import io
from uuid import uuid4

import pytest
from openpyxl import Workbook
from sqlalchemy import select,func
from app.models import AppEntrega,AppInforme,AppRecepcion,AppEvento
from app.services import app_modelo as m,archivos,correo_redactado as correo
from app.services.instantaneas import compactar

CODIGO='ISZ-RAISZ04520-16-10-2026'
ORIGENES=['PRINCIPAL','RAISZ04520']
RUTA='/api/operacion/recepciones/'+CODIGO


def excel(origen):
    w=Workbook();w.active.append(['ITEM','Cantidad','Embarque']);w.active.append(['SKU-'+origen,3,origen]);b=io.BytesIO();w.save(b)
    return base64.b64encode(b.getvalue()).decode()


@pytest.fixture
def historica(cliente,db,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    m.crear_recepcion(db,{'codigo':CODIGO,'cliente':'VENTURA'},'sup')
    for i,origen in enumerate(ORIGENES):
        sku='SKU-'+origen
        m.guardar_packing_list(db,CODIGO,{'lineas':[{'linea':1,'sku':sku,'cantidad':3,'cruda':[sku,3]}],
            'porSku':{sku:3},'unidades':3,'columnas':{'sku':0,'cantidad':1},'encabezados':['ITEM','Cantidad']},origen)
        m.registrar_conteo(db,CODIGO,'sup',{'id':'previo53-'+origen,'sku':sku,'cantidad':4 if i==0 else 2,
            'origen':origen,'pallet':'B01' if i==0 else 'B02','confirmarSobrante':True})
    v=cliente.get(RUTA+'/correo').json()
    v=cliente.put(RUTA+'/correo',json={'version':v['version'],'campos':{**v['campos'],'destinatarios':'ejecutivo@example.test'}}).json()
    # Simula una entrega producida antes de la separación por packing list.
    a=archivos.guardar(db,CODIGO,'informe',{'nombre':'informe-agrupado-original.xlsx','base64':excel('AGRUPADO')},'sup')
    skus=m.leer_coleccion(db,CODIGO,'skus');lineas=m.leer_coleccion(db,CODIGO,'lineas');eventos=m.leer_coleccion(db,CODIGO,'eventos')
    cierre=m.cerrar_recepcion(db,CODIGO,'sup',confirmar=False)
    e=AppEntrega(id=uuid4().hex,recepcion=CODIGO,usuario='sup',clave=uuid4().hex,estado='ENTREGADA',datos=compactar({
        'recepcion':cierre,'skus':skus,'lineas':lineas,'eventos':eventos,'informes':[a.id],'fotos':[],
        'destinatarios':'ejecutivo@example.test','correoFinal':{k:v[k] for k in ('asunto','html','texto','remitente','campos','imagenesDrive','presentacion','fotosSeleccionadas','validacionDepot')}}))
    db.add(e);db.commit()
    return e.id


def test_cerrada_distingue_revision_actual_y_original_sin_modificar_entrega(cliente,db,historica):
    db.expire_all();original=db.get(AppEntrega,historica);datos_originales=dict(original.datos)
    estado_original=m.doc_recepcion(db.get(AppRecepcion,CODIGO))
    eventos=[e.id for e in db.scalars(select(AppEvento).where(AppEvento.recepcion==CODIGO))];db.rollback()
    v=cliente.get(RUTA+'/correo').json()
    assert v['estadoRecepcion']=='CERRADA' and v['entregaAgrupada'] and not v['vistaArchivada']
    assert v['origenes']==ORIGENES and v['correosSeparados']
    assert v['entregaDisponible']==historica and v['entregaHistoricaDisponible']==historica
    for origen in ORIGENES:
        borrador=cliente.get(RUTA+'/correo',params={'origen':origen}).json()
        assert borrador['origen']==origen and not borrador['soloLectura']
        assert borrador['campos']['destinatarios']=='ejecutivo@example.test'
        assert len(borrador['archivos'])==0  # No adjudica el Excel global a cada embarque.
        otro=next(o for o in ORIGENES if o!=origen)
        assert m.normalizar_codigo('SKU-'+origen) in borrador['html'] and m.normalizar_codigo('SKU-'+otro) not in borrador['html']
        r=cliente.put(RUTA+'/correo',json={'origen':origen,'version':borrador['version'],'campos':{**borrador['campos'],'notas':'Revisión '+origen}})
        assert r.status_code==200,r.text
    archivo=cliente.get(RUTA+'/correo',params={'entregaId':historica}).json()
    assert archivo['vistaArchivada'] and archivo['soloLectura'] and not archivo['correosSeparados']
    assert archivo['html']==datos_originales['correoFinal']['html']
    db.rollback();db.expire_all()
    assert db.get(AppEntrega,historica).datos==datos_originales
    assert m.doc_recepcion(db.get(AppRecepcion,CODIGO))==estado_original
    assert [e.id for e in db.scalars(select(AppEvento).where(AppEvento.recepcion==CODIGO))]==eventos
    assert db.scalar(select(func.count()).select_from(AppEntrega))==1


def test_preparar_documentos_cerrada_da_un_archivo_por_origen_y_se_reutiliza(cliente,db,historica):
    f=cliente.post(RUTA+'/informes',json={'clave':'revision-historica-53','tipo':'DESCARGA','formato':'envio-ampliado','ultimoVisto':None})
    assert f.status_code==200,f.text
    f=f.json();adjuntos=[{'origen':o,'nombre':o+f['sufijo']+'.xlsx','base64':excel(o)} for o in ORIGENES]
    r=cliente.put(RUTA+'/informes/'+f['id'],json={'adjuntos':adjuntos});assert r.status_code==200,r.text
    for origen in ORIGENES:
        v=cliente.get(RUTA+'/correo',params={'origen':origen}).json()
        assert len(v['archivos'])==1 and v['archivos'][0]['nombre'].startswith(origen)
    vigente=cliente.get(RUTA+'/informe-actual?formato=envio-ampliado').json()
    assert vigente['actual'] and vigente['informe']['id']==f['id']
    db.rollback();db.expire_all()
    assert db.get(AppRecepcion,CODIGO).estado=='CERRADA'
    assert db.scalar(select(func.count()).select_from(AppEntrega))==1
    assert db.scalar(select(func.count()).select_from(AppInforme))==1
    assert db.get(AppEntrega,historica).estado=='ENTREGADA'


def test_reabierta_no_redirige_al_correo_anterior_y_archivo_usa_origenes_de_su_cierre(cliente,db,historica):
    m.reabrir_recepcion(db,CODIGO,'sup','Agregar un packing list posterior')
    m.guardar_packing_list(db,CODIGO,{'lineas':[{'linea':1,'sku':'OTRO53','cantidad':1}], 'porSku':{'OTRO53':1},'unidades':1},'NUEVO53')
    v=cliente.get(RUTA+'/correo').json()
    assert not v['entregaDisponible'] and v['entregaHistoricaDisponible']==historica
    assert v['origenes']==[*ORIGENES,'NUEVO53'] and v['correosSeparados']
    archivado=cliente.get(RUTA+'/correo',params={'entregaId':historica}).json()
    assert archivado['origenes']==ORIGENES and archivado['vistaArchivada']
    assert cliente.get(RUTA+'/correo',params={'entregaId':historica,'origen':'NUEVO53'}).status_code==422


def test_cambio_destinatarios_generales_invalida_default_no_guardado_por_embarque(cliente,historica):
    primero=cliente.get(RUTA+'/correo',params={'origen':'PRINCIPAL'}).json()
    general=cliente.get(RUTA+'/correo').json()
    assert cliente.put(RUTA+'/correo',json={'version':general['version'],'campos':{**general['campos'],'destinatarios':'otro@example.test'}}).status_code==200
    segundo=cliente.get(RUTA+'/correo',params={'origen':'PRINCIPAL'}).json()
    assert segundo['campos']['destinatarios']=='otro@example.test' and segundo['version']!=primero['version']
    assert cliente.put(RUTA+'/correo',json={'origen':'PRINCIPAL','version':primero['version'],'campos':primero['campos']}).status_code==409
