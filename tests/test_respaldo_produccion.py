"""El respaldo no carga la app, no filtra contraseñas y no sobrescribe copias."""
import gzip
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

import pytest


@pytest.fixture
def respaldo(monkeypatch, tmp_path):
    ruta = Path(__file__).resolve().parents[1] / 'scripts/respaldo_produccion.py'
    spec = importlib.util.spec_from_file_location('respaldo_itsanet', ruta)
    modulo = importlib.util.module_from_spec(spec); spec.loader.exec_module(modulo)
    datos = tmp_path / 'datos'; datos.mkdir()
    (datos / 'foto.jpg').write_bytes(b'evidencia-preservada')
    secretos = datos / 'secretos'; secretos.mkdir(); (secretos / 'integraciones.key').write_bytes(b'clave-de-prueba')
    monkeypatch.setenv('VAL_DATABASE_URL', 'mysql+pymysql://u:claveprivada@localhost/itsanet_test?charset=utf8mb4')
    monkeypatch.setenv('VAL_DATA_DIR', str(datos))
    return modulo


def test_respaldo_contiene_base_archivos_clave_y_sumarios_sin_password(respaldo, monkeypatch, tmp_path):
    ejecutable = tmp_path / 'mysqldump'
    ejecutable.write_text('#!/usr/bin/env python3\nprint("-- MySQL dump de prueba\\n" + "CREATE TABLE ejemplo (id INT);\\n" * 10)\n')
    ejecutable.chmod(0o700)
    monkeypatch.setattr(respaldo.shutil, 'which', lambda _: str(ejecutable))
    salida = tmp_path / 'respaldo'
    respaldo.respaldar(tmp_path, salida, 'a' * 40)
    assert 'CREATE TABLE ejemplo' in gzip.decompress((salida / 'mysql.sql.gz').read_bytes()).decode()
    with tarfile.open(salida / 'archivos.tar.gz') as t:
        assert t.extractfile('datos/foto.jpg').read() == b'evidencia-preservada'
        assert t.extractfile('datos/secretos/integraciones.key').read() == b'clave-de-prueba'
    d = json.loads((salida / 'respaldo.json').read_text())
    assert d['revisionAnterior'] == 'a' * 40 and len(d['sha256']) == 2
    assert 'claveprivada' not in (salida / 'respaldo.json').read_text()
    assert not list(salida.glob('.conexion-*'))
    assert (tmp_path / 'datos/foto.jpg').read_bytes() == b'evidencia-preservada'
    with pytest.raises(ValueError, match='no se sobrescribe'):
        respaldo.respaldar(tmp_path, salida, 'b' * 40)


def test_fallo_dump_no_produce_acuse_de_respaldo_completo(respaldo, monkeypatch, tmp_path):
    ejecutable = tmp_path / 'mysqldump'
    ejecutable.write_text('#!/usr/bin/env python3\nimport sys\nprint("fallo",file=sys.stderr)\nsys.exit(1)\n')
    ejecutable.chmod(0o700)
    monkeypatch.setattr(respaldo.shutil, 'which', lambda _: str(ejecutable))
    salida = tmp_path / 'fallido'
    with pytest.raises(RuntimeError, match='Falló el respaldo'):
        respaldo.respaldar(tmp_path, salida, 'a' * 40)
    assert not (salida / 'respaldo.json').exists()
    assert not list(salida.glob('.conexion-*'))


def test_comprobaciones_ocurren_sin_crear_respaldo_y_rechazan_ubicacion_incorrecta(respaldo, monkeypatch, tmp_path):
    monkeypatch.setattr(respaldo.shutil, 'which', lambda _: '/usr/bin/mysqldump')
    salida = tmp_path / 'datos/respaldo'
    with pytest.raises(ValueError, match='fuera de VAL_DATA_DIR'):
        respaldo.parametros(tmp_path, salida)
    assert not salida.exists()
    monkeypatch.setenv('VAL_DATABASE_URL', 'mysql+pymysql://u:clave@localhost/db?ssl_ca=ca.pem')
    with pytest.raises(ValueError, match='opciones especiales'):
        respaldo.parametros(tmp_path, tmp_path / 'externo')


def test_credenciales_en_archivo_privado_y_escapadas_sin_argumentos_en_linea(respaldo, monkeypatch, tmp_path):
    ejecutable = tmp_path / 'mysqldump'
    ejecutable.write_text('''#!/usr/bin/env python3
import pathlib,sys
args=sys.argv[1:]
p=pathlib.Path(args[0].split('=',1)[1])
assert p.stat().st_mode & 0o777 == 0o600
assert 'password="claveprivada"' in p.read_text()
assert not any('claveprivada' in a for a in args)
print('-- respaldo ' + 'x'*150)
''')
    ejecutable.chmod(0o700)
    monkeypatch.setattr(respaldo.shutil, 'which', lambda _: str(ejecutable))
    respaldo.respaldar(tmp_path, tmp_path / 'seguro', 'a' * 40)
    assert respaldo.opcion('x"\\\n') == '"x\\"\\\\\\n"'


@pytest.mark.parametrize('fallo', ['', 'respaldo', 'salud'])
def test_pase_preserva_datos_y_recupera_codigo_si_falla(tmp_path, fallo):
    raiz = Path(__file__).resolve().parents[1]
    repo = tmp_path / 'operacion'; repo.mkdir()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=True, stderr=subprocess.PIPE).strip()
    git('init'); git('config', 'user.name', 'Pruebas'); git('config', 'user.email', 'pruebas@example.test')
    (repo / 'mysql').mkdir(); sql = repo / 'mysql/01-crear-base.sql'; sql.write_text('SQL original\n')
    (repo / 'version.txt').write_text('anterior')
    (repo / 'requirements.txt').write_text('')
    git('add', '.'); git('commit', '-m', 'Operación inicial'); anterior = git('rev-parse', 'HEAD')
    (repo / 'scripts').mkdir(); shutil.copy(raiz / 'scripts/respaldo_produccion.py', repo / 'scripts')
    (repo / 'version.txt').write_text('nueva')
    git('add', '.'); git('commit', '-m', 'Candidato'); revision = git('rev-parse', 'HEAD')
    git('checkout', '--detach', anterior)
    sql.write_text('SQL propio de producción\n')
    datos = repo / 'data'; datos.mkdir(); (datos / 'foto.jpg').write_bytes(b'foto-operativa')
    binarios = tmp_path / 'bin'; binarios.mkdir()
    llamadas = tmp_path / 'llamadas.log'
    dispatcher = '''#!/usr/bin/env python3
import os,pathlib,shutil,subprocess,sys
nombre=pathlib.Path(sys.argv[0]).name;a=sys.argv[1:];repo=os.environ['QA_REPO']
with open(os.environ['QA_LOG'],'a') as f:f.write(nombre+' '+' '.join(a)+'\\n')
if nombre=='systemctl':
 if a[0]=='show':print(repo)
 sys.exit(0)
if nombre=='curl':
 print('{"ok":true}')
 sys.exit(1 if os.environ.get('QA_FALLO')=='salud' else 0)
if nombre=='mysqldump':
 print('-- MySQL '+ 'x'*150)
 sys.exit(1 if os.environ.get('QA_FALLO')=='respaldo' else 0)
if nombre=='sudo':
 if a[0] in ('-v','test'):sys.exit(0)
 if a[0]=='install':pathlib.Path(a[-1]).write_text('ENTORNO=privado');sys.exit(0)
 sys.exit(subprocess.call(a))
if nombre=='systemd-run':
 i=next(i for i,v in enumerate(a) if v.endswith('/.venv/bin/python'))
 sys.exit(subprocess.call(a[i:]))
if nombre=='python':
 if a[:2]==['-m','pip']:sys.exit(0)
 sys.exit(subprocess.call([os.environ['QA_PYTHON'],*a]))
raise SystemExit(2)
'''
    for nombre in ['sudo', 'systemctl', 'systemd-run', 'curl', 'mysqldump']:
        f = binarios / nombre; f.write_text(dispatcher); f.chmod(0o700)
    venv = repo / '.venv/bin'; venv.mkdir(parents=True)
    (venv / 'python').write_text(dispatcher); (venv / 'python').chmod(0o700)
    env = {**os.environ, 'PATH': str(binarios) + ':' + os.environ['PATH'],
        'QA_REPO': str(repo), 'QA_LOG': str(llamadas), 'QA_PYTHON': sys.executable, 'QA_FALLO': fallo,
        'VAL_DATABASE_URL': 'mysql+pymysql://u:clave@localhost/operativa?charset=utf8mb4', 'VAL_DATA_DIR': str(datos)}
    r = subprocess.run(['bash', str(raiz / 'scripts/actualizar_produccion.sh'), str(repo), revision],
        env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode == (1 if fallo else 0), r.stdout + r.stderr
    assert git('rev-parse', 'HEAD') == (anterior if fallo else revision)
    assert sql.read_text() == 'SQL propio de producción\n'
    assert (datos / 'foto.jpg').read_bytes() == b'foto-operativa'
    assert 'systemctl stop iv-itsanet' in llamadas.read_text()
    assert 'systemctl start iv-itsanet' in llamadas.read_text()
    if fallo == 'salud':
        assert llamadas.read_text().splitlines().count('systemctl stop iv-itsanet') == 2
    copia = next((tmp_path / 'respaldos-itsanet').glob('pase-*'))
    if fallo == 'respaldo': assert not (copia / 'respaldo.json').exists()
    else:
        assert (copia / 'respaldo.json').exists()
        with tarfile.open(copia / 'archivos.tar.gz') as t:
            assert t.extractfile('datos/foto.jpg').read() == b'foto-operativa'
