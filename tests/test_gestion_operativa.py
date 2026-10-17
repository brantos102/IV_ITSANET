"""Regresiones: cantidades parciales, permisos, presencia e informes versionados."""
import base64
import io
from datetime import timedelta
from uuid import uuid4
from urllib.parse import quote
import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import select
from app.main import app
from app.models import Operador,Rol,AppPresencia,AppInforme,AppEvento,utcnow
from app.security import hash_pin
from app.services import app_modelo as m,archivos

@pytest.fixture
def admin(cliente,db):
    db.add(Operador(usuario='administrador',nombre='Admin',email='admin@example.test',rol=Rol.ADMIN,pin_hash=hash_pin('123456')));db.commit()
    c=TestClient(app);assert c.post('/api/auth/login',json={'usuario':'administrador','pin':'123456'}).status_code==200
    return c

def recepcion(db,codigo='PARCIAL'):
    m.crear_recepcion(db,{'codigo':codigo,'cliente':'VENTURA'},'sup')
    m.guardar_packing_list(db,codigo,{'lineas':[{'linea':1,'sku':'SKU1','cantidad':6}], 'porSku':{'SKU1':6},'unidades':6},'PL')
    return codigo

def contar(cliente,codigo='PARCIAL',**extra):
    return cliente.post(f'/api/app/recepciones/{codigo}/conteos',json={'sku':'SKU1','cantidad':6,'pallet':'P1','idempotencyKey':uuid4().hex,**extra})

def test_incidencia_parcial_y_anulacion_no_alteran_total(cliente,db):
    codigo=recepcion(db)
    r=contar(cliente,incidencias=[{'tipo':'MAL_ESTADO','cantidad':2}]);assert r.status_code==200,r.text
    assert r.json()['cantidadPnc']==2 and r.json()['cantidadConforme']==4 and r.json()['contado']==6
    doc=cliente.get(f'/api/app/recepciones/{codigo}/skus').json()[0];assert doc['tienePnc'] and doc['cantidadConIncidencia']==2
    db.rollback();db.expire_all();assert m.recalcular_sku(db,codigo,'SKU1')['cantidadPnc']==2
    ident=r.json()['eventoId'];a=cliente.post(f'/api/app/recepciones/{codigo}/conteos/{ident}/anular',json={'motivo':'conteo corregido'})
    assert a.status_code==200,a.text
    s=cliente.get(f'/api/app/recepciones/{codigo}/skus').json()[0];assert s['contado']==0 and s['cantidadPnc']==0 and not s['tienePnc']

@pytest.mark.parametrize('inc',[ [{'tipo':'MAL_ESTADO','cantidad':7}], [{'tipo':'MAL_ESTADO','cantidad':-1}], [{'tipo':'FALTANTE','cantidad':1}], [{'tipo':'MAL_ESTADO','cantidad':4},{'tipo':'INCORRECTO','cantidad':3}] ])
def test_clasificacion_invalida_no_registra_conteo(cliente,db,inc):
    recepcion(db);r=contar(cliente,incidencias=inc);assert r.status_code==422,r.text
    assert cliente.get('/api/app/recepciones/PARCIAL/eventos').json()==[]

def test_correccion_calidad_mantiene_libro_mayor(cliente,db):
    recepcion(db);r=contar(cliente,estadoFisico='PNC');assert r.json()['cantidadPnc']==6
    ident=r.json()['eventoId'];u=cliente.post(f'/api/operacion/recepciones/PARCIAL/eventos/{ident}/calidad',json={'motivo':'Solo dos rotos','incidencias':[{'tipo':'MAL_ESTADO','cantidad':2}]})
    assert u.status_code==200,u.text
    assert u.json()['contado']==6 and u.json()['cantidadPnc']==2 and u.json()['cantidadConforme']==4
    assert len(cliente.get('/api/app/recepciones/PARCIAL/eventos').json())==2


def test_supervisor_aprueba_y_promueve_sin_poder_asignar_admin(admin,cliente,db):
    nuevo=cliente.post('/api/auth/operadores',json={'usuario':'nuevo','nombre':'Nuevo supervisor','email':'nuevo@example.test','pin':'abcdef','rol':'SUPERVISOR'})
    assert nuevo.status_code==201,nuevo.text
    assert cliente.patch('/api/auth/operadores/'+str(nuevo.json()['id']),json={'rol':'ADMIN'}).status_code==403
    politicas=admin.get('/api/operacion/politicas').json();politicas['permisos']['SUPERVISOR']['asignarSupervisor']=False
    assert admin.put('/api/operacion/politicas',json=politicas).status_code==200
    assert cliente.patch('/api/auth/operadores/'+str(nuevo.json()['id']),json={'rol':'OPERADOR'}).status_code==403
    assert cliente.get('/api/operacion/politicas').status_code==403
    assert cliente.get('/api/app/estado').status_code==403
    assert admin.get('/api/app/estado').status_code==200
    assert cliente.get('/api/auth/yo').json()['permisos']['asignarSupervisor'] is False


def test_cliente_sin_pallet_y_posicion_configurable(admin,cliente,db):
    recepcion(db)
    p=admin.get('/api/operacion/politicas').json();p['clientes']['VENTURA']={'palletRequerido':False,'posicionRequerida':False,'columnas':{'marca':0,'codigoBarra':12,'cantidadIncidencia':15,'incidencia':16,'observacion':17,'evidencia':18}}
    assert admin.put('/api/operacion/politicas',json=p).status_code==200
    assert contar(cliente,cantidad=1,pallet='').status_code==200
    p['clientes']['VENTURA']['posicionRequerida']=True;assert admin.put('/api/operacion/politicas',json=p).status_code==200
    assert contar(cliente,cantidad=1,pallet='').status_code==422
    assert contar(cliente,cantidad=1,pallet='',posicionReal='A01').status_code==200


@pytest.mark.parametrize('nombre', ['VENTURA/VW', 'IMPOFACTOR / IMPOVENTURA', 'VENTURA'])
def test_reglas_de_cliente_con_barra_abren_recepcion_existente_sin_cambiar_conteos(admin,cliente,db,nombre):
    codigo='RECEPCION-EXISTENTE'
    m.crear_recepcion(db,{'codigo':codigo,'cliente':nombre},'sup')
    m.guardar_packing_list(db,codigo,{'lineas':[{'linea':1,'sku':'SKU1','cantidad':6}],
        'porSku':{'SKU1':6},'unidades':6},'PL')
    assert contar(cliente,codigo,cantidad=2).status_code==200
    politica=admin.get('/api/operacion/politicas').json()
    politica['clientes'][nombre]={'palletRequerido':False,'posicionRequerida':True}
    assert admin.put('/api/operacion/politicas',json=politica).status_code==200
    recibida=cliente.get(f'/api/app/recepciones/{codigo}').json()
    antes=cliente.get(f'/api/app/recepciones/{codigo}/skus').json()
    eventos=cliente.get(f'/api/app/recepciones/{codigo}/eventos').json()
    for identificador in (quote(recibida['cliente'],safe=''), recibida['cliente']):
        r=cliente.get('/api/operacion/reglas/'+identificador)
        assert r.status_code==200,r.text
        assert r.json()['palletRequerido'] is False
        assert r.json()['posicionRequerida'] is True
        assert {i['codigo'] for i in r.json()['incidencias']}=={i['codigo'] for i in politica['incidencias']}
    assert cliente.get(f'/api/app/recepciones/{codigo}').json()==recibida
    assert cliente.get(f'/api/app/recepciones/{codigo}/skus').json()==antes
    assert antes[0]['contado']==2
    assert cliente.get(f'/api/app/recepciones/{codigo}/eventos').json()==eventos
    # La consulta no rebaja las reglas al valor predeterminado de otro cliente.
    assert contar(cliente,codigo,cantidad=1,pallet='').status_code==422
    assert contar(cliente,codigo,cantidad=1,pallet='',posicionReal='A01').status_code==200
    anonimo=TestClient(app)
    assert anonimo.get('/api/operacion/reglas/'+quote(nombre,safe='')).status_code==401


def test_presencia_expira_y_cierra_solo_su_sesion(cliente,db):
    codigo=recepcion(db);ruta=f'/api/operacion/recepciones/{codigo}'
    assert cliente.put(ruta+'/presencia',json={'dispositivo':'pestana-1234','actividad':'CONTANDO'}).status_code==200
    assert len(cliente.get(ruta+'/equipo').json()['equipoActivo'])==1
    db.rollback();p=db.get(AppPresencia,(codigo,'pestana-1234'));p.visto_en=utcnow().replace(tzinfo=None)-timedelta(seconds=121);db.commit()
    assert cliente.get(ruta+'/equipo').json()['equipoActivo']==[]
    cliente.put(ruta+'/presencia',json={'dispositivo':'pestana-1234'});cliente.post('/api/auth/logout')
    db.rollback();db.expire_all();assert db.get(AppPresencia,(codigo,'pestana-1234')) is None


def test_cerrada_muestra_contado_y_cien_revisado_aunque_falte(cliente,db):
    codigo=recepcion(db);r=contar(cliente,cantidad=5);assert r.status_code==200
    db.rollback();m.cerrar_recepcion(db,codigo,'sup')
    listado=cliente.get('/api/app/recepciones').json()[0]
    assert listado['seguimiento']['contado']==5 and listado['seguimiento']['avance']==100


def test_informe_secuencia_conflicto_y_descarga_auditada(cliente,db,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    codigo=recepcion(db);ruta=f'/api/operacion/recepciones/{codigo}/informes'
    f=cliente.post(ruta,json={'clave':'generacion-uno','tipo':'DESCARGA','ultimoVisto':None});assert f.status_code==200,f.text
    f=f.json();assert f['numero']==1 and '_R0001_' in f['sufijo']
    assert cliente.post(ruta,json={'clave':'generacion-dos','tipo':'DESCARGA','ultimoVisto':None}).status_code==409
    w=Workbook();w.active.append(['SKU','CONTADO']);w.active.append(['SKU1',0]);b=io.BytesIO();w.save(b)
    adjunto={'nombre':'informe'+f['sufijo']+'.xlsx','base64':base64.b64encode(b.getvalue()).decode()}
    a=cliente.put(ruta+'/'+f['id'],json={'adjuntos':[adjunto]});assert a.status_code==200,a.text
    a=a.json();assert a['estado']=='GENERADO'
    descarga=cliente.get(a['archivos'][0]['url']);assert descarga.status_code==200 and descarga.content==b.getvalue()
    h=cliente.get(ruta).json()[0];assert h['descargas'][0]['usuario']=='sup'
    nuevo=cliente.post(ruta,json={'clave':'generacion-dos','tipo':'DESCARGA','ultimoVisto':f['id']});assert nuevo.json()['numero']==2
    assert contar(cliente,cantidad=1).status_code==200
    assert cliente.put(ruta+'/'+nuevo.json()['id'],json={'adjuntos':[adjunto]}).status_code==409


def test_email_responsable_solo_admin_y_sin_duplicados(admin,cliente,db,operadores):
    ident=operadores['sup'].id
    assert cliente.patch(f'/api/auth/operadores/{ident}',json={'email':'bespinoza@itsanet.com'}).status_code==403
    assert admin.patch(f'/api/auth/operadores/{ident}',json={'email':'bespinoza@itsanet.com'}).status_code==200
    assert admin.patch(f'/api/auth/operadores/{operadores["op1"].id}',json={'email':'bespinoza@itsanet.com'}).status_code==409
    assert admin.patch(f'/api/auth/operadores/{ident}',json={'email':'invalido'}).status_code==422


def test_correo_prueba_solo_admin_y_cuenta_real(admin,cliente,db,operadores,monkeypatch):
    from app.services import entregas
    op=operadores['sup'];op.email='bespinoza@itsanet.com';db.commit()
    llamadas=[]
    def llamar(accion,clave,datos):
        llamadas.append((accion,datos))
        return {'exito':True,'remitente':'bespinoza@itsanet.com','capacidades':['pruebaCorreo'],'carpeta':'https://drive.google.com/drive/folders/prueba'}
    monkeypatch.setattr(entregas,'llamar',llamar)
    datos={'supervisor':'bespinoza@itsanet.com','destinatario':'brantos102@gmail.com','clave':'a'*32}
    assert cliente.post('/api/app/integraciones/google/correo-prueba',json=datos).status_code==403
    assert not llamadas
    r=admin.post('/api/app/integraciones/google/correo-prueba',json=datos)
    assert r.status_code==200,r.text
    assert [x[0] for x in llamadas]==['estado','pruebaCorreo']
    assert r.json()['remitente']=='bespinoza@itsanet.com'
    assert admin.post('/api/app/integraciones/google/correo-prueba',json={**datos,'supervisor':'otro@itsanet.com'}).status_code==422


def test_cierre_usa_informe_archivado_y_no_envia_dos_veces(cliente,db,tmp_path,monkeypatch):
    from app.models import AppEntrega
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    codigo=recepcion(db);assert contar(cliente).status_code==200
    ruta=f'/api/operacion/recepciones/{codigo}/informes'
    f=cliente.post(ruta,json={'clave':'informe-final','tipo':'CORREO','ultimoVisto':None}).json()
    w=Workbook();w.active.append(['SKU','CONTADO']);w.active.append(['SKU1',6]);b=io.BytesIO();w.save(b)
    adjunto={'nombre':'informe'+f['sufijo']+'.xlsx','base64':base64.b64encode(b.getvalue()).decode()}
    a=cliente.put(ruta+'/'+f['id'],json={'adjuntos':[adjunto]});assert a.status_code==200,a.text
    eventos=[e['id'] for e in cliente.get(f'/api/app/recepciones/{codigo}/eventos').json()]
    payload={'informeId':f['id'],'adjuntos':[adjunto],'eventos':eventos,'destinatarios':'destino@example.test'}
    e=cliente.post(f'/api/app/recepciones/{codigo}/entrega',json=payload);assert e.status_code==201,e.text
    assert cliente.get(ruta).json()[0]['estado']=='EN_COLA'
    repetido=cliente.post(f'/api/app/recepciones/{codigo}/entrega',json=payload);assert repetido.json()['id']==e.json()['id']
    db.rollback();db.expire_all();assert len(list(db.scalars(select(AppEntrega))))==1
    from app import config
    from app.services import entregas
    monkeypatch.setattr(config,'VAL_GOOGLE_PROXY_URL','https://script.google.com/macros/s/test/exec')
    monkeypatch.setattr(config,'VAL_GOOGLE_PROXY_SECRET','s'*40)
    monkeypatch.setattr(entregas,'llamar',lambda accion,clave,datos:{'exito':True,'remitente':'sup','fileId':clave.split(':')[-1],'carpeta':'https://drive.google.com/drive/folders/prueba'})
    assert entregas.procesar_uno()
    final=cliente.get(ruta).json()[0]
    assert final['estado']=='ENVIADO' and final['confirmadoEn'] and final['destinatarios']=='destino@example.test'


def test_columnas_por_lista_controlan_version_y_conservan_cabecera(cliente,db):
    codigo='FORMATO';m.crear_recepcion(db,{'codigo':codigo,'cliente':'VENTURA'},'sup')
    m.guardar_packing_list(db,codigo,{'lineas':[{'linea':1,'sku':'S','cantidad':1,'cruda':['S',1,'']}], 'porSku':{'S':1},'unidades':1,'encabezados':['ITEM','CANTIDAD','INCIDENCIA'],'columnas':{'sku':0,'cantidad':1}},'PL')
    ruta=f'/api/operacion/recepciones/{codigo}'
    meta=cliente.get(ruta+'/informe-metadatos').json()
    r=cliente.put(ruta+'/columnas-informe',json={'version':meta['versionFormatos'],'origen':'PL','columnas':{'incidencia':2}});assert r.status_code==200,r.text
    assert cliente.put(ruta+'/columnas-informe',json={'version':meta['versionFormatos'],'origen':'PL','columnas':{'incidencia':1}}).status_code==409
    nuevo=cliente.get(ruta+'/informe-metadatos').json();assert nuevo['formatos']['PL']['encabezados']==meta['formatos']['PL']['encabezados']
    assert nuevo['formatos']['PL']['salida']=={'incidencia':2}


def test_borrar_recepcion_con_proyeccion_y_presencia(cliente,db,admin):
    recepcion(db);assert contar(cliente,incidencias=[{'tipo':'MAL_ESTADO','cantidad':2}]).status_code==200
    assert cliente.put('/api/operacion/recepciones/PARCIAL/presencia',json={'dispositivo':'pantalla-1234'}).status_code==200
    assert admin.delete('/api/app/recepciones/PARCIAL').status_code==200
    assert cliente.get('/api/app/recepciones').json()==[]


def test_dos_supervisores_no_reservan_a_ciegas_la_misma_version(cliente,db):
    import threading
    from fastapi import HTTPException
    from app.db import SessionLocal
    from app.services import informes
    codigo=recepcion(db);barrera=threading.Barrier(2);resultados=[]
    def reservar(n):
        with SessionLocal() as sesion:
            barrera.wait(timeout=10)
            try:
                f=informes.reservar(sesion,codigo,{'clave':f'concurrencia-informe-{n}','ultimoVisto':None,'tipo':'DESCARGA'},f'supervisor{n}')
                resultados.append(f['numero'])
            except HTTPException as exc:
                sesion.rollback();resultados.append(exc.status_code)
    hilos=[threading.Thread(target=reservar,args=(n,)) for n in range(2)]
    for h in hilos:h.start()
    for h in hilos:h.join(timeout=20)
    assert not any(h.is_alive() for h in hilos)
    assert sorted(resultados)==[1,409]


def test_novedad_fisica_aparece_en_resumen_aunque_cuadren_cantidades(cliente,db):
    from app.services.entregas import resumen_final
    recepcion(db);assert contar(cliente,incidencias=[{'tipo':'MAL_ESTADO','cantidad':2}]).status_code==200
    s=cliente.get('/api/app/recepciones/PARCIAL/skus').json()
    r=resumen_final(s);assert r['unidadesPnc']==2 and r['novedades'][0]['cantidadConforme']==4
    assert r['unidadesFisicas']==6 and r['discrepancias']==[]


def test_reintento_idempotente_respeta_lo_guardado_aunque_cambien_reglas(admin,cliente,db):
    recepcion(db)
    p=admin.get('/api/operacion/politicas').json();p['clientes']['VENTURA']={'palletRequerido':False,'posicionRequerida':False}
    assert admin.put('/api/operacion/politicas',json=p).status_code==200
    datos={'sku':'SKU1','cantidad':6,'pallet':'','idempotencyKey':'reintento-sin-pallet','incidencias':[{'tipo':'MAL_ESTADO','cantidad':2}]}
    ruta='/api/app/recepciones/PARCIAL/conteos';r=cliente.post(ruta,json=datos);assert r.status_code==200,r.text
    p['clientes']['VENTURA']['palletRequerido']=True;assert admin.put('/api/operacion/politicas',json=p).status_code==200
    repetido=cliente.post(ruta,json=datos);assert repetido.status_code==200,repetido.text
    assert repetido.json()['duplicado'] and repetido.json()['contado']==6 and repetido.json()['cantidadPnc']==2


def test_final_con_columna_drive_espera_links_pero_avance_no_bloquea(cliente,db):
    from app.models import AppArchivo,AppEvidencia
    codigo='ENLACES';m.crear_recepcion(db,{'codigo':codigo,'cliente':'VENTURA'},'sup')
    m.guardar_packing_list(db,codigo,{'lineas':[{'linea':1,'sku':'S','cantidad':1}], 'porSku':{'S':1},'unidades':1,'encabezados':['ITEM','CANTIDAD','FOTOS'],'columnas':{'sku':0,'cantidad':1,'evidencia':2}},'PL')
    a=AppArchivo(id='a'*32,recepcion=codigo,tipo='foto',nombre='foto.png',mime='image/png',sha256='b'*64,bytes=10,usuario='sup');db.add(a);db.flush()
    db.add(AppEvidencia(id='c'*32,archivo_id=a.id,recepcion=codigo,sku='S',categoria='PNC',tipo='ITEM_NOVEDAD',protocolo='COTIDIANO',usuario='sup'));db.commit()
    ruta=f'/api/operacion/recepciones/{codigo}/informes'
    assert cliente.post(ruta,json={'clave':'enlaces-final','tipo':'CORREO','ultimoVisto':None}).status_code==409
    assert cliente.post(ruta,json={'clave':'enlaces-avance','tipo':'DESCARGA','ultimoVisto':None}).status_code==200
