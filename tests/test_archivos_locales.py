import base64
import hashlib
import io

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import func, select

from app.main import app
from app.models import AppArchivo, Operador, Rol
from app.security import hash_pin
from app.services import archivos

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jMZkAAAAASUVORK5CYII=')


def crear(cliente):
    r = cliente.post('/api/app/recepciones', json={'codigo': 'PRUEBA-LOCAL'})
    assert r.status_code == 201, r.text


def test_foto_local_autenticada_repetible_sin_firebase(cliente, db, monkeypatch, tmp_path):
    monkeypatch.setattr(archivos, 'DATA_DIR', tmp_path)
    crear(cliente)
    payload = {'base64': base64.b64encode(PNG).decode(), 'nombre': '../../foto.png'}
    r = cliente.post('/api/app/recepciones/PRUEBA-LOCAL/archivos/foto', json=payload)
    assert r.status_code == 201, r.text
    foto = r.json()
    assert foto['nombre'] == 'foto.png'
    assert foto['sha256'] == hashlib.sha256(PNG).hexdigest()
    assert TestClient(app).get(foto['url']).status_code == 401
    res = cliente.get(foto['url'])
    assert res.status_code == 200 and res.content == PNG
    assert res.headers['cache-control'] == 'private, no-store'
    assert res.headers['content-type'] == 'image/png'
    repetida = cliente.post('/api/app/recepciones/PRUEBA-LOCAL/archivos/foto', json=payload)
    assert repetida.json()['id'] == foto['id']
    assert db.scalar(select(func.count()).select_from(AppArchivo)) == 1


def test_informe_xlsx_se_conserva_y_no_lo_sube_un_operario(cliente, operadores, db, monkeypatch, tmp_path):
    monkeypatch.setattr(archivos, 'DATA_DIR', tmp_path)
    crear(cliente)
    libro = Workbook(); libro.active.append(['ITEM', 'CANTIDAD']); libro.active.append(['SKU1', 3])
    salida = io.BytesIO(); libro.save(salida)
    datos = {'base64': base64.b64encode(salida.getvalue()).decode(), 'nombre': 'informe.xlsx'}
    op = TestClient(app)
    op.post('/api/auth/login', json={'usuario': 'op1', 'pin': '2222'})
    ruta = '/api/app/recepciones/PRUEBA-LOCAL/archivos/informe'
    assert op.post(ruta, json=datos).status_code == 403
    r = cliente.post(ruta, json=datos)
    assert r.status_code == 201, r.text
    assert cliente.get(r.json()['url']).content == salida.getvalue()
    assert cliente.post(ruta, json={'base64': base64.b64encode(b'no es un excel').decode()}).status_code == 422


def test_archivos_invalidos_y_sin_recepcion_no_se_guardan(cliente, monkeypatch, tmp_path):
    monkeypatch.setattr(archivos, 'DATA_DIR', tmp_path)
    crear(cliente)
    ruta = '/api/app/recepciones/PRUEBA-LOCAL/archivos/foto'
    assert cliente.post(ruta, json={'base64': 'no/base64!!'}).status_code == 422
    assert cliente.post(ruta, json={'base64': base64.b64encode(b'<html>no es foto</html>').decode()}).status_code == 422
    assert cliente.post('/api/app/recepciones/NO-EXISTE/archivos/foto', json={'base64': base64.b64encode(PNG).decode()}).status_code == 404
    assert not list(tmp_path.glob('app_archivos/*'))


def test_csv_local_permiso_admin_y_estado_sin_credenciales(cliente, db):
    datos = {'formatos': [{'id': 'CANTIDADES', 'columnas': [{'encabezado': 'SKU', 'campo': 'sku'}]}]}
    assert cliente.put('/api/app/config/csv', json=datos).status_code == 403
    db.add(Operador(usuario='jefe', nombre='Jefe', rol=Rol.ADMIN, pin_hash=hash_pin('prueba123')))
    db.commit()
    admin = TestClient(app)
    admin.post('/api/auth/login', json={'usuario': 'jefe', 'pin': 'prueba123'})
    assert admin.put('/api/app/config/csv', json=datos).status_code == 200
    assert cliente.get('/api/app/config/csv').json() == datos
    estado = cliente.get('/api/app/estado').json()
    assert estado['destino'] == 'servidor'
    assert estado['firebase_requerido'] is False
    assert 'url' not in estado and 'password' not in estado


def test_fotos_por_item_sin_conteo_y_una_copia_para_varios_items(cliente, db, monkeypatch, tmp_path):
    from app.models import AppArchivoSku, AppEvento, AppRecepcion, AppEntrega
    from uuid import uuid4
    monkeypatch.setattr(archivos, 'DATA_DIR', tmp_path)
    crear(cliente)
    ruta = '/api/app/recepciones/PRUEBA-LOCAL/archivos/foto'
    for sku in ['SKU1', 'SKU2']:
        r = cliente.post(ruta, json={'base64': base64.b64encode(PNG).decode(), 'sku': sku})
        assert r.status_code == 201, r.text
    ident = r.json()['id']
    assert db.query(AppArchivo).count() == 1 and db.query(AppArchivoSku).count() == 2
    assert db.query(AppEvento).filter(AppEvento.tipo == 'CONTEO').count() == 0
    assert db.query(AppEvento).filter(AppEvento.tipo == 'AUDITORIA').count() == 2
    galeria = '/api/app/recepciones/PRUEBA-LOCAL/imagenes'
    for sku in ['SKU1', 'SKU2']:
        r = cliente.get(galeria, params={'sku': sku})
        assert r.status_code == 200
        assert r.json()['total'] == 1
        assert r.json()['archivos'][0]['almacen'] == 'SERVIDOR'
        assert set(r.json()['archivos'][0]['skus']) == {'SKU1', 'SKU2'}
        assert 'rutaServidor' not in r.text
    assert cliente.get(galeria, params={'sku': 'OTRO'}).json()['total'] == 0
    assert TestClient(app).get(galeria).status_code == 401
    db.add(Operador(usuario='admin-fotos',nombre='Admin',rol=Rol.ADMIN,pin_hash=hash_pin('1111')));db.commit()
    admin=TestClient(app);admin.post('/api/auth/login',json={'usuario':'admin-fotos','pin':'1111'})
    assert admin.get(galeria).json()['archivos'][0]['rutaServidor'] == str(tmp_path / 'app_archivos' / ident)
    db.expire_all();a=db.get(AppArchivo,ident);a.drive_id='archivo-drive';a.drive_url='https://drive.google.com/file/d/archivo-drive/view'
    db.add(AppEntrega(id=uuid4().hex,clave=uuid4().hex,recepcion='PRUEBA-LOCAL',usuario='sup',datos={},estado='ENTREGADA',
        resultado={'carpeta':'https://drive.google.com/folders/recepcion','carpetaFotos':'https://drive.google.com/folders/imagenes'}))
    db.get(AppRecepcion,'PRUEBA-LOCAL').estado='CERRADA';db.commit()
    archivos.ruta(a).unlink()
    r=cliente.get(galeria).json()
    assert r['carpetaDrive']=='https://drive.google.com/folders/imagenes'
    assert r['archivos'][0]['almacen']=='DRIVE' and r['archivos'][0]['driveUrl']==a.drive_url
    assert cliente.get('/api/app/archivos/'+ident,follow_redirects=False).status_code==307
    assert cliente.post(ruta,json={'base64':base64.b64encode(PNG).decode(),'sku':'SKU1'}).status_code==409


def test_entrada_principal_abre_la_app_operativa():
    r = TestClient(app).get('/', follow_redirects=False)
    assert r.status_code == 302 and r.headers['location'] == '/app/'
