"""Base de pruebas: cada test usa su propia base SQLite temporal."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="valventura-test-"))
os.environ.setdefault("VAL_DATA_DIR", str(_TMP))
os.environ.setdefault("VAL_DATABASE_URL", f"sqlite:///{_TMP / 'test.db'}")

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Operador, Rol  # noqa: E402
from app.security import hash_pin  # noqa: E402

ARCHIVO_REAL = Path(
    "/tmp/claude-0/-home-user/78ba3ba8-45b7-57d8-830f-e1e30fcd622a/scratchpad/data/"
    "9edbb300-29-06-2026_VW.xlsx"
)


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
