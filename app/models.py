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
    JSON, Boolean, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String,
    Text, UniqueConstraint,
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
    # Con que queda firmado lo que hace. La aplicacion de los operarios firma
    # cada conteo con el correo —es lo que sale en la bitacora y en el informe—
    # y las cuentas importadas de Firebase lo traen. Opcional: un operario dado
    # de alta a mano en el servidor puede no tener buzon, y entonces firma con
    # su usuario.
    email: Mapped[str | None] = mapped_column(String(160), index=True)
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
class ProductoCodigo(Base):
    """Etiquetas adicionales del mismo SKU; no reemplaza el EAN del maestro."""
    __tablename__ = 'producto_codigos'
    codigo: Mapped[str] = mapped_column(String(80), primary_key=True)
    valor: Mapped[str] = mapped_column(String(80))
    sku: Mapped[str] = mapped_column(ForeignKey('productos.sku'), index=True)
    registrado_por: Mapped[str | None] = mapped_column(String(160))
    exportar: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(FECHA, default=utcnow)


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


# --------------------------------------------------------------------------- #
# El modelo de la aplicacion de los operarios
# --------------------------------------------------------------------------- #
# Las tablas de arriba son del prototipo: una recepcion con sus lineas y su
# libro mayor, pensado desde el servidor. La aplicacion que usan los operarios
# en el handheld lleva meses en produccion con un modelo propio, y ese modelo
# sabe cosas que el otro no:
#
#   - De que packing list viene cada linea (`origen`) y cuanto declara cada uno
#     del mismo SKU. Dos listas de la misma recepcion con el mismo codigo es lo
#     normal, no la excepcion.
#   - El reparto de lo contado por pallet Y por lista, que es lo que permite
#     devolver el archivo con las mismas filas que trajo: 22 filas, 22 filas.
#   - La cabecera original de cada archivo, para reescribirlo igual.
#   - La huella de contenido de cada lista, para reconocerla si vuelve a
#     subirse en otra recepcion.
#
# Traducir eso al modelo del prototipo seria perderlo. Asi que la migracion va
# al reves: estas tablas guardan los MISMOS documentos que la aplicacion ya
# escribe, con los mismos nombres de campo, y el servidor habla su idioma. Lo
# que no se puede fijar en columnas —los mapas por pallet, por origen, las
# cabeceras— va en JSON, que es exactamente lo que son.
#
# El prefijo `app_` las separa de las del prototipo. Conviven: el prototipo
# sigue sirviendo sus pantallas y sus KPIs mientras dure la transicion.
JSON_MAPA = JSON().with_variant(mysql.JSON(), "mysql")


class AppRecepcion(Base):
    """Una recepcion, como la escribe la aplicacion de los operarios."""

    __tablename__ = "app_recepciones"

    # El codigo ES el identificador, como en Firestore: REC0260002. No un
    # autoincremental. Asi un enlace de la aplicacion vieja sigue valiendo y la
    # importacion no tiene que inventar correspondencias.
    codigo: Mapped[str] = mapped_column(String(60), primary_key=True)
    cliente: Mapped[str] = mapped_column(String(60), default="VENTURA", index=True)
    descripcion: Mapped[str | None] = mapped_column(String(300))
    bultos: Mapped[int | None] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(String(20), default="ABIERTA", index=True)
    hoja: Mapped[str | None] = mapped_column(String(120))

    creado_por: Mapped[str | None] = mapped_column(String(120))
    creado_en: Mapped[datetime] = mapped_column(FECHA, default=utcnow, index=True)
    packing_list_en: Mapped[datetime | None] = mapped_column(FECHA)
    cerrada_en: Mapped[datetime | None] = mapped_column(FECHA)
    cerrada_por: Mapped[str | None] = mapped_column(String(120))

    # totales {lineas, skus, unidades}; el resto son mapas por origen.
    totales: Mapped[dict | None] = mapped_column(JSON_MAPA)
    origenes: Mapped[list | None] = mapped_column(JSON_MAPA)
    lineas_por_origen: Mapped[dict | None] = mapped_column(JSON_MAPA)
    formatos: Mapped[dict | None] = mapped_column(JSON_MAPA)
    embarques: Mapped[list | None] = mapped_column(JSON_MAPA)


class AppLinea(Base):
    """Una linea del packing list, tal como venia en el archivo.

    `orden` conserva el sitio que ocupaba: el informe se devuelve con las mismas
    filas y en el mismo orden, y eso no se puede reconstruir ordenando por SKU.
    """

    __tablename__ = "app_lineas"
    __table_args__ = (
        UniqueConstraint("recepcion", "origen", "linea", name="uq_app_linea"),
        Index("ix_app_lineas_rec_orden", "recepcion", "orden"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recepcion: Mapped[str] = mapped_column(
        ForeignKey("app_recepciones.codigo", ondelete="CASCADE"), index=True)
    origen: Mapped[str] = mapped_column(String(40), default="PRINCIPAL")
    linea: Mapped[int] = mapped_column(Integer)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    sku: Mapped[str] = mapped_column(String(80), index=True)
    descripcion: Mapped[str | None] = mapped_column(String(300))
    cantidad: Mapped[float] = mapped_column(CANTIDAD, default=0)
    # Las columnas que no son estandar del archivo: se devuelven igual.
    extra: Mapped[dict | None] = mapped_column(JSON_MAPA)


class AppSku(Base):
    """El estado de un SKU dentro de una recepcion.

    `contado` y los mapas se derivan de los eventos: aqui estan materializados
    porque el handheld los lee en cada escaneo y recalcularlos cada vez seria
    sumar el libro mayor entero en cada codigo. La verdad sigue siendo el libro
    mayor: `recalcular_sku` los vuelve a armar desde cero.
    """

    __tablename__ = "app_skus"
    __table_args__ = (UniqueConstraint("recepcion", "sku", name="uq_app_sku"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    recepcion: Mapped[str] = mapped_column(
        ForeignKey("app_recepciones.codigo", ondelete="CASCADE"), index=True)
    sku: Mapped[str] = mapped_column(String(80), index=True)
    descripcion: Mapped[str | None] = mapped_column(String(300))
    esperado: Mapped[float] = mapped_column(CANTIDAD, default=0)
    contado: Mapped[float] = mapped_column(CANTIDAD, default=0)
    verificado: Mapped[bool] = mapped_column(Boolean, default=False)
    estado: Mapped[str] = mapped_column(String(20), default="PENDIENTE", index=True)
    en_packing_list: Mapped[bool] = mapped_column(Boolean, default=True)
    tiene_pnc: Mapped[bool] = mapped_column(Boolean, default=False)

    # Si es un adicional, por que se registro y quien lo vio. Va aqui y no en
    # una tabla aparte porque es un dato del SKU en esta recepcion, y asi no hay
    # dos sitios que puedan discrepar sobre si algo es adicional o no.
    motivo: Mapped[str | None] = mapped_column(String(300))
    detectado_por: Mapped[str | None] = mapped_column(String(120))
    ultimo_operador: Mapped[str | None] = mapped_column(String(120))

    pallets: Mapped[dict | None] = mapped_column(JSON_MAPA)            # {pallet: cantidad}
    por_origen: Mapped[dict | None] = mapped_column(JSON_MAPA)         # {origen: {pallet: cant}}
    origenes: Mapped[list | None] = mapped_column(JSON_MAPA)
    esperado_por_origen: Mapped[dict | None] = mapped_column(JSON_MAPA)
    creado_en: Mapped[datetime] = mapped_column(FECHA, default=utcnow)
    actualizado_en: Mapped[datetime] = mapped_column(FECHA, default=utcnow)


class AppEvento(Base):
    """El libro mayor: cada conteo, cada anulacion, cada no encontrado.

    El identificador lo pone el handheld y es la clave de idempotencia: si la
    red se corta despues de escribir y el operario repite el escaneo, el segundo
    intento reescribe el mismo evento en vez de contar dos veces. Es la misma
    garantia que daba el identificador del documento en Firestore.
    """

    __tablename__ = "app_eventos"
    __table_args__ = (Index("ix_app_eventos_rec_fecha", "recepcion", "creado_en"),)

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    recepcion: Mapped[str] = mapped_column(
        ForeignKey("app_recepciones.codigo", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(30), index=True)   # CONTEO|ANULACION|NO_ENCONTRADO…
    sku: Mapped[str | None] = mapped_column(String(80), index=True)
    cantidad: Mapped[float] = mapped_column(CANTIDAD, default=0)
    pallet: Mapped[str | None] = mapped_column(String(60))
    posicion: Mapped[str | None] = mapped_column(String(60))
    origen: Mapped[str | None] = mapped_column(String(40))
    usuario: Mapped[str | None] = mapped_column(String(120), index=True)
    anula_a: Mapped[str | None] = mapped_column(String(120), index=True)
    motivo: Mapped[str | None] = mapped_column(String(300))
    datos: Mapped[dict | None] = mapped_column(JSON_MAPA)       # fotos, extra, lo que venga
    creado_en: Mapped[datetime] = mapped_column(FECHA, default=utcnow, index=True)


class AppHuella(Base):
    """La huella de contenido de un packing list ya cargado.

    Sirve para avisar de que el archivo que se esta subiendo ya se cargo antes,
    aunque venga con otro nombre: la huella se calcula sobre los pares
    `sku:cantidad`, no sobre el nombre del archivo.
    """

    __tablename__ = "app_huellas"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    huella: Mapped[str] = mapped_column(String(32), index=True)
    recepcion: Mapped[str] = mapped_column(String(60), index=True)
    codigo: Mapped[str | None] = mapped_column(String(60))
    origen: Mapped[str | None] = mapped_column(String(40))
    archivo: Mapped[str | None] = mapped_column(String(300), index=True)
    lineas: Mapped[int] = mapped_column(Integer, default=0)
    skus: Mapped[int] = mapped_column(Integer, default=0)
    unidades: Mapped[float] = mapped_column(CANTIDAD, default=0)
    creado_en: Mapped[datetime] = mapped_column(FECHA, default=utcnow)


class AppArchivo(Base):
    """Fotos e informes retenidos por el servidor, con contenido inmutable."""
    __tablename__ = 'app_archivos'
    __table_args__ = (UniqueConstraint('recepcion', 'tipo', 'sha256', name='uq_app_archivo_contenido'),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    recepcion: Mapped[str] = mapped_column(ForeignKey('app_recepciones.codigo', ondelete='CASCADE'), index=True)
    tipo: Mapped[str] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(200))
    mime: Mapped[str] = mapped_column(String(80))
    drive_id: Mapped[str | None] = mapped_column(String(128))
    drive_url: Mapped[str | None] = mapped_column(String(300))
    sha256: Mapped[str] = mapped_column(String(64))
    bytes: Mapped[int] = mapped_column(Integer)
    usuario: Mapped[str | None] = mapped_column(String(120))
    creado_en: Mapped[datetime] = mapped_column(FECHA, default=utcnow)


class AppArchivoSku(Base):
    """Una imagen puede documentar varios ítems sin duplicar el archivo."""
    __tablename__ = 'app_archivo_skus'
    archivo_id: Mapped[str] = mapped_column(ForeignKey('app_archivos.id', ondelete='CASCADE'), primary_key=True)
    sku: Mapped[str] = mapped_column(String(80), primary_key=True, index=True)


class AppConfig(Base):
    """Preferencias operativas y credenciales cifradas; la clave vive fuera de MySQL."""
    __tablename__ = 'app_config'
    clave: Mapped[str] = mapped_column(String(40), primary_key=True)
    datos: Mapped[dict] = mapped_column(JSON_MAPA)
    usuario: Mapped[str | None] = mapped_column(String(120))
    modificado_en: Mapped[datetime] = mapped_column(FECHA, default=utcnow)


class AppEntrega(Base):
    """Instantanea de cierre y cola durable hacia Drive, Sheets y correo."""
    __tablename__ = 'app_entregas'
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    clave: Mapped[str] = mapped_column(String(64), unique=True)
    recepcion: Mapped[str] = mapped_column(ForeignKey('app_recepciones.codigo', ondelete='CASCADE'), index=True)
    estado: Mapped[str] = mapped_column(String(20), default='PENDIENTE', index=True)
    datos: Mapped[dict] = mapped_column(JSON_MAPA)
    resultado: Mapped[dict | None] = mapped_column(JSON_MAPA)
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(300))
    usuario: Mapped[str] = mapped_column(String(120))
    proximo_en: Mapped[datetime] = mapped_column(FECHA, default=utcnow, index=True)
    creado_en: Mapped[datetime] = mapped_column(FECHA, default=utcnow)


class AppIngreso(Base):
    __tablename__ = 'app_ingresos'
    recepcion: Mapped[str] = mapped_column(ForeignKey('app_recepciones.codigo', ondelete='CASCADE'), primary_key=True)
    datos: Mapped[dict] = mapped_column(JSON_MAPA, default=dict)
    actualizado_en: Mapped[datetime] = mapped_column(FECHA, default=utcnow)


class AppUnidadLogistica(Base):
    __tablename__ = 'app_unidades_logisticas'
    __table_args__ = (UniqueConstraint('recepcion', 'tipo', 'numero', name='uq_app_unidad_fisica'),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    recepcion: Mapped[str] = mapped_column(ForeignKey('app_recepciones.codigo', ondelete='CASCADE'), index=True)
    tipo: Mapped[str] = mapped_column(String(20))
    numero: Mapped[int] = mapped_column(Integer)
    codigo: Mapped[str] = mapped_column(String(80), default='')
    padre_id: Mapped[str | None] = mapped_column(ForeignKey('app_unidades_logisticas.id', ondelete='CASCADE'), index=True)
    datos: Mapped[dict] = mapped_column(JSON_MAPA, default=dict)


class AppEvidencia(Base):
    __tablename__ = 'app_evidencias'
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    archivo_id: Mapped[str] = mapped_column(ForeignKey('app_archivos.id', ondelete='CASCADE'), index=True)
    recepcion: Mapped[str] = mapped_column(ForeignKey('app_recepciones.codigo', ondelete='CASCADE'), index=True)
    unidad_id: Mapped[str | None] = mapped_column(ForeignKey('app_unidades_logisticas.id', ondelete='CASCADE'), index=True)
    sku: Mapped[str | None] = mapped_column(String(80), index=True)
    origen: Mapped[str | None] = mapped_column(String(40))
    categoria: Mapped[str] = mapped_column(String(20))
    tipo: Mapped[str] = mapped_column(String(40))
    protocolo: Mapped[str] = mapped_column(String(20))
    usuario: Mapped[str] = mapped_column(String(120))
    creado_en: Mapped[datetime] = mapped_column(FECHA, default=utcnow)
    eliminado_en: Mapped[datetime | None] = mapped_column(FECHA)


class AppCopiaDrive(Base):
    __tablename__ = 'app_copias_drive'
    archivo_id: Mapped[str] = mapped_column(ForeignKey('app_archivos.id', ondelete='CASCADE'), primary_key=True)
    recepcion: Mapped[str] = mapped_column(ForeignKey('app_recepciones.codigo', ondelete='CASCADE'), index=True)
    estado: Mapped[str] = mapped_column(String(20), default='PENDIENTE', index=True)
    datos: Mapped[dict] = mapped_column(JSON_MAPA)
    usuario: Mapped[str] = mapped_column(String(120))
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    proximo_en: Mapped[datetime] = mapped_column(FECHA, default=utcnow, index=True)
    error: Mapped[str | None] = mapped_column(String(160))


class AppStockDepot(Base):
    __tablename__ = 'app_stock_depot'
    sku: Mapped[str] = mapped_column(String(80), primary_key=True)
    cliente: Mapped[str] = mapped_column(String(60), primary_key=True)
    posiciones: Mapped[list] = mapped_column(JSON_MAPA, default=list)
    actualizado_en: Mapped[datetime] = mapped_column(FECHA, default=utcnow)


class AppImpresion(Base):
    __tablename__ = 'app_impresiones'
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    clave: Mapped[str] = mapped_column(String(80), unique=True)
    estacion: Mapped[str] = mapped_column(String(40), index=True)
    recepcion: Mapped[str | None] = mapped_column(ForeignKey('app_recepciones.codigo', ondelete='CASCADE'), index=True)
    usuario: Mapped[str] = mapped_column(String(120))
    estado: Mapped[str] = mapped_column(String(20), default='PENDIENTE', index=True)
    datos: Mapped[dict] = mapped_column(JSON_MAPA)
    reserva: Mapped[str | None] = mapped_column(String(64))
    reservado_en: Mapped[datetime | None] = mapped_column(FECHA)
    creado_en: Mapped[datetime] = mapped_column(FECHA, default=utcnow)
    actualizado_en: Mapped[datetime] = mapped_column(FECHA, default=utcnow)
