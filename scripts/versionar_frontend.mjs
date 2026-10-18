// Una version comun para TODO el grafo ESM: evita HTML nuevo con imports viejos.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

export const VERSION_FRONTEND='20261018-43';
export async function versionarFrontend() {
  const raiz=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../firebase/public');
  for(const carpeta of [raiz,path.join(raiz,'js')]) {
    for(const nombre of await fs.readdir(carpeta)) {
      if(!/\.(html|js)$/.test(nombre) || nombre==='sw.js')continue;
      const ruta=path.join(carpeta,nombre),original=await fs.readFile(ruta,'utf8');
      let texto=original.replace(/((?:\bfrom\s*|\bimport\s*\(\s*)['"])(\.\.?\/[^'"]+\.js)(?:\?v=[\w.-]+)?(['"])/g,
        (_,antes,modulo,fin)=>`${antes}${modulo}?v=${VERSION_FRONTEND}${fin}`);
      texto=texto.replace(/(<script\b[^>]*\bsrc=['"])(\.\/[^'"]+\.js)(?:\?v=[\w.-]+)?(['"])/g,
        (_,antes,recurso,fin)=>`${antes}${recurso}?v=${VERSION_FRONTEND}${fin}`);
      texto=texto.replace(/(css\/marca\.css)\?v=[\w.-]+/g,`$1?v=${VERSION_FRONTEND}`);
      if(texto!==original)await fs.writeFile(ruta,texto);
    }
  }
  const sw=path.join(raiz,'sw.js'),antes=await fs.readFile(sw,'utf8');
  const despues=antes.replace(/const VERSION = '[^']+';/,`const VERSION = 'iv-${VERSION_FRONTEND}';`)
    .replace(/const VERSION_RECURSOS = '[^']+';/,`const VERSION_RECURSOS = '${VERSION_FRONTEND}';`)
    .replace(/(css\/marca\.css)\?v=[\w.-]+/g,`$1?v=${VERSION_FRONTEND}`);
  if(despues!==antes)await fs.writeFile(sw,despues);
}
if(process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url))await versionarFrontend();
