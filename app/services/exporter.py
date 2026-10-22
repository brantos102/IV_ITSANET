"""Generacion del PACKING LIST FINAL (.xlsx) que se entrega al ejecutivo.

Reglas del flujo de trabajo respetadas al pie de la letra:
  * "No anadir filas"  -> una fila por linea original, en el orden original.
    Los sobrantes de SKU que NO estaban en el packing list van al final.
  * "No caracteres especiales" -> celdas saneadas (sin acentos ni simbolos).
  * "1 SKU en dos pallets se puede misma celda" -> pallets unidos en una celda.

El reparto de la cantidad fisica entre varias lineas del mismo SKU se hace en
orden de linea, llenando cada una hasta su cantidad esperada; el excedente cae
en la ultima linea de ese SKU (que queda marcada como Sobrante).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import EXPORT_DIR, PALLET_SEPARADOR, SANITIZE_EXPORT, SOBRANTES_AL_FINAL
from app.models import EstadoSku, PackingItem, Producto, Recepcion, ScanEvent
from app.services.normalize import entero_si_aplica, limpiar, sanear_celda
from app.services.validation import (
    contado_por_sku, esperado_por_sku, estado_sku_final, ubicaciones_de_sku,
)

COLUMNAS = [
    "ITEM", "Descripción", "ReferenciaPedido", "Factura", "Cantidad", "PrecioUnit",
    "PrecioTotal", "Numerodepiezareemplazo", "Embarque", "Cantidad Física",
    "Validación", "PALLET", "CODIGO BARRA", "COD/PROD", "OBSERVACION", "ok", "POSICION FINAL SUGERIDA",
]

ETIQUETA = {EstadoSku.OK: "Ok", EstadoSku.FALTANTE: "Faltante", EstadoSku.SOBRANTE: "Sobrante",
            EstadoSku.PENDIENTE: "Faltante"}

_AZUL = PatternFill("solid", fgColor="4FC3F7")
_ROJO = PatternFill("solid", fgColor="F4A7A7")
_AMARILLO = PatternFill("solid", fgColor="FFF59D")
_CELESTE = PatternFill("solid", fgColor="BBDEFB")
_BORDE = Border(*[Side(style="thin", color="999999")] * 4)


def _txt(valor) -> str:
    return sanear_celda(valor) if SANITIZE_EXPORT else limpiar(valor)


def _repartir(cantidad_total: float, lineas: list[PackingItem]) -> dict[int, float]:
    """Distribuye la cantidad fisica entre las lineas del mismo SKU."""
    resto = cantidad_total
    asignado: dict[int, float] = {}
    for item in lineas:
        toma = min(max(item.cantidad, 0), max(resto, 0))
        asignado[item.id] = toma
        resto -= toma
    if resto > 0 and lineas:  # excedente -> ultima linea (queda Sobrante)
        asignado[lineas[-1].id] += resto
    return asignado


def _pallets_de(db: Session, recepcion_id: int, sku: str) -> tuple[str, str]:
    ubic = ubicaciones_de_sku(db, recepcion_id, sku)
    celda = PALLET_SEPARADOR.join(u["pallet"] for u in ubic)
    nota = ""
    if len(ubic) > 1:
        nota = "SKU EN " + str(len(ubic)) + " PALLETS: " + ", ".join(
            f"{u['pallet']}={u['cantidad']}" for u in ubic
        )
    return celda, nota


def _observaciones_de(db: Session, recepcion_id: int, sku: str) -> str:
    obs = db.execute(
        select(ScanEvent.observacion)
        .where(
            ScanEvent.recepcion_id == recepcion_id,
            ScanEvent.sku == sku,
            ScanEvent.observacion.is_not(None),
        )
        .order_by(ScanEvent.creado_en)
    ).scalars().all()
    vistos, salida = set(), []
    for o in obs:
        t = _txt(o)
        if t and t not in vistos:
            vistos.add(t)
            salida.append(t)
    return " | ".join(salida)


def _posiciones_de(db,recepcion_id,sku):
    anulados=select(ScanEvent.evento_ref_id).where(ScanEvent.recepcion_id==recepcion_id,ScanEvent.evento_ref_id.is_not(None))
    return ' / '.join(dict.fromkeys(db.scalars(select(ScanEvent.posicion_real).where(
        ScanEvent.recepcion_id==recepcion_id,ScanEvent.sku==sku,ScanEvent.cantidad>0,
        ScanEvent.posicion_real.is_not(None),ScanEvent.id.not_in(anulados)).order_by(ScanEvent.creado_en))))


def construir_filas(db: Session, recepcion: Recepcion) -> list[dict]:
    """Arma las filas del packing list final (sin escribir el archivo)."""
    items = db.execute(
        select(PackingItem)
        .where(PackingItem.recepcion_id == recepcion.id)
        .order_by(PackingItem.linea)
    ).scalars().all()

    esperado = esperado_por_sku(db, recepcion.id)
    contado = contado_por_sku(db, recepcion.id)

    por_sku: dict[str, list[PackingItem]] = defaultdict(list)
    for it in items:
        por_sku[it.sku].append(it)
    reparto: dict[int, float] = {}
    for sku, lineas in por_sku.items():
        reparto.update(_repartir(contado.get(sku, 0.0), lineas))

    skus_existentes = {
        p.sku
        for p in db.execute(
            select(Producto).where(Producto.sku.in_(list(set(esperado) | set(contado))))
        ).scalars()
    } if (esperado or contado) else set()

    filas: list[dict] = []
    for it in items:
        fisica = reparto.get(it.id, 0.0)
        estado = estado_sku_final(it.cantidad, fisica)
        pallet_celda, nota_pallet = _pallets_de(db, recepcion.id, it.sku)
        obs = _observaciones_de(db, recepcion.id, it.sku)
        if estado is EstadoSku.FALTANTE and fisica == 0:
            obs = " | ".join(filter(None, [obs, "FALTANTE CONFIRMADO"]))
        if nota_pallet:
            obs = " | ".join(filter(None, [obs, nota_pallet]))
        ean = db.execute(
            select(ScanEvent.ean).where(
                ScanEvent.recepcion_id == recepcion.id,
                ScanEvent.sku == it.sku,
                ScanEvent.ean.is_not(None),
            ).limit(1)
        ).scalar_one_or_none()

        filas.append({
            "ITEM": _txt(it.sku),
            "Descripción": _txt(it.descripcion),
            "ReferenciaPedido": _txt(it.referencia_pedido),
            "Factura": _txt(it.factura),
            "Cantidad": entero_si_aplica(it.cantidad),
            "PrecioUnit": it.precio_unit,
            "PrecioTotal": it.precio_total,
            "Numerodepiezareemplazo": _txt(it.num_pieza_reemplazo),
            "Embarque": _txt(it.embarque),
            "Cantidad Física": entero_si_aplica(fisica),
            "Validación": ETIQUETA[estado],
            "PALLET": pallet_celda or 0,
            "POSICION FINAL SUGERIDA":_posiciones_de(db,recepcion.id,it.sku),
            "CODIGO BARRA": _txt(ean),
            "COD/PROD": "",
            "OBSERVACION": obs,
            "ok": "ok" if it.sku in skus_existentes else "#N/A",
            "_estado": estado.value,
        })

    # Sobrantes: SKU contados que no estaban en el packing list -> al final.
    extras = sorted(set(contado) - set(esperado))
    for sku in extras:
        if contado[sku] == 0:
            continue
        pallet_celda, nota_pallet = _pallets_de(db, recepcion.id, sku)
        obs = " | ".join(filter(None, [
            _observaciones_de(db, recepcion.id, sku), "SOBRANTE CONFIRMADO", nota_pallet,
        ]))
        ean = db.execute(
            select(ScanEvent.ean).where(
                ScanEvent.recepcion_id == recepcion.id, ScanEvent.sku == sku,
                ScanEvent.ean.is_not(None),
            ).limit(1)
        ).scalar_one_or_none()
        prod = db.get(Producto, sku)
        fila = {
            "ITEM": _txt(sku),
            "Descripción": _txt(prod.descripcion if prod else ""),
            "ReferenciaPedido": "", "Factura": "", "Cantidad": 0,
            "PrecioUnit": None, "PrecioTotal": None, "Numerodepiezareemplazo": "",
            "Embarque": "", "Cantidad Física": entero_si_aplica(contado[sku]),
            "Validación": "Sobrante", "PALLET": pallet_celda or 0,
            "POSICION FINAL SUGERIDA":_posiciones_de(db,recepcion.id,sku),
            "CODIGO BARRA": _txt(ean), "COD/PROD": "", "OBSERVACION": obs,
            "ok": "ok" if prod else "#N/A", "_estado": EstadoSku.SOBRANTE.value,
        }
        if SOBRANTES_AL_FINAL:
            filas.append(fila)
        else:
            filas.append(fila)
    return filas


def exportar_packing_final(db: Session, recepcion: Recepcion, ruta: Path | None = None) -> Path:
    filas = construir_filas(db, recepcion)
    wb = Workbook()
    ws = wb.active
    ws.title = "REV"

    for c, nombre in enumerate(COLUMNAS, start=1):
        celda = ws.cell(row=1, column=c, value=nombre)
        celda.font = Font(bold=True)
        celda.fill = _AZUL
        celda.border = _BORDE
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for r, fila in enumerate(filas, start=2):
        relleno = {
            "FALTANTE": _ROJO, "SOBRANTE": _CELESTE,
        }.get(fila["_estado"])
        if not relleno and fila["OBSERVACION"]:
            relleno = _AMARILLO
        for c, nombre in enumerate(COLUMNAS, start=1):
            celda = ws.cell(row=r, column=c, value=fila[nombre])
            celda.border = _BORDE
            if relleno:
                celda.fill = relleno

    anchos = [18, 42, 16, 14, 10, 11, 12, 20, 12, 14, 12, 14, 18, 12, 40, 8, 30]
    for i, ancho in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(i)].width = ancho
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNAS))}{len(filas) + 1}"

    _hoja_resumen(wb, db, recepcion, filas)

    if ruta is None:
        marca = datetime.now().strftime("%Y%m%d-%H%M")
        nombre = f"PL-FINAL_{sanear_celda(recepcion.codigo).replace(' ', '_')}_{marca}.xlsx"
        ruta = EXPORT_DIR / nombre
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    wb.save(ruta)
    return ruta


def _hoja_resumen(wb: Workbook, db: Session, recepcion: Recepcion, filas: list[dict]) -> None:
    from app.services.validation import resumen_recepcion

    res = resumen_recepcion(db, recepcion)
    ws = wb.create_sheet("RESUMEN")
    ws["A1"], ws["A1"].font = "RESUMEN DE VALIDACION FISICA", Font(bold=True, size=14)
    datos = [
        ("Recepcion", recepcion.codigo),
        ("Cliente", recepcion.cliente),
        ("Estado", recepcion.estado.value),
        ("Generado", datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("", ""),
        ("SKUs en packing list", res["totales"]["skus_packing_list"]),
        ("Unidades segun sistema", res["totales"]["unidades_sistema"]),
        ("Unidades fisicas", res["totales"]["unidades_fisicas"]),
        ("Diferencia", res["totales"]["diferencia"]),
        ("", ""),
        ("SKU Ok", res["por_estado"].get("OK", 0)),
        ("SKU Faltante", res["por_estado"].get("FALTANTE", 0)),
        ("SKU Sobrante", res["por_estado"].get("SOBRANTE", 0)),
        ("Exactitud %", res["totales"]["exactitud_pct"]),
        ("", ""),
        ("Operadores", res["totales"]["operadores"]),
        ("Eventos de conteo", res["totales"]["eventos"]),
        ("SKU por crear en Depot", res["totales"]["skus_sin_crear_en_depot"]),
    ]
    for i, (k, v) in enumerate(datos, start=3):
        ws.cell(row=i, column=1, value=k).font = Font(bold=bool(k))
        ws.cell(row=i, column=2, value=v)
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 30
