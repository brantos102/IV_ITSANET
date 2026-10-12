"""Cliente del sistema Depot con cache local y degradacion elegante.

Estrategia de resolucion de un codigo escaneado:
  1. Cache local `productos` (espejo del maestro) -> respuesta inmediata.
  2. API Depot, si esta configurada y el cache no resolvio.
  3. Busqueda difusa local -> candidatos para "validar a profundidad".

Si la API no responde la app NO se detiene: sigue operando contra el cache y
marca el resultado como degradado. La bodega no puede parar por la red.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import (
    DEPOT_BASE_URL, DEPOT_CLIENTE, DEPOT_ENABLED, DEPOT_TIMEOUT, DEPOT_TOKEN,
)
from app.models import EstadoDepot, Producto, utcnow
from app.services.normalize import normalizar_ean, normalizar_sku

log = logging.getLogger(__name__)

# Accion sugerida al operador
ACCION_OK = "OK"                        # existe -> continuar
ACCION_REVISAR = "VALIDAR_PROFUNDIDAD"  # hay parecidos -> revisar antes de crear
ACCION_CREAR = "CREAR"                  # no existe -> solicitar creacion


@dataclass
class ResultadoDepot:
    sku: str
    existe: bool
    estado: EstadoDepot
    accion: str
    descripcion: str | None = None
    ean: str | None = None
    unidad: str | None = None
    inactivo: bool = False
    fuente: str = "CACHE"          # CACHE | API | NINGUNA
    degradado: bool = False        # True si la API fallo y se uso cache
    candidatos: list[dict] = field(default_factory=list)
    mensaje: str = ""

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["estado"] = self.estado.value
        return d


class _CircuitBreaker:
    """Evita castigar cada escaneo cuando la API esta caida."""

    def __init__(self, umbral: int = 3, enfriamiento: int = 60):
        self.umbral, self.enfriamiento = umbral, enfriamiento
        self.fallos, self.abierto_hasta = 0, 0.0

    @property
    def abierto(self) -> bool:
        return time.monotonic() < self.abierto_hasta

    def exito(self) -> None:
        self.fallos, self.abierto_hasta = 0, 0.0

    def fallo(self) -> None:
        self.fallos += 1
        if self.fallos >= self.umbral:
            self.abierto_hasta = time.monotonic() + self.enfriamiento


_breaker = _CircuitBreaker()


class DepotClient:
    def __init__(self, base_url: str = DEPOT_BASE_URL, token: str = DEPOT_TOKEN):
        self.base_url, self.token = base_url.rstrip("/"), token

    @property
    def habilitado(self) -> bool:
        return bool(self.base_url) and not _breaker.abierto

    def _headers(self) -> dict:
        h = {"Accept": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def buscar_producto(self, sku: str) -> dict | None:
        """GET /productos/{sku}. Devuelve None si no existe (404)."""
        if not self.habilitado:
            return None
        url = f"{self.base_url}/productos/{sku}"
        try:
            r = httpx.get(
                url, headers=self._headers(), timeout=DEPOT_TIMEOUT,
                params={"cliente": DEPOT_CLIENTE},
            )
            _breaker.exito()
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # red caida, timeout, 5xx
            _breaker.fallo()
            log.warning("Depot no disponible (%s): %s", url, exc)
            raise DepotNoDisponible(str(exc)) from exc

    def crear_producto(self, payload: dict) -> dict:
        if not self.base_url:
            raise DepotNoDisponible("DEPOT_BASE_URL no configurada")
        r = httpx.post(
            f"{self.base_url}/productos", headers=self._headers(),
            json=payload, timeout=DEPOT_TIMEOUT * 2,
        )
        r.raise_for_status()
        return r.json()

    def subir_recepcion(self, payload: dict) -> dict:
        if not self.base_url:
            raise DepotNoDisponible("DEPOT_BASE_URL no configurada")
        r = httpx.post(
            f"{self.base_url}/recepciones", headers=self._headers(),
            json=payload, timeout=DEPOT_TIMEOUT * 5,
        )
        r.raise_for_status()
        return r.json()


class DepotNoDisponible(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# Resolucion de un codigo escaneado
# --------------------------------------------------------------------------- #
def _candidatos_locales(db: Session, sku: str, limite: int = 6) -> list[dict]:
    """SKUs parecidos: prefijo largo o coincidencia por raiz, para 'validar a fondo'."""
    if len(sku) < 5:
        return []
    raiz = sku[:7]
    filas = db.execute(
        select(Producto.sku, Producto.descripcion)
        .where(or_(Producto.sku.like(f"{raiz}%"), Producto.codigo_alternativo == sku))
        .limit(limite)
    ).all()
    return [{"sku": s, "descripcion": d} for s, d in filas if s != sku]


def resolver_codigo(db: Session, codigo: str, usar_api: bool = True) -> ResultadoDepot:
    """Resuelve un codigo escaneado (SKU o EAN) contra Depot.

    Nunca lanza excepcion por fallo de red: devuelve `degradado=True`.
    """
    sku = normalizar_sku(codigo)
    if not sku:
        return ResultadoDepot(
            sku="", existe=False, estado=EstadoDepot.NO_EXISTE, accion=ACCION_CREAR,
            fuente="NINGUNA", mensaje="Codigo vacio o invalido",
        )

    # 1. Cache local por SKU
    prod = db.get(Producto, sku)

    # 2. Cache local por EAN o codigo alternativo
    if prod is None:
        ean = normalizar_ean(codigo)
        if ean:
            prod = db.execute(
                select(Producto)
                .where(or_(Producto.ean == ean, Producto.codigo_alternativo == sku))
                .limit(1)
            ).scalar_one_or_none()

    if prod is not None:
        return ResultadoDepot(
            sku=prod.sku, existe=True, estado=EstadoDepot.EXISTE, accion=ACCION_OK,
            descripcion=prod.descripcion, ean=prod.ean, unidad=prod.unidad,
            inactivo=prod.inactivo, fuente="CACHE",
            mensaje="Producto inactivo en Depot: confirmar con supervisor"
            if prod.inactivo else "",
        )

    # 3. API Depot
    degradado = False
    if usar_api and DEPOT_ENABLED:
        cli = DepotClient()
        try:
            data = cli.buscar_producto(sku)
            if data:
                guardar_producto_api(db, sku, data)
                return ResultadoDepot(
                    sku=sku, existe=True, estado=EstadoDepot.EXISTE, accion=ACCION_OK,
                    descripcion=data.get("descripcion"), ean=data.get("codigo_barra"),
                    unidad=data.get("unidad_id"), fuente="API",
                )
        except DepotNoDisponible:
            degradado = True

    # 4. No existe -> buscar parecidos
    candidatos = _candidatos_locales(db, sku)
    estado = EstadoDepot.REVISAR if candidatos else EstadoDepot.NO_EXISTE
    accion = ACCION_REVISAR if candidatos else ACCION_CREAR
    if degradado:
        msg = "Depot no responde: verificado solo contra el maestro local."
    elif candidatos:
        msg = f"SKU no existe en Depot. Hay {len(candidatos)} codigo(s) similar(es): validar a profundidad."
    else:
        msg = "SKU no existe en Depot. Registrar codigo EAN y solicitar creacion."

    return ResultadoDepot(
        sku=sku, existe=False, estado=estado, accion=accion, fuente="CACHE",
        degradado=degradado, candidatos=candidatos, mensaje=msg,
    )


def guardar_producto_api(db: Session, sku: str, data: dict) -> Producto:
    from app.services.normalize import limpiar

    prod = db.get(Producto, sku) or Producto(sku=sku)
    prod.descripcion = limpiar(data.get("descripcion"))[:300] or prod.descripcion
    prod.ean = normalizar_ean(data.get("codigo_barra")) or prod.ean
    prod.unidad = limpiar(data.get("unidad_id"))[:20] or prod.unidad
    prod.existe_depot = True
    prod.origen = "API"
    prod.actualizado_en = utcnow().replace(tzinfo=None)
    db.merge(prod)
    db.commit()
    return prod


def estado_integracion(db: Session) -> dict:
    total = db.scalar(select(func.count()).select_from(Producto)) or 0
    return {
        "api_configurada": DEPOT_ENABLED,
        "base_url": DEPOT_BASE_URL or None,
        "circuito_abierto": _breaker.abierto,
        "fallos_consecutivos": _breaker.fallos,
        "productos_en_cache": total,
        "modo": "API + CACHE" if DEPOT_ENABLED else "SOLO CACHE LOCAL",
    }


def json_candidatos(c: list[dict]) -> str | None:
    return json.dumps(c, ensure_ascii=False) if c else None
