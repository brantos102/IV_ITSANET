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
    DEPOT_BASE_URL, DEPOT_CABECERA_TOKEN, DEPOT_CLAVE, DEPOT_CLIENTE,
    DEPOT_ENABLED, DEPOT_RUTA_STOCK, DEPOT_RUTA_TOKEN, DEPOT_TIMEOUT,
    DEPOT_CACHE_TTL, DEPOT_TTL_HORAS, DEPOT_USUARIO,
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


# --------------------------------------------------------------------------- #
# La API real del WMS
# --------------------------------------------------------------------------- #
class DepotNoDisponible(RuntimeError):
    pass


class DepotRechazado(RuntimeError):
    """Las credenciales no valen. No es un problema de red: no se reintenta."""


class DepotAPI:
    """Cliente de la API de Depot, tal como la habla el WMS en produccion.

    Dos llamadas y un token:

        GET /gettoken   cabeceras usuario / clave / cliente  -> token
        GET /getstock   cabecera  token                      -> filas de stock

    El token vence, y el WMS puede revocarlo antes de su vencimiento, asi que
    un 401 o un 403 no es un fallo: es «pide otro». Se reintenta UNA vez. Si el
    segundo tambien lo rechaza, entonces si son las credenciales.

    No hay endpoint por SKU: /getstock devuelve el inventario entero. Por eso
    aqui se descarga completo y se guarda en el espejo local, y el escaneo
    resuelve contra el espejo. Un handheld no puede esperar a que baje el
    inventario de un cliente en cada codigo.

    `transporte` existe para las pruebas: con un httpx.MockTransport se puede
    comprobar el reintento y el formato de la respuesta sin tocar el WMS.
    """

    def __init__(self, base_url: str | None = None, usuario: str | None = None,
                 clave: str | None = None, cliente: str | None = None,
                 transporte=None):
        self.base_url = (base_url if base_url is not None else DEPOT_BASE_URL).rstrip("/")
        self.usuario = DEPOT_USUARIO if usuario is None else usuario
        self.clave = DEPOT_CLAVE if clave is None else clave
        self.cliente = DEPOT_CLIENTE if cliente is None else cliente
        self.transporte = transporte
        self._token: str | None = None
        self._vence: float = 0.0

    # -- token -------------------------------------------------------------- #
    @property
    def configurada(self) -> bool:
        return bool(self.base_url and self.usuario and self.clave)

    def _cliente_http(self) -> httpx.Client:
        return httpx.Client(timeout=DEPOT_TIMEOUT, transport=self.transporte)

    def token(self, forzar: bool = False) -> str:
        if not forzar and self._token and time.monotonic() < self._vence:
            return self._token
        if not self.base_url:
            raise DepotNoDisponible("DEPOT_BASE_URL no configurada")

        cab = {"Accept": "application/json, text/plain, */*"}
        if self.usuario:
            cab["usuario"] = self.usuario
        if self.clave:
            cab["clave"] = self.clave
        if self.cliente:
            cab["cliente"] = self.cliente

        try:
            with self._cliente_http() as http:
                r = http.get(self.base_url + DEPOT_RUTA_TOKEN, headers=cab)
        except httpx.HTTPError as exc:
            _breaker.fallo()
            raise DepotNoDisponible(f"no se pudo pedir el token: {exc}") from exc

        if r.status_code in (401, 403):
            raise DepotRechazado("Depot rechazo las credenciales al pedir el token")
        if r.status_code != 200:
            _breaker.fallo()
            raise DepotNoDisponible(f"Depot respondio {r.status_code} en {DEPOT_RUTA_TOKEN}")

        token = extraer_token(r.text)
        if not token:
            raise DepotNoDisponible(
                f"Depot respondio sin un token reconocible en {DEPOT_RUTA_TOKEN}: "
                f"{r.text[:120]}"
            )
        self._token = token
        self._vence = time.monotonic() + DEPOT_TTL_HORAS * 3600
        return token

    def invalidar(self) -> None:
        self._token, self._vence = None, 0.0

    # -- llamadas ----------------------------------------------------------- #
    def pedir(self, ruta: str, _reintento: bool = False):
        """GET con el token puesto. Devuelve el JSON, o None si no hay nada."""
        cab = {
            "Accept": "application/json, text/plain, */*",
            DEPOT_CABECERA_TOKEN: self.token(),
        }
        try:
            with self._cliente_http() as http:
                r = http.get(self.base_url + ruta, headers=cab)
        except httpx.HTTPError as exc:
            _breaker.fallo()
            raise DepotNoDisponible(f"{ruta}: {exc}") from exc

        if r.status_code in (401, 403) and not _reintento:
            # Puede haber revocado el token antes de su vencimiento.
            self.invalidar()
            self.token(forzar=True)
            return self.pedir(ruta, _reintento=True)
        if r.status_code in (401, 403):
            raise DepotRechazado(f"Depot rechazo el token en {ruta}")
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            _breaker.fallo()
            raise DepotNoDisponible(f"Depot respondio {r.status_code} en {ruta}")

        _breaker.exito()
        if not r.text.strip():
            return None
        try:
            return r.json()
        except ValueError as exc:
            raise DepotNoDisponible(
                f"Depot respondio algo que no es JSON en {ruta}: {r.text[:120]}"
            ) from exc

    def stock(self, ruta: str | None = None) -> list[dict]:
        """El inventario, ya traducido. Las filas que no se entienden se saltan."""
        cuerpo = self.pedir(ruta or DEPOT_RUTA_STOCK)
        return [m for m in (mapear_stock(f) for f in filas_de(cuerpo)) if m]


def extraer_token(texto: str) -> str | None:
    """Lee el token de la respuesta de /gettoken.

    Los nombres son los que usa el WMS en produccion (token, Token, Result,
    result) y se aceptan ademas texto plano y una cadena entrecomillada, que no
    cuestan nada y evitan una sorpresa en otro despliegue. Es la misma lectura
    que hace el proxy de Apps Script: si uno de los dos entiende la respuesta,
    el otro tambien.
    """
    t = (texto or "").strip()
    if not t:
        return None
    if t[0] in "{[":
        try:
            j = json.loads(t)
        except ValueError:
            return None
        d = j[0] if isinstance(j, list) and j else j
        if not isinstance(d, dict):
            return None
        v = None
        for clave in ("token", "Token", "TOKEN", "Result", "result", "access_token"):
            if d.get(clave):
                v = d[clave]
                break
        if isinstance(v, dict):                     # Result anidado
            v = v.get("token") or v.get("Token")
        return str(v).strip() if v else None
    return t.strip('"') or None


def filas_de(cuerpo) -> list[dict]:
    """Saca la lista de filas: array suelto, o dentro de Result, result, data…"""
    if isinstance(cuerpo, list):
        return [f for f in cuerpo if isinstance(f, dict)]
    if not isinstance(cuerpo, dict):
        return []
    for clave in ("Result", "result", "data", "Data", "stock", "items", "Table", "rows"):
        if isinstance(cuerpo.get(clave), list):
            return [f for f in cuerpo[clave] if isinstance(f, dict)]
    return [cuerpo]


def _texto(v) -> str:
    """Limpia una celda del WMS: espacios invisibles incluidos."""
    s = str("" if v is None else v)
    for raro in ("​", "﻿", " "):
        s = s.replace(raro, " ")
    return " ".join(s.split())


def mapear_stock(fila: dict) -> dict | None:
    """Traduce una fila de /getstock.

    Los nombres de campo son los reales del WMS —en mayusculas, con espacios y
    puntos: «COD. PRODUCTO», «NRO. LOTE»— y son los mismos que lee el proxy.

    OJO: la respuesta NO trae codigo de barras. La validacion por EAN no puede
    salir de aqui.
    """
    if not isinstance(fila, dict):
        return None
    sku = (fila.get("COD. PRODUCTO") or fila.get("COD.PRODUCTO")
           or fila.get("codigo_producto") or fila.get("CodProducto")
           or fila.get("codigo") or fila.get("sku"))
    sku = normalizar_sku(_texto(sku))
    if not sku:
        return None

    posicion = "-".join(
        p for p in (_texto(fila.get(c)) for c in ("NAVE", "CALLE", "COLUMNA", "NIVEL")) if p
    )
    try:
        cantidad = float(_texto(fila.get("CANTIDAD") or fila.get("cantidad") or 0) or 0)
    except ValueError:
        cantidad = 0.0

    return {
        "sku": sku,
        "descripcion": _texto(fila.get("DESCRIPCION") or fila.get("descripcion")) or None,
        "unidad": _texto(fila.get("UNIDAD") or fila.get("unidad")) or None,
        "familia": _texto(fila.get("FAMILIA")) or None,
        "cliente": _texto(fila.get("COD. CLIENTE")).upper() or None,
        "stock": cantidad,
        "posicion": posicion or None,
        "lote": _texto(fila.get("NRO. LOTE")) or None,
        "serie": _texto(fila.get("NRO. SERIE")) or None,
        "partida": _texto(fila.get("NRO. PARTIDA")) or None,
        "estado_mercaderia": _texto(fila.get("EST. MERC.")) or None,
        "ean": None,            # /getstock no lo devuelve
    }


# --------------------------------------------------------------------------- #
# Del WMS al espejo local
# --------------------------------------------------------------------------- #
def sincronizar_maestro(db: Session, api: DepotAPI | None = None,
                        cliente: str | None = None) -> dict:
    """Baja el stock de Depot y actualiza el espejo local de productos.

    Devuelve el recuento por cliente, que es lo que hay que leer antes de dar
    por buena una sincronizacion: con una sola credencial el WMS puede devolver
    varios clientes, y si aparece uno que no se esperaba —o falta el que si— es
    que la credencial no es la que se creia.

    Una fila de stock es una posicion, no un producto: el mismo SKU viene
    repetido en varias ubicaciones. Aqui se consolida por SKU, que es lo que
    necesita el escaneo.
    """
    api = api or DepotAPI()
    if not api.configurada:
        raise DepotNoDisponible(
            "Faltan las credenciales de Depot: DEPOT_USUARIO y DEPOT_CLAVE. "
            "Van en /etc/iv-itsanet.env, no en el codigo."
        )

    filas = api.stock()
    por_sku: dict[str, dict] = {}
    por_cliente: dict[str, int] = {}
    for f in filas:
        if cliente and (f["cliente"] or "") != cliente.upper():
            continue
        c = f["cliente"] or DEPOT_CLIENTE or "SIN CLIENTE"
        anterior = por_sku.get(f["sku"])
        if anterior is None:
            por_cliente[c] = por_cliente.get(c, 0) + 1
            por_sku[f["sku"]] = f
        else:
            # Misma pieza en otra ubicacion: se suma el stock y se conserva la
            # primera descripcion, que es la del maestro.
            anterior["stock"] += f["stock"]
            anterior["descripcion"] = anterior["descripcion"] or f["descripcion"]

    ahora = utcnow().replace(tzinfo=None)
    registros = [{
        "sku": f["sku"],
        "cliente": (f["cliente"] or DEPOT_CLIENTE or "")[:60],
        "descripcion": (f["descripcion"] or "")[:300] or None,
        "unidad": (f["unidad"] or "")[:20] or None,
        "familia": (f["familia"] or "")[:60] or None,
        "existe_depot": True,
        "origen": "API",
        "actualizado_en": ahora,
    } for f in por_sku.values()]

    from app.routers.catalogo import _upsert     # la misma carga por lotes del maestro

    for i in range(0, len(registros), 2000):
        _upsert(db, registros[i:i + 2000])
    db.commit()

    return {
        "filas_recibidas": len(filas),
        "productos": len(registros),
        "por_cliente": dict(sorted(por_cliente.items())),
        "sincronizado_en": ahora.isoformat(timespec="seconds"),
    }


def clientes_en_espejo(db: Session) -> list[dict]:
    """Los clientes que hay en el espejo local, con cuantos productos cada uno.

    Es la respuesta a «de que clientes tenemos data»: no se adivina, se cuenta
    lo que el WMS devolvio con las credenciales que hay puestas.
    """
    filas = db.execute(
        select(Producto.cliente, func.count(), func.max(Producto.actualizado_en))
        .group_by(Producto.cliente)
        .order_by(func.count().desc())
    ).all()
    return [
        {"cliente": c or "SIN CLIENTE", "productos": n,
         "actualizado_en": a.isoformat(timespec="seconds") if a else None}
        for c, n, a in filas
    ]



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
    # 3. El WMS, si hay credenciales y el espejo esta vacio o viejo.
    #
    # /getstock no tiene busqueda por SKU: devuelve el inventario entero. Pedir
    # eso en cada codigo que no esta en el espejo dejaria el handheld colgado,
    # asi que solo se baja cuando el espejo no sirve —esta vacio o lleva mas de
    # DEPOT_CACHE_TTL sin actualizarse— y despues se vuelve a mirar en el.
    degradado = False
    if usar_api and DEPOT_ENABLED and not _breaker.abierto and espejo_caducado(db):
        try:
            sincronizar_maestro(db)
            prod = db.get(Producto, sku)
            if prod is not None:
                return ResultadoDepot(
                    sku=prod.sku, existe=True, estado=EstadoDepot.EXISTE,
                    accion=ACCION_OK, descripcion=prod.descripcion, ean=prod.ean,
                    unidad=prod.unidad, inactivo=prod.inactivo, fuente="API",
                )
        except (DepotNoDisponible, DepotRechazado) as exc:
            log.warning("Depot no disponible: %s", exc)
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
    ultima = db.scalar(select(func.max(Producto.actualizado_en)))
    return {
        "api_configurada": DEPOT_ENABLED,
        "base_url": DEPOT_BASE_URL or None,
        "usuario": DEPOT_USUARIO or None,       # el usuario si; la clave nunca
        "clave_puesta": bool(DEPOT_CLAVE),
        "cliente": DEPOT_CLIENTE or None,
        "ruta_token": DEPOT_RUTA_TOKEN,
        "ruta_stock": DEPOT_RUTA_STOCK,
        "cabecera_token": DEPOT_CABECERA_TOKEN,
        "circuito_abierto": _breaker.abierto,
        "fallos_consecutivos": _breaker.fallos,
        "productos_en_cache": total,
        "actualizado_en": ultima.isoformat(timespec="seconds") if ultima else None,
        "espejo_caducado": espejo_caducado(db),
        "clientes": clientes_en_espejo(db),
        "modo": "API + ESPEJO" if DEPOT_ENABLED else "SOLO ESPEJO LOCAL",
        "falta": [] if DEPOT_ENABLED else [
            c for c, v in (("DEPOT_BASE_URL", DEPOT_BASE_URL),
                           ("DEPOT_USUARIO", DEPOT_USUARIO),
                           ("DEPOT_CLAVE", DEPOT_CLAVE)) if not v
        ],
    }


def espejo_caducado(db: Session) -> bool:
    """Si el espejo local esta vacio o lleva demasiado sin actualizarse."""
    ultima = db.scalar(select(func.max(Producto.actualizado_en)))
    if ultima is None:
        return True
    edad = (utcnow().replace(tzinfo=None) - ultima).total_seconds()
    return edad > DEPOT_CACHE_TTL


def json_candidatos(c: list[dict]) -> str | None:
    return json.dumps(c, ensure_ascii=False) if c else None
