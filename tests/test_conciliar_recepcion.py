"""Diagnóstico aislado: no importa app.main ni inicializa tablas."""
import importlib.util
from pathlib import Path
from decimal import Decimal
import pytest

ruta=Path(__file__).resolve().parents[1]/'scripts/conciliar_recepcion.py'
spec=importlib.util.spec_from_file_location('conciliacion',ruta);c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)


def datos():
    r={'codigo':'PRUEBA','estado':'EN_VALIDACION','totales':{'lineas':3,'skus':2,'unidades':7},
        'formatos':{'LISTA~1':{'encabezados':['SKU','Cantidad','Nombre Contenedor','Embarque']}}}
    ls=[{'origen':'LISTA.1','sku':'SKU-A','cantidad':Decimal('2'),'extra':{'cruda':['SKU-A',2,'CONT-A','EMB-A'],'embarque':'EMB-A','contenedor':'CONT-A'}},
        {'origen':'LISTA.1','sku':'SKU-A','cantidad':Decimal('3'),'extra':{'cruda':['SKU-A',3,'CONT-B','EMB-A'],'embarque':'EMB-A','contenedor':'CONT-B'}},
        {'origen':'LISTA.1','sku':'SKU-B','cantidad':Decimal('2'),'extra':{'cruda':['SKU-B',2,'CONT-C','EMB-B'],'embarque':'EMB-B','contenedor':'CONT-C'}}]
    sk=[{'sku':'SKU-A','esperado':5,'contado':3,'en_packing_list':True},{'sku':'SKU-B','esperado':2,'contado':0,'en_packing_list':True}]
    return r,ls,sk


def test_cuenta_lineas_sku_y_unidades_sin_sumar_referencias_repetidas():
    r=c.analizar(*datos());assert r['lineas_guardadas']=={'lineas':3,'sku_distintos':2,'unidades':7}
    assert r['por_embarque'][0]['sku_distintos']==1 and r['por_embarque'][0]['unidades']==5
    assert r['unidades_fisicas_registradas']==3 and not r['avisos']
    assert r['unidades_en_celdas_originales']==7 and r['lineas_con_cantidad_distinta_original']==0
    assert r['segun_celdas_originales'][0]['embarque_excel']=='EMB-A'


def test_detecta_totales_desajustados_y_metadatos_cruzados_sin_repararlos():
    r,ls,sk=datos();r['totales']['unidades']=6;ls[0]['extra']['embarque']='OTRO';sk[0]['esperado']=4
    resultado=c.analizar(r,ls,sk)
    assert resultado['lineas_con_metadatos_distintos']==1 and len(resultado['avisos'])==3
    assert ls[0]['extra']['embarque']=='OTRO' and sk[0]['esperado']==4


@pytest.mark.parametrize('existe',[True,False])
def test_mysql_consulta_parametrizada_read_only_y_cierre_siempre(monkeypatch,existe):
    import pymysql
    r,ls,sk=datos();instrucciones=[];estado={'rollback':False,'cerrado':False}
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,args=None):instrucciones.append((sql,args))
        def fetchone(self):return r if existe else None
        def fetchall(self):return ls if 'app_lineas' in instrucciones[-1][0] else sk
    class Conexion:
        def cursor(self,*a):return Cursor()
        def rollback(self):estado['rollback']=True
        def close(self):estado['cerrado']=True
    monkeypatch.setattr(pymysql,'connect',lambda **kw:Conexion())
    if existe:assert c.consultar('mysql+pymysql://usuario:clave@localhost/pruebas','PRUEBA')['lineas_guardadas']['unidades']==7
    else:
        with pytest.raises(ValueError):c.consultar('mysql+pymysql://usuario:clave@localhost/pruebas','PRUEBA')
    assert estado=={'rollback':True,'cerrado':True}
    assert instrucciones[1][0]=='START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY'
    assert all(sql.startswith(('SET TRANSACTION','START TRANSACTION','SELECT ')) for sql,_ in instrucciones)
    assert instrucciones[2][1]==('PRUEBA',)


def test_mysql_real_reporte_coincide_y_no_modifica_recepcion(cliente,db):
    if db.bind.dialect.name!='mysql':pytest.skip('Lectura consistente en MySQL aislado')
    import os
    from tests.test_mejoras_operativas import preparar
    codigo=preparar(db);antes=cliente.get('/api/app/recepciones/'+codigo).json()
    r=c.consultar(os.environ['VAL_TEST_DATABASE_URL'],codigo)
    despues=cliente.get('/api/app/recepciones/'+codigo).json()
    assert antes==despues
    assert r['lineas_guardadas']['unidades']==antes['totales']['unidades']


def test_json_null_de_filas_historicas_no_impide_el_diagnostico():
    r,ls,sk=datos();ls[0]['extra']='null'
    resultado=c.analizar(r,ls,sk)
    assert resultado['lineas_guardadas']['unidades']==7
    assert resultado['lineas_con_cantidad_original_verificable']==2
    assert resultado['unidades_en_celdas_originales'] is None
