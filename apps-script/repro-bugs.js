#!/usr/bin/env node
/**
 * Reproduce los tres defectos criticos de Index.html descritos en
 * PARCHE-CRITICO.md, sin necesidad de desplegar la app.
 *
 *   node repro-bugs.js ruta/al/Index.html
 *
 * Los IDs del DOM se leen del archivo real, asi que la prueba sigue siendo
 * valida despues de aplicar el parche: entonces debe imprimir OK en los tres.
 */
const fs = require('fs');

const ruta = process.argv[2] || './Index.html';
if (!fs.existsSync(ruta)) {
  console.error(`No existe: ${ruta}\nUso: node repro-bugs.js ruta/al/Index.html`);
  process.exit(1);
}
const html = fs.readFileSync(ruta, 'utf8');

// DOM minimo: solo responden los IDs que realmente estan en el HTML.
const idsEnHtml = new Set([...html.matchAll(/id="([^"]+)"/g)].map((m) => m[1]));
const doc = {
  getElementById: (id) =>
    idsEnHtml.has(id) ? { innerText: '', style: {}, className: '', value: '' } : null,
};

let fallos = 0;

// --- 1. playSound definida? -------------------------------------------------
const llamadas = (html.match(/playSound\(/g) || []).length;
const definida = /function\s+playSound|playSound\s*=\s*function|const\s+playSound/.test(html);
if (!definida && llamadas > 0) {
  fallos++;
  console.log(`BUG 1  playSound se invoca ${llamadas} veces y NO esta definida.`);
  console.log('       Toda rama de manejarEscaneo la llama antes de sincronizarCelda,');
  console.log('       asi que ningun escaneo llega a guardarse en el Google Sheet.');
} else {
  console.log('OK  1  playSound definida.');
}

// --- 2. calcularKPIs contra el DOM real -------------------------------------
function calcularKPIs(currentData) {
  let totales = 0, completadas = 0, uEsperadas = 0, uFisicas = 0;
  currentData.forEach((i) => {
    if (!i.referencia) return;
    totales++;
    const e = parseFloat(i.esperada) || 0;
    const f = parseFloat(i.fisica) || 0;
    uEsperadas += e; uFisicas += f;
    if (f === e && e !== 0) completadas++;
  });
  // Linea 854 del archivo original:
  doc.getElementById('kpiTotal').innerText = totales;
  doc.getElementById('kpiUnidadesEsperadas').innerText = uEsperadas;
  return { totales, completadas, pendientes: totales - completadas };
}

try {
  const r = calcularKPIs([
    { referencia: '7210002ADU0600', esperada: 1, fisica: 1 },
    { referencia: '7185012ASV0000M10', esperada: 2, fisica: 3 },
  ]);
  console.log('OK  2  calcularKPIs completa:', JSON.stringify(r));
} catch (e) {
  fallos++;
  console.log(`BUG 2  calcularKPIs lanza ${e.constructor.name}: ${e.message}`);
  console.log('       La barra de progreso, el texto "x / y Refs" y el grafico');
  console.log('       quedan congelados en 0, con las filas ya validadas.');
}

// --- 3. .find() sobre SKU repetidos ----------------------------------------
// 6Q09598589B9 ocupa las filas 16, 17 y 18 del packing list real (2+1+1 = 4).
const packingList = [
  { fila: 16, referencia: '6Q09598589B9', esperada: 2, fisica: 0 },
  { fila: 17, referencia: '6Q09598589B9', esperada: 1, fisica: 0 },
  { fila: 18, referencia: '6Q09598589B9', esperada: 1, fisica: 0 },
];
const esperadoReal = packingList.reduce((a, b) => a + b.esperada, 0);
const usaFind = /currentData\.find\(/.test(html);
const hit = packingList.find((i) => String(i.referencia).toUpperCase() === '6Q09598589B9');

if (usaFind) {
  fallos++;
  console.log('BUG 3  manejarEscaneo usa currentData.find(): toma solo la primera linea.');
  console.log(`       Esperado real del SKU: ${esperadoReal} · el que ve la app: ${hit.esperada}`);
  console.log(`       Las filas ${packingList.slice(1).map((f) => f.fila).join(' y ')} quedan en 0:`);
  console.log('       faltantes fantasma en el reporte final.');
} else {
  console.log('OK  3  el escaneo ya no depende de currentData.find().');
}

console.log(`\n${fallos === 0 ? 'Sin defectos conocidos.' : fallos + ' defecto(s) presente(s).'}`);
process.exit(fallos === 0 ? 0 : 1);
