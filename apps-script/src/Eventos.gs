/**
 * Libro mayor de conteos (append-only).
 *
 * Reemplaza al guardarFilaRecepcion anterior, que escribia el valor absoluto
 * de la celda y hacia que dos operadores sobre el mismo SKU se borraran entre
 * si en silencio.
 *
 * Aqui cada conteo es una FILA NUEVA que nunca se modifica ni se borra. Los
 * totales se derivan sumando. Corregir es registrar un evento compensatorio.
 * De ahi salen, sin trabajo extra: trazabilidad de quien conto que y cuando,
 * y los KPIs historicos por SKU, recepcion y fecha.
 */

/** Lee todos los eventos de una recepcion. */
function eventosDe_(fileId) {
  var hoja = hojaEventos_();
  var ultima = hoja.getLastRow();
  if (ultima < 2) return [];
  var datos = hoja.getRange(2, 1, ultima - 1, EVENTOS_HEADER.length).getValues();
  var salida = [];
  for (var i = 0; i < datos.length; i++) {
    if (String(datos[i][EVT.FILE_ID - 1]) === String(fileId)) {
      salida.push(filaAEvento_(datos[i], i + 2));
    }
  }
  return salida;
}

function filaAEvento_(fila, numFila) {
  return {
    numFila: numFila,
    id: fila[EVT.ID - 1],
    fecha: fila[EVT.FECHA - 1],
    recepcion: fila[EVT.RECEPCION - 1],
    fileId: String(fila[EVT.FILE_ID - 1]),
    sku: String(fila[EVT.SKU - 1]),
    ean: String(fila[EVT.EAN - 1] || ''),
    pallet: String(fila[EVT.PALLET - 1] || ''),
    cantidad: aNumero_(fila[EVT.CANTIDAD - 1]),
    estadoFisico: String(fila[EVT.ESTADO_FISICO - 1] || 'BUENO'),
    tipo: String(fila[EVT.TIPO - 1] || 'CONTEO'),
    observacion: String(fila[EVT.OBSERVACION - 1] || ''),
    operador: String(fila[EVT.OPERADOR - 1] || ''),
    dispositivo: String(fila[EVT.DISPOSITIVO - 1] || ''),
    idem: String(fila[EVT.IDEM - 1] || ''),
    ref: String(fila[EVT.REF - 1] || '')
  };
}

/** Busca un evento por clave de idempotencia (doble disparo del lector). */
function eventoPorIdem_(clave) {
  if (!clave) return null;
  var hoja = hojaEventos_();
  var ultima = hoja.getLastRow();
  if (ultima < 2) return null;
  var columna = hoja.getRange(2, EVT.IDEM, ultima - 1, 1).getValues();
  for (var i = 0; i < columna.length; i++) {
    if (String(columna[i][0]) === String(clave)) {
      var fila = hoja.getRange(i + 2, 1, 1, EVENTOS_HEADER.length).getValues()[0];
      return filaAEvento_(fila, i + 2);
    }
  }
  return null;
}

/** Agrega un evento al libro mayor. Debe llamarse dentro de conCandado_. */
function agregarEvento_(e) {
  var hoja = hojaEventos_();
  var fila = [];
  fila[EVT.ID - 1] = e.id || uuid_();
  fila[EVT.FECHA - 1] = e.fecha || ahora_();
  fila[EVT.RECEPCION - 1] = e.recepcion || '';
  fila[EVT.FILE_ID - 1] = e.fileId;
  fila[EVT.SKU - 1] = e.sku;
  fila[EVT.EAN - 1] = e.ean || '';
  fila[EVT.PALLET - 1] = e.pallet;
  fila[EVT.CANTIDAD - 1] = e.cantidad;
  fila[EVT.ESTADO_FISICO - 1] = e.estadoFisico || 'BUENO';
  fila[EVT.TIPO - 1] = e.tipo || 'CONTEO';
  fila[EVT.OBSERVACION - 1] = e.observacion || '';
  fila[EVT.OPERADOR - 1] = e.operador || '';
  fila[EVT.DISPOSITIVO - 1] = e.dispositivo || '';
  fila[EVT.IDEM - 1] = e.idem || '';
  fila[EVT.REF - 1] = e.ref || '';
  hoja.appendRow(fila);
  invalidarCache_(e.fileId);
  return fila[EVT.ID - 1];
}

// --------------------------------------------------------------------------
// Agregados derivados del libro mayor
// --------------------------------------------------------------------------

/** { sku: cantidad } contado en la recepcion. */
function contadoPorSku_(fileId) {
  var total = {};
  var evs = eventosDe_(fileId);
  for (var i = 0; i < evs.length; i++) {
    total[evs[i].sku] = (total[evs[i].sku] || 0) + evs[i].cantidad;
  }
  return total;
}

/**
 * Pallets donde ya se guardo este SKU, de mayor a menor cantidad.
 *
 * Es la base de la sugerencia "ya guardaste este item en la caja X", que el
 * ultimoPallet anterior no podia dar: aquel recordaba el ultimo pallet que
 * escribio ESE operador, no donde quedo ESTE SKU.
 */
function ubicacionesDeSku_(fileId, sku) {
  var porPallet = {};
  var ultimo = {};
  var evs = eventosDe_(fileId);
  for (var i = 0; i < evs.length; i++) {
    if (evs[i].sku !== sku) continue;
    var p = evs[i].pallet;
    porPallet[p] = (porPallet[p] || 0) + evs[i].cantidad;
    if (!ultimo[p] || evs[i].fecha > ultimo[p]) ultimo[p] = evs[i].fecha;
  }
  var salida = [];
  for (var pal in porPallet) {
    if (porPallet[pal] !== 0) {
      salida.push({ pallet: pal, cantidad: porPallet[pal], ultimo: fechaIso_(ultimo[pal]) });
    }
  }
  salida.sort(function (a, b) { return b.cantidad - a.cantidad; });
  return salida;
}

function contadoDeSku_(fileId, sku) {
  return contadoPorSku_(fileId)[sku] || 0;
}

// --------------------------------------------------------------------------
// Cache de agregados (una recepcion se consulta mucho mas de lo que se escribe)
// --------------------------------------------------------------------------

function invalidarCache_(fileId) {
  try { CacheService.getScriptCache().remove('agg_' + fileId); } catch (e) { /* no critico */ }
}

function cacheGet_(fileId) {
  try {
    var v = CacheService.getScriptCache().get('agg_' + fileId);
    return v ? JSON.parse(v) : null;
  } catch (e) { return null; }
}

function cachePut_(fileId, obj) {
  try {
    CacheService.getScriptCache().put('agg_' + fileId, JSON.stringify(obj), CFG.CACHE_SEG);
  } catch (e) { /* el cache es opcional */ }
}
