#!/usr/bin/env node
/**
 * Ejecuta todas las pruebas del proyecto.    node pruebas.js
 *
 * Las rutas se resuelven desde este archivo, no desde donde se invoque, así
 * que funciona igual lanzándolo desde la raíz o desde `firebase/`. Es lo que
 * antes obligaba a adivinar la carpeta correcta.
 */
'use strict';
const { spawnSync } = require('child_process');
const path = require('path');

const RAIZ = __dirname;

const SUITES = [
  ['Apps Script — lógica de la app anterior', 'apps-script/test/run-tests.js'],
  ['Apps Script — credenciales y token por cliente', 'apps-script/test/clientes.test.js'],
  ['Apps Script — contrato de Depot', 'apps-script/test/proxy.test.js'],
  ['Navegador — acceso, normalización e informe', 'firebase/test/app.test.mjs'],
  ['Navegador — páginas: sintaxis, imports y referencias', 'firebase/test/paginas.test.mjs'],
  ['Referencia — motor de conteo', 'firebase/functions/test/conteo.test.js'],
  ['Referencia — administración', 'firebase/functions/test/admin.test.js'],
  ['Referencia — token', 'firebase/functions/test/token.test.js'],
  ['Referencia — adaptador de Depot', 'firebase/functions/test/depot-itsanet.test.js'],
];

let pasadas = 0, falladas = 0, suitesRotas = 0;

for (const [titulo, archivo] of SUITES) {
  console.log('\n\x1b[1m── ' + titulo + '\x1b[0m  (' + archivo + ')');
  const r = spawnSync(process.execPath, [path.join(RAIZ, archivo)], {
    cwd: RAIZ, encoding: 'utf8',
  });

  const salida = (r.stdout || '') + (r.stderr || '');
  const m = salida.match(/(\d+)\s+pasadas,\s+(\d+)\s+falladas/);

  if (m) {
    pasadas += Number(m[1]);
    falladas += Number(m[2]);
    // Solo se imprimen las que fallan: en verde no interesa el detalle.
    if (Number(m[2]) > 0) {
      console.log(salida.split('\n').filter((l) => /FALLA/.test(l)).join('\n'));
      console.log('\x1b[31m   ' + m[1] + ' pasadas, ' + m[2] + ' FALLADAS\x1b[0m');
    } else {
      console.log('\x1b[32m   ' + m[1] + ' pasadas\x1b[0m');
    }
  } else {
    suitesRotas++;
    console.log('\x1b[31m   No se pudo ejecutar:\x1b[0m');
    console.log(salida.split('\n').slice(0, 6).map((l) => '   ' + l).join('\n'));
  }
}

console.log('\n' + '─'.repeat(58));
if (falladas || suitesRotas) {
  console.log('\x1b[31m\x1b[1m  ' + pasadas + ' pasadas, ' + falladas + ' falladas' +
    (suitesRotas ? ', ' + suitesRotas + ' suite(s) sin ejecutar' : '') + '\x1b[0m');
  process.exit(1);
}
console.log('\x1b[32m\x1b[1m  ' + pasadas + ' pruebas, todas en verde\x1b[0m');
