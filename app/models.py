"""Modelo de datos.

Principio central: el conteo fisico NO se guarda como un total mutable.
Se guarda como un libro mayor append-only (`scan_events`). Los totales
siempre se derivan con SUM(). Esto garantiza:

  * Sin "lost updates" cuando varios operadores cuentan el mismo SKU.
  * Trazabilidad completa: quien conto, cuanto, cuando, en que pallet.
  * Correcciones por evento compensatorio (nunca DELETE ni UPDATE).
  * KPIs historicos sin trabajo extra.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Cantidades y precios en DECIMAL, no en coma flotante.
#
# Un FLOAT de MySQL son cuatro bytes y unos siete digitos significativos: suma
# 300 lineas y el total ya no cuadra con el papel. En un inventario eso no es un
# detalle, es la diferencia entre cerrar una recepcion y no poder.
#
# asdecimal=False deja que Python siga trabajando con float, que es lo que
# espera el resto del codigo; lo que cambia es como se GUARDA y como suma el
# motor, que es donde estaba el riesgo.
CANTIDAD = Numeric(14, 3, asdecimal=False)
PRECIO = Numeric(14, 4, asdecimal=False)

# Fecha con milesimas en MySQL. Sin ellas, DATETIME redondea al segundo y dos
# escaneos del mismo segundo quedan empatados: el libro mayor deja de tener un
# orden y la bitacora los muestra en cualquiera.
FECHA = DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql")


# --------------------------------------------------------------------------- #
# Enumeraciones
# --------------------------------------------------------------------------- #
class Rol(str, enum.Enum):
    OPERADOR = "OPERADOR"
    SUPERVISOR = "SUPERVISOR"
    ADMIN = "ADMIN"


class EstadoRecepcion(str, enum.Enum):
    ABIERTA = "ABIERTA"
    EN_VALIDACION = "EN_VALIDACION"
    CERRADA = "CERRADA"      # ya no admite escaneos
    ENTREGADA = "ENTREGADA"  # packing list final entregado al ejecutivo


class EstadoFisico(str, enum.Enum):
    BUENO = "BUENO"
    MALO = "MALO"


class TipoEvento(str, enum.Enum):
    CONTEO = "CONTEO"        # suma normal
    AJUSTE = "AJUSTE"        # correccion manual (+/-) de supervisor
    ANULACION = "ANULACION"  # reversa exacta de un evento previo


class EstadoSku(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    OK = "OK"
    FALTANTE = "FALTANTE"
    SOBRANTE = "SOBRANTE"


class EstadoDepot(str, enum.Enum):
    EXISTE = "EXISTE"
    NO_EXISTE = "NO_EXISTE"
    REVISAR = "REVISAR"  # hay coincidencia parcial -> validar a profundidad


class EstadoCreacion(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    SOLICITADO = "SOLICITADO"
    CREADO = "CREADO"
    RECHAZADO = "RECHAZADO"


# --------------------------------------------------------------------------- #
# Usuarios
# --------------------------------------------------------------------------- #
class Operador(Base):
    __tablename__ = "operadores"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    pin_hash: Mapped[str] = mapped_column(String(200))
    rol: Mapped[Rol] = mapped_column(Enum(Rol), default=Rol.OPERADOR)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(FECHA, default=utcnow)

    @property
    def es_supervisor(self) -> bool:
        return self.rol in (Rol.SUPERVISOR, Rol.ADMIN)


class Sesion(Base):
    """Token de sesion (cookie). Simple y suficiente para red local."""

    __tablename__ = "sesiones"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    operador_id: Mapped[int] = mapped_column(ForeignKey("operadores.id"), index=True)
    creada_en: Mapped[datetime] = mapped_column(FECHA, default=utcnow)
    expira_en: Mapped[datetime] = mapped_column(FECHA)

    operador: Mapped[Operador] = relationship()


# --------------------------------------------------------------------------- #
# Catalogo (cache del maestro Depot)
# --------------------------------------------------------------------------- #
class Producto(Base):
    """Espejo local del maestro de productos de Depot.

    Permite operar sin conexion a la API y responder el lookup del escaneo
    en microsegundos. `origen` indica de donde salio el dato.
    """

    __tablename__ = "productos"

    sku: Mapped[str] = mapped_column(String(80), primary_key=True)
    cliente: Mapped[str] = mapped_column(String(60), default="VENTURA", index=True)
    descripcion: Mapped[str | None] = mapped_column(String(300))
    ean: Mapped[str | None] = mapped_column(String(60), index=True)
    unidad: Mapped[str | None] = mapped_column(String(20))
    familia: Mapped[str | None] = mapped_column(String(60))
    codigo_alternativo: Mapped[str | None] = mapped_column(String(80), index=True)
    inactivo: Mapped[bool] = mapped_column(Boolean, default=False)
    existe_depot: Mapped[bool] = mapped_column(Boolean, default=True)
    origen: Mapped[str] = mapped_column(String(20), default="MAESTRO")  # MAESTRO|API|LOCAL
    actualizado_en: Mapped[datetime] = mapped_column(FECHA, default=utcnow)


# --------------------------------------------------------------------------- #
# Recepcion / Packing list
# --------------------------------------------------------------------------- #
class Recepcion(Base):
    __tablename__ = "recepciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    cliente: Mapped[str] = mapped_column(String(60), default="VENTURA")
    descripcion: Mapped[str | None] = mapped_column(String(300))
    estado: Mapped[EstadoRecepcion] = mapped_column(
        Enum(EstadoRecepcion), default=EstadoRecepcion.ABIERTA, index=True
    )
    archivo_origen: Mapped[str | None] = mapped_column(String(300))
    hash_archivo: Mapped[str | None] = mapped_column(String(64))
    bultos_declarados: Mapped[int | None] = mapped_column(Integer)
    creado_por_id: Mapped[int | None] = mapped_column(ForeignKey("operadores.id"))
    creado_en: Mapped[datetime] = mapped_column(FECHA, default=utcnow, index=True)
    cerrado_en: Mapped[datetime | None] = mapped_column(FECHA)
    entregado_en: Mapped[datetime | None] = mapped_column(FECHA)

    items: Mapped[list["PackingItem"]] = relationship(
        back_populates="recepcion", cascade="all, delete-orphan"
    )
    creado_por: Mapped[Operador | None] = relationship()

    @property
    def abierta(self) -> bool:
        return self.estado in (EstadoRecepcion.ABIERTA, EstadoRecepcion.EN_VALIDACION)


class PackingItem(Base):
    """Linea tal cual llego en el packing list. INMUTABLE: es la version del sistema."""

    __tablename__ = "packing_items"
    __table_args__ = (
        # La lista entra en la clave porque una recepcion puede consolidar
        # VARIOS packing lists, y dos listas tienen cada una su linea 1. Sin el
        # origen, la segunda lista pisaria a la primera fila por fila.
        UniqueConstraint("recepcion_id", "origen", "linea", name="uq_item_linea"),
        Index("ix_item_rec_sku", "recepcion_id", "sku"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recepcion_id: Mapped[int] = mapped_column(ForeignKey("recepciones.id"), index=True)
    linea: Mapped[int] = mapped_column(Integer)  # orden original en el archivo
    # Nombre del packing list del que salio esta fila. El informe final se
    # genera POR LISTA: si una trajo 22 filas y otra 7, salen 22 y 7, nunca 29
    # mezcladas, porque quien recibe cada archivo espera el suyo.
    origen: Mapped[str] = mapped_column(String(40), default="PRINCIPAL", index=True)
    sku: Mapped[str] = mapped_column(String(80), index=True)
    descripcion: Mapped[str | None] = mapped_column(String(300))
    referencia_pedido: Mapped[str | None] = mapped_column(String(80))
    factura: Mapped[str | None] = mapped_column(String(80))
    cantidad: Mapped[float] = mapped_column(CANTIDAD, default=0)
    precio_unit: Mapped[float | None] = mapped_column(PRECIO)
    precio_total: Mapped[float | None] = mapped_column(PRECIO)
    num_pieza_reemplazo: Mapped[str | None] = mapped_column(String(80))
    embarque: Mapped[str | None] = mapped_column(String(80), index=True)
    extra: Mapped[str | None] = mapped_column(Text)  # JSON con columnas no estandar

    recepcion: Mapped[Recepcion] = relationship(back_populates="items")


class Pallet(Base):
    """Pallet o sub-pallet (caja interna) de la recepcion. Formato A1 / A1.1"""

    __tablename__ = "pallets"
    __table_args__ = (UniqueConstraint("recepcion_id", "codigo", name="uq_pallet_codigo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    recepcion_id: Mapped[int] = mapped_column(ForeignKey("recepciones.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(40))
    padre: Mapped[str | None] = mapped_column(String(40))  # A1.1 -> padre A1
    es_subpallet: Mapped[bool] = mapped_column(Boolean, default=False)
    creado_en: Mapped[datetime] = mapped_column(FECHA, default=utcnow)


class ScanEvent(Base):
    """LIBRO MAYOR APPEND-ONLY. Nunca se actualiza ni se borra.

    Una correccion se registra como un evento nuevo con cantidad negativa
    (tipo ANULACION/AJUSTE) apuntando al evento original.
    """

    __tablename__ = "scan_events"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_scan_idem"),
        Index("ix_scan_rec_sku", "recepcion_id", "sku"),
        Index("ix_scan_rec_fecha", "recepcion_id", "creado_en"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recepcion_id: Mapped[int] = mapped_column(ForeignKey("recepciones.id"), index=True)
    sku: Mapped[str] = mapped_column(String(80), index=True)
    ean: Mapped[str | None] = mapped_column(String(60))
    pallet: Mapped[str] = mapped_column(String(40), index=True)
    # Donde quedo fisicamente en bodega (A-01-03-2). Es distinto del pallet: de
    # 30 unidades pueden ir 12 a una posicion real y 18 quedarse en un pallet
    # por ubicar, y el archivo que se carga a Depot necesita las dos cosas.
    posicion_real: Mapped[str | None] = mapped_column(String(60), index=True)
    # Contra que packing list se conto, cuando la recepcion consolida varios.
    origen: Mapped[str | None] = mapped_column(String(40), index=True)
    cantidad: Mapped[float] = mapped_column(CANTIDAD)  # puede ser negativa (correccion)
    estado_fisico: Mapped[EstadoFisico] = mapped_column(
        Enum(EstadoFisico), default=EstadoFisico.BUENO
    )
    tipo: Mapped[TipoEvento] = mapped_column(Enum(TipoEvento), default=TipoEvento.CONTEO)
    observacion: Mapped[str | None] = mapped_column(String(300))
    foto: Mapped[str | None] = mapped_column(String(300))
    # Un producto no conforme suele llevar varias fotos. JSON, porque una sola
    # columna de texto obligaria a inventar un separador que algun nombre de
    # archivo acabaria conteniendo.
    fotos: Mapped[str | None] = mapped_column(Text)
    operador_id: Mapped[int] = mapped_column(ForeignKey("operadores.id"), index=True)
    evento_ref_id: Mapped[int | None] = mapped_column(ForeignKey("scan_events.id"))
    idempotency_key: Mapped[str | None] = mapped_column(String(80))
    dispositivo: Mapped[str | None] = mapped_column(String(80))
    creado_en: Mapped[datetime] = mapped_column(FECHA, default=utcnow, index=True)

    operador: Mapped[Operador] = relationship()


class SkuPendiente(Base):
    """SKU escaneado que no existe en Depot: hay que validarlo o crearlo."""

    __tablename__ = "skus_pendientes"
    __table_args__ = (UniqueConstraint("recepcion_id", "sku", name="uq_pend_rec_sku"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    recepcion_id: Mapped[int] = mapped_column(ForeignKey("recepciones.id"), index=True)
    sku: Mapped[str] = mapped_column(String(80), index=True)
    descripcion: Mapped[str | None] = mapped_column(String(300))
    ean: Mapped[str | None] = mapped_column(String(60))
    estado_depot: Mapped[EstadoDepot] = mapped_column(
        Enum(EstadoDepot), default=EstadoDepot.NO_EXISTE
    )
    estado: Mapped[EstadoCreacion] = mapped_column(
        Enum(EstadoCreacion), default=EstadoCreacion.PENDIENTE
    )
    candidatos: Mapped[str | None] = mapped_column(Text)  # JSON de coincidencias parciales
    notas: Mapped[str | None] = mapped_column(String(300))
    detectado_por_id: Mapped[int | None] = mapped_column(ForeignKey("operadores.id"))
    creado_en: Mapped[datetime] = mapped_column(FECHA, default=utcnow)
    resuelto_en: Mapped[datetime | None] = mapped_column(FECHA)


class Auditoria(Base):
    """Bitacora de acciones sensibles (cierre, ajuste, reapertura, export)."""

    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    recepcion_id: Mapped[int | None] = mapped_column(ForeignKey("recepciones.id"), index=True)
    operador_id: Mapped[int | None] = mapped_column(ForeignKey("operadores.id"))
    accion: Mapped[str] = mapped_column(String(60), index=True)
    detalle: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(FECHA, default=utcnow, index=True)
