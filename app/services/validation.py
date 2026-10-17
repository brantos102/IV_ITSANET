"""Motor de validacion fisica.

Reglas implementadas (del flujo de trabajo):
  * Un packing list -> una unica base por recepcion; varios operadores escriben
    en ella sin cruzarse, porque cada conteo es un INSERT en el libro mayor.
  * Un mismo SKU puede quedar en varios pallets; el sistema SUGIERE el pallet
    donde ya se guardo ese SKU antes de aceptar uno nuevo.
  * Pallets alfanumericos (A1) con subpallets secuenciales (A1.1, A1.2).
  * Estado por SKU: Ok / Faltante / Sobrante segun fisico vs sistema.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Auditoria, EstadoDepot, EstadoFisico, EstadoRecepcion, EstadoSku, Operador,
    PackingItem, Pallet, Recepcion, ScanEvent, SkuPendiente, TipoEvento, utcnow,
)
from app.services import depot as depot_svc
from app.services.normalize import (
    entero_si_aplica, limpiar, normalizar_ean, normalizar_pallet, normalizar_sku,
    pallet_padre, pallet_valido,
)


class ErrorValidacion(ValueError):
    """Error de negocio: se devuelve al operador como 400/409."""

    def __init__(self, mensaje: str, codigo: str = "ERROR"):
        super().__init__(mensaje)
        self.codigo = codigo


# --------------------------------------------------------------------------- #
# Consultas agregadas (los totales SIEMPRE se derivan del libro mayor)
# --------------------------------------------------------------------------- #
def esperado_por_sku(db: Session, recepcion_id: int) -> dict[str, float]:
    filas = db.execute(
        select(PackingItem.sku, func.sum(PackingItem.cantidad))
        .where(PackingItem.recepcion_id == recepcion_id)
        .group_by(PackingItem.sku)
    ).all()
    return {sku: float(total or 0) for sku, total in filas}


def contado_por_sku(db: Session, recepcion_id: int) -> dict[str, float]:
    filas = db.execute(
        select(ScanEvent.sku, func.sum(ScanEvent.cantidad))
        .where(ScanEvent.recepcion_id == recepcion_id)
        .group_by(ScanEvent.sku)
    ).all()
    return {sku: float(total or 0) for sku, total in filas}


def contado_de_sku(db: Session, recepcion_id: int, sku: str) -> float:
    total = db.scalar(
        select(func.sum(ScanEvent.cantidad)).where(
            ScanEvent.recepcion_id == recepcion_id, ScanEvent.sku == sku
        )
    )
    return float(total or 0)


def ubicaciones_de_sku(db: Session, recepcion_id: int, sku: str) -> list[dict]:
    """Pallets donde ya se guardo este SKU, con cantidad y ultimo movimiento.

    Es la base de la sugerencia "ya guardaste este item en la caja X".
    """
    filas = db.execute(
        select(
            ScanEvent.pallet,
            func.sum(ScanEvent.cantidad),
            func.max(ScanEvent.creado_en),
            func.count(ScanEvent.id),
        )
        .where(ScanEvent.recepcion_id == recepcion_id, ScanEvent.sku == sku)
        .group_by(ScanEvent.pallet)
        .order_by(func.sum(ScanEvent.cantidad).desc())
    ).all()
    return [
        {
            "pallet": p,
            "cantidad": entero_si_aplica(float(c or 0)),
            "ultimo": u.isoformat() if u else None,
            "eventos": n,
        }
        for p, c, u, n in filas
        if float(c or 0) != 0
    ]


def estado_sku(esperado: float, contado: float) -> EstadoSku:
    if contado == 0 and esperado > 0:
        return EstadoSku.PENDIENTE if contado == 0 else EstadoSku.FALTANTE
    if contado == esperado:
        return EstadoSku.OK
    return EstadoSku.FALTANTE if contado < esperado else EstadoSku.SOBRANTE


def estado_sku_final(esperado: float, contado: float) -> EstadoSku:
    """Estado al cerrar: lo no contado ya es faltante confirmado."""
    if contado == esperado:
        return EstadoSku.OK
    return EstadoSku.FALTANTE if contado < esperado else EstadoSku.SOBRANTE


# --------------------------------------------------------------------------- #
# Lookup: que pasa cuando el operador escanea un codigo
# --------------------------------------------------------------------------- #
@dataclass
class ResultadoLookup:
    codigo_escaneado: str
    sku: str
    en_packing_list: bool
    esperado: float
    contado: float
    pendiente: float
    estado: str
    descripcion: str | None
    depot: dict
    ubicaciones: list[dict] = field(default_factory=list)
    pallet_sugerido: str | None = None
    avisos: list[str] = field(default_factory=list)
    bloqueante: bool = False

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        for k in ("esperado", "contado", "pendiente"):
            d[k] = entero_si_aplica(d[k])
        return d


def lookup(db: Session, recepcion: Recepcion, codigo: str) -> ResultadoLookup:
    sku = normalizar_sku(codigo)
    if not sku:
        raise ErrorValidacion("Codigo vacio o invalido.", "CODIGO_INVALIDO")

    res_depot = depot_svc.resolver_codigo(db, codigo)
    # Si el codigo era un EAN, Depot devuelve el SKU real.
    if res_depot.existe and res_depot.sku:
        sku = res_depot.sku

    items = db.execute(
        select(PackingItem).where(
            PackingItem.recepcion_id == recepcion.id, PackingItem.sku == sku
        ).order_by(PackingItem.linea)
    ).scalars().all()

    esperado = sum(i.cantidad for i in items)
    contado = contado_de_sku(db, recepcion.id, sku)
    ubic = ubicaciones_de_sku(db, recepcion.id, sku)

    avisos: list[str] = []
    if not items:
        avisos.append("SKU NO esta en el packing list: todo lo que registre sera SOBRANTE.")
    if res_depot.mensaje:
        avisos.append(res_depot.mensaje)
    if ubic:
        lista = ", ".join(f"{u['pallet']} ({u['cantidad']})" for u in ubic)
        avisos.append(f"Este SKU ya fue guardado en: {lista}. Use el mismo pallet si es posible.")
    if esperado and contado >= esperado:
        avisos.append(f"Ya se completo la cantidad esperada ({entero_si_aplica(esperado)}).")

    descripcion = (items[0].descripcion if items else None) or res_depot.descripcion

    return ResultadoLookup(
        codigo_escaneado=limpiar(codigo),
        sku=sku,
        en_packing_list=bool(items),
        esperado=esperado,
        contado=contado,
        pendiente=max(esperado - contado, 0),
        estado=estado_sku(esperado, contado).value,
        descripcion=descripcion,
        depot=res_depot.to_dict(),
        ubicaciones=ubic,
        pallet_sugerido=ubic[0]["pallet"] if ubic else None,
        avisos=avisos,
        bloqueante=False,
    )


# --------------------------------------------------------------------------- #
# Registro de conteo (INSERT en el libro mayor)
# --------------------------------------------------------------------------- #
def _asegurar_pallet(db: Session, recepcion_id: int, codigo: str) -> None:
    """Registra el pallet si es nuevo.

    Dos operadores pueden estrenar el mismo pallet a la vez. El alta va en un
    SAVEPOINT: si otro gano la carrera, se descarta ese insert y el conteo
    sigue intacto. El pallet es metadato, nunca debe tumbar un conteo.
    """
    existe = db.execute(
        select(Pallet.id)
        .where(Pallet.recepcion_id == recepcion_id, Pallet.codigo == codigo)
        .limit(1)
    ).scalar_one_or_none()
    if existe:
        return
    padre = pallet_padre(codigo)
    try:
        with db.begin_nested():
            db.add(
                Pallet(
                    recepcion_id=recepcion_id, codigo=codigo,
                    padre=padre, es_subpallet=bool(padre),
                )
            )
    except IntegrityError:
        pass  # otro operador lo creo primero


def registrar_scan(
    db: Session,
    recepcion: Recepcion,
    operador: Operador,
    *,
    codigo: str,
    cantidad: float,
    pallet: str,
    estado_fisico: str = "BUENO",
    ean: str | None = None,
    observacion: str | None = None,
    foto: str | None = None,
    tipo: TipoEvento = TipoEvento.CONTEO,
    idempotency_key: str | None = None,
    dispositivo: str | None = None,
    confirmar_sobrante: bool = False,
) -> dict:
    """Registra un conteo fisico. Operacion atomica e idempotente."""
    if not recepcion.abierta:
        raise ErrorValidacion(
            f"La recepcion {recepcion.codigo} esta {recepcion.estado.value}: no admite escaneos.",
            "RECEPCION_CERRADA",
        )

    sku = normalizar_sku(codigo)
    if not sku:
        raise ErrorValidacion("Codigo de producto vacio o invalido.", "CODIGO_INVALIDO")

    cant = float(cantidad)
    if cant == 0:
        raise ErrorValidacion("La cantidad no puede ser 0.", "CANTIDAD_INVALIDA")
    if cant < 0:
        raise ErrorValidacion(
            "No se admiten cantidades negativas. Corrige anulando el conteo original.", "CANTIDAD_INVALIDA"
        )

    pal = normalizar_pallet(pallet)
    if not pallet_valido(pal):
        raise ErrorValidacion(
            "Pallet invalido. Use formato alfanumerico (A1, B04) o subpallet (A1.1, B04.3).",
            "PALLET_INVALIDO",
        )

    try:
        ef = EstadoFisico(str(estado_fisico).upper())
    except ValueError:
        raise ErrorValidacion("Estado fisico debe ser BUENO o MALO.", "ESTADO_INVALIDO") from None

    if ef is EstadoFisico.MALO and not limpiar(observacion):
        raise ErrorValidacion(
            "Un item en mal estado fisico requiere observacion.", "OBSERVACION_REQUERIDA"
        )

    # Idempotencia: el mismo envio repetido no suma dos veces.
    if idempotency_key:
        previo = db.execute(
            select(ScanEvent)
            .where(ScanEvent.idempotency_key == idempotency_key)
            .limit(1)
        ).scalar_one_or_none()
        if previo:
            return _respuesta_scan(db, recepcion, previo, duplicado=True)

    esperado = sum(
        i.cantidad
        for i in db.execute(
            select(PackingItem).where(
                PackingItem.recepcion_id == recepcion.id, PackingItem.sku == sku
            )
        ).scalars()
    )
    contado = contado_de_sku(db, recepcion.id, sku)

    # Sobrante: exige confirmacion explicita del operador.
    if cant > 0 and (contado + cant) > esperado and not confirmar_sobrante:
        exceso = contado + cant - esperado
        raise ErrorValidacion(
            (
                f"SOBRANTE: el packing list declara {entero_si_aplica(esperado)} y ya hay "
                f"{entero_si_aplica(contado)}. Esta cantidad genera {entero_si_aplica(exceso)} "
                "de exceso. Confirme para registrarlo."
            ),
            "CONFIRMAR_SOBRANTE",
        )

    res_depot = depot_svc.resolver_codigo(db, sku)
    if not res_depot.existe:
        _registrar_pendiente(db, recepcion.id, sku, res_depot, ean, operador)

    _asegurar_pallet(db, recepcion.id, pal)

    evento = ScanEvent(
        recepcion_id=recepcion.id,
        sku=sku,
        ean=normalizar_ean(ean) or None,
        pallet=pal,
        cantidad=cant,
        estado_fisico=ef,
        tipo=tipo,
        observacion=limpiar(observacion)[:300] or None,
        foto=foto,
        operador_id=operador.id,
        idempotency_key=idempotency_key,
        dispositivo=limpiar(dispositivo)[:80] or None,
    )
    db.add(evento)

    if recepcion.estado is EstadoRecepcion.ABIERTA:
        recepcion.estado = EstadoRecepcion.EN_VALIDACION

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # La unica colision esperable es la misma idempotency_key enviada dos
        # veces a la vez: gana el primero y el segundo recibe ese evento.
        # Sin clave no hay nada que deduplicar: el error es real y se propaga.
        if not idempotency_key:
            raise
        previo = db.execute(
            select(ScanEvent)
            .where(ScanEvent.idempotency_key == idempotency_key)
            .limit(1)
        ).scalar_one_or_none()
        if previo is None:
            raise
        return _respuesta_scan(db, recepcion, previo, duplicado=True)

    db.refresh(evento)
    return _respuesta_scan(db, recepcion, evento)


def _registrar_pendiente(db, recepcion_id, sku, res_depot, ean, operador) -> None:
    pend = db.execute(
        select(SkuPendiente).where(
            SkuPendiente.recepcion_id == recepcion_id, SkuPendiente.sku == sku
        )
    ).scalar_one_or_none()
    if pend is None:
        db.add(
            SkuPendiente(
                recepcion_id=recepcion_id,
                sku=sku,
                descripcion=res_depot.descripcion,
                ean=normalizar_ean(ean) or None,
                estado_depot=res_depot.estado,
                candidatos=depot_svc.json_candidatos(res_depot.candidatos),
                detectado_por_id=operador.id,
            )
        )
    elif ean and not pend.ean:
        pend.ean = normalizar_ean(ean)


def _respuesta_scan(db: Session, recepcion: Recepcion, evento: ScanEvent, duplicado=False) -> dict:
    esperado = sum(
        i.cantidad
        for i in db.execute(
            select(PackingItem).where(
                PackingItem.recepcion_id == recepcion.id, PackingItem.sku == evento.sku
            )
        ).scalars()
    )
    contado = contado_de_sku(db, recepcion.id, evento.sku)
    return {
        "evento_id": evento.id,
        "duplicado": duplicado,
        "sku": evento.sku,
        "pallet": evento.pallet,
        "cantidad_registrada": entero_si_aplica(evento.cantidad),
        "esperado": entero_si_aplica(esperado),
        "contado": entero_si_aplica(contado),
        "pendiente": entero_si_aplica(max(esperado - contado, 0)),
        "estado": estado_sku(esperado, contado).value,
        "ubicaciones": ubicaciones_de_sku(db, recepcion.id, evento.sku),
        "operador": evento.operador.nombre if evento.operador else None,
        "hora": evento.creado_en.isoformat(),
    }


def anular_scan(db: Session, recepcion: Recepcion, operador: Operador, evento_id: int,
                motivo: str) -> dict:
    """Reversa un conteo con un evento compensatorio. Nunca borra el original."""
    if not recepcion.abierta:
        raise ErrorValidacion("La recepcion esta cerrada.", "RECEPCION_CERRADA")
    orig = db.get(ScanEvent, evento_id)
    if not orig or orig.recepcion_id != recepcion.id:
        raise ErrorValidacion("Evento no encontrado en esta recepcion.", "NO_ENCONTRADO")
    if orig.tipo is TipoEvento.ANULACION:
        raise ErrorValidacion("Ese evento ya es una anulacion.", "YA_ANULADO")
    ya = db.execute(
        select(ScanEvent.id).where(ScanEvent.evento_ref_id == evento_id)
    ).scalar_one_or_none()
    if ya:
        raise ErrorValidacion("Ese conteo ya fue anulado.", "YA_ANULADO")
    if not limpiar(motivo):
        raise ErrorValidacion("Debe indicar el motivo de la anulacion.", "MOTIVO_REQUERIDO")

    rev = ScanEvent(
        recepcion_id=recepcion.id, sku=orig.sku, ean=orig.ean, pallet=orig.pallet,
        cantidad=-orig.cantidad, estado_fisico=orig.estado_fisico,
        tipo=TipoEvento.ANULACION, observacion=f"ANULA #{orig.id}: {limpiar(motivo)}"[:300],
        operador_id=operador.id, evento_ref_id=orig.id,
    )
    db.add(rev)
    db.add(Auditoria(
        recepcion_id=recepcion.id, operador_id=operador.id, accion="ANULAR_SCAN",
        detalle=json.dumps({"evento": orig.id, "sku": orig.sku,
                            "cantidad": orig.cantidad, "motivo": limpiar(motivo)}),
    ))
    db.commit()
    db.refresh(rev)
    return _respuesta_scan(db, recepcion, rev)


# --------------------------------------------------------------------------- #
# Resumen de la recepcion
# --------------------------------------------------------------------------- #
def resumen_recepcion(db: Session, recepcion: Recepcion) -> dict:
    esperado = esperado_por_sku(db, recepcion.id)
    contado = contado_por_sku(db, recepcion.id)
    cerrada = not recepcion.abierta
    fn = estado_sku_final if cerrada else estado_sku

    skus = sorted(set(esperado) | set(contado))
    detalle, conteo = [], {e.value: 0 for e in EstadoSku}
    desc = {
        i.sku: i.descripcion
        for i in db.execute(
            select(PackingItem).where(PackingItem.recepcion_id == recepcion.id)
        ).scalars()
    }
    for sku in skus:
        e, c = esperado.get(sku, 0.0), contado.get(sku, 0.0)
        st = fn(e, c)
        conteo[st.value] += 1
        detalle.append({
            "sku": sku,
            "descripcion": desc.get(sku),
            "esperado": entero_si_aplica(e),
            "contado": entero_si_aplica(c),
            "diferencia": entero_si_aplica(c - e),
            "estado": st.value,
            "en_packing_list": sku in esperado,
            "ubicaciones": ubicaciones_de_sku(db, recepcion.id, sku),
        })

    total_esp, total_cont = sum(esperado.values()), sum(contado.values())
    pendientes = db.scalar(
        select(func.count()).select_from(SkuPendiente)
        .where(SkuPendiente.recepcion_id == recepcion.id)
    ) or 0
    operadores = db.scalar(
        select(func.count(func.distinct(ScanEvent.operador_id)))
        .where(ScanEvent.recepcion_id == recepcion.id)
    ) or 0
    eventos = db.scalar(
        select(func.count()).select_from(ScanEvent)
        .where(ScanEvent.recepcion_id == recepcion.id)
    ) or 0

    return {
        "recepcion": {
            "id": recepcion.id, "codigo": recepcion.codigo,
            "cliente": recepcion.cliente, "estado": recepcion.estado.value,
            "creado_en": recepcion.creado_en.isoformat(),
        },
        "totales": {
            "skus": len(skus),
            "skus_packing_list": len(esperado),
            "unidades_sistema": entero_si_aplica(total_esp),
            "unidades_fisicas": entero_si_aplica(total_cont),
            "diferencia": entero_si_aplica(total_cont - total_esp),
            "eventos": eventos,
            "operadores": operadores,
            "skus_sin_crear_en_depot": pendientes,
            "avance_pct": round(100 * min(total_cont, total_esp) / total_esp, 1) if total_esp else 0.0,
            "exactitud_pct": round(100 * conteo["OK"] / len(skus), 1) if skus else 0.0,
        },
        "por_estado": conteo,
        "detalle": detalle,
    }


def cerrar_recepcion(db: Session, recepcion: Recepcion, operador: Operador) -> dict:
    if not recepcion.abierta:
        raise ErrorValidacion("La recepcion ya esta cerrada.", "YA_CERRADA")
    resumen = resumen_recepcion(db, recepcion)
    recepcion.estado = EstadoRecepcion.CERRADA
    recepcion.cerrado_en = utcnow().replace(tzinfo=None)
    db.add(Auditoria(
        recepcion_id=recepcion.id, operador_id=operador.id, accion="CERRAR_RECEPCION",
        detalle=json.dumps(resumen["totales"]),
    ))
    db.commit()
    return resumen


def reabrir_recepcion(db: Session, recepcion: Recepcion, operador: Operador, motivo: str) -> None:
    if recepcion.abierta:
        raise ErrorValidacion("La recepcion ya esta abierta.", "YA_ABIERTA")
    if not limpiar(motivo):
        raise ErrorValidacion("Debe indicar el motivo de la reapertura.", "MOTIVO_REQUERIDO")
    recepcion.estado = EstadoRecepcion.EN_VALIDACION
    recepcion.cerrado_en = None
    db.add(Auditoria(
        recepcion_id=recepcion.id, operador_id=operador.id, accion="REABRIR_RECEPCION",
        detalle=json.dumps({"motivo": limpiar(motivo)}),
    ))
    db.commit()
