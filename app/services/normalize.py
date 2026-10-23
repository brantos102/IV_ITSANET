"""Normalizacion de codigos y saneamiento de texto.

Los datos reales traen basura que rompe los cruces:
  * espacios no separables (\\xa0) al inicio del producto_id en el MAESTRO,
  * SKUs escritos en minusculas o con guiones,
  * acentos y caracteres especiales que el sistema Depot rechaza.
"""
from __future__ import annotations

import re
import unicodedata

_INVISIBLES = dict.fromkeys(map(ord, "\xa0​‌‍﻿\t\r\n"), " ")
_RE_PALLET = re.compile(r"^[A-Z0-9]+(?:\.[A-Z0-9]+)*(?:-[A-Z0-9]+(?:\.[A-Z0-9]+)*)*$")
# Permitido en celdas exportadas al sistema Depot.
_RE_PERMITIDO = re.compile(r"[^A-Z0-9 ./\-,:+#%()]")


def limpiar(valor) -> str:
    """Quita invisibles y espacios sobrantes. Nunca devuelve None."""
    if valor is None:
        return ""
    s = str(valor).translate(_INVISIBLES)
    return re.sub(r"\s+", " ", s).strip()


def normalizar_sku(valor) -> str:
    """Clave canonica de un SKU: sin invisibles, sin separadores, en mayusculas.

    '\\xa05C6845202B' -> '5C6845202B' ; '2h0-525345' -> '2H0525345'
    """
    s = limpiar(valor).upper()
    return re.sub(r"[\s\-_.]", "", s)


def normalizar_ean(valor) -> str:
    s = limpiar(valor).upper()
    return re.sub(r"[^0-9A-Z]", "", s)


def normalizar_pallet(valor) -> str:
    """Pallet alfanumerico, subpallet con punto: A1, A1.1, B04.3."""
    return re.sub(r"\s", "", limpiar(valor).upper())


def pallet_valido(codigo: str) -> bool:
    c = normalizar_pallet(codigo)
    return bool(c) and len(c) <= 40 and bool(_RE_PALLET.match(c))


def pallet_padre(codigo: str) -> str | None:
    c = normalizar_pallet(codigo)
    return c.rsplit(".", 1)[0] if "." in c else None


def sin_acentos(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def sanear_celda(valor, max_len: int = 300) -> str:
    """Texto apto para subir al sistema Depot: sin acentos ni caracteres raros.

    Regla del flujo de trabajo: "No caracteres especiales".
    """
    s = sin_acentos(limpiar(valor)).upper()
    s = _RE_PERMITIDO.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()[:max_len]


def a_numero(valor, default: float = 0.0) -> float:
    if valor is None or valor == "":
        return default
    if isinstance(valor, (int, float)):
        return float(valor)
    s = limpiar(valor).replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    try:
        return float(s)
    except ValueError:
        return default


def entero_si_aplica(n: float):
    """Devuelve int cuando el numero no tiene decimales (para no exportar 1.0)."""
    return int(n) if float(n).is_integer() else n
