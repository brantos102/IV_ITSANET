/**
 * Normalizacion de codigos y texto.
 *
 * Los datos reales traen basura que rompe los cruces: espacios no separables
 * ( ) delante del producto_id en el maestro de Depot, codigos en minuscula
 * o con guiones, acentos que el WMS rechaza.
 */
'use strict';

const INVISIBLES = /[ ​‌‍﻿\t\r\n]/g;

function limpiar(valor) {
  if (valor === null || valor === undefined) return '';
  return String(valor).replace(INVISIBLES, ' ').replace(/\s+/g, ' ').trim();
}

/** Clave canonica de cualquier codigo: SKU, EAN o alterno. */
function normalizarCodigo(valor) {
  return limpiar(valor).toUpperCase().replace(/[\s\-_.]/g, '');
}

/** Pallet alfanumerico, subpallet con punto: A1, A1.1, B04.3 */
function normalizarPallet(valor) {
  return limpiar(valor).toUpperCase().replace(/[\s_-]/g, '');
}

function palletValido(codigo) {
  const c = normalizarPallet(codigo);
  return !!c && c.length <= 40 && /^[A-Z0-9]+(\.[A-Z0-9]+)*$/.test(c);
}

function palletPadre(codigo) {
  const c = normalizarPallet(codigo);
  return c.includes('.') ? c.slice(0, c.lastIndexOf('.')) : null;
}

function sinAcentos(texto) {
  return String(texto).normalize('NFD').replace(/[̀-ͯ]/g, '');
}

/** Texto apto para subir al WMS: regla "no caracteres especiales". */
function sanearCelda(valor, maxLen = 300) {
  return sinAcentos(limpiar(valor))
    .toUpperCase()
    .replace(/[^A-Z0-9 .\/\-,:+#%()]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, maxLen);
}

function aNumero(valor, porDefecto = 0) {
  if (valor === null || valor === undefined || valor === '') return porDefecto;
  if (typeof valor === 'number') return Number.isFinite(valor) ? valor : porDefecto;
  const n = parseFloat(limpiar(valor).replace(',', '.').replace(/[^0-9.\-]/g, ''));
  return Number.isNaN(n) ? porDefecto : n;
}

/**
 * Clave segura para usar un pallet como campo de un mapa de Firestore.
 *
 * Firestore interpreta el punto como separador de ruta: escribir
 * `pallets.B04.1` crea `pallets -> B04 -> 1`, no la clave "B04.1". Los
 * subpallets son justo los que llevan punto, asi que hay que codificarlos.
 *
 * Se usa `~` porque `palletValido` solo admite [A-Z0-9.]: no puede colisionar
 * con un pallet real.
 */
function clavePallet(pallet) {
  return normalizarPallet(pallet).replace(/\./g, '~');
}

function palletDesdeClave(clave) {
  return String(clave || '').replace(/~/g, '.');
}

/** Convierte el mapa guardado {B04~1: 2} al mapa real {B04.1: 2}. */
function decodificarPallets(mapa) {
  const salida = {};
  for (const [k, v] of Object.entries(mapa || {})) salida[palletDesdeClave(k)] = v;
  return salida;
}

module.exports = {
  limpiar, normalizarCodigo, normalizarPallet, palletValido, palletPadre,
  sinAcentos, sanearCelda, aNumero,
  clavePallet, palletDesdeClave, decodificarPallets,
};
