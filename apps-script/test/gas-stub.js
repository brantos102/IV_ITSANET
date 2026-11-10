/**
 * Simulador minimo de los servicios de Apps Script, suficiente para ejecutar
 * los .gs reales en Node y probar la logica sin desplegar nada.
 *
 * Solo implementa lo que el codigo usa: hojas en memoria, candado, cache y uuid.
 */
'use strict';

class Range {
  constructor(hoja, fila, col, nFilas, nCols) {
    Object.assign(this, { hoja, fila, col, nFilas, nCols });
  }
  getValues() {
    const out = [];
    for (let r = 0; r < this.nFilas; r++) {
      const fila = [];
      for (let c = 0; c < this.nCols; c++) {
        fila.push(this.hoja._celda(this.fila + r, this.col + c));
      }
      out.push(fila);
    }
    return out;
  }
  getValue() { return this.hoja._celda(this.fila, this.col); }
  setValue(v) { this.hoja._set(this.fila, this.col, v); return this; }
  setValues(m) {
    m.forEach((fila, r) => fila.forEach((v, c) => this.hoja._set(this.fila + r, this.col + c, v)));
    return this;
  }
  setFontWeight() { return this; }
  setBackground() { return this; }
  getRichTextValues() {
    return this.getValues().map((f) => f.map(() => ({ getLinkUrl: () => null })));
  }
}

class Sheet {
  constructor(nombre, datos) { this.nombre = nombre; this.datos = datos || []; }
  getName() { return this.nombre; }
  _celda(f, c) {
    const fila = this.datos[f - 1];
    const v = fila ? fila[c - 1] : '';
    return v === undefined ? '' : v;
  }
  _set(f, c, v) {
    while (this.datos.length < f) this.datos.push([]);
    const fila = this.datos[f - 1];
    while (fila.length < c) fila.push('');
    fila[c - 1] = v;
  }
  getLastRow() { return this.datos.length; }
  getLastColumn() { return this.datos.reduce((m, f) => Math.max(m, f.length), 0); }
  getRange(f, c, nf, nc) { return new Range(this, f, c, nf || 1, nc || 1); }
  getDataRange() { return new Range(this, 1, 1, this.getLastRow() || 1, this.getLastColumn() || 1); }
  appendRow(fila) { this.datos.push(fila.slice()); }
  clear() { this.datos = []; }
  setFrozenRows() { return this; }
}

class Spreadsheet {
  constructor(id, hojas) { this.id = id; this.hojas = hojas || []; }
  getSheets() { return this.hojas; }
  getSheetByName(n) { return this.hojas.find((h) => h.getName() === n) || null; }
  insertSheet(n) { const h = new Sheet(n); this.hojas.push(h); return h; }
}

const libros = new Map();
let contadorUuid = 0;
const correosEnviados = [];

const stub = {
  Sheet, Spreadsheet, libros, correosEnviados,
  registrarLibro(id, hojas) { const s = new Spreadsheet(id, hojas); libros.set(id, s); return s; },
  reset() { libros.clear(); correosEnviados.length = 0; contadorUuid = 0; },
};

function instalar(global) {
  global.SpreadsheetApp = {
    openById(id) {
      const s = libros.get(id);
      if (!s) throw new Error(`No existe el libro ${id}`);
      return s;
    },
  };
  global.DriveApp = {
    createFile: () => ({ getId: () => 'nuevo', getUrl: () => 'http://x', setTrashed: () => {} }),
  };
  global.Utilities = {
    getUuid: () => `uuid-${++contadorUuid}`,
    formatDate: (d, tz, fmt) => {
      const p = (n) => String(n).padStart(2, '0');
      if (fmt.indexOf("'T'") > -1) {
        return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T` +
               `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
      }
      if (fmt.indexOf('dd/MM') === 0) {
        return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
      }
      return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-` +
             `${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
    },
    newBlob: () => ({}),
    base64Decode: () => [],
  };
  global.Session = {
    getScriptTimeZone: () => 'America/Guayaquil',
    getEffectiveUser: () => ({ getEmail: () => 'gerencia@itsanet.com' }),
    getActiveUser: () => ({ getEmail: () => 'operario@itsanet.com' }),
  };
  // Candado real de un solo hilo: detecta reentradas, que en Apps Script
  // significarian dos ejecuciones concurrentes sin proteccion.
  let tomado = false;
  global.LockService = {
    getScriptLock: () => ({
      tryLock: () => { if (tomado) return false; tomado = true; return true; },
      releaseLock: () => { tomado = false; },
    }),
    _estaTomado: () => tomado,
  };
  global.CacheService = {
    getScriptCache: () => ({ get: () => null, put: () => {}, remove: () => {} }),
  };
  global.MailApp = { sendEmail: (o) => correosEnviados.push(o) };
  global.HtmlService = {
    createHtmlOutputFromFile: () => ({
      setTitle() { return this; }, setXFrameOptionsMode() { return this; },
      addMetaTag() { return this; },
    }),
    XFrameOptionsMode: { ALLOWALL: 1 },
  };
  return global;
}

/** Carga los .gs en el contexto global de Node, en orden de dependencia. */
function cargarFuentes(dir, archivos) {
  const fs = require('fs');
  const path = require('path');
  const vm = require('vm');
  instalar(global);
  const ctx = vm.createContext(global);
  for (const a of archivos) {
    const codigo = fs.readFileSync(path.join(dir, a), 'utf8');
    vm.runInContext(codigo, ctx, { filename: a });
  }
  return ctx;
}

module.exports = { ...stub, instalar, cargarFuentes };
