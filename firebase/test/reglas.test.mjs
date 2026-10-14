#!/usr/bin/env node
/**
 * Las reglas de Firestore.   node firebase/test/reglas.test.mjs
 *
 * Aquí no hay emulador: estas pruebas no dicen que las reglas hagan lo que se
 * quiere, dicen que no se ha vuelto a cometer un error concreto que ya costó
 * caro. Vale la pena porque las reglas se despliegan aparte de la aplicación y
 * un error en ellas no se ve hasta que alguien, en la bodega, pulsa un botón
 * que no hace nada.
 *
 * El caso que las trajo: `usuarios` permitía escribir solo a `esAdmin()`, pero
 * la pantalla de usuarios la ven los supervisores y el registro abierto nace
 * desactivado esperando aprobación. Resultado: el supervisor veía la cola de
 * pendientes y el botón de aprobar le fallaba en silencio.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, eq, ok, resumen } from './cargador.mjs';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const REGLAS = fs.readFileSync(path.join(AQUI, '..', 'firestore.rules'), 'utf8');

/** El cuerpo de un bloque `match /coleccion/{x} { … }`, con sus llaves contadas. */
function bloque(coleccion) {
  const i = REGLAS.indexOf(`match /${coleccion}/`);
  ok(i > 0, `no hay bloque para ${coleccion}`);
  // El primer `{` de la línea es el de `{uid}`, no el del bloque: el del bloque
  // es el último antes del salto de línea.
  const fin = REGLAS.indexOf('\n', i);
  let nivel = 0, j = REGLAS.lastIndexOf('{', fin);
  for (let k = j; k < REGLAS.length; k++) {
    if (REGLAS[k] === '{') nivel++;
    else if (REGLAS[k] === '}' && --nivel === 0) return REGLAS.slice(j + 1, k);
  }
  throw new Error(`el bloque de ${coleccion} no cierra`);
}

/** La regla `allow x, y: if …;` de un bloque. */
function permiso(cuerpo, verbo) {
  const re = new RegExp(`allow[^:;]*\\b${verbo}\\b[^:]*:([\\s\\S]*?);`, 'm');
  const m = cuerpo.match(re);
  if (!m) return null;
  return m[1].replace(/\/\/[^\n]*/g, ' ').replace(/\s+/g, ' ')
             .replace(/^\s*if\s+/, '').trim();
}

await test('el archivo está equilibrado: cada llave cierra', () => {
  const sin = REGLAS.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
  let nivel = 0;
  for (const c of sin) {
    if (c === '{') nivel++;
    else if (c === '}') nivel--;
    ok(nivel >= 0, 'cierra una llave que nadie abrió');
  }
  eq(nivel, 0, 'quedan llaves abiertas: las reglas no se despliegan');
});

await test('un supervisor puede aprobar y corregir usuarios', () => {
  const u = permiso(bloque('usuarios'), 'update');
  ok(u, 'sin regla de update no se aprueba a nadie');
  ok(/esSupervisor\(\)/.test(u),
     'volvió a quedarse en esAdmin(): el supervisor ve la cola y no puede con ella');
});

await test('pero el rol se lo cambia solo un administrador', () => {
  const u = permiso(bloque('usuarios'), 'update');
  ok(/esAdmin\(\)/.test(u), 'alguien tiene que ser el que reparte permisos');
  ok(/request\.resource\.data\.rol == resource\.data\.rol/.test(u),
     'si el supervisor puede tocar el rol, puede hacerse administrador');
});

await test('la identidad de una ficha no se edita', () => {
  const u = permiso(bloque('usuarios'), 'update');
  ok(/request\.resource\.data\.uid == resource\.data\.uid/.test(u), 'el uid');
  ok(/request\.resource\.data\.email == resource\.data\.email/.test(u),
     'el correo: cambiarlo sería entregarle la cuenta de alguien a otra persona');
});

await test('nadie se queda sin administradores por un descuido', () => {
  const u = permiso(bloque('usuarios'), 'update');
  ok(/request\.auth\.uid == uid/.test(u),
     'falta el cierre de no quitarse a uno mismo el rol ni el acceso');
});

await test('una ficha no se borra: se desactiva', () => {
  eq(permiso(bloque('usuarios'), 'delete'), 'false',
     'borrarla dejaría conteos firmados por un uid que ya no existe');
});

await test('el alias se puede consultar sin sesión, pero no listar', () => {
  const a = bloque('alias');
  eq(permiso(a, 'get'), 'true', 'el operario escribe su usuario antes de entrar');
  eq(permiso(a, 'list'), 'false', 'listarlo sería sacar el directorio de la empresa');
});

await test('un supervisor que renombra a alguien puede mover su alias', () => {
  const a = bloque('alias');
  ok(/esSupervisor\(\)/.test(permiso(a, 'create') || ''),
     'sin esto le cambia el usuario en la ficha y la persona se queda fuera');
  ok(/esSupervisor\(\)|esAdmin\(\)/.test(permiso(a, 'update') || ''));
});

await test('ningún bloque está abierto de par en par', () => {
  for (const m of REGLAS.matchAll(/allow\s+([a-z, ]+):\s*if\s+true\s*;/g)) {
    const verbos = m[1].replace(/\s/g, '');
    ok(verbos === 'get',
       `«allow ${verbos}: if true» deja la colección al aire (solo alias/get lo tiene a propósito)`);
  }
});

resumen();
