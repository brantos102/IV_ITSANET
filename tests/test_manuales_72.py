import importlib.util
import json
from pathlib import Path
import pytest
import subprocess
import sys
import zipfile
from fastapi.testclient import TestClient
from app import config
from app.main import app
from scripts.publicar_manuales import publicar

ROOT=Path(__file__).resolve().parents[1]

def documentos(tmp_path):
    html=tmp_path/'usuario.html';pdf=tmp_path/'usuario.pdf';th=tmp_path/'tecnico.html';tp=tmp_path/'tecnico.pdf'
    html.write_text('<!doctype html><html><header>Manual</header>'+''.join(f'<section class="step" id="paso-{i}">Paso {i}</section>' for i in range(1,39))+'</html>')
    pdf.write_bytes(b'%PDF-1.4\nManual de usuario\n%%EOF\n');th.write_text('<html>Documento técnico privado</html>');tp.write_bytes(b'%PDF-1.4\nDocumento tecnico privado\n%%EOF\n')
    return html,pdf,th,tp

def test_generador_conserva_38_pasos_y_no_recrea_los_eliminados():
    spec=importlib.util.spec_from_file_location('manual_base_72',ROOT/'scripts/generar_manual_usuario_completo.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    pasos=m.pasos();assert len(pasos)==38
    assert pasos[-1][1]=='Resolver falta de conexión o una vista desactualizada'
    assert not any('paso 39' in str(p) or 'paso 40' in str(p) for p in pasos)

def test_publicacion_requiere_38_pasos_y_no_sustituye_un_par_valido_con_otro_incompleto(tmp_path):
    h,p,th,tp=documentos(tmp_path);destino=tmp_path/'publicados'
    primero=publicar(h,p,destino,'revision',th,tp)
    puntero=(destino/'usuario/actual.json').read_bytes()
    h.write_text(h.read_text().replace('</html>','<section class="step" id="paso-39"></section></html>'))
    with pytest.raises(ValueError):publicar(h,p,destino)
    assert (destino/'usuario/actual.json').read_bytes()==puntero
    assert (destino/'usuario/versiones'/primero['version']/'Manual-usuario-IV-ITSANET.pdf').read_bytes()==p.read_bytes()

def test_pdf_invalido_no_publica_y_version_anterior_se_conserva(tmp_path):
    h,p,th,tp=documentos(tmp_path);destino=tmp_path/'publicados'
    primero=publicar(h,p,destino);p.write_bytes(b'No es un PDF')
    with pytest.raises(ValueError):publicar(h,p,destino)
    assert json.loads((destino/'usuario/actual.json').read_text())['version']==primero['version']

def test_acceso_autenticado_y_tecnico_no_publicado(cliente,tmp_path,monkeypatch):
    h,p,th,tp=documentos(tmp_path);destino=tmp_path/'publicados';publicar(h,p,destino,'revision',th,tp)
    monkeypatch.setattr(config,'MANUALES_DIR',destino)
    anonimo=TestClient(app)
    assert anonimo.get('/api/app/manuales/usuario/html').status_code==401
    anonimo.close()
    for formato in ('html','pdf'):
        r=cliente.get('/api/app/manuales/usuario/'+formato);assert r.status_code==200,r.text
        assert r.headers['cache-control']=='private, no-store'
    r=cliente.get('/api/app/manuales/usuario/html')
    assert "connect-src 'none'" in r.headers['content-security-policy'] and 'allow-same-origin' not in r.headers['content-security-policy']
    assert 'data-pdf-publicado' in r.text
    assert cliente.get('/api/app/manuales/tecnico/html').status_code==404
    assert cliente.get('/app/documentacion/manuales/tecnico/actual.json').status_code==404

def test_dos_publicaciones_conservan_pares_y_enlaces_de_cada_version(cliente,tmp_path,monkeypatch):
    h,p,th,tp=documentos(tmp_path);destino=tmp_path/'publicados';a=publicar(h,p,destino)
    p.write_bytes(b'%PDF-1.4\nNueva revision\n%%EOF\n');b=publicar(h,p,destino)
    monkeypatch.setattr(config,'MANUALES_DIR',destino)
    assert a['version']!=b['version']
    actual=cliente.get('/api/app/manuales/usuario/html');assert b['version'] in actual.text
    anterior=cliente.get('/api/app/manuales/usuario/pdf',params={'version':a['version']})
    assert anterior.status_code==200 and b'Manual de usuario' in anterior.content
    assert b'Nueva revision' in cliente.get('/api/app/manuales/usuario/pdf').content
    assert 'attachment' in cliente.get('/api/app/manuales/usuario/pdf?descargar=true').headers['content-disposition']

def test_version_invalida_o_faltante_no_expone_archivos(cliente,tmp_path,monkeypatch):
    monkeypatch.setattr(config,'MANUALES_DIR',tmp_path)
    assert cliente.get('/api/app/manuales/usuario/html').status_code==404
    assert cliente.get('/api/app/manuales/usuario/html?version=../tecnico').status_code==503
    assert cliente.get('/api/app/manuales/usuario/otro').status_code==404

def test_regeneracion_archiva_pdf_antiguo_y_no_lo_mezcla_con_html_38(tmp_path):
    word=tmp_path/'manual.docx';salida=tmp_path/'salida';salida.mkdir()
    with zipfile.ZipFile(word,'w') as z:
        z.writestr('word/_rels/document.xml.rels','<Relationships/>')
        z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>PASO 1 DE 40</w:t></w:r></w:p></w:body></w:document>')
    anterior=salida/'Manual-usuario-final-IV-ITSANET.pdf';anterior.write_bytes(b'%PDF-1.4\nAntiguo 40 pasos\n%%EOF')
    subprocess.run([sys.executable,str(ROOT/'scripts/preparar_manuales_desde_word.py'),'--word',str(word),'--salida',str(salida),'--revision','prueba'],check=True,capture_output=True)
    assert not anterior.exists()
    assert next((salida/'_anteriores').glob('*/Manual-usuario-final-IV-ITSANET.pdf')).read_bytes().find(b'Antiguo 40 pasos')>=0
    with zipfile.ZipFile(salida/'IV-ITSANET-manuales-38-pasos.zip') as z:
        assert 'Manual-usuario-final-IV-ITSANET.pdf' not in z.namelist()
        html=z.read('Manual-usuario-final-IV-ITSANET.html').decode()
        assert 'id="paso-38"' in html and 'id="paso-39"' not in html and 'de 40 ·' not in html

def test_captura_nueva_del_selector_en_word_no_se_reemplaza_por_referencia(tmp_path):
    word=tmp_path/'manual-actualizado.docx';salida=tmp_path/'salida'
    imagen=(ROOT/'docs/muestras/manuales-v70/33-Agrupacion-correos-referencia.png').read_bytes()
    with zipfile.ZipFile(word,'w') as z:
        z.writestr('word/_rels/document.xml.rels','<Relationships><Relationship Id="foto" Target="media/image57.png"/></Relationships>')
        z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body><w:p><w:r><w:t>PASO 33 DE 38</w:t></w:r><a:blip r:embed="foto"/></w:p></w:body></w:document>')
        z.writestr('word/media/image57.png',imagen)
    subprocess.run([sys.executable,str(ROOT/'scripts/preparar_manuales_desde_word.py'),'--word',str(word),'--salida',str(salida),'--revision','prueba'],check=True,capture_output=True)
    r=json.loads((salida/'Revision-del-Word-V2.json').read_text());s=next(x for x in r['pasos'] if x['paso']==33)
    assert s['origen']=='WORD' and s['imagenes']==1 and r['pasosFinales']==38
