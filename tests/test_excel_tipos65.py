"""Los tipos/formato del origen sobreviven a la API sin cambiar conteos ni datos fuente."""
from copy import deepcopy
from app.services import app_modelo as m


def test_metadatos_excel_se_conservan_en_lineas_sin_migrar_ni_crear_conteos(cliente,db):
    codigo='TIPOS-EXCEL-65'
    m.crear_recepcion(db,{'codigo':codigo,'cliente':'DEMOSTRACION'},'sup')
    resultado={'encabezados':['SKU','Cantidad','PrecioUnit','Fecha'],'columnas':{'sku':0,'cantidad':1},
        'lineas':[{'linea':1,'sku':'00001234','cantidad':2.125,'precioUnit':1.234,
            'cruda':['00001234','2.125','1.234','46317'],'filaOriginal':2,
            'tiposCelda':{'1':'n','2':'n','3':'n'},'formatosCelda':{'2':'0.000','3':'dd/mm/yyyy'}}],
        'porSku':{'00001234':2.125},'unidades':2.125}
    antes=deepcopy(resultado)
    respuesta=cliente.post(f'/api/app/recepciones/{codigo}/packing-list',json={'resultado':resultado,'origen':'PL'})
    assert respuesta.status_code==200,respuesta.text
    fila=cliente.get(f'/api/app/recepciones/{codigo}/lineas').json()[0]
    assert fila['tiposCelda']==resultado['lineas'][0]['tiposCelda']
    assert fila['formatosCelda']==resultado['lineas'][0]['formatosCelda']
    assert fila['cruda']==resultado['lineas'][0]['cruda'] and fila['precioUnit']==1.234
    assert fila['sku']=='00001234' and fila['cantidad']==2.125
    assert cliente.get(f'/api/app/recepciones/{codigo}/eventos').json()==[]
    sku=cliente.get(f'/api/app/recepciones/{codigo}/skus').json()[0]
    assert sku['esperado']==2.125 and sku['contado']==0
    assert resultado==antes
