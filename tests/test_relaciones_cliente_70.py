import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from app.models import ProductoRelacion,AppEvento,AppUnidadLogistica,AppRecepcion
from app.services import app_modelo as m,relacion_codigos as rc,etiquetas_bultos as eb,operacion


def test_lectura_por_cliente_no_cruza_sku_y_no_registra_unidades(cliente,db):
    filas=[{'cliente':'A','sku':'SKU-A','codigoBarras':'0001234567890','cantidadReferencia':10},
           {'cliente':'B','sku':'SKU-B','codigoBarras':'0001234567890','cantidadReferencia':100}]
    for _ in range(2):
        r=cliente.post('/api/app/catalogo/relaciones/importar',json={'filas':filas});assert r.status_code==200,r.text
    assert db.scalar(select(func.count()).select_from(ProductoRelacion))==2
    for c,s,n in [('A','SKUA',10),('B','SKUB',100)]:
        m.crear_recepcion(db,{'codigo':'R-'+c,'cliente':c},'sup')
        m.guardar_packing_list(db,'R-'+c,{'lineas':[{'linea':1,'sku':s,'cantidad':n}],'porSku':{s:n},'unidades':n},'L')
        p=cliente.get('/api/app/catalogo/0001234567890',params={'cliente':c});assert p.status_code==200,p.text
        assert p.json()['sku']==s and p.json()['otroCliente'] is False
        l=cliente.post('/api/operacion/lecturas/resolver',json={'lectura':'0001234567890','recepcion':'R-'+c})
        assert l.status_code==200,l.text
        assert l.json()['sku']==s and l.json()['unidadesPorCodigo']==n
    assert cliente.get('/api/app/catalogo/0001234567890').status_code==409
    r=cliente.get('/api/app/recepciones-abiertas/por-codigo/0001234567890')
    assert {x['codigo'] for x in r.json()['recepciones']}=={'R-A','R-B'}
    assert db.scalar(select(func.count()).select_from(AppEvento))==0


def test_conflicto_importacion_no_cambia_relaciones_previas(cliente,db):
    url='/api/app/catalogo/relaciones/importar';f={'cliente':'A','sku':'S1','codigoBarras':'001','cantidadReferencia':2}
    assert cliente.post(url,json={'filas':[f]}).status_code==200
    r=cliente.post(url,json={'filas':[{**f,'codigoBarras':'002'},{**f,'sku':'OTRO'}]})
    assert r.status_code==409
    db.expire_all();assert db.scalar(select(func.count()).select_from(ProductoRelacion))==1
    assert db.get(ProductoRelacion,('A','001')).sku=='S1'
    # Mismo alias con separadores y un factor vacío: conservar el factor conocido.
    rc.importar(db,[{**f,'codigoBarras':'0-01'},{**f,'cantidadReferencia':None}],'sup');db.commit()
    assert db.get(ProductoRelacion,('A','001')).cantidad_referencia==2
    with pytest.raises(HTTPException):rc.importar(db,[f,{**f,'cantidadReferencia':3}],'sup')


def test_upc_y_ean_solo_se_equivalen_con_control_valido_y_cliente(db):
    rc.importar(db,[{'cliente':'A','sku':'S','codigoBarras':'012345678905','cantidadReferencia':12}],'sup');db.commit()
    assert rc.candidatos(db,'0012345678905','A')[0].sku=='S'
    assert rc.detalle(db,'0012345678905','A')['unidadesPorCodigo']==12
    assert rc.candidatos(db,'0012345678905','B')==[]
    assert rc.variantes('0012345678906')==['0012345678906']


def test_subbulto_solo_de_unidad_registrada_y_reimpresion_estable(cliente,db):
    m.crear_recepcion(db,{'codigo':'SUB-70','cliente':'PRUEBA','bultos':2},'sup')
    j=eb.generar(db,'SUB-70',{'clave':'padre-70-123456','version':0,'cantidadAnterior':2,'total':2,
        'literal':'A','formato':'100x50','destino':'NAVEGADOR','numeros':[1,2]},'sup')
    padre=db.scalar(select(AppUnidadLogistica).where(AppUnidadLogistica.recepcion=='SUB-70',AppUnidadLogistica.numero==1))
    hijo=AppUnidadLogistica(id='c'*32,recepcion='SUB-70',tipo='CAJA_MADRE',numero=1,padre_id=padre.id,codigo='CAJA',datos={})
    db.add(hijo);db.commit();e=eb.estado(db,'SUB-70');assert e['subbultos'][0]['rotulo']=='A01.1'
    d={'clave':'hijo-70-123456','version':e['version'],'cantidadAnterior':2,'unidadIds':[hijo.id],
       'formato':'100x50','destino':'NAVEGADOR'}
    r=cliente.post('/api/impresion/recepciones/SUB-70/subbultos',json=d);assert r.status_code==201,r.text
    assert r.json()['copias']==1 and r.json()['etiquetas'][0]['rotulo']=='A01.1'
    assert cliente.post('/api/impresion/recepciones/SUB-70/subbultos',json=d).json()['id']==r.json()['id']
    assert db.get(AppRecepcion,'SUB-70').bultos==2
    with pytest.raises(HTTPException):
        eb.generar_subbultos(db,'SUB-70',{**d,'clave':'otra-123456789','unidadIds':['NO-EXISTE']},'sup')


def test_reintento_de_atajo_reutiliza_id_aunque_post_perdio_respuesta(db,monkeypatch):
    from app.services import google_drive_api as g
    archivos={};posts=[]
    monkeypatch.setattr(g,'listar',lambda *args:[])
    monkeypatch.setattr(g,'generar',lambda *args:'RESERVADO70')
    def ficha(cuenta,ident):
        if ident not in archivos:raise RuntimeError('GOOGLE_NO_ENCONTRADO: no existe')
        return archivos[ident]
    monkeypatch.setattr(g,'ficha',ficha)
    def post(*args,**kw):
        f=kw['json'];posts.append(f);archivos[f['id']]=f
        raise RuntimeError('GOOGLE_RED: sin respuesta')
    monkeypatch.setattr(g.g,'peticion',post)
    g.atajo('prueba@example.test','PADRE70','ARCHIVO70','Foto','clave')
    g.atajo('prueba@example.test','PADRE70','ARCHIVO70','Foto','clave')
    assert len(posts)==1 and posts[0]['id']=='RESERVADO70'


def test_edicion_total_consolida_sin_borrar_historia_ni_cajas(cliente,db):
    from app.services import recepcion_edicion as ed
    m.crear_recepcion(db,{'codigo':'TOTAL-70','cliente':'PRUEBA','bultos':2},'sup')
    eb.generar(db,'TOTAL-70',{'clave':'etiquetas-total-70123','version':0,'cantidadAnterior':2,'total':2,
        'literal':'A','formato':'100x50','destino':'NAVEGADOR','numeros':[1,2]},'sup')
    r=ed.obtener(db,'TOTAL-70')
    d={'version':r['versionEdicion'],'descripcion':'Consolidado','embarques':[],'bultos':1,
       'consolidar':True,'motivoConsolidacion':'Consolidación física confirmada'}
    res=ed.editar(db,'TOTAL-70',d,'sup');assert res['bultos']==1
    viejo=db.scalar(select(AppUnidadLogistica).where(AppUnidadLogistica.recepcion=='TOTAL-70',AppUnidadLogistica.numero==2))
    assert viejo and viejo.datos['archivadoPorConsolidacion'] and viejo.datos['rotulo']=='A02'
    with pytest.raises(HTTPException):ed.editar(db,'TOTAL-70',d,'sup')
