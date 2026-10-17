"""Listar informes grandes sin ordenar sus documentos JSON en MySQL."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db import engine, get_db
from app.main import app
from app.models import AppEntrega
from app.services import app_modelo as m


def sembrar(db, codigo, cantidad, *, grande=False, cliente='CLIENTE-A'):
    m.crear_recepcion(db, {'codigo': codigo, 'cliente': cliente}, 'sup')
    fecha = datetime(2026, 10, 17, 10)
    for i in range(cantidad):
        ident = f'{codigo}-{i:04d}'
        datos = {'destinatarios': f'destino{i % 9}@example.test', 'remitente':'responsable@example.test',
            'lineas': [{'descripcion': 'Documento privado del conteo ' * 24000}] if grande else [],
            'eventos': [{'observacion': 'DATOS-PRIVADOS-NO-DEVOLVER'}]}
        db.add(AppEntrega(id=ident, clave=ident.ljust(64, 'x'), recepcion=codigo, usuario='sup',
            estado='CANCELADA', creado_en=fecha + timedelta(minutes=i // 2), datos=datos,
            resultado={'carpeta':'https://drive.google.com/drive/folders/recepcion-prueba'}))
    db.commit()
    return [f'{codigo}-{i:04d}' for i in reversed(range(cantidad))]


def test_orden_limites_y_vistas_de_una_recepcion_sin_exponer_instantaneas(cliente, db):
    ids = sembrar(db, 'ORDEN-A', 105)
    sembrar(db, 'ORDEN-B', 1, cliente='CLIENTE-B')
    r = cliente.get('/api/app/entregas')
    assert r.status_code == 200, r.text
    assert [e['id'] for e in r.json()] == ids[:100]
    assert 'DATOS-PRIVADOS' not in r.text
    r = cliente.get('/api/app/recepciones/ORDEN-A/entregas')
    assert r.status_code == 200 and [e['id'] for e in r.json()] == ids[:10]
    recientes = cliente.get('/api/app/recepciones/ORDEN-A/destinatarios-recientes').json()
    assert len(recientes) == 8 and all(g['recepcion'] == 'ORDEN-A' for g in recientes)
    assert cliente.get('/api/app/recepciones/ORDEN-A/imagenes?contexto=true').json()['carpetaDrive'].endswith('recepcion-prueba')
    assert db.query(AppEntrega).count() == 106
    assert all(e.estado == 'CANCELADA' for e in db.scalars(select(AppEntrega)))


@pytest.mark.skipif(engine.dialect.name != 'mysql', reason='Regresión real de filesort: requiere MySQL')
def test_mysql_json_grande_reproduce_1038_y_listados_corregidos_funcionan(cliente, db):
    ids = sembrar(db, 'SORT-GRANDE', 8, grande=True)
    # Solo esta conexión y esta base desechable. No cambia variables globales.
    with engine.connect() as cx:
        original = cx.exec_driver_sql('SELECT @@SESSION.sort_buffer_size').scalar_one()
        cx.exec_driver_sql('SET SESSION sort_buffer_size = 32768')
        cx.commit()
        sesion = Session(bind=cx)
        try:
            # Reproducir la consulta anterior demuestra la causa del 500 aportado.
            with pytest.raises(OperationalError) as fallo:
                cx.execute(select(AppEntrega).order_by(AppEntrega.creado_en.desc()).limit(100)).all()
            assert fallo.value.orig.args[0] == 1038
            cx.rollback()
            def sesion_prueba():
                yield sesion
            app.dependency_overrides[get_db] = sesion_prueba
            for ruta in ['/api/app/entregas', '/api/app/recepciones/SORT-GRANDE/entregas']:
                r = cliente.get(ruta)
                assert r.status_code == 200, r.text
                assert [e['id'] for e in r.json()] == ids
                assert 'Documento privado' not in r.text and len(r.content) < 20000
            for ruta in ['/api/app/recepciones/SORT-GRANDE/destinatarios-recientes',
                         '/api/app/recepciones/SORT-GRANDE/imagenes?contexto=true']:
                r = cliente.get(ruta)
                assert r.status_code == 200, r.text
            assert cx.exec_driver_sql('SELECT @@SESSION.sort_buffer_size').scalar_one() == 32768
        finally:
            app.dependency_overrides.pop(get_db, None)
            sesion.close()
            cx.rollback()
            cx.exec_driver_sql(f'SET SESSION sort_buffer_size = {int(original)}')
            cx.commit()
