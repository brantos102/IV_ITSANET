"""Base de pruebas: cada test usa su propia base SQLite temporal."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="itsanet-test-"))

# Las pruebas NUNCA tocan la base configurada. Se impone la suya.
#
# Antes esto usaba setdefault, que respeta lo que ya haya en el entorno. En el
# servidor VAL_DATABASE_URL apunta a MySQL de produccion, asi que las pruebas se
# ejecutaban contra ella — y el fixture de abajo empieza con drop_all. Es decir:
# lanzar las pruebas en el servidor borraba las recepciones, los conteos y la
# auditoria enteros, sin preguntar y sin dejar rastro.
#
# Para probar contra un MySQL de verdad se usa VAL_TEST_DATABASE_URL, que hay
# que escribir a proposito y apuntando a OTRA base. Un nombre distinto es lo que
# impide que pase por descuido.
os.environ["VAL_DATA_DIR"] = str(_TMP)
os.environ["VAL_DATABASE_URL"] = os.getenv(
    "VAL_TEST_DATABASE_URL", f"sqlite:///{_TMP / 'test.db'}")

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Operador, Rol  # noqa: E402
from app.security import hash_pin  # noqa: E402

def _buscar_archivo_real() -> Path:
    """Packing list real usado por las pruebas end-to-end.

    No se versiona (lleva datos del cliente). Para ejecutarlas, copie el
    archivo en tests/fixtures/ o apunte VAL_TEST_XLSX a su ubicacion.
    Si no esta, esas pruebas se omiten; el resto corre igual.
    """
    env = os.getenv("VAL_TEST_XLSX")
    if env:
        return Path(env)
    aqui = Path(__file__).parent / "fixtures"
    if aqui.is_dir():
        for cand in sorted(aqui.glob("*.xlsx")):
            return cand
    return aqui / "packing_list_real.xlsx"


ARCHIVO_REAL = _buscar_archivo_real()


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def operadores(db):
    sup = Operador(usuario="sup", nombre="Supervisora", pin_hash=hash_pin("1111"),
                   rol=Rol.SUPERVISOR)
    o1 = Operador(usuario="op1", nombre="Operador Uno", pin_hash=hash_pin("2222"))
    o2 = Operador(usuario="op2", nombre="Operador Dos", pin_hash=hash_pin("3333"))
    db.add_all([sup, o1, o2])
    db.commit()
    return {"sup": sup, "op1": o1, "op2": o2}


@pytest.fixture()
def cliente(db, operadores):
    c = TestClient(app)
    c.post("/api/auth/login", json={"usuario": "sup", "pin": "1111"})
    return c


def test_las_pruebas_no_tocan_la_base_de_produccion():
    """Una prueba sobre las propias pruebas, porque esto ya se llevó una base.

    El fixture `db` empieza con drop_all. Si la configuración del servidor se
    colara aquí, ejecutar las pruebas borraría lo que hay en producción.
    """
    from app.db import DATABASE_URL

    esperada = os.environ["VAL_DATABASE_URL"]
    assert DATABASE_URL == esperada
    if not os.getenv("VAL_TEST_DATABASE_URL"):
        assert DATABASE_URL.startswith("sqlite:///"), DATABASE_URL
        assert str(_TMP) in DATABASE_URL, "tiene que ser la temporal de esta ejecución"
