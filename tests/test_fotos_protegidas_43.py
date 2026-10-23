"""Panorámicas sin bulto y confirmación de imágenes durables y de su autor."""
import base64
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import AppArchivo, AppEvidencia, AppCopiaDrive
from app.services import archivos
from tests.test_archivos_locales import PNG
from tests.test_operacion_desarrollo import rec


def payload(**datos):
    return {'nombre':'panoramica.png','tipo':'image/png','tipoEvidencia':'PANORAMICA',
        'categoria':'RECEPCION','base64':base64.b64encode(PNG).decode(),**datos}


def test_panoramica_anterior_al_primer_bulto_no_crea_unidad_y_pasa_a_packing(cliente,db):
    codigo=rec(cliente);ruta=f'/api/operacion/recepciones/{codigo}'
    inicial=cliente.put(ruta+'/ingreso',json={'marca':'PRUEBA','protocolo':'REGLAMENTARIO','version':0})
    assert inicial.status_code==200 and inicial.json()['unidades']==[],inicial.text
    r=cliente.post(f'/api/app/recepciones/{codigo}/archivos/foto',json=payload())
    assert r.status_code==201,r.text
    db.rollback();e=db.query(AppEvidencia).one()
    assert e.tipo=='PANORAMICA' and e.unidad_id is None and e.categoria=='RECEPCION'
    actual=cliente.get(ruta+'/ingreso').json();assert actual['unidades']==[]
    r=cliente.put(ruta+'/ingreso',json={'paso':'PACKING','version':actual['version']})
    assert r.status_code==200 and r.json()['paso']=='PACKING' and r.json()['protocolo']=='REGLAMENTARIO'


def test_foto_pendiente_no_se_registra_con_sesion_de_otro_usuario(cliente,db,operadores):
    codigo=rec(cliente)
    op=TestClient(app);op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    r=op.post(f'/api/app/recepciones/{codigo}/archivos/foto',json=payload(operadorOrigen=operadores['sup'].id))
    assert r.status_code==409 and 'sesión cambió' in r.text,r.text
    assert db.query(AppArchivo).count()==0 and db.query(AppEvidencia).count()==0


def test_reintento_de_una_foto_confirmada_no_duplica_archivo_evidencia_o_copia(cliente,db):
    codigo=rec(cliente);yo=cliente.get('/api/auth/yo').json()
    ruta=f'/api/app/recepciones/{codigo}/archivos/foto';datos=payload(operadorOrigen=yo['id'])
    uno=cliente.post(ruta,json=datos);dos=cliente.post(ruta,json=datos)
    assert uno.status_code==dos.status_code==201
    assert uno.json()['id']==dos.json()['id']
    assert db.query(AppArchivo).count()==db.query(AppEvidencia).count()==db.query(AppCopiaDrive).count()==1


@pytest.mark.parametrize('estado',['ausente','corrupta'])
def test_reintento_repara_copia_local_no_respaldada_sin_crear_otro_registro(cliente,db,estado):
    codigo=rec(cliente);ruta=f'/api/app/recepciones/{codigo}/archivos/foto'
    uno=cliente.post(ruta,json=payload());assert uno.status_code==201,uno.text
    a=db.get(AppArchivo,uno.json()['id']);destino=archivos.ruta(a)
    if estado=='ausente':destino.unlink()
    else:destino.write_bytes(b'copia incompleta')
    r=cliente.post(ruta,json=payload());assert r.status_code==201,r.text
    assert r.json()['id']==a.id and destino.read_bytes()==PNG
    assert db.query(AppArchivo).count()==1 and not list(destino.parent.glob('*.tmp'))


def test_fallo_de_disco_no_confirma_metadatos(cliente,db,monkeypatch,tmp_path):
    codigo=rec(cliente);monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    def disco_lleno(_):raise OSError('No se pudo sincronizar disco de prueba')
    monkeypatch.setattr(archivos.os,'fsync',disco_lleno)
    with pytest.raises(OSError):cliente.post(f'/api/app/recepciones/{codigo}/archivos/foto',json=payload())
    db.rollback()
    assert db.query(AppArchivo).count()==db.query(AppEvidencia).count()==0
    assert not list((tmp_path/'app_archivos').iterdir())


def test_contenido_se_sincroniza_antes_de_confirmar_el_archivo(cliente,db,monkeypatch,tmp_path):
    codigo=rec(cliente);monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    original=os.fsync;sincronizados=[]
    def sincronizar(fd):
        sincronizados.append(os.fstat(fd).st_size)
        assert db.query(AppArchivo).count()==0
        return original(fd)
    monkeypatch.setattr(archivos.os,'fsync',sincronizar)
    r=cliente.post(f'/api/app/recepciones/{codigo}/archivos/foto',json=payload())
    assert r.status_code==201 and len(PNG) in sincronizados,r.text
