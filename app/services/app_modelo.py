"""La lógica de la aplicación de los operarios, del lado del servidor.

Es la traducción de `js/datos.js` y `js/conteo.js` —lo que lleva meses en
producción contra Firestore— a esta base de datos. Las reglas son las mismas y
están puestas en el mismo orden a propósito: si alguna vez discrepan, lo que
manda es lo que el operario ya conoce.

Las cuatro que no se pueden perder:

1. **22 filas = 22 filas.** El packing list se devuelve con las mismas filas que
   trajo. Lo que aparece físicamente y no estaba en el archivo NO añade filas:
   vive aparte, como adicional.
2. **El reparto por lista.** Dos packing lists de la misma recepción pueden
   traer el mismo SKU. Lo contado se imputa a la lista que diga el operario,
   porque repartirlo después es adivinar.
3. **La clave de idempotencia.** El identificador del evento lo pone el
   handheld. Si la red se corta después de escribir, repetir el escaneo no
   cuenta dos veces.
4. **Las cantidades no se editan ni borran.** Una anulación es otro evento,
   compensatorio. La posición final puede completarse sin alterar unidades,
   con registro de auditoría de su valor anterior y responsable.
"""
from __future__ import annotations

import re
import math
from datetime import datetime
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    AppEvento, AppHuella, AppLinea, AppRecepcion, AppSku, utcnow,
)
from app.services import calidad, ajustes

ABIERTAS = ("ABIERTA", "EN_VALIDACION")


class ErrorApp(Exception):
    """Un error que el operario tiene que ver tal cual, con su código."""

    def __init__(self, mensaje: str, codigo: str = "ERROR"):
        super().__init__(mensaje)
        self.codigo = codigo


# --------------------------------------------------------------------------- #
# Las mismas normalizaciones que hace el navegador
# --------------------------------------------------------------------------- #
INVISIBLES = re.compile(r"[​‌‍﻿ ]")


def limpiar(v) -> str:
    return " ".join(INVISIBLES.sub(" ", str("" if v is None else v)).split())


def normalizar_codigo(v) -> str:
    return re.sub(r"[\s.\-_/]", "", limpiar(v)).upper()


def normalizar_pallet(v) -> str:
    """Punto de subpallet y guion entre bultos se conservan; se quitan espacios."""
    return re.sub(r"\s", "", limpiar(v)).upper()


def clave_pallet(p) -> str:
    """La clave con la que viaja un pallet dentro de un mapa JSON."""
    return normalizar_pallet(p).replace(".", "~")


def clave_mapa(v) -> str:
    """La de una lista: conserva los guiones del nombre, protege el punto."""
    return limpiar(v).upper().replace(".", "~")


def a_numero(v, por_defecto: float = 0.0) -> float:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return por_defecto
    return n if n == n and n not in (float("inf"), float("-inf")) else por_defecto


def estado_de(esperado: float, contado: float, verificado: bool | None = None) -> str:
    """El mismo semáforo que pinta la pantalla.

    Verificado = alguien ya lo buscó. Sin eso, un SKU con cero contado no se
    distingue de uno que nadie ha mirado todavía, y son cosas distintas.
    """
    if verificado is None:
        verificado = contado != 0
    if not verificado and contado == 0:
        return "PENDIENTE"
    if esperado == 0 and contado > 0:
        return "ADICIONAL"
    if contado == esperado:
        return "OK"
    if contado < esperado:
        return "FALTANTE"
    return "SOBRANTE"


# --------------------------------------------------------------------------- #
# De la base al documento que espera el navegador
# --------------------------------------------------------------------------- #
def _iso(f: datetime | None) -> str | None:
    return (f.isoformat(timespec="milliseconds") + ("Z" if f.tzinfo is None else "")) if f else None


def doc_recepcion(r: AppRecepcion, operarios: list[str] | None = None) -> dict:
    return {
        "id": r.codigo,
        "codigo": r.codigo,
        "cliente": r.cliente,
        "descripcion": r.descripcion or "",
        "bultos": r.bultos,
        "estado": r.estado,
        "hoja": r.hoja or "",
        "creadoPor": r.creado_por,
        "creadoEn": _iso(r.creado_en),
        "packingListEn": _iso(r.packing_list_en),
        "cerradaEn": _iso(r.cerrada_en),
        "cerradaPor": r.cerrada_por,
        "totales": r.totales or {"lineas": 0, "skus": 0, "unidades": 0},
        "origenes": r.origenes or [],
        "lineasPorOrigen": r.lineas_por_origen or {},
        "formatos": r.formatos or {},
        "embarques": r.embarques or [],
        "operarios": operarios if operarios is not None else [],
    }


def doc_sku(s: AppSku) -> dict:
    return {
        **calidad.documento(s),
        "id": s.sku,
        "sku": s.sku,
        "descripcion": s.descripcion or "",
        "esperado": s.esperado,
        "contado": s.contado,
        "verificado": s.verificado,
        "estado": s.estado,
        "enPackingList": s.en_packing_list,
        "tienePnc": s.tiene_pnc,
        "pallets": s.pallets or {},
        "porOrigen": s.por_origen or {},
        "origenes": s.origenes or [],
        "esperadoPorOrigen": s.esperado_por_origen or {},
        "ultimoOperador": s.ultimo_operador,
        "creadoEn": _iso(s.creado_en),
        "actualizadoEn": _iso(s.actualizado_en),
    }


def doc_linea(l: AppLinea) -> dict:
    return {
        "id": f"{l.origen}-{l.linea}",
        "linea": l.linea,
        "orden": l.orden,
        "origen": l.origen,
        "sku": l.sku,
        "descripcion": l.descripcion or "",
        "cantidad": l.cantidad,
        **(l.extra or {}),
    }


def doc_evento(e: AppEvento) -> dict:
    d = dict(e.datos or {})
    d.update({
        "id": e.id,
        "tipo": e.tipo,
        "sku": e.sku,
        "cantidad": e.cantidad,
        "pallet": e.pallet,
        "posicionReal": e.posicion,
        "origen": e.origen,
        "motivo": e.motivo,
        "anulaA": e.anula_a,
        "operadorEmail": e.usuario,
        "creadoEn": _iso(e.creado_en),
    })
    return d


def doc_adicional(s: AppSku) -> dict:
    return {
        "id": s.sku,
        "sku": s.sku,
        "descripcion": s.descripcion or "",
        "motivo": s.motivo or "Llegó físicamente sin estar en el packing list",
        "detectadoPorEmail": s.detectado_por,
        "creadoEn": _iso(s.creado_en),
    }


# --------------------------------------------------------------------------- #
# Consultas
# --------------------------------------------------------------------------- #
def obtener(db: Session, codigo: str, bloquear: bool = False) -> AppRecepcion:
    codigo = limpiar(codigo).upper()
    if bloquear:
        if db.get_bind().dialect.name == 'sqlite':
            # SQLite no tiene FOR UPDATE. Se toma el bloqueo de escritura
            # antes de leer el total; sirve tambien entre procesos distintos.
            cx = db.connection()
            if not cx.connection.driver_connection.in_transaction:
                cx.exec_driver_sql('BEGIN IMMEDIATE')
        r = db.scalar(select(AppRecepcion).where(AppRecepcion.codigo == codigo)
                      .with_for_update().execution_options(populate_existing=True))
    else:
        r = db.get(AppRecepcion, codigo)
    if r is None:
        raise ErrorApp(f"La recepción {codigo} no existe.", "NO_ENCONTRADA")
    return r


def operarios_de(db: Session, codigo: str) -> list[str]:
    """Quién ha contado en esta recepción.

    Se deriva del libro mayor en vez de guardarse en la recepción: en Firestore
    era una lista en el documento porque listar eventos costaba lecturas; aquí
    es un DISTINCT y no puede quedarse desincronizada.
    """
    return [
        u for u in db.execute(
            select(AppEvento.usuario).where(AppEvento.recepcion == codigo).distinct()
        ).scalars() if u
    ]


def listar_recepciones(db: Session, max_filas: int = 50,
                       usuario: str | None = None) -> list[dict]:
    q = select(AppRecepcion).order_by(AppRecepcion.creado_en.desc()).limit(max_filas)
    if usuario:
        # Las suyas: aquellas donde registró algo. Es la pregunta que hace el
        # operario al entrar, y la respuesta no puede costar una lectura por
        # conteo de la jornada.
        suyas = select(AppEvento.recepcion).where(AppEvento.usuario == usuario).distinct()
        q = (select(AppRecepcion).where(AppRecepcion.codigo.in_(suyas))
             .order_by(AppRecepcion.creado_en.desc()).limit(max_filas))
    from app.services.seguimiento import resumenes
    filas = list(db.execute(q).scalars().all())
    metricas = resumenes(db, [r.codigo for r in filas])
    nombres=nombres_listas(db,[r.codigo for r in filas])
    return [{**doc_recepcion(r), 'nombresListas':nombres.get(r.codigo,{}), **metricas.get(r.codigo, {})} for r in filas]


def nombres_listas(db,codigos):
    """Identificación ligera; no descargar las celdas originales de los Excel."""
    if not codigos:return {}
    embs={}
    for codigo,origen,emb in db.execute(select(AppLinea.recepcion,AppLinea.origen,AppLinea.extra['embarque'].as_string()).where(AppLinea.recepcion.in_(codigos)).distinct()):
        if emb:embs.setdefault(codigo,{}).setdefault(origen,set()).add(str(emb))
    return {codigo:{o:o+' - '+', '.join(sorted(es)) if o=='PRINCIPAL' else o for o,es in os.items()} for codigo,os in embs.items()}


def leer_coleccion(db: Session, codigo: str, nombre: str, max_filas: int = 0, *, actual: bool = False) -> list[dict]:
    """Las subcolecciones que la aplicación lee de una recepción."""
    codigo = limpiar(codigo).upper()
    if nombre == "lineas":
        q = select(AppLinea).where(AppLinea.recepcion == codigo).order_by(AppLinea.orden)
        return [doc_linea(x) for x in db.execute(q.with_for_update().execution_options(populate_existing=True) if actual else q).scalars().all()]
    if nombre == "skus":
        q = select(AppSku).where(AppSku.recepcion == codigo).order_by(AppSku.verificado.desc(), AppSku.actualizado_en.desc(), AppSku.sku)
        return [doc_sku(x) for x in db.execute(q.with_for_update().execution_options(populate_existing=True) if actual else q).scalars().all()]
    if nombre == "adicionales":
        q = (select(AppSku)
             .where(AppSku.recepcion == codigo, AppSku.en_packing_list.is_(False))
             .order_by(AppSku.sku))
        return [doc_adicional(x) for x in db.execute(q.with_for_update().execution_options(populate_existing=True) if actual else q).scalars().all()]
    if nombre in ("eventos", "auditoria"):
        q = select(AppEvento).where(AppEvento.recepcion == codigo)
        if nombre == "auditoria":
            q = q.where(AppEvento.tipo.in_(
                ("CIERRE", "REAPERTURA", "AJUSTE", "EXPORT", "AUDITORIA", "ANULACION")))
        q = q.order_by(AppEvento.creado_en.desc())
        if max_filas:
            q = q.limit(max_filas)
        return [doc_evento(x) for x in db.execute(q.with_for_update().execution_options(populate_existing=True) if actual else q).scalars().all()]
    raise ErrorApp(f"No existe la colección «{nombre}».", "COLECCION_DESCONOCIDA")


# --------------------------------------------------------------------------- #
# Alta de una recepción
# --------------------------------------------------------------------------- #
def crear_recepcion(db: Session, datos: dict, usuario: str | None) -> dict:
    codigo = limpiar(datos.get("codigo")).upper()
    if not codigo:
        raise ErrorApp("Falta el código de la recepción.", "CODIGO_REQUERIDO")
    if db.get(AppRecepcion, codigo) is not None:
        raise ErrorApp(f"Ya existe una recepción con el código {codigo}.", "DUPLICADA")

    from app.models import AppConfig
    fichas=db.get(AppConfig,'clientes_fichas')
    ficha=(fichas.datos or {}).get(limpiar(datos.get('cliente')).upper(),{}) if fichas else {}
    if ficha.get('eliminado'):raise ErrorApp('El cliente fue eliminado de la lista activa. Selecciona un cliente vigente.','CLIENTE_ELIMINADO')
    r = AppRecepcion(
        codigo=codigo,
        cliente=limpiar(datos.get("cliente")).upper() or "VENTURA",
        descripcion=limpiar(datos.get("descripcion")) or None,
        bultos=int(a_numero(datos.get("bultos"), 0)) or None,
        estado="ABIERTA",
        creado_por=usuario,
        totales={"lineas": 0, "skus": 0, "unidades": 0},
        origenes=[], lineas_por_origen={}, formatos={}, embarques=[],
    )
    db.add(r)
    db.commit()
    return doc_recepcion(r, [])


def borrar_recepcion(db: Session, codigo: str) -> dict:
    """Se lleva por delante líneas, SKU, eventos y huellas. Es irreversible."""
    codigo = limpiar(codigo).upper()
    r = obtener(db, codigo, bloquear=True)
    cuentas = {}
    for modelo, nombre in ((AppLinea, "lineas"), (AppSku, "skus"),
                           (AppEvento, "eventos"), (AppHuella, "huellas")):
        cuentas[nombre] = db.scalar(
            select(func.count()).select_from(modelo).where(modelo.recepcion == codigo)) or 0
        db.execute(delete(modelo).where(modelo.recepcion == codigo))
    from app.models import AppConfig
    from app.services.correo_redactado import clave_config
    db.execute(delete(AppConfig).where(AppConfig.clave.in_([clave_config(codigo),clave_config(codigo,manual=True)])))
    db.delete(r)
    db.commit()
    return {"codigo": codigo, "borrado": cuentas}


# --------------------------------------------------------------------------- #
# El packing list
# --------------------------------------------------------------------------- #
def guardar_packing_list(db: Session, codigo: str, resultado: dict,
                         origen: str = "PRINCIPAL", archivo: str | None = None) -> dict:
    """Guarda un packing list ya leído por el navegador.

    El archivo NO se sube: lo lee el navegador con la misma rutina que lleva
    meses en producción —la que conoce los formatos de VENTURA, GAC e
    IMPOFACTOR— y manda el resultado ya traducido. Tener dos lectores de Excel,
    uno en cada lado, sería tener dos cosas que pueden discrepar sobre cuántas
    unidades declara una fila.

    Se puede cargar más de una lista en la misma recepción. Lo esperado se
    acumula: el mismo SKU en dos listas se cuenta una vez, contra la suma.
    """
    r = obtener(db, codigo, bloquear=True)
    origen = limpiar(origen).upper()[:40] or "PRINCIPAL"
    origenes = list(r.origenes or [])

    if origen in origenes:
        raise ErrorApp(
            f"Ya se cargó un packing list con el nombre «{origen}» en esta recepción. "
            "Usa otro nombre para distinguirlos en el informe.",
            "ORIGEN_DUPLICADO",
        )

    lineas = resultado.get("lineas") or []
    por_sku = resultado.get("porSku") or {}
    if not lineas:
        raise ErrorApp("El packing list no trae ninguna línea.", "SIN_LINEAS")
    if any(not math.isfinite(a_numero(l.get('cantidad'), 0)) or a_numero(l.get('cantidad'), 0) < 0 for l in lineas) or any(
            not math.isfinite(a_numero(v, 0)) or a_numero(v, 0) < 0 for v in por_sku.values()):
        raise ErrorApp('El packing list contiene cantidades negativas o no válidas. Corrige el archivo antes de importarlo.', 'CANTIDAD_INVALIDA')

    ya = r.totales or {"lineas": 0, "skus": 0, "unidades": 0}
    base = int(a_numero(ya.get("lineas"), 0))

    # 1. Las líneas, tal cual venían. El orden se conserva sumando el número de
    #    línea a lo que ya había: así dos listas con una línea 1 no se pisan.
    orden_base=db.scalar(select(func.max(AppLinea.orden)).where(AppLinea.recepcion==codigo)) or 0
    conocidas = {"linea", "sku", "descripcion", "cantidad", "origen", "orden"}
    for l in lineas:
        n = int(a_numero(l.get("linea"), 0))
        db.add(AppLinea(
            recepcion=r.codigo, origen=origen, linea=n, orden=orden_base + n,
            sku=normalizar_codigo(l.get("sku")),
            descripcion=limpiar(l.get("descripcion"))[:300] or None,
            cantidad=a_numero(l.get("cantidad"), 0),
            extra={k: v for k, v in l.items() if k not in conocidas} or None,
        ))

    # 2. Lo esperado por SKU, acumulando sobre lo que ya hubiera.
    existentes = {
        s.sku: s for s in db.execute(
            select(AppSku).with_for_update().execution_options(populate_existing=True).where(AppSku.recepcion == r.codigo)).scalars().all()
    }
    ahora = utcnow().replace(tzinfo=None)
    compartidos = []
    for sku_crudo, esperado in por_sku.items():
        sku = normalizar_codigo(sku_crudo)
        esperado = a_numero(esperado, 0)
        primera = next((l for l in lineas if normalizar_codigo(l.get("sku")) == sku), None)
        s = existentes.get(sku)
        if s is None:
            s = AppSku(recepcion=r.codigo, sku=sku, contado=0, verificado=False,
                       pallets={}, por_origen={}, origenes=[], esperado_por_origen={},
                       creado_en=ahora)
            db.add(s)
            existentes[sku] = s
        else:
            compartidos.append(sku)
        s.esperado = a_numero(s.esperado, 0) + esperado
        s.descripcion = s.descripcion or (limpiar(primera.get("descripcion"))[:300]
                                          if primera else "")
        s.en_packing_list = True
        s.origenes = sorted({*(s.origenes or []), origen})
        s.esperado_por_origen = {**(s.esperado_por_origen or {}),
                                 clave_mapa(origen): esperado}
        s.estado = estado_de(s.esperado, a_numero(s.contado, 0), s.verificado)
        s.actualizado_en = ahora

    # 3. La cabecera del archivo, para devolverlo igual, y la huella, para
    #    reconocerlo si vuelve a subirse en otra recepción.
    formato = {
        "encabezados": resultado.get("encabezados") or [],
        "prefijo": resultado.get("prefijo") or [],
        "columnas": resultado.get("columnas") or {},
        "hoja": resultado.get("hoja") or "",
    }
    for clave in ("huella", "lineas", "skus", "unidades", "archivo"):
        if clave in (resultado.get("resumen") or {}):
            formato[clave] = resultado["resumen"][clave]

    r.totales = {
        "lineas": base + len(lineas),
        "skus": len(existentes),
        "unidades": a_numero(ya.get("unidades"), 0) + a_numero(resultado.get("unidades"), 0),
    }
    r.origenes = [*origenes, origen]
    r.lineas_por_origen = {**(r.lineas_por_origen or {}), clave_mapa(origen): len(lineas)}
    r.formatos = {**(r.formatos or {}), clave_mapa(origen): formato}
    r.hoja = resultado.get("hoja") or r.hoja
    r.embarques = sorted({*(r.embarques or []), *(resultado.get("embarques") or [])})
    r.packing_list_en = ahora
    from app.services.fotos_organizacion import actualizar_por_embarques
    actualizar_por_embarques(db,r.codigo)

    resumen = resultado.get("resumen") or {}
    if resumen.get("huella"):
        db.merge(AppHuella(
            id=f"{r.codigo}__{clave_mapa(origen)}",
            huella=str(resumen["huella"])[:32],
            recepcion=r.codigo, codigo=r.codigo, origen=origen,
            archivo=limpiar(resumen.get("archivo") or archivo)[:300] or None,
            lineas=int(a_numero(resumen.get("lineas"), len(lineas))),
            skus=int(a_numero(resumen.get("skus"), len(por_sku))),
            unidades=a_numero(resumen.get("unidades"), 0),
            creado_en=ahora,
        ))

    db.commit()
    return {"origen": origen, "lineas": len(lineas), "compartidos": compartidos}


def packing_lists_parecidos(db: Session, resumen: dict,
                            excluir: str | None = None) -> list[dict]:
    """Packing lists ya cargados que se parecen al que se está subiendo.

    Tres preguntas, de más a menos segura: ¿la misma huella de contenido?, ¿el
    mismo número de líneas y de SKU?, ¿el mismo nombre de archivo? Un duplicado
    cambia de nombre con un clic; su contenido no.
    """
    huella = limpiar(resumen.get("huella"))
    lineas = int(a_numero(resumen.get("lineas"), 0))
    skus = int(a_numero(resumen.get("skus"), 0))
    archivo = limpiar(resumen.get("archivo"))

    encontrados: dict[str, AppHuella] = {}
    consultas = []
    if huella:
        consultas.append(select(AppHuella).where(AppHuella.huella == huella))
    if lineas and skus:
        consultas.append(select(AppHuella).where(
            AppHuella.lineas == lineas, AppHuella.skus == skus))
    if archivo:
        consultas.append(select(AppHuella).where(AppHuella.archivo == archivo))

    for q in consultas:
        for h in db.execute(q.limit(20)).scalars().all():
            if excluir and h.recepcion == limpiar(excluir).upper():
                continue
            encontrados[h.id] = h

    return [{
        "id": h.id, "huella": h.huella, "recepcion": h.recepcion, "codigo": h.codigo,
        "origen": h.origen, "archivo": h.archivo, "lineas": h.lineas,
        "skus": h.skus, "unidades": h.unidades, "creadoEn": _iso(h.creado_en),
    } for h in encontrados.values()]


# --------------------------------------------------------------------------- #
# El libro mayor: contar, anular, declarar un cero
# --------------------------------------------------------------------------- #
def _sumar_en_mapa(mapa: dict | None, clave: str, cantidad: float) -> dict:
    """Suma dentro de un mapa JSON y deja fuera lo que quede en cero.

    En Firestore esto era `increment()` sobre un campo anidado. Aquí es Python,
    pero la regla que importa es la misma: el mapa guarda el reparto, y un
    pallet que queda a cero después de una anulación no es «pallet con cero
    unidades», es un pallet en el que ya no hay nada.
    """
    nuevo = dict(mapa or {})
    total = a_numero(nuevo.get(clave), 0) + cantidad
    if total == 0:
        nuevo.pop(clave, None)
    else:
        nuevo[clave] = total
    return nuevo


def _aplicar_al_sku(s: AppSku, d: dict, usuario: str | None) -> None:
    """Lleva un evento al agregado del SKU. No decide nada: ya está decidido."""
    cantidad = d["cantidad"]
    s.contado = a_numero(s.contado, 0) + cantidad
    s.pallets = _sumar_en_mapa(s.pallets, clave_pallet(d["pallet"]), cantidad)

    # El reparto por lista: {lista: {pallet: cantidad}}. Es lo que permite
    # devolver cada packing list con lo suyo en vez de repartirlo a ojo.
    if d.get("origen"):
        por_origen = dict(s.por_origen or {})
        clave = clave_mapa(d["origen"])
        anidado = _sumar_en_mapa(por_origen.get(clave), clave_pallet(d["pallet"]), cantidad)
        if anidado:
            por_origen[clave] = anidado
        else:
            por_origen.pop(clave, None)
        s.por_origen = por_origen

    if d.get("estado_fisico") == "PNC":
        s.tiene_pnc = True
    if cantidad != 0 or d.get("tipo") == "CERO":
        s.verificado = True
    if usuario:
        s.ultimo_operador = usuario
    s.estado = estado_de(a_numero(s.esperado, 0), a_numero(s.contado, 0), s.verificado)
    s.actualizado_en = utcnow().replace(tzinfo=None)


def registrar_conteo(db: Session, codigo: str, usuario: str | None, p: dict, *, confirmar=True) -> dict:
    """Registra un conteo físico. El orden de las comprobaciones es el de la app.

    Devuelve lo mismo que devolvía la transacción de Firestore, porque la
    pantalla del handheld lee exactamente esos campos.
    """
    sku = normalizar_codigo(p.get("sku"))
    if not sku:
        raise ErrorApp("Falta el código del producto.", "SKU_REQUERIDO")
    pallet = normalizar_pallet(p.get("pallet"))
    cantidad = a_numero(p.get("cantidad"), 0)
    if not math.isfinite(cantidad) or cantidad < 0:
        raise ErrorApp('La cantidad física no admite negativos. Si no apareció, declara 0; para corregir, anula el conteo.', 'CANTIDAD_INVALIDA')
    idem = limpiar(p.get("idempotencyKey") or p.get("id"))
    if not idem:
        raise ErrorApp("Falta la clave del evento.", "CLAVE_REQUERIDA")

    codigo = limpiar(codigo).upper()
    r = obtener(db, codigo, bloquear=True)

    # 1. ¿Ya estaba escrito? Entonces la red se cortó DESPUÉS de guardar y el
    #    operario está repitiendo. No se cuenta dos veces.
    anterior = db.scalar(select(AppEvento).where(AppEvento.id == idem).with_for_update())
    if anterior is not None:
        if anterior.recepcion != codigo or anterior.sku != sku:
            raise ErrorApp('El identificador ya corresponde a otro movimiento. Inicia un nuevo registro.', 'CLAVE_EN_CONFLICTO')
        s = db.execute(select(AppSku).with_for_update().execution_options(populate_existing=True).where(
            AppSku.recepcion == codigo, AppSku.sku == sku)).scalar_one_or_none()
        if s:
            from app.models import AppCalidadSku
            s.calidad=db.scalar(select(AppCalidadSku).where(AppCalidadSku.sku_id==s.id).with_for_update().execution_options(populate_existing=True))
        esperado = a_numero(s.esperado, 0) if s else 0
        contado = a_numero(s.contado, 0) if s else 0
        return {
            "duplicado": True, "sku": sku, "esperado": esperado, "contado": contado,
            "pendiente": max(esperado - contado, 0),
            "estado": (s.estado if s else estado_de(esperado, contado)),
            'pallets': s.pallets if s else {},
            **(calidad.documento(s) if s else {}),
        }

    if r.estado not in ABIERTAS:
        raise ErrorApp(
            f"La recepción está {r.estado}: no admite más conteos.", "RECEPCION_CERRADA")

    reglas = ajustes.cliente(db, r.cliente)
    if not pallet and reglas['palletRequerido']:
        raise ErrorApp("Falta el pallet.", "PALLET_REQUERIDO")
    if pallet and (len(pallet)>40 or not re.fullmatch(r'[A-Z0-9]+(?:\.[A-Z0-9]+)*(?:-[A-Z0-9]+(?:\.[A-Z0-9]+)*)*',pallet)):
        raise ErrorApp('Pallet / subpallet: usa letras y números; punto para subpallet (B02.1), guion entre bultos (B02-B03). No se admiten otros caracteres.', 'PALLET_INVALIDO')
    if cantidad > 0 and reglas['posicionRequerida'] and not normalizar_pallet(p.get('posicionReal')):
        raise ErrorApp('Este cliente requiere la posición real.', 'POSICION_REQUERIDA')

    s = db.execute(select(AppSku).with_for_update().execution_options(populate_existing=True).where(
        AppSku.recepcion == codigo, AppSku.sku == sku)).scalar_one_or_none()
    esperado = a_numero(s.esperado, 0) if s else 0
    previo = a_numero(s.contado, 0) if s else 0
    total = previo + cantidad
    en_packing = bool(s.en_packing_list) if s else False
    origen = limpiar(p.get('origen')).upper()
    if s and s.origenes:
        if not origen and len(s.origenes) == 1:
            origen = s.origenes[0]
        if origen and origen not in s.origenes:
            raise ErrorApp('El producto no pertenece a ese packing list.', 'ORIGEN_INVALIDO')
        if len(s.origenes) > 1 and not origen:
            raise ErrorApp('Selecciona el packing list del producto.', 'ORIGEN_REQUERIDO')
        dec = a_numero((s.esperado_por_origen or {}).get(clave_mapa(origen)), 0)
        por_pallet = (s.por_origen or {}).get(clave_mapa(origen), {})
        ya = sum(a_numero(n,0) for n in por_pallet.values()) if isinstance(por_pallet,dict) else a_numero(por_pallet,0)
        if origen and cantidad > 0 and ya + cantidad > dec and not p.get('confirmarSobrante'):
            raise ErrorApp(f'La lista {origen} declara {dec} y lleva {ya}. Revisa las otras listas o confirma el sobrante de esta lista.', 'CONFIRMAR_SOBRANTE')
    p = {**p, 'origen': origen}

    # 2. Un ajuste no puede dejar el conteo en negativo.
    if total < 0:
        raise ErrorApp(
            f"El ajuste dejaría el conteo en {total}. Contado actual: {previo}.",
            "AJUSTE_INVALIDO")

    # 3. Sobrante: lo confirma el operario, no el servidor.
    if cantidad > 0 and total > esperado and not p.get("confirmarSobrante"):
        if esperado == 0:
            msg = (f"{sku} no está en el packing list. Si llegó físicamente, "
                   "confírmelo como adicional.")
        else:
            msg = (f"SOBRANTE: el packing list declara {esperado} y ya hay {previo}. "
                   f"Esto genera {total - esperado} de exceso. Confirme para registrarlo.")
        raise ErrorApp(msg, "CONFIRMAR_SOBRANTE")

    ahora = utcnow().replace(tzinfo=None)
    incidencias = calidad.validar(db, p, cantidad)
    fotos = p.get('fotos') or []
    if not isinstance(fotos,list) or any(not isinstance(f,str) or len(f)>2048 or not f.startswith(('/api/app/archivos/','https://')) for f in fotos):
        raise ErrorApp('Las fotos del conteo deben ser enlaces de archivos guardados, no imágenes incrustadas.', 'FOTOS_INVALIDAS')
    datos = {
        'incidencias': incidencias,
        "codigoEscaneado": limpiar(p.get("codigoEscaneado")) or None,
        "estadoFisico": limpiar(p.get("estadoFisico")) or None,
        "observacion": limpiar(p.get("observacion")) or None,
        "fotos": fotos,
        "operadorNombre": limpiar(p.get("operadorNombre")) or None,
        "interpretacionLectura": limpiar(p.get("interpretacionLectura"))[:500] or None,
    }
    db.add(AppEvento(
        id=idem, recepcion=codigo, tipo=limpiar(p.get("tipo")) or "CONTEO", sku=sku,
        cantidad=cantidad, pallet=pallet,
        posicion=re.sub(r"\s", "", limpiar(p.get("posicionReal"))).upper() or None,
        origen=limpiar(p.get("origen")).upper() or None,
        usuario=usuario, motivo=None, datos=datos, creado_en=ahora,
    ))

    if s is None:
        s = AppSku(
            recepcion=codigo, sku=sku, esperado=0, contado=0, verificado=False,
            en_packing_list=False, tiene_pnc=False, pallets={}, por_origen={},
            origenes=[], esperado_por_origen={},
            descripcion=limpiar(p.get("descripcion"))[:300] or "",
            motivo=limpiar(p.get("motivo"))[:300]
                   or "Llegó físicamente sin estar en el packing list",
            detectado_por=usuario, creado_en=ahora, actualizado_en=ahora,
        )
        db.add(s)
        db.flush()
    elif not s.descripcion:
        s.descripcion = limpiar(p.get("descripcion"))[:300] or ""

    _aplicar_al_sku(s, {
        "cantidad": cantidad, "pallet": pallet,
        "origen": limpiar(p.get("origen")).upper() or None,
        "estado_fisico": limpiar(p.get("estadoFisico")) or None,
        "tipo": limpiar(p.get("tipo")) or "CONTEO",
    }, usuario)

    # 4. La recepción pasa a EN_VALIDACION en cuanto alguien cuenta algo.
    if r.estado == "ABIERTA":
        r.estado = "EN_VALIDACION"

    calidad.actualizar(db, s)
    from app.services.operacion import actualizar_fotos_conteo
    actualizar_fotos_conteo(db,s,fotos,usuario,idem)
    db.commit() if confirmar else db.flush()
    return {
        "duplicado": False, "eventoId": idem, "sku": sku,
        "cantidadRegistrada": cantidad, "pallet": pallet,
        'pallets': s.pallets or {}, 'porOrigen': s.por_origen or {},
        "actualizadoEn": _iso(s.actualizado_en),
        "esperado": esperado, "contado": a_numero(s.contado, 0),
        "pendiente": max(esperado - a_numero(s.contado, 0), 0),
        "estado": s.estado,
        "esAdicional": not en_packing and esperado == 0,
        **calidad.documento(s),
    }


def anular_conteo(db: Session, codigo: str, usuario: str | None,
                  evento_id: str, motivo: str, *, confirmar=True) -> dict:
    """Reversa un conteo con un evento compensatorio. El original nunca se borra."""
    motivo = limpiar(motivo)
    if not motivo:
        raise ErrorApp("Debe indicar el motivo de la anulación.", "MOTIVO_REQUERIDO")

    codigo = limpiar(codigo).upper()
    r = obtener(db, codigo, bloquear=True)
    original = db.scalar(select(AppEvento).with_for_update().where(AppEvento.id == limpiar(evento_id)))
    if original is None or original.recepcion != codigo:
        raise ErrorApp("Ese movimiento no existe en esta recepción.", "NO_ENCONTRADO")
    if original.tipo == "ANULACION":
        raise ErrorApp("Ese movimiento ya es una anulación.", "YA_ANULADO")

    ya = db.execute(select(AppEvento).with_for_update().where(
        AppEvento.anula_a == original.id)).scalar_one_or_none()
    if ya is not None:
        raise ErrorApp("Ese movimiento ya estaba anulado.", "YA_ANULADO")

    if r.estado not in ABIERTAS:
        raise ErrorApp(
            f"La recepción está {r.estado}: no admite anulaciones.", "RECEPCION_CERRADA")

    ahora = utcnow().replace(tzinfo=None)
    compensacion = AppEvento(
        id=f"anu_{original.id}", recepcion=codigo, tipo="ANULACION", sku=original.sku,
        cantidad=-a_numero(original.cantidad, 0), pallet=original.pallet,
        posicion=original.posicion, origen=original.origen, usuario=usuario,
        anula_a=original.id, motivo=motivo[:300], creado_en=ahora,
        datos={"operadorNombre": None},
    )
    db.add(compensacion)

    s = db.execute(select(AppSku).with_for_update().execution_options(populate_existing=True).where(
        AppSku.recepcion == codigo, AppSku.sku == original.sku)).scalar_one_or_none()
    if s is not None:
        _aplicar_al_sku(s, {
            "cantidad": -a_numero(original.cantidad, 0),
            "pallet": original.pallet, "origen": original.origen,
            "estado_fisico": None, "tipo": "ANULACION",
        }, usuario)
        calidad.actualizar(db, s)

    db.commit() if confirmar else db.flush()
    return {
        "eventoId": compensacion.id, "anulado": original.id, "sku": original.sku,
        "cantidad": -a_numero(original.cantidad, 0),
        "contado": a_numero(s.contado, 0) if s else 0,
        "estado": s.estado if s else "PENDIENTE",
    }


def declarar_no_encontrado(db: Session, codigo: str, usuario: str | None,
                           p: dict) -> dict:
    """Un cero declarado: alguien lo buscó y no estaba.

    No es lo mismo que un SKU que nadie ha mirado, y por eso deja evento: es la
    diferencia entre «faltante confirmado» y «pendiente».
    """
    return registrar_conteo(db, codigo, usuario, {
        **p, "cantidad": 0, "tipo": "CERO",
        "pallet": p.get("pallet") or "SIN-UBICACION",
    })


def registrar_auditoria(db: Session, codigo: str, usuario: str | None,
                        tipo: str, detalle: dict | None = None) -> dict:
    ahora = utcnow().replace(tzinfo=None)
    ident = "aud_" + uuid4().hex
    db.add(AppEvento(
        id=ident, recepcion=limpiar(codigo).upper(), tipo=limpiar(tipo).upper() or "AUDITORIA",
        sku=None, cantidad=0, usuario=usuario, datos=detalle or {}, creado_en=ahora,
    ))
    db.commit()
    return {"id": ident}


# --------------------------------------------------------------------------- #
# Cierre y reapertura
# --------------------------------------------------------------------------- #
def cerrar_recepcion(db: Session, codigo: str, usuario: str | None, *, confirmar: bool = True) -> dict:
    r = obtener(db, codigo, bloquear=True)
    if r.estado == "CERRADA":
        raise ErrorApp("La recepción ya estaba cerrada.", "YA_CERRADA")
    ahora = utcnow().replace(tzinfo=None)
    r.estado = "CERRADA"
    r.cerrada_en = ahora
    r.cerrada_por = usuario
    db.add(AppEvento(
        id=f"cie_{r.codigo}_{ahora.timestamp():.3f}", recepcion=r.codigo, tipo="CIERRE",
        cantidad=0, usuario=usuario, creado_en=ahora,
        datos={"totales": r.totales or {}},
    ))
    if confirmar:
        db.commit()
    else:
        db.flush()
        # MySQL conserva milisegundos; usar el valor realmente persistido
        # para la clave idempotente del cierre y su instantanea.
        db.refresh(r, attribute_names=["cerrada_en"])
    return doc_recepcion(r, operarios_de(db, r.codigo))


def reabrir_recepcion(db: Session, codigo: str, usuario: str | None,
                      motivo: str = "") -> dict:
    r = obtener(db, codigo, bloquear=True)
    if r.estado != "CERRADA":
        raise ErrorApp("La recepción no está cerrada.", "NO_CERRADA")
    ahora = utcnow().replace(tzinfo=None)
    r.estado = "EN_VALIDACION"
    r.cerrada_en = None
    r.cerrada_por = None
    db.add(AppEvento(
        id=f"rea_{r.codigo}_{ahora.timestamp():.3f}", recepcion=r.codigo,
        tipo="REAPERTURA", cantidad=0, usuario=usuario,
        motivo=limpiar(motivo)[:300] or None, creado_en=ahora, datos={},
    ))
    db.commit()
    return doc_recepcion(r, operarios_de(db, r.codigo))


def recalcular_sku(db: Session, codigo: str, sku: str) -> dict:
    """Vuelve a armar el agregado de un SKU desde el libro mayor.

    El agregado existe por velocidad; la verdad son los eventos. Esto es lo que
    permite afirmarlo: si alguna vez discrepan, esto los vuelve a poner de
    acuerdo, y una prueba puede comprobar que no discrepaban.
    """
    codigo, sku = limpiar(codigo).upper(), normalizar_codigo(sku)
    obtener(db, codigo, bloquear=True)
    s = db.execute(select(AppSku).with_for_update().execution_options(populate_existing=True).where(
        AppSku.recepcion == codigo, AppSku.sku == sku)).scalar_one_or_none()
    if s is None:
        raise ErrorApp(f"{sku} no está en la recepción {codigo}.", "NO_ENCONTRADO")

    eventos = db.execute(
        select(AppEvento).with_for_update().where(AppEvento.recepcion == codigo, AppEvento.sku == sku)
        .order_by(AppEvento.creado_en)
    ).scalars().all()

    s.contado, s.pallets, s.por_origen = 0, {}, {}
    s.verificado, s.tiene_pnc = False, False
    for e in eventos:
        _aplicar_al_sku(s, {
            "cantidad": a_numero(e.cantidad, 0), "pallet": e.pallet, "origen": e.origen,
            "estado_fisico": (e.datos or {}).get("estadoFisico"), "tipo": e.tipo,
        }, e.usuario)
    calidad.actualizar(db, s)
    db.commit()
    return doc_sku(s)
