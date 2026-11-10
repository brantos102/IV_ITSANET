/**
 * KPIs historicos.
 *
 * Requerimiento inicial que el modelo anterior no podia cumplir: "datos por
 * cada SKU por cada recepcion por fechas". Como cada conteo es un evento con
 * fecha, SKU, pallet y operador, los indicadores salen de agregar la hoja
 * EVENTOS; no hay proceso de consolidacion que pueda quedar desactualizado.
 */

/** Lee EVENTOS completo una sola vez. */
function todosLosEventos_() {
  var hoja = hojaEventos_();
  var ultima = hoja.getLastRow();
  if (ultima < 2) return [];
  var datos = hoja.getRange(2, 1, ultima - 1, EVENTOS_HEADER.length).getValues();
  return datos.map(function (f, i) { return filaAEvento_(f, i + 2); });
}

/** Nombre y fecha de cada recepcion, indexado por fileId. */
function indiceRecepciones_() {
  var hoja = hoja_(CFG.HOJA_HISTORIAL);
  var data = hoja.getDataRange().getValues();
  var idx = {};
  for (var i = 1; i < data.length; i++) {
    var fileId = String(data[i][5] || '');
    if (!fileId) {
      var m = String(data[i][4] || '').match(/[-\w]{25,}/);
      fileId = m ? m[0] : '';
    }
    if (fileId) {
      idx[fileId] = { id: data[i][0], nombre: data[i][2], estado: data[i][3], fecha: data[i][1] };
    }
  }
  return idx;
}

function enRango_(fecha, desde, hasta) {
  if (!(fecha instanceof Date)) return false;
  if (desde && fecha < desde) return false;
  if (hasta && fecha > hasta) return false;
  return true;
}

/** Indicadores globales y por recepcion. */
function kpisGlobales(desdeIso, hastaIso) {
  try {
    var desde = desdeIso ? new Date(desdeIso) : null;
    var hasta = hastaIso ? new Date(hastaIso + 'T23:59:59') : null;
    var evs = todosLosEventos_();
    var idx = indiceRecepciones_();

    // Agrupa por recepcion y SKU.
    var porRec = {};
    evs.forEach(function (e) {
      if (!enRango_(e.fecha, desde, hasta)) return;
      if (!porRec[e.fileId]) porRec[e.fileId] = { skus: {}, eventos: 0, operadores: {},
                                                  primera: e.fecha, ultima: e.fecha };
      var r = porRec[e.fileId];
      r.skus[e.sku] = (r.skus[e.sku] || 0) + e.cantidad;
      r.eventos++;
      if (e.operador) r.operadores[e.operador] = true;
      if (e.fecha < r.primera) r.primera = e.fecha;
      if (e.fecha > r.ultima) r.ultima = e.fecha;
    });

    var recepciones = [], totOk = 0, totFalt = 0, totSobr = 0, uFis = 0, uEsp = 0;

    for (var fileId in porRec) {
      var r = porRec[fileId];
      var esperado = esperadoPorSkuDeArchivo_(fileId);
      var todos = {}, k;
      for (k in esperado) todos[k] = true;
      for (k in r.skus) todos[k] = true;

      var ok = 0, falt = 0, sobr = 0, re = 0, rf = 0;
      for (var sku in todos) {
        var e = esperado[sku] || 0, f = r.skus[sku] || 0;
        re += e; rf += f;
        if (f === e) ok++; else if (f < e) falt++; else sobr++;
      }
      totOk += ok; totFalt += falt; totSobr += sobr; uEsp += re; uFis += rf;

      var meta = idx[fileId] || {};
      var horas = Math.round(100 * (r.ultima - r.primera) / 3600000) / 100;
      recepciones.push({
        fileId: fileId, codigo: meta.id || fileId.substring(0, 8),
        nombre: meta.nombre || '', estado: meta.estado || '',
        fecha: fechaIso_(meta.fecha || r.primera).substring(0, 10),
        skus: Object.keys(todos).length, ok: ok, faltante: falt, sobrante: sobr,
        unidadesEsperadas: re, unidadesFisicas: rf,
        exactitud: Object.keys(todos).length ? Math.round(1000 * ok / Object.keys(todos).length) / 10 : 0,
        horas: horas, eventos: r.eventos, operadores: Object.keys(r.operadores).length
      });
    }

    recepciones.sort(function (a, b) { return a.fecha < b.fecha ? 1 : -1; });
    var totSkus = totOk + totFalt + totSobr;

    return ok_({
      recepciones: recepciones.length,
      skusValidados: totSkus, ok: totOk, faltante: totFalt, sobrante: totSobr,
      exactitud: totSkus ? Math.round(1000 * totOk / totSkus) / 10 : 0,
      tasaDiscrepancia: totSkus ? Math.round(1000 * (totFalt + totSobr) / totSkus) / 10 : 0,
      unidadesEsperadas: uEsp, unidadesFisicas: uFis, diferencia: uFis - uEsp,
      porRecepcion: recepciones
    });
  } catch (e) {
    return error_(e);
  }
}

var _esperadoCache = {};

function esperadoPorSkuDeArchivo_(fileId) {
  if (_esperadoCache[fileId]) return _esperadoCache[fileId];
  var mapa = {};
  try {
    var data = SpreadsheetApp.openById(fileId).getSheets()[0].getDataRange().getValues();
    for (var i = 1; i < data.length; i++) {
      var sku = normalizarSku_(data[i][CFG.COL_SKU - 1]);
      if (!sku) continue;
      mapa[sku] = (mapa[sku] || 0) + aNumero_(data[i][CFG.COL_CANTIDAD - 1]);
    }
  } catch (e) { /* archivo borrado o sin permiso: se trata como vacio */ }
  _esperadoCache[fileId] = mapa;
  return mapa;
}

/** Productividad por operador. */
function kpisPorOperador(desdeIso, hastaIso) {
  try {
    var desde = desdeIso ? new Date(desdeIso) : null;
    var hasta = hastaIso ? new Date(hastaIso + 'T23:59:59') : null;
    var acum = {};

    todosLosEventos_().forEach(function (e) {
      if (!e.operador || !enRango_(e.fecha, desde, hasta)) return;
      var a = acum[e.operador] || (acum[e.operador] = {
        nombre: e.operador, eventos: 0, unidades: 0, skus: {}, recepciones: {},
        anulaciones: 0, malEstado: 0, primera: e.fecha, ultima: e.fecha
      });
      a.eventos++;
      if (e.cantidad > 0) a.unidades += e.cantidad;
      a.skus[e.sku] = true;
      a.recepciones[e.fileId] = true;
      if (e.tipo === 'ANULACION') a.anulaciones++;
      if (e.estadoFisico === 'MALO') a.malEstado++;
      if (e.fecha < a.primera) a.primera = e.fecha;
      if (e.fecha > a.ultima) a.ultima = e.fecha;
    });

    var salida = [];
    for (var nombre in acum) {
      var a = acum[nombre];
      var horas = (a.ultima - a.primera) / 3600000;
      salida.push({
        nombre: a.nombre, eventos: a.eventos, unidades: a.unidades,
        skusDistintos: Object.keys(a.skus).length,
        recepciones: Object.keys(a.recepciones).length,
        anulaciones: a.anulaciones, malEstado: a.malEstado,
        tasaAnulacion: a.eventos ? Math.round(1000 * a.anulaciones / a.eventos) / 10 : 0,
        scansPorHora: horas > 0.05 ? Math.round(10 * a.eventos / horas) / 10 : null
      });
    }
    salida.sort(function (x, y) { return y.eventos - x.eventos; });
    return ok_(salida);
  } catch (e) {
    return error_(e);
  }
}

/**
 * Historico por SKU: en cuantas recepciones aparecio y en cuantas hubo
 * discrepancia. Sirve para detectar los SKU que fallan siempre.
 */
function kpisPorSku(limite, soloProblematicos) {
  try {
    var porRecSku = {};
    todosLosEventos_().forEach(function (e) {
      var clave = e.fileId + '|' + e.sku;
      porRecSku[clave] = (porRecSku[clave] || 0) + e.cantidad;
    });

    var acum = {};
    var idx = indiceRecepciones_();
    for (var clave in porRecSku) {
      var partes = clave.split('|');
      var fileId = partes[0], sku = partes[1];
      var esperado = esperadoPorSkuDeArchivo_(fileId)[sku] || 0;
      var fisico = porRecSku[clave];

      var a = acum[sku] || (acum[sku] = {
        sku: sku, recepciones: 0, ok: 0, faltante: 0, sobrante: 0,
        unidadesEsperadas: 0, unidadesFisicas: 0, ultima: ''
      });
      a.recepciones++;
      a.unidadesEsperadas += esperado;
      a.unidadesFisicas += fisico;
      if (fisico === esperado) a.ok++; else if (fisico < esperado) a.faltante++; else a.sobrante++;
      var meta = idx[fileId];
      if (meta && meta.nombre) a.ultima = meta.nombre;
    }

    var salida = [];
    for (var s in acum) {
      var x = acum[s];
      var disc = x.faltante + x.sobrante;
      if (soloProblematicos && disc === 0) continue;
      x.tasaDiscrepancia = x.recepciones ? Math.round(1000 * disc / x.recepciones) / 10 : 0;
      x.diferenciaUnidades = x.unidadesFisicas - x.unidadesEsperadas;
      salida.push(x);
    }
    salida.sort(function (a, b) {
      return (b.tasaDiscrepancia - a.tasaDiscrepancia) || (b.recepciones - a.recepciones);
    });
    return ok_(salida.slice(0, limite || 100));
  } catch (e) {
    return error_(e);
  }
}

/** SKU pendientes de crear en Depot, de todas las recepciones. */
function skusPendientesDepot() {
  try {
    var hoja = libroBase_().getSheetByName(CFG.HOJA_PENDIENTES);
    if (!hoja || hoja.getLastRow() < 2) return ok_([]);
    var data = hoja.getDataRange().getValues();
    var salida = [];
    for (var i = 1; i < data.length; i++) {
      salida.push({
        fila: i + 1, fecha: fechaIso_(data[i][0]), fileId: data[i][1], sku: data[i][2],
        descripcion: data[i][3], ean: data[i][4], estadoDepot: data[i][5],
        estado: data[i][6], notas: data[i][9]
      });
    }
    return ok_(salida);
  } catch (e) {
    return error_(e);
  }
}

/** Marca un pendiente como creado en Depot. */
function resolverPendiente(fila, estado, ean, notas) {
  try {
    var hoja = libroBase_().getSheetByName(CFG.HOJA_PENDIENTES);
    if (!hoja) return error_('No hay pendientes registrados.');
    hoja.getRange(fila, 7).setValue(String(estado || 'CREADO').toUpperCase());
    if (ean) hoja.getRange(fila, 5).setValue(normalizarEan_(ean));
    if (notas) hoja.getRange(fila, 10).setValue(limpiar_(notas));
    return ok_(null, 'Pendiente actualizado.');
  } catch (e) {
    return error_(e);
  }
}
