"""Genera HTML privados y un ZIP desde el Word del usuario, sin arrancar la app."""
from pathlib import Path
import argparse
import subprocess
import sys
import zipfile
import hashlib
import shutil
from datetime import datetime, timezone
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--word',type=Path,required=True)
    p.add_argument('--salida',type=Path,required=True)
    p.add_argument('--revision',required=True)
    p.add_argument('--captura-correos',type=Path,nargs='+')
    p.add_argument('--pdf',action='store_true',help='Exportar con un Chrome/Chromium/Edge ya instalado.')
    p.add_argument('--chrome',help='Ruta del navegador para la exportación PDF.')
    p.add_argument('--sin-sandbox',action='store_true',help='Solo para pruebas; no usar como configuración operativa.')
    a=p.parse_args()
    if not a.word.is_file():p.error('No se encuentra el Word. Súbelo primero desde tu computador al servidor con el Explorador de VS Code.')
    destino=a.salida.resolve()
    publico=(ROOT/'firebase/public').resolve()
    if destino==publico or publico in destino.parents:p.error('Usa una carpeta privada fuera de firebase/public para conservar las capturas operativas.')
    destino.mkdir(parents=True,exist_ok=True,mode=0o700)
    destino.chmod(0o700)
    generados=['Manual-usuario-final-IV-ITSANET.html','Manual-tecnico-final-IV-ITSANET.html',
        'Manual-usuario-final-IV-ITSANET.pdf','Manual-tecnico-final-IV-ITSANET.pdf','Exportacion-PDF.json',
        'IV-ITSANET-manuales-privados-v71.zip','IV-ITSANET-manuales-38-pasos.zip']
    anteriores=[destino/n for n in generados if (destino/n).is_file()]
    if anteriores:
        historial=destino/'_anteriores'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-')+uuid4().hex[:8])
        historial.mkdir(parents=True,mode=0o700)
        for f in anteriores:shutil.copy2(f,historial/f.name)
        print('Copia anterior conservada en:',historial,flush=True)
    comando=[sys.executable,str(ROOT/'scripts/generar_manuales_word_70.py'),
        '--word',str(a.word.resolve()),'--salida',str(destino),
        '--referencias',str(ROOT/'docs/muestras/manuales-v70'),
        '--revision',a.revision,'--version','72']
    if a.captura_correos:comando+=['--captura-correos',*[str(f.resolve()) for f in a.captura_correos]]
    subprocess.run(comando,check=True)
    # No mezclar el HTML nuevo de 38 pasos con un PDF o ZIP de una generación anterior.
    for n in generados:
        if n.endswith(('.pdf','.zip')) or n=='Exportacion-PDF.json':(destino/n).unlink(missing_ok=True)
    if a.pdf:
        pdf=[sys.executable,str(ROOT/'scripts/exportar_pdf_manuales.py'),'--carpeta',str(destino)]
        if a.chrome:pdf+=['--chrome',a.chrome]
        if a.sin_sandbox:pdf+=['--sin-sandbox']
        subprocess.run(pdf,check=True)
    guia=ROOT/'docs/entrega-v71/Guia-continuidad-IV-ITSANET.html'
    if guia.is_file():(destino/guia.name).write_bytes(guia.read_bytes())
    (destino/'LEEME.txt').write_text('IV ITSANET · Manuales privados\n\nAbre los HTML con Chrome o Edge. Cada manual contiene sus imágenes.\nUsa Imprimir / PDF para guardar una copia PDF.\nEn el Explorador remoto de VS Code: clic derecho en el ZIP → Descargar.\nNo copies estos documentos con capturas operativas a una carpeta pública.\nLa generación no actualiza ni reinicia el aplicativo.\n',encoding='utf-8')
    archivos=[f for f in destino.iterdir() if f.suffix in ('.html','.pdf','.json','.txt') and f.name!='SHA256SUMS.txt']
    (destino/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(f.read_bytes()).hexdigest()+'  '+f.name+'\n' for f in sorted(archivos)),encoding='utf-8')
    salida=destino/'IV-ITSANET-manuales-38-pasos.zip'
    with zipfile.ZipFile(salida,'w',zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        for f in archivos+[destino/'SHA256SUMS.txt']:z.write(f,f.name)
    print('Documentos creados en:',destino)
    print('Clic derecho en este archivo desde VS Code → Descargar:',salida)
    print('No se conectó a MySQL, Google ni al servicio de producción.')

if __name__=='__main__':main()
