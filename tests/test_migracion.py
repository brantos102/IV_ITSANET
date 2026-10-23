"""La importación desde Firestore, contra una base de verdad (SQLite en memoria).

Lo que se comprueba no es que el código corra, es que no se pierda nada por el
camino y que volver a lanzarla no duplique: una migración que hay que hacer una
sola vez y bien es justo la que más falta le hace poder repetirse.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    Auditoria, EstadoFisico, EstadoRecepcion, Operador, PackingItem, Recepcion,
    Rol, ScanEvent, SkuPendiente, TipoEvento,
)
from app.security import verify_pin
from app.services.migracion import HASH_SIN_PIN, importar


@pytest.fixture()
def db():
    motor = create_engine("sqlite://", future=True)
    Base.metadata.create_all(motor)
    with sessionmaker(bind=motor, future=True)() as s:
        yield s


EXPORT = {
    "version": 1,
    "exportadoEn": "2026-10-14T12:00:00Z",
    "usuarios": [
        {"email": "bespinoza@itsanet.com", "usuario": "bespinoza",
         "nombre": "Bryan Espinoza", "rol": "ADMIN", "creadoEn": "2026-01-02T08:00:00Z"},
        {"email": "ana@itsanet.com", "nombre": "Ana Torres", "rol": "OPERADOR"},
    ],
    "recepciones": [{
        "id": "REC0260002", "codigo": "REC0260002", "cliente": "VENTURA",
        "descripcion": "Embarque RB48529", "estado": "CERRADA", "bultos": 12,
        "origenes": ["PL-A", "PL-B"],
        "creadoPorEmail": "bespinoza@itsanet.com",
        "creadoEn": "2026-03-01T13:00:00Z", "cerradoEn": "2026-03-01T19:30:00Z",
        "lineas": [
            {"linea": 1, "origen": "PL-A", "sku": "2H0525345", "descripcion": "ARANDELA",
             "cantidad": 30, "embarque": "RB48529", "cruda": ["1", "2H0525345", "30"]},
            {"linea": 1, "origen": "PL-B", "sku": "9XX111", "descripcion": "PIEZA",
             "cantidad": 7},
        ],
        "eventos": [
            {"id": "ev-1", "sku": "2H0525345", "cantidad": 12, "pallet": "A1",
             "posicionReal": "A-01-03-2", "origen": "PL-A", "estadoFisico": "BUENO",
             "tipo": "CONTEO", "operadorEmail": "ana@itsanet.com",
             "creadoEn": "2026-03-01T14:00:00Z"},
            {"id": "ev-2", "sku": "2H0525345", "cantidad": 18, "pallet": "B04",
             "origen": "PL-A", "estadoFisico": "PNC", "tipo": "CONTEO",
             "observacion": "caja mojada", "fotos": ["f1.jpg", "f2.jpg"],
             "operadorEmail": "ana@itsanet.com", "creadoEn": "2026-03-01T14:05:00Z"},
            {"id": "ev-3", "sku": "9XX111", "cantidad": 0, "pallet": "",
             "tipo": "CERO", "observacion": "no apareció",
             "operadorEmail": "nadie@itsanet.com", "creadoEn": "2026-03-01T15:00:00Z"},
        ],
        "adicionales": [
            {"sku": "SOBRA1", "descripcion": "NO ESTABA", "motivo": "llegó de más",
             "detectadoPorEmail": "ana@itsanet.com"},
        ],
        "auditoria": [
            {"accion": "CIERRE", "operadorEmail": "bespinoza@itsanet.com",
             "detalle": {"filas": 2, "exactitud": 100},
             "creadoEn": "2026-03-01T19:30:00Z"},
        ],
    }],
}


def test_entra_todo(db):
    r = importar(db, EXPORT)

    assert db.scalar(select(func.count()).select_from(Recepcion)) == 1
    assert db.scalar(select(func.count()).select_from(PackingItem)) == 2
    assert db.scalar(select(func.count()).select_from(ScanEvent)) == 3
    assert db.scalar(select(func.count()).select_from(SkuPendiente)) == 1
    assert db.scalar(select(func.count()).select_from(Auditoria)) == 1
    assert r.creado["conteos"] == 3


def test_dos_listas_con_la_misma_linea_1_no_se_pisan(db):
    """Una recepción consolidada trae dos listas, y cada una empieza por la 1."""
    importar(db, EXPORT)
    lineas = db.scalars(select(PackingItem).order_by(PackingItem.origen)).all()
    assert [(l.origen, l.linea, l.sku) for l in lineas] == [
        ("PL-A", 1, "2H0525345"), ("PL-B", 1, "9XX111")]


def test_el_total_contado_cuadra(db):
    """Las 30 unidades repartidas en dos sitios siguen sumando 30."""
    importar(db, EXPORT)
    total = db.scalar(select(func.sum(ScanEvent.cantidad))
                      .where(ScanEvent.sku == "2H0525345"))
    assert float(total) == 30.0


def test_no_se_pierde_donde_quedo_la_mercaderia(db):
    """La posición real no es el pallet: hacen falta las dos para cargar a Depot."""
    importar(db, EXPORT)
    ev = db.scalar(select(ScanEvent).where(ScanEvent.idempotency_key == "ev-1"))
    assert ev.pallet == "A1"
    assert ev.posicion_real == "A-01-03-2"
    assert ev.origen == "PL-A"


def test_el_pnc_queda_como_malo_con_sus_fotos(db):
    importar(db, EXPORT)
    ev = db.scalar(select(ScanEvent).where(ScanEvent.idempotency_key == "ev-2"))
    assert ev.estado_fisico is EstadoFisico.MALO
    assert ev.observacion == "caja mojada"
    assert json.loads(ev.fotos) == ["f1.jpg", "f2.jpg"]
    assert ev.foto == "f1.jpg"


def test_el_no_aparecio_es_un_conteo_de_cero(db):
    """«CERO» no es otra clase de evento: es haber buscado y no encontrar."""
    importar(db, EXPORT)
    ev = db.scalar(select(ScanEvent).where(ScanEvent.idempotency_key == "ev-3"))
    assert ev.tipo is TipoEvento.CONTEO
    assert float(ev.cantidad) == 0.0


def test_un_conteo_nunca_se_queda_sin_autor(db):
    """ev-3 lo firma un correo que no está en la lista de usuarios."""
    r = importar(db, EXPORT)
    ev = db.scalar(select(ScanEvent).where(ScanEvent.idempotency_key == "ev-3"))
    assert ev.operador_id is not None
    assert db.get(Operador, ev.operador_id).usuario == "nadie"
    assert any("nadie@itsanet.com" in a for a in r.avisos), r.avisos


def test_los_operarios_entran_sin_poder_entrar(db):
    """Las contraseñas no se pueden traer. Que quede explícito, no a medias."""
    r = importar(db, EXPORT)
    op = db.scalar(select(Operador).where(Operador.usuario == "bespinoza"))
    assert op.rol is Rol.ADMIN
    assert op.activo is False
    assert "bespinoza" in r.sin_pin


@pytest.mark.parametrize("intento", ["", "0000", "sin-pin-importado", HASH_SIN_PIN])
def test_el_pin_del_importado_no_lo_acierta_nadie(db, intento):
    """Ni siquiera quien conozca el centinela.

    Si aquí se guardara el hash de una palabra conocida, esa palabra seria una
    contrasena valida para todo el que se importe.
    """
    importar(db, EXPORT)
    op = db.scalar(select(Operador).where(Operador.usuario == "bespinoza"))
    assert verify_pin(intento, op.pin_hash) is False


def test_el_usuario_sale_del_correo_si_no_hay_alias(db):
    importar(db, EXPORT)
    assert db.scalar(select(Operador).where(Operador.usuario == "ana")) is not None


def test_la_recepcion_conserva_su_estado_y_sus_fechas(db):
    importar(db, EXPORT)
    rec = db.scalar(select(Recepcion))
    assert rec.estado is EstadoRecepcion.CERRADA
    assert rec.cerrado_en is not None
    assert rec.creado_en.tzinfo is None, "se guarda en UTC sin zona, como la columna"
    assert rec.archivo_origen == "PL-A, PL-B"


def test_la_fila_original_del_packing_list_se_conserva(db):
    """El informe final tiene que devolver el archivo igual que llegó."""
    importar(db, EXPORT)
    item = db.scalar(select(PackingItem).where(PackingItem.origen == "PL-A"))
    assert json.loads(item.extra) == ["1", "2H0525345", "30"]


def test_importar_dos_veces_no_duplica_nada(db):
    """Si se corta a mitad hay que poder relanzarla sin pensárselo."""
    importar(db, EXPORT)
    r2 = importar(db, EXPORT)

    assert db.scalar(select(func.count()).select_from(ScanEvent)) == 3
    assert db.scalar(select(func.count()).select_from(PackingItem)) == 2
    assert db.scalar(select(func.count()).select_from(Recepcion)) == 1
    assert db.scalar(select(func.count()).select_from(Operador)) == 3
    assert db.scalar(select(func.count()).select_from(Auditoria)) == 1
    assert r2.creado == {}, r2.creado


def test_una_observacion_larguisima_no_tumba_el_conteo(db):
    """Con MySQL en modo estricto, lo que no cabe rechaza la fila entera."""
    datos = json.loads(json.dumps(EXPORT))
    datos["recepciones"][0]["eventos"][0]["observacion"] = "x" * 900
    importar(db, datos)
    ev = db.scalar(select(ScanEvent).where(ScanEvent.idempotency_key == "ev-1"))
    assert len(ev.observacion) == 300


def test_un_archivo_de_otra_version_avisa_pero_no_se_planta(db):
    datos = json.loads(json.dumps(EXPORT))
    datos["version"] = 2
    r = importar(db, datos)
    assert any("versión" in a for a in r.avisos)
    assert db.scalar(select(func.count()).select_from(Recepcion)) == 1


def test_un_export_vacio_no_rompe(db):
    r = importar(db, {"version": 1})
    assert r.creado == {}


def test_importar_no_confirma_por_su_cuenta(db):
    """El script tiene un modo de ensayo, y para que signifique algo la decisión
    de confirmar o deshacer tiene que ser de quien llama."""
    importar(db, EXPORT)
    db.rollback()
    assert db.scalar(select(func.count()).select_from(Recepcion)) == 0
