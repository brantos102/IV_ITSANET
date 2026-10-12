"""Prueba de concurrencia real: varios operadores escaneando a la vez.

Es la garantia central del diseno: como cada conteo es un INSERT en un libro
mayor append-only (y no un UPDATE sobre un total), no hay 'lost updates'
aunque varios operadores cuenten el mismo SKU al mismo tiempo.
"""
from __future__ import annotations

import threading

from app.db import SessionLocal
from app.models import Operador, PackingItem, Producto, Recepcion, Rol, ScanEvent
from app.security import hash_pin
from app.services import validation as val

HILOS = 8
POR_HILO = 25


def test_conteos_simultaneos_no_pierden_registros(db):
    """8 operadores x 25 conteos del MISMO SKU = 200 unidades exactas."""
    rec = Recepcion(codigo="REC-CONC", cliente="VENTURA")
    db.add(rec)
    db.flush()
    db.add(PackingItem(recepcion_id=rec.id, linea=1, sku="SKUC", cantidad=HILOS * POR_HILO))
    db.add(Producto(sku="SKUC", descripcion="PIEZA CONCURRENTE"))
    ops = [
        Operador(usuario=f"c{i}", nombre=f"Operador {i}", pin_hash=hash_pin("0000"),
                 rol=Rol.OPERADOR)
        for i in range(HILOS)
    ]
    db.add_all(ops)
    db.commit()
    rec_id = rec.id
    op_ids = [o.id for o in ops]

    errores: list[Exception] = []
    barrera = threading.Barrier(HILOS)

    def trabajar(op_id: int, pallet: str) -> None:
        # Cada hilo con su propia sesion, como cada operador con su dispositivo.
        with SessionLocal() as s:
            r = s.get(Recepcion, rec_id)
            o = s.get(Operador, op_id)
            barrera.wait()          # arrancan todos a la vez
            for _ in range(POR_HILO):
                try:
                    val.registrar_scan(s, r, o, codigo="SKUC", cantidad=1, pallet=pallet)
                except Exception as exc:  # noqa: BLE001
                    errores.append(exc)

    hilos = [
        threading.Thread(target=trabajar, args=(op_id, f"A{i % 3 + 1}"))
        for i, op_id in enumerate(op_ids)
    ]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert not errores, f"errores de concurrencia: {errores[:3]}"

    with SessionLocal() as s:
        total = val.contado_de_sku(s, rec_id, "SKUC")
        eventos = s.query(ScanEvent).filter_by(recepcion_id=rec_id).count()
        # Ni una sola unidad perdida ni duplicada.
        assert total == HILOS * POR_HILO
        assert eventos == HILOS * POR_HILO
        # Cada operador conservo su atribucion.
        por_op = {}
        for e in s.query(ScanEvent).filter_by(recepcion_id=rec_id):
            por_op[e.operador_id] = por_op.get(e.operador_id, 0) + e.cantidad
        assert set(por_op) == set(op_ids)
        assert all(v == POR_HILO for v in por_op.values())


def test_idempotencia_bajo_concurrencia(db):
    """La misma clave enviada por varios hilos solo puede registrarse una vez."""
    rec = Recepcion(codigo="REC-IDEM", cliente="VENTURA")
    db.add(rec)
    db.flush()
    db.add(PackingItem(recepcion_id=rec.id, linea=1, sku="SKUI", cantidad=100))
    op = Operador(usuario="idem", nombre="Idem", pin_hash=hash_pin("0000"))
    db.add(op)
    db.commit()
    rec_id, op_id = rec.id, op.id

    resultados: list[dict] = []
    barrera = threading.Barrier(6)

    def enviar() -> None:
        with SessionLocal() as s:
            r, o = s.get(Recepcion, rec_id), s.get(Operador, op_id)
            barrera.wait()
            try:
                resultados.append(val.registrar_scan(
                    s, r, o, codigo="SKUI", cantidad=5, pallet="A1",
                    idempotency_key="misma-clave",
                ))
            except Exception:  # noqa: BLE001,S110
                pass

    hilos = [threading.Thread(target=enviar) for _ in range(6)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    with SessionLocal() as s:
        assert val.contado_de_sku(s, rec_id, "SKUI") == 5
        assert s.query(ScanEvent).filter_by(recepcion_id=rec_id).count() == 1
