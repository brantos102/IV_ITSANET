"""El maestro de productos llega en dos formatos y los dos tienen que entrar.

Uno es una exportación directa de la base de Depot (producto_id, unidad_id…);
el otro es lo que devuelve la API del WMS, en mayúsculas y con puntos
(«COD. PRODUCTO»). Con solo el primero, un maestro sacado de la API se rechazaba
entero pidiendo una columna que ese archivo nunca va a tener.
"""
from __future__ import annotations

import openpyxl
import pytest

from app.services.importer import leer_maestro


def guardar(tmp_path, filas, hoja="MAESTRO"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = hoja
    for f in filas:
        ws.append(f)
    ruta = tmp_path / "maestro.xlsx"
    wb.save(ruta)
    return ruta


def test_el_formato_del_wms(tmp_path):
    ruta = guardar(tmp_path, [
        ["COD. PRODUCTO", "DESCRIPCION", "UNIDAD", "FAMILIA", "COD. CLIENTE"],
        ["2H0525345", "ARANDELA", "UND", "REPUESTOS", "VENTURA"],
    ])
    filas = list(leer_maestro(ruta))
    assert len(filas) == 1
    assert filas[0]["sku"] == "2H0525345"
    assert filas[0]["descripcion"] == "ARANDELA"
    assert filas[0]["unidad"] == "UND"
    assert filas[0]["cliente"] == "VENTURA"


def test_el_formato_de_la_base_sigue_entrando(tmp_path):
    """Lo que ya funcionaba no puede dejar de funcionar."""
    ruta = guardar(tmp_path, [
        ["producto_id", "descripcion", "unidad_id", "cliente_id"],
        ["2H0525345", "ARANDELA", "UND", "VENTURA"],
    ])
    filas = list(leer_maestro(ruta))
    assert len(filas) == 1
    assert filas[0]["sku"] == "2H0525345"


@pytest.mark.parametrize("encabezado", ["COD. PRODUCTO", "CODIGO", "SKU", "ITEM",
                                        "producto_id", "cod.producto"])
def test_los_nombres_que_se_aceptan_para_el_codigo(tmp_path, encabezado):
    ruta = guardar(tmp_path, [[encabezado, "DESCRIPCION"], ["X1", "PIEZA"]])
    assert [f["sku"] for f in leer_maestro(ruta)] == ["X1"]


def test_sin_columna_de_codigo_dice_que_columnas_trae(tmp_path):
    """«Falta producto_id» mandaba a buscar una columna inexistente."""
    ruta = guardar(tmp_path, [["PESO", "VOLUMEN", "ORIGEN"], [1, 2, "X"]], hoja="Hoja1")
    with pytest.raises(ValueError) as e:
        list(leer_maestro(ruta))
    m = str(e.value)
    assert "PESO" in m and "VOLUMEN" in m, m
    assert "Hoja1" in m, "tiene que decir en qué hoja miró"
    assert "packing list" in m, "y recordar que puede haberse equivocado de recuadro"


def test_las_filas_sin_codigo_se_saltan(tmp_path):
    ruta = guardar(tmp_path, [
        ["COD. PRODUCTO", "DESCRIPCION"],
        ["X1", "PIEZA"],
        ["", "FILA VACIA"],
        ["0", "CERO NO ES UN CODIGO"],
        ["X2", "OTRA"],
    ])
    assert [f["sku"] for f in leer_maestro(ruta)] == ["X1", "X2"]


def test_el_catalogo_se_carga_por_la_api(cliente, tmp_path):
    """De punta a punta, como lo hace la pantalla."""
    ruta = guardar(tmp_path, [
        ["COD. PRODUCTO", "DESCRIPCION", "UNIDAD"],
        ["A1", "PIEZA UNO", "UND"],
        ["A2", "PIEZA DOS", "UND"],
    ])
    with ruta.open("rb") as fh:
        r = cliente.post("/api/catalogo/maestro", files={"archivo": ("maestro.xlsx", fh)})
    assert r.status_code == 200, r.text
    assert r.json()["procesados"] == 2
    assert r.json()["total_en_cache"] == 2


def test_un_archivo_que_no_sirve_responde_422_y_no_500(cliente, tmp_path):
    ruta = guardar(tmp_path, [["PESO"], [1]], hoja="Hoja1")
    with ruta.open("rb") as fh:
        r = cliente.post("/api/catalogo/maestro", files={"archivo": ("raro.xlsx", fh)})
    assert r.status_code == 422, r.text
    assert "PESO" in r.json()["detail"]
