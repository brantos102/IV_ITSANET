"""Un archivo puede contener varios embarques; la suma repartida conserva el libro mayor."""
import base64
import io
import pytest
from fastapi import HTTPException
from openpyxl import Workbook
from sqlalchemy import select,func
from app.models import AppEntrega,AppEvento,AppRecepcion
from app.services import app_modelo as m,agrupacion_correo as ag,entregas
from app.services.instantaneas import expandir
from tests.test_remitente_responsable import correo


def test_reparto_preparado_bloquea_cambios_posteriores_de_cantidad_o_calidad():
    compartido={'id':'sku','sku':'MISMO','cantidad':8,'grupos':[{'id':'a'},{'id':'b'}],
        'incidencias':[{'tipo':'MAL_ESTADO','cantidad':2,'pnc':1}]}
    c={'repartos':{'sku':{g:{'cantidad':4,'incidencias':{'MAL_ESTADO':1},'pnc':{'MAL_ESTADO':p}}
        for g,p in (('a',1),('b',0))}}}
    ag.reparto_vigente(c,[compartido])
    for cambio in ({'cantidad':9},{'incidencias':[]},
        {'incidencias':[{'tipo':'MAL_ESTADO','cantidad':2,'pnc':2}]}):
        with pytest.raises(HTTPException) as e:ag.reparto_vigente(c,[{**compartido,**cambio}])
        assert e.value.status_code==409


@pytest.fixture
def multi(cliente,db,correo):
    c='ARCHIVO-CON-DOS-EMBARQUES'
    m.crear_recepcion(db,{'codigo':c,'cliente':'VENTURA'},'personal@example.test')
    m.guardar_packing_list(db,c,{'lineas':[{'linea':1,'sku':'MISMO','cantidad':3,'embarque':'EMB-A','cruda':['MISMO',3,'EMB-A']},
        {'linea':2,'sku':'MISMO','cantidad':5,'embarque':'EMB-B','cruda':['MISMO',5,'EMB-B']}],
        'porSku':{'MISMO':8},'unidades':8,'encabezados':['ITEM','Cantidad','Embarque'],'columnas':{'sku':0,'cantidad':1,'embarque':2}},'PRINCIPAL')
    m.registrar_conteo(db,c,'sup',{'id':'multi53','sku':'MISMO','cantidad':8,'pallet':'B01','incidencias':[{'tipo':'MAL_ESTADO','cantidad':2}]})
    return c


def plan(cliente,c,**cambios):
    ruta='/api/operacion/recepciones/'+c+'/correos-embarques'
    actual=cliente.get(ruta).json()
    preview=cliente.post(ruta+'/vista',json={'modo':'EMBARQUE',**cambios});assert preview.status_code==200,preview.text
    p=preview.json()
    datos={'version':actual['version'],'modo':'EMBARQUE','asignaciones':{},'embarquesPorLinea':{},
        'repartos':{s['id']:s['propuesta'] for s in p['repartos']},'repartoConfirmado':True,**cambios}
    return ruta,p,datos


def documentos(cliente,c,p):
    ruta='/api/operacion/recepciones/'+c
    f=cliente.post(ruta+'/informes',json={'tipo':'CORREO','formato':'envio-ampliado','clave':'embarques53-'+c,'ultimoVisto':None})
    assert f.status_code==200,f.text
    f=f.json();adjuntos=[]
    for g in p['grupos']:
        for o in g['packingLists']:
            w=Workbook();w.active.append(['ITEM','Cantidad','EMBARQUE']);w.active.append(['MISMO',3,g['nombre']+' '+o]);b=io.BytesIO();w.save(b)
            adjuntos.append({'grupo':g['id'],'origen':o,'nombre':o+'_'+g['nombre']+f['sufijo']+'.xlsx','base64':base64.b64encode(b.getvalue()).decode()})
    r=cliente.put(ruta+'/informes/'+f['id'],json={'adjuntos':adjuntos});assert r.status_code==200,r.text
    return f


def test_elegir_por_embarque_separa_un_archivo_y_exige_conservar_cantidad_y_pnc(cliente,db,multi):
    ruta,p,d=plan(cliente,multi);assert len(p['grupos'])==2 and len(p['origenes'])==1 and len(p['repartos'])==1
    assert cliente.put(ruta,json={**d,'repartoConfirmado':False}).status_code==422
    rid=p['repartos'][0]['id'];g1,g2=[g['id'] for g in p['grupos']]
    d['repartos'][rid][g1].update(cantidad=4,incidencias={'MAL_ESTADO':1},pnc={'MAL_ESTADO':1},observacion='Asignado a EMB-A')
    d['repartos'][rid][g2].update(cantidad=4,incidencias={'MAL_ESTADO':1},pnc={'MAL_ESTADO':1},observacion='Asignado a EMB-B')
    assert cliente.put(ruta,json=d).status_code==200
    assert cliente.put(ruta,json=d).status_code==409
    for g in (g1,g2):
        v=cliente.get('/api/operacion/recepciones/'+multi+'/correo',params={'origen':g}).json()
        assert v['modoAgrupacion']=='EMBARQUE' and v['nombreGrupo'] in ('EMB-A','EMB-B')
        assert ('Asignado a '+v['nombreGrupo']) in v['html']
    db.rollback();db.expire_all();assert len(m.leer_coleccion(db,multi,'eventos'))==1
    assert m.leer_coleccion(db,multi,'skus')[0]['contado']==8
    db.rollback()
    ruta,p,d=plan(cliente,multi);d['repartos'][rid][g1]['cantidad']=99
    assert cliente.put(ruta,json=d).status_code==422
    d['repartos'][rid][g1]['cantidad']=4;d['repartos'][rid][g1]['pnc']['MAL_ESTADO']=0
    assert cliente.put(ruta,json=d).status_code==422


def test_cierra_un_archivo_con_dos_embarques_y_envia_dos_correos_sin_cruces(cliente,db,multi,monkeypatch):
    ruta,p,d=plan(cliente,multi);r=cliente.put(ruta,json=d);assert r.status_code==200,r.text
    f=documentos(cliente,multi,p);cs=[]
    for g in p['grupos']:
        q='/api/operacion/recepciones/'+multi+'/correo';v=cliente.get(q,params={'origen':g['id']}).json()
        v=cliente.put(q,json={'version':v['version'],'origen':g['id'],'campos':{**v['campos'],'destinatarios':g['nombre'].lower()+'@example.test'}}).json()
        assert len(v['archivos'])==1
        cs.append({'origen':g['id'],'correoVersion':v['version'],'destinatarios':v['campos']['destinatarios']})
    datos={'informeId':f['id'],'correos':cs,'destinatarios':','.join(x['destinatarios'] for x in cs),
        'eventos':[e['id'] for e in cliente.get('/api/app/recepciones/'+multi+'/eventos').json()], 'remitenteConfirmado':'personal@example.test'}
    r=cliente.post('/api/app/recepciones/'+multi+'/entrega',json=datos);assert r.status_code==201,r.text
    finales=[]
    def google(a,k,payload):
        if a=='estado':return {'exito':True,'remitente':'personal@example.test','capacidades':['correoEditable']}
        if a=='archivo':return {'exito':True,'fileId':'drive-'+k[-32:]}
        finales.append(payload);return {'exito':True,'enviadoA':payload['destinatarios'],'remitente':'personal@example.test'}
    monkeypatch.setattr(entregas,'llamar',google);assert entregas.procesar_uno()
    assert len(finales)==2 and sum(x['resumen']['unidadesFisicas'] for x in finales)==8 and sum(x['resumen']['unidadesPnc'] for x in finales)==2
    assert all(len(x['archivos'])==1 for x in finales)
    db.rollback();db.expire_all();assert db.get(AppEntrega,r.json()['id']).estado=='ENTREGADA'
    assert db.get(AppRecepcion,multi).estado=='CERRADA'


def test_embarque_comun_en_dos_archivos_tiene_un_correo_con_dos_adjuntos(cliente,db,multi):
    m.guardar_packing_list(db,multi,{'lineas':[{'linea':1,'sku':'OTRO','cantidad':1,'embarque':'EMB-A'}], 'porSku':{'OTRO':1},'unidades':1},'SEGUNDO')
    m.registrar_conteo(db,multi,'sup',{'id':'otro53','sku':'OTRO','cantidad':1,'pallet':'B02'})
    ruta,p,d=plan(cliente,multi);assert cliente.put(ruta,json=d).status_code==200
    g=next(g for g in p['grupos'] if g['nombre']=='EMB-A');assert g['packingLists']==['PRINCIPAL','SEGUNDO']
    documentos(cliente,multi,p)
    v=cliente.get('/api/operacion/recepciones/'+multi+'/correo',params={'origen':g['id']}).json()
    assert len(v['archivos'])==2


def test_filas_sin_embarque_requieren_asignacion_explicita_sin_modificar_fuente(cliente,db,multi):
    m.guardar_packing_list(db,multi,{'lineas':[{'linea':1,'sku':'SINDATO','cantidad':1}], 'porSku':{'SINDATO':1},'unidades':1},'SIN-DATO')
    ruta,p,d=plan(cliente,multi);assert p['faltanEmbarques']
    assert cliente.put(ruta,json=d).status_code==422
    d['embarquesPorLinea']={x['id']:'EMB-C' for x in p['faltanEmbarques']}
    ruta,p,d=plan(cliente,multi,embarquesPorLinea=d['embarquesPorLinea'])
    assert cliente.put(ruta,json=d).status_code==200
    lineas=cliente.get('/api/app/recepciones/'+multi+'/lineas').json()
    assert 'embarque' not in next(l for l in lineas if l['sku']=='SINDATO')
