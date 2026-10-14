"""La aplicación de los operarios se sirve desde este servidor.

Es la que usan en el handheld: el escáner, el informe con el formato del packing
list, los duplicados, los CSV. Que se sirva desde aquí es lo que permite darles
UNA dirección —la de la red local— que seguirá valiendo cuando la capa de datos
pase a hablar con este servidor en vez de con Firestore.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import BASE_DIR
from app.main import app

HAY_APP = (BASE_DIR / "firebase" / "public" / "validar.html").is_file()
sin_app = pytest.mark.skipif(not HAY_APP, reason="sin la carpeta firebase/public")


@sin_app
@pytest.mark.parametrize("ruta", [
    "/app/",                 # el acceso
    "/app/validar.html",     # la pantalla de validación
    "/app/recepciones.html",
    "/app/kpis.html",
])
def test_las_pantallas_de_los_operarios_se_sirven(ruta):
    r = TestClient(app).get(ruta)
    assert r.status_code == 200, ruta
    assert "<html" in r.text.lower()


@sin_app
@pytest.mark.parametrize("recurso", [
    "/app/js/datos.js", "/app/js/conteo.js", "/app/js/informe.js",
    "/app/js/csv.js", "/app/js/nombres.js", "/app/css/app.css",
])
def test_sus_modulos_tambien(recurso):
    """Sin estos la pantalla carga en blanco, que es peor que no cargar."""
    r = TestClient(app).get(recurso)
    assert r.status_code == 200, recurso


@sin_app
def test_no_estorba_a_la_aplicacion_del_servidor():
    """Las dos conviven: /app es la de los operarios, / la del servidor."""
    c = TestClient(app)
    assert c.get("/login").status_code == 200
    assert c.get("/api/catalogo/estado").status_code in (200, 401, 403)
