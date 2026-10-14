/**
 * Modelo de datos y lectura del packing list.
 *
 * El archivo se analiza EN EL NAVEGADOR y se escribe a Firestore. Sin Cloud
 * Functions no hay dónde hacerlo del lado servidor, y además así el operario
 * ve el resultado al instante en vez de esperar a un disparador.
 */
import {
  collection, doc, getDoc, getDocs, setDoc, updateDoc, query, where,
  orderBy, limit, writeBatch, serverTimestamp, onSnapshot,
} from 'https://www.gstatic.com/firebasejs/10.14.1/firebase-firestore.js';
import { db } from './auth.js';

// --------------------------------------------------------------------------- //
// Normalización — la misma que usa el proxy, para que los cruces coincidan
// --------------------------------------------------------------------------- //
const INVISIBLES = /[ ​‌‍﻿\t\r\n]/g;

export function limpiar(v) {
  if (v === null || v === undefined) return '';
  return String(v).replace(INVISIBLES, ' ').replace(/\s+/g, ' ').trim();
}

/** Clave canónica de cualquier código: SKU, EAN o alterno. */
export function normalizarCodigo(v) {
  return limpiar(v).toUpperCase().replace(/[\s\-_.]/g, '');
}

export function normalizarPallet(v) {
  return limpiar(v).toUpperCase().replace(/[\s_-]/g, '');
}

/**
 * Posición del almacén: `A-01-03-2`.
 *
 * NO vale `normalizarPallet` aquí: ese borra los guiones, y los guiones son el
 * separador de nave, calle, columna y nivel. Pasar una posición por él la
 * convertía en `A01032`, que no se puede buscar en Depot ni leer de un vistazo.
 */
export function normalizarPosicion(v) {
  return limpiar(v).toUpperCase().replace(/\s+/g, '').slice(0, 40);
}

export function palletValido(c) {
  const p = normalizarPallet(c);
  return !!p && p.length <= 40 && /^[A-Z0-9]+(\.[A-Z0-9]+)*$/.test(p);
}

/**
 * Convierte a número tolerando cómo se escriben las cantidades aquí.
 *
 * «1.234,50» y «1,234.50» son el mismo número con los separadores invertidos.
 * Se toma como decimal el ÚLTIMO punto o coma que aparezca, y todo lo anterior
 * se trata como separador de miles. Sin esto, «1.234,50» se leía como 1,234:
 * mil unidades menos en el informe que se sube a Depot.
 */
export function aNumero(v, def = 0) {
  if (v === null || v === undefined || v === '') return def;
  if (typeof v === 'number') return Number.isFinite(v) ? v : def;

  let t = limpiar(v).replace(/[^0-9.,\-]/g, '');
  const negativo = t.startsWith('-');
  t = t.replace(/-/g, '');

  const corte = Math.max(t.lastIndexOf('.'), t.lastIndexOf(','));
  if (corte > -1) {
    const decimales = t.slice(corte + 1);
    // Tres dígitos tras el separador y sin otro separador antes: son miles.
    const esMiles = decimales.length === 3 && !/[.,]/.test(t.slice(0, corte));
    t = esMiles
      ? t.replace(/[.,]/g, '')
      : t.slice(0, corte).replace(/[.,]/g, '') + '.' + decimales;
  }

  const n = parseFloat(t);
  if (Number.isNaN(n)) return def;
  return negativo ? -n : n;
}

/**
 * Clave segura para usar un pallet dentro de un mapa de Firestore.
 *
 * Firestore trata el punto como separador de ruta: `pallets.B04.1` crearía
 * `pallets → B04 → 1`, no la clave "B04.1". Los subpallets son justo los que
 * llevan punto. Se usa `~`, que el validador de pallets no admite y por tanto
 * no puede colisionar con uno real.
 */
export const clavePallet = (p) => normalizarPallet(p).replace(/\./g, '~');
export const palletDesdeClave = (k) => String(k || '').replace(/~/g, '.');

export function decodificarPallets(mapa) {
  const out = {};
  for (const [k, v] of Object.entries(mapa || {})) {
    if (v !== 0) out[palletDesdeClave(k)] = v;
  }
  return out;
}

/**
 * Estado de un SKU. Cinco, no cuatro, y la diferencia importa.
 *
 * «Nadie lo ha buscado todavía» y «se buscó y no apareció» son cosas
 * distintas: la primera es trabajo pendiente, la segunda es un faltante
 * confirmado que hay que reclamar. Mezcladas en PENDIENTE, el operario no sabe
 * qué le queda por hacer y el supervisor no sabe qué reclamar.
 *
 * `verificado` se marca cuando alguien registra algo de ese SKU, incluido un
 * cero explícito.
 */
export function estadoDe(esperado, contado, verificado = contado !== 0) {
  if (!verificado) return esperado > 0 ? 'PENDIENTE' : 'OK';
  if (contado === esperado) return 'OK';
  if (contado === 0) return esperado > 0 ? 'NO_ENCONTRADO' : 'OK';
  return contado < esperado ? 'FALTANTE' : 'SOBRANTE';
}

/** Lo que se le muestra al operario, en su idioma. */
export const ETIQUETA_ESTADO = {
  OK: 'Completo',
  FALTANTE: 'Faltan unidades',
  NO_ENCONTRADO: 'No apareció',
  SOBRANTE: 'Sobran unidades',
  PENDIENTE: 'Sin buscar',
};

// --------------------------------------------------------------------------- //
// Lectura del packing list
// --------------------------------------------------------------------------- //

/** Alias de encabezado → campo. Se compara sin acentos y en mayúsculas. */
const ALIAS = {
  ITEM: 'sku', SKU: 'sku', CODIGO: 'sku', PARTE: 'sku', PRODUCTO: 'sku',
  'NUMERO DE PARTE': 'sku', 'PART NUMBER': 'sku', 'COD PRODUCTO': 'sku',
  DESCRIPCION: 'descripcion', DESCRIPTION: 'descripcion', DETALLE: 'descripcion',
  REFERENCIAPEDIDO: 'referencia', 'REFERENCIA PEDIDO': 'referencia',
  REFERENCIA: 'referencia', PEDIDO: 'referencia',
  FACTURA: 'factura', INVOICE: 'factura',
  CANTIDAD: 'cantidad', QTY: 'cantidad', QUANTITY: 'cantidad', CANT: 'cantidad',
  EMBARQUE: 'embarque', SHIPMENT: 'embarque', BL: 'embarque',
  PRECIOUNIT: 'precioUnit', 'PRECIO UNIT': 'precioUnit',
  PRECIOTOTAL: 'precioTotal', 'PRECIO TOTAL': 'precioTotal',
};

/** Columnas que genera la app: si vienen en el archivo, se descartan. */
const COLUMNAS_RESULTADO = new Set([
  'CANTIDAD FISICA', 'CANTIDADFISICA', 'VALIDACION', 'PALLET',
  'CODIGO BARRA', 'CODIGOBARRA', 'COD/PROD', 'CODPROD', 'OBSERVACION', 'OK',
]);

const sinAcentos = (t) => String(t).normalize('NFD').replace(/[̀-ͯ]/g, '');
const clave = (t) => sinAcentos(limpiar(t)).toUpperCase();

function mapearEncabezado(fila) {
  const mapa = {};
  fila.forEach((celda, i) => {
    const k = clave(celda);
    if (!k || COLUMNAS_RESULTADO.has(k)) return;
    const campo = ALIAS[k] || ALIAS[k.replace(/\s/g, '')];
    if (campo) mapa[i] = campo;
  });
  return mapa;
}

/**
 * Lee un .xlsx y devuelve las líneas.
 *
 * Busca la fila de encabezados en las primeras 25, así que tolera archivos con
 * títulos o logos encima de la tabla.
 */
export function leerPackingList(arrayBuffer) {
  if (typeof XLSX === 'undefined') {
    throw new Error('No se cargó la librería de Excel. Revisa la conexión y recarga.');
  }
  const libro = XLSX.read(arrayBuffer, { type: 'array' });

  for (const nombreHoja of libro.SheetNames) {
    const hoja = libro.Sheets[nombreHoja];
    const filas = XLSX.utils.sheet_to_json(hoja, { header: 1, blankrows: false, defval: '' });

    for (let i = 0; i < Math.min(filas.length, 25); i++) {
      const mapa = mapearEncabezado(filas[i]);
      const campos = new Set(Object.values(mapa));
      if (!campos.has('sku') || !campos.has('cantidad')) continue;

      // Encontrada la cabecera: todo lo de abajo son datos.
      const lineas = [];
      let descartadas = 0;
      for (let j = i + 1; j < filas.length; j++) {
        const cruda = filas[j];
        if (!cruda || cruda.every((c) => c === '' || c === null)) continue;

        const d = {};
        for (const [idx, campo] of Object.entries(mapa)) d[campo] = cruda[idx];

        const sku = normalizarCodigo(d.sku);
        if (!sku) { descartadas++; continue; }

        lineas.push({
          linea: lineas.length + 1,
          sku,
          descripcion: limpiar(d.descripcion).slice(0, 300),
          referencia: limpiar(d.referencia).slice(0, 80),
          factura: limpiar(d.factura).slice(0, 80),
          embarque: limpiar(d.embarque).slice(0, 80),
          cantidad: aNumero(d.cantidad),
          precioUnit: aNumero(d.precioUnit) || null,
          precioTotal: aNumero(d.precioTotal) || null,
        });
      }

      if (!lineas.length) continue;

      const porSku = {};
      lineas.forEach((l) => { porSku[l.sku] = (porSku[l.sku] || 0) + l.cantidad; });

      return {
        hoja: nombreHoja,
        lineas,
        descartadas,
        skusUnicos: Object.keys(porSku).length,
        unidades: lineas.reduce((a, l) => a + l.cantidad, 0),
        embarques: [...new Set(lineas.map((l) => l.embarque).filter(Boolean))],
        porSku,
      };
    }
  }

  throw new Error(
    'No se encontró la tabla. El archivo debe tener una fila de encabezados ' +
    'con al menos las columnas ITEM (o SKU) y CANTIDAD.',
  );
}

// --------------------------------------------------------------------------- //
// Recepciones
// --------------------------------------------------------------------------- //

export async function crearRecepcion({ codigo, cliente, descripcion, bultos }, usuario) {
  const id = normalizarCodigo(codigo);
  if (!id) throw new Error('El código de la recepción es obligatorio.');

  const ref = doc(db, 'recepciones', id);
  if ((await getDoc(ref)).exists()) {
    throw new Error(`Ya existe una recepción con el código ${id}.`);
  }

  await setDoc(ref, {
    codigo: id,
    cliente: limpiar(cliente).toUpperCase() || null,
    descripcion: limpiar(descripcion) || null,
    bultos: aNumero(bultos) || null,
    estado: 'ABIERTA',
    totales: { lineas: 0, skus: 0, unidades: 0 },
    creadoPorUid: usuario.uid,
    creadoPorEmail: usuario.email,
    creadoEn: serverTimestamp(),
  });
  return id;
}

/**
 * Guarda las líneas y el agregado por SKU.
 *
 * Firestore admite 500 operaciones por lote, así que se parte en tandas. Las
 * líneas son inmutables: son la versión del sistema contra la que se compara.
 */
export async function guardarPackingList(recepcionId, resultado, alAvanzar) {
  const refRec = doc(db, 'recepciones', recepcionId);
  const operaciones = [];

  resultado.lineas.forEach((l) => {
    operaciones.push({
      ref: doc(db, 'recepciones', recepcionId, 'lineas', String(l.linea)),
      datos: { ...l, creadoEn: serverTimestamp() },
    });
  });

  Object.entries(resultado.porSku).forEach(([sku, esperado]) => {
    const primera = resultado.lineas.find((l) => l.sku === sku);
    operaciones.push({
      ref: doc(db, 'recepciones', recepcionId, 'skus', sku),
      datos: {
        sku,
        descripcion: primera?.descripcion || '',
        esperado,
        contado: 0,
        pallets: {},
        estado: esperado > 0 ? 'PENDIENTE' : 'OK',
        enPackingList: true,
        tienePnc: false,
        creadoEn: serverTimestamp(),
      },
    });
  });

  const TANDA = 450;
  for (let i = 0; i < operaciones.length; i += TANDA) {
    const lote = writeBatch(db);
    operaciones.slice(i, i + TANDA).forEach((o) => lote.set(o.ref, o.datos));
    await lote.commit();
    if (alAvanzar) alAvanzar(Math.min(i + TANDA, operaciones.length), operaciones.length);
  }

  await updateDoc(refRec, {
    totales: {
      lineas: resultado.lineas.length,
      skus: resultado.skusUnicos,
      unidades: resultado.unidades,
    },
    hoja: resultado.hoja,
    embarques: resultado.embarques,
    packingListEn: serverTimestamp(),
  });
}

export async function listarRecepciones(max = 50) {
  const q = query(collection(db, 'recepciones'), orderBy('creadoEn', 'desc'), limit(max));
  const snap = await getDocs(q);
  return snap.docs.map((d) => ({ id: d.id, ...d.data() }));
}

export async function obtenerRecepcion(id) {
  const snap = await getDoc(doc(db, 'recepciones', id));
  if (!snap.exists()) throw new Error('La recepción no existe.');
  return { id: snap.id, ...snap.data() };
}

/** Escucha los SKU en tiempo real: lo que cuenta un operario lo ven los demás. */
export function escucharSkus(recepcionId, alCambiar, alFallar) {
  return onSnapshot(
    collection(db, 'recepciones', recepcionId, 'skus'),
    (snap) => alCambiar(snap.docs.map((d) => ({ id: d.id, ...d.data() }))),
    (e) => alFallar && alFallar(e),
  );
}

export async function cerrarRecepcion(recepcionId) {
  await updateDoc(doc(db, 'recepciones', recepcionId), {
    estado: 'CERRADA',
    cerradoEn: serverTimestamp(),
  });
}

// --------------------------------------------------------------------------- //
// Catálogo
// --------------------------------------------------------------------------- //

/**
 * Guarda el catálogo del WMS en Firestore.
 *
 * Esto es el precalentado: se hace una vez por recepción y convierte cada
 * escaneo en la lectura de un documento, en vez de una llamada al WMS.
 */
export async function guardarCatalogo(productos, alAvanzar) {
  const TANDA = 200;   // cada producto son 2 escrituras: producto + código
  for (let i = 0; i < productos.length; i += TANDA) {
    const lote = writeBatch(db);
    for (const p of productos.slice(i, i + TANDA)) {
      if (!p.sku) continue;
      lote.set(doc(db, 'productos', p.sku), {
        sku: p.sku,
        descripcion: p.descripcion || '',
        unidad: p.unidad || null,
        stock: p.stock ?? null,
        posicion: p.posicion || null,
        // Todas las ubicaciones donde el WMS tiene existencia de este producto.
        // Se recorta a 20: un SKU repartido en más sitios ya no se decide
        // mirando una lista, y veinte ya llenan la pantalla de un handheld.
        posiciones: (p.posiciones || []).slice(0, 30).map((u) => ({
          posicion: u.posicion || '',
          stock: aNumero(u.stock, 0),
          lote: u.lote || null,
          serie: u.serie || null,
          partida: u.partida || null,
          estado: u.estado || null,
        })),
        familia: p.familia || null,
        cliente: p.cliente || p.codCliente || null,
        actualizadoEn: serverTimestamp(),
      }, { merge: true });

      lote.set(doc(db, 'codigos', p.sku), {
        sku: p.sku, tipo: 'SKU', vigente: true, actualizadoEn: serverTimestamp(),
      }, { merge: true });
    }
    await lote.commit();
    if (alAvanzar) alAvanzar(Math.min(i + TANDA, productos.length), productos.length);
  }
}

/** Resuelve un código contra el catálogo local. Una lectura, sin red al WMS. */
export async function buscarEnCatalogo(codigo) {
  const c = normalizarCodigo(codigo);
  if (!c) return null;

  const idx = await getDoc(doc(db, 'codigos', c));
  const sku = idx.exists() ? idx.get('sku') : c;

  const prod = await getDoc(doc(db, 'productos', sku));
  if (!prod.exists()) return null;
  return { sku, ...prod.data(), codigoVigente: idx.exists() ? idx.get('vigente') !== false : true };
}

/** Equivalencia código escaneado → SKU, cuando el WMS no la conoce. */
export async function registrarEquivalencia(codigo, sku, usuario) {
  const c = normalizarCodigo(codigo);
  if (!c || !sku) return;
  await setDoc(doc(db, 'codigos', c), {
    sku: normalizarCodigo(sku),
    tipo: 'EAN',
    vigente: true,
    registradoPorUid: usuario.uid,
    registradoPorEmail: usuario.email,
    actualizadoEn: serverTimestamp(),
  }, { merge: true });
}
