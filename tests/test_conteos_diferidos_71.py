from sqlalchemy import select, func
import pytest
from app.models import AppEvento, AppSku
from app.services import app_modelo as m, relacion_codigos as rc


def preparar(db, codigo='OFF71', cantidad=10):
    m.crear_recepcion(db, {'codigo': codigo, 'cliente': 'A'}, 'sup')
    m.guardar_packing_list(db,codigo,{'lineas':[{'linea':1,'sku':'SKU1','cantidad':cantidad}],
        'porSku':{'SKU1':cantidad},'unidades':cantidad},'LISTA')


def cuerpo(id='offline-71-123456', cantidad=4):
    return {'idempotencyKey':id,'sku':'SKU1','cantidad':cantidad,'pallet':'A01','origen':'LISTA',
        'operadorPendiente':'sup','envioDiferido':True,'capturadoEnDispositivo':'2026-11-09T10:00:00-05:00',
        'dispositivoOrigen':'equipo71','observacion':'Conteo físico conservado en el dispositivo'}


def test_confirmacion_perdida_no_duplica_y_conserva_fecha_de_captura(cliente,db):
    preparar(db)
    p=cuerpo();r=cliente.post('/api/app/recepciones/OFF71/conteos',json=p);assert r.status_code==200,r.text
    # Simula que el operario no recibió la respuesta, mientras otro sigue trabajando.
    cliente.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    otro=cliente.post('/api/app/recepciones/OFF71/conteos',json={**cuerpo('otro-71-123456',3),'operadorPendiente':'op1'})
    assert otro.status_code==200,otro.text
    cliente.post('/api/auth/login',json={'usuario':'sup','pin':'1111'})
    repetido=cliente.post('/api/app/recepciones/OFF71/conteos',json=p)
    assert repetido.status_code==200 and repetido.json()['duplicado'] and repetido.json()['contado']==7
    assert repetido.json()['eventoId']==p['idempotencyKey'] and repetido.json()['cantidadRegistrada']==4
    db.rollback()
    assert db.scalar(select(func.count()).select_from(AppEvento).where(AppEvento.tipo=='CONTEO'))==2
    e=db.get(AppEvento,p['idempotencyKey'])
    assert e.datos['capturadoEnDispositivo']==p['capturadoEnDispositivo'] and e.datos['envioDiferido'] is True
    assert e.creado_en is not None


def test_no_firma_pendientes_con_otra_cuenta_en_ninguna_ruta(cliente,db):
    preparar(db)
    for ruta in ['/api/app/recepciones/OFF71/conteos','/api/app/recepciones/OFF71/no-encontrado',
                 '/api/operacion/recepciones/OFF71/conteos-repartidos']:
        r=cliente.post(ruta,json={**cuerpo(),'operadorPendiente':'op1'})
        assert r.status_code==409 and r.json()['detail']['codigo']=='CUENTA_CAMBIADA',r.text
    assert db.scalar(select(func.count()).select_from(AppEvento))==0


def test_reintento_de_otro_operario_no_reconoce_evento_ajeno(cliente,db):
    preparar(db)
    assert cliente.post('/api/app/recepciones/OFF71/conteos',json=cuerpo()).status_code==200
    cliente.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    r=cliente.post('/api/app/recepciones/OFF71/conteos',json={**cuerpo(),'operadorPendiente':'op1'})
    assert r.status_code==409 and r.json()['detail']['codigo']=='CLAVE_EN_CONFLICTO'


def test_sobrante_por_actividad_de_otro_operario_exige_confirmacion(cliente,db):
    preparar(db)
    assert cliente.post('/api/app/recepciones/OFF71/conteos',json=cuerpo('primero-71-123456',8)).status_code==200
    p=cuerpo('segundo-71-123456',4)
    r=cliente.post('/api/app/recepciones/OFF71/conteos',json=p)
    assert r.status_code==409 and r.json()['detail']['codigo']=='CONFIRMAR_SOBRANTE'
    assert db.get(AppEvento,p['idempotencyKey']) is None
    assert cliente.post('/api/app/recepciones/OFF71/conteos',json={**p,'confirmarSobrante':True}).json()['contado']==12


def test_cierre_bloquea_nuevos_pendientes_pero_reconoce_el_ya_confirmado(cliente,db):
    preparar(db)
    p=cuerpo();assert cliente.post('/api/app/recepciones/OFF71/conteos',json=p).status_code==200
    r=m.obtener(db,'OFF71');r.estado='CERRADA';db.commit()
    nuevo=cliente.post('/api/app/recepciones/OFF71/conteos',json=cuerpo('nuevo-71-123456'))
    assert nuevo.status_code==409 and nuevo.json()['detail']['codigo']=='RECEPCION_CERRADA'
    assert cliente.post('/api/app/recepciones/OFF71/conteos',json=p).json()['duplicado'] is True


def test_cero_diferido_no_resta_las_cantidades_de_otros_conteos(cliente,db):
    preparar(db)
    cliente.post('/api/app/recepciones/OFF71/conteos',json=cuerpo())
    r=cliente.post('/api/app/recepciones/OFF71/no-encontrado',json={**cuerpo('cero-71-123456',0),'pallet':''})
    assert r.status_code==200 and r.json()['contado']==4,r.text


def test_manifiesto_local_solo_incluye_cliente_y_sku_de_la_recepcion(cliente,db):
    preparar(db)
    rc.importar(db,[{'cliente':'A','sku':'SKU1','codigoBarras':'012345678905','cantidadReferencia':12},
        {'cliente':'B','sku':'OTRO','codigoBarras':'012345678905','cantidadReferencia':100},
        {'cliente':'A','sku':'FUERA','codigoBarras':'99999','cantidadReferencia':1}],'sup');db.commit()
    r=cliente.get('/api/app/recepciones/OFF71/lecturas-locales');assert r.status_code==200,r.text
    filas=r.json()['lecturas'];assert {f['sku'] for f in filas}=={'SKU1'}
    assert {'SKU1','012345678905','0012345678905'}=={f['codigo'] for f in filas}
    assert next(f for f in filas if f['codigo']=='0012345678905')['unidadesPorCodigo']==12


def test_mysql_varios_operarios_y_reintentos_no_pierden_ni_duplican_conteos(db):
    from app.db import engine, SessionLocal
    from concurrent.futures import ThreadPoolExecutor
    if engine.dialect.name!='mysql':pytest.skip('El bloqueo de fila se verifica en MySQL aislado.')
    preparar(db,cantidad=100)
    def contar(i):
        for n in range(10):
            with SessionLocal() as s:
                p=cuerpo(f'hilo-71-{i:02d}-{n:02d}',1)
                m.registrar_conteo(s,'OFF71',f'operario{i}',p)
                # Pérdida de confirmación y reintento del mismo operario.
                assert m.registrar_conteo(s,'OFF71',f'operario{i}',p)['duplicado'] is True
    with ThreadPoolExecutor(max_workers=4) as ex:list(ex.map(contar,range(4)))
    db.rollback()
    assert db.scalar(select(AppSku.contado).where(AppSku.recepcion=='OFF71'))==40
    assert db.scalar(select(func.count()).select_from(AppEvento).where(AppEvento.recepcion=='OFF71'))==40
