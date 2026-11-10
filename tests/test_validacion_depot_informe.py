"""Sin MAESTRO pesado: procedencia verificable, cliente correcto y correo congelado."""
from app.models import Producto, AppStockDepot, AppConfig, AppEntrega
from app.services.validacion_depot import validar
from app.services import app_modelo as m
from app.services.instantaneas import expandir
from tests.test_remitente_responsable import correo
from tests.test_mejoras_operativas import preparar


def test_ausencia_sin_catalogo_no_afirma_inexistencia(db):
    d=validar(db,'VENTURA',['AUSENTE'])
    assert d['porSku']['AUSENTE']['estado']=='SIN_VALIDAR'
    assert d['porSku']['AUSENTE']['valor']=='PENDIENTE'
    assert d['actualizadoEn'] is None and 'No hay catálogo' in d['metodo']


def test_distingue_api_stock_cero_inactivo_negativo_y_otro_cliente(db):
    db.add_all([Producto(sku='OK',cliente='VENTURA',origen='API'),
        Producto(sku='INACTIVO',cliente='VENTURA',origen='API',inactivo=True),
        Producto(sku='NEGATIVO',cliente='VENTURA',origen='API',existe_depot=False),
        Producto(sku='OTRO',cliente='HYCITE',origen='API'),
        Producto(sku='LOCAL',cliente='VENTURA',origen='LOCAL',existe_depot=False),
        Producto(sku='COMPARTIDO',cliente='HYCITE',origen='API'),
        AppStockDepot(sku='COMPARTIDO',cliente='VENTURA',posiciones=[])]);db.commit()
    d=validar(db,'VENTURA',['OK','INACTIVO','NEGATIVO','OTRO','LOCAL','COMPARTIDO','AUSENTE'])
    assert {s:v['estado'] for s,v in d['porSku'].items()}=={'OK':'OK','INACTIVO':'INACTIVO',
        'NEGATIVO':'NO_REGISTRADO','OTRO':'OTRO_CLIENTE','LOCAL':'NO_ENCONTRADO','COMPARTIDO':'OK','AUSENTE':'NO_ENCONTRADO'}
    assert 'API de stock' in d['metodo'] and d['actualizadoEn']
    assert 'no confirma inexistencia' in d['porSku']['AUSENTE']['nota']
    assert '(Ecuador)' in d['fechaActualizacion']
    assert 'solicitar su creación' in d['porSku']['NEGATIVO']['observacion']
    assert 'habilitación' in d['porSku']['INACTIVO']['observacion']
    assert 'credencial' not in str(d) and 'secreto' not in str(d)


def test_alias_de_cliente_y_fuente_maestro_importado(db):
    db.add(AppConfig(clave='depot:VENTURA',datos={'cliente':'VENTURA/VW','activo':True}))
    db.add(Producto(sku='S',cliente='VENTURA/VW',origen='MAESTRO'));db.commit()
    a=validar(db,'VENTURA',['S']);assert a['porSku']['S']['estado']=='OK'
    assert 'importado del maestro' in a['metodo'] and 'API' not in a['metodo']
    b=validar(db,'HYCITE',['S']);assert b['porSku']['S']['estado']=='OTRO_CLIENTE'


def test_metadatos_sin_fuente_no_reusan_nd_de_formula_y_no_escriben_datos(cliente,db):
    c=preparar(db);ruta=f'/api/operacion/recepciones/{c}/informe-metadatos'
    a=cliente.get(ruta).json();b=cliente.get(ruta).json()
    assert a==b
    assert a['validacionDepot']['porSku']['SKU1']['valor']=='PENDIENTE'
    assert 'No se adjunta la hoja MAESTRO' in a['validacionDepot']['notaMaestro']
    assert cliente.get(f'/api/app/recepciones/{c}/eventos').json()==[]


def test_depot_solo_avisa_internamente_y_catalogo_exige_revisar(cliente,db,correo):
    c,_=correo
    cliente_depot=m.obtener(db,c).cliente
    db.add(Producto(sku='OTROSKU',cliente=cliente_depot,origen='API'));db.commit()
    ruta=f'/api/operacion/recepciones/{c}/correo';v=cliente.get(ruta).json()
    assert 'Productos por verificar en Depot' not in v['html']
    assert 'No se adjunta la hoja MAESTRO' not in v['texto'] and 'SKU1' not in v['texto']
    assert v['validacionDepot']['porSku']['SKU1']['estado']=='NO_ENCONTRADO'
    assert 'antes de cargar cantidades en Depot' not in v['texto']
    db.add(Producto(sku='SKU1',cliente=cliente_depot,origen='API'));db.commit()
    r=cliente.put(ruta,json={'version':v['version'],'campos':{**v['campos'],'notas':'Ubicación revisada'}})
    assert r.status_code==409
    v=cliente.get(ruta).json();assert v['validacionDepot']['porSku']['SKU1']['estado']=='OK'
    r=cliente.put(ruta,json={'version':v['version'],'campos':{**v['campos'],'notas':'Ubicación revisada'}})
    assert r.status_code==200,r.text
    assert 'Ubicación revisada' in r.json()['texto'] and 'Productos por verificar en Depot' not in r.json()['html']


def test_correo_conserva_validacion_emitida_tras_actualizar_catalogo(cliente,db,correo):
    c,datos=correo;ruta=f'/api/operacion/recepciones/{c}/correo'
    v=cliente.get(ruta).json();v=cliente.put(ruta,json={'version':v['version'],
        'campos':{**v['campos'],'destinatarios':datos['destinatarios']}}).json()
    datos['eventos']=[e['id'] for e in cliente.get(f'/api/app/recepciones/{c}/eventos').json()]
    r=cliente.post(f'/api/app/recepciones/{c}/entrega',json={**datos,'modoEntrega':'MANUAL','correoVersion':v['version']})
    assert r.status_code==201,r.text
    db.rollback();db.expire_all();e=db.get(AppEntrega,r.json()['id']);final=expandir(e.datos)['correoFinal']
    assert final['validacionDepot']['porSku']['SKU1']['estado']=='SIN_VALIDAR'
    db.add(Producto(sku='SKU1',cliente='VENTURA',origen='API'));e.estado='ENTREGADA';db.commit()
    emitido=cliente.get(ruta+'?entregaId='+e.id).json()
    assert emitido['html']==final['html'] and emitido['soloLectura']
    assert emitido['validacionDepot']['porSku']['SKU1']['estado']=='SIN_VALIDAR'
