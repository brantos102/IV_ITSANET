/**
 * Informe final de la recepción.
 *
 * Regla del cliente, textual: «si tenemos 22 filas debemos entregar 22 filas».
 * Por eso el archivo se construye desde la subcolección `lineas`, que conserva
 * el orden y el número de fila del archivo original, y NO desde el agregado por
 * SKU. Se añaden columnas a la derecha; no se añade ni se quita ninguna fila.
 *
 * Lo que llegó sin estar en el packing list va en su propia hoja ADICIONALES, y
 * los conteos uno a uno en BITACORA, para que Depot reciba la tabla limpia y el
 * auditor tenga el detalle en el mismo archivo.
 */
import { collection, getDocs, query, orderBy } from 'https://www.gstatic.com/firebasejs/10.14.1/firebase-firestore.js';
import { db } from './auth.js';
import { aNumero, decodificarPallets } from './datos.js';

async function leerColeccion(recepcionId, nombre) {
  const snap = await getDocs(collection(db, 'recepciones', recepcionId, nombre));
  return snap.docs.map((d) => ({ id: d.id, ...d.data() }));
}

/**
 * Reparte el conteo físico de un SKU entre sus líneas del packing list.
 *
 * Un mismo SKU puede venir en varias líneas (distinta factura o embarque). El
 * conteo es por SKU, así que hay que decidir dónde va cada unidad: se llenan las
 * líneas en orden hasta su cantidad declarada, y el excedente —si lo hay— se
 * acumula en la última línea de ese SKU, que es donde el sobrante queda visible.
 */
export function repartirPorLinea(lineas, totalPorSku) {
  const restante = { ...totalPorSku };
  const ultima = {};
  lineas.forEach((l) => { ultima[l.sku] = l.linea; });

  return lineas.map((l) => {
    const declarada = aNumero(l.cantidad, 0);
    const disponible = aNumero(restante[l.sku], 0);
    const fisica = ultima[l.sku] === l.linea
      ? disponible                              // la última se queda con todo lo que sobre
      : Math.max(Math.min(disponible, declarada), 0);
    restante[l.sku] = disponible - fisica;
    return { ...l, fisica, diferencia: fisica - declarada };
  });
}

const etiquetaEstado = (declarada, fisica) => {
  if (fisica === declarada) return declarada === 0 ? 'SIN CANTIDAD' : 'OK';
  if (fisica === 0) return 'NO LLEGO';
  return fisica < declarada ? 'FALTANTE' : 'SOBRANTE';
};

/** Reúne todo lo necesario para el informe con 4 lecturas de colección. */
export async function reunirInforme(recepcionId, recepcion) {
  const [lineas, skus, adicionales, eventos] = await Promise.all([
    leerColeccion(recepcionId, 'lineas'),
    leerColeccion(recepcionId, 'skus'),
    leerColeccion(recepcionId, 'adicionales'),
    getDocs(query(collection(db, 'recepciones', recepcionId, 'eventos'), orderBy('creadoEn', 'asc')))
      .then((s) => s.docs.map((d) => ({ id: d.id, ...d.data() }))),
  ]);

  lineas.sort((a, b) => aNumero(a.linea) - aNumero(b.linea));

  const porSku = {};
  const palletsPorSku = {};
  const pncPorSku = {};
  for (const s of skus) {
    porSku[s.sku] = aNumero(s.contado, 0);
    palletsPorSku[s.sku] = Object.entries(decodificarPallets(s.pallets))
      .sort((a, b) => b[1] - a[1])
      .map(([p, c]) => `${p}(${c})`)
      .join(' ');
    pncPorSku[s.sku] = s.tienePnc === true;
  }

  // Observaciones del operario, por SKU y sin repetir.
  const obsPorSku = {};
  // Dónde quedó físicamente. Va en su propia columna: el pallet es cómo se
  // movió, la posición real es dónde está, y para buscarlo después vale la
  // segunda.
  const posPorSku = {};
  for (const e of eventos) {
    if (e.tipo === 'ANULACION') continue;
    if (e.observacion) {
      const set = (obsPorSku[e.sku] = obsPorSku[e.sku] || new Set());
      set.add(e.observacion);
    }
    if (e.posicionReal) {
      const set = (posPorSku[e.sku] = posPorSku[e.sku] || new Set());
      set.add(e.posicionReal);
    }
  }

  const detalle = repartirPorLinea(lineas, porSku).map((l) => ({
    ...l,
    pallets: palletsPorSku[l.sku] || '',
    estado: etiquetaEstado(aNumero(l.cantidad, 0), l.fisica),
    pnc: pncPorSku[l.sku] ? 'PNC' : '',
    posicionReal: [...(posPorSku[l.sku] || [])].join(' / ').slice(0, 120),
    observacion: [...(obsPorSku[l.sku] || [])].join(' | ').slice(0, 300),
  }));

  const adicionalesDetalle = adicionales.map((a) => {
    const s = skus.find((x) => x.sku === a.sku);
    return {
      sku: a.sku,
      descripcion: a.descripcion || s?.descripcion || '',
      fisica: aNumero(s?.contado, 0),
      pallets: palletsPorSku[a.sku] || '',
      motivo: a.motivo || '',
      detectadoPor: a.detectadoPorEmail || '',
      observacion: [...(obsPorSku[a.sku] || [])].join(' | ').slice(0, 300),
    };
  }).filter((a) => a.fisica !== 0 || a.motivo);

  return { recepcion, detalle, adicionales: adicionalesDetalle, eventos, skus };
}

/** Construye el .xlsx y lo devuelve en base64, listo para el correo. */
export function construirLibro({ recepcion, detalle, adicionales, eventos }) {
  if (typeof XLSX === 'undefined') {
    throw new Error('No se cargó la librería de Excel. Recarga la página.');
  }
  const libro = XLSX.utils.book_new();

  // --- Hoja 1: el packing list, misma cantidad de filas que el original --- //
  const validada = detalle.map((l) => ({
    'ITEM': l.sku,
    'DESCRIPCION': l.descripcion || '',
    'REFERENCIA PEDIDO': l.referencia || '',
    'FACTURA': l.factura || '',
    'EMBARQUE': l.embarque || '',
    'CANTIDAD': aNumero(l.cantidad, 0),
    'CANTIDAD FISICA': l.fisica,
    'DIFERENCIA': l.diferencia,
    'VALIDACION': l.estado,
    'PALLET': l.pallets,
    'POSICION REAL ASIGNADA': l.posicionReal,
    'ESTADO MERCADERIA': l.pnc || 'BUENO',
    'OBSERVACION': l.observacion,
  }));
  const h1 = XLSX.utils.json_to_sheet(validada);
  h1['!cols'] = [{ wch: 18 }, { wch: 40 }, { wch: 16 }, { wch: 14 }, { wch: 14 },
    { wch: 10 }, { wch: 14 }, { wch: 11 }, { wch: 13 }, { wch: 22 }, { wch: 24 },
    { wch: 17 }, { wch: 38 }];
  h1['!autofilter'] = { ref: XLSX.utils.encode_range({ s: { r: 0, c: 0 },
    e: { r: validada.length, c: 12 } }) };
  XLSX.utils.book_append_sheet(libro, h1, 'VALIDADA');

  // --- Hoja 2: adicionales, aparte para no alterar el conteo de filas --- //
  const h2 = XLSX.utils.json_to_sheet(adicionales.length ? adicionales.map((a) => ({
    'ITEM': a.sku,
    'DESCRIPCION': a.descripcion,
    'CANTIDAD FISICA': a.fisica,
    'PALLET': a.pallets,
    'MOTIVO': a.motivo,
    'OBSERVACION': a.observacion,
    'DETECTADO POR': a.detectadoPor,
  })) : [{ 'ITEM': '', 'DESCRIPCION': 'Sin adicionales en esta recepción.' }]);
  h2['!cols'] = [{ wch: 18 }, { wch: 40 }, { wch: 14 }, { wch: 22 }, { wch: 34 },
    { wch: 34 }, { wch: 26 }];
  XLSX.utils.book_append_sheet(libro, h2, 'ADICIONALES');

  // --- Hoja 3: la bitácora, el respaldo de cada unidad contada --- //
  const h3 = XLSX.utils.json_to_sheet(eventos.map((e) => ({
    'FECHA': e.creadoEn?.toDate ? e.creadoEn.toDate().toLocaleString('es-EC') : '',
    'ITEM': e.sku,
    'CODIGO ESCANEADO': e.codigoEscaneado || e.sku,
    'CANTIDAD': aNumero(e.cantidad, 0),
    'PALLET': e.pallet || '',
    'POSICION REAL': e.posicionReal || '',
    'ESTADO': e.estadoFisico || '',
    'TIPO': e.tipo || 'CONTEO',
    'OPERARIO': e.operadorNombre || e.operadorEmail || '',
    'OBSERVACION': e.observacion || '',
    'FOTOS': (e.fotos || []).join(' '),
  })));
  h3['!cols'] = [{ wch: 20 }, { wch: 18 }, { wch: 18 }, { wch: 10 }, { wch: 12 },
    { wch: 16 }, { wch: 9 }, { wch: 11 }, { wch: 28 }, { wch: 34 }, { wch: 40 }];
  XLSX.utils.book_append_sheet(libro, h3, 'BITACORA');

  const base64 = XLSX.write(libro, { bookType: 'xlsx', type: 'base64' });
  return {
    base64,
    nombre: `validacion-${(recepcion?.codigo || 'recepcion')}-${new Date().toISOString().slice(0, 10)}`,
    filas: detalle.length,
  };
}

/** Descarga local del mismo archivo, por si el correo falla o no se quiere enviar. */
export function descargarLibro(libro) {
  const bytes = Uint8Array.from(atob(libro.base64), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes],
    { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = libro.nombre + '.xlsx';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

/** Fotos de PNC para incrustar en el correo. */
export function fotosDe(eventos, max = 12) {
  const out = [];
  for (const e of eventos) {
    for (const url of e.fotos || []) {
      if (out.length >= max) return out;
      out.push({ url, enlace: url, sku: e.sku });
    }
  }
  return out;
}
