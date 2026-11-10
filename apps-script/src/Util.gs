/**
 * Normalizacion y utilidades compartidas.
 *
 * Los datos reales traen basura que rompe los cruces: espacios no separables
 * ( ) delante del producto_id en el maestro, SKU en minuscula o con
 * guiones, acentos que el sistema Depot rechaza.
 */

/** Quita invisibles y espacios sobrantes. Nunca devuelve null. */
function limpiar_(valor) {
  if (valor === null || valor === undefined) return '';
  return String(valor)
      .replace(/[ ​‌‍﻿\t\r\n]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
}

/** Clave canonica de un SKU: sin invisibles ni separadores, en mayuscula. */
function normalizarSku_(valor) {
  return limpiar_(valor).toUpperCase().replace(/[\s\-_.]/g, '');
}

function normalizarEan_(valor) {
  return limpiar_(valor).toUpperCase().replace(/[^0-9A-Z]/g, '');
}

/** Pallet alfanumerico, subpallet con punto: A1, A1.1, B04.3 */
function normalizarPallet_(valor) {
  return limpiar_(valor).toUpperCase().replace(/[\s_\-]/g, '');
}

function palletValido_(codigo) {
  var c = normalizarPallet_(codigo);
  return !!c && c.length <= 40 && /^[A-Z0-9]+(\.[A-Z0-9]+)*$/.test(c);
}

function palletPadre_(codigo) {
  var c = normalizarPallet_(codigo);
  return c.indexOf('.') > -1 ? c.substring(0, c.lastIndexOf('.')) : null;
}

function sinAcentos_(texto) {
  return String(texto).normalize('NFD').replace(/[̀-ͯ]/g, '');
}

/** Texto apto para subir a Depot: regla "no caracteres especiales". */
function sanearCelda_(valor, maxLen) {
  var s = sinAcentos_(limpiar_(valor)).toUpperCase()
      .replace(/[^A-Z0-9 .\/\-,:+#%()]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  return s.substring(0, maxLen || 300);
}

function aNumero_(valor, porDefecto) {
  if (valor === null || valor === undefined || valor === '') return porDefecto || 0;
  if (typeof valor === 'number') return valor;
  var s = limpiar_(valor).replace(',', '.').replace(/[^0-9.\-]/g, '');
  var n = parseFloat(s);
  return isNaN(n) ? (porDefecto || 0) : n;
}

function uuid_() { return Utilities.getUuid(); }

function ahora_() { return new Date(); }

function fechaIso_(d) {
  return (d instanceof Date)
      ? Utilities.formatDate(d, Session.getScriptTimeZone(), "yyyy-MM-dd'T'HH:mm:ss")
      : String(d || '');
}

/** Respuesta uniforme para el cliente. */
function ok_(datos, mensaje) {
  var r = { exito: true };
  if (datos !== undefined) r.datos = datos;
  if (mensaje) r.mensaje = mensaje;
  return r;
}

function error_(mensaje, codigo) {
  return { exito: false, mensaje: String(mensaje), codigo: codigo || 'ERROR' };
}

/**
 * Ejecuta fn con el candado de escritura tomado.
 *
 * Sin esto, dos operadores guardando a la vez se pisan: es exactamente el
 * defecto del guardarFilaRecepcion anterior.
 */
function conCandado_(fn) {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(CFG.LOCK_MS)) {
    throw new Error('El sistema esta ocupado guardando otro conteo. Reintente.');
  }
  try {
    return fn();
  } finally {
    lock.releaseLock();
  }
}
