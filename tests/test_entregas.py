"""Sin Google real: cierre atomico, instantaneas, permisos y recuperacion."""
import base64
import io
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import func, select

from app import config
from app.main import app
from app.models import AppEntrega, AppRecepcion, utcnow
from app.services import app_modelo as m, archivos, entregas


def preparar(cliente, db):
    codigo = 'ENTREGA-PRUEBA'
    m.crear_recepcion(db, {'codigo': codigo, 'cliente': 'PRUEBA'}, 'sup')
    m.guardar_packing_list(db, codigo, {'lineas': [{'linea': 1, 'sku': 'SKU1', 'cantidad': 3}],
        'porSku': {'SKU1': 3}, 'unidades': 3, 'hoja': 'PACKING',
        'columnas': {'sku': 0, 'cantidad': 1}, 'encabezados': ['SKU', 'CANTIDAD']}, 'LISTA')
    m.registrar_conteo(db, codigo, 'op1', {'id': 'conteo-1', 'sku': 'SKU1', 'cantidad': 3, 'pallet': 'A1'})
    libro = Workbook(); libro.active.append(['SKU', 'CANTIDAD']); libro.active.append(['SKU1', 3])
    bruto = io.BytesIO(); libro.save(bruto)
    datos = {'destinatarios': 'ejecutivo@example.test', 'carpetaMes': '2026-10',
        'carpetaRecepcion': 'PRUEBA', 'adjuntos': [{'nombre': 'informe', 'base64': base64.b64encode(bruto.getvalue()).decode()}],
        'eventos': [e['id'] for e in m.leer_coleccion(db, codigo, 'eventos')]}
    return codigo, datos


def test_cierre_archiva_y_encola_sin_google_y_se_puede_repetir(cliente, db, monkeypatch, tmp_path):
    monkeypatch.setattr(archivos, 'DATA_DIR', tmp_path)
    codigo, datos = preparar(cliente, db)
    r = cliente.post(f'/api/app/recepciones/{codigo}/entrega', json=datos)
    assert r.status_code == 201, r.text
    e = r.json()
    assert e['estado'] == 'PENDIENTE' and 'configurar' in e['mensaje']
    db.rollback(); db.expire_all()
    assert db.get(AppRecepcion, codigo).estado == 'CERRADA'
    guardada = db.get(AppEntrega, e['id'])
    assert guardada.datos['exportarSheet'] is False
    assert 'sheetId' not in guardada.datos
    assert guardada.datos['skus'][0]['contado'] == 3
    assert guardada.datos['lineas'][0]['cantidad'] == 3
    assert len(guardada.datos['eventos']) == 1
    assert list(tmp_path.glob('app_archivos/*'))
    assert cliente.post(f'/api/app/recepciones/{codigo}/entrega', json=datos).json()['id'] == e['id']
    assert db.scalar(select(func.count()).select_from(AppEntrega)) == 1
    op = TestClient(app); op.post('/api/auth/login', json={'usuario': 'op1', 'pin': '2222'})
    assert op.get('/api/app/entregas').status_code == 403
    assert cliente.get('/api/app/entregas').json()[0]['id'] == e['id']


def test_informe_invalido_o_conteos_posteriores_no_cierran(cliente, db, monkeypatch, tmp_path):
    monkeypatch.setattr(archivos, 'DATA_DIR', tmp_path)
    codigo, datos = preparar(cliente, db)
    roto = {**datos, 'adjuntos': [{'base64': base64.b64encode(b'invalido').decode()}]}
    assert cliente.post(f'/api/app/recepciones/{codigo}/entrega', json=roto).status_code == 422
    m.registrar_conteo(db, codigo, 'op2', {'id': 'conteo-2', 'sku': 'SKU1', 'cantidad': 1, 'pallet': 'A2', 'confirmarSobrante': True})
    r = cliente.post(f'/api/app/recepciones/{codigo}/entrega', json=datos)
    assert r.status_code == 409 and 'cambio' in r.text
    db.expire_all()
    assert db.get(AppRecepcion, codigo).estado != 'CERRADA'
    assert db.scalar(select(func.count()).select_from(AppEntrega)) == 0


def test_caida_google_reintento_y_revision_sin_reenviar_automaticamente(cliente, db, monkeypatch, tmp_path):
    monkeypatch.setattr(archivos, 'DATA_DIR', tmp_path)
    codigo, datos = preparar(cliente, db)
    ident = cliente.post(f'/api/app/recepciones/{codigo}/entrega', json=datos).json()['id']
    monkeypatch.setattr(config, 'VAL_GOOGLE_PROXY_URL', 'https://script.google.com/macros/s/prueba/exec')
    monkeypatch.setattr(config, 'VAL_GOOGLE_PROXY_SECRET', 's' * 40)
    llamadas = []
    def falla(*args):
        llamadas.append(args)
        raise OSError('red interrumpida')
    monkeypatch.setattr(entregas, 'llamar', falla)
    assert entregas.procesar_uno()
    db.rollback(); db.expire_all(); e = db.get(AppEntrega, ident)
    assert e.estado == 'PENDIENTE' and e.intentos == 1 and len(llamadas) == 1
    assert 'red interrumpida' not in e.error
    assert not entregas.procesar_uno()  # respeta espera entre intentos
    assert cliente.post(f'/api/app/entregas/{ident}/reintentar').status_code == 200
    def ambiguo(operacion, clave, payload):
        if operacion == 'estado': return {'exito': True, 'remitente': 'sup'}
        if operacion == 'archivo': return {'exito': True, 'fileId': 'file-test', 'tipoArchivo': 'informe'}
        raise entregas.RevisionEntrega('Confirmacion del correo interrumpida')
    monkeypatch.setattr(entregas, 'llamar', ambiguo)
    assert entregas.procesar_uno()
    db.rollback(); db.expire_all(); assert db.get(AppEntrega, ident).estado == 'REVISION'
    assert not entregas.procesar_uno()
    assert cliente.post(f'/api/app/entregas/{ident}/reintentar').status_code == 409


def test_arrendamiento_recupera_un_reinicio_y_finaliza(cliente, db, monkeypatch, tmp_path):
    monkeypatch.setattr(archivos, 'DATA_DIR', tmp_path)
    codigo, datos = preparar(cliente, db)
    ident = cliente.post(f'/api/app/recepciones/{codigo}/entrega', json=datos).json()['id']
    monkeypatch.setattr(config, 'VAL_GOOGLE_PROXY_URL', 'https://script.google.com/macros/s/prueba/exec')
    monkeypatch.setattr(config, 'VAL_GOOGLE_PROXY_SECRET', 's' * 40)
    db.rollback(); db.expire_all()
    e = db.get(AppEntrega, ident); e.estado = 'PROCESANDO'; e.proximo_en = utcnow() - timedelta(seconds=5); db.commit()
    llamadas = []
    def exito(operacion, clave, payload):
        llamadas.append((operacion, clave))
        return {'exito': True, 'remitente':'sup', 'fileId': 'file-test', 'tipoArchivo': 'informe', 'carpeta': 'https://drive.google.com/test', 'sheet': ''}
    monkeypatch.setattr(entregas, 'llamar', exito)
    assert entregas.procesar_uno()
    db.rollback(); db.expire_all(); e = db.get(AppEntrega, ident)
    assert e.estado == 'ENTREGADA' and e.resultado['exito']
    assert [op for op, _ in llamadas] == ['estado', 'archivo', 'finalizar']
    assert not entregas.procesar_uno()


def test_firma_solo_servidor_sin_exponer_el_secreto(db, monkeypatch):
    import hashlib, hmac, json
    capturado = {}
    class Cliente:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, json):
            capturado.update(json)
            class R:
                def raise_for_status(self): pass
                def json(self): return {'exito': True}
            return R()
    monkeypatch.setattr(config, 'VAL_GOOGLE_PROXY_SECRET', 'clave-test-' * 4)
    monkeypatch.setattr(entregas.httpx, 'Client', Cliente)
    entregas.llamar('archivo', 'a' * 32 + ':' + 'b' * 32, {'nombre': 'Validación.xlsx'})
    assert capturado['accion'] == 'entregaServidor'
    esperado = hmac.new(config.VAL_GOOGLE_PROXY_SECRET.encode(), capturado['payload'].encode(), hashlib.sha256).hexdigest()
    assert capturado['firma'] == esperado
    assert config.VAL_GOOGLE_PROXY_SECRET not in json.dumps(capturado)


def test_foto_confirmada_en_drive_deja_solo_referencia_mysql_y_url_autenticada(cliente, db, monkeypatch, tmp_path):
    from app.models import AppArchivo
    from tests.test_archivos_locales import PNG
    monkeypatch.setattr(archivos, 'DATA_DIR', tmp_path)
    codigo, datos = preparar(cliente, db)
    foto = cliente.post(f'/api/app/recepciones/{codigo}/archivos/foto', json={
        'sku': 'SKU1', 'base64': base64.b64encode(PNG).decode()}).json()
    assert (tmp_path / 'app_archivos' / foto['id']).is_file()
    ident = cliente.post(f'/api/app/recepciones/{codigo}/entrega', json=datos).json()['id']
    monkeypatch.setattr(config, 'VAL_GOOGLE_PROXY_URL', 'https://script.google.com/macros/s/prueba/exec')
    monkeypatch.setattr(config, 'VAL_GOOGLE_PROXY_SECRET', 's' * 40)
    def entregar(operacion, clave, payload):
        if operacion == 'estado': return {'exito': True, 'remitente': 'sup'}
        if operacion == 'archivo':
            return {'exito': True, 'fileId': 'drive-' + clave.split(':')[1], 'tipoArchivo': payload['tipoArchivo']}
        assert 'eventos' not in payload and 'lineas' not in payload
        assert payload['exportarSheet'] is False
        return {'exito': True, 'carpeta': 'https://drive.google.com/folders/prueba'}
    monkeypatch.setattr(entregas, 'llamar', entregar)
    assert entregas.procesar_uno()
    db.rollback(); db.expire_all()
    a = db.get(AppArchivo, foto['id'])
    assert a.drive_id == 'drive-' + foto['id']
    assert not archivos.ruta(a).exists()
    assert db.get(AppEntrega, ident).estado == 'ENTREGADA'
    res = cliente.get(foto['url'], follow_redirects=False)
    assert res.status_code == 307 and a.drive_id in res.headers['location']
    assert TestClient(app).get(foto['url'], follow_redirects=False).status_code == 401


def test_remitente_distinto_no_sube_archivos_ni_envia(cliente,db,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    codigo,datos=preparar(cliente,db)
    ident=cliente.post(f'/api/app/recepciones/{codigo}/entrega',json=datos).json()['id']
    monkeypatch.setattr(config,'VAL_GOOGLE_PROXY_URL','https://script.google.com/macros/s/test/exec')
    monkeypatch.setattr(config,'VAL_GOOGLE_PROXY_SECRET','s'*40)
    llamadas=[]
    def otro(op,clave,datos):
        llamadas.append(op);return {'exito':True,'remitente':'otra@gmail.com'}
    monkeypatch.setattr(entregas,'llamar',otro)
    assert entregas.procesar_uno()
    db.rollback();db.expire_all()
    assert db.get(AppEntrega,ident).estado=='PENDIENTE'
    assert llamadas==['estado']
    assert list(tmp_path.glob('app_archivos/*'))
