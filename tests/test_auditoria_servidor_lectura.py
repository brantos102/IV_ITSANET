"""La captura administrativa no carga la app ni imprime secretos."""
import json
from pathlib import Path
import sys
import os
import subprocess

import pytest
from scripts import auditar_servidor_lectura as audit


def test_apache_selecciona_directivas_y_oculta_credenciales(tmp_path):
    (tmp_path / 'itsanet-app-8443.conf').write_text('''<VirtualHost *:8443>
ServerName apps.flexnetuio.com
SSLCertificateKeyFile /privado/certificado.key
ProxyPass /api/ http://usuario:CLAVE@127.0.0.1:3002/api/?token=TOKEN
RequestHeader set Authorization "Bearer SECRETO"
RequestHeader set X-Forwarded-Proto "https"
''')
    s = json.dumps(audit.apache(tmp_path))
    assert '127.0.0.1:3002/api/' in s and 'X-Forwarded-Proto https' in s
    assert 'CLAVE' not in s and 'TOKEN' not in s and 'SECRETO' not in s and 'Authorization' not in s
    assert '/privado/certificado.key' in s  # Solo ruta, nunca lectura de la clave.


def test_contar_no_lee_contenido_ni_sigue_enlaces(tmp_path):
    (tmp_path / 'a').write_bytes(b'123'); (tmp_path / 'enlace').symlink_to('/etc/passwd')
    assert audit.contar(tmp_path) == {'estado': 'ok', 'archivos': 1, 'bytes': 3}
    assert audit.contar(tmp_path / 'ausente')['bytes'] is None


def preparar(monkeypatch, tmp_path):
    repo = tmp_path / 'repo'; (repo / 'scripts').mkdir(parents=True)
    (repo / 'scripts/versionar_frontend.mjs').write_text("export const VERSION_FRONTEND='20261018-48';")
    datos = tmp_path / 'datos'; (datos / 'app_archivos').mkdir(parents=True)
    (datos / 'app_archivos/foto').write_bytes(b'foto')
    monkeypatch.setenv('VAL_DATABASE_URL', 'mysql+pymysql://usuario:CLAVE_NO_IMPRIMIR@host/base')
    monkeypatch.setenv('VAL_SECRET_KEY', 'SECRET_KEY_NO_IMPRIMIR')
    monkeypatch.setenv('VAL_DATA_DIR', str(datos))
    monkeypatch.setattr(audit.estado, 'comando', lambda args, cwd=None: 'dato-de-lectura')
    monkeypatch.setattr(audit, 'apache', lambda: [])
    monkeypatch.setattr(audit, 'tls', lambda: {'verificacion': 'No ensayada en esta prueba'})
    class Respuesta:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self, n): return b'{"ok":true}'
    monkeypatch.setattr(audit.urllib.request, 'urlopen', lambda *a, **kw: Respuesta())
    monkeypatch.setattr(audit.estado, 'base_mysql', lambda url: {'tablas': [], 'avisos': []})
    return repo, datos


def test_captura_y_fallos_no_revelan_valores(monkeypatch, tmp_path):
    repo, datos = preparar(monkeypatch, tmp_path)
    r = audit.capturar(repo)
    texto = json.dumps(r)
    assert 'CLAVE_NO_IMPRIMIR' not in texto and 'SECRET_KEY_NO_IMPRIMIR' not in texto
    assert r['configuracionSinValores']['secretKeyPersonalizadaEnEntorno'] is True
    assert r['archivos']['app_archivos']['bytes'] == 4 and r['saludLocal'] == 'ok'
    assert r['frontendEnDisco'] == '20261018-48'
    def falla(url): raise ValueError('CLAVE_NO_IMPRIMIR')
    monkeypatch.setattr(audit.estado, 'base_mysql', falla)
    r = audit.capturar(repo)
    assert r['mysql'] is None and 'CLAVE_NO_IMPRIMIR' not in json.dumps(r)


def test_salida_privada_fuera_del_codigo(monkeypatch, tmp_path, capsys):
    repo, _ = preparar(monkeypatch, tmp_path)
    salida = tmp_path / 'reportes'
    monkeypatch.setattr(sys, 'argv', ['auditar', '--repo', str(repo), '--salida', str(salida)])
    assert audit.main() == 0
    for f in salida.iterdir(): assert f.stat().st_mode & 0o077 == 0
    assert len(list(salida.glob('*.md'))) == 1 and len(list(salida.glob('*.json'))) == 1
    monkeypatch.setattr(sys, 'argv', ['auditar', '--repo', str(repo), '--salida', str(repo / 'reportes')])
    with pytest.raises(SystemExit): audit.main()


def test_wrapper_usa_unidad_temporal_y_muestra_informe_sin_reiniciar(tmp_path):
    repo = tmp_path / 'repo'; python = repo / '.venv/bin/python'; python.parent.mkdir(parents=True)
    python.write_text('#!/bin/sh\nexit 0\n');python.chmod(0o755)
    salida = tmp_path / 'reportes';salida.mkdir();md = salida / 'auditoria-prueba.md';md.write_text('Informe de lectura sintético')
    binarios = tmp_path / 'bin';binarios.mkdir();registro = tmp_path / 'comando.json'
    sudo = binarios / 'sudo'
    sudo.write_text('#!' + sys.executable + '\nimport sys,json\nfrom pathlib import Path\n' +
        'Path('+repr(str(registro))+').write_text(json.dumps(sys.argv[1:]))\n' +
        'print('+repr(str(salida / 'auditoria-prueba.json'))+')\nprint('+repr(str(md))+')\n')
    sudo.chmod(0o755)
    script = Path(audit.__file__).with_name('revisar_servidor_lectura.sh')
    r = subprocess.run(['bash', str(script), str(repo), str(salida)], env={**os.environ,'PATH':str(binarios)+os.pathsep+os.environ['PATH']},capture_output=True,text=True)
    assert r.returncode == 0,r.stderr
    args = json.loads(registro.read_text())
    assert args[0] == 'systemd-run' and '--property=EnvironmentFile=/etc/iv-itsanet.env' in args
    assert any(a.startswith('--unit=iv-itsanet-auditoria-') for a in args)
    assert not any(a in ('restart','stop','start','daemon-reload') for a in args)
    assert 'Informe de lectura sintético' in r.stdout
