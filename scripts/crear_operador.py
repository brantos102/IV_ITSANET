#!/usr/bin/env python3
"""Crea o actualiza un operador.

    python scripts/crear_operador.py juan "Juan Perez" 4821 --rol OPERADOR
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Operador, Rol  # noqa: E402
from app.security import hash_pin  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("usuario")
    p.add_argument("nombre")
    p.add_argument("pin")
    p.add_argument("--rol", default="OPERADOR", choices=[r.value for r in Rol])
    args = p.parse_args()

    init_db()
    with SessionLocal() as db:
        usuario = args.usuario.strip().lower()
        op = db.execute(
            select(Operador).where(Operador.usuario == usuario)
        ).scalar_one_or_none()
        if op:
            op.nombre, op.pin_hash, op.rol = args.nombre, hash_pin(args.pin), Rol(args.rol)
            accion = "actualizado"
        else:
            db.add(Operador(usuario=usuario, nombre=args.nombre,
                            pin_hash=hash_pin(args.pin), rol=Rol(args.rol)))
            accion = "creado"
        db.commit()
    print(f"Operador '{usuario}' {accion} con rol {args.rol}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
