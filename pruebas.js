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
  ['Apps Script — puente autenticado del servidor', 'apps-script/test/servidor.test.js'],
  ['Apps Script — contrato de Depot', 'apps-script/test/proxy.test.js'],
  ['Navegador — acceso, normalización e informe', 'firebase/test/app.test.mjs'],
  ['Usuarios — registro y aprobación en nube y servidor', 'firebase/test/usuarios.test.mjs'],
  ['Usuarios — permisos de aprobación', 'firebase/test/reglas.test.mjs'],
  ['Navegador — páginas: sintaxis, imports y referencias', 'firebase/test/paginas.test.mjs'],
  ['Formato — el informe devuelve el packing list igual', 'firebase/test/formato.test.mjs'],
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

// --- El servidor local (Python) ------------------------------------------- //
//
// Va aquí y no en un comando aparte porque una suite que hay que acordarse de
// lanzar es una suite que no se lanza. Si no está pytest, se dice y se sigue:
// quien trabaja solo en la parte del navegador no tiene por qué instalarlo.
console.log('\n\x1b[1m── Servidor local — API, migración y esquema MySQL\x1b[0m  (tests/)');
const py = spawnSync('python3', ['-m', 'pytest', 'tests', '-q'],
  { cwd: RAIZ, encoding: 'utf8' });
const salidaPy = (py.stdout || '') + (py.stderr || '');

if (/No module named pytest|No module named 'pytest'/.test(salidaPy) || py.error) {
  console.log('\x1b[33m   Sin pytest: no se ejecutaron. '
    + 'pip install -r requirements.txt\x1b[0m');
} else {
  const mp = salidaPy.match(/(\d+) passed/);
  const mf = salidaPy.match(/(\d+) failed/);
  if (mp || mf) {
    pasadas += mp ? Number(mp[1]) : 0;
    falladas += mf ? Number(mf[1]) : 0;
    if (mf) {
      console.log(salidaPy.split('\n').filter((l) => /FAILED/.test(l)).join('\n'));
      console.log('\x1b[31m   ' + (mp ? mp[1] : 0) + ' pasadas, ' + mf[1] + ' FALLADAS\x1b[0m');
    } else {
      console.log('\x1b[32m   ' + mp[1] + ' pasadas\x1b[0m');
    }
  } else {
    suitesRotas++;
    console.log('\x1b[31m   No se pudo ejecutar:\x1b[0m');
    console.log(salidaPy.split('\n').slice(0, 6).map((l) => '   ' + l).join('\n'));
  }
}

console.log('\n' + '─'.repeat(58));
if (falladas || suitesRotas) {
  console.log('\x1b[31m\x1b[1m  ' + pasadas + ' pasadas, ' + falladas + ' falladas' +
    (suitesRotas ? ', ' + suitesRotas + ' suite(s) sin ejecutar' : '') + '\x1b[0m');
  process.exit(1);
}
console.log('\x1b[32m\x1b[1m  ' + pasadas + ' pruebas, todas en verde\x1b[0m');
