/**
 * ITSANET IMS - Recepcion de mercaderia.
 * API publica que consume Index.html via google.script.run.
 */

function doGet() {
  return HtmlService.createHtmlOutputFromFile('Index')
      .setTitle('ITSANET - Recepcion')
      .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
      .addMetaTag('viewport', 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no');
}

// ==========================================================================
// Carga del packing list
// ==========================================================================

function procesarArchivo(base64Data, fileName) {
  try {
    var blob = Utilities.newBlob(Utilities.base64Decode(base64Data),
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', fileName);
    var file = DriveApp.createFile(blob);
    var fileId = file.getId();

    // Verifica que sea legible como hoja antes de registrarlo: si Drive no lo
    // convirtio, el operador se enteraria recien al abrir la recepcion.
    try {
      SpreadsheetApp.openById(fileId).getSheets()[0].getRange(1, 1).getValue();
    } catch (e) {
      file.setTrashed(true);
      return { success: false, mensaje:
        'El archivo no se pudo abrir como hoja de calculo. Subalo convertido a ' +
        'Google Sheets, o active la conversion automatica en Drive.' };
    }

    var hoja = hoja_(CFG.HOJA_HISTORIAL);
    var idContenedor = 'CONT-' + Utilities.formatDate(
        ahora_(), Session.getScriptTimeZone(), 'yyyyMMdd-HHmmss');
    hoja.appendRow([idContenedor, ahora_(), fileName, 'Pendiente Validación',
                    file.getUrl(), fileId]);
    return { success: true, id: idContenedor, mensaje: 'Contenedor registrado exitosamente.' };
  } catch (error) {
    return { success: false, mensaje: String(error) };
  }
}

function obtenerListaContenedores() {
  try {
    var hoja = hoja_(CFG.HOJA_HISTORIAL);
    var data = hoja.getDataRange().getValues();
    var rich = hoja.getDataRange().getRichTextValues();
    var salida = [];

    for (var i = 1; i < data.length; i++) {
      var id = data[i][0], fecha = data[i][1], nombre = data[i][2], estado = data[i][3];
      if (!id || estado === 'Cerrado') continue;

      var enlace = rich[i][4] ? rich[i][4].getLinkUrl() : null;
      var texto = enlace ? enlace : String(data[i][5] || data[i][4]);
      var m = texto.match(/[-\w]{25,}/);
      if (!m) continue;

      salida.push({
        id: id, nombre: nombre, estado: estado, fileId: m[0],
        fecha: (fecha instanceof Date)
            ? Utilities.formatDate(fecha, Session.getScriptTimeZone(), 'dd/MM/yyyy HH:mm')
            : String(fecha)
      });
    }
    return ok_(salida);
  } catch (e) {
    return error_(e);
  }
}

/**
 * Estado completo de la recepcion: lineas del packing list + lo contado.
 *
 * Las cantidades fisicas ya no se leen de la columna J del archivo: se derivan
 * del libro mayor de eventos, que es la unica fuente de verdad.
 */
function obtenerDatosContenedor(fileId) {
  try {
    var hoja = SpreadsheetApp.openById(fileId).getSheets()[0];
    var data = hoja.getDataRange().getValues();

    var lineas = [];
    var esperadoPorSku = {};
    for (var i = 1; i < data.length; i++) {
      var sku = normalizarSku_(data[i][CFG.COL_SKU - 1]);
      if (!sku) continue;
      var cant = aNumero_(data[i][CFG.COL_CANTIDAD - 1]);
      lineas.push({
        filaReaEnExcel: i + 1,
        referencia: sku,
        descripcion: limpiar_(data[i][CFG.COL_DESCRIPCION - 1]),
        embarque: limpiar_(data[i][CFG.COL_EMBARQUE - 1]),
        esperada: cant
      });
      esperadoPorSku[sku] = (esperadoPorSku[sku] || 0) + cant;
    }

    var contado = contadoPorSku_(fileId);
    var mapa = maestro_();

    // Agregado por SKU: es el nivel al que se cuenta, no la linea del Excel.
    var skus = [];
    var vistos = {};
    for (var j = 0; j < lineas.length; j++) {
      var s = lineas[j].referencia;
      if (vistos[s]) continue;
      vistos[s] = true;
      skus.push({
        sku: s,
        descripcion: lineas[j].descripcion,
        esperada: esperadoPorSku[s],
        fisica: contado[s] || 0,
        enDepot: !!mapa[s],
        ubicaciones: ubicacionesDeSku_(fileId, s),
        enPackingList: true
      });
    }
    // Sobrantes: contados pero ausentes del packing list.
    for (var sk in contado) {
      if (!vistos[sk] && contado[sk] !== 0) {
        skus.push({
          sku: sk, descripcion: (mapa[sk] ? mapa[sk].descripcion : ''),
          esperada: 0, fisica: contado[sk], enDepot: !!mapa[sk],
          ubicaciones: ubicacionesDeSku_(fileId, sk), enPackingList: false
        });
      }
    }

    return ok_({ skus: skus, lineas: lineas.length });
  } catch (e) {
    return error_(e);
  }
}

// ==========================================================================
// Escaneo
// ==========================================================================

/** Paso 1: valida el codigo y sugiere donde guardarlo. */
function lookupCodigo(fileId, codigo) {
  try {
    var depot = resolverCodigo_(codigo);
    var sku = depot.existe && depot.sku ? depot.sku : normalizarSku_(codigo);
    if (!sku) return error_('Codigo vacio o invalido.', 'CODIGO_INVALIDO');

    var hoja = SpreadsheetApp.openById(fileId).getSheets()[0];
    var data = hoja.getDataRange().getValues();
    var esperado = 0, descripcion = '';
    for (var i = 1; i < data.length; i++) {
      if (normalizarSku_(data[i][CFG.COL_SKU - 1]) === sku) {
        esperado += aNumero_(data[i][CFG.COL_CANTIDAD - 1]);
        if (!descripcion) descripcion = limpiar_(data[i][CFG.COL_DESCRIPCION - 1]);
      }
    }

    var contado = contadoDeSku_(fileId, sku);
    var ubic = ubicacionesDeSku_(fileId, sku);
    var avisos = [];

    if (esperado === 0) {
      avisos.push('Este SKU NO esta en el packing list: lo que registre sera SOBRANTE.');
    }
    if (depot.mensaje) avisos.push(depot.mensaje);
    if (ubic.length) {
      var lista = ubic.map(function (u) { return u.pallet + ' (' + u.cantidad + ')'; }).join(', ');
      avisos.push('Este SKU ya fue guardado en: ' + lista + '. Use el mismo pallet si es posible.');
    }
    if (esperado > 0 && contado >= esperado) {
      avisos.push('Ya se completo la cantidad esperada (' + esperado + ').');
    }

    return ok_({
      sku: sku,
      descripcion: descripcion || depot.descripcion || '',
      enPackingList: esperado > 0,
      esperado: esperado,
      contado: contado,
      pendiente: Math.max(esperado - contado, 0),
      depot: depot,
      ubicaciones: ubic,
      palletSugerido: ubic.length ? ubic[0].pallet : null,
      avisos: avisos
    });
  } catch (e) {
    return error_(e);
  }
}

/**
 * Paso 2: registra la cantidad fisica encontrada.
 *
 * Atomico (candado de escritura) e idempotente (el doble disparo del lector o
 * un reintento de red no suman dos veces).
 */
function registrarConteo(p) {
  try {
    var sku = normalizarSku_(p.codigo);
    if (!sku) return error_('Codigo de producto vacio o invalido.', 'CODIGO_INVALIDO');

    var cant = aNumero_(p.cantidad);
    if (cant === 0) return error_('La cantidad no puede ser 0.', 'CANTIDAD_INVALIDA');
    if (cant < 0 && p.tipo !== 'AJUSTE') {
      return error_('Las cantidades negativas requieren un ajuste de supervisor.', 'AJUSTE_REQUERIDO');
    }

    var pallet = normalizarPallet_(p.pallet);
    if (!palletValido_(pallet)) {
      return error_('Pallet invalido. Use formato alfanumerico (A1, B04) o subpallet (A1.1, B04.3).',
                    'PALLET_INVALIDO');
    }

    var estadoFisico = String(p.estadoFisico || 'BUENO').toUpperCase();
    if (estadoFisico !== 'BUENO' && estadoFisico !== 'MALO') {
      return error_('Estado fisico debe ser BUENO o MALO.', 'ESTADO_INVALIDO');
    }
    if (estadoFisico === 'MALO' && !limpiar_(p.observacion)) {
      return error_('Un item en mal estado fisico requiere observacion.', 'OBSERVACION_REQUERIDA');
    }

    return conCandado_(function () {
      // Idempotencia
      if (p.idem) {
        var previo = eventoPorIdem_(p.idem);
        if (previo) return respuestaConteo_(p.fileId, previo, true);
      }

      // Sobrante: exige confirmacion explicita del operador.
      var hoja = SpreadsheetApp.openById(p.fileId).getSheets()[0];
      var data = hoja.getDataRange().getValues();
      var esperado = 0;
      for (var i = 1; i < data.length; i++) {
        if (normalizarSku_(data[i][CFG.COL_SKU - 1]) === sku) {
          esperado += aNumero_(data[i][CFG.COL_CANTIDAD - 1]);
        }
      }
      var contado = contadoDeSku_(p.fileId, sku);
      if (cant > 0 && (contado + cant) > esperado && !p.confirmarSobrante) {
        return error_('SOBRANTE: el packing list declara ' + esperado + ' y ya hay ' + contado +
                      '. Esta cantidad genera ' + (contado + cant - esperado) +
                      ' de exceso. Confirme para registrarlo.', 'CONFIRMAR_SOBRANTE');
      }

      var depot = resolverCodigo_(sku);
      if (!depot.existe) {
        registrarPendiente_(p.fileId, sku, depot, normalizarEan_(p.ean), p.operador);
      }

      var id = agregarEvento_({
        fileId: p.fileId, recepcion: p.recepcion || '', sku: sku,
        ean: normalizarEan_(p.ean), pallet: pallet, cantidad: cant,
        estadoFisico: estadoFisico, tipo: p.tipo || 'CONTEO',
        observacion: limpiar_(p.observacion), operador: limpiar_(p.operador),
        dispositivo: limpiar_(p.dispositivo), idem: p.idem || ''
      });

      return respuestaConteo_(p.fileId, {
        id: id, sku: sku, pallet: pallet, cantidad: cant, operador: p.operador
      }, false);
    });
  } catch (e) {
    return error_(e);
  }
}

function respuestaConteo_(fileId, evento, duplicado) {
  var hoja = SpreadsheetApp.openById(fileId).getSheets()[0];
  var data = hoja.getDataRange().getValues();
  var esperado = 0;
  for (var i = 1; i < data.length; i++) {
    if (normalizarSku_(data[i][CFG.COL_SKU - 1]) === evento.sku) {
      esperado += aNumero_(data[i][CFG.COL_CANTIDAD - 1]);
    }
  }
  var contado = contadoDeSku_(fileId, evento.sku);
  return ok_({
    eventoId: evento.id, duplicado: !!duplicado, sku: evento.sku,
    pallet: evento.pallet, cantidadRegistrada: evento.cantidad,
    esperado: esperado, contado: contado,
    pendiente: Math.max(esperado - contado, 0),
    ubicaciones: ubicacionesDeSku_(fileId, evento.sku)
  });
}

/** Reversa un conteo con un evento compensatorio. Nunca borra el original. */
function anularConteo(fileId, eventoId, motivo, operador) {
  try {
    if (!limpiar_(motivo)) return error_('Debe indicar el motivo de la anulacion.', 'MOTIVO_REQUERIDO');

    return conCandado_(function () {
      var evs = eventosDe_(fileId);
      var orig = null;
      for (var i = 0; i < evs.length; i++) {
        if (String(evs[i].id) === String(eventoId)) orig = evs[i];
        if (String(evs[i].ref) === String(eventoId)) {
          return error_('Ese conteo ya fue anulado.', 'YA_ANULADO');
        }
      }
      if (!orig) return error_('Evento no encontrado en esta recepcion.', 'NO_ENCONTRADO');
      if (orig.tipo === 'ANULACION') return error_('Ese evento ya es una anulacion.', 'YA_ANULADO');

      agregarEvento_({
        fileId: fileId, sku: orig.sku, ean: orig.ean, pallet: orig.pallet,
        cantidad: -orig.cantidad, estadoFisico: orig.estadoFisico, tipo: 'ANULACION',
        observacion: 'ANULA ' + orig.id + ': ' + limpiar_(motivo),
        operador: limpiar_(operador), ref: orig.id
      });
      return ok_({ sku: orig.sku, contado: contadoDeSku_(fileId, orig.sku) },
                 'Conteo anulado. El registro original queda en la bitacora.');
    });
  } catch (e) {
    return error_(e);
  }
}

/** Historial de conteos de la recepcion, para la vista de bitacora. */
function obtenerBitacora(fileId, limite) {
  try {
    var evs = eventosDe_(fileId);
    var anulados = {};
    evs.forEach(function (e) { if (e.ref) anulados[e.ref] = true; });
    evs.sort(function (a, b) { return b.fecha - a.fecha; });
    return ok_(evs.slice(0, limite || 100).map(function (e) {
      return {
        id: e.id, sku: e.sku, pallet: e.pallet, cantidad: e.cantidad,
        estadoFisico: e.estadoFisico, tipo: e.tipo, observacion: e.observacion,
        ean: e.ean, operador: e.operador, hora: fechaIso_(e.fecha),
        anulado: !!anulados[e.id]
      };
    }));
  } catch (e) {
    return error_(e);
  }
}
