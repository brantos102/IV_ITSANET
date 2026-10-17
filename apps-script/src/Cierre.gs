/**
 * Cierre de la recepcion: escribe el packing list final y envia el reporte.
 *
 * Reglas del flujo de trabajo, respetadas al pie de la letra:
 *   - "No anadir filas"  -> una fila por linea original, en el orden original.
 *     Los sobrantes de SKU ausentes del packing list van al final.
 *   - "No caracteres especiales" -> celdas saneadas.
 *   - "1 SKU en dos pallets se puede misma celda" -> pallets unidos en una celda.
 */

/**
 * Reparte la cantidad fisica de un SKU entre sus lineas del packing list.
 * Llena cada linea hasta su cantidad esperada; el excedente cae en la ultima.
 */
function repartir_(total, lineas) {
  var resto = total, asignado = {};
  for (var i = 0; i < lineas.length; i++) {
    var toma = Math.min(Math.max(lineas[i].cantidad, 0), Math.max(resto, 0));
    asignado[lineas[i].fila] = toma;
    resto -= toma;
  }
  if (resto > 0 && lineas.length) {
    asignado[lineas[lineas.length - 1].fila] += resto;
  }
  return asignado;
}

/** Escribe cantidad fisica, validacion, pallet, EAN y observaciones en el archivo. */
function escribirPackingFinal_(fileId) {
  var hoja = SpreadsheetApp.openById(fileId).getSheets()[0];
  var data = hoja.getDataRange().getValues();
  var contado = contadoPorSku_(fileId);
  var evs = eventosDe_(fileId);
  var mapa = maestro_();

  // Agrupa lineas por SKU conservando el orden original.
  var porSku = {}, orden = [];
  for (var i = 1; i < data.length; i++) {
    var sku = normalizarSku_(data[i][CFG.COL_SKU - 1]);
    if (!sku) continue;
    if (!porSku[sku]) { porSku[sku] = []; orden.push(sku); }
    porSku[sku].push({ fila: i + 1, cantidad: aNumero_(data[i][CFG.COL_CANTIDAD - 1]) });
  }

  // Observaciones y EAN por SKU, sin repetir.
  var obsPorSku = {}, eanPorSku = {};
  for (var e = 0; e < evs.length; e++) {
    var ev = evs[e];
    if (ev.observacion) {
      var t = sanearCelda_(ev.observacion);
      if (!obsPorSku[ev.sku]) obsPorSku[ev.sku] = [];
      if (t && obsPorSku[ev.sku].indexOf(t) === -1) obsPorSku[ev.sku].push(t);
    }
    if (ev.ean && !eanPorSku[ev.sku]) eanPorSku[ev.sku] = ev.ean;
  }

  function celdasDeSku(sku, fisica, esperada) {
    var ubic = ubicacionesDeSku_(fileId, sku);
    var celdaPallet = ubic.map(function (u) { return u.pallet; }).join(CFG.PALLET_SEPARADOR);
    var obs = (obsPorSku[sku] || []).slice();
    if (ubic.length > 1) {
      obs.push('SKU EN ' + ubic.length + ' PALLETS: ' +
               ubic.map(function (u) { return u.pallet + '=' + u.cantidad; }).join(', '));
    }
    var validacion;
    if (fisica === esperada) validacion = 'Ok';
    else if (fisica < esperada) { validacion = 'Faltante'; if (fisica === 0) obs.push('FALTANTE CONFIRMADO'); }
    else { validacion = 'Sobrante'; obs.push('SOBRANTE CONFIRMADO'); }
    return {
      pallet: celdaPallet || 0,
      validacion: validacion,
      ean: eanPorSku[sku] || '',
      obs: obs.join(' | '),
      ok: mapa[sku] ? 'ok' : '#N/A'
    };
  }

  // Escribe las lineas existentes. Una fila por linea: no se anade ninguna.
  for (var o = 0; o < orden.length; o++) {
    var s = orden[o];
    var reparto = repartir_(contado[s] || 0, porSku[s]);
    for (var L = 0; L < porSku[s].length; L++) {
      var linea = porSku[s][L];
      var fis = reparto[linea.fila] || 0;
      var c = celdasDeSku(s, fis, linea.cantidad);
      hoja.getRange(linea.fila, CFG.COL_FISICA).setValue(fis);
      hoja.getRange(linea.fila, CFG.COL_VALIDACION).setValue(c.validacion);
      hoja.getRange(linea.fila, CFG.COL_PALLET).setValue(c.pallet);
      hoja.getRange(linea.fila, CFG.COL_CODIGO_BARRA).setValue(c.ean);
      hoja.getRange(linea.fila, CFG.COL_OBSERVACION).setValue(c.obs);
      hoja.getRange(linea.fila, CFG.COL_OK).setValue(c.ok);
    }
  }

  // Sobrantes de SKU fuera del packing list: al final, con cantidad 0.
  for (var sk in contado) {
    if (porSku[sk] || contado[sk] === 0) continue;
    var cc = celdasDeSku(sk, contado[sk], 0);
    var fila = [];
    fila[CFG.COL_SKU - 1] = sanearCelda_(sk);
    fila[CFG.COL_DESCRIPCION - 1] = sanearCelda_(mapa[sk] ? mapa[sk].descripcion : '');
    fila[CFG.COL_CANTIDAD - 1] = 0;
    fila[CFG.COL_FISICA - 1] = contado[sk];
    fila[CFG.COL_VALIDACION - 1] = 'Sobrante';
    fila[CFG.COL_PALLET - 1] = cc.pallet;
    fila[CFG.COL_CODIGO_BARRA - 1] = cc.ean;
    fila[CFG.COL_OBSERVACION - 1] = cc.obs;
    fila[CFG.COL_OK - 1] = cc.ok;
    for (var z = 0; z < CFG.COL_OK; z++) if (fila[z] === undefined) fila[z] = '';
    hoja.appendRow(fila);
  }
}

/** Totales de la recepcion para el reporte y los KPI. */
function resumenRecepcion_(fileId) {
  var hoja = SpreadsheetApp.openById(fileId).getSheets()[0];
  var data = hoja.getDataRange().getValues();
  var esperado = {};
  for (var i = 1; i < data.length; i++) {
    var sku = normalizarSku_(data[i][CFG.COL_SKU - 1]);
    if (!sku) continue;
    esperado[sku] = (esperado[sku] || 0) + aNumero_(data[i][CFG.COL_CANTIDAD - 1]);
  }
  var contado = contadoPorSku_(fileId);

  var todos = {}, k;
  for (k in esperado) todos[k] = true;
  for (k in contado) todos[k] = true;

  var ok = 0, faltante = 0, sobrante = 0, uEsp = 0, uFis = 0, detalle = [];
  for (var sku2 in todos) {
    var e = esperado[sku2] || 0, f = contado[sku2] || 0;
    uEsp += e; uFis += f;
    var estado = (f === e) ? 'Ok' : (f < e ? 'Faltante' : 'Sobrante');
    if (estado === 'Ok') ok++; else if (estado === 'Faltante') faltante++; else sobrante++;
    if (e !== f) detalle.push({ sku: sku2, esperado: e, fisico: f, diferencia: f - e, estado: estado });
  }
  var evs = eventosDe_(fileId);
  var operadores = {};
  evs.forEach(function (ev) { if (ev.operador) operadores[ev.operador] = true; });

  return {
    skus: Object.keys(todos).length, ok: ok, faltante: faltante, sobrante: sobrante,
    unidadesEsperadas: uEsp, unidadesFisicas: uFis, diferencia: uFis - uEsp,
    eventos: evs.length, operadores: Object.keys(operadores),
    exactitud: Object.keys(todos).length ? Math.round(1000 * ok / Object.keys(todos).length) / 10 : 0,
    detalle: detalle
  };
}

function obtenerResumen(fileId) {
  try { return ok_(resumenRecepcion_(fileId)); } catch (e) { return error_(e); }
}

// ==========================================================================
// Cierre
// ==========================================================================

function finalizarRecepcionConfirmada(fileId, firmaBase64, tiempoTranscurrido, nombreOperario) {
  try {
    return conCandado_(function () {
      var hoja = hoja_(CFG.HOJA_HISTORIAL);
      var data = hoja.getDataRange().getValues();
      var nombreContenedor = null;

      for (var i = 1; i < data.length; i++) {
        // El codigo anterior hacia indexOf sobre un valor que podia no ser string.
        var idDrive = String(data[i][5] || data[i][4] || '');
        if (idDrive && idDrive.indexOf(fileId) > -1) {
          hoja.getRange(i + 1, 4).setValue('Cerrado');
          nombreContenedor = data[i][2];
          break;
        }
      }
      if (nombreContenedor === null) {
        // Antes se enviaba el correo igual y la recepcion quedaba abierta.
        return error_('No se encontro la recepcion en el Historial. No se cerro nada.',
                      'RECEPCION_NO_ENCONTRADA');
      }

      escribirPackingFinal_(fileId);
      var resumen = resumenRecepcion_(fileId);
      enviarReporte_(nombreContenedor, resumen, firmaBase64, tiempoTranscurrido, nombreOperario);

      return ok_(resumen, 'Contenedor cerrado. Packing list final actualizado y reporte enviado.');
    });
  } catch (e) {
    return error_(e);
  }
}

function enviarReporte_(nombreContenedor, r, firmaBase64, tiempo, operario) {
  var destino = CFG.EMAIL_REPORTE || Session.getEffectiveUser().getEmail();
  if (!destino) return;

  var filas = r.detalle.map(function (d) {
    var color = d.estado === 'Sobrante' ? '#ef4444' : '#f59e0b';
    return '<tr>' +
      '<td style="padding:10px;border-bottom:1px solid #e2e8f0;font-family:monospace;font-weight:bold;">' + d.sku + '</td>' +
      '<td style="padding:10px;text-align:center;border-bottom:1px solid #e2e8f0;color:#64748b;">' + d.esperado + '</td>' +
      '<td style="padding:10px;text-align:center;border-bottom:1px solid #e2e8f0;font-weight:bold;">' + d.fisico + '</td>' +
      '<td style="padding:10px;text-align:center;color:' + color + ';font-weight:bold;border-bottom:1px solid #e2e8f0;">' +
        (d.diferencia > 0 ? '+' + d.diferencia : d.diferencia) + ' (' + d.estado + ')</td></tr>';
  }).join('');

  if (!filas) {
    filas = "<tr><td colspan='4' style='padding:20px;text-align:center;color:#10b981;font-weight:bold;background:#ecfdf5;'>" +
            'Inventario 100% cuadrado. No se encontraron diferencias.</td></tr>';
  }

  var html =
    '<div style="font-family:Segoe UI,sans-serif;max-width:650px;margin:0 auto;border:1px solid #cbd5e1;border-radius:12px;overflow:hidden;">' +
      '<div style="background:#0f172a;color:white;padding:25px;text-align:center;">' +
        '<h2 style="margin:0;">ITSANET IMS - Reporte de Recepcion</h2>' +
        '<p style="margin:5px 0 0 0;color:#94a3b8;font-size:14px;">Contenedor: ' + nombreContenedor + '</p>' +
      '</div>' +
      '<div style="padding:30px;background:#f8fafc;">' +
        '<p><b>Operario:</b> ' + (operario || '-') + ' &nbsp;|&nbsp; <b>Tiempo total:</b> ' + (tiempo || '-') + '</p>' +
        '<p><b>Unidades esperadas:</b> ' + r.unidadesEsperadas + ' &nbsp;|&nbsp; <b>Recibidas:</b> ' + r.unidadesFisicas +
          ' &nbsp;|&nbsp; <b>Exactitud:</b> ' + r.exactitud + '%</p>' +
        '<p><b>SKU:</b> ' + r.ok + ' Ok &nbsp;·&nbsp; ' + r.faltante + ' Faltante &nbsp;·&nbsp; ' + r.sobrante + ' Sobrante</p>' +
        '<p style="color:#64748b;font-size:13px;">Validado por: ' + r.operadores.join(', ') +
          ' &nbsp;|&nbsp; ' + r.eventos + ' conteos registrados.</p>' +
        '<h3 style="border-bottom:2px solid #2563eb;padding-bottom:8px;">Detalle de discrepancias</h3>' +
        '<table style="width:100%;border-collapse:collapse;background:white;border:1px solid #e2e8f0;">' +
          '<thead><tr style="background:#f1f5f9;text-align:left;font-size:12px;color:#475569;">' +
            '<th style="padding:12px;">Referencia</th><th style="padding:12px;text-align:center;">Esperado</th>' +
            '<th style="padding:12px;text-align:center;">Fisico</th><th style="padding:12px;text-align:center;">Diferencia</th>' +
          '</tr></thead><tbody>' + filas + '</tbody></table>' +
        (firmaBase64 ?
          '<h3 style="border-bottom:2px solid #2563eb;padding-bottom:8px;margin-top:30px;">Firma de conformidad</h3>' +
          '<div style="border:2px dashed #cbd5e1;padding:20px;text-align:center;background:white;border-radius:12px;">' +
            '<img src="' + firmaBase64 + '" alt="Firma" style="max-width:100%;max-height:150px;" />' +
          '</div>' : '') +
      '</div></div>';

  MailApp.sendEmail({ to: destino, subject: 'Reporte de Cierre: ' + nombreContenedor, htmlBody: html });
}
