"""La API que consume el handheld, por HTTP.

Las reglas están probadas en `test_app_modelo.py`. Aquí se comprueba lo que solo
se rompe en la frontera: que cada error llegue con SU código —la pantalla decide
con él, no con el texto—, que el código de la recepción valga como dirección, y
que nada de esto se sirva sin sesión.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import hash_pin
from app.models import Operador, Rol

LINEAS = [{"linea": i, "sku": f"SKU{i:03d}", "descripcion": f"PIEZA {i}", "cantidad": 10}
          for i in range(1, 23)]
PACKING = {
    "lineas": LINEAS,
    "porSku": {l["sku"]: l["cantidad"] for l in LINEAS},
    "unidades": 220,
    "encabezados": ["ITEM", "COD. PRODUCTO", "DESCRIPCION", "CANTIDAD"],
    "columnas": {"sku": 1, "cantidad": 3},
    "hoja": "PACKING",
    "embarques": ["RB48529"],
}


@pytest.fixture()
def rec(cliente):
    r = cliente.post("/api/app/recepciones", json={"codigo": "REC0260002",
                                                   "cliente": "VENTURA"})
    assert r.status_code == 201, r.text
    return "REC0260002"


@pytest.fixture()
def conPacking(cliente, rec):
    r = cliente.post(f"/api/app/recepciones/{rec}/packing-list",
                     json={"resultado": PACKING, "origen": "PRINCIPAL",
                           "archivo": "PACKING.xlsx"})
    assert r.status_code == 200, r.text
    return rec


# --------------------------------------------------------------------------- #
# Sin sesión no se sirve nada
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("metodo,ruta", [
    ("get", "/api/app/recepciones"),
    ("get", "/api/app/recepciones/REC1/skus"),
    ("post", "/api/app/recepciones"),
    ("post", "/api/app/recepciones/REC1/conteos"),
    ("post", "/api/app/recepciones/REC1/cerrar"),
])
def test_sin_sesion_no_se_entra(metodo, ruta, db):
    c = TestClient(app)
    r = c.get(ruta) if metodo == "get" else c.post(ruta, json={})
    assert r.status_code in (401, 403), f"{ruta} respondió {r.status_code}"


# --------------------------------------------------------------------------- #
# El código de la recepción es su dirección
# --------------------------------------------------------------------------- #
def test_la_recepcion_se_pide_por_su_codigo(cliente, rec):
    r = cliente.get(f"/api/app/recepciones/{rec}")
    assert r.status_code == 200
    assert r.json()["id"] == rec, "el identificador es el código, no un número"


def test_una_que_no_existe_responde_404_con_su_codigo(cliente):
    r = cliente.get("/api/app/recepciones/REC-NADA")
    assert r.status_code == 404
    assert r.json()["detail"]["codigo"] == "NO_ENCONTRADA"


def test_el_listado_trae_los_documentos_que_pinta_la_pantalla(cliente, conPacking):
    filas = cliente.get("/api/app/recepciones").json()
    assert len(filas) == 1
    assert filas[0]["totales"] == {"lineas": 22, "skus": 22, "unidades": 220}
    assert filas[0]["origenes"] == ["PRINCIPAL"]


@pytest.mark.parametrize("coleccion,cuantos", [
    ("lineas", 22), ("skus", 22), ("adicionales", 0), ("eventos", 0),
])
def test_las_subcolecciones_se_leen_con_una_sola_ruta(cliente, conPacking,
                                                      coleccion, cuantos):
    r = cliente.get(f"/api/app/recepciones/{conPacking}/{coleccion}")
    assert r.status_code == 200, r.text
    assert len(r.json()) == cuantos


def test_una_coleccion_inventada_no_devuelve_la_recepcion_entera(cliente, conPacking):
    r = cliente.get(f"/api/app/recepciones/{conPacking}/loquesea")
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Cada error con su código: la pantalla decide con él
# --------------------------------------------------------------------------- #
def test_un_sobrante_llega_con_el_codigo_que_abre_el_dialogo(cliente, conPacking):
    r = cliente.post(f"/api/app/recepciones/{conPacking}/conteos",
                     json={"id": "e1", "sku": "SKU001", "cantidad": 12, "pallet": "A1"})
    assert r.status_code == 409
    assert r.json()["detail"]["codigo"] == "CONFIRMAR_SOBRANTE"
    assert "declara 10" in r.json()["detail"]["mensaje"]

    r = cliente.post(f"/api/app/recepciones/{conPacking}/conteos",
                     json={"id": "e1", "sku": "SKU001", "cantidad": 12,
                           "pallet": "A1", "confirmarSobrante": True})
    assert r.status_code == 200 and r.json()["estado"] == "SOBRANTE"


def test_una_recepcion_cerrada_lo_dice_con_su_codigo(cliente, conPacking):
    assert cliente.post(f"/api/app/recepciones/{conPacking}/cerrar").status_code == 200
    r = cliente.post(f"/api/app/recepciones/{conPacking}/conteos",
                     json={"id": "e1", "sku": "SKU001", "cantidad": 1, "pallet": "A1"})
    assert r.status_code == 409
    assert r.json()["detail"]["codigo"] == "RECEPCION_CERRADA"


def test_dos_listas_con_el_mismo_nombre_409(cliente, conPacking):
    r = cliente.post(f"/api/app/recepciones/{conPacking}/packing-list",
                     json={"resultado": PACKING, "origen": "PRINCIPAL"})
    assert r.status_code == 409
    assert r.json()["detail"]["codigo"] == "ORIGEN_DUPLICADO"


# --------------------------------------------------------------------------- #
# El ciclo entero, como lo hace el handheld
# --------------------------------------------------------------------------- #
def test_de_punta_a_punta(cliente, conPacking):
    rec = conPacking

    # Cuenta dos pallets del mismo SKU.
    for i, (pallet, cantidad) in enumerate([("A1-B04-C1", 6), ("A1-B04-C2", 4)], 1):
        r = cliente.post(f"/api/app/recepciones/{rec}/conteos", json={
            "id": f"ev{i}", "sku": "SKU001", "cantidad": cantidad,
            "pallet": pallet, "origen": "PRINCIPAL",
            "codigoEscaneado": "sku 001", "estadoFisico": "OK",
        })
        assert r.status_code == 200, r.text

    sku = next(s for s in cliente.get(f"/api/app/recepciones/{rec}/skus").json()
               if s["sku"] == "SKU001")
    assert sku["contado"] == 10 and sku["estado"] == "OK"
    assert sku["pallets"] == {"A1B04C1": 6, "A1B04C2": 4}
    assert sku["porOrigen"] == {"PRINCIPAL": {"A1B04C1": 6, "A1B04C2": 4}}
    assert sku["ultimoOperador"]

    # La recepción se movió sola a EN_VALIDACION.
    assert cliente.get(f"/api/app/recepciones/{rec}").json()["estado"] == "EN_VALIDACION"

    # Un error se corrige con una anulación, no borrando.
    r = cliente.post(f"/api/app/recepciones/{rec}/conteos/ev2/anular",
                     json={"motivo": "estaba en otro pallet"})
    assert r.status_code == 200, r.text
    assert r.json()["contado"] == 6
    assert len(cliente.get(f"/api/app/recepciones/{rec}/eventos").json()) == 3

    # Y se cierra.
    assert cliente.post(f"/api/app/recepciones/{rec}/cerrar").json()["estado"] == "CERRADA"
    tipos = [e["tipo"] for e in cliente.get(f"/api/app/recepciones/{rec}/auditoria").json()]
    assert "CIERRE" in tipos and "ANULACION" in tipos


def test_el_handheld_puede_repetir_el_envio_sin_contar_dos_veces(cliente, conPacking):
    cuerpo = {"id": "mismo", "sku": "SKU001", "cantidad": 10, "pallet": "A1"}
    a = cliente.post(f"/api/app/recepciones/{conPacking}/conteos", json=cuerpo).json()
    b = cliente.post(f"/api/app/recepciones/{conPacking}/conteos", json=cuerpo).json()
    assert a["duplicado"] is False and b["duplicado"] is True
    assert b["contado"] == 10


def test_el_duplicado_de_un_packing_list_se_consulta_antes_de_cargarlo(cliente, rec):
    resumen = {"huella": "ff00ff00", "lineas": 22, "skus": 22,
               "unidades": 220, "archivo": "PACKING.xlsx"}
    cliente.post(f"/api/app/recepciones/{rec}/packing-list",
                 json={"resultado": {**PACKING, "resumen": resumen}, "origen": "PRINCIPAL"})

    r = cliente.post("/api/app/packing-lists/parecidos",
                     json={"resumen": {**resumen, "archivo": "PACKING (2).xlsx"}})
    assert r.status_code == 200
    assert [h["recepcion"] for h in r.json()] == [rec]


# --------------------------------------------------------------------------- #
# Quién puede qué
# --------------------------------------------------------------------------- #
def test_un_operario_cuenta_pero_no_crea_recepciones(db, operadores):
    c = TestClient(app)
    c.post("/api/auth/login", json={"usuario": "op1", "pin": "2222"})
    assert c.get("/api/app/recepciones").status_code == 200
    assert c.post("/api/app/recepciones", json={"codigo": "X"}).status_code == 403


def test_borrar_una_recepcion_es_solo_del_administrador(db, operadores, cliente, rec):
    """Se lleva la bitácora y la auditoría: no es una operación de supervisión."""
    assert cliente.delete(f"/api/app/recepciones/{rec}").status_code == 403

    admin = Operador(usuario="adm", nombre="Admin", pin_hash=hash_pin("4444"),
                     rol=Rol.ADMIN)
    db.add(admin)
    db.commit()
    c = TestClient(app)
    c.post("/api/auth/login", json={"usuario": "adm", "pin": "4444"})
    assert c.delete(f"/api/app/recepciones/{rec}").status_code == 200
