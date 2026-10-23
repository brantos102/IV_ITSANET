"""KPIs historicos sobre el libro mayor de escaneos.

Como cada conteo es un evento con fecha, SKU, pallet y operador, los KPIs
salen de consultas agregadas sin almacenamiento adicional.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import Float, case, cast, func, select
from sqlalchemy.orm import Session

from app.models import (
    EstadoFisico, EstadoRecepcion, Operador, PackingItem, Recepcion, ScanEvent,
    SkuPendiente, TipoEvento,
)
from app.services.normalize import entero_si_aplica
from app.services.validation import (
    contado_por_sku, esperado_por_sku, estado_sku_final,
)


def _rango(desde: str | None, hasta: str | None):
    d = datetime.fromisoformat(desde) if desde else datetime.now() - timedelta(days=90)
    h = datetime.fromisoformat(hasta) if hasta else datetime.now() + timedelta(days=1)
    return d, h


def kpis_globales(db: Session, desde: str | None = None, hasta: str | None = None) -> dict:
    d, h = _rango(desde, hasta)
    recs = db.execute(
        select(Recepcion).where(Recepcion.creado_en >= d, Recepcion.creado_en <= h)
        .order_by(Recepcion.creado_en.desc())
    ).scalars().all()

    tot_ok = tot_falt = tot_sobr = 0
    u_sis = u_fis = 0.0
    por_recepcion = []
    for r in recs:
        esp, cont = esperado_por_sku(db, r.id), contado_por_sku(db, r.id)
        skus = set(esp) | set(cont)
        ok = falt = sobr = 0
        for sku in skus:
            st = estado_sku_final(esp.get(sku, 0.0), cont.get(sku, 0.0)).value
            ok += st == "OK"
            falt += st == "FALTANTE"
            sobr += st == "SOBRANTE"
        tot_ok, tot_falt, tot_sobr = tot_ok + ok, tot_falt + falt, tot_sobr + sobr
        se, sc = sum(esp.values()), sum(cont.values())
        u_sis, u_fis = u_sis + se, u_fis + sc
        dur = None
        if r.cerrado_en:
            dur = round((r.cerrado_en - r.creado_en).total_seconds() / 3600, 2)
        por_recepcion.append({
            "id": r.id, "codigo": r.codigo, "estado": r.estado.value,
            "fecha": r.creado_en.date().isoformat(),
            "skus": len(skus), "ok": ok, "faltante": falt, "sobrante": sobr,
            "unidades_sistema": entero_si_aplica(se), "unidades_fisicas": entero_si_aplica(sc),
            "exactitud_pct": round(100 * ok / len(skus), 1) if skus else 0.0,
            "horas": dur,
        })

    total_skus = tot_ok + tot_falt + tot_sobr
    return {
        "rango": {"desde": d.date().isoformat(), "hasta": h.date().isoformat()},
        "recepciones": len(recs),
        "recepciones_abiertas": sum(
            1 for r in recs if r.estado in (EstadoRecepcion.ABIERTA, EstadoRecepcion.EN_VALIDACION)
        ),
        "skus_validados": total_skus,
        "ok": tot_ok, "faltante": tot_falt, "sobrante": tot_sobr,
        "exactitud_pct": round(100 * tot_ok / total_skus, 1) if total_skus else 0.0,
        "tasa_discrepancia_pct": round(100 * (tot_falt + tot_sobr) / total_skus, 1)
        if total_skus else 0.0,
        "unidades_sistema": entero_si_aplica(u_sis),
        "unidades_fisicas": entero_si_aplica(u_fis),
        "diferencia_unidades": entero_si_aplica(u_fis - u_sis),
        "por_recepcion": por_recepcion,
    }


def kpis_por_operador(db: Session, desde: str | None = None, hasta: str | None = None) -> list[dict]:
    d, h = _rango(desde, hasta)
    filas = db.execute(
        select(
            Operador.id, Operador.nombre, Operador.rol,
            func.count(ScanEvent.id),
            func.sum(case((ScanEvent.cantidad > 0, ScanEvent.cantidad), else_=0)),
            func.count(func.distinct(ScanEvent.sku)),
            func.count(func.distinct(ScanEvent.recepcion_id)),
            func.sum(case((ScanEvent.tipo == TipoEvento.ANULACION, 1), else_=0)),
            func.sum(case((ScanEvent.estado_fisico == EstadoFisico.MALO, 1), else_=0)),
            func.min(ScanEvent.creado_en), func.max(ScanEvent.creado_en),
        )
        .join(ScanEvent, ScanEvent.operador_id == Operador.id)
        .where(ScanEvent.creado_en >= d, ScanEvent.creado_en <= h)
        .group_by(Operador.id)
        .order_by(func.count(ScanEvent.id).desc())
    ).all()

    salida = []
    for (oid, nombre, rol, n, unidades, skus, recs, anul, malos, t0, t1) in filas:
        horas = (t1 - t0).total_seconds() / 3600 if t0 and t1 else 0
        salida.append({
            "operador_id": oid, "nombre": nombre, "rol": rol.value,
            "eventos": n, "unidades": entero_si_aplica(float(unidades or 0)),
            "skus_distintos": skus, "recepciones": recs,
            "anulaciones": int(anul or 0),
            "items_mal_estado": int(malos or 0),
            "tasa_anulacion_pct": round(100 * (anul or 0) / n, 1) if n else 0.0,
            "scans_por_hora": round(n / horas, 1) if horas > 0.05 else None,
        })
    return salida


def kpis_por_sku(db: Session, limite: int = 100, solo_problematicos: bool = False) -> list[dict]:
    """Historico por SKU: cuantas veces se recibio y cuantas hubo discrepancia."""
    recs = db.execute(select(Recepcion.id, Recepcion.codigo, Recepcion.creado_en)).all()
    acum: dict[str, dict] = {}
    for rid, codigo, fecha in recs:
        esp, cont = esperado_por_sku(db, rid), contado_por_sku(db, rid)
        for sku in set(esp) | set(cont):
            e, c = esp.get(sku, 0.0), cont.get(sku, 0.0)
            st = estado_sku_final(e, c).value
            a = acum.setdefault(sku, {
                "sku": sku, "recepciones": 0, "ok": 0, "faltante": 0, "sobrante": 0,
                "unidades_sistema": 0.0, "unidades_fisicas": 0.0, "ultima_recepcion": None,
                "ultima_fecha": None,
            })
            a["recepciones"] += 1
            a[st.lower()] += 1
            a["unidades_sistema"] += e
            a["unidades_fisicas"] += c
            if a["ultima_fecha"] is None or fecha > a["ultima_fecha"]:
                a["ultima_fecha"], a["ultima_recepcion"] = fecha, codigo

    salida = []
    for a in acum.values():
        disc = a["faltante"] + a["sobrante"]
        a["tasa_discrepancia_pct"] = round(100 * disc / a["recepciones"], 1) if a["recepciones"] else 0
        a["diferencia_unidades"] = entero_si_aplica(a["unidades_fisicas"] - a["unidades_sistema"])
        a["unidades_sistema"] = entero_si_aplica(a["unidades_sistema"])
        a["unidades_fisicas"] = entero_si_aplica(a["unidades_fisicas"])
        a["ultima_fecha"] = a["ultima_fecha"].date().isoformat() if a["ultima_fecha"] else None
        if solo_problematicos and disc == 0:
            continue
        salida.append(a)

    salida.sort(key=lambda x: (-x["tasa_discrepancia_pct"], -x["recepciones"]))
    return salida[:limite]


def serie_diaria(db: Session, dias: int = 30) -> list[dict]:
    desde = datetime.now() - timedelta(days=dias)
    filas = db.execute(
        select(
            func.date(ScanEvent.creado_en),
            func.count(ScanEvent.id),
            func.sum(cast(ScanEvent.cantidad, Float)),
            func.count(func.distinct(ScanEvent.recepcion_id)),
            func.count(func.distinct(ScanEvent.operador_id)),
        )
        .where(ScanEvent.creado_en >= desde)
        .group_by(func.date(ScanEvent.creado_en))
        .order_by(func.date(ScanEvent.creado_en))
    ).all()
    return [
        {"fecha": str(f), "eventos": n, "unidades": entero_si_aplica(float(u or 0)),
         "recepciones": r, "operadores": o}
        for f, n, u, r, o in filas
    ]


def skus_pendientes_creacion(db: Session) -> list[dict]:
    filas = db.execute(
        select(SkuPendiente, Recepcion.codigo)
        .join(Recepcion, Recepcion.id == SkuPendiente.recepcion_id)
        .order_by(SkuPendiente.creado_en.desc())
    ).all()
    return [
        {
            "id": p.id, "sku": p.sku, "descripcion": p.descripcion, "ean": p.ean,
            "estado": p.estado.value, "estado_depot": p.estado_depot.value,
            "recepcion": codigo, "creado_en": p.creado_en.isoformat(),
            "notas": p.notas,
        }
        for p, codigo in filas
    ]
