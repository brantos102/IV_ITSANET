"""Una base anterior al correo arranca sin recrear usuarios o historicos."""
from sqlalchemy import create_engine, inspect, text

from app.db import actualizar_email_operadores


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
