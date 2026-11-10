import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('configurar_google', Path(__file__).parents[1] / 'scripts/configurar_google.py')
modulo = importlib.util.module_from_spec(spec); spec.loader.exec_module(modulo)


def test_conserva_configuracion_ajena_y_no_rota_claves_al_repetir(tmp_path):
    env = tmp_path / 'iv-itsanet.env'
    original = '# Configuracion empresarial\nVAL_DATABASE_URL="mysql://demo:no-es-clave-real@localhost/pruebas"\nVAL_PORT=3002\n'
    env.write_text(original)
    clave = modulo.configurar(env, modulo.URL)
    assert env.read_text().startswith(original)
    assert env.stat().st_mode & 0o777 == 0o600
    assert modulo.configurar(env, modulo.URL) == clave
    assert env.read_text().count('VAL_GOOGLE_PROXY_SECRET=') == 1
