#!/usr/bin/env python3
"""Crea las tablas y dice con qué base se está hablando de verdad.

    python scripts/preparar_base.py

Lo segundo importa tanto como lo primero: el fallo más caro de este paso no es
que falle, es que funcione contra el SQLite de pruebas mientras todo el mundo
cree que está escribiendo en MySQL. Por eso imprime el motor, la versión y el
juego de caracteres antes de tocar nada, y avisa si no es utf8mb4.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect  # noqa: E402

from app.db import comprobar_conexion, engine, init_db  # noqa: E402


def main() -> int:
    try:
        datos = comprobar_conexion()
    except Exception as e:                       # noqa: BLE001
        print(f"No se pudo conectar: {e}\n")
        print("Revisa VAL_DATABASE_URL. Para MySQL:")
        print("  mysql+pymysql://val:CLAVE@127.0.0.1:3306/val_ventura?charset=utf8mb4")
        return 1

    print(f"Motor    : {datos['motor']} {datos.get('version', '')}")
    print(f"Destino  : {datos['url']}")

    if datos["motor"] in ("mysql", "mariadb"):
        print(f"Juego    : {datos.get('charset')} / {datos.get('collation')}")
        if datos.get("charset") != "utf8mb4":
            print("\n  AVISO: la base no está en utf8mb4. Las tildes y las eñes se")
            print("  guardarán rotas. Córrelo así y vuelve a intentarlo:")
            print("    ALTER DATABASE val_ventura CHARACTER SET utf8mb4 "
                  "COLLATE utf8mb4_unicode_ci;")
            return 1
    else:
        print("\n  AVISO: esto NO es MySQL. Si creías que sí, para aquí: la")
        print("  aplicación escribiría en otro sitio. Define VAL_DATABASE_URL.")

    antes = set(inspect(engine).get_table_names())
    init_db()
    despues = set(inspect(engine).get_table_names())

    nuevas = sorted(despues - antes)
    print(f"\nTablas   : {len(despues)}"
          + (f" ({len(nuevas)} creadas: {', '.join(nuevas)})" if nuevas else " (ya estaban)"))
    print("\nListo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
