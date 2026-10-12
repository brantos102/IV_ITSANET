"""Pruebas de la API HTTP: autenticacion, roles y flujo completo."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import ARCHIVO_REAL


def _login(c: TestClient, usuario: str, pin: str):
    r = c.post("/api/auth/login", json={"usuario": usuario, "pin": pin})
    assert r.status_code == 200, r.text
    return r


def test_sin_sesion_se_rechaza(db, operadores):
    c = TestClient(app)
    assert c.get("/api/recepciones").status_code == 401
    assert c.post("/api/auth/login", json={"usuario": "sup", "pin": "mal"}).status_code == 401


def test_operador_no_puede_cerrar_ni_crear_usuarios(db, operadores):
    c = TestClient(app)
    _login(c, "sup", "1111")
    rec = c.post("/api/recepciones", json={"codigo": "R-ROL"}).json()

    o = TestClient(app)
    _login(o, "op1", "2222")
    assert o.post(f"/api/recepciones/{rec['id']}/cerrar").status_code == 403
    assert o.post("/api/auth/operadores", json={
        "usuario": "x", "nombre": "X", "pin": "9999"}).status_code == 403
    # ...pero si puede escanear.
    assert o.post(f"/api/recepciones/{rec['id']}/lookup",
                  json={"codigo": "ABC123"}).status_code == 200


def test_flujo_http_completo(db, operadores, tmp_path):
    c = TestClient(app)
    _login(c, "sup", "1111")

    rec = c.post("/api/recepciones", json={
        "codigo": "R-HTTP", "cliente": "VENTURA", "bultos_declarados": 6}).json()
    rid = rec["id"]

    # Codigo duplicado -> 409
    assert c.post("/api/recepciones", json={"codigo": "R-HTTP"}).status_code == 409

    with ARCHIVO_REAL.open("rb") as fh:
        r = c.post(f"/api/recepciones/{rid}/packing-list", files={"archivo": fh})
    assert r.status_code == 200, r.text
    assert r.json()["lineas"] == 73

    # Segunda carga sin reemplazar -> 409
    with ARCHIVO_REAL.open("rb") as fh:
        assert c.post(f"/api/recepciones/{rid}/packing-list",
                      files={"archivo": fh}).status_code == 409

    # Lookup de un SKU del packing list
    r = c.post(f"/api/recepciones/{rid}/lookup", json={"codigo": "2H0525345"})
    assert r.status_code == 200
    d = r.json()
    assert d["en_packing_list"] is True and d["esperado"] == 1

    # Conteo correcto
    r = c.post(f"/api/recepciones/{rid}/scans", json={
        "codigo": "2H0525345", "cantidad": 1, "pallet": "B04.1"})
    assert r.status_code == 201, r.text
    assert r.json()["estado"] == "OK"

    # Pallet invalido -> 400
    assert c.post(f"/api/recepciones/{rid}/scans", json={
        "codigo": "5K6955435", "cantidad": 1, "pallet": "A 1..2"}).status_code == 400

    # Sobrante sin confirmar -> 409 con codigo accionable
    r = c.post(f"/api/recepciones/{rid}/scans", json={
        "codigo": "2H0525345", "cantidad": 5, "pallet": "B04.1"})
    assert r.status_code == 409
    assert r.json()["detail"]["codigo"] == "CONFIRMAR_SOBRANTE"

    # Confirmado -> 201
    assert c.post(f"/api/recepciones/{rid}/scans", json={
        "codigo": "2H0525345", "cantidad": 5, "pallet": "B04.1",
        "confirmar_sobrante": True}).status_code == 201

    resumen = c.get(f"/api/recepciones/{rid}").json()
    assert resumen["totales"]["unidades_fisicas"] == 6

    # Cierre y descarga del packing list final
    assert c.post(f"/api/recepciones/{rid}/cerrar").status_code == 200
    assert c.post(f"/api/recepciones/{rid}/scans", json={
        "codigo": "5K6955435", "cantidad": 1, "pallet": "B01"}).status_code == 409

    r = c.get(f"/api/recepciones/{rid}/export")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument")
    assert len(r.content) > 5000

    # La bitacora registra las acciones sensibles.
    acciones = {a["accion"] for a in c.get(f"/api/recepciones/{rid}/auditoria").json()}
    assert {"CARGAR_PACKING_LIST", "CERRAR_RECEPCION", "EXPORTAR_PACKING_FINAL"} <= acciones


def test_kpis_responden(db, operadores):
    c = TestClient(app)
    _login(c, "sup", "1111")
    for ruta in ("/api/kpi/resumen", "/api/kpi/operadores", "/api/kpi/skus",
                 "/api/kpi/serie", "/api/kpi/pendientes", "/api/catalogo/estado"):
        assert c.get(ruta).status_code == 200, ruta
