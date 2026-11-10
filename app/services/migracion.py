"""Traer a la base local lo que hay en Firestore.

La aplicación en la nube se montó sobre Firebase porque no había servidor. Ahora
lo hay, y lo que se cuenta tiene que acabar en MySQL. Lo que se mueve es el
histórico de validaciones: recepciones, sus líneas, el libro mayor de conteos y
la auditoría.

Dos cosas que NO se traen, a propósito:

  * **El catálogo de productos.** Es una copia del maestro de Depot, se vuelve a
    descargar en un minuto y traerlo solo sirve para arrastrar datos viejos.
  * **Las contraseñas.** Firebase guarda hashes que no se pueden exportar desde
    el navegador, y aunque se pudiera, el formato no es el de aquí. Los
    operarios se importan para que sus conteos sigan teniendo autor, pero
    desactivados y sin PIN: hay que dárselo con scripts/crear_operador.py.

La importación es **repetible**. La clave de idempotencia de cada conteo es la
misma que tenía en Firestore, así que volver a correrla no duplica nada: ni
conteos, ni líneas, ni recepciones. Si se corta a mitad, se vuelve a lanzar.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Auditoria, EstadoCreacion, EstadoDepot, EstadoFisico, EstadoRecepcion,
    Operador, PackingItem, Recepcion, Rol, ScanEvent, SkuPendiente, TipoEvento,
)

# No es el hash de ningún PIN: no tiene el formato que verify_pin sabe leer, así
# que esa función devuelve False para cualquier cosa que se pruebe contra él.
#
# Guardar aquí el hash de un PIN conocido —aunque fuera una palabra cualquiera—
# sería dejar una credencial utilizable que nadie pidió. Y uno aleatorio sería
# una credencial que existe y que nadie conoce, que tampoco sirve de nada.
HASH_SIN_PIN = "sin-pin-importado"


def _fecha(valor) -> datetime | None:
    """Una fecha de Firestore, en lo que entiende la base.

    Vienen como texto ISO desde el exportador del navegador. Las que traen zona
    se pasan a UTC y se les quita: la columna es DATETIME y guardar una hora con
    zona en una sin ella es pedir que se desplace sola más adelante.
    """
    if not valor:
        return None
    if isinstance(valor, datetime):
        d = valor
    else:
        try:
            d = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        except ValueError:
            return None
    return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d


def _num(valor, por_defecto=0.0) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return por_defecto


def _recortar(texto, largo: int) -> str | None:
    """Recorta a lo que cabe en la columna.

    Con sql_mode estricto, MySQL rechaza la fila entera si algo no cabe. En una
    migración eso significa perder un conteo por una observación larga, que es
    mucho peor que perder el final de la observación.
    """
    if texto in (None, ""):
        return None
    t = str(texto)
    return t[:largo]


# --------------------------------------------------------------------------- #
# Correspondencias entre los dos vocabularios
# --------------------------------------------------------------------------- #
ESTADO_RECEPCION = {
    "ABIERTA": EstadoRecepcion.ABIERTA,
    "EN_VALIDACION": EstadoRecepcion.EN_VALIDACION,
    "CERRADA": EstadoRecepcion.CERRADA,
}

# «PNC» (producto no conforme) es como lo llama el operario en la aplicación de
# la nube; aquí la columna solo distingue bueno de malo. Se guarda como MALO y
# la observación del conteo conserva el detalle.
ESTADO_FISICO = {"BUENO": EstadoFisico.BUENO, "PNC": EstadoFisico.MALO,
                 "MALO": EstadoFisico.MALO}

# «CERO» es el «no apareció»: un conteo de 0 unidades, no otra clase de evento.
TIPO_EVENTO = {"CONTEO": TipoEvento.CONTEO, "CERO": TipoEvento.CONTEO,
               "AJUSTE": TipoEvento.AJUSTE, "ANULACION": TipoEvento.ANULACION}

ROL = {"OPERADOR": Rol.OPERADOR, "SUPERVISOR": Rol.SUPERVISOR, "ADMIN": Rol.ADMIN}


class Resumen:
    """Lo que entró, lo que ya estaba y lo que no se pudo."""

    def __init__(self) -> None:
        self.creado: dict[str, int] = {}
        self.repetido: dict[str, int] = {}
        self.avisos: list[str] = []
        self.sin_pin: list[str] = []

    def nuevo(self, que: str) -> None:
        self.creado[que] = self.creado.get(que, 0) + 1

    def ya_estaba(self, que: str) -> None:
        self.repetido[que] = self.repetido.get(que, 0) + 1

    def aviso(self, texto: str) -> None:
        if texto not in self.avisos:
            self.avisos.append(texto)

    def __str__(self) -> str:
        filas = [f"  {k}: {v}" + (f" ({self.repetido.get(k)} ya estaban)"
                                  if self.repetido.get(k) else "")
                 for k, v in sorted(self.creado.items())]
        for k, v in sorted(self.repetido.items()):
            if k not in self.creado:
                filas.append(f"  {k}: 0 ({v} ya estaban)")
        return "\n".join(filas) or "  nada que traer"


# --------------------------------------------------------------------------- #
# Operarios
# --------------------------------------------------------------------------- #
def _nombre_de_usuario(u: dict) -> str:
    """El nombre con el que entrará aquí.

    En la nube se entra con un alias o con el correo; aquí el usuario es corto.
    Se usa el alias si lo hay, y si no la parte del correo antes de la arroba.
    """
    alias = (u.get("usuario") or "").strip()
    if alias:
        return alias[:50]
    return (u.get("email") or "").split("@")[0][:50] or "sin-usuario"


def importar_operadores(db: Session, usuarios: list[dict], resumen: Resumen) -> dict[str, Operador]:
    """Devuelve el mapa correo -> operador, que es como vienen firmados los conteos."""
    por_correo: dict[str, Operador] = {}

    for u in usuarios or []:
        correo = (u.get("email") or "").strip().lower()
        if not correo:
            continue

        usuario = _nombre_de_usuario(u)
        existente = db.scalar(select(Operador).where(Operador.usuario == usuario))
        if existente:
            por_correo[correo] = existente
            resumen.ya_estaba("operadores")
            continue

        op = Operador(
            usuario=usuario,
            nombre=_recortar(u.get("nombre") or correo, 120),
            pin_hash=HASH_SIN_PIN,
            rol=ROL.get((u.get("rol") or "").upper(), Rol.OPERADOR),
            # Desactivado a propósito: no tiene PIN utilizable. Sus conteos sí
            # quedan firmados con su nombre, que es para lo que se importa.
            activo=False,
            creado_en=_fecha(u.get("creadoEn")) or datetime.now(timezone.utc),
        )
        db.add(op)
        db.flush()
        por_correo[correo] = op
        resumen.nuevo("operadores")
        resumen.sin_pin.append(usuario)

    return por_correo


# --------------------------------------------------------------------------- #
# Recepciones
# --------------------------------------------------------------------------- #
def _operador_de(correo, por_correo, db, resumen) -> Operador | None:
    """Quién hizo esto. Si no está en el export, se crea un marcador.

    Un conteo sin autor no sirve para reclamar nada, y perder el conteo entero
    por eso sería peor. Queda registrado en los avisos.
    """
    correo = (correo or "").strip().lower()
    if not correo:
        return None
    if correo in por_correo:
        return por_correo[correo]

    usuario = correo.split("@")[0][:50] or "desconocido"
    op = db.scalar(select(Operador).where(Operador.usuario == usuario))
    if not op:
        op = Operador(usuario=usuario, nombre=correo[:120], pin_hash=HASH_SIN_PIN,
                      rol=Rol.OPERADOR, activo=False)
        db.add(op)
        db.flush()
        resumen.nuevo("operadores")
        resumen.sin_pin.append(usuario)
        resumen.aviso(f"«{correo}» firmaba conteos pero no estaba en la lista de "
                      "usuarios; se creó para no dejar esos conteos sin autor.")
    por_correo[correo] = op
    return op


def importar_recepcion(db: Session, r: dict, por_correo: dict, resumen: Resumen) -> None:
    codigo = (r.get("codigo") or r.get("id") or "").strip()
    if not codigo:
        resumen.aviso("Una recepción venía sin código y se omitió.")
        return

    rec = db.scalar(select(Recepcion).where(Recepcion.codigo == codigo))
    if rec:
        resumen.ya_estaba("recepciones")
    else:
        rec = Recepcion(
            codigo=codigo[:80],
            cliente=_recortar(r.get("cliente") or "VENTURA", 60),
            descripcion=_recortar(r.get("descripcion"), 300),
            estado=ESTADO_RECEPCION.get((r.get("estado") or "").upper(),
                                        EstadoRecepcion.ABIERTA),
            archivo_origen=_recortar(", ".join(r.get("origenes") or []), 300),
            bultos_declarados=int(_num(r.get("bultos"), 0)) or None,
            creado_por_id=(_operador_de(r.get("creadoPorEmail"), por_correo, db,
                                        resumen) or Operador(id=None)).id,
            creado_en=_fecha(r.get("creadoEn")) or datetime.now(timezone.utc),
            cerrado_en=_fecha(r.get("cerradoEn")),
        )
        db.add(rec)
        db.flush()
        resumen.nuevo("recepciones")

    _importar_lineas(db, rec, r.get("lineas") or [], resumen)
    _importar_eventos(db, rec, r.get("eventos") or [], por_correo, resumen)
    _importar_adicionales(db, rec, r.get("adicionales") or [], por_correo, resumen)
    _importar_auditoria(db, rec, r.get("auditoria") or [], por_correo, resumen)


def _importar_lineas(db: Session, rec: Recepcion, lineas: list[dict], resumen: Resumen) -> None:
    ya = {
        (i.origen, i.linea)
        for i in db.scalars(select(PackingItem).where(PackingItem.recepcion_id == rec.id))
    }
    for l in lineas:
        origen = (l.get("origen") or "PRINCIPAL")[:40]
        numero = int(_num(l.get("linea"), 0))
        if (origen, numero) in ya:
            resumen.ya_estaba("líneas")
            continue

        extra = l.get("cruda")
        db.add(PackingItem(
            recepcion_id=rec.id,
            linea=numero,
            origen=origen,
            sku=_recortar(l.get("sku"), 80) or "",
            descripcion=_recortar(l.get("descripcion"), 300),
            cantidad=_num(l.get("cantidad")),
            embarque=_recortar(l.get("embarque"), 80),
            # La fila original entera, por si el formato del cliente trae
            # columnas que aquí no tienen sitio: el informe final tiene que
            # devolver el archivo igual que llegó.
            extra=json.dumps(extra, ensure_ascii=False) if extra else None,
        ))
        ya.add((origen, numero))
        resumen.nuevo("líneas")


def _importar_eventos(db: Session, rec: Recepcion, eventos: list[dict],
                      por_correo: dict, resumen: Resumen) -> None:
    # La clave de idempotencia es la misma que en Firestore, así que volver a
    # importar no duplica ni un conteo.
    ya = set(db.scalars(
        select(ScanEvent.idempotency_key).where(ScanEvent.recepcion_id == rec.id)
    ))
    for e in eventos:
        clave = (e.get("id") or "")[:80]
        if not clave or clave in ya:
            resumen.ya_estaba("conteos")
            continue

        operador = _operador_de(e.get("operadorEmail"), por_correo, db, resumen)
        if operador is None:
            resumen.aviso("Había conteos sin correo de operario; se omitieron "
                          "porque la columna de autor no admite vacío.")
            continue

        fotos = e.get("fotos") or []
        db.add(ScanEvent(
            recepcion_id=rec.id,
            sku=_recortar(e.get("sku"), 80) or "",
            pallet=_recortar(e.get("pallet"), 40) or "",
            posicion_real=_recortar(e.get("posicionReal"), 60),
            origen=_recortar(e.get("origen"), 40),
            cantidad=_num(e.get("cantidad")),
            estado_fisico=ESTADO_FISICO.get((e.get("estadoFisico") or "").upper(),
                                            EstadoFisico.BUENO),
            tipo=TIPO_EVENTO.get((e.get("tipo") or "").upper(), TipoEvento.CONTEO),
            observacion=_recortar(e.get("observacion"), 300),
            foto=_recortar(fotos[0] if fotos else None, 300),
            fotos=json.dumps(fotos, ensure_ascii=False) if fotos else None,
            operador_id=operador.id,
            idempotency_key=clave,
            creado_en=_fecha(e.get("creadoEn")) or datetime.now(timezone.utc),
        ))
        ya.add(clave)
        resumen.nuevo("conteos")


def _importar_adicionales(db: Session, rec: Recepcion, adicionales: list[dict],
                          por_correo: dict, resumen: Resumen) -> None:
    ya = set(db.scalars(
        select(SkuPendiente.sku).where(SkuPendiente.recepcion_id == rec.id)
    ))
    for a in adicionales:
        sku = _recortar(a.get("sku"), 80)
        if not sku or sku in ya:
            resumen.ya_estaba("adicionales")
            continue
        db.add(SkuPendiente(
            recepcion_id=rec.id,
            sku=sku,
            descripcion=_recortar(a.get("descripcion"), 300),
            estado_depot=EstadoDepot.NO_EXISTE,
            estado=EstadoCreacion.PENDIENTE,
            notas=_recortar(a.get("motivo") or a.get("observacion"), 300),
            detectado_por_id=(_operador_de(a.get("detectadoPorEmail"), por_correo,
                                           db, resumen) or Operador(id=None)).id,
            creado_en=_fecha(a.get("creadoEn")) or datetime.now(timezone.utc),
        ))
        ya.add(sku)
        resumen.nuevo("adicionales")


def _importar_auditoria(db: Session, rec: Recepcion, registros: list[dict],
                        por_correo: dict, resumen: Resumen) -> None:
    ya = {
        (a.accion, a.creado_en)
        for a in db.scalars(select(Auditoria).where(Auditoria.recepcion_id == rec.id))
    }
    for a in registros:
        accion = _recortar(a.get("accion"), 60) or "DESCONOCIDA"
        cuando = _fecha(a.get("creadoEn")) or datetime.now(timezone.utc)
        if (accion, cuando) in ya:
            resumen.ya_estaba("auditoría")
            continue
        db.add(Auditoria(
            recepcion_id=rec.id,
            operador_id=(_operador_de(a.get("operadorEmail"), por_correo, db,
                                      resumen) or Operador(id=None)).id,
            accion=accion,
            detalle=json.dumps(a.get("detalle"), ensure_ascii=False)
            if a.get("detalle") is not None else None,
            creado_en=cuando,
        ))
        ya.add((accion, cuando))
        resumen.nuevo("auditoría")


# --------------------------------------------------------------------------- #
# Entrada
# --------------------------------------------------------------------------- #
def importar(db: Session, datos: dict) -> Resumen:
    """Mete en la base lo que trae un export de la aplicación de la nube."""
    resumen = Resumen()

    version = datos.get("version")
    if version != 1:
        resumen.aviso(f"El archivo dice ser de la versión {version!r} y este "
                      "importador entiende la 1. Revisa el resultado.")

    por_correo = importar_operadores(db, datos.get("usuarios") or [], resumen)
    for r in datos.get("recepciones") or []:
        importar_recepcion(db, r, por_correo, resumen)

    # Se deja escrito en la sesión pero SIN confirmar: quien llama decide si
    # confirma o deshace. Confirmar aquí dejaba sin efecto el modo de ensayo del
    # script, que hacía la importación entera y la daba por descartada después.
    db.flush()
    return resumen
