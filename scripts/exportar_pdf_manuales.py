"""Exporta los HTML completos a PDF con Chrome/Chromium local, con las herramientas documentales de esta copia del código."""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess

def navegador(explicito=None):
    if explicito:
        if not Path(explicito).is_file():raise ValueError('No se encuentra el navegador indicado.')
        return str(Path(explicito).resolve())
    for n in ('google-chrome','chromium','chromium-browser','chrome','msedge'):
        if p:=shutil.which(n):return p
    for raiz in (os.getenv('PROGRAMFILES'),os.getenv('PROGRAMFILES(X86)'),os.getenv('LOCALAPPDATA')):
        if raiz:
            for n in ('Google/Chrome/Application/chrome.exe','Microsoft/Edge/Application/msedge.exe'):
                p=Path(raiz)/n
                if p.is_file():return str(p)
    raise ValueError('No se encontró Chrome/Chromium/Edge. Los HTML se conservan: ábrelos en tu computador y usa Imprimir / PDF, o indica --chrome con la ruta del navegador.')

def exportar(carpeta,chrome=None,sin_sandbox=False):
    ejecutable=navegador(chrome);carpeta=Path(carpeta).resolve()
    node=shutil.which('node')
    if not node:raise ValueError('Para la exportación automática instala Node.js 18 o superior; también puedes usar Imprimir / PDF desde el HTML.')
    comando=[node,str(Path(__file__).with_suffix('.mjs')),str(carpeta),ejecutable]
    if sin_sandbox:comando+=['--sin-sandbox']
    r=subprocess.run(comando,timeout=240)
    if r.returncode:raise ValueError('No se completó la exportación PDF. Los HTML y los PDF anteriores se conservan.')
    return json.loads((carpeta/'Exportacion-PDF.json').read_text())

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--carpeta',type=Path,required=True);p.add_argument('--chrome');p.add_argument('--sin-sandbox',action='store_true',help='Solo para entornos de pruebas que lo requieren; no es el valor predeterminado.')
    a=p.parse_args()
    try:exportar(a.carpeta,a.chrome,a.sin_sandbox)
    except (ValueError,OSError,subprocess.TimeoutExpired) as e:p.exit(1,str(e)+'\n')
if __name__=='__main__':main()
