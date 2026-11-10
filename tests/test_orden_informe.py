"""Organización por embarque: no altera fuentes, movimientos ni informes anteriores."""
import pytest
from sqlalchemy import select
from app.models import AppRecepcion, AppAuditoriaGeneral
from tests.test_mejoras_operativas import preparar


def orden_simple():
    return ['resultado:marca','resultado:cliente','original:0','original:1','original:2',
        *['resultado:'+k for k in ('fisica','validacion','desface','pallet','posicion','codigoBarra',
          'cantidadIncidencia','incidencia','observacion','evidencia')]]


def guardar(cliente,codigo,orden,meta=None,**extras):
    ruta=f'/api/operacion/recepciones/{codigo}'
    meta=meta or cliente.get(ruta+'/informe-metadatos').json()
    return cliente.put(ruta+'/columnas-informe',json={'origen':'A','version':meta['versionFormatos'],
        'columnas':{'depot':2},'ordenSalida':orden,**extras})


def test_orden_se_guarda_por_lista_y_audita_sin_mover_datos_fuente(cliente,db):
    c=preparar(db,True);ruta=f'/api/operacion/recepciones/{c}'
    antes=cliente.get(ruta+'/informe-metadatos').json();lineas=cliente.get(f'/api/app/recepciones/{c}/lineas').json()
    res=guardar(cliente,c,orden_simple(),antes);assert res.status_code==200,res.text
    nuevo=cliente.get(ruta+'/informe-metadatos').json()
    assert nuevo['formatos']['A']['ordenSalida']==orden_simple()
    for k in ('encabezados','columnas','prefijo'):assert nuevo['formatos']['A'].get(k)==antes['formatos']['A'].get(k)
    assert nuevo['formatos']['B']==antes['formatos']['B']
    assert cliente.get(f'/api/app/recepciones/{c}/lineas').json()==lineas
    assert cliente.get(f'/api/app/recepciones/{c}/eventos').json()==[]
    assert nuevo['versionFormatos']!=antes['versionFormatos']
    assert guardar(cliente,c,list(reversed(orden_simple())),antes).status_code==409
    db.rollback();db.expire_all()
    aud=db.scalar(select(AppAuditoriaGeneral).where(AppAuditoriaGeneral.accion=='COLUMNAS_INFORME'))
    assert aud.datos['ordenSalida']==orden_simple()


@pytest.mark.parametrize('orden',[[],['original:0'],orden_simple()+['resultado:marca'],
    ['original:999',*orden_simple()[1:]],{0:'original:0'},[None,*orden_simple()[1:]]])
def test_orden_invalido_no_modifica_configuracion(cliente,db,orden):
    c=preparar(db);antes=cliente.get(f'/api/operacion/recepciones/{c}/informe-metadatos').json()
    r=guardar(cliente,c,orden,antes);assert r.status_code==422,r.text
    assert cliente.get(f'/api/operacion/recepciones/{c}/informe-metadatos').json()['versionFormatos']==antes['versionFormatos']


def test_guardado_anterior_conserva_orden_y_restablecer_es_explicito(cliente,db):
    c=preparar(db);assert guardar(cliente,c,orden_simple()).status_code==200
    ruta=f'/api/operacion/recepciones/{c}'
    meta=cliente.get(ruta+'/informe-metadatos').json()
    r=cliente.put(ruta+'/columnas-informe',json={'origen':'A','columnas':{},'version':meta['versionFormatos']})
    assert r.status_code==200,r.text
    assert cliente.get(ruta+'/informe-metadatos').json()['formatos']['A']['ordenSalida']==orden_simple()
    assert guardar(cliente,c,None).status_code==200
    assert 'ordenSalida' not in cliente.get(ruta+'/informe-metadatos').json()['formatos']['A']


def test_cambiar_orden_invalida_generacion_pendiente_y_recepcion_cerrada_lo_bloquea(cliente,db):
    c=preparar(db);ruta=f'/api/operacion/recepciones/{c}'
    f=cliente.post(ruta+'/informes',json={'clave':'orden-informe51','tipo':'DESCARGA','formato':'envio-ampliado','ultimoVisto':None})
    assert f.status_code==200,f.text
    assert guardar(cliente,c,orden_simple()).status_code==200
    assert cliente.put(ruta+'/informes/'+f.json()['id'],json={'adjuntos':[]}).status_code==409
    db.rollback();r=db.get(AppRecepcion,c);r.estado='CERRADA';db.commit()
    assert guardar(cliente,c,list(reversed(orden_simple()))).status_code==409


def test_operador_sin_permiso_no_puede_reordenar(cliente,db):
    c=preparar(db);cliente.post('/api/auth/logout');cliente.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    r=guardar(cliente,c,orden_simple(),{'versionFormatos':'ninguna'});assert r.status_code==403
