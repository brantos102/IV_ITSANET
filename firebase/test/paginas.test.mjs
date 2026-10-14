#!/usr/bin/env node
/**
 * Comprobaciones estáticas de las páginas.   node firebase/test/paginas.test.mjs
 *
 * Nada de esto lo detecta una prueba unitaria: son errores que solo aparecen al
 * abrir la página en un navegador, y que en un almacén significan un operario
 * parado delante de una pantalla en blanco.
 *
 *   - Sintaxis de cada módulo y de cada <script> incrustado.
 *   - Que lo que un archivo importa exista de verdad en el que lo exporta.
 *   - Que cada $('id') tenga su elemento en el HTML.
 *   - Que los <script> sueltos no usen nada del módulo: no lo ven.
 *   - Que los archivos referenciados existan.
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

import { fileURLToPath } from 'node:url';
const RAIZ = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'public');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'chk-'));
let fallos = 0, revisiones = 0;
const malo = (m) => { fallos++; console.log('  FALLA ' + m); };
const bien = (m) => { console.log('  ok    ' + m); };

function sintaxis(nombre, codigo) {
  const f = path.join(tmp, nombre.replace(/[^\w]/g, '_') + '.mjs');
  fs.writeFileSync(f, codigo);
  try { execFileSync(process.execPath, ['--check', f], { stdio: 'pipe' }); return true; }
  catch (e) { malo(`${nombre}: ${String(e.stderr).split('\n').slice(0,4).join(' ')}`); return false; }
}

// --- módulos js --- //
const exportados = {};
for (const f of fs.readdirSync(path.join(RAIZ, 'js'))) {
  if (!f.endsWith('.js')) continue;
  const codigo = fs.readFileSync(path.join(RAIZ, 'js', f), 'utf8');
  revisiones++;
  sintaxis('js/' + f, codigo);
  const nombres = new Set();
  for (const m of codigo.matchAll(/^export\s+(?:async\s+)?(?:function|class)\s+(\w+)/gm)) nombres.add(m[1]);
  for (const m of codigo.matchAll(/^export\s+(?:const|let|var)\s+(\w+)/gm)) nombres.add(m[1]);
  for (const m of codigo.matchAll(/^export\s*\{([^}]+)\}/gm))
    m[1].split(',').forEach((n) => nombres.add(n.trim().split(/\s+as\s+/).pop()));
  exportados['./' + f] = nombres;
  exportados['/js/' + f] = nombres;
}

/**
 * Usar algo de un módulo sin importarlo.
 *
 * Es el error que se cuela: se añade una llamada a `decodificarPallets(...)` y
 * se olvida la línea del import. No falla al cargar la página —solo cuando se
 * ejecuta esa función—, así que aparece delante del operario a mitad de turno
 * y no en ninguna comprobación.
 *
 * Se mira solo contra los nombres que de verdad exportan los módulos del
 * proyecto, así que no hay falsos positivos con variables locales.
 */
function usaSinImportar(etiqueta, codigo) {
  const importados = new Set();
  for (const m of codigo.matchAll(/import\s*\{([^}]+)\}\s*from/g)) {
    m[1].split(',').forEach((n) => {
      const nombre = n.trim().split(/\s+as\s+/).pop();
      if (nombre) importados.add(nombre);
    });
  }

  // Lo que el propio script define no necesita importarse.
  const propios = new Set();
  for (const m of codigo.matchAll(/(?:^|\n)\s*(?:async\s+)?function\s+(\w+)/g)) propios.add(m[1]);
  for (const m of codigo.matchAll(/(?:^|\n)\s*(?:const|let|var)\s+(\w+)/g)) propios.add(m[1]);

  const todosLosExportados = new Set();
  for (const nombres of Object.values(exportados)) {
    for (const n of nombres) todosLosExportados.add(n);
  }

  for (const nombre of todosLosExportados) {
    if (importados.has(nombre) || propios.has(nombre)) continue;
    // Como llamada o como referencia, pero no dentro de otra palabra.
    const usa = new RegExp(`(^|[^\\w.$'"\`])${nombre}\\s*\\(`, 'm');
    if (usa.test(codigo)) {
      malo(`${etiqueta}: usa ${nombre}() sin importarlo`);
    }
  }
}

function revisarImports(etiqueta, codigo, base) {
  for (const m of codigo.matchAll(/import\s*\{([^}]+)\}\s*from\s*['"]([^'"]+)['"]/g)) {
    const ruta = m[2];
    if (ruta.startsWith('http')) continue;
    const resuelta = ruta.replace(/^\.\/js\//, './').replace(/^\.\//, './');
    const clave = Object.keys(exportados).find((k) => k.endsWith(path.basename(ruta)));
    if (!clave) { malo(`${etiqueta}: módulo no encontrado ${ruta}`); continue; }
    for (const nombre of m[1].split(',').map((s) => s.trim().split(/\s+as\s+/)[0]).filter(Boolean)) {
      if (!exportados[clave].has(nombre)) malo(`${etiqueta}: '${nombre}' no está exportado por ${ruta}`);
    }
  }
}

for (const f of fs.readdirSync(path.join(RAIZ, 'js'))) {
  if (!f.endsWith('.js')) continue;
  const antes = fallos;
  revisarImports('js/' + f, fs.readFileSync(path.join(RAIZ, 'js', f), 'utf8'));
  if (fallos === antes) bien('js/' + f);
}

// --- html --- //
for (const f of fs.readdirSync(RAIZ)) {
  if (!f.endsWith('.html')) continue;
  const html = fs.readFileSync(path.join(RAIZ, f), 'utf8');
  revisiones++;
  const antes = fallos;
  const ids = new Set([...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]));
  const guiones = [...html.matchAll(/<script\s+type="module"[^>]*>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
  guiones.forEach((g, i) => {
    sintaxis(`${f}#${i}`, g);
    revisarImports(`${f}#${i}`, g);
    usaSinImportar(`${f}#${i}`, g);
    for (const m of g.matchAll(/(?:getElementById|\$)\(\s*['"]([\w-]+)['"]\s*\)/g)) {
      if (!ids.has(m[1])) malo(`${f}: $('${m[1]}') no existe en el HTML`);
    }
  });

  // Un <form> sin manejador de «submit» es una trampa silenciosa: el botón de
  // enviar y la tecla «Ir» del teclado del móvil hacen que el navegador envíe
  // el formulario DE VERDAD. La página se recarga y, si los campos no llevan
  // «name», la dirección se queda sin sus parámetros. Así se perdía el «?r=»
  // de la recepción a mitad de una validación, y solo en el móvil, que es
  // donde se toca el botón en vez de pulsar Intro.
  const sinComentarios = html.replace(/<!--[\s\S]*?-->/g, '');
  for (const m of sinComentarios.matchAll(/<form\b([^>]*)>/g)) {
    const id = (m[1].match(/\sid="([^"]+)"/) || [])[1];
    if (!id) {
      malo(`${f}: hay un <form> sin id; no se le puede enganchar el submit`);
      continue;
    }
    const engancha = new RegExp(
      `\\$\\(\\s*['"]${id}['"]\\s*\\)\\.addEventListener\\(\\s*['"]submit['"]`);
    const guion = guiones.find((g) => engancha.test(g));
    if (!guion) {
      malo(`${f}: el <form id="${id}"> no escucha «submit»; al enviarlo el `
         + `navegador recarga la página y se pierden los parámetros de la URL`);
    } else if (!/preventDefault/.test(guion.slice(guion.search(engancha),
                                                  guion.search(engancha) + 400))) {
      malo(`${f}: el submit de <form id="${id}"> no llama a preventDefault()`);
    }
  }

  // Los <script> sueltos solo llevan el registro del service worker. Si crece,
  // es que se coló ahí código del módulo: ese script no ve $ ni esc, y revienta
  // en tiempo de ejecución con un ReferenceError que no aparece en ninguna
  // comprobación estática.
  for (const m of html.matchAll(/<script>([\s\S]*?)<\/script>/g)) {
    const cuerpo = m[1];
    sintaxis(`${f}#suelto`, cuerpo);
    for (const ident of ['$(', 'esc(', 'aviso(']) {
      if (cuerpo.includes(ident)) {
        malo(`${f}: un <script> sin type="module" usa ${ident}…) — eso vive en el módulo`);
      }
    }
    if (cuerpo.split('\n').filter((l) => l.trim()).length > 12) {
      malo(`${f}: hay un <script> suelto con demasiado código; ¿debería ir en el módulo?`);
    }
  }
  // referencias a archivos locales
  for (const m of html.matchAll(/(?:src|href)="(\/[^"]+)"/g)) {
    const p = path.join(RAIZ, m[1].split("#")[0].split("?")[0]);
    if (!m[1].includes("${") && !fs.existsSync(p) && !m[1].startsWith("/data:")) malo(`${f}: falta el archivo ${m[1]}`);
  }
  // XLSX usado sin cargar la librería
  if (guiones.some((g) => /\bXLSX\b/.test(g)) && !/sheetjs|xlsx\.full|xlsx\.min/i.test(html)) {
    malo(`${f}: usa XLSX pero no carga SheetJS`);
  }

  if (fallos === antes) bien(f);
}

// Mismo formato que el resto de suites, para que el runner lo sume.
console.log(`\n  ${revisiones - fallos} pasadas, ${fallos} falladas`);
process.exit(fallos ? 1 : 0);
