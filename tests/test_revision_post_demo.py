from datetime import datetime
import pymysql
import pytest
from app.models import AppRecepcion, AppEvento, AppSku
from scripts.revisar_recepciones_post_demo import fecha_utc, revisar


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
