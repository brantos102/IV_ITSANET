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

/** El codigo sin comentarios: una regla no puede saltar por un comentario. */
function sinComentar(codigo) {
  return codigo.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/(^|[^:])\/\/[^\n]*/g, '$1');
}

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

/**
 * El codigo sin cadenas ni comentarios, y para cada caracter que queda, si el
 * parentesis mas cercano que lo envuelve es una llave.
 *
 * Hace falta para no confundir f(a, b) con { a, b }: en el primero b es un
 * argumento y en el segundo es un nombre abreviado. Sin esta distincion la
 * comprobacion de abajo avisaba de cualquier funcion de dos argumentos.
 *
 * No es un analizador de JavaScript: solo sigue comillas, plantillas y
 * parentesis, que es lo justo para esto.
 */
function enLlaves(codigo) {
  let fuera = '';
  const marca = [];
  const pila = [];        // '(' '[' '{' y '`' para plantillas
  const poner = (c) => { fuera += c; marca.push(pila[pila.length - 1] === '{'); };

  let i = 0;
  while (i < codigo.length) {
    const c = codigo[i];
    const d = codigo[i + 1];

    // Dentro de una plantilla: el texto se tira y solo interesa lo de ${...}.
    // El ${ se apila como llave, asi que su } vuelve solo al texto, y una
    // plantilla dentro de otra se apila otra vez. Sin esto, el primer } de una
    // plantilla anidada daba por cerrada la de fuera y el resto del archivo se
    // leia corrido.
    if (pila[pila.length - 1] === '`') {
      if (c === '\\') { i += 2; continue; }
      if (c === '`') { pila.pop(); poner(' '); i++; continue; }
      if (c === '$' && d === '{') { pila.push('{'); poner(' '); i += 2; continue; }
      i++; continue;
    }

    if (c === '/' && d === '/') { while (i < codigo.length && codigo[i] !== '\n') i++; continue; }
    if (c === '/' && d === '*') {
      i += 2;
      while (i < codigo.length && !(codigo[i] === '*' && codigo[i + 1] === '/')) i++;
      i += 2; continue;
    }
    if (c === '"' || c === "'") {
      i++;
      while (i < codigo.length && codigo[i] !== c) i += codigo[i] === '\\' ? 2 : 1;
      i++; poner(' '); continue;
    }
    // Un literal de expresion regular. Hay que reconocerlo porque dentro lleva
    // comillas y corchetes: el /[&<>"']/g de esc() abria una cadena falsa que se
    // comia el resto del archivo, y con el se iba toda la comprobacion.
    //
    // Que / abra una regex o sea una division se decide por lo ultimo que vino:
    // despues de un valor es division; despues de un operador o un signo de
    // apertura, regex. Es la regla de siempre y aqui basta.
    if (c === '/') {
      const antes = fuera.replace(/\s+$/, '').slice(-1);
      const palabra = /\b(return|typeof|case|in|of|delete|void|instanceof|do|else)$/
        .test(fuera.replace(/\s+$/, ''));
      if (!antes || palabra || '([{,;:=!&|?+-*%<>~^'.includes(antes)) {
        i++;
        let clase = false;
        while (i < codigo.length) {
          if (codigo[i] === '\\') { i += 2; continue; }
          if (codigo[i] === '[') clase = true;
          else if (codigo[i] === ']') clase = false;
          else if (codigo[i] === '/' && !clase) { i++; break; }
          else if (codigo[i] === '\n') break;          // no era una regex
          i++;
        }
        while (/[a-z]/.test(codigo[i] || '')) i++;     // las banderas
        poner(' '); continue;
      }
    }
    if (c === '`') { pila.push('`'); poner(' '); i++; continue; }
    if (c === '{' || c === '(' || c === '[') { poner(c); pila.push(c); i++; continue; }
    if (c === '}' || c === ')' || c === ']') { pila.pop(); poner(c); i++; continue; }
    poner(c); i++;
  }
  return { fuera, marca };
}

/**
 * Nombres que el propio archivo declara: importados, declarados, parametros.
 *
 * No es un analisis de ambitos de verdad; se queda del lado de no avisar. Un
 * nombre declarado en cualquier sitio del archivo cuenta como declarado en
 * todos, asi que de aqui no salen falsos positivos por anidamiento.
 */
function declarados(codigo) {
  const n = new Set();
  const anadir = (txt) => String(txt || '').split(',').forEach((t) => {
    // «a as b» y «a: b» enlazan a b; «a = 1» declara a.
    const m = t.split(/\s+as\s+|:/).pop().split('=')[0]
      .replace(/[[\]{}.]/g, ' ').trim().split(/\s+/);
    m.forEach((x) => { if (/^[A-Za-z_$][\w$]*$/.test(x)) n.add(x); });
  });

  for (const m of codigo.matchAll(/import\s+([^'"]+?)\s+from/g)) anadir(m[1].replace(/[{}*]/g, ' '));
  for (const m of codigo.matchAll(/\b(?:const|let|var)\s+([^=;\n]+)/g)) anadir(m[1]);
  for (const m of codigo.matchAll(/\bfunction\s*\*?\s*([\w$]+)/g)) n.add(m[1]);
  for (const m of codigo.matchAll(/\bclass\s+([\w$]+)/g)) n.add(m[1]);
  for (const m of codigo.matchAll(/\bcatch\s*\(\s*([\w$]+)/g)) n.add(m[1]);
  for (const m of codigo.matchAll(/\bfor\s*\(\s*(?:const|let|var)\s+([^;)]+?)\s+(?:of|in)\b/g)) anadir(m[1]);
  for (const m of codigo.matchAll(/\bfunction\s*\*?\s*[\w$]*\s*\(([^)]*)\)/g)) anadir(m[1]);
  for (const m of codigo.matchAll(/\(([^()]*)\)\s*=>/g)) anadir(m[1]);
  for (const m of codigo.matchAll(/(?:^|[^\w$.)])([\w$]+)\s*=>/g)) n.add(m[1]);
  return n;
}

const GLOBALES = new Set((
  'window document navigator location history console setTimeout clearTimeout '
+ 'setInterval clearInterval requestAnimationFrame fetch URL Blob File FileReader '
+ 'FormData Headers Request Response AbortController Promise Array Object String '
+ 'Number Boolean Math JSON Date RegExp Map Set WeakMap WeakSet Symbol Error '
+ 'TypeError RangeError Intl Infinity NaN undefined null true false parseInt '
+ 'parseFloat isNaN isFinite encodeURIComponent decodeURIComponent atob btoa '
+ 'localStorage sessionStorage indexedDB crypto performance alert confirm prompt '
+ 'XLSX jspdf html2canvas addEventListener removeEventListener globalThis self '
+ 'Audio Image Event CustomEvent MutationObserver IntersectionObserver '
+ 'BarcodeDetector MediaRecorder AudioContext speechSynthesis structuredClone'
).split(' '));

/**
 * Un nombre suelto dentro de un objeto —{ version }— que no existe en ninguna
 * parte del archivo.
 *
 * En un modulo eso no es undefined: es un ReferenceError que tumba la funcion
 * entera. Asi se habia quedado el cierre de recepciones, que llamaba a
 * construirLibro(datos, { version }) con una variable que nadie declaraba: la
 * recepcion no llegaba a cerrarse nunca y no lo veia ninguna comprobacion.
 */
function abreviadoSinDeclarar(etiqueta, codigo) {
  const { fuera, marca } = enLlaves(codigo);
  const hay = declarados(fuera);
  const avisados = new Set();
  for (const m of fuera.matchAll(/[{,]\s*([A-Za-z_$][\w$]*)\s*[,}]/g)) {
    const nombre = m[1];
    // Se mira la marca del NOMBRE, no la del caracter de delante: ese esta
    // todavia en el ambito de fuera, y con el { version } de una llamada
    // —construirLibro(datos, { version })— la comprobacion se saltaba justo el
    // caso que la motivo.
    if (!marca[m.index + m[0].indexOf(nombre)]) continue;   // lista de argumentos
    if (hay.has(nombre) || GLOBALES.has(nombre) || avisados.has(nombre)) continue;
    avisados.add(nombre);
    malo(`${etiqueta}: { ${nombre} } no esta declarado en el archivo `
       + '— en un modulo eso es un ReferenceError, no un undefined');
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
    abreviadoSinDeclarar(`${f}#${i}`, g);
    for (const m of g.matchAll(/(?:getElementById|\$)\(\s*['"]([\w-]+)['"]\s*\)/g)) {
      if (!ids.has(m[1])) malo(`${f}: $('${m[1]}') no existe en el HTML`);
    }

    // confirm(), prompt() y alert() del navegador no valen en el handheld: salen
    // diminutos, se cierran de un toque y en algunos navegadores de Android
    // prompt() esta desactivado — el operario pulsa y no pasa nada. Para eso
    // esta js/modal.js.
    for (const m of sinComentar(g).matchAll(/(?<!\w)(?:window\.)?(confirm|prompt|alert)\s*\(/g)) {
      malo(`${f}: usa ${m[1]}() del navegador; usa js/modal.js`);
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
