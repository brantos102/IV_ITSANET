/**
 * Modelo de datos y lectura del packing list.
 *
 * El archivo se analiza EN EL NAVEGADOR y se escribe a Firestore. Sin Cloud
 * Functions no hay dónde hacerlo del lado servidor, y además así el operario
 * ve el resultado al instante en vez de esperar a un disparador.
 */
import {
  collection, doc, getDoc, getDocs, setDoc, updateDoc, deleteDoc, query, where,
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

/**
 * Clave de mapa para algo que NO es un pallet: el nombre de un packing list.
 *
 * `clavePallet` no sirve aquí porque normaliza como un pallet y borra los
 * guiones: «PL-A» quedaba como «PLA», y entonces lo imputado a una lista no se
 * podía volver a encontrar por su nombre. Lo único que hay que proteger es el
 * punto, que Firestore trata como separador de ruta.
 */
export const claveMapa = (v) => limpiar(v).toUpperCase().replace(/\./g, '~');

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

/**
 * Columnas que RELLENA la validación.
 *
 * El packing list que llega ya las trae vacías: `Cantidad Física`,
 * `Validación`, `DESFACE`, `PALLET`, `OBSERVACION`… El informe final tiene que
 * devolver el archivo con esas mismas columnas, en la misma posición y con el
 * mismo encabezado, solo que llenas. Por eso aquí no se descartan: se marcan,
 * para saber dónde escribir cada cosa al exportar.
 */
export const ROL_COLUMNA = {
  'CANTIDAD FISICA': 'fisica', 'CANTIDADFISICA': 'fisica',
  'CANT FISICA': 'fisica', 'CANTIDAD VALIDADA': 'fisica',
  'VALIDACION': 'validacion', 'ESTADO': 'validacion',
  'DESFACE': 'desface', 'DESFASE': 'desface', 'DIFERENCIA': 'desface',
  'PALLET': 'pallet', 'PALETA': 'pallet',
  'CODIGO BARRA': 'codigoBarra', 'CODIGOBARRA': 'codigoBarra',
  'OBSERVACION': 'observacion', 'OBSERVACIONES': 'observacion',
};

const COLUMNAS_RESULTADO = new Set(Object.keys(ROL_COLUMNA));

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

      // Los encabezados TAL CUAL. El informe final devuelve el archivo con
      // estas mismas columnas, en este mismo orden: quien lo recibe lo abre
      // esperando el suyo, no uno parecido.
      const encabezados = filas[i].map((c) => (c === null || c === undefined ? '' : String(c)));
      const anchoReal = encabezados.length;

      // Dónde está cada columna que la validación rellena.
      const columnas = {};
      encabezados.forEach((c, idx) => {
        const rol = ROL_COLUMNA[clave(c)] || ROL_COLUMNA[clave(c).replace(/\s/g, '')];
        if (rol && columnas[rol] === undefined) columnas[rol] = idx;
      });

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
          // La fila completa, para poder devolverla igual. Se normaliza a texto
          // y al ancho de la cabecera: Firestore no admite arrays irregulares
          // con huecos, y al exportar tiene que cuadrar columna por columna.
          cruda: [...Array(anchoReal)].map((_, k) => {
            const v = cruda[k];
            return v === null || v === undefined ? '' : String(v);
          }),
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
        encabezados,
        columnas,
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
/**
 * Guarda las líneas y el agregado por SKU.
 *
 * Una recepción puede consolidar VARIOS packing lists. Pasa cuando llegan dos
 * embarques cortos el mismo día, o cuando uno se parte. Validarlos por separado
 * obliga a recorrer el almacén dos veces para la misma mercadería.
 *
 * Cada línea guarda de qué lista viene (`origen`), y el informe final se genera
 * por lista: cada una entrega exactamente las filas que trajo. El agregado por
 * SKU sí es común —se cuenta una vez— y por eso se SUMA en vez de sobrescribir.
 *
 * Firestore admite 500 operaciones por lote, así que se parte en tandas. Las
 * líneas son inmutables: son la versión del sistema contra la que se compara.
 */
export async function guardarPackingList(recepcionId, resultado, alAvanzar, opciones = {}) {
  const refRec = doc(db, 'recepciones', recepcionId);
  const origen = limpiar(opciones.origen).toUpperCase().slice(0, 40) || 'PRINCIPAL';
  const previo = (await getDoc(refRec)).data() || {};
  const yaHabia = previo.totales || { lineas: 0, skus: 0, unidades: 0 };
  const origenes = previo.origenes || [];

  if (origenes.includes(origen)) {
    throw new Error(
      `Ya se cargó un packing list con el nombre «${origen}» en esta recepción. ` +
      'Usa otro nombre para distinguirlos en el informe.',
    );
  }

  // El número de línea lleva el origen delante: así dos listas con una línea 1
  // no se pisan, y el orden dentro de cada una se conserva.
  const operaciones = resultado.lineas.map((l) => ({
    ref: doc(db, 'recepciones', recepcionId, 'lineas', `${origen}-${l.linea}`),
    datos: { ...l, origen, orden: yaHabia.lineas + l.linea, creadoEn: serverTimestamp() },
  }));

  // Lo esperado se acumula: el mismo SKU en dos listas se cuenta una sola vez,
  // contra la suma de las dos.
  const existentes = {};
  if (origenes.length) {
    const snap = await getDocs(collection(db, 'recepciones', recepcionId, 'skus'));
    snap.docs.forEach((d) => { existentes[d.id] = d.data(); });
  }

  Object.entries(resultado.porSku).forEach(([sku, esperado]) => {
    const primera = resultado.lineas.find((l) => l.sku === sku);
    const antes = existentes[sku];
    const total = aNumero(antes?.esperado, 0) + esperado;
    operaciones.push({
      ref: doc(db, 'recepciones', recepcionId, 'skus', sku),
      datos: {
        sku,
        descripcion: antes?.descripcion || primera?.descripcion || '',
        esperado: total,
        contado: aNumero(antes?.contado, 0),
        pallets: antes?.pallets || {},
        verificado: antes?.verificado === true,
        estado: estadoDe(total, aNumero(antes?.contado, 0), antes?.verificado === true),
        enPackingList: true,
        tienePnc: antes?.tienePnc === true,
        // En qué listas aparece: es lo que avisa de un SKU compartido.
        origenes: [...new Set([...(antes?.origenes || []), origen])],
        // Y cuánto declara cada una, para que el operario elija sabiendo.
        esperadoPorOrigen: {
          ...(antes?.esperadoPorOrigen || {}),
          [claveMapa(origen)]: esperado,
        },
        creadoEn: antes?.creadoEn || serverTimestamp(),
      },
    });
  });

  const TANDA = 450;
  for (let i = 0; i < operaciones.length; i += TANDA) {
    const lote = writeBatch(db);
    operaciones.slice(i, i + TANDA).forEach((o) => lote.set(o.ref, o.datos, { merge: true }));
    await lote.commit();
    if (alAvanzar) alAvanzar(Math.min(i + TANDA, operaciones.length), operaciones.length);
  }

  const skusTotales = new Set([
    ...Object.keys(existentes),
    ...Object.keys(resultado.porSku),
  ]).size;

  await updateDoc(refRec, {
    totales: {
      lineas: yaHabia.lineas + resultado.lineas.length,
      skus: skusTotales,
      unidades: aNumero(yaHabia.unidades, 0) + resultado.unidades,
    },
    origenes: [...origenes, origen],
    // La cabecera original de cada lista, para devolver el archivo igual.
    formatos: {
      ...(previo.formatos || {}),
      [claveMapa(origen)]: {
        encabezados: resultado.encabezados || [],
        columnas: resultado.columnas || {},
        hoja: resultado.hoja || '',
      },
    },
    hoja: resultado.hoja,
    embarques: [...new Set([...(previo.embarques || []), ...resultado.embarques])],
    packingListEn: serverTimestamp(),
  });

  // SKU que ya venían de otra lista: la atribución de lo contado entre listas
  // es una convención, no un hecho, y quien carga tiene que saberlo.
  const compartidos = Object.keys(resultado.porSku).filter((sku) => existentes[sku]);
  return { origen, lineas: resultado.lineas.length, compartidos };
}

/**
 * Borra una recepción entera, con todo lo que cuelga de ella.
 *
 * Existe porque subir el archivo equivocado pasa, y una recepción vacía o de
 * demostración en el listado no es inofensiva: el operario no sabe cuál es la
 * buena, y acaba contando contra la que no era.
 *
 * Firestore no borra en cascada: hay que recorrer cada subcolección. Se hace en
 * lotes de 400 porque el límite es 500 operaciones.
 *
 * Es irreversible y se lleva por delante la bitácora y la auditoría. Por eso lo
 * puede hacer solo un administrador, y la pantalla exige escribir el código.
 */
export async function borrarRecepcion(recepcionId, alAvanzar) {
  const subcolecciones = ['eventos', 'lineas', 'skus', 'adicionales', 'auditoria'];
  let borrados = 0;

  for (const nombre of subcolecciones) {
    const snap = await getDocs(collection(db, 'recepciones', recepcionId, nombre));
    for (let i = 0; i < snap.docs.length; i += 400) {
      const lote = writeBatch(db);
      snap.docs.slice(i, i + 400).forEach((d) => lote.delete(d.ref));
      await lote.commit();
      borrados += Math.min(400, snap.docs.length - i);
      if (alAvanzar) alAvanzar(borrados, nombre);
    }
  }

  await deleteDoc(doc(db, 'recepciones', recepcionId));
  return borrados;
}

export async function listarRecepciones(max = 50) {
  const q = query(collection(db, 'recepciones'), orderBy('creadoEn', 'desc'), limit(max));
  const snap = await getDocs(q);
  return snap.docs.map((d) => ({ id: d.id, ...d.data() }));
}

/**
 * Las recepciones en las que ha trabajado este operario.
 *
 * Sale de la lista que la recepción guarda, no de recorrer la bitácora: eso
 * costaría una lectura por conteo de la jornada.
 *
 * Se ordena aquí y no en la consulta para no obligar a crear un índice
 * compuesto en Firestore: son pocas decenas de recepciones y el orden en el
 * navegador es gratis.
 */
export async function listarMisRecepciones(uid, max = 60) {
  if (!uid) return [];
  const snap = await getDocs(query(
    collection(db, 'recepciones'),
    where('operarios', 'array-contains', uid),
    limit(max),
  ));
  return snap.docs
    .map((d) => ({ id: d.id, ...d.data() }))
    .sort((a, b) => (b.creadoEn?.toMillis?.() || 0) - (a.creadoEn?.toMillis?.() || 0));
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

/**
 * Reabre una recepción cerrada.
 *
 * Cerrar por error, o descubrir al día siguiente que faltó contar un pallet,
 * pasa. La alternativa —crear una recepción nueva con el mismo packing list—
 * parte el historial en dos y deja dos informes del mismo embarque.
 *
 * No borra nada: los conteos siguen donde estaban y el cierre anterior queda
 * en la auditoría. Lo que cambia es que vuelve a admitir conteos.
 */
export async function reabrirRecepcion(recepcionId) {
  await updateDoc(doc(db, 'recepciones', recepcionId), {
    estado: 'EN_VALIDACION',
    reabiertoEn: serverTimestamp(),
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

/**
 * Las ubicaciones de un producto, venga como venga del catálogo.
 *
 * El catálogo guardaba UNA sola posición por SKU hasta hace poco. Un catálogo
 * descargado antes de ese cambio no trae el array `posiciones`, solo `posicion`
 * y `stock`: leyendo únicamente el array, la ficha decía «sin existencia en
 * bodega» mientras la línea de arriba mostraba la posición. Dos afirmaciones
 * contrarias en la misma pantalla, y el operario sin saber a cuál hacer caso.
 */
export function ubicacionesDepot(producto) {
  const nuevas = (producto?.posiciones || []).filter((u) => u && u.posicion);
  if (nuevas.length) return nuevas;
  return producto?.posicion
    ? [{ posicion: producto.posicion, stock: aNumero(producto.stock, 0) }]
    : [];
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
