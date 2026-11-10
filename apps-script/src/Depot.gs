/**
 * Validacion contra el maestro de productos Depot.
 *
 * Requerimiento inicial que no existia en la version anterior: al escanear, el
 * sistema debe decir si el producto existe en Depot o avisar que hay que
 * validarlo a profundidad / crearlo, y registrar el codigo EAN.
 *
 * El maestro vive en la hoja MAESTRO del libro base (export de Depot). Se lee
 * una vez y se cachea en memoria del script.
 */

var ACCION_OK = 'OK';
var ACCION_REVISAR = 'VALIDAR_PROFUNDIDAD';
var ACCION_CREAR = 'CREAR';

var _maestroCache = null;

/** { sku: {descripcion, ean, unidad} } con el SKU ya normalizado. */
function maestro_() {
  if (_maestroCache) return _maestroCache;

  var hoja = libroBase_().getSheetByName(CFG.HOJA_MAESTRO);
  if (!hoja || hoja.getLastRow() < 2) { _maestroCache = {}; return _maestroCache; }

  var datos = hoja.getDataRange().getValues();
  var hdr = datos[0].map(function (h) { return limpiar_(h).toLowerCase(); });
  var cSku = hdr.indexOf('producto_id');
  var cDesc = hdr.indexOf('descripcion');
  var cEan = hdr.indexOf('codigo_barra');
  var cUnidad = hdr.indexOf('unidad_id');
  if (cSku < 0) cSku = 1;   // layout por defecto del export de Depot

  var mapa = {};
  for (var i = 1; i < datos.length; i++) {
    var sku = normalizarSku_(datos[i][cSku]);
    if (!sku || sku === '0') continue;
    var ean = cEan >= 0 ? limpiar_(datos[i][cEan]) : '';
    mapa[sku] = {
      descripcion: cDesc >= 0 ? limpiar_(datos[i][cDesc]) : '',
      ean: (ean && ean.toUpperCase() !== 'DEFAULT' && ean !== '0') ? ean : '',
      unidad: cUnidad >= 0 ? limpiar_(datos[i][cUnidad]) : ''
    };
  }
  _maestroCache = mapa;
  return mapa;
}

/**
 * Resuelve un codigo escaneado contra el maestro.
 *
 * Devuelve la accion que debe tomar el operador. Cuando el SKU no existe pero
 * hay codigos parecidos, pide validarlo a profundidad antes de crear un
 * duplicado en Depot.
 */
function resolverCodigo_(codigo) {
  var sku = normalizarSku_(codigo);
  if (!sku) {
    return { sku: '', existe: false, accion: ACCION_CREAR, mensaje: 'Codigo vacio o invalido.' };
  }

  var mapa = maestro_();
  if (mapa[sku]) {
    return {
      sku: sku, existe: true, accion: ACCION_OK,
      descripcion: mapa[sku].descripcion, ean: mapa[sku].ean,
      unidad: mapa[sku].unidad, mensaje: ''
    };
  }

  // Busqueda por EAN
  var ean = normalizarEan_(codigo);
  if (ean) {
    for (var k in mapa) {
      if (mapa[k].ean && normalizarEan_(mapa[k].ean) === ean) {
        return {
          sku: k, existe: true, accion: ACCION_OK,
          descripcion: mapa[k].descripcion, ean: mapa[k].ean, mensaje: ''
        };
      }
    }
  }

  // Codigos similares: misma raiz. Evita crear duplicados en Depot.
  var candidatos = [];
  if (sku.length >= 5) {
    var raiz = sku.substring(0, 7);
    for (var c in mapa) {
      if (c !== sku && c.indexOf(raiz) === 0) {
        candidatos.push({ sku: c, descripcion: mapa[c].descripcion });
        if (candidatos.length >= 6) break;
      }
    }
  }

  if (candidatos.length) {
    return {
      sku: sku, existe: false, accion: ACCION_REVISAR, candidatos: candidatos,
      mensaje: 'SKU no existe en Depot. Hay ' + candidatos.length +
               ' codigo(s) similar(es): validar a profundidad antes de crearlo.'
    };
  }
  return {
    sku: sku, existe: false, accion: ACCION_CREAR, candidatos: [],
    mensaje: 'SKU no existe en Depot. Registre el codigo EAN y solicite su creacion.'
  };
}

/** Deja constancia de un SKU que hay que crear o revisar en Depot. */
function registrarPendiente_(fileId, sku, resultado, ean, operador) {
  var hoja = hoja_(CFG.HOJA_PENDIENTES,
      ['fecha', 'file_id', 'sku', 'descripcion', 'ean', 'estado_depot', 'estado',
       'candidatos', 'detectado_por', 'notas']);
  var ultima = hoja.getLastRow();

  if (ultima >= 2) {
    var previos = hoja.getRange(2, 2, ultima - 1, 2).getValues();   // file_id, sku
    for (var i = 0; i < previos.length; i++) {
      if (String(previos[i][0]) === String(fileId) && String(previos[i][1]) === sku) {
        if (ean) hoja.getRange(i + 2, 5).setValue(ean);   // completa el EAN si faltaba
        return;
      }
    }
  }
  hoja.appendRow([
    ahora_(), fileId, sku, resultado.descripcion || '', ean || '',
    resultado.accion, 'PENDIENTE',
    JSON.stringify(resultado.candidatos || []), operador || '', ''
  ]);
}

/** Carga el maestro desde la primera hoja de un archivo de Drive. */
function cargarMaestroDesde(fileIdOrigen, nombreHoja) {
  try {
    var origen = SpreadsheetApp.openById(fileIdOrigen);
    var hojaOrigen = nombreHoja ? origen.getSheetByName(nombreHoja) : origen.getSheets()[0];
    if (!hojaOrigen) return error_('No se encontro la hoja ' + nombreHoja);

    var datos = hojaOrigen.getDataRange().getValues();
    if (datos.length < 2) return error_('El maestro esta vacio.');

    var destino = hoja_(CFG.HOJA_MAESTRO, datos[0]);
    destino.clear();
    destino.getRange(1, 1, datos.length, datos[0].length).setValues(datos);
    destino.getRange(1, 1, 1, datos[0].length).setFontWeight('bold');
    _maestroCache = null;

    return ok_({ filas: datos.length - 1 }, (datos.length - 1) + ' productos cargados.');
  } catch (e) {
    return error_(e);
  }
}
