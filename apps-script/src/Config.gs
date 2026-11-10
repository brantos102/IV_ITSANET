/**
 * ITSANET IMS - Configuracion central.
 *
 * El ID del libro base estaba repetido en tres funciones del codigo anterior.
 * Aqui vive una sola vez.
 */

var CFG = {
  // Libro base: Historial, EVENTOS, MAESTRO, PENDIENTES.
  LIBRO_BASE: '1h3BrU2k96l4M_4j91vDgY3CxUC1Qwi9OevjoTVjmYuI',

  // Correo del reporte de cierre. Vacio = dueno del script.
  EMAIL_REPORTE: '',

  HOJA_HISTORIAL: 'Historial',
  HOJA_EVENTOS: 'EVENTOS',
  HOJA_MAESTRO: 'MAESTRO',
  HOJA_PENDIENTES: 'PENDIENTES',

  // Columnas del packing list (1-based), formato REV.
  COL_SKU: 1,
  COL_DESCRIPCION: 2,
  COL_CANTIDAD: 5,
  COL_EMBARQUE: 9,
  COL_FISICA: 10,
  COL_VALIDACION: 11,
  COL_PALLET: 12,
  COL_CODIGO_BARRA: 13,
  COL_COD_PROD: 14,
  COL_OBSERVACION: 15,
  COL_OK: 16,

  LOCK_MS: 25000,          // espera maxima por el candado de escritura
  CACHE_SEG: 1800,         // vida del cache de agregados
  PALLET_SEPARADOR: ' / '
};

var EVT = {   // columnas de la hoja EVENTOS (1-based)
  ID: 1, FECHA: 2, RECEPCION: 3, FILE_ID: 4, SKU: 5, EAN: 6, PALLET: 7,
  CANTIDAD: 8, ESTADO_FISICO: 9, TIPO: 10, OBSERVACION: 11, OPERADOR: 12,
  DISPOSITIVO: 13, IDEM: 14, REF: 15
};

var EVENTOS_HEADER = [
  'evento_id', 'fecha', 'recepcion_id', 'file_id', 'sku', 'ean', 'pallet',
  'cantidad', 'estado_fisico', 'tipo', 'observacion', 'operador',
  'dispositivo', 'idempotency_key', 'evento_ref'
];

function libroBase_() {
  return SpreadsheetApp.openById(CFG.LIBRO_BASE);
}

/** Devuelve la hoja, creandola con encabezados si no existe. */
function hoja_(nombre, encabezados) {
  var libro = libroBase_();
  var hoja = libro.getSheetByName(nombre);
  if (!hoja) {
    hoja = libro.insertSheet(nombre);
    if (encabezados) {
      hoja.getRange(1, 1, 1, encabezados.length).setValues([encabezados])
          .setFontWeight('bold').setBackground('#4FC3F7');
      hoja.setFrozenRows(1);
    }
  }
  return hoja;
}

function hojaEventos_() { return hoja_(CFG.HOJA_EVENTOS, EVENTOS_HEADER); }
