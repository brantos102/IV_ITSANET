"""Las pantallas tienen que abrirse. Suena obvio; no estaba comprobado.

La suite entera pasaba con /login devolviendo un 500: las pruebas iban contra la
API y ninguna abría una página. El fallo era una llamada a TemplateResponse con
la firma antigua —el nombre de la plantilla primero— que Starlette dejó de
aceptar: toma el nombre por la petición, el contexto por el nombre, y responde
«unhashable type: dict», que no se parece en nada a lo que pasa.

Un 500 aquí es una pantalla en blanco delante de un operario, así que basta con
pedir cada ruta y mirar que no reviente.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Recepcion

PANTALLAS_PUBLICAS = ["/login"]
PANTALLAS_PRIVADAS = ["/prototipo", "/kpi"]


@pytest.mark.parametrize("ruta", PANTALLAS_PUBLICAS)
def test_las_publicas_se_abren_sin_entrar(db, ruta):
    r = TestClient(app).get(ruta)
    assert r.status_code == 200, r.text[:400]
    assert "<html" in r.text.lower()


@pytest.mark.parametrize("ruta", PANTALLAS_PRIVADAS)
def test_las_privadas_mandan_al_acceso_sin_sesion(db, ruta):
    r = TestClient(app).get(ruta, follow_redirects=False)
    assert r.status_code == 302, r.text[:400]
    assert r.headers["location"] == "/login"


@pytest.mark.parametrize("ruta", PANTALLAS_PRIVADAS)
def test_las_privadas_se_abren_con_sesion(cliente, ruta):
    r = cliente.get(ruta)
    assert r.status_code == 200, r.text[:400]
    assert "<html" in r.text.lower()


def test_la_pantalla_de_acceso_trae_su_formulario(db):
    """Un 200 con la página vacía seguiría sin servir de nada."""
    t = TestClient(app).get("/login").text.lower()
    assert "usuario" in t
    assert "password" in t or "pin" in t


def test_las_pantallas_de_una_recepcion_se_abren(cliente, db):
    rec = Recepcion(codigo="PRUEBA-PANTALLAS", cliente="VENTURA")
    db.add(rec)
    db.commit()
    for ruta in (f"/recepciones/{rec.id}", f"/recepciones/{rec.id}/escanear"):
        r = cliente.get(ruta)
        assert r.status_code == 200, f"{ruta}: {r.text[:400]}"


def test_una_recepcion_que_no_existe_no_revienta(cliente):
    r = cliente.get("/recepciones/999999", follow_redirects=False)
    assert r.status_code == 302, r.text[:400]
