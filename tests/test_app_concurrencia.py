"""El agregado que leen los handhelds debe cuadrar con todos los eventos."""
import threading
import time

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import AppEvento, AppRecepcion, AppSku
from app.services import app_modelo as m


def test_operarios_simultaneos_conservan_eventos_y_totales(db, monkeypatch):
    codigo = 'PRUEBA-CONCURRENTE-APP'
    m.crear_recepcion(db, {'codigo': codigo}, 'supervisor')
    m.guardar_packing_list(db, codigo, {
        'lineas': [{'linea': 1, 'sku': 'SKU1', 'cantidad': 80}],
        'porSku': {'SKU1': 80}, 'unidades': 80,
    })
    aplicar = m._aplicar_al_sku

    def con_otros_operarios(s, datos, usuario):
        time.sleep(0.002)
        aplicar(s, datos, usuario)

    monkeypatch.setattr(m, '_aplicar_al_sku', con_otros_operarios)
    barrera = threading.Barrier(4)
    errores = []

    def operar(numero):
        with SessionLocal() as sesion:
            # Como la comprobacion de sesion HTTP: una lectura anterior al
            # bloqueo no debe dejar una instantanea antigua en MySQL.
            sesion.scalar(select(func.count()).select_from(AppRecepcion))
            barrera.wait(timeout=10)
            for i in range(20):
                try:
                    m.registrar_conteo(sesion, codigo, f'operario{numero}', {
                        'sku': 'SKU1', 'cantidad': 1, 'pallet': f'A{numero + 1}',
                        'origen': 'PRINCIPAL', 'idempotencyKey': f'paralelo-{numero}-{i}',
                    })
                except Exception as exc:
                    sesion.rollback()
                    errores.append(exc)

    hilos = [threading.Thread(target=operar, args=(i,)) for i in range(4)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)
    assert not any(h.is_alive() for h in hilos)
    assert not errores, errores[:3]
    with SessionLocal() as s:
        sku = s.scalar(select(AppSku).where(AppSku.recepcion == codigo))
        assert s.scalar(select(func.count()).select_from(AppEvento).where(AppEvento.recepcion == codigo)) == 80
        assert s.scalar(select(func.sum(AppEvento.cantidad)).where(AppEvento.recepcion == codigo)) == 80
        assert sku.contado == 80
        assert sku.pallets == {'A1': 20, 'A2': 20, 'A3': 20, 'A4': 20}
