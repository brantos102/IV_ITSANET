"""Alias por documento y selección revisada, sin renombrar los archivos históricos."""
import base64
import io
from uuid import uuid4
from fastapi.testclient import TestClient
from openpyxl import Workbook
from app.main import app
from app.models import AppArchivo,AppEntrega
from app.services import app_modelo as m
from app.services.instantaneas import expandir
from tests.test_remitente_responsable import correo as cuenta_correo


def generar(cliente,c,formato='envio-ampliado',tipo='DESCARGA'):
    ruta='/api/operacion/recepciones/'+c+'/informes';hs=cliente.get(ruta).json()
    r=cliente.post(ruta,json={'clave':uuid4().hex,'tipo':tipo,'formato':formato,'ultimoVisto':hs[0]['id'] if hs else None})
    assert r.status_code==200,r.text
    f=r.json();docs=[]
    for origen in cliente.get('/api/app/recepciones/'+c).json()['origenes']:
        w=Workbook();w.active.append(['ITEM','CANTIDAD']);w.active.append(['SKU1',3]);w.properties.subject=origen+formato+f['sufijo'];b=io.BytesIO();w.save(b)
        docs.append({'nombre':formato+'_'+origen+f['sufijo']+'.xlsx','origen':origen,'base64':base64.b64encode(b.getvalue()).decode()})
    r=cliente.put(ruta+'/'+f['id'],json={'adjuntos':docs});assert r.status_code==200,r.text
    return r.json()


def guardar(cliente,ruta,v,adjuntos,alias=None,origen=''):
    r=cliente.put(ruta,json={'version':v['version'],'versionEdicion':v['versionEdicion'],'campos':{**v['campos'],'destinatarios':'ejecutivo@example.test','notas':'Redacción conservada'},'origen':origen,'adjuntos':adjuntos,**({'nombresDocumentos':alias} if alias is not None else {})})
    assert r.status_code==200,r.text
    return r.json()


def test_alias_de_cada_formato_persisten_aunque_se_prepare_otro_y_se_desmarque(cliente,db,cuenta_correo):
    c,_=cuenta_correo;ruta='/api/operacion/recepciones/'+c+'/correo';f1=generar(cliente,c);a=f1['archivos'][0]
    v=guardar(cliente,ruta,cliente.get(ruta).json(),[{'id':a['id'],'nombre':'Cliente_final.xlsx'}])
    f2=generar(cliente,c,'envio');b=f2['archivos'][0];v=cliente.get(ruta).json()
    assert [(x['id'],x['nombre']) for x in v['archivos']]==[(a['id'],'Cliente_final.xlsx')]
    v=guardar(cliente,ruta,v,[{'id':a['id'],'nombre':'Cliente_final.xlsx'},{'id':b['id'],'nombre':'Ejecutivo_final.xlsx'}])
    v=guardar(cliente,ruta,v,[{'id':b['id'],'nombre':'Ejecutivo_final.xlsx'}],{a['id']:'Cliente_descarga.xlsx',b['id']:'Ejecutivo_final.xlsx'})
    v=cliente.get(ruta).json();assert v['nombresDocumentos'][a['id']]=='Cliente_descarga.xlsx'
    assert [x['id'] for x in v['archivos']]==[b['id']]
    assert 'Redacción conservada' in v['texto']
    db.rollback();assert db.get(AppArchivo,a['id']).nombre==a['nombre'] and db.get(AppArchivo,b['id']).nombre==b['nombre']


def test_borrador_sin_adjuntos_conserva_alias_y_el_envio_exige_una_seleccion(cliente,db,cuenta_correo):
    c,_=cuenta_correo;ruta='/api/operacion/recepciones/'+c+'/correo';a=generar(cliente,c)['archivos'][0]
    v=guardar(cliente,ruta,cliente.get(ruta).json(),[],{a['id']:'Nombre_para_despues.xlsx'})
    assert not v['archivos'] and v['nombresDocumentos'][a['id']]=='Nombre_para_despues.xlsx'
    r=cliente.post(ruta+'/enviar',json={'confirmar':True,'version':v['version'],'remitenteConfirmado':'personal@example.test'})
    assert r.status_code==422 and 'Selecciona' in r.text
    db.rollback();assert db.query(AppEntrega).count()==0 and m.obtener(db,c).estado!='CERRADA'


def test_alias_rechaza_documentos_ajenos_extension_cambiada_y_operario(cliente,db,cuenta_correo):
    c,_=cuenta_correo;ruta='/api/operacion/recepciones/'+c+'/correo';a=generar(cliente,c)['archivos'][0];v=cliente.get(ruta).json()
    datos={'version':v['version'],'campos':v['campos']}
    for alias,estado in [({'ajeno':'Nombre.xlsx'},409),({a['id']:'Nombre.pdf'},422),({a['id']:'../../Nombre.xlsx'},422)]:
        assert cliente.put(ruta,json={**datos,'nombresDocumentos':alias}).status_code==estado
    op=TestClient(app);op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'});v=op.get(ruta).json()
    assert op.put(ruta,json={'version':v['version'],'campos':v['campos'],'nombresDocumentos':{a['id']:'Operario.xlsx'}}).status_code==403


def test_envio_directo_solo_incluye_el_documento_elegido_con_nombre_final(cliente,db,cuenta_correo):
    c,_=cuenta_correo;ruta='/api/operacion/recepciones/'+c+'/correo';a=generar(cliente,c)['archivos'][0];b=generar(cliente,c,'auditable')['archivos'][0]
    v=guardar(cliente,ruta,cliente.get(ruta).json(),[{'id':b['id'],'nombre':'Control_final.xlsx'}],{a['id']:'Cliente_no_adjunto.xlsx'})
    r=cliente.post(ruta+'/enviar',json={'confirmar':True,'version':v['version'],'remitenteConfirmado':'personal@example.test'})
    assert r.status_code==201,r.text
    db.rollback();e=db.get(AppEntrega,r.json()['id']);d=expandir(e.datos)
    assert d['informes']==[b['id']] and d['nombresAdjuntos']=={b['id']:'Control_final.xlsx'}
    assert db.get(AppArchivo,a['id']).nombre==a['nombre'] and db.get(AppArchivo,b['id']).nombre==b['nombre']


def test_cierre_conserva_varios_formatos_y_alias_sin_sumar_archivos_no_elegidos(cliente,db,cuenta_correo):
    c,datos=cuenta_correo;ruta='/api/operacion/recepciones/'+c+'/correo';f=generar(cliente,c,tipo='CORREO');a=f['archivos'][0];b=generar(cliente,c,'envio')['archivos'][0]
    v=guardar(cliente,ruta,cliente.get(ruta).json(),[{'id':a['id'],'nombre':'Cliente_final.xlsx'},{'id':b['id'],'nombre':'Ejecutivo_final.xlsx'}])
    db.rollback();r=cliente.post('/api/app/recepciones/'+c+'/entrega',json={**datos,'adjuntos':[],'informeId':f['id'],'correoVersion':v['version'],'modoEntrega':'MANUAL'})
    assert r.status_code==201,r.text
    db.rollback();d=expandir(db.get(AppEntrega,r.json()['id']).datos)
    assert set(d['informes'])=={a['id'],b['id']}
    assert d['nombresAdjuntos']=={a['id']:'Cliente_final.xlsx',b['id']:'Ejecutivo_final.xlsx'}
    archivado=cliente.get(ruta,params={'entregaId':r.json()['id']}).json()
    assert {a['nombre'] for a in archivado['archivos']}=={'Cliente_final.xlsx','Ejecutivo_final.xlsx'}


def test_cierre_por_packing_list_respeta_selecciones_y_alias_distintos_por_grupo(cliente,db,cuenta_correo):
    c,datos=cuenta_correo
    m.guardar_packing_list(db,c,{'lineas':[{'linea':1,'sku':'SKU2','cantidad':2}], 'porSku':{'SKU2':2},'unidades':2,'encabezados':['ITEM','CANTIDAD'],'columnas':{'sku':0,'cantidad':1}},'OTRA')
    m.registrar_conteo(db,c,'op1',{'id':'adicional-grupo65','sku':'SKU2','cantidad':2,'origen':'OTRA','pallet':'B01'})
    f1=generar(cliente,c,tipo='CORREO');f2=generar(cliente,c,'envio');a={d['origen']:d for d in f1['archivos']};b={d['origen']:d for d in f2['archivos']}
    ruta='/api/operacion/recepciones/'+c+'/correo';revisados=[];nombres={a['LISTA']['id']:'Cliente_LISTA.xlsx',b['LISTA']['id']:'Ejecutivo_LISTA.xlsx',b['OTRA']['id']:'Ejecutivo_OTRA.xlsx'}
    for origen,ids in [('LISTA',[a['LISTA']['id'],b['LISTA']['id']]),('OTRA',[b['OTRA']['id']])]:
        v=cliente.get(ruta,params={'origen':origen}).json();v=guardar(cliente,ruta,v,[{'id':ident,'nombre':nombres[ident]} for ident in ids],origen=origen)
        revisados.append({'origen':origen,'correoVersion':v['version'],'destinatarios':v['campos']['destinatarios']})
    db.rollback();eventos=[e['id'] for e in m.leer_coleccion(db,c,'eventos')];db.rollback()
    r=cliente.post('/api/app/recepciones/'+c+'/entrega',json={**datos,'informeId':f1['id'],'adjuntos':[],'eventos':eventos,'correos':revisados,'modoEntrega':'MANUAL'})
    assert r.status_code==201,r.text
    db.rollback();d=expandir(db.get(AppEntrega,r.json()['id']).datos)
    assert set(d['informes'])==set(nombres) and d['nombresAdjuntos']==nombres
    assert a['OTRA']['id'] not in d['informes']
    for hijo in d['correosPorOrigen']:
        assert hijo['nombresAdjuntos']=={ident:nombres[ident] for ident in hijo['informes']}
    v=cliente.get(ruta,params={'entregaId':r.json()['id'],'origen':'LISTA'}).json()
    assert {x['nombre'] for x in v['archivos']}=={'Cliente_LISTA.xlsx','Ejecutivo_LISTA.xlsx'}
