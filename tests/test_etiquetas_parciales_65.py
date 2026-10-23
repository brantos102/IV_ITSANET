"""La reimpresión selecciona números físicos y conserva la identidad emitida."""
from sqlalchemy import select
from app.models import AppUnidadLogistica, AppImpresion
from tests.test_etiquetas_bultos_finales import crear, solicitud
from tests.test_operacion_desarrollo import admin  # noqa: F401


def test_reimpresion_parcial_no_renumera_ni_modifica_total(cliente,db):
    ruta=crear(cliente,cantidad=70)
    completo=cliente.post(ruta,json=solicitud(cliente,ruta)).json()
    datos=solicitud(cliente,ruta,numeros=[70,3,2])
    r=cliente.post(ruta,json=datos);assert r.status_code==201,r.text
    parcial=r.json();assert parcial['copias']==3 and parcial['totalBultos']==70
    assert parcial['numeros']==[2,3,70]
    assert [e['rotulo'] for e in parcial['etiquetas']]==['P02','P03','P70']
    assert [e['unidadId'] for e in parcial['etiquetas']]==[completo['etiquetas'][i-1]['unidadId'] for i in [2,3,70]]
    assert parcial['zpl'].count('^PQ1')==3 and '^FDP01^FS' not in parcial['zpl']
    assert cliente.post(ruta,json=datos).json()==parcial
    assert cliente.get('/api/app/recepciones/BULTOS').json()['bultos']==70
    db.rollback();assert db.query(AppUnidadLogistica).count()==70 and db.query(AppImpresion).count()==2


def test_maximo_aplica_a_seleccion_no_al_total_fisico(cliente,admin):
    ruta=crear(cliente,cantidad=70)
    conf=admin.get('/api/operacion/config').json();conf['maxCopias']=4
    assert admin.put('/api/operacion/config',json=conf).status_code==200
    r=cliente.post(ruta,json=solicitud(cliente,ruta,numeros=[51,52,53]));assert r.status_code==201,r.text
    assert r.json()['copias']==3 and r.json()['totalBultos']==70
    assert cliente.post(ruta,json=solicitud(cliente,ruta,numeros=[1,2,3,4,5])).status_code==422


def test_literal_de_una_etiqueta_emitida_no_cambia_al_reimprimir(cliente,db):
    ruta=crear(cliente,cantidad=5)
    primero=cliente.post(ruta,json=solicitud(cliente,ruta,numeros=[2])).json()
    cambio=cliente.post(ruta,json=solicitud(cliente,ruta,numeros=[2],literal='B'))
    assert cambio.status_code==409 and 'rótulo P02' in cambio.text
    db.rollback();u=db.get(AppUnidadLogistica,primero['etiquetas'][0]['unidadId']);assert u.datos['rotulo']=='P02'
    assert db.query(AppImpresion).count()==1


def test_seleccion_invalida_no_genera_lote(cliente,db):
    ruta=crear(cliente,cantidad=5)
    for numeros in [[],[0],[6],[1,1],[True],[1.5],['1'],'1-5',None]:
        r=cliente.post(ruta,json=solicitud(cliente,ruta,numeros=numeros));assert r.status_code==422,r.text
    db.rollback();assert not db.scalar(select(AppImpresion.id))


def test_grande_aprovecha_datos_y_compacta_mantiene_codigo_solo(cliente):
    ruta=crear(cliente,cantidad=5)
    grande=cliente.post(ruta,json=solicitud(cliente,ruta,numeros=[3],formato='100x150')).json()['zpl']
    assert '^LL1200' in grande and '^FO24,1020' in grande and '^FO24,30' in grande
    assert '^FDP03^FS' in grande and grande.count('^XA')==1
    compacto=cliente.post(ruta,json=solicitud(cliente,ruta,numeros=[3],formato='100x50')).json()['zpl']
    assert '^LL400' in compacto and '^FO24,1020' not in compacto and '^FDP03^FS' in compacto


def test_consolidar_excluye_etiquetas_archivadas_y_reintento_no_reimprime_total_antiguo(cliente,db):
    ruta=crear(cliente,cantidad=70)
    datos=solicitud(cliente,ruta);original=cliente.post(ruta,json=datos).json()
    r=cliente.post('/api/operacion/recepciones/BULTOS/bultos',json={'cantidad':50,'cantidadAnterior':70,'consolidar':True,'motivo':'Consolidación física realizada'})
    assert r.status_code==200,r.text
    assert len(r.json()['unidades'])==50 and len(r.json()['bultosArchivados'])==20
    anterior=cliente.post(ruta,json=datos);assert anterior.status_code==409 and 'total vigente' in anterior.text
    nuevo=cliente.post(ruta,json=solicitud(cliente,ruta,numeros=[1,50]));assert nuevo.status_code==201,nuevo.text
    assert nuevo.json()['numeros']==[1,50] and nuevo.json()['totalBultos']==50
    assert cliente.post(ruta,json=solicitud(cliente,ruta,numeros=[51])).status_code==422
    db.rollback();assert db.query(AppUnidadLogistica).count()==70
    assert len(db.get(AppImpresion,original['id']).datos['etiquetas'])==70
