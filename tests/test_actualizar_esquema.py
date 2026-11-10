"""Una base anterior al correo arranca sin recrear usuarios o historicos."""
import pytest
from sqlalchemy import MetaData, create_engine, inspect, select, text
from sqlalchemy.dialects import mysql

from app.db import Base, SessionLocal, actualizar_email_operadores, crear_tablas_compatibles, engine


def test_actualizacion_aditiva_repetible_conserva_filas_y_hashes():
    motor = create_engine('sqlite://')
    with motor.begin() as cx:
        cx.execute(text('CREATE TABLE operadores (id INTEGER PRIMARY KEY, usuario VARCHAR(50), pin_hash VARCHAR(200))'))
        cx.execute(text("INSERT INTO operadores VALUES (17, 'existente', 'hash-a-conservar')"))
        cx.execute(text('CREATE TABLE historico (id INTEGER PRIMARY KEY, cantidad INTEGER)'))
        cx.execute(text('INSERT INTO historico VALUES (9, 200)'))
    actualizar_email_operadores(motor)
    actualizar_email_operadores(motor)
    with motor.connect() as cx:
        assert cx.execute(text('SELECT id, usuario, pin_hash, email FROM operadores')).one() == (17, 'existente', 'hash-a-conservar', None)
        assert cx.execute(text('SELECT * FROM historico')).one() == (9, 200)
        assert any(i['column_names'] == ['email'] for i in inspect(cx).get_indexes('operadores'))


@pytest.mark.skipif(engine.dialect.name not in ('mysql', 'mariadb'), reason='Compatibilidad de esquema requiere MySQL real')
@pytest.mark.parametrize('collation', ['utf8mb4_unicode_ci', 'utf8mb4_general_ci'])
def test_tablas_nuevas_respetan_claves_operativas_sin_convertir_tablas(db, collation):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models import Operador, Rol, AppRecepcion, AppSku, AppArchivo, AppPresencia
    from app.security import hash_pin
    nuevas = {'app_calidad_skus', 'app_presencias', 'app_informes', 'app_auditoria_general',
        'app_ingresos', 'app_unidades_logisticas', 'app_evidencias', 'app_copias_drive',
        'app_stock_depot', 'app_impresiones'}
    db.close()
    Base.metadata.drop_all(bind=engine)  # Únicamente la base desechable protegida por conftest.
    anterior = MetaData()
    for t in Base.metadata.sorted_tables:
        if t.name not in nuevas:
            c = t.to_metadata(anterior)
            c.dialect_options['mysql']['collate'] = collation
    # Archivo y recepción pueden usar collations distintas incluso en una misma FK compuesta por vínculos separados.
    archivo_collation = 'utf8mb4_general_ci' if collation == 'utf8mb4_unicode_ci' else 'utf8mb4_unicode_ci'
    anterior.tables['app_archivos'].dialect_options['mysql']['collate'] = archivo_collation
    for t in anterior.tables.values():
        for c in t.columns:
            for fk in c.foreign_keys:
                if fk.column.table.name == 'app_archivos':
                    c.type = mysql.VARCHAR(length=fk.column.type.length, collation=archivo_collation)
    anterior.tables['app_archivos'].c.recepcion.type = mysql.VARCHAR(length=60, collation=collation)
    anterior.create_all(bind=engine)
    hash_anterior = hash_pin('clave-operativa-prueba')
    with SessionLocal() as s:
        s.add(Operador(usuario='anterior', nombre='Operador anterior', rol=Rol.SUPERVISOR, pin_hash=hash_anterior))
        s.add(AppRecepcion(codigo='CONSERVAR', cliente='VENTURA', estado='EN_VALIDACION'))
        s.commit()
        s.add(AppSku(recepcion='CONSERVAR', sku='SKU1', esperado=7, contado=2, estado='FALTANTE'))
        s.add(AppArchivo(id='foto-anterior', recepcion='CONSERVAR', tipo='foto', nombre='evidencia.jpg',
            mime='image/jpeg', sha256='a'*64, bytes=123))
        s.commit()
    with engine.connect() as cx:
        antes = {n: cx.execute(text(f'SHOW CREATE TABLE {n}')).one()[1] for n in anterior.tables}
    crear_tablas_compatibles(engine)
    crear_tablas_compatibles(engine)
    with engine.connect() as cx:
        despues = {n: cx.execute(text(f'SHOW CREATE TABLE {n}')).one()[1] for n in anterior.tables}
        assert antes == despues
        assert cx.execute(text('SELECT usuario, pin_hash FROM operadores')).one() == ('anterior', hash_anterior)
        assert cx.execute(text('SELECT esperado, contado FROM app_skus')).one() == (7, 2)
        assert cx.execute(text('SELECT id, bytes FROM app_archivos')).one() == ('foto-anterior', 123)
        assert nuevas.issubset(set(inspect(cx).get_table_names()))
    # La copia para DDL no cambia los tipos globales del ORM.
    assert AppPresencia.__table__.c.recepcion.type.collation is None
    with SessionLocal() as s:
        assert s.scalar(select(AppSku)).contado == 2
    c = TestClient(app)
    assert c.post('/api/auth/login', json={'usuario': 'anterior', 'pin': 'clave-operativa-prueba'}).status_code == 200
    r = c.get('/api/app/recepciones/CONSERVAR/skus')
    assert r.status_code == 200 and r.json()[0]['contado'] == 2
