"""El supervisor identifica fotos pendientes y reintenta sin duplicar ni cerrar."""
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import AppArchivo, AppCopiaDrive, AppEntrega, AppEvento, AppEvidencia, utcnow
from app.services import archivos, drive, entregas, app_modelo as m
from tests.test_operacion_desarrollo import foto


def preparar(db, codigo='CIERRE'):
    m.crear_recepcion(db, {'codigo': codigo, 'cliente': 'VENTURA'}, 'sup')
    m.guardar_packing_list(db, codigo, {
        'lineas': [{'linea': 1, 'sku': 'SKU1', 'cantidad': 1}], 'porSku': {'SKU1': 1},
        'unidades': 1, 'encabezados': ['SKU', 'CANTIDAD', 'EVIDENCIA'],
        'columnas': {'sku': 0, 'cantidad': 1, 'evidencia': 2}}, 'PL')
    return '/api/operacion/recepciones/' + codigo


def test_identifica_foto_sku_tipo_bulto_sin_exponer_errores_tecnicos(cliente, db, monkeypatch, tmp_path):
    monkeypatch.setattr(archivos, 'DATA_DIR', tmp_path)
    ruta = preparar(db)
    unidad = cliente.post(ruta + '/bultos', json={'cantidad': 1}).json()['unidades'][0]
    f = foto(cliente, 'CIERRE', sku='SKU1', unidadId=unidad['id'], origen='PL',
        tipoEvidencia='CAJA_ABIERTA', categoria='PNC').json()
    db.rollback(); db.expire_all()
    j = db.get(AppCopiaDrive, f['id']); j.error = 'HMAC secreto y URL de infraestructura'; db.commit()
    # Un vínculo adicional no debe contar dos veces la misma foto física.
    db.add(AppEvidencia(id='vinculo-extra', archivo_id=f['id'], recepcion='CIERRE',
        sku='SKU2', categoria='PNC', tipo='ITEM_NOVEDAD', protocolo='GENERAL', usuario='sup'))
    db.commit()
    r = cliente.get(ruta + '/pendientes-cierre')
    assert r.status_code == 200, r.text
    d = r.json(); assert d['total'] == 1 and d['bloqueaCierre'] and d['requierenAyuda'] == 1
    assert cliente.get(ruta.lower() + '/pendientes-cierre').json()['total'] == 1
    a = d['archivos'][0]
    assert a['archivoId'] == f['id'] and a['nombre'] == f['nombre']
    assert {v['sku'] for v in a['vinculos']} == {'SKU1', 'SKU2'}
    assert any(v['tipo'] == 'CAJA_ABIERTA' and 'BULTO 1' in v['unidad'] for v in a['vinculos'])
    assert 'HMAC' not in r.text and 'infraestructura' not in r.text
    final = cliente.post(ruta + '/informes', json={'clave': 'cierre-pendiente', 'tipo': 'CORREO'})
    assert final.status_code == 409
    assert final.json()['detail']['codigo'] == 'EVIDENCIAS_PENDIENTES'
    assert final.json()['detail']['pendientes'] == 1
    assert cliente.post(ruta + '/informes', json={'clave': 'avance-permitido', 'tipo': 'DESCARGA'}).status_code == 200


def test_no_solicita_fotos_nuevas_ni_incluye_retiradas_o_confirmadas(cliente, db, monkeypatch, tmp_path):
    monkeypatch.setattr(archivos, 'DATA_DIR', tmp_path)
    ruta = preparar(db)
    confirmada = foto(cliente, 'CIERRE', sku='SKU1', variante=1).json()
    retirada = foto(cliente, 'CIERRE', sku='SKU1', variante=2).json()
    foto(cliente, 'CIERRE', variante=3)  # General: no impide generar columna de SKU.
    assert cliente.delete('/api/operacion/evidencias/' + retirada['id']).status_code == 200
    db.rollback(); db.expire_all()
    j = db.get(AppCopiaDrive, confirmada['id'])
    j.estado = 'COPIADA'; j.datos = {**j.datos, 'carpetaSkuUrl': 'https://drive.google.com/drive/folders/sku'}
    db.commit()
    d = cliente.get(ruta + '/pendientes-cierre').json()
    assert d['total'] == 0 and d['archivos'] == [] and not d['bloqueaCierre']
    assert cliente.post(ruta + '/informes', json={'clave': 'final-confirmado', 'tipo': 'CORREO'}).status_code == 200


def test_reintento_reusa_cola_no_invade_otra_recepcion_ni_reservas_activas(cliente, db, monkeypatch, tmp_path):
    monkeypatch.setattr(archivos, 'DATA_DIR', tmp_path)
    ruta = preparar(db); preparar(db, 'OTRA')
    pendiente = foto(cliente, 'CIERRE', sku='SKU1', variante=1).json()
    activa = foto(cliente, 'CIERRE', sku='SKU1', variante=2).json()
    sincola = foto(cliente, 'CIERRE', sku='SKU1', variante=3).json()
    otra = foto(cliente, 'OTRA', sku='SKU1', variante=1).json()
    db.rollback(); db.expire_all()
    despues = utcnow().replace(microsecond=0) + timedelta(hours=1)
    db.get(AppCopiaDrive, pendiente['id']).proximo_en = despues
    j = db.get(AppCopiaDrive, activa['id']); j.estado = 'PROCESANDO'; j.proximo_en = despues
    db.get(AppCopiaDrive, otra['id']).proximo_en = despues
    db.delete(db.get(AppCopiaDrive, sincola['id'])); db.commit()
    for _ in range(2):
        r = cliente.post(ruta + '/drive/reintentar', json={})
        assert r.status_code == 200 and r.json()['programadas'] == 2, r.text
    db.rollback(); db.expire_all()
    assert len(list(db.scalars(select(AppArchivo)))) == 4
    assert len(list(db.scalars(select(AppCopiaDrive)))) == 4
    assert db.get(AppCopiaDrive, activa['id']).estado == 'PROCESANDO'
    assert db.get(AppCopiaDrive, activa['id']).proximo_en.replace(tzinfo=None) == despues.replace(tzinfo=None)
    assert db.get(AppCopiaDrive, otra['id']).proximo_en.replace(tzinfo=None) == despues.replace(tzinfo=None)
    assert db.get(AppCopiaDrive, pendiente['id']).proximo_en.replace(tzinfo=None) < despues.replace(tzinfo=None)
    assert not list(db.scalars(select(AppEntrega)))
    assert not list(db.scalars(select(AppEvento).where(AppEvento.tipo == 'CIERRE')))


def test_reintento_termina_en_drive_y_habilita_cierre_sin_enviar_correo(cliente, db, monkeypatch, tmp_path):
    monkeypatch.setattr(archivos, 'DATA_DIR', tmp_path); drive._verificados.clear()
    ruta = preparar(db); f = foto(cliente, 'CIERRE', sku='SKU1').json()
    monkeypatch.setattr(entregas, 'configurado', lambda *a: True)
    acciones = []
    def puente(accion, clave, datos):
        acciones.append(accion)
        if accion == 'estado': return {'versionPuente': 2, 'remitente': 'sup'}
        return {'fileId': 'foto-confirmada', 'carpetaSkuUrl': 'https://drive.google.com/drive/folders/sku'}
    monkeypatch.setattr(entregas, 'llamar', puente)
    assert cliente.post(ruta + '/drive/reintentar', json={}).status_code == 200
    assert drive.procesar_uno()
    assert cliente.get(ruta + '/pendientes-cierre').json()['total'] == 0
    assert cliente.post(ruta + '/informes', json={'clave': 'listo-para-cierre', 'tipo': 'CORREO'}).status_code == 200
    assert acciones == ['estado', 'archivo']
    assert not (tmp_path / 'app_archivos' / f['id']).exists()


def test_permisos_y_paginacion_del_cierre(cliente, db, monkeypatch, tmp_path):
    monkeypatch.setattr(archivos, 'DATA_DIR', tmp_path); ruta = preparar(db)
    for i in range(3): foto(cliente, 'CIERRE', sku='SKU1', variante=i)
    d = cliente.get(ruta + '/pendientes-cierre?offset=1&limite=1').json()
    assert d['total'] == 3 and len(d['archivos']) == 1 and d['hayMas']
    assert cliente.get(ruta + '/pendientes-cierre?limite=101').status_code == 422
    anon = TestClient(app); op = TestClient(app)
    op.post('/api/auth/login', json={'usuario': 'op1', 'pin': '2222'})
    for c, estado in [(anon, 401), (op, 403)]:
        assert c.get(ruta + '/pendientes-cierre').status_code == estado
        assert c.post(ruta + '/drive/reintentar', json={}).status_code == estado
