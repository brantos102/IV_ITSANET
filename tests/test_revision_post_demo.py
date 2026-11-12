from datetime import datetime
import pymysql
import pytest
from app.models import AppRecepcion, AppEvento, AppSku
from scripts.revisar_recepciones_post_demo import fecha_utc, revisar, clasificar_operativa


def test_fecha_de_la_reunion_utiliza_la_hora_de_quito():
    assert fecha_utc('2026-10-30T11:00:00-05:00') == datetime(2026,10,30,16)
    with pytest.raises(ValueError):
        fecha_utc('2026-10-30T11:00:00')


def test_revision_incluye_recepciones_anteriores_con_actividad_y_no_escribe(db,monkeypatch):
    for codigo in ['CON-ACTIVIDAD','NUEVA','SIN-ACTIVIDAD','CERRADA']:
        db.add(AppRecepcion(codigo=codigo, cliente='PRUEBA', creado_en=datetime(2026,10,29),
                            cerrada_en=datetime(2026,11,1) if codigo=='CERRADA' else None,
                            estado='CERRADA' if codigo=='CERRADA' else 'ABIERTA'))
    db.flush()
    db.get(AppRecepcion,'NUEVA').creado_en=datetime(2026,10,31)
    db.add(AppEvento(id='conteo-demo', recepcion='CON-ACTIVIDAD', tipo='CONTEO', sku='SKU',
                    cantidad=1, creado_en=datetime(2026,10,30,17)))
    db.add(AppSku(recepcion='CON-ACTIVIDAD', sku='SKU', esperado=2, contado=1, verificado=True))
    db.commit()
    ejecutadas=[]
    class Cursor:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def execute(self,sql,params=()):
            ejecutadas.append(sql)
            if sql.startswith('SELECT VERSION'):
                self.version=True
            elif sql.startswith(('SET SESSION','START TRANSACTION')):
                self.version=False
            else:
                self.version=False
                self.cursor=db.connection().exec_driver_sql(sql.replace('%s','?'),params)
        def fetchone(self): return {'version':'8.0-pruebas'}
        def fetchall(self): return [dict(r) for r in self.cursor.mappings()]
    class Conexion:
        cerrada=False
        revertida=False
        def cursor(self): return Cursor()
        def rollback(self): self.revertida=True
        def close(self): self.cerrada=True
    conexion=Conexion()
    monkeypatch.setattr(pymysql,'connect',lambda **kw: conexion)
    r=revisar('mysql+pymysql://usuario:secreto@localhost/pruebas',
              datetime(2026,10,30,16),datetime(2026,11,10))
    assert {x['codigo'] for x in r['recepciones']} == {'CON-ACTIVIDAD','NUEVA','CERRADA'}
    assert r['totalRevisionFisicaCompleta']==1 and r['totalCerradasOEntregadas']==1
    assert r['soloLectura'] and conexion.cerrada and conexion.revertida
    assert 'START TRANSACTION READ ONLY' in ejecutadas
    assert all(sql.startswith(('SELECT','SET SESSION','START TRANSACTION READ ONLY')) for sql in ejecutadas)
    assert 'secreto' not in str(r)
    todas=revisar('mysql+pymysql://usuario:secreto@localhost/pruebas',
                  datetime(2026,10,30,16),datetime(2026,11,10),True)
    assert todas['historialCompleto'] and todas['totalRecepciones']==4
    filtradas=revisar('mysql+pymysql://usuario:secreto@localhost/pruebas',datetime(2026,10,30,16),datetime(2026,11,10),True,True)
    assert filtradas['totalRecepciones']==0 and len(filtradas['excluidasPruebaOEliminadas'])==4
    assert filtradas['registrosConsultados']==4 and filtradas['soloLectura']
    # Una descripción de un trabajo real no debe excluirse por mencionar una prueba.
    operativa=db.get(AppRecepcion,'CON-ACTIVIDAD')
    operativa.cliente='VENTURA'
    operativa.descripcion='Repuestos para prueba de motor'
    cerrada=db.get(AppRecepcion,'CERRADA')
    cerrada.cliente='VENTURA'
    db.commit()
    mixtas=revisar('mysql+pymysql://usuario:secreto@localhost/pruebas',datetime(2026,10,30,16),datetime(2026,11,10),True,True)
    assert mixtas['totalRecepciones']==2 and mixtas['registrosConsultados']==4
    assert mixtas['totalRevisionFisicaCompleta']==1 and mixtas['totalCerradasOEntregadas']==1
    assert [r['codigo'] for r in mixtas['descripcionesPorRevisar']]==['CON-ACTIVIDAD']
    explicitas=revisar('mysql+pymysql://usuario:secreto@localhost/pruebas',datetime(2026,10,30,16),datetime(2026,11,10),True,True,['CERRADA'])
    assert explicitas['totalRecepciones']==1 and explicitas['totalCerradasOEntregadas']==0
    assert any(r['codigo']=='CERRADA' and r['motivo']=='EXCLUSION_EXPLICITA' for r in explicitas['excluidasPruebaOEliminadas'])
    assert all(sql.startswith(('SELECT','SET SESSION','START TRANSACTION READ ONLY')) for sql in ejecutadas)


@pytest.mark.parametrize('codigo,cliente,descripcion,motivo',[
    ('DEMO-01','VENTURA','Ensayo','CODIGO_MARCADO_PRUEBA'),
    ('PRUEBA2','VENTURA','','CODIGO_MARCADO_PRUEBA'),
    ('VW-RA26836-09-11-2026','VENTURA','Repuestos para prueba de motor',None),
    ('VW-RA26836-09-11-2026','VENTURA','PRUEBA DEL SISTEMA','DESCRIPCION_MARCADA_PRUEBA'),
    ('REC-001','CLIENTE DE PRUEBA','','CLIENTE_MARCADO_PRUEBA'),
    ('VW-RM55839-14-10-2026','VENTURA','Recepción operativa',None),
])
def test_clasifica_solo_marcas_explicitas(codigo,cliente,descripcion,motivo):
    assert clasificar_operativa({'codigo':codigo,'cliente':cliente,'descripcion':descripcion,'estado':'CERRADA'})==motivo
