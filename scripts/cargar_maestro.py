#!/usr/bin/env python3
"""Carga el maestro de productos de Depot al cache local.

    python scripts/cargar_maestro.py archivo.xlsx [--hoja MAESTRO]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Producto  # noqa: E402
from app.routers.catalogo import cargar_maestro_desde  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Carga el maestro de productos Depot")
    p.add_argument("archivo", type=Path)
    p.add_argument("--hoja", default=None)
    args = p.parse_args()

    if not args.archivo.exists():
        print(f"No existe: {args.archivo}", file=sys.stderr)
        return 1

    init_db()
    with SessionLocal() as db:
        n = cargar_maestro_desde(db, args.archivo, args.hoja)
        total = db.scalar(select(func.count()).select_from(Producto))
    print(f"Procesados {n} registros. Cache local: {total} productos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
