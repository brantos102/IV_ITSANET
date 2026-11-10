#!/usr/bin/env python3
"""Mete en la base local el histórico exportado de la aplicación en la nube.

    python scripts/importar_firestore.py export-itsanet.json

El archivo sale de Administración → «Exportar para el servidor local», en
https://iv-itsanet.web.app/admin.html, entrando como ADMIN.

Se puede lanzar las veces que haga falta: no duplica nada. Con --ensayo hace
todo el trabajo y deshace al final, para ver qué entraría sin tocar la base.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal, comprobar_conexion, init_db  # noqa: E402
from app.services.migracion import importar  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("archivo", type=Path, help="el .json exportado desde la nube")
    p.add_argument("--ensayo", action="store_true",
                   help="no guarda nada; solo dice qué entraría")
    args = p.parse_args()

    if not args.archivo.is_file():
        print(f"No existe: {args.archivo}")
        return 1

    try:
        datos = json.loads(args.archivo.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"El archivo no es un JSON válido: {e}")
        return 1

    conexion = comprobar_conexion()
    print(f"Destino  : {conexion['motor']} {conexion.get('version', '')} "
          f"— {conexion['url']}")
    print(f"Archivo  : {args.archivo.name}, exportado "
          f"{datos.get('exportadoEn', '(sin fecha)')}")
    print(f"Trae     : {len(datos.get('recepciones') or [])} recepciones, "
          f"{len(datos.get('usuarios') or [])} usuarios")
    if args.ensayo:
        print("Modo     : ENSAYO (no se guarda nada)\n")
    print()

    init_db()
    db = SessionLocal()
    try:
        resumen = importar(db, datos)
        # importar() deja todo escrito pero sin confirmar. Aquí se decide.
        db.rollback() if args.ensayo else db.commit()
    except Exception as e:                       # noqa: BLE001
        db.rollback()
        print(f"No se importó nada: {e}")
        return 1
    finally:
        db.close()

    print("Entró:")
    print(resumen)

    if resumen.avisos:
        print("\nAvisos:")
        for a in resumen.avisos:
            print(f"  - {a}")

    if resumen.sin_pin:
        print(f"\n{len(resumen.sin_pin)} operarios entraron DESACTIVADOS y sin PIN.")
        print("Sus conteos conservan el autor, pero no pueden entrar hasta que les")
        print("des uno. Las contraseñas de Firebase no se pueden traer:")
        for u in resumen.sin_pin:
            print(f"  python scripts/crear_operador.py {u} \"{u}\" 1234 --rol OPERADOR")

    if args.ensayo:
        print("\nEra un ensayo: la base está como estaba.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
