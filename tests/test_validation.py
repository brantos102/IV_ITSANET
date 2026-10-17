"""Pruebas del motor de validacion: concurrencia, pallets, estados."""
from __future__ import annotations

import pytest

from app.models import (
    EstadoRecepcion, EstadoSku, PackingItem, Producto, Recepcion, ScanEvent,
)
from app.services import validation as val
from app.services.validation import ErrorValidacion


def _recepcion(db, lineas=((("SKU1"), 10),)):
    rec = Recepcion(codigo="REC-TEST", cliente="VENTURA")
    db.add(rec)
    db.flush()
    for i, (sku, cant) in enumerate(lineas, start=1):
        db.add(PackingItem(recepcion_id=rec.id, linea=i, sku=sku,
                           descripcion=f"DESC {sku}", cantidad=cant))
    db.add(Producto(sku="SKU1", descripcion="PIEZA UNO"))
    db.commit()
    return rec


def test_conteo_de_dos_operadores_suma_sin_cruzarse(db, operadores):
    """El caso que exige la bodega: dos personas cuentan el mismo SKU a la vez."""
    rec = _recepcion(db, [("SKU1", 10)])
    val.registrar_scan(db, rec, operadores["op1"], codigo="SKU1", cantidad=4, pallet="A1")
    val.registrar_scan(db, rec, operadores["op2"], codigo="SKU1", cantidad=6, pallet="A2")
    assert val.contado_de_sku(db, rec.id, "SKU1") == 10
    # Cada conteo quedo como evento propio, con su autor.
    eventos = db.query(ScanEvent).filter_by(recepcion_id=rec.id).all()
    assert len(eventos) == 2
    assert {e.operador_id for e in eventos} == {operadores["op1"].id, operadores["op2"].id}


def test_mismo_sku_en_varios_pallets_y_sugerencia(db, operadores):
    rec = _recepcion(db, [("SKU1", 10)])
    val.registrar_scan(db, rec, operadores["op1"], codigo="SKU1", cantidad=6, pallet="B04")
    val.registrar_scan(db, rec, operadores["op2"], codigo="SKU1", cantidad=4, pallet="B04.1")

    ubic = val.ubicaciones_de_sku(db, rec.id, "SKU1")
    assert [u["pallet"] for u in ubic] == ["B04", "B04.1"]   # mayor cantidad primero
    assert [u["cantidad"] for u in ubic] == [6, 4]

    # El lookup sugiere el pallet donde ya se guardo el item.
    r = val.lookup(db, rec, "SKU1")
    assert r.pallet_sugerido == "B04"
    assert any("ya fue guardado en" in a for a in r.avisos)


def test_idempotencia_evita_doble_conteo(db, operadores):
    """Un doble disparo del lector o un reintento de red no debe sumar dos veces."""
    rec = _recepcion(db, [("SKU1", 10)])
    a = val.registrar_scan(db, rec, operadores["op1"], codigo="SKU1", cantidad=3,
                           pallet="A1", idempotency_key="k-123")
    b = val.registrar_scan(db, rec, operadores["op1"], codigo="SKU1", cantidad=3,
                           pallet="A1", idempotency_key="k-123")
    assert b["duplicado"] is True
    assert a["evento_id"] == b["evento_id"]
    assert val.contado_de_sku(db, rec.id, "SKU1") == 3


def test_sobrante_requiere_confirmacion_explicita(db, operadores):
    rec = _recepcion(db, [("SKU1", 2)])
    with pytest.raises(ErrorValidacion) as exc:
        val.registrar_scan(db, rec, operadores["op1"], codigo="SKU1", cantidad=3, pallet="A1")
    assert exc.value.codigo == "CONFIRMAR_SOBRANTE"
    assert val.contado_de_sku(db, rec.id, "SKU1") == 0   # nada se registro

    val.registrar_scan(db, rec, operadores["op1"], codigo="SKU1", cantidad=3,
                       pallet="A1", confirmar_sobrante=True)
    assert val.contado_de_sku(db, rec.id, "SKU1") == 3


def test_pallet_invalido_se_rechaza(db, operadores):
    rec = _recepcion(db)
    with pytest.raises(ErrorValidacion) as exc:
        val.registrar_scan(db, rec, operadores["op1"], codigo="SKU1", cantidad=1, pallet="A 1..2")
    assert exc.value.codigo == "PALLET_INVALIDO"


def test_mal_estado_exige_observacion(db, operadores):
    rec = _recepcion(db)
    with pytest.raises(ErrorValidacion) as exc:
        val.registrar_scan(db, rec, operadores["op1"], codigo="SKU1", cantidad=1,
                           pallet="A1", estado_fisico="MALO")
    assert exc.value.codigo == "OBSERVACION_REQUERIDA"
    val.registrar_scan(db, rec, operadores["op1"], codigo="SKU1", cantidad=1, pallet="A1",
                       estado_fisico="MALO", observacion="P.N.C. PRODUCTO DOBLADO")
    assert val.contado_de_sku(db, rec.id, "SKU1") == 1


def test_anulacion_es_evento_compensatorio_no_borrado(db, operadores):
    rec = _recepcion(db)
    r = val.registrar_scan(db, rec, operadores["op1"], codigo="SKU1", cantidad=5, pallet="A1")
    val.anular_scan(db, rec, operadores["sup"], r["evento_id"], "conteo erroneo")
    assert val.contado_de_sku(db, rec.id, "SKU1") == 0
    # El evento original sigue existiendo: trazabilidad intacta.
    assert db.get(ScanEvent, r["evento_id"]) is not None
    assert db.query(ScanEvent).filter_by(recepcion_id=rec.id).count() == 2
    with pytest.raises(ErrorValidacion):
        val.anular_scan(db, rec, operadores["sup"], r["evento_id"], "otra vez")


def test_sku_fuera_del_packing_list_es_sobrante(db, operadores):
    rec = _recepcion(db, [("SKU1", 1)])
    r = val.lookup(db, rec, "SKUX")
    assert r.en_packing_list is False
    assert any("NO esta en el packing list" in a for a in r.avisos)
    val.registrar_scan(db, rec, operadores["op1"], codigo="SKUX", cantidad=1,
                       pallet="B04.3", confirmar_sobrante=True)
    resumen = val.resumen_recepcion(db, rec)
    fila = next(d for d in resumen["detalle"] if d["sku"] == "SKUX")
    assert fila["estado"] == EstadoSku.SOBRANTE.value
    assert fila["en_packing_list"] is False


def test_sku_no_existente_en_depot_queda_pendiente(db, operadores):
    from app.models import SkuPendiente

    rec = _recepcion(db, [("SKU1", 1), ("SKUNUEVO", 1)])
    r = val.lookup(db, rec, "SKUNUEVO")
    assert r.depot["existe"] is False
    assert r.depot["accion"] == "CREAR"
    val.registrar_scan(db, rec, operadores["op1"], codigo="SKUNUEVO", cantidad=1,
                       pallet="A1", ean="7501234567890")
    p = db.query(SkuPendiente).filter_by(recepcion_id=rec.id, sku="SKUNUEVO").one()
    assert p.ean == "7501234567890"


def test_cierre_bloquea_escaneos(db, operadores):
    rec = _recepcion(db)
    val.registrar_scan(db, rec, operadores["op1"], codigo="SKU1", cantidad=10, pallet="A1")
    val.cerrar_recepcion(db, rec, operadores["sup"])
    assert rec.estado is EstadoRecepcion.CERRADA
    with pytest.raises(ErrorValidacion) as exc:
        val.registrar_scan(db, rec, operadores["op1"], codigo="SKU1", cantidad=1, pallet="A1")
    assert exc.value.codigo == "RECEPCION_CERRADA"
    val.reabrir_recepcion(db, rec, operadores["sup"], "faltaba un bulto")
    val.registrar_scan(db, rec, operadores["op1"], codigo="SKU1", cantidad=1,
                       pallet="A1", confirmar_sobrante=True)


def test_estados_faltante_ok_sobrante(db, operadores):
    rec = _recepcion(db, [("SKU1", 5), ("SKU2", 3), ("SKU3", 2)])
    val.registrar_scan(db, rec, operadores["op1"], codigo="SKU1", cantidad=5, pallet="A1")
    val.registrar_scan(db, rec, operadores["op1"], codigo="SKU2", cantidad=1, pallet="A1")
    val.registrar_scan(db, rec, operadores["op1"], codigo="SKU3", cantidad=4, pallet="A1",
                       confirmar_sobrante=True)
    val.cerrar_recepcion(db, rec, operadores["sup"])
    res = val.resumen_recepcion(db, rec)
    estados = {d["sku"]: d["estado"] for d in res["detalle"]}
    assert estados == {"SKU1": "OK", "SKU2": "FALTANTE", "SKU3": "SOBRANTE"}
    assert res["totales"]["diferencia"] == 0   # -2 +2
