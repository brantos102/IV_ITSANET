"""Vistas previas opcionales y consultas Gmail, sin operaciones Google reales."""
import base64
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app.models import AppArchivo, AppCopiaDrive
from app.services import archivos, entregas
from tests.test_mejoras_operativas import preparar
from tests.test_operacion_desarrollo import foto
from tests.test_archivos_locales import PNG
from tests.test_remitente_responsable import correo


def test_miniaturas_fallidas_no_pierden_original_ni_repiten_puente(cliente,db,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    c=preparar(db)
    fotos=[foto(cliente,c,sku='SKU1',variante=i).json() for i in range(2)]
    db.rollback();db.expire_all()
    for f in fotos:
        a=db.get(AppArchivo,f['id']);a.drive_id='original-'+a.id
        db.get(AppCopiaDrive,a.id).estado='COPIADA'
        archivos.ruta(a).unlink()
    db.commit()
    llamadas=[]
    def fallar(*args):
        llamadas.append(args)
        raise httpx.ReadTimeout('No devolver contenido privado')
    monkeypatch.setattr(entregas,'llamar',fallar)
    for f in [fotos[0],fotos[0],fotos[1]]:
        r=cliente.get(f['url']+'?miniatura=1')
        assert r.status_code==204 and not r.content
        assert r.headers['cache-control']=='private, no-store'
        assert r.headers['x-itsanet-miniatura']=='no-disponible'
        original=cliente.get(f['url'],follow_redirects=False)
        assert original.status_code==307 and 'drive.google.com' in original.headers['location']
    assert len(llamadas)==1
    db.rollback();db.expire_all()
    for f in fotos:
        assert db.get(AppArchivo,f['id']).drive_id
        assert db.get(AppCopiaDrive,f['id']).estado=='COPIADA'
    assert TestClient(app).get(fotos[0]['url']+'?miniatura=1').status_code==401
    assert cliente.delete('/api/operacion/evidencias/'+fotos[0]['id']).status_code==200
    assert cliente.get(fotos[0]['url']+'?miniatura=1').status_code==410


def test_foto_local_usa_miniatura_sin_consultar_google(cliente,db,monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path);c=preparar(db)
    f=foto(cliente,c,sku='SKU1').json()
    monkeypatch.setattr(entregas,'llamar',lambda *a:pytest.fail('La foto aún es local'))
    assert cliente.get(f['url']+'?miniatura=1').status_code==200
    assert cliente.get(f['url']).status_code==200


def test_miniaturas_maximo_dos_y_sin_retener_conexion_mysql(monkeypatch,tmp_path):
    monkeypatch.setattr(archivos,'DATA_DIR',tmp_path)
    esperando=threading.Event();dos=threading.Event();lock=threading.Lock();llamadas=[]
    class DB:
        liberada=False
        def get(self,*args):return SimpleNamespace(usuario='supervisor@example.test')
        def rollback(self):self.liberada=True
    def puente(accion,ident,datos):
        assert sesiones[ident].liberada
        with lock:
            llamadas.append(ident)
            if len(llamadas)==2:dos.set()
        assert esperando.wait(5)
        return {'base64':base64.b64encode(PNG).decode()}
    monkeypatch.setattr(entregas,'llamar',puente)
    sesiones={str(i)*32:DB() for i in range(1,4)}
    archivos_foto={i:SimpleNamespace(id=i,drive_id='google-'+i,tipo='foto',nombre='foto.png',recepcion='R') for i in sesiones}
    monkeypatch.setattr(archivos,'ruta',lambda a:tmp_path/(a.id+'.png'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        tareas=[pool.submit(archivos.miniatura_drive,sesiones[i],archivos_foto[i]) for i in list(sesiones)[:2]]
        try:
            assert dos.wait(5)
            tercero=list(sesiones)[2]
            with pytest.raises(HTTPException) as e:archivos.miniatura_drive(sesiones[tercero],archivos_foto[tercero])
            assert e.value.status_code==503 and len(llamadas)==2
        finally:esperando.set()
        assert all(t.result()==PNG for t in tareas)


@pytest.mark.parametrize('codigo',['GMAIL_API_DESACTIVADA','GMAIL_PERMISOS','GMAIL_POLITICA','GMAIL_BUZON','GMAIL_CUOTA','GMAIL_AUTORIZACION'])
def test_supervisor_recibe_diagnostico_gmail_sin_cuerpo_google(cliente,correo,monkeypatch,codigo):
    def puente(accion,clave,datos,conexion):
        if accion=='estado':return {'remitente':'personal@example.test','capacidades':['gmailHilos']}
        raise RuntimeError(entregas._error_google({'error':codigo+': contenido-privado-token'}))
    monkeypatch.setattr(entregas,'llamar_conexion',puente)
    r=cliente.get('/api/app/integraciones/mi-google/gmail',params={'busqueda':'packing'})
    assert r.status_code==409,r.text
    assert r.json()['detail']['codigo']==codigo
    assert 'contenido-privado-token' not in r.text


@pytest.mark.parametrize('fallo,estado,codigo',[(httpx.ReadTimeout,504,'GMAIL_TIEMPO'),(httpx.ConnectError,502,'GMAIL_RED')])
def test_gmail_timeout_permiso_supervisor_y_operario_bloqueado(cliente,correo,monkeypatch,fallo,estado,codigo):
    def puente(accion,clave,datos,conexion):
        if accion=='estado':return {'remitente':'personal@example.test','capacidades':['gmailHilos']}
        raise fallo('No mostrar token')
    monkeypatch.setattr(entregas,'llamar_conexion',puente)
    r=cliente.get('/api/app/integraciones/mi-google/gmail',params={'busqueda':'packing'})
    assert r.status_code==estado and r.json()['detail']['codigo']==codigo
    op=TestClient(app);op.post('/api/auth/login',json={'usuario':'op1','pin':'2222'})
    assert op.get('/api/app/integraciones/mi-google/gmail',params={'busqueda':'packing'}).status_code==403


@pytest.mark.parametrize('accion,segundos',[('miniatura',12),('gmailBuscar',25),('gmailMensaje',25),('estado',25),('finalizar',120)])
def test_timeout_lecturas_corto_envio_conservado(monkeypatch,accion,segundos):
    class Cliente:
        def __init__(self,timeout,**kwargs):
            assert (timeout.read if isinstance(timeout,httpx.Timeout) else timeout)==segundos
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def post(self,*a,**kw):return httpx.Response(200,json={'exito':True})
    monkeypatch.setattr(httpx,'Client',Cliente)
    assert entregas.llamar_conexion(accion,'clave',{}, {'url':'https://script.google.com/macros/s/simulado/exec','secreto':'prueba-'*8})['exito']
