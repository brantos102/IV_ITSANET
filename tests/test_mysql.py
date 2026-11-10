"""El esquema tiene que ser válido en MySQL, y se comprueba sin MySQL.

Montar un servidor para esto convertiría la comprobación en algo que se salta
cuando hay prisa. SQLAlchemy sabe generar el DDL de MySQL sin conectarse a
ninguna parte, así que una incompatibilidad se ve aquí y no la tarde del
despliegue en el servidor de la empresa.
"""
from __future__ import annotations

import re

import pytest
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from app.db import Base
import app.models  # noqa: F401  (registra las tablas)

DIALECTO = mysql.dialect()
TABLAS = list(Base.metadata.sorted_tables)


def ddl(tabla) -> str:
    return str(CreateTable(tabla).compile(dialect=DIALECTO))


def test_hay_tablas():
    assert len(TABLAS) >= 8, [t.name for t in TABLAS]


@pytest.mark.parametrize("tabla", TABLAS, ids=lambda t: t.name)
def test_el_ddl_compila_en_mysql(tabla):
    assert ddl(tabla).startswith("\nCREATE TABLE")


@pytest.mark.parametrize("tabla", TABLAS, ids=lambda t: t.name)
def test_ningun_varchar_sin_longitud(tabla):
    """MySQL rechaza un VARCHAR sin longitud; SQLite lo acepta.

    Es la forma más fácil de que algo funcione en el portátil y falle al crear
    las tablas en el servidor.
    """
    sueltos = re.findall(r"\bVARCHAR\b(?!\s*\()", ddl(tabla))
    assert not sueltos, f"{tabla.name}: VARCHAR sin longitud"


@pytest.mark.parametrize("tabla", TABLAS, ids=lambda t: t.name)
def test_innodb_y_utf8mb4(tabla):
    """Sin InnoDB no hay transacciones ni claves foráneas, y el libro mayor
    depende de las dos. Sin utf8mb4, «utf8» de MySQL son tres bytes y se come
    caracteres que un packing list sí trae."""
    t = ddl(tabla)
    assert "ENGINE=InnoDB" in t, tabla.name
    assert "CHARSET=utf8mb4" in t, tabla.name


def test_las_cantidades_no_son_coma_flotante():
    """Un FLOAT pierde precisión al sumar, y aquí se suman cientos de líneas.

    Ya pasó una vez, en la otra aplicación: mil unidades perdidas por leer mal
    un número. Que no vuelva por el tipo de la columna.
    """
    columnas = [
        ("packing_items", "cantidad"), ("packing_items", "precio_unit"),
        ("packing_items", "precio_total"), ("scan_events", "cantidad"),
    ]
    for nombre_tabla, nombre_col in columnas:
        tabla = Base.metadata.tables[nombre_tabla]
        tipo = tabla.c[nombre_col].type.compile(dialect=DIALECTO)
        assert tipo.startswith("DECIMAL") or tipo.startswith("NUMERIC"), \
            f"{nombre_tabla}.{nombre_col} es {tipo}"


def test_el_libro_mayor_guarda_milesimas():
    """Dos escaneos del mismo segundo tienen que quedar ordenados."""
    tipo = Base.metadata.tables["scan_events"].c["creado_en"].type
    assert "fsp=3" in repr(tipo.dialect_impl(DIALECTO)) or \
           "DATETIME(3)" in tipo.compile(dialect=DIALECTO), tipo.compile(dialect=DIALECTO)


@pytest.mark.parametrize("tabla", TABLAS, ids=lambda t: t.name)
def test_los_indices_caben_en_innodb(tabla):
    """Una clave de InnoDB admite 3072 bytes, y en utf8mb4 cada carácter ocupa
    cuatro. Un índice sobre una columna larga se crea en SQLite y falla en
    MySQL con un error que no dice cuál es la columna."""
    for indice in list(tabla.indexes) + [c for c in tabla.constraints
                                         if hasattr(c, "columns")]:
        bytes_clave = sum(
            (getattr(c.type, "length", 0) or 0) * 4
            for c in indice.columns if hasattr(c.type, "length")
        )
        assert bytes_clave <= 3072, f"{tabla.name}: índice de {bytes_clave} bytes"


def test_el_motor_recicla_las_conexiones_en_mysql():
    """MySQL cierra las conexiones ociosas. Sin reciclarlas, el primer escaneo
    de la mañana falla con «MySQL server has gone away»."""
    from app import db as modulo_db

    guardado = modulo_db.DATABASE_URL
    try:
        modulo_db.DATABASE_URL = "mysql+pymysql://u:c@h/d"
        modulo_db._is_sqlite = False
        modulo_db._is_mysql = True
        opciones = modulo_db._opciones_motor()
        assert opciones["pool_recycle"] > 0
        assert opciones["connect_args"]["charset"] == "utf8mb4"
    finally:
        modulo_db.DATABASE_URL = guardado
        modulo_db._is_sqlite = guardado.startswith("sqlite")
        modulo_db._is_mysql = False
