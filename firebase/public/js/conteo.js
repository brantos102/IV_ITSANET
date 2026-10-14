/**
 * Registro de conteos físicos.
 *
 * Dos escrituras en una sola transacción:
 *   1. `eventos/{idempotencyKey}` — libro mayor append-only, nunca se modifica.
 *   2. `skus/{sku}`               — agregado en vivo, con increment() atómico.
 *
 * El agregado existe para que el operario lea UN documento en vez de sumar N
 * eventos, y para que onSnapshot propague el cambio al resto de dispositivos
 * al instante. El libro mayor existe para la trazabilidad y los KPI.
 *
 * `increment()` es atómico del lado del servidor: dos operarios contando el
 * mismo SKU a la vez suman bien, y dos en SKU distintos no compiten por nada.
 *
 * El id del evento ES la clave de idempotencia: un reintento escribe el mismo
 * documento, no uno nuevo, así que el doble disparo del lector no suma dos veces.
 */
import {
  doc, collection, runTransaction, increment, serverTimestamp,
  query, orderBy, limit, getDocs, where,
} from 'https://www.gstatic.com/firebasejs/10.14.1/firebase-firestore.js';
import { db } from './auth.js';
import {
  normalizarCodigo, normalizarPallet, normalizarPosicion, palletValido,
  limpiar, aNumero, clavePallet, decodificarPallets, estadoDe,
} from './datos.js';

export class ErrorConteo extends Error {
  constructor(mensaje, codigo = 'ERROR') {
    super(mensaje);
    this.codigo = codigo;
  }
}

export function nuevaClave() {
  return (crypto.randomUUID ? crypto.randomUUID()
    : 'k-' + Date.now() + '-' + Math.random().toString(36).slice(2)).slice(0, 60);
}

function validar(p) {
  const sku = normalizarCodigo(p.sku);
  if (!sku) throw new ErrorConteo('Código de producto vacío.', 'CODIGO_INVALIDO');

  const cantidad = aNumero(p.cantidad, 0);
  if (cantidad === 0) throw new ErrorConteo('La cantidad no puede ser 0.', 'CANTIDAD_INVALIDA');
  if (Math.abs(cantidad) > 100000) {
    throw new ErrorConteo(
      'Cantidad fuera de rango. ¿Se escaneó dentro del campo de cantidad?',
      'CANTIDAD_INVALIDA',
    );
  }

  const pallet = normalizarPallet(p.pallet);
  if (!palletValido(pallet)) {
    throw new ErrorConteo(
      'Pallet inválido. Use A1, B04 o un subpallet como B04.1',
      'PALLET_INVALIDO',
    );
  }

  const estadoFisico = String(p.estadoFisico || 'BUENO').toUpperCase();
  const fotos = Array.isArray(p.fotos) ? p.fotos.filter(Boolean).slice(0, 10) : [];

  // Un producto no conforme sin evidencia no sirve para reclamar al proveedor.
  if (estadoFisico === 'PNC' && !limpiar(p.observacion)) {
    throw new ErrorConteo('Un producto no conforme requiere observación.', 'OBSERVACION_REQUERIDA');
  }

  return {
    sku, cantidad, pallet, estadoFisico, fotos,
    observacion: limpiar(p.observacion).slice(0, 500) || null,
    codigoEscaneado: normalizarCodigo(p.codigoEscaneado) || sku,
    // Dónde quedó de verdad en el almacén. Es información del almacén, no del
    // packing list, así que no se valida contra nada: se registra tal cual y
    // viaja al informe en su propia columna.
    posicionReal: normalizarPosicion(p.posicionReal) || null,
  };
}

/**
 * Registra un conteo.
 *
 * @param {string} recepcionId
 * @param {object} usuario  { uid, email, displayName }
 * @param {object} p        { sku, cantidad, pallet, estadoFisico, observacion,
 *                            fotos, idempotencyKey, confirmarSobrante, enPackingList }
 */
export async function registrarConteo(recepcionId, usuario, p) {
  const d = validar(p);
  const idem = p.idempotencyKey || nuevaClave();

  const refRec = doc(db, 'recepciones', recepcionId);
  const refSku = doc(db, 'recepciones', recepcionId, 'skus', d.sku);
  const refEvt = doc(db, 'recepciones', recepcionId, 'eventos', idem);

  return runTransaction(db, async (tx) => {
    const [snapRec, snapSku, snapEvt] = await Promise.all([
      tx.get(refRec), tx.get(refSku), tx.get(refEvt),
    ]);

    if (snapEvt.exists()) {
      const s = snapSku.exists() ? snapSku.data() : { esperado: 0, contado: 0 };
      return {
        duplicado: true, sku: d.sku,
        esperado: s.esperado || 0, contado: s.contado || 0,
        pendiente: Math.max((s.esperado || 0) - (s.contado || 0), 0),
        estado: s.estado || estadoDe(s.esperado || 0, s.contado || 0),
      };
    }

    if (!snapRec.exists()) throw new ErrorConteo('La recepción no existe.', 'NO_ENCONTRADA');
    const estadoRec = snapRec.get('estado');
    if (!['ABIERTA', 'EN_VALIDACION'].includes(estadoRec)) {
      throw new ErrorConteo(
        `La recepción está ${estadoRec}: no admite más conteos.`,
        'RECEPCION_CERRADA',
      );
    }

    const actual = snapSku.exists()
      ? snapSku.data()
      : { esperado: 0, contado: 0, enPackingList: false };

    const esperado = aNumero(actual.esperado, 0);
    const previo = aNumero(actual.contado, 0);
    const total = previo + d.cantidad;

    if (total < 0) {
      throw new ErrorConteo(
        `El ajuste dejaría el conteo en ${total}. Contado actual: ${previo}.`,
        'AJUSTE_INVALIDO',
      );
    }

    // Sobrante: exige confirmación explícita del operario.
    if (d.cantidad > 0 && total > esperado && !p.confirmarSobrante) {
      throw new ErrorConteo(
        esperado === 0
          ? `${d.sku} no está en el packing list. Si llegó físicamente, confírmelo como adicional.`
          : `SOBRANTE: el packing list declara ${esperado} y ya hay ${previo}. ` +
            `Esto genera ${total - esperado} de exceso. Confirme para registrarlo.`,
        'CONFIRMAR_SOBRANTE',
      );
    }

    // --- 1. Evento en el libro mayor --- //
    tx.set(refEvt, {
      sku: d.sku,
      codigoEscaneado: d.codigoEscaneado,
      cantidad: d.cantidad,
      pallet: d.pallet,
      posicionReal: d.posicionReal,
      estadoFisico: d.estadoFisico,
      tipo: p.tipo || 'CONTEO',
      observacion: d.observacion,
      fotos: d.fotos,
      operadorUid: usuario.uid,
      operadorEmail: usuario.email,
      operadorNombre: usuario.displayName || null,
      creadoEn: serverTimestamp(),
    });

    // --- 2. Agregado en vivo --- //
    tx.set(refSku, {
      sku: d.sku,
      esperado,
      contado: increment(d.cantidad),
      [`pallets.${clavePallet(d.pallet)}`]: increment(d.cantidad),
      estado: estadoDe(esperado, total),
      enPackingList: actual.enPackingList === true,
      tienePnc: d.estadoFisico === 'PNC' ? true : (actual.tienePnc || false),
      descripcion: actual.descripcion || p.descripcion || '',
      ultimoOperador: usuario.displayName || usuario.email,
      actualizadoEn: serverTimestamp(),
    }, { merge: true });

    // --- 3. Adicional: SKU fuera del packing list --- //
    // Regla del cliente: si el archivo trae 22 filas, se entregan 22 filas.
    // Los adicionales viven aparte y se exportan en su propia pestaña.
    if (!actual.enPackingList && esperado === 0) {
      tx.set(doc(db, 'recepciones', recepcionId, 'adicionales', d.sku), {
        sku: d.sku,
        descripcion: p.descripcion || '',
        motivo: p.motivo || 'Llegó físicamente sin estar en el packing list',
        detectadoPorUid: usuario.uid,
        detectadoPorEmail: usuario.email,
        creadoEn: serverTimestamp(),
      }, { merge: true });
    }

    // --- 4. La recepción pasa a EN_VALIDACION con el primer conteo --- //
    if (estadoRec === 'ABIERTA') {
      tx.update(refRec, { estado: 'EN_VALIDACION', iniciadoEn: serverTimestamp() });
    }

    return {
      duplicado: false, eventoId: idem, sku: d.sku,
      cantidadRegistrada: d.cantidad, pallet: d.pallet,
      esperado, contado: total,
      pendiente: Math.max(esperado - total, 0),
      estado: estadoDe(esperado, total),
      esAdicional: !actual.enPackingList && esperado === 0,
    };
  });
}

/** Reversa un conteo con un evento compensatorio. El original nunca se borra. */
export async function anularConteo(recepcionId, usuario, eventoId, motivo) {
  if (!limpiar(motivo)) {
    throw new ErrorConteo('Debe indicar el motivo de la anulación.', 'MOTIVO_REQUERIDO');
  }

  const refRec = doc(db, 'recepciones', recepcionId);
  const refOrig = doc(db, 'recepciones', recepcionId, 'eventos', eventoId);
  const refRev = doc(db, 'recepciones', recepcionId, 'eventos', `anula-${eventoId}`);

  return runTransaction(db, async (tx) => {
    const [snapRec, snapOrig, snapRev] = await Promise.all([
      tx.get(refRec), tx.get(refOrig), tx.get(refRev),
    ]);

    if (!snapOrig.exists()) throw new ErrorConteo('Evento no encontrado.', 'NO_ENCONTRADO');
    if (snapRev.exists()) throw new ErrorConteo('Ese conteo ya fue anulado.', 'YA_ANULADO');
    if (snapOrig.get('tipo') === 'ANULACION') {
      throw new ErrorConteo('Ese evento ya es una anulación.', 'YA_ANULADO');
    }
    if (!['ABIERTA', 'EN_VALIDACION'].includes(snapRec.get('estado'))) {
      throw new ErrorConteo('La recepción está cerrada.', 'RECEPCION_CERRADA');
    }

    const orig = snapOrig.data();
    const refSku = doc(db, 'recepciones', recepcionId, 'skus', orig.sku);
    const snapSku = await tx.get(refSku);
    const esperado = aNumero(snapSku.get('esperado'), 0);
    const total = aNumero(snapSku.get('contado'), 0) - orig.cantidad;

    tx.set(refRev, {
      sku: orig.sku,
      cantidad: -orig.cantidad,
      pallet: orig.pallet,
      estadoFisico: orig.estadoFisico,
      tipo: 'ANULACION',
      observacion: `ANULA ${eventoId}: ${limpiar(motivo)}`.slice(0, 500),
      fotos: [],
      operadorUid: usuario.uid,
      operadorEmail: usuario.email,
      operadorNombre: usuario.displayName || null,
      refEvento: eventoId,
      creadoEn: serverTimestamp(),
    });

    tx.set(refSku, {
      contado: increment(-orig.cantidad),
      [`pallets.${clavePallet(orig.pallet)}`]: increment(-orig.cantidad),
      estado: estadoDe(esperado, total),
      actualizadoEn: serverTimestamp(),
    }, { merge: true });

    return { sku: orig.sku, contado: total, esperado };
  });
}

/** Historial de conteos, el más reciente primero. */
export async function leerBitacora(recepcionId, max = 60) {
  const q = query(
    collection(db, 'recepciones', recepcionId, 'eventos'),
    orderBy('creadoEn', 'desc'),
    limit(max),
  );
  const snap = await getDocs(q);
  const eventos = snap.docs.map((d) => ({ id: d.id, ...d.data() }));
  const anulados = new Set(eventos.filter((e) => e.refEvento).map((e) => e.refEvento));
  return eventos.map((e) => ({ ...e, anulado: anulados.has(e.id) }));
}

/** Pallets donde ya está este SKU, de mayor a menor cantidad. */
export function ubicacionesDe(skuDoc) {
  if (!skuDoc || !skuDoc.pallets) return [];
  return Object.entries(decodificarPallets(skuDoc.pallets))
    .filter(([, v]) => v !== 0)
    .sort((a, b) => b[1] - a[1])
    .map(([pallet, cantidad]) => ({ pallet, cantidad }));
}

/** Totales de la recepción, para el cierre y el informe. */
export function resumir(skus) {
  let ok = 0, faltante = 0, sobrante = 0, pendiente = 0;
  let unidadesEsperadas = 0, unidadesFisicas = 0;
  // Unidades que ya están verificadas: lo contado de cada SKU SIN pasarse de lo
  // que declara el packing list.
  let unidadesCubiertas = 0;
  const discrepancias = [];

  for (const s of skus) {
    const e = aNumero(s.esperado, 0);
    const f = aNumero(s.contado, 0);
    unidadesEsperadas += e;
    unidadesFisicas += f;
    unidadesCubiertas += Math.min(f, e);

    // Al cerrar, lo no contado ya es faltante confirmado.
    const estado = f === e ? 'Ok' : (f < e ? 'Faltante' : 'Sobrante');
    if (estado === 'Ok') ok++;
    else if (estado === 'Faltante') { faltante++; if (f === 0) pendiente++; }
    else sobrante++;

    if (e !== f) {
      discrepancias.push({ sku: s.sku, esperado: e, fisico: f, diferencia: f - e, estado });
    }
  }

  const total = skus.length;
  return {
    skus: total, ok, faltante, sobrante, sinContar: pendiente,
    unidadesEsperadas, unidadesFisicas,
    diferencia: unidadesFisicas - unidadesEsperadas,
    exactitud: total ? Math.round((ok / total) * 1000) / 10 : 0,
    unidadesCubiertas,
    /**
     * Avance = unidades verificadas sobre unidades declaradas.
     *
     * El tope se aplica POR SKU, no al total. Comparando los totales, contar de
     * más en un producto tapaba lo que faltaba en otro: con 20 SKU faltantes y
     * un sobrante grande la barra marcaba 100%, y lo que queda por buscar es
     * justo lo que hay que ver.
     */
    avance: unidadesEsperadas
      ? Math.round((unidadesCubiertas / unidadesEsperadas) * 100)
      : 0,
    discrepancias,
    adicionales: skus.filter((s) => s.enPackingList === false).length,
  };
}
