"""Contrato Drive: generateIds distingue files de shortcuts.

Referencia: googleapis/google-api-go-client, drive/v3/drive-api.json,
files.generateIds.parameters.type: valores files (predeterminado) y shortcuts.
"""
import hashlib

import httpx
from app.models import AppArchivo, AppConfig, AppCopiaDrive
from app.services import google_drive_api as d, google_cuentas as g


def api_simulada(monkeypatch, existentes=None, perder=False):
    remotos = dict(existentes or {})
    generados, posts, subidas = [], [], []
    def api(cuenta, servicio, metodo, ruta, **kw):
        if ruta == 'files/generateIds':
            tipo = kw['params'].get('type', 'files')
            ident = tipo.upper() + str(len(generados))
            generados.append((tipo, ident))
            return httpx.Response(200, json={'ids': [ident]})
        if servicio == 'upload':
            subidas.append(kw)
            raise AssertionError('Organizar una foto existente no debe volver a subir su contenido')
        if metodo == 'GET' and ruta == 'files':
            return httpx.Response(200, json={'files': [v for v in remotos.values()
                if v.get('mimeType') == d.ATAJO]})
        if metodo == 'GET':
            ident = ruta.split('/')[-1]
            if ident not in remotos:
                raise RuntimeError('GOOGLE_NO_ENCONTRADO: HTTP 404')
            return httpx.Response(200, json=remotos[ident])
        if metodo == 'POST':
            f = kw['json']
            posts.append(f)
            if f.get('mimeType') == d.ATAJO and not f['id'].startswith('SHORTCUTS'):
                raise RuntimeError('GOOGLE_RED: HTTP 400; ID de tipo incorrecto')
            remotos[f['id']] = f
            if perder:
                raise RuntimeError('GOOGLE_RED: respuesta perdida después de crear')
            return httpx.Response(200, json=f)
        if metodo == 'PATCH':
            ident = ruta.split('/')[-1]
            remotos[ident].update(kw['json'])
            return httpx.Response(200, json=remotos[ident])
        raise AssertionError((servicio, metodo, ruta))
    monkeypatch.setattr(g, 'peticion', api)
    return remotos, generados, posts, subidas


def test_atajo_usa_tipo_correcto_y_reserva_reutilizable_con_respuesta_perdida(db, monkeypatch):
    remotos, generados, posts, _ = api_simulada(monkeypatch, perder=True)
    for _ in range(2):
        d.atajo('drive@example.test', 'PADRE123', 'FOTO123', 'Foto.jpg', 'huella')
    assert generados == [('shortcuts', 'SHORTCUTS0')]
    assert len(posts) == 1 and posts[0]['shortcutDetails']['targetId'] == 'FOTO123'
    assert remotos['SHORTCUTS0']['parents'] == ['PADRE123']


def test_reserva_antigua_incompatible_no_cambia_identidad_del_original(db, monkeypatch):
    cuenta, padre, archivo = 'drive@example.test', 'PADRE123', 'FOTO123'
    vieja = 'gd:' + hashlib.sha256((cuenta + '|atajo:' + padre + '/' + archivo).encode()).hexdigest()[:32]
    db.add(AppConfig(clave=vieja, usuario=cuenta, datos={'id': 'FILES_ANTIGUO'}))
    db.commit()
    _, generados, posts, _ = api_simulada(monkeypatch)
    d.atajo(cuenta, padre, archivo, 'Foto.jpg', 'huella')
    db.expire_all()
    assert db.get(AppConfig, vieja).datos == {'id': 'FILES_ANTIGUO'}
    assert generados[0][0] == 'shortcuts' and posts[0]['shortcutDetails']['targetId'] == archivo


def test_adopta_atajo_existente_sin_crear_otro(db, monkeypatch):
    f = {'id': 'ATAJO_EXISTENTE', 'mimeType': d.ATAJO, 'parents': ['PADRE123'],
         'shortcutDetails': {'targetId': 'FOTO123'}}
    _, generados, posts, _ = api_simulada(monkeypatch, {f['id']: f})
    d.atajo('drive@example.test', 'PADRE123', 'FOTO123', 'Foto.jpg', 'huella')
    assert not generados and not posts


def test_organizar_archivo_remoto_no_necesita_original_local_ni_duplica_foto(db, monkeypatch):
    original = {'id': 'FOTO123', 'mimeType': 'image/jpeg', 'parents': ['PRIMARIA123'],
                'appProperties': {}}
    remotos, generados, posts, subidas = api_simulada(monkeypatch, {'FOTO123': original})
    monkeypatch.setattr(d, 'recepcion', lambda *a: 'RECEPCION123')
    monkeypatch.setattr(d, 'ruta', lambda cuenta, raiz, partes, **kw: partes[-1])
    p = {'tipoArchivo': 'foto', 'fileId': 'FOTO123', 'nombre': 'Foto.jpg',
         'recepcion': 'RECEP123', 'ruta': ['PRIMARIA123'], 'rutasVinculadas': [
             {'ruta': ['SECUNDARIA123'], 'categoria': 'GENERAL', 'evidenciaId': 'EVIDENCIA123'}]}
    for _ in range(2):
        r = d.subir('drive@example.test', 'archivo:archivo', p)
        assert r['fileId'] == 'FOTO123'
    assert not subidas and len(posts) == 1 and generados[0][0] == 'shortcuts'
    assert len([f for f in remotos.values() if f.get('mimeType') == 'image/jpeg']) == 1


def test_conserva_original_local_si_debe_terminar_organizacion(cliente, db, monkeypatch, tmp_path):
    from app import config
    from app.services import archivos, drive, entregas
    from tests.test_cierre_guiado import preparar
    from tests.test_operacion_desarrollo import foto
    monkeypatch.setattr(config, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(archivos, 'DATA_DIR', tmp_path)
    preparar(db)
    f = foto(cliente, 'CIERRE', sku='SKU1').json()
    ident = f['id']
    monkeypatch.setattr(entregas, 'configurado', lambda *a: True)
    monkeypatch.setattr(drive, 'verificar_puente', lambda *a: None)
    real = drive.descripcion
    lecturas = []
    def descripcion(*a, **kw):
        p = real(*a, **kw)
        lecturas.append(p)
        if len(lecturas) > 1:
            p['rutasVinculadas'] = [*p.get('rutasVinculadas', []), {'ruta': ['OTRA123']}]
        return p
    monkeypatch.setattr(drive, 'descripcion', descripcion)
    monkeypatch.setattr(entregas, 'llamar', lambda *a: {'fileId': 'FOTO123'})
    assert drive.procesar_uno()
    db.rollback(); db.expire_all()
    tarea = db.get(AppCopiaDrive, ident)
    assert tarea.estado == 'PENDIENTE' and tarea.datos['accion'] == 'ubicar'
    assert db.get(AppArchivo, ident).drive_id == 'FOTO123'
    assert (tmp_path / 'app_archivos' / ident).is_file()
