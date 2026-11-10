"""Avisos rápidos y compartidos sin sustituir el libro mayor ni su autorización."""
import asyncio
import time
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.models import AppConfig, AppEvento, AppAuditoriaGeneral, utcnow
from app.services import cambios_recepcion as cambios, app_modelo as m
from tests.test_mejoras_operativas import preparar


def test_firma_detecta_conteo_anulacion_y_no_incluye_datos_privados(cliente,db):
    c=preparar(db);ruta=f'/api/operacion/recepciones/{c}/cambios/estado'
    inicial=cliente.get(ruta).json()
    m.registrar_conteo(db,c,'op1',{'id':'conteo-vivo65','sku':'SKU1','cantidad':4,'pallet':'A01','observacion':'NOTA-PRIVADA-NO-DIFUNDIR'})
    siguiente=cliente.get(ruta).json()
    assert siguiente['revision']!=inicial['revision'] and siguiente['secciones']['conteos']!=inicial['secciones']['conteos']
    assert 'NOTA-PRIVADA' not in str(siguiente) and 'operadorEmail' not in str(siguiente)
    m.anular_conteo(db,c,'sup','conteo-vivo65','Revisión física')
    final=cliente.get(ruta).json()
    assert final['secciones']['conteos']!=siguiente['secciones']['conteos']
    assert cliente.get('/api/app/recepciones/'+c+'/skus').json()[0]['contado']==0


def test_presencia_muestra_todos_caduca_y_no_invalida_conteos(cliente,db):
    c=preparar(db);ruta=f'/api/operacion/recepciones/{c}'
    antes=cliente.get(ruta+'/cambios/estado').json()['secciones']['conteos']
    dos=TestClient(app);dos.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    tres=TestClient(app);tres.post('/api/auth/login',json={'usuario':'op2','pin':'3333'})
    for cli,disp in [(cliente,'supervisor-65'),(dos,'operadoruno-65'),(tres,'operadordos-65')]:
        assert cli.put(ruta+'/sku-en-curso',json={'dispositivo':disp,'sku':'SKU1','actividad':'CONTANDO'}).status_code==200
    datos=cliente.get(ruta+'/cambios/estado').json()
    assert {p['nombre'] for p in datos['equipoSku']}=={'Supervisora','Operador Uno','Operador Dos'}
    assert datos['secciones']['conteos']==antes and '@' not in str(datos['equipoSku'])
    db.rollback();f=db.scalar(select(AppConfig).where(AppConfig.usuario=='op2',AppConfig.clave.like('sku:%')))
    f.datos={**f.datos,'vence':time.time()-1};db.commit()
    despues=cliente.get(ruta+'/cambios/estado').json()
    assert len(despues['equipoSku'])==2 and despues['secciones']['presencia']!=datos['secciones']['presencia']
    assert db.query(AppEvento).filter(AppEvento.tipo=='CONTEO').count()==0


def test_estado_global_roster_respetan_permiso_y_catalogo_distingue_seccion(cliente,db):
    c=preparar(db);ruta=f'/api/operacion/recepciones/{c}/sku-en-curso'
    cliente.put(ruta,json={'dispositivo':'supervisor65','sku':'SKU1','actividad':'CONTANDO'})
    op=TestClient(app);op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    publico=op.get('/api/operacion/cambios/estado').json()
    assert publico['equipoSku']==[] and 'presencia' not in publico['secciones']
    sup=cliente.get('/api/operacion/cambios/estado').json()
    assert sup['equipoSku'][0]['nombre']=='Supervisora'
    previo=sup['secciones']['catalogo']
    db.add(AppAuditoriaGeneral(id='catalogo-marca65',usuario='sup',accion='CATALOGO_CARGADO',referencia='catalogo',datos={}))
    db.commit()
    assert cliente.get('/api/operacion/cambios/estado').json()['secciones']['catalogo']!=previo
    sin_sesion=TestClient(app)
    assert sin_sesion.get('/api/operacion/cambios/estado').status_code==401
    assert sin_sesion.get('/api/operacion/cambios').status_code==401


def test_un_observador_distribuye_a_dos_suscriptores_y_se_detiene(monkeypatch):
    estado={'recepcion':'R','revision':'uno','secciones':{'conteos':'1'},'equipoSku':[],'existe':True};llamadas=[]
    def leer(c):llamadas.append(c);return {**estado,'secciones':dict(estado['secciones'])}
    monkeypatch.setattr(cambios,'leer_estado',leer);monkeypatch.setattr(cambios,'INTERVALO',.01)
    async def comprobar():
        canal=cambios.Canal('R');a=canal.suscribir();b=canal.suscribir()
        assert (await asyncio.wait_for(a.get(),1))['revision']=='uno'
        assert (await asyncio.wait_for(b.get(),1))['revision']=='uno'
        assert len(llamadas)==1
        estado.update(revision='dos',secciones={'conteos':'2'})
        assert (await asyncio.wait_for(a.get(),1))['secciones']==['conteos']
        assert (await asyncio.wait_for(b.get(),1))['revision']=='dos'
        await canal.retirar(a);assert not canal.tarea.done()
        await canal.retirar(b);assert canal.tarea.done()
    asyncio.run(comprobar())


def test_operador_solo_recibe_equipo_de_skus_donde_tiene_presencia(cliente,db):
    c=preparar(db);ruta=f'/api/operacion/recepciones/{c}'
    op=TestClient(app);op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    cliente.put(ruta+'/sku-en-curso',json={'dispositivo':'supervisor-otro65','sku':'OTRO','actividad':'CONTANDO'})
    assert op.get(ruta+'/cambios/estado').json()['equipoSku']==[]
    op.put(ruta+'/sku-en-curso',json={'dispositivo':'operador-sku65','sku':'SKU1','actividad':'CONTANDO'})
    datos=op.get(ruta+'/cambios/estado').json()
    assert {p['sku'] for p in datos['equipoSku']}=={'SKU1'}
    assert 'Supervisora' not in str(datos['equipoSku'])
    cliente.put(ruta+'/sku-en-curso',json={'dispositivo':'supervisor-otro65','sku':'SKU1','actividad':'REVISANDO'})
    assert {p['nombre'] for p in op.get(ruta+'/cambios/estado').json()['equipoSku']}=={'Supervisora','Operador Uno'}


def test_firma_global_distingue_eventos_con_fecha_igual(cliente,db):
    c=preparar(db);fecha=utcnow()
    db.add(AppEvento(id='zz-evento65',recepcion=c,tipo='AUDITORIA',cantidad=0,usuario='sup',creado_en=fecha));db.commit()
    primero=cliente.get('/api/operacion/cambios/estado').json()
    db.add(AppEvento(id='aa-evento65',recepcion=c,tipo='AUDITORIA',cantidad=0,usuario='sup',creado_en=fecha));db.commit()
    segundo=cliente.get('/api/operacion/cambios/estado').json()
    assert segundo['revision']!=primero['revision'] and segundo['secciones']['operacion']!=primero['secciones']['operacion']


def test_canal_global_identifica_commit_antiguo_y_no_pierde_invalidaciones_coalescidas(monkeypatch):
    # El último timestamp global puede pertenecer a otra recepción. Las firmas
    # por recepción identifican igual el commit tardío y acumulan avisos si el
    # consumidor es lento, sin perder la invalidación anterior.
    estado={'recepcion':'','recepciones':[],'versionesRecepcion':{'R1':'viejo','R2':'nuevo'},'revision':'uno',
            'secciones':{'operacion':'1','presencia':'1'},'equipoSku':[],'existe':True}
    def leer(c):return {**estado,'versionesRecepcion':dict(estado['versionesRecepcion']),'secciones':dict(estado['secciones'])}
    monkeypatch.setattr(cambios,'leer_estado',leer);monkeypatch.setattr(cambios,'INTERVALO',.005)
    async def comprobar():
        canal=cambios.Canal('');cola=canal.suscribir()
        await asyncio.wait_for(cola.get(),1)
        estado.update(revision='dos',versionesRecepcion={'R1':'commit-antiguo-recien-confirmado','R2':'nuevo'},secciones={'operacion':'2','presencia':'1'})
        await asyncio.sleep(.02)
        estado.update(revision='tres',secciones={'operacion':'2','presencia':'2'})
        await asyncio.sleep(.02)
        aviso=await asyncio.wait_for(cola.get(),1)
        assert aviso['revision']=='tres' and aviso['recepciones']==['R1']
        assert set(aviso['secciones'])=={'operacion','presencia'}
        await canal.retirar(cola)
    asyncio.run(comprobar())
