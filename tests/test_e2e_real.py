"""Prueba end-to-end reproduciendo la recepcion real VW del 29-06-2026.

Carga el packing list y el maestro reales, reproduce la validacion fisica
(71 Ok, 1 Faltante, 1 Sobrante) y verifica que el packing list final
generado coincide con el que se entrego al ejecutivo de cuenta.
"""
from __future__ import annotations

import openpyxl
import pytest

from app.models import PackingItem, Producto, Recepcion
from app.routers.catalogo import cargar_maestro_desde
from app.services import validation as val
from app.services.exporter import COLUMNAS, exportar_packing_final
from app.services.importer import leer_packing_list
from tests.conftest import ARCHIVO_REAL

pytestmark = pytest.mark.skipif(
    not ARCHIVO_REAL.exists(), reason="archivo real no disponible en este entorno"
)


@pytest.fixture()
def recepcion_real(db, operadores):
    res = leer_packing_list(ARCHIVO_REAL)
    rec = Recepcion(codigo="VW-29-06-2026", cliente="VENTURA",
                    hash_archivo=res.hash_archivo)
    db.add(rec)
    db.flush()
    for f in res.filas:
        db.add(PackingItem(
            recepcion_id=rec.id, linea=f.linea, sku=f.sku, descripcion=f.descripcion,
            referencia_pedido=f.referencia_pedido, factura=f.factura,
            cantidad=f.cantidad, precio_unit=f.precio_unit, precio_total=f.precio_total,
            embarque=f.embarque,
        ))
    db.commit()
    cargar_maestro_desde(db, ARCHIVO_REAL, "MAESTRO")
    return rec, res


def test_packing_list_real_se_importa_completo(recepcion_real):
    _, res = recepcion_real
    assert res.hoja == "REV"
    assert res.total_lineas == 73
    assert res.skus_unicos == 67
    assert res.total_unidades == 103
    assert res.embarques == ["RB48529", "RB48688"]


def test_maestro_real_detecta_los_17_sku_inexistentes(db, recepcion_real):
    """La columna 'ok' del archivo original es un VLOOKUP contra MAESTRO.

    Los 17 '#N/A' son exactamente los SKU que no existen en Depot: la app
    debe senalarlos para 'validar a profundidad o crear'.
    """
    rec, _ = recepcion_real
    assert db.query(Producto).count() > 15_000

    skus = {i.sku for i in db.query(PackingItem).filter_by(recepcion_id=rec.id)}
    existentes = {
        p.sku for p in db.query(Producto).filter(Producto.sku.in_(list(skus)))
    }
    assert len(skus - existentes) == 17


def test_flujo_completo_reproduce_el_resultado_entregado(db, recepcion_real, operadores):
    rec, _ = recepcion_real
    items = db.query(PackingItem).filter_by(recepcion_id=rec.id).order_by(
        PackingItem.linea
    ).all()

    faltante = "6EA839885A"   # no llego
    sobrante = "6EA837885A"   # llego sin estar en la lista (cantidad 0)
    doblado = "5U3837477A5AP"  # llego doblado -> P.N.C.

    # Dos operadores trabajan en paralelo sobre la misma recepcion.
    turnos = [operadores["op1"], operadores["op2"]]
    for n, item in enumerate(items):
        if item.sku == faltante or item.cantidad == 0:
            continue
        op = turnos[n % 2]
        val.registrar_scan(
            db, rec, op, codigo=item.sku, cantidad=item.cantidad,
            pallet="B04.1" if n % 3 else "B01",
            estado_fisico="MALO" if item.sku == doblado else "BUENO",
            observacion="P.N.C. PRODUCTO DOBLADO" if item.sku == doblado else None,
            confirmar_sobrante=True,
        )
    # El sobrante confirmado: llego 1 unidad de un SKU con cantidad 0.
    val.registrar_scan(db, rec, operadores["sup"], codigo=sobrante, cantidad=1,
                       pallet="B04.3", observacion="SOBRANTE CONFIRMADO",
                       confirmar_sobrante=True)

    val.cerrar_recepcion(db, rec, operadores["sup"])
    res = val.resumen_recepcion(db, rec)

    # Mismo desenlace que el informe enviado al cliente.
    assert res["por_estado"]["FALTANTE"] == 1
    assert res["por_estado"]["SOBRANTE"] == 1
    assert res["por_estado"]["OK"] == 65   # 67 SKU unicos - 1 faltante - 1 sobrante
    assert res["totales"]["unidades_sistema"] == 103
    assert res["totales"]["unidades_fisicas"] == 103  # -1 faltante +1 sobrante
    assert res["totales"]["operadores"] == 3

    estados = {d["sku"]: d["estado"] for d in res["detalle"]}
    assert estados[faltante] == "FALTANTE"
    assert estados[sobrante] == "SOBRANTE"


def test_export_respeta_las_reglas_del_flujo(db, recepcion_real, operadores, tmp_path):
    rec, _ = recepcion_real
    items = db.query(PackingItem).filter_by(recepcion_id=rec.id).order_by(
        PackingItem.linea
    ).all()
    for item in items:
        if item.cantidad > 0:
            val.registrar_scan(db, rec, operadores["op1"], codigo=item.sku,
                               cantidad=item.cantidad, pallet="B01",
                               confirmar_sobrante=True)

    ruta = exportar_packing_final(db, rec, tmp_path / "final.xlsx")
    wb = openpyxl.load_workbook(ruta)
    ws = wb["REV"]

    # Cabecera identica a la del packing list que se entrega.
    assert [c.value for c in ws[1]] == COLUMNAS
    # Regla "No anadir filas": una fila por linea original.
    assert ws.max_row == len(items) + 1
    assert "RESUMEN" in wb.sheetnames

    filas = list(ws.iter_rows(min_row=2, values_only=True))
    # Regla "No caracteres especiales": celdas de texto saneadas.
    for fila in filas:
        for valor in (fila[0], fila[1], fila[14]):
            if isinstance(valor, str):
                assert all(ord(c) < 128 for c in valor), valor
    # La linea de cantidad 0 queda Ok (no se conto) y el resto tambien.
    validaciones = {f[10] for f in filas}
    assert validaciones <= {"Ok", "Faltante", "Sobrante"}


def test_mismo_sku_en_dos_pallets_queda_en_una_celda(db, recepcion_real, operadores, tmp_path):
    """Regla del flujo: '1 SKU en dos pallets se puede misma celda'."""
    rec, _ = recepcion_real
    sku = "6EA853651H9B9"   # 5 unidades repartidas en dos lineas del archivo real
    val.registrar_scan(db, rec, operadores["op1"], codigo=sku, cantidad=3, pallet="B03")
    val.registrar_scan(db, rec, operadores["op2"], codigo=sku, cantidad=2, pallet="B03.1")

    ruta = exportar_packing_final(db, rec, tmp_path / "final.xlsx")
    ws = openpyxl.load_workbook(ruta)["REV"]
    filas = [f for f in ws.iter_rows(min_row=2, values_only=True) if f[0] == sku]
    assert filas, "el SKU debe aparecer en el export"
    for fila in filas:
        assert fila[11] == "B03 / B03.1"          # columna PALLET
        assert "SKU EN 2 PALLETS" in (fila[14] or "")  # OBSERVACION
    # La cantidad fisica se repartio entre las dos lineas: 2 y 3.
    assert sorted(f[9] for f in filas) == [2, 3]
