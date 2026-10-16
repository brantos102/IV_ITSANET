import base64
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import socket
import threading

from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import select

from app.main import app
from app.models import (AppArchivo, AppCopiaDrive, AppEvidencia, AppEvento, AppImpresion,
    AppSku, AppStockDepot, Operador, Producto, Rol, utcnow)
from app.security import hash_pin
from app.services import archivos, drive, entregas, lecturas, operacion
from app.services.catalogo_programado import guardar_posiciones, posiciones_de, turno_pendiente
from tests.test_archivos_locales import PNG


@pytest.fixture
def admin(cliente, db):
    db.add(Operador(usuario='admin-nuevo', email='admin@example.test',nombre='Admin',rol=Rol.ADMIN,pin_hash=hash_pin('123456')))
    db.commit()
    c=TestClient(app);assert c.post('/api/auth/login',json={'usuario':'admin-nuevo','pin':'123456'}).status_code==200
    return c


def rec(cliente, codigo='INGRESO'):
    r=cliente.post('/api/app/recepciones',json={'codigo':codigo,'cliente':'VENTURA'})
    assert r.status_code==201,r.text
    return codigo


def foto(cliente,codigo,**datos):
    return cliente.post(f'/api/app/recepciones/{codigo}/archivos/foto',json={
        'base64':base64.b64encode(PNG+str(datos.pop('variante',0)).encode()).decode(),**datos})


def test_configuracion_solo_admin_y_preferencias_sin_infraestructura(admin,cliente):
    assert cliente.get('/api/operacion/config').status_code==403
    c=admin.get('/api/operacion/config').json()
    assert c['catalogo']['horas']==[8,10,15] and c['evidencias']['bloquear'] is False
    c['repositorios']=[{'id':'VENTURA','nombre':'Evidencias','cliente':'VENTURA','carpetaId':'https://drive.google.com/drive/folders/1234567890abc'}]
    c['impresoras']=[{'id':'ZEBRA1','nombre':'Mesa 1','host':'192.168.1.50','equipo':'PC-PRUEBA','puerto':9100}]
    r=admin.put('/api/operacion/config',json=c);assert r.status_code==200,r.text
    assert r.json()['repositorios'][0]['carpetaId']=='1234567890abc'
    p=cliente.get('/api/operacion/preferencias').json()
    assert p['impresoras']==[{'id':'ZEBRA1','nombre':'Mesa 1'}]
    assert 'repositorios' not in p and '192.168' not in json.dumps(p)
    assert cliente.post('/api/impresion/estaciones/ZEBRA1/token',json={}).status_code==403


def test_bultos_codigos_repetidos_cajas_y_avisos_no_bloquean(cliente,db):
    codigo=rec(cliente)
    ruta='/api/operacion/recepciones/'+codigo
    assert cliente.put(ruta+'/ingreso',json={'marca':'ISUZU','protocolo':'REGLAMENTARIO'}).status_code==200
    r=cliente.post(ruta+'/bultos',json={'cantidad':2});assert r.status_code==200,r.text
    bultos=r.json()['unidades'];assert len(bultos)==2
    for b in bultos:
        assert cliente.post(ruta+'/unidades',json={**b,'codigo':'MADRE-REPETIDA','origenes':['PL1','PL2']}).status_code==200
        assert cliente.post(ruta+'/unidades',json={'tipo':'CAJA_MADRE','padreId':b['id'],'codigo':'SUB-REPETIDA'}).status_code==200
    r=cliente.post(ruta+'/bultos',json={'cantidad':2})
    assert len(r.json()['unidades'])==4
    version=cliente.get(ruta+'/ingreso').json()['version']
    r=cliente.put(ruta+'/ingreso',json={'paso':'PACKING','version':version})
    assert r.status_code==200 and r.json()['avisos']
    assert len([u for u in r.json()['unidades'] if u['codigo']=='MADRE-REPETIDA'])==2


def test_evidencia_sin_tope_relacion_y_retirada_con_auditoria(cliente,db,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    codigo=rec(cliente)
    unidades=cliente.post('/api/operacion/recepciones/INGRESO/bultos',json={'cantidad':1}).json()['unidades']
    for i in range(8):
        r=foto(cliente,codigo,variante=i,sku='SKU1',unidadId=unidades[0]['id'],
            tipoEvidencia='ITEM_NOVEDAD',categoria='PNC',protocolo='REGLAMENTARIO',origen='PL1')
        assert r.status_code==201,r.text
    assert db.query(AppEvidencia).count()==8 and db.query(AppCopiaDrive).count()==8
    assert not db.query(AppEvento).filter(AppEvento.tipo=='CONTEO').count()
    archivo=r.json()
    op=TestClient(app);op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    assert op.delete('/api/operacion/evidencias/'+archivo['id']).status_code==403
    assert cliente.delete('/api/operacion/evidencias/'+archivo['id']).status_code==200
    assert cliente.get(archivo['url']).status_code==410
    assert cliente.get('/api/app/recepciones/INGRESO/imagenes').json()['total']==7
    db.rollback()  # Finaliza la instantánea REPEATABLE READ de MySQL.
    db.expire_all()
    assert db.query(AppArchivo).count()==8
    assert db.get(AppCopiaDrive,archivo['id']).estado=='ELIMINADA'
    assert db.query(AppEvento).filter(AppEvento.motivo=='EVIDENCIA_RETIRADA').count()==1


def test_no_se_asocia_evidencia_a_bulto_de_otra_recepcion(cliente,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    rec(cliente);rec(cliente,'OTRA')
    uid=cliente.post('/api/operacion/recepciones/OTRA/bultos',json={'cantidad':1}).json()['unidades'][0]['id']
    r=foto(cliente,'INGRESO',unidadId=uid)
    assert r.status_code==422 and not list(tmp_path.glob('app_archivos/*'))


def test_copia_drive_abierta_reintenta_y_elimina_local_solo_con_confirmacion(cliente,db,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    drive._verificados.clear()
    rec(cliente);f=foto(cliente,'INGRESO',sku='SKU1',categoria='PNC').json()
    monkeypatch.setattr(entregas,'configurado',lambda *a:True)
    llamadas=[]
    def puente(op,clave,d):
        llamadas.append((op,d))
        if op=='estado':return {'versionPuente':2,'remitente':'sup'}
        raise RuntimeError('Interrupción de prueba')
    monkeypatch.setattr(entregas,'llamar',puente)
    assert drive.procesar_uno()
    assert (tmp_path/'app_archivos'/f['id']).exists()
    db.rollback();db.expire_all();j=db.get(AppCopiaDrive,f['id']);j.proximo_en=utcnow();db.commit()
    def confirmado(op,clave,d):
        if op=='estado':return {'versionPuente':2,'remitente':'sup'}
        assert d['ruta']==['PNC','SKU1','ADICIONAL'] and d['cliente']=='VENTURA'
        return {'exito':True,'fileId':'drive-confirmada','carpetaRecepcionUrl':'https://drive.google.com/folders/recepcion'}
    monkeypatch.setattr(entregas,'llamar',confirmado)
    assert drive.procesar_uno()
    db.rollback();db.expire_all()
    assert db.get(AppArchivo,f['id']).drive_id=='drive-confirmada'
    assert db.get(AppCopiaDrive,f['id']).estado=='COPIADA'
    assert not (tmp_path/'app_archivos'/f['id']).exists()


def test_puente_antiguo_no_sube_imagen_en_ubicacion_incorrecta(cliente,db,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path);drive._verificados.clear()
    rec(cliente);f=foto(cliente,'INGRESO').json()
    monkeypatch.setattr(entregas,'configurado',lambda *a:True)
    llamadas=[]
    def antiguo(op,*a):llamadas.append(op);return {'exito':True,'remitente':'sup'}
    monkeypatch.setattr(entregas,'llamar',antiguo)
    assert drive.procesar_uno() and llamadas==['estado']
    assert (tmp_path/'app_archivos'/f['id']).exists()


def test_resolver_qr_y_prefijos_no_modifica_digitos_sin_confirmar(cliente,db):
    rec(cliente)
    for sku in ['2GJ823308A','7610022DRS0200','000123','P555']:
        db.add(Producto(sku=sku,cliente='VENTURA'))
        db.add(AppSku(recepcion='INGRESO',sku=sku,esperado=1,contado=0,estado='PENDIENTE'))
    db.commit()
    q=lecturas.resolver(db,json.dumps({'partNumber':'7610022DRS0200','lot':'F20241209-037001','qty':1}),'INGRESO')
    assert q['sku']=='7610022DRS0200' and q['resuelto']
    q=lecturas.resolver(db,'2GJ-823-302-A','INGRESO')
    assert q['resuelto'] is False and q['confirmar'] and q['candidatos']==['2GJ823308A']
    assert lecturas.resolver(db,'P7610022DRS0200','INGRESO')['confirmar']
    assert lecturas.resolver(db,'000123','INGRESO')['sku']=='000123'
    assert lecturas.resolver(db,'P555','INGRESO')['sku']=='P555'
    assert lecturas.resolver(db,'https://proveedor.test/qr?sku=7610022DRS0200&qty=7','INGRESO')['sku']=='7610022DRS0200'


def test_stock_posiciones_separadas_por_cliente_y_horarios_ecuador(db):
    filas=[{'sku':'SKU','cliente':'VENTURA','posicion':'BM-A1','stock':3},
           {'sku':'SKU','cliente':'VENTURA','posicion':'BM-B2','stock':4},
           {'sku':'SKU','cliente':'FACTOR','posicion':'BM-C3','stock':99}]
    guardar_posiciones(db,filas);db.commit()
    assert posiciones_de(db,'SKU','VENTURA')['stock']==7
    assert len(posiciones_de(db,'SKU','VENTURA')['posiciones'])==2
    assert posiciones_de(db,'SKU')['stockDisponible'] is False
    assert posiciones_de(db,'OTRO','VENTURA')['stock'] is None
    cfg={'activo':True,'horas':[8,10,15],'zona':'America/Guayaquil'}
    for hora,turno in [(12,None),(13,'08'),(15,'10'),(20,'15')]:
        r=turno_pendiente(datetime(2026,10,15,hora,tzinfo=timezone.utc),cfg)
        assert (r.rsplit(':',1)[-1] if r else None)==turno


def impresora(admin,host='127.0.0.1',puerto=9100):
    c=admin.get('/api/operacion/config').json()
    c['impresoras']=[{'id':'MESA','nombre':'Zebra de prueba','host':host,'puerto':puerto,'equipo':'PC-PRUEBA'}]
    assert admin.put('/api/operacion/config',json=c).status_code==200
    return admin.post('/api/impresion/estaciones/MESA/token',json={}).json()['token']


def test_cola_etiqueta_unitaria_siete_copias_y_reserva_unica(admin,cliente,db):
    token=impresora(admin)
    body={'estacion':'MESA','copias':7,'clave':'solicitud-unica-1234','etiqueta':{'sku':'SKU1','cantidad':7,'descripcion':'pieza'}}
    r=cliente.post('/api/impresion/trabajos',json=body);assert r.status_code==201,r.text
    assert cliente.post('/api/impresion/trabajos',json=body).json()['id']==r.json()['id']
    assert db.query(AppImpresion).count()==1
    j=db.get(AppImpresion,r.json()['id'])
    assert j.datos['cantidadPorEtiqueta']==1 and '^PQ7' in j.datos['zpl']
    assert 'tokenHash' not in admin.get('/api/operacion/config').text
    assert TestClient(app).post('/api/impresion/agente/MESA/siguiente',json={'equipo':'PC-PRUEBA'}).status_code==401
    headers={'Authorization':'Bearer '+token};a=TestClient(app)
    j=a.post('/api/impresion/agente/MESA/siguiente',json={'equipo':'PC-PRUEBA'},headers=headers).json()['trabajo']
    assert j
    assert a.post('/api/impresion/agente/MESA/siguiente',json={'equipo':'PC-PRUEBA'},headers=headers).json()['trabajo'] is None
    assert a.post('/api/impresion/agente/MESA/confirmar',json={'id':j['id'],'reserva':'erronea','estado':'ENVIADA'},headers=headers).status_code==409
    assert a.post('/api/impresion/agente/MESA/confirmar',json={**j,'estado':'ENVIADA'},headers=headers).json()['estado']=='ENVIADA'


def test_agente_respuesta_perdida_no_reimprime(admin,cliente,tmp_path):
    ruta=Path(__file__).parents[1]/'scripts/agente_impresion.py'
    spec=importlib.util.spec_from_file_location('agente',ruta);agente=importlib.util.module_from_spec(spec);spec.loader.exec_module(agente)
    servidor=socket.socket();servidor.bind(('127.0.0.1',0));servidor.listen(1);servidor.settimeout(5)
    recibidos=[]
    def recibir():
        with servidor:
            s,_=servidor.accept()
            with s:
                partes=[]
                while b:=s.recv(8192):partes.append(b)
                recibidos.append(b''.join(partes))
    hilo=threading.Thread(target=recibir);hilo.start()
    token=impresora(admin,puerto=servidor.getsockname()[1])
    r=cliente.post('/api/impresion/trabajos',json={'estacion':'MESA','copias':7,'clave':'prueba-agente-1234','etiqueta':{'sku':'SKU1'}})
    assert r.status_code==201
    a=TestClient(app);fallar=[True]
    def transport(req):
        if req.url.path.endswith('/confirmar') and fallar[0]:
            fallar[0]=False;return httpx.Response(503,json={'detail':'respuesta perdida'})
        r=a.request(req.method,req.url.path,content=req.content,headers=dict(req.headers))
        return httpx.Response(r.status_code,json=r.json())
    c={'servidor':'http://testserver','estacion':'MESA','token':token}
    with httpx.Client(transport=httpx.MockTransport(transport)) as http:
        with pytest.raises(httpx.HTTPStatusError):agente.ciclo(c,tmp_path,http,'PC-PRUEBA')
        assert agente.ciclo(c,tmp_path,http,'PC-PRUEBA') is False
    hilo.join(6)
    assert len(recibidos)==1 and b'^PQ7' in recibidos[0]


def test_retirada_no_resucita_por_reintentar_la_misma_foto(cliente,db,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    rec(cliente)
    a=foto(cliente,'INGRESO',sku='SKU1').json()
    assert cliente.delete('/api/operacion/evidencias/'+a['id']).status_code==200
    assert foto(cliente,'INGRESO',sku='SKU1').status_code==409
    db.rollback()
    assert db.query(AppEvidencia).filter(AppEvidencia.eliminado_en.is_(None)).count()==0


def test_contexto_bulto_y_lista_no_mezcla_fotos_de_otro_sku(cliente,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path);rec(cliente)
    uid=cliente.post('/api/operacion/recepciones/INGRESO/bultos',json={'cantidad':1}).json()['unidades'][0]['id']
    contexto=foto(cliente,'INGRESO',variante=1,unidadId=uid,tipoEvidencia='ETIQUETA_CAJA').json()
    propia=foto(cliente,'INGRESO',variante=2,sku='SKU1',unidadId=uid).json()
    foto(cliente,'INGRESO',variante=3,sku='OTRO',unidadId=uid)
    assert cliente.get('/api/app/recepciones/INGRESO/imagenes?sku=SKU1').json()['total']==1
    r=cliente.get('/api/app/recepciones/INGRESO/imagenes?sku=SKU1&contexto=true').json()
    assert {a['id'] for a in r['archivos']}=={contexto['id'],propia['id']}
    assert all(a['evidencias'] for a in r['archivos'])


def test_reporte_sql_tiene_logo_y_no_ejecuta_formulas(cliente,monkeypatch,tmp_path):
    import io
    import zipfile
    from openpyxl import load_workbook
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path);rec(cliente)
    foto(cliente,'INGRESO',origen='=FORMULA()',categoria='PNC')
    r=cliente.get('/api/operacion/recepciones/INGRESO/evidencias.xlsx')
    assert r.status_code==200
    b=load_workbook(io.BytesIO(r.content));assert b.active['L6'].value=='=FORMULA()'
    assert b.active['L6'].data_type=='s'
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert any(n.startswith('xl/media/') for n in z.namelist())


def test_catalogo_programado_una_ejecucion_por_turno(cliente,db,monkeypatch):
    from app.services import catalogo_programado as tareas,depot,integraciones
    class API:
        configurada=True
    monkeypatch.setattr(integraciones,'credenciales',lambda db:[])
    monkeypatch.setattr(depot,'DepotAPI',API)
    llamadas=[]
    def sincronizar(db,**kw):llamadas.append(kw);return {'productos':7}
    monkeypatch.setattr(depot,'sincronizar_maestro',sincronizar)
    for hora,total in [(13,1),(13,1),(15,2),(15,2),(20,3),(21,3)]:
        tareas.sincronizar_turno(datetime(2026,10,15,hora,tzinfo=timezone.utc))
        assert len(llamadas)==total


def test_bloqueo_fotos_solo_si_admin_lo_habilita_y_operador_no_modifica_formato(admin,cliente):
    rec(cliente)
    c=admin.get('/api/operacion/config').json();c['evidencias']['bloquear']=True
    assert admin.put('/api/operacion/config',json=c).status_code==200
    assert cliente.put('/api/operacion/recepciones/INGRESO/ingreso',json={'protocolo':'REGLAMENTARIO'}).status_code==200
    version=cliente.get('/api/operacion/recepciones/INGRESO/ingreso').json()['version']
    r=cliente.put('/api/operacion/recepciones/INGRESO/ingreso',json={'paso':'PACKING','version':version})
    assert r.status_code==409 and 'recomendaciones' in r.text
    assert cliente.put('/api/operacion/formatos-packing/VENTURA',json={}).status_code==403


def test_ingreso_sin_fotos_permita_packing_y_conteo_con_decision_auditada(admin,cliente):
    rec(cliente)
    config=admin.get('/api/operacion/config').json();config['evidencias']['bloquear']=True
    assert admin.put('/api/operacion/config',json=config).status_code==200
    ruta='/api/operacion/recepciones/INGRESO/ingreso'
    op=TestClient(app);op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    assert op.put(ruta,json={'protocolo':'SIN_FOTOS','paso':'PACKING'}).status_code==403
    for protocolo in ('REGLAMENTARIO','GENERAL'):
        version=cliente.get(ruta).json()['version']
        a=cliente.put(ruta,json={'protocolo':protocolo,'version':version})
        assert a.status_code==200,a.text
        assert cliente.put(ruta,json={'paso':'PACKING','version':a.json()['version']}).status_code==409
    version=cliente.get(ruta).json()['version']
    a=cliente.put(ruta,json={'protocolo':'SIN_FOTOS','paso':'PACKING','version':version})
    assert a.status_code==200,a.text
    assert a.json()['avisos']==[] and a.json()['unidades']==[]
    assert a.json()['responsable']=='sup' and a.json()['protocolo']=='SIN_FOTOS'
    assert cliente.put(ruta,json={'protocolo':'GENERAL','version':version}).status_code==409
    carga=cliente.post('/api/app/recepciones/INGRESO/packing-list',json={'origen':'PRINCIPAL',
        'resultado':{'lineas':[{'linea':1,'sku':'SKU1','cantidad':2}],'porSku':{'SKU1':2},'unidades':2}})
    assert carga.status_code==200,carga.text
    conteo=op.post('/api/app/recepciones/INGRESO/conteos',json={
        'sku':'SKU1','cantidad':1,'pallet':'A1','idempotencyKey':'conteo-recepcion-sin-fotos'})
    assert conteo.status_code==200,conteo.text
    assert cliente.get('/api/app/recepciones/INGRESO/imagenes').json()['total']==0
    eventos=cliente.get('/api/app/recepciones/INGRESO/eventos').json()
    assert any(e.get('protocolo')=='SIN_FOTOS' and e['operadorEmail']=='sup' for e in eventos)


def test_sin_fotos_conserva_evidencias_y_unidades_anteriores(cliente,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path);rec(cliente)
    ruta='/api/operacion/recepciones/INGRESO'
    antes=cliente.post(ruta+'/bultos',json={'cantidad':2}).json()
    archivo=foto(cliente,'INGRESO',unidadId=antes['unidades'][0]['id']).json()
    antes=cliente.get(ruta+'/ingreso').json()
    r=cliente.put(ruta+'/ingreso',json={'protocolo':'SIN_FOTOS','paso':'PACKING','version':antes['version']})
    assert r.status_code==200,r.text
    assert r.json()['unidades']==antes['unidades'] and r.json()['evidencias']==antes['evidencias']
    assert cliente.get(archivo['url']).status_code==200
    # El modo de recepción no se usa como clasificación fotográfica.
    assert foto(cliente,'INGRESO',protocolo='SIN_FOTOS',variante=1).status_code==422
    assert foto(cliente,'INGRESO',protocolo='GENERAL',variante=2).status_code==201
    assert cliente.get(ruta+'/ingreso').json()['protocolo']=='SIN_FOTOS'


def test_identificador_de_conteo_no_se_reutiliza_en_otra_recepcion(cliente):
    for codigo in ['INGRESO','OTRA']:
        rec(cliente,codigo)
        assert cliente.post(f'/api/app/recepciones/{codigo}/packing-list',json={
            'resultado':{'lineas':[{'sku':'SKU1','cantidad':1,'linea':1}], 'porSku':{'SKU1':1},'unidades':1}, 'origen':'PRINCIPAL'}).status_code==200
    cuerpo={'sku':'SKU1','cantidad':1,'pallet':'A1','idempotencyKey':'misma-clave-prueba'}
    assert cliente.post('/api/app/recepciones/INGRESO/conteos',json=cuerpo).status_code==200
    r=cliente.post('/api/app/recepciones/OTRA/conteos',json=cuerpo)
    assert r.status_code==409 and r.json()['detail']['codigo']=='CLAVE_EN_CONFLICTO'
    assert cliente.get('/api/app/recepciones/OTRA/skus').json()[0]['contado']==0


def test_dos_supervisores_no_sobrescriben_bulto_y_foto_obsoleta_no_se_asocia(admin,cliente,db,monkeypatch,tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path);rec(cliente)
    ruta='/api/operacion/recepciones/INGRESO'
    u=cliente.post(ruta+'/bultos',json={'cantidad':2}).json()['unidades'][0]
    barrera=threading.Barrier(2)
    def editar(c,n):
        barrera.wait(timeout=5)
        return c.post(ruta+'/unidades',json={'id':u['id'],'version':u['version'],'codigo':'MADRE-'+n,'observacion':n})
    with ThreadPoolExecutor(max_workers=2) as ex:
        respuestas=list(ex.map(lambda p:editar(*p),[(cliente,'UNO'),(admin,'DOS')]))
    assert sorted(r.status_code for r in respuestas)==[200,409]
    actual=cliente.get(ruta+'/ingreso').json()['unidades'][0]
    assert actual['version']==1 and actual['observacion'] in ('UNO','DOS')
    assert foto(cliente,'INGRESO',unidadId=u['id'],unidadVersion=0).status_code==409
    assert not list(tmp_path.glob('app_archivos/*'))
    r=cliente.post(ruta+'/unidades',json={'id':actual['id'],'version':actual['version'],'pallet':'A1'})
    assert r.status_code==200
    siguiente=r.json()['unidades'][0]
    assert siguiente['codigo']==actual['codigo'] and siguiente['observacion']==actual['observacion']
    assert siguiente['pallet']=='A1' and siguiente['version']==2


def test_ingreso_responsable_automatico_y_revision_no_pierde_embarque(cliente):
    rec(cliente);ruta='/api/operacion/recepciones/INGRESO/ingreso'
    a=cliente.put(ruta,json={'marca':'ISUZU','embarque':'RB-ORIGINAL','responsable':'otra@example.test'}).json()
    assert a['responsable']=='sup'
    assert cliente.put(ruta,json={'marca':'GEELY','version':0}).status_code==409
    b=cliente.put(ruta,json={'protocolo':'GENERAL','version':a['version']})
    assert b.status_code==200 and b.json()['embarque']=='RB-ORIGINAL' and b.json()['marca']=='ISUZU'


def test_corregir_total_solo_quita_bultos_vacios_y_no_pierde_evidencia(cliente,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path);rec(cliente)
    ruta='/api/operacion/recepciones/INGRESO'
    bs=cliente.post(ruta+'/bultos',json={'cantidad':3}).json()['unidades']
    assert cliente.post(ruta+'/bultos',json={'cantidad':2,'cantidadAnterior':3}).status_code==200
    assert cliente.post(ruta+'/bultos',json={'cantidad':4,'cantidadAnterior':3}).status_code==409
    assert foto(cliente,'INGRESO',unidadId=bs[1]['id']).status_code==201
    assert cliente.post(ruta+'/bultos',json={'cantidad':1,'cantidadAnterior':2}).status_code==409
    assert len(cliente.get(ruta+'/ingreso').json()['unidades'])==2


def test_galeria_por_bulto_incluye_cajas_internas_y_excluye_otras(cliente,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path);rec(cliente)
    ruta='/api/operacion/recepciones/INGRESO'
    bs=cliente.post(ruta+'/bultos',json={'cantidad':2}).json()['unidades']
    caja=cliente.post(ruta+'/unidades',json={'tipo':'CAJA_MADRE','codigo':'CAJA1','padreId':bs[0]['id']}).json()['unidades'][-1]
    for i,u in enumerate([bs[0],bs[1],caja]):
        assert foto(cliente,'INGRESO',variante=i,unidadId=u['id']).status_code==201
    r=cliente.get('/api/app/recepciones/INGRESO/imagenes',params={'unidadId':bs[0]['id']}).json()
    assert r['total']==2
    assert cliente.get('/api/app/recepciones/INGRESO/imagenes?unidadId=unidad-inexistente').status_code==422
