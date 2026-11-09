"""Genera HTML privados y un ZIP desde el Word del usuario, sin arrancar la app."""
from pathlib import Path
import argparse
import subprocess
import sys
import zipfile
import hashlib

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--word',type=Path,required=True)
    p.add_argument('--salida',type=Path,required=True)
    p.add_argument('--revision',required=True)
    a=p.parse_args()
    if not a.word.is_file():p.error('No se encuentra el Word. Súbelo primero desde tu computador al servidor con el Explorador de VS Code.')
    destino=a.salida.resolve()
    publico=(ROOT/'firebase/public').resolve()
    if destino==publico or publico in destino.parents:p.error('Usa una carpeta privada fuera de firebase/public para conservar las capturas operativas.')
    destino.mkdir(parents=True,exist_ok=True,mode=0o700)
    destino.chmod(0o700)
    subprocess.run([sys.executable,str(ROOT/'scripts/generar_manuales_word_70.py'),
        '--word',str(a.word.resolve()),'--salida',str(destino),
        '--referencias',str(ROOT/'docs/muestras/manuales-v70'),
        '--revision',a.revision,'--version','71'],check=True)
    guia=ROOT/'docs/entrega-v71/Guia-continuidad-IV-ITSANET.html'
    if guia.is_file():(destino/guia.name).write_bytes(guia.read_bytes())
    (destino/'LEEME.txt').write_text('IV ITSANET · Manuales privados\n\nAbre los HTML con Chrome o Edge. Cada manual contiene sus imágenes.\nUsa Imprimir / PDF para guardar una copia PDF.\nEn el Explorador remoto de VS Code: clic derecho en el ZIP → Descargar.\nNo copies estos documentos con capturas operativas a una carpeta pública.\nLa generación no actualiza ni reinicia el aplicativo.\n',encoding='utf-8')
    archivos=[f for f in destino.iterdir() if f.suffix in ('.html','.json','.txt') and f.name!='SHA256SUMS.txt']
    (destino/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(f.read_bytes()).hexdigest()+'  '+f.name+'\n' for f in sorted(archivos)),encoding='utf-8')
    salida=destino/'IV-ITSANET-manuales-privados-v71.zip'
    with zipfile.ZipFile(salida,'w',zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        for f in archivos+[destino/'SHA256SUMS.txt']:z.write(f,f.name)
    print('Documentos creados en:',destino)
    print('Clic derecho en este archivo desde VS Code → Descargar:',salida)
    print('No se conectó a MySQL, Google ni al servicio de producción.')

if __name__=='__main__':main()
