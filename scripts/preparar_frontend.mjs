// Recursos de navegador retenidos en Git: el servidor no necesita npm ni CDN.
import { build } from 'esbuild';
import { mkdir, copyFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { versionarFrontend } from './versionar_frontend.mjs';

const raiz = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const destino = path.join(raiz, 'firebase/public/vendor');
await mkdir(destino, { recursive: true });
await build({
  stdin: {
    contents: "export * from 'firebase/app'; export * from 'firebase/auth'; export * from 'firebase/firestore';",
    resolveDir: raiz, sourcefile: 'firebase-sdk-entry.js', loader: 'js',
  },
  outfile: path.join(destino, 'firebase-sdk.js'),
  bundle: true, minify: true, format: 'esm', target: 'es2020', legalComments: 'eof',
});
await copyFile(path.join(raiz, 'node_modules/xlsx/dist/xlsx.full.min.js'),
               path.join(destino, 'xlsx.full.min.js'));
await copyFile(path.join(raiz, 'node_modules/jspdf/dist/jspdf.umd.min.js'), path.join(destino, 'jspdf.umd.min.js'));
await copyFile(path.join(raiz, 'node_modules/jspdf-autotable/dist/jspdf.plugin.autotable.min.js'), path.join(destino, 'jspdf.plugin.autotable.min.js'));
await copyFile(path.join(raiz, 'node_modules/jsbarcode/dist/JsBarcode.all.min.js'), path.join(destino, 'JsBarcode.all.min.js'));
await build({
  stdin:{contents:"export { BrowserMultiFormatReader, MultiFormatReader, DecodeHintType, BarcodeFormat, BinaryBitmap, HybridBinarizer, HTMLCanvasElementLuminanceSource } from '@zxing/library';",resolveDir:raiz,sourcefile:'zxing-entry.js',loader:'js'},
  outfile:path.join(destino,'zxing.js'),bundle:true,minify:true,format:'esm',target:'es2020',legalComments:'eof',
});
await copyFile(path.join(raiz,'node_modules/@zxing/library/LICENSE'),path.join(destino,'ZXING-LICENSE.txt'));
console.log('SDK y lector Excel preparados para servir desde la bodega.');
await versionarFrontend();
