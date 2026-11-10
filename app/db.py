"""Motor de base de datos.

Dos destinos, el mismo modelo:

  * **SQLite** (por defecto) en modo WAL. Para una sola máquina y pocos
    operadores va sobrado, y no hay nada que instalar.
  * **MySQL** en el servidor de la empresa, que es a donde va esto.

Lo que cambia entre uno y otro no es el esquema sino el cuidado de la conexión:
MySQL cierra las conexiones ociosas por su cuenta y, si no se recicla el pool,
el primer escaneo de la mañana se encuentra una conexión muerta y falla con un
«MySQL server has gone away» que no dice nada a quien está con el handheld.
"""
from __future__ import annotations

from sqlalchemy import MetaData, Table, create_engine, event, inspect, text
from sqlalchemy.sql.sqltypes import String
from sqlalchemy.exc import DBAPIError
from sqlalchemy.schema import CreateColumn
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL, DB_POOL_RECYCLE, DB_POOL_SIZE

_is_sqlite = DATABASE_URL.startswith("sqlite")
_is_mysql = DATABASE_URL.startswith(("mysql", "mariadb"))


def _opciones_motor() -> dict:
    """Los argumentos del motor, según a qué base se conecte."""
    if _is_sqlite:
        return {"connect_args": {"check_same_thread": False, "timeout": 30}}

    if _is_mysql:
        return {
            # MySQL cierra las conexiones ociosas (wait_timeout, 8 h por
            # defecto). Reciclar antes de que eso pase evita que la primera
            # petición tras una pausa larga reviente.
            "pool_recycle": DB_POOL_RECYCLE,
            "pool_size": DB_POOL_SIZE,
            "max_overflow": DB_POOL_SIZE,
            "connect_args": {"charset": "utf8mb4"},
        }

    return {}


engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True, **_opciones_motor())


if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _rec):  # pragma: no cover - infraestructura
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")       # lectores no bloquean escritores
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=30000")     # espera en vez de fallar
        cur.close()


if _is_mysql:

    @event.listens_for(engine, "connect")
    def _mysql_sesion(dbapi_conn, _rec):  # pragma: no cover - infraestructura
        cur = dbapi_conn.cursor()
        # Modo estricto: un dato que no cabe tiene que dar error, no guardarse
        # recortado. Sin esto MySQL acepta una descripción de 400 caracteres en
        # una columna de 300 y la corta sin avisar a nadie.
        cur.execute("SET SESSION sql_mode = 'STRICT_ALL_TABLES,NO_ENGINE_SUBSTITUTION'")
        # Todo se guarda en UTC. Si el servidor está en otra zona, las horas de
        # los conteos saldrían desplazadas en los informes.
        cur.execute("SET SESSION time_zone = '+00:00'")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


# InnoDB y utf8mb4 en TODAS las tablas.
#
# InnoDB porque hacen falta transacciones y claves foráneas, y el libro mayor
# depende de las dos. utf8mb4 porque «utf8» a secas en MySQL son tres bytes por
# carácter y no le caben cosas que un packing list sí trae.
#
# Va como escucha y no en __table_args__ del Base porque una clase que defina el
# suyo —y cuatro lo hacen, con sus índices— pisaría el del Base sin que nadie se
# entere hasta crear las tablas en el servidor. Así no hay nada que recordar al
# añadir un modelo nuevo.
@event.listens_for(Table, "after_parent_attach")
def _opciones_mysql(tabla, _padre):  # pragma: no cover - se comprueba en el DDL
    tabla.kwargs.setdefault("mysql_engine", "InnoDB")
    tabla.kwargs.setdefault("mysql_charset", "utf8mb4")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401  (registra los modelos)

    crear_tablas_compatibles(engine)
    actualizar_email_operadores(engine)


def crear_tablas_compatibles(bind) -> None:
    """Crea solo tablas ausentes, respetando tipos/collations de claves existentes.

    MySQL exige la misma collation en ambos extremos de una FK textual.
    Especificar CHARSET=utf8mb4 en una tabla nueva puede elegir 0900_ai_ci
    aunque las tablas operativas usen unicode_ci. No se convierten tablas ni
    se modifican columnas operativas para solucionar esa incompatibilidad.
    """
    if bind.dialect.name not in ('mysql', 'mariadb'):
        Base.metadata.create_all(bind=bind)
        return
    with bind.begin() as cx:
        inspector = inspect(cx)
        existentes = set(inspector.get_table_names())
        # Una copia evita cambiar los tipos ORM globales entre motores/hilos.
        modelo = MetaData()
        for tabla in Base.metadata.sorted_tables:
            tabla.to_metadata(modelo)
        textos = {(r.TABLE_NAME, r.COLUMN_NAME): (r.CHARACTER_SET_NAME, r.COLLATION_NAME)
            for r in cx.execute(text('''SELECT TABLE_NAME, COLUMN_NAME, CHARACTER_SET_NAME, COLLATION_NAME
                FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE()
                AND CHARACTER_SET_NAME IS NOT NULL'''))}
        columnas = {}
        for tabla in modelo.sorted_tables:
            if tabla.name in existentes:
                continue
            for columna in tabla.columns:
                for fk in columna.foreign_keys:
                    origen = fk.column
                    if origen.table.name not in existentes:
                        continue
                    nombre = origen.table.name
                    if nombre not in columnas:
                        columnas[nombre] = {c['name']: c['type'] for c in inspector.get_columns(nombre)}
                    tipo = columnas[nombre][origen.name].copy()
                    if isinstance(tipo, String) and (nombre, origen.name) in textos:
                        tipo.charset, tipo.collation = textos[(nombre, origen.name)]
                    columna.type = tipo
        modelo.create_all(bind=cx)


def actualizar_email_operadores(bind) -> None:
    """Actualizacion aditiva para instalaciones anteriores al correo.

    create_all no modifica tablas existentes. No se recrean tablas, se rellenan
    correos ni se cambian usuarios, claves o eventos del historico migrado.
    """
    from app.models import Operador

    with bind.begin() as cx:
        if "email" not in {c["name"] for c in inspect(cx).get_columns("operadores")}:
            columna = str(CreateColumn(Operador.__table__.c.email).compile(dialect=cx.dialect))
            try:
                cx.execute(text(f"ALTER TABLE operadores ADD COLUMN {columna}"))
            except DBAPIError:
                # Otro worker puede haber terminado la misma actualizacion.
                if "email" not in {c["name"] for c in inspect(cx).get_columns("operadores")}:
                    raise
        for indice in Operador.__table__.indexes:
            if list(indice.columns.keys()) == ["email"]:
                indice.create(cx, checkfirst=True)


def comprobar_conexion() -> dict:
    """Con qué base se está hablando de verdad, y si responde.

    Sirve para no descubrir en el primer escaneo que la aplicación está
    escribiendo en el SQLite de pruebas en vez de en MySQL.
    """
    datos = {"url": DATABASE_URL.split("@")[-1], "motor": engine.dialect.name}
    with engine.connect() as cx:
        if _is_mysql:
            fila = cx.execute(text(
                "SELECT VERSION(), @@character_set_database, @@collation_database"
            )).first()
            datos.update(version=fila[0], charset=fila[1], collation=fila[2])
        else:
            datos["version"] = cx.execute(text("SELECT sqlite_version()")).scalar()
    return datos
