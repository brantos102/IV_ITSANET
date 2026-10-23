"""Históricos intactos; ni reutilización ni correo usan el formato anterior."""
from uuid import uuid4
import pytest
from app.models import AppEvento, AppInforme
from app.services import informes, app_modelo as m
from sqlalchemy import select
from tests.test_adjuntos_independientes_65 import generar, cuenta_correo


@pytest.mark.parametrize('formato', ['envio', 'envio-ampliado', 'auditable'])
def test_revision_65_no_se_reutiliza_y_se_conserva_historica(cliente, db, cuenta_correo, monkeypatch, formato):
    codigo, _ = cuenta_correo
    with monkeypatch.context() as contexto:
        contexto.setattr(informes, 'REVISION_FORMATO', 65)
        anterior = generar(cliente, codigo, formato)
    db.rollback()
    eventos = list(db.scalars(select(AppEvento.id).where(AppEvento.recepcion == codigo)))
    ruta = '/api/operacion/recepciones/' + codigo
    assert not cliente.get(ruta + '/informe-actual?formato=' + formato).json()['actual']
    r = cliente.post(ruta + '/informes', json={'clave': uuid4().hex, 'tipo': 'DESCARGA', 'formato': formato,
        'ultimoVisto': anterior['id'], 'reutilizarId': anterior['id']})
    assert r.status_code == 409
    assert cliente.get('/api/operacion/informes/' + anterior['id'] + '/descarga').status_code == 200
    nuevo = generar(cliente, codigo, formato)
    assert nuevo['numero'] == anterior['numero'] + 1
    assert cliente.get(ruta + '/informe-actual?formato=' + formato).json()['informe']['id'] == nuevo['id']
    db.rollback()
    assert list(db.scalars(select(AppEvento.id).where(AppEvento.recepcion == codigo))) == eventos
    assert db.get(AppInforme, anterior['id']).estado == 'GENERADO'
    assert db.get(AppInforme, anterior['id']).datos['archivos'] == anterior['archivos']
    assert db.get(AppInforme, anterior['id']).datos['huellaContenido'] != informes.huella_contenido(db, m.obtener(db, codigo))
