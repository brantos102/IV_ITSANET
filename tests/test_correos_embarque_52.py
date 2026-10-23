"""Separación por packing list, descarga vigente y recuperación sin duplicados."""
import base64
import io
import re
from zipfile import ZipFile

import pytest
from openpyxl import Workbook
from sqlalchemy import select
from app.models import AppArchivo, AppEntrega, AppEvento, AppRecepcion
from app.services import app_modelo as m, archivos, entregas, informes, correos_embarque as ce
from app.services.instantaneas import expandir
from tests.test_remitente_responsable import correo


def ruta(codigo):return '/api/operacion/recepciones/'+codigo


@pytest.fixture
def lote(cliente,db,correo):
    codigo='EMBARQUES-52'
    m.crear_recepcion(db,{'codigo':codigo,'cliente':'PRUEBA'},'personal@example.test')
    for origen,n in [('RB52A',3),('RB52B',5)]:
        m.guardar_packing_list(db,codigo,{'lineas':[{'linea':1,'sku':'COMPARTIDO','cantidad':n,'descripcion':'Producto común','cruda':['COMPARTIDO',n]}],
            'porSku':{'COMPARTIDO':n},'unidades':n,'columnas':{'sku':0,'cantidad':1},'encabezados':['ITEM','CANTIDAD']},origen)
        m.registrar_conteo(db,codigo,'sup',{'id':origen+'-conteo','sku':'COMPARTIDO','cantidad':n+(origen=='RB52A'),
            'pallet':'A1' if origen=='RB52A' else 'B1','origen':origen,'confirmarSobrante':True,
            'observacion':'NOTA-A' if origen=='RB52A' else 'NOTA-B',
            'incidencias':[{'tipo':'MAL_ESTADO','cantidad':1}] if origen=='RB52B' else []})
    return codigo


def generar(cliente,codigo,tipo='CORREO',formato='envio-ampliado'):
    ruta_inf=ruta(codigo)+'/informes'
    f=cliente.post(ruta_inf,json={'clave':'generacion52-'+codigo,'tipo':tipo,'formato':formato,'ultimoVisto':None})
    assert f.status_code==200,f.text
    f=f.json();adjuntos=[]
    for origen in ['RB52A','RB52B']:
        w=Workbook();w.active.append(['ITEM','CANTIDAD',origen]);w.active.append(['COMPARTIDO',3]);b=io.BytesIO();w.save(b)
        adjuntos.append({'origen':origen,'nombre':origen+f['sufijo']+'.xlsx','base64':base64.b64encode(b.getvalue()).decode()})
    r=cliente.put(ruta_inf+'/'+f['id'],json={'adjuntos':adjuntos});assert r.status_code==200,r.text
    return r.json(),adjuntos


def revisar(cliente,codigo,entrega=''):
    correos=[]
    for origen in ['RB52A','RB52B']:
        v=cliente.get(ruta(codigo)+'/correo',params={'origen':origen,'entregaId':entrega}).json()
        if v['soloLectura']:correos.append({'origen':origen,'confirmado':True});continue
        campos={**v['campos'],'destinatarios':origen.lower()+'@example.test'}
        v=cliente.put(ruta(codigo)+'/correo',json={'origen':origen,'entregaId':entrega,'version':v['version'],'campos':campos}).json()
        assert 'version' in v,v
        correos.append({'origen':origen,'correoVersion':v['version'],'destinatarios':v['campos']['destinatarios']})
    return correos


def cerrar(cliente,db,codigo,modo='AUTOMATICO'):
    f,_=generar(cliente,codigo)
    datos={'informeId':f['id'],'adjuntos':[],'eventos':[e['id'] for e in m.leer_coleccion(db,codigo,'eventos')],
        'correos':revisar(cliente,codigo),'destinatarios':'rb52a@example.test,rb52b@example.test',
        'modoEntrega':modo,'remitenteConfirmado':'personal@example.test','carpetaMes':'2026-10','carpetaRecepcion':codigo}
    r=cliente.post('/api/app/recepciones/'+codigo+'/entrega',json=datos);assert r.status_code==201,r.text
    return r.json(),datos


def google(llamadas,fallar=False):
    def llamada(accion,clave,payload):
        llamadas.append((accion,clave,payload))
        if accion=='estado':return {'exito':True,'remitente':'personal@example.test','versionPuente':2,'capacidades':['correoEditable','correoVerificado']}
        if accion=='archivo':return {'exito':True,'fileId':'drive-'+clave[-32:],'tipoArchivo':payload['tipoArchivo']}
        assert accion=='finalizar'
        assert re.fullmatch('[a-f0-9]{32}',clave)
        if fallar and payload['origen']=='RB52B':raise OSError('simulación de red')
        return {'exito':True,'remitente':'personal@example.test','enviadoA':payload['destinatarios'],'carpeta':'https://drive.google.com/drive/folders/pruebas52'}
    return llamada


def test_cada_vista_contiene_solo_su_embarque_y_documento(cliente,db,lote):
    f,_=generar(cliente,lote)
    for origen,otra,contado,esperado,pnc in [('RB52A','RB52B',4,3,0),('RB52B','RB52A',5,5,1)]:
        _,_,fuente,docs=__import__('app.services.correo_redactado',fromlist=['_fuente'])._fuente(db,lote,origen=origen)
        s=fuente['skus'][0];assert (s['contado'],s['esperado'],s['cantidadPnc'])==(contado,esperado,pnc)
        assert {e['origen'] for e in fuente['eventos']}=={origen}
        db.rollback()  # Liberar los bloqueos de lectura actual antes de otra sesión HTTP.
        v=cliente.get(ruta(lote)+'/correo',params={'origen':origen}).json()
        assert origen in v['asunto'] and len(v['archivos'])==1 and origen in v['archivos'][0]['nombre']
        assert otra not in v['html']
    assert cliente.get(ruta(lote)+'/correo').json()['correosSeparados']


def test_un_cierre_dos_correos_y_reintento_omite_el_confirmado(cliente,db,lote,monkeypatch):
    e,datos=cerrar(cliente,db,lote)
    assert len(e['correos'])==2
    assert cliente.post('/api/app/recepciones/'+lote+'/entrega',json=datos).json()['id']==e['id']
    llamadas=[];monkeypatch.setattr(entregas,'llamar',google(llamadas,True))
    assert entregas.procesar_uno()
    db.rollback();db.expire_all();guardado=db.get(AppEntrega,e['id']);d=expandir(guardado.datos)
    assert [c['estado'] for c in d['correosPorOrigen']]==['ENTREGADA','PENDIENTE']
    assert guardado.estado=='PENDIENTE'
    assert len(list(db.scalars(select(AppEntrega).where(AppEntrega.recepcion==lote))))==1
    assert guardado.datos.get('instantaneaGzip')
    for _,_,payload in [c for c in llamadas if c[0]=='finalizar']:
        origen=payload['origen'];otra='RB52B' if origen=='RB52A' else 'RB52A'
        assert len(payload['archivos'])==1 and origen in payload['archivos'][0]['nombre']
        assert otra not in payload['correoFinal']['html'] and payload['destinatarios']==origen.lower()+'@example.test'
        assert payload['resumen']['unidadesFisicas']==(4 if origen=='RB52A' else 5)
    clave_b=next(c[1] for c in llamadas if c[0]=='finalizar' and c[2]['origen']=='RB52B')
    assert cliente.post('/api/app/entregas/'+e['id']+'/reintentar').status_code==200
    siguientes=[];monkeypatch.setattr(entregas,'llamar',google(siguientes))
    assert entregas.procesar_uno()
    finales=[c for c in siguientes if c[0]=='finalizar'];assert len(finales)==1 and finales[0][2]['origen']=='RB52B' and finales[0][1]==clave_b
    db.rollback();db.expire_all();assert db.get(AppEntrega,e['id']).estado=='ENTREGADA';assert all(c['estado']=='ENTREGADA' for c in db.get(AppEntrega,e['id']).datos['correosPorOrigen'])


def test_correos_no_revisados_desactualizados_o_sin_destino_no_cierran(cliente,db,lote):
    f,_=generar(cliente,lote);cs=revisar(cliente,lote)
    datos={'informeId':f['id'],'eventos':[e['id'] for e in m.leer_coleccion(db,lote,'eventos')],'destinatarios':'a@example.test','modoEntrega':'MANUAL'}
    for valor in [None,[],['invalido'],[cs[0],cs[0]],[cs[0],{**cs[1],'correoVersion':'obsoleta'}]]:
        r=cliente.post('/api/app/recepciones/'+lote+'/entrega',json={**datos,'correos':valor})
        assert r.status_code in (409,422),r.text
    db.rollback();assert db.get(AppRecepcion,lote).estado!='CERRADA'
    assert not db.scalar(select(AppEntrega).where(AppEntrega.recepcion==lote))


def test_descarga_vigente_reutiliza_documentos_y_zip_unico(cliente,db,lote):
    f,adjuntos=generar(cliente,lote)
    assert cliente.get(ruta(lote)+'/informe-actual?formato=envio-ampliado').json()['informe']['id']==f['id']
    url='/api/operacion/informes/'+f['id']+'/descarga'
    r=cliente.get(url);assert r.status_code==200 and r.headers['content-type']=='application/zip'
    with ZipFile(io.BytesIO(r.content)) as z:
        assert set(z.namelist())=={a['nombre'] for a in adjuntos}
        for a in adjuntos:assert z.read(a['nombre'])==base64.b64decode(a['base64'])
    r=cliente.get(url+'?origen=RB52A');assert r.status_code==200 and r.content==base64.b64decode(adjuntos[0]['base64'])
    assert cliente.get(url+'?origen=AJENO').status_code==404
    assert len(cliente.get(ruta(lote)+'/informes').json())==1
    assert not list(archivos.DATA_DIR.rglob('*.zip'))
    assert len(cliente.get(ruta(lote)+'/informes').json()[0]['descargas'])==2
    m.registrar_conteo(db,lote,'op1',{'id':'cambio-52','sku':'COMPARTIDO','cantidad':1,'pallet':'A1','origen':'RB52A','confirmarSobrante':True})
    assert not cliente.get(ruta(lote)+'/informe-actual?formato=envio-ampliado').json()['actual']
    assert cliente.get(url).status_code==200  # Histórico preservado.


def test_cerrar_solo_no_invalida_la_descarga_y_declaracion_manual_exige_cada_embarque(cliente,db,lote):
    e,_=cerrar(cliente,db,lote,'MANUAL')
    assert cliente.get(ruta(lote)+'/informe-actual?formato=envio-ampliado').json()['actual']
    vista=cliente.get(ruta(lote)+'/correo',params={'entregaId':e['id']}).json()
    datos={'versionGestion':e['versionGestion'],'correoVersion':vista['version'],'motivo':'Todos enviados desde mi cuenta de prueba','confirmarEnviado':True}
    url='/api/app/entregas/'+e['id']+'/manual-confirmado'
    assert cliente.post(url,json=datos).status_code==422
    cs=[]
    for o in ['RB52A','RB52B']:
        v=cliente.get(ruta(lote)+'/correo',params={'entregaId':e['id'],'origen':o}).json()
        cs.append({'origen':o,'correoVersion':v['version'],'confirmarEnviado':True})
    r=cliente.post(url,json={**datos,'correos':cs});assert r.status_code==200,r.text
    assert all(c['estado']=='MANUAL_DECLARADO' for c in r.json()['correos'])
    assert cliente.get(ruta(lote)+'/correo',params={'entregaId':e['id'],'origen':'RB52A'}).json()['soloLectura']


def test_fotos_asociadas_no_se_cruzan_entre_embarques():
    fuente={'skus':[{'sku':'S','contado':2}], 'eventos':[], 'fotos':[
        {'archivoId':'a','origen':'A','sku':'S'}, {'archivoId':'b','origen':'B','sku':'S'},
        {'archivoId':'sin-asignar','sku':'S'}, {'archivoId':'panoramica','sku':''}]}
    lineas=[{'sku':'S','origen':'A','cantidad':1},{'sku':'S','origen':'B','cantidad':1}]
    assert {f['archivoId'] for f in ce.filtrar(fuente,lineas,'A',{})['fotos']}=={'a','panoramica'}
    assert {f['archivoId'] for f in ce.filtrar(fuente,lineas,'B',{})['fotos']}=={'b','panoramica'}


def test_asignacion_adicional_versionada_y_permisos(cliente,db,lote):
    m.registrar_conteo(db,lote,'sup',{'id':'adicional52','sku':'EXTRA52','cantidad':2,'descripcion':'No declarado','pallet':'A2','motivo':'Vino fuera de packing','confirmarSobrante':True})
    p=cliente.get(ruta(lote)+'/correos-embarques').json()
    assert [s['sku'] for s in p['adicionales']]==['EXTRA52']
    from fastapi import HTTPException
    with pytest.raises(HTTPException,match='') as exc:ce.validar_cierre(db,m.obtener(db,lote))
    assert exc.value.status_code==409
    db.rollback()
    url=ruta(lote)+'/correos-embarques'
    assert cliente.put(url,json={'version':p['version'],'asignaciones':{'EXTRA52':'AJENO'}}).status_code==422
    assert cliente.put(url,json={'version':p['version'],'asignaciones':{'EXTRA52':'RB52B'}}).status_code==200
    assert cliente.put(url,json={'version':p['version'],'asignaciones':{'EXTRA52':'RB52A'}}).status_code==409
    from app.services.correo_redactado import _fuente
    assert 'EXTRA52' not in [s['sku'] for s in _fuente(db,lote,origen='RB52A')[2]['skus']]
    assert 'EXTRA52' in [s['sku'] for s in _fuente(db,lote,origen='RB52B')[2]['skus']]
    from fastapi.testclient import TestClient
    from app.main import app
    op=TestClient(app);op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    assert op.get(url).status_code==403


def test_recuperar_lote_preserva_confirmado_y_no_reenvia(cliente,db,lote,monkeypatch):
    e,_=cerrar(cliente,db,lote);llamadas=[];monkeypatch.setattr(entregas,'llamar',google(llamadas,True));assert entregas.procesar_uno()
    cs=revisar(cliente,lote,e['id'])
    monkeypatch.setattr(entregas,'llamar',google([]))
    r=cliente.post('/api/app/entregas/'+e['id']+'/solicitar',json={'correos':cs,'confirmarNoEnviado':True,'motivo':'Revisé Enviados y solo falta el segundo','remitenteConfirmado':'personal@example.test'})
    assert r.status_code==200,r.text
    assert [c['estado'] for c in r.json()['correos']]==['ENTREGADA','PENDIENTE']
    siguientes=[];monkeypatch.setattr(entregas,'llamar',google(siguientes));assert entregas.procesar_uno()
    assert [c[2]['origen'] for c in siguientes if c[0]=='finalizar']==['RB52B']
    assert cliente.get(ruta(lote)+'/correo',params={'origen':'RB52A','entregaId':e['id']}).json()['soloLectura']


def test_falta_de_archivo_o_informe_ajeno_no_descarga(cliente,db,lote):
    f,_=generar(cliente,lote);a=db.get(AppArchivo,f['archivos'][0]['id'])
    archivos.ruta(a).unlink()
    assert cliente.get('/api/operacion/informes/'+f['id']+'/descarga').status_code==409
    assert not cliente.get(ruta(lote)+'/informe-actual?formato=envio-ampliado').json()['actual']
    assert cliente.get('/api/operacion/informes/inexistente/descarga').status_code==404


def test_dos_supervisores_cierran_lote_una_sola_vez_mysql(cliente,db,lote):
    if db.bind.dialect.name!='mysql':pytest.skip('Bloqueos reales en MySQL desechable')
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi import HTTPException
    from app.db import SessionLocal
    f,_=generar(cliente,lote);cs=revisar(cliente,lote)
    datos={'informeId':f['id'],'eventos':[e['id'] for e in m.leer_coleccion(db,lote,'eventos')],
        'correos':cs,'destinatarios':'rb52a@example.test,rb52b@example.test','modoEntrega':'MANUAL'}
    db.rollback();barrera=Barrier(2)
    def ejecutar(_):
        with SessionLocal() as s:
            barrera.wait(timeout=10)
            try:return entregas.preparar(s,lote,datos,'personal@example.test')['id']
            except HTTPException as exc:s.rollback();return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:resultados=list(pool.map(ejecutar,range(2)))
    exitos={r for r in resultados if isinstance(r,str)}
    assert len(exitos)==1 and all(isinstance(r,str) or r==409 for r in resultados)
    db.expire_all();assert len(list(db.scalars(select(AppEntrega).where(AppEntrega.recepcion==lote))))==1


def test_no_reintenta_si_google_no_confirma_destinatario_de_un_embarque(cliente,db,lote,monkeypatch):
    e,_=cerrar(cliente,db,lote);llamadas=[];normal=google(llamadas)
    def ambiguo(accion,clave,payload):
        r=normal(accion,clave,payload)
        if accion=='finalizar' and payload['origen']=='RB52B':r.pop('enviadoA')
        return r
    monkeypatch.setattr(entregas,'llamar',ambiguo);assert entregas.procesar_uno()
    db.rollback();db.expire_all();e=db.get(AppEntrega,e['id'])
    assert e.estado=='REVISION' and e.datos['correosPorOrigen'][0]['estado']=='ENTREGADA'
    assert not entregas.procesar_uno()
