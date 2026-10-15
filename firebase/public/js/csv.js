/**
 * CSV para la carga masiva hacia Depot.
 *
 * El CSV se usa SOLO para esto. Los informes y los indicadores salen en Excel o
 * PDF: un CSV pierde el formato del packing list, que es justo lo que el cliente
 * espera recibir igual que lo mandó.
 *
 * Lo que entra a Depot no se teclea fila por fila: se sube un archivo. Hasta
 * ahora ese archivo se armaba a mano a partir del informe, que es donde se
 * cuelan los errores — una columna de más, un separador que Excel interpreta al
 * revés, una posición partida mal.
 *
 * Los encabezados por defecto son los nombres REALES que devuelve el WMS
 * («COD. PRODUCTO», «NRO. LOTE»), tomados del mapeo del proxy. Aun así, el
 * formato de SUBIDA puede no ser el mismo que el de consulta: por eso los
 * mantiene el administrador y no están fijos en el código.
 */

import {
  doc, getDoc, setDoc, serverTimestamp,
} from '../vendor/firebase-sdk.js';
import { db } from './auth.js';
import * as local from './local.js';

/** Los campos que la aplicación sabe rellenar. Lo demás se deja en blanco. */
export const CAMPOS = {
  '': 'En blanco, para rellenar a mano',
  sku: 'Código del producto',
  descripcion: 'Descripción',
  unidad: 'Unidad de medida',
  cantidad: 'Cantidad contada',
  pallet: 'Pallet (A1, B04…)',
  posicion: 'Posición real completa (A-01-03-2)',
  nave: 'Posición: nave',
  calle: 'Posición: calle',
  columna: 'Posición: columna',
  nivel: 'Posición: nivel',
  lote: 'N.º de lote',
  serie: 'N.º de serie',
  partida: 'N.º de partida',
  estado: 'Estado de la mercadería',
  cliente: 'Código del cliente',
  recepcion: 'Código de la recepción',
  observacion: 'Observación del operario',
  fecha: 'Fecha de la validación',
};

/**
 * Los dos formatos que se usan, como punto de partida.
 *
 * El administrador los ajusta en Administración. Están aquí para que el día uno
 * haya algo que descargar, no para quedarse fijos.
 */
export const FORMATOS_BASE = [
  {
    id: 'CANTIDADES',
    nombre: 'Alta masiva de cantidades',
    descripcion: 'Lo contado, una fila por producto y posición. Es el archivo que '
               + 'carga las existencias de la recepción.',
    archivo: 'alta-cantidades',
    separador: ';',
    columnas: [
      { encabezado: 'COD. PRODUCTO', campo: 'sku' },
      { encabezado: 'DESCRIPCION', campo: 'descripcion' },
      { encabezado: 'CANTIDAD', campo: 'cantidad' },
      { encabezado: 'NAVE', campo: 'nave' },
      { encabezado: 'CALLE', campo: 'calle' },
      { encabezado: 'COLUMNA', campo: 'columna' },
      { encabezado: 'NIVEL', campo: 'nivel' },
      { encabezado: 'PALLET', campo: 'pallet' },
      { encabezado: 'NRO. LOTE', campo: 'lote' },
      { encabezado: 'NRO. SERIE', campo: 'serie' },
      { encabezado: 'NRO. PARTIDA', campo: 'partida' },
      { encabezado: 'EST. MERC.', campo: 'estado' },
      { encabezado: 'COD. CLIENTE', campo: 'cliente' },
    ],
  },
  {
    id: 'PRODUCTOS',
    nombre: 'Alta de productos nuevos',
    descripcion: 'Los códigos que aparecieron físicamente y no estaban en el '
               + 'catálogo. Hay que darlos de alta antes de cargarles cantidad.',
    archivo: 'alta-productos',
    separador: ';',
    columnas: [
      { encabezado: 'COD. PRODUCTO', campo: 'sku' },
      { encabezado: 'DESCRIPCION', campo: 'descripcion' },
      { encabezado: 'UNIDAD', campo: 'unidad' },
      { encabezado: 'FAMILIA', campo: '' },
      { encabezado: 'COD. CLIENTE', campo: 'cliente' },
    ],
  },
];

/** Un formato guardado puede venir incompleto: se completa con el de base. */
export function normalizarFormato(formato, base) {
  const b = base || FORMATOS_BASE[0];
  const columnas = (formato?.columnas || []).filter((c) => c && c.encabezado);
  return {
    id: formato?.id || b.id,
    nombre: formato?.nombre || b.nombre,
    descripcion: formato?.descripcion || b.descripcion,
    archivo: formato?.archivo || b.archivo,
    separador: formato?.separador || ';',
    columnas: columnas.length ? columnas : b.columnas,
  };
}

/**
 * Una celda, escapada.
 *
 * Se entrecomilla solo cuando hace falta: si el valor lleva el separador, una
 * comilla o un salto de línea. Una descripción con coma partía la fila en dos y
 * Depot rechazaba el archivo entero sin decir en qué línea.
 */
export function celda(valor, separador) {
  const t = valor === null || valor === undefined ? '' : String(valor);
  return /["\r\n]/.test(t) || t.includes(separador)
    ? `"${t.replace(/"/g, '""')}"`
    : t;
}

/**
 * El texto del CSV.
 *
 * Lleva BOM porque Excel, sin él, abre el UTF-8 como si fuera Latin-1 y las
 * tildes y las eñes salen rotas. Y termina las líneas en CRLF, que es lo que
 * dice el estándar y lo que esperan los cargadores de Windows.
 */
export function aCsv(filas, separador = ';') {
  return '﻿' + filas
    .map((f) => f.map((c) => celda(c, separador)).join(separador))
    .join('\r\n') + '\r\n';
}

/** La plantilla vacía: solo los encabezados, para rellenar a mano. */
export function plantilla(formato) {
  const f = normalizarFormato(formato);
  return aCsv([f.columnas.map((c) => c.encabezado)], f.separador);
}

/**
 * Parte una posición en sus cuatro partes.
 *
 * El proxy arma la posición uniendo NAVE-CALLE-COLUMNA-NIVEL con guiones, así
 * que partir por guiones es exactamente la operación inversa. El guion no se
 * puede quitar al normalizar: «A-01-03-2» sin él es un número sin sentido.
 */
export function partesDePosicion(posicion) {
  const p = String(posicion || '').trim().split('-').map((x) => x.trim());
  return { nave: p[0] || '', calle: p[1] || '', columna: p[2] || '', nivel: p[3] || '' };
}

/**
 * Lo contado, agrupado como se carga: una fila por producto y sitio.
 *
 * Sale de la bitácora y no del informe porque el informe entrega una fila por
 * línea del packing list, y de las 30 unidades de una línea pueden haber ido 12
 * a una posición real y 18 a un pallet. Cargar eso como una sola fila sería
 * meter en el sistema algo que no está donde dice.
 *
 * Las anulaciones no se restan de un montón: se descarta el conteo anulado
 * entero. El evento que anula no guarda la posición, así que restarlo sin más
 * dejaría la cantidad bien y el sitio mal.
 */
export function agruparConteos(eventos, { skus = [] } = {}) {
  const anulados = new Set(
    (eventos || [])
      .filter((e) => e.tipo === 'ANULACION')
      .map((e) => String(e.id || '').replace(/^anula-/, '')),
  );
  const descripcionDe = Object.fromEntries(skus.map((s) => [s.sku, s.descripcion || '']));

  const grupos = new Map();
  for (const e of eventos || []) {
    if (e.tipo === 'ANULACION' || anulados.has(e.id)) continue;
    const cantidad = Number(e.cantidad) || 0;
    if (cantidad <= 0) continue;          // los «no apareció» se registran con 0

    const pallet = e.pallet || '';
    const posicion = e.posicionReal || '';
    const clave = [e.sku, posicion, pallet, e.estadoFisico || ''].join('\u0000');

    const previo = grupos.get(clave);
    if (previo) { previo.cantidad += cantidad; continue; }
    grupos.set(clave, {
      sku: e.sku,
      descripcion: e.descripcion || descripcionDe[e.sku] || '',
      cantidad,
      pallet,
      posicion,
      estado: e.estadoFisico === 'PNC' ? 'PNC' : (e.estadoFisico || ''),
      observacion: e.observacion || '',
    });
  }
  // Por producto, y dentro de cada uno primero lo que tiene posición real: es
  // lo concreto. Lo que quedó en un pallet sin posición va detrás, que es lo
  // que todavía hay que ubicar.
  return [...grupos.values()].sort((a, b) => {
    if (a.sku !== b.sku) return a.sku.localeCompare(b.sku);
    if (!a.posicion !== !b.posicion) return a.posicion ? -1 : 1;
    return a.posicion.localeCompare(b.posicion) || a.pallet.localeCompare(b.pallet);
  });
}

/** Rellena una fila del formato con lo que la aplicación sabe de ese registro. */
function filaDe(formato, dato, comunes) {
  const pos = partesDePosicion(dato.posicion);
  const valores = { ...comunes, ...dato, ...pos };
  return formato.columnas.map((c) => (c.campo ? valores[c.campo] ?? '' : ''));
}

/**
 * El CSV de cantidades de una recepción ya validada.
 *
 * `datos` es lo que devuelve reunirInforme.
 */
export function csvDeCantidades(formato, datos) {
  const f = normalizarFormato(formato, FORMATOS_BASE[0]);
  const rec = datos?.recepcion || {};
  const comunes = {
    cliente: rec.cliente || '',
    recepcion: rec.codigo || '',
    fecha: new Date().toISOString().slice(0, 10),
    unidad: '', lote: '', serie: '', partida: '',
  };
  const filas = agruparConteos(datos?.eventos, { skus: datos?.skus });
  return {
    texto: aCsv([f.columnas.map((c) => c.encabezado),
                 ...filas.map((d) => filaDe(f, d, comunes))], f.separador),
    filas: filas.length,
    nombre: `${f.archivo}-${rec.codigo || 'recepcion'}.csv`,
  };
}

/**
 * El CSV de productos que hay que dar de alta.
 *
 * Son los adicionales: lo que apareció físicamente y no estaba ni en el packing
 * list ni en el catálogo. Cargarles cantidad antes de darlos de alta es lo que
 * hace que Depot rechace la carga entera.
 */
export function csvDeProductos(formato, datos) {
  const f = normalizarFormato(formato, FORMATOS_BASE[1]);
  const rec = datos?.recepcion || {};
  const comunes = { cliente: rec.cliente || '', recepcion: rec.codigo || '', unidad: '' };
  const filas = (datos?.adicionales || []).map((a) => ({
    sku: a.sku,
    descripcion: a.descripcion || '',
    cantidad: a.fisica,
    observacion: a.observacion || a.motivo || '',
    pallet: a.pallets || '', posicion: '', estado: '',
  }));
  return {
    texto: aCsv([f.columnas.map((c) => c.encabezado),
                 ...filas.map((d) => filaDe(f, d, comunes))], f.separador),
    filas: filas.length,
    nombre: `${f.archivo}-${rec.codigo || 'recepcion'}.csv`,
  };
}

/** Descarga un texto como archivo .csv. */
export function descargarCsv(texto, nombre) {
  const url = URL.createObjectURL(new Blob([texto], { type: 'text/csv;charset=utf-8;' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = nombre.endsWith('.csv') ? nombre : nombre + '.csv';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

// --------------------------------------------------------------------------- //
// Los formatos los mantiene el administrador, no el código
// --------------------------------------------------------------------------- //

/**
 * Los formatos guardados, o los de base si todavía no se tocaron.
 *
 * Nunca falla: si no se puede leer la configuración, se devuelven los de base.
 * Quedarse sin poder descargar una plantilla porque la red falló sería peor que
 * descargarla con los encabezados por defecto.
 */
export async function leerFormatos() {
  let guardados = [];
  try {
    if (local.modoLocal()) guardados = (await local.leerFormatosCsv()).formatos || [];
    else {
      const snap = await getDoc(doc(db, 'config', 'csv'));
      guardados = snap.exists() ? (snap.data().formatos || []) : [];
    }
  } catch { /* se siguen usando los de base */ }

  return FORMATOS_BASE.map((base) =>
    normalizarFormato(guardados.find((g) => g.id === base.id), base));
}

/** Guarda los formatos. Solo un administrador puede, por las reglas. */
export async function guardarFormatos(formatos, usuario) {
  if (local.modoLocal()) return local.guardarFormatosCsv(formatos.map((f) =>
    normalizarFormato(f, FORMATOS_BASE.find((b) => b.id === f.id))));
  await setDoc(doc(db, 'config', 'csv'), {
    formatos: formatos.map((f) => normalizarFormato(f,
      FORMATOS_BASE.find((b) => b.id === f.id))),
    editadoEn: serverTimestamp(),
    editadoPor: usuario?.email || null,
  });
}
