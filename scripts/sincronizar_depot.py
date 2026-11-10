#!/usr/bin/env python3
"""Baja el maestro de productos desde Depot al espejo local.

    cd ~/bryan/IV_ITSANET
    .venv/bin/python scripts/sincronizar_depot.py            # todos los clientes
    .venv/bin/python scripts/sincronizar_depot.py --cliente VENTURA
    .venv/bin/python scripts/sincronizar_depot.py --probar    # solo las credenciales

Pensado para dos sitios: la mano, al instalar, y el cron de la madrugada. Un
catálogo que solo se actualizaba subiendo un Excel a mano se queda viejo el día
que la persona que lo subía está de vacaciones.

Para dejarlo automático, una vez al día a las 5:40:

    crontab -e
    40 5 * * * cd /home/bryan/IV_ITSANET && \
      set -a && . /etc/iv-itsanet.env && set +a && \
      .venv/bin/python scripts/sincronizar_depot.py >> /tmp/depot.log 2>&1

Las credenciales NO van en la línea del cron: se leen de /etc/iv-itsanet.env,
que solo puede leer root, igual que el servicio.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal, comprobar_conexion            # noqa: E402
from app.services import depot as svc                          # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cliente", help="solo este cliente (COD. CLIENTE del WMS)")
    p.add_argument("--probar", action="store_true",
                   help="pide el token y sale: no baja el inventario")
    args = p.parse_args()

    api = svc.DepotAPI()
    print(f"Depot : {api.base_url or '(sin DEPOT_BASE_URL)'}")
    print(f"Usuario: {api.usuario or '(sin DEPOT_USUARIO)'}")
    print(f"Clave : {'puesta' if api.clave else '(sin DEPOT_CLAVE)'}")

    if not api.configurada:
        print()
        print("  ✗ Faltan credenciales. Van en /etc/iv-itsanet.env:")
        print('      DEPOT_BASE_URL=https://ec.itsanet.com/q_apidepot')
        print('      DEPOT_USUARIO=...')
        print('      DEPOT_CLAVE=...')
        print("    y después: sudo systemctl restart iv-itsanet")
        return 2

    try:
        api.token(forzar=True)
        print("  ✓ token obtenido")
    except svc.DepotRechazado as exc:
        print(f"  ✗ el WMS rechazó las credenciales: {exc}")
        return 3
    except svc.DepotNoDisponible as exc:
        print(f"  ✗ el WMS no contesta: {exc}")
        return 4

    if args.probar:
        return 0

    try:
        base = comprobar_conexion()
        print(f"  ✓ base {base['motor']} {base.get('version', '')} en {base['url']}")
    except Exception as exc:                     # noqa: BLE001 - se informa y se sale
        print(f"  ✗ sin base de datos: {exc}")
        return 5

    with SessionLocal() as db:
        try:
            res = svc.sincronizar_maestro(db, api=api, cliente=args.cliente)
        except (svc.DepotNoDisponible, svc.DepotRechazado) as exc:
            print(f"  ✗ {exc}")
            return 6

    print()
    print(f"  filas de stock recibidas : {res['filas_recibidas']}")
    print(f"  productos en el espejo   : {res['productos']}")
    print("  por cliente:")
    for c, n in res["por_cliente"].items():
        print(f"    {c:<20} {n}")
    print()
    print("  Revisa la lista de clientes: si falta uno que esperabas, o sobra")
    print("  uno que no, la credencial no es la que se creía.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
