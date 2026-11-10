/**
 * Registro de conteos físicos.
 *
 * Dos escrituras en una sola transacción de Firestore:
 *   1. `eventos/{id}`  — libro mayor append-only, nunca se modifica ni se borra.
 *   2. `skus/{sku}`    — agregado en vivo, con `increment()` atómico.
 *
 * El agregado existe para que el operario lea UN documento en vez de sumar N
 * eventos, y para que `onSnapshot` propague el cambio a los demás dispositivos
 * al instante. El libro mayor existe para la trazabilidad y los KPIs.
 *
 * `increment()` es atómico del lado del servidor: dos operarios contando el
 * mismo SKU a la vez suman correctamente sin bloquearse, y dos operarios en SKU
 * distintos no compiten por nada. Es la diferencia con `LockService`, que ponía
 * a todos en la misma fila.
 */
'use strict';

const { normalizarCodigo, normalizarPallet, palletValido, palletPadre, limpiar, aNumero,
        clavePallet, decodificarPallets } = require('./normalize');

const ESTADO = {
  PENDIENTE: 'PENDIENTE',
  OK: 'OK',
  FALTANTE: 'FALTANTE',
  SOBRANTE: 'SOBRANTE',
};

const TIPO = { CONTEO: 'CONTEO', AJUSTE: 'AJUSTE', ANULACION: 'ANULACION' };

class ErrorConteo extends Error {
  constructor(mensaje, codigo = 'ERROR') {
    super(mensaje);
    this.codigo = codigo;
  }
}

function estadoDe(esperado, contado) {
  if (contado === 0) return esperado > 0 ? ESTADO.PENDIENTE : ESTADO.OK;
  if (contado === esperado) return ESTADO.OK;
  return contado < esperado ? ESTADO.FALTANTE : ESTADO.SOBRANTE;
}

/**
 * Valida la entrada del operario antes de tocar la base.
 * Devuelve el payload ya normalizado.
 */
function validarEntrada(p) {
  const sku = normalizarCodigo(p.sku);
  if (!sku) throw new ErrorConteo('Código de producto vacío o inválido.', 'CODIGO_INVALIDO');

  const cantidad = aNumero(p.cantidad, 0);
  if (cantidad === 0) throw new ErrorConteo('La cantidad no puede ser 0.', 'CANTIDAD_INVALIDA');
  if (!Number.isFinite(cantidad)) throw new ErrorConteo('Cantidad inválida.', 'CANTIDAD_INVALIDA');
  if (Math.abs(cantidad) > 100000) {
    throw new ErrorConteo('Cantidad fuera de rango. ¿Se escaneó dentro del campo?', 'CANTIDAD_INVALIDA');
  }
  if (cantidad < 0 && p.tipo !== TIPO.AJUSTE) {
    throw new ErrorConteo('Las cantidades negativas requieren un ajuste de supervisor.', 'AJUSTE_REQUERIDO');
  }

  const pallet = normalizarPallet(p.pallet);
  if (!palletValido(pallet)) {
    throw new ErrorConteo(
      'Pallet inválido. Use formato alfanumérico (A1, B04) o subpallet (A1.1, B04.3).',
      'PALLET_INVALIDO',
    );
  }

  const estadoFisico = String(p.estadoFisico || 'BUENO').toUpperCase();
  if (estadoFisico !== 'BUENO' && estadoFisico !== 'PNC') {
    throw new ErrorConteo('Estado físico debe ser BUENO o PNC.', 'ESTADO_INVALIDO');
  }

  const fotos = Array.isArray(p.fotos) ? p.fotos.filter(Boolean).slice(0, 10) : [];
  // Un producto no conforme sin evidencia no sirve para reclamar al proveedor.
  if (estadoFisico === 'PNC' && fotos.length === 0) {
    throw new ErrorConteo('Un producto no conforme requiere al menos una foto.', 'FOTO_REQUERIDA');
  }
  if (estadoFisico === 'PNC' && !limpiar(p.observacion)) {
    throw new ErrorConteo('Un producto no conforme requiere observación.', 'OBSERVACION_REQUERIDA');
  }

  return {
    sku,
    cantidad,
    pallet,
    estadoFisico,
    fotos,
    observacion: limpiar(p.observacion).slice(0, 500),
    ean: normalizarCodigo(p.ean) || null,
    tipo: p.tipo || TIPO.CONTEO,
    codigoEscaneado: normalizarCodigo(p.codigoEscaneado) || sku,
  };
}

/**
 * Registra un conteo.
 *
 * @param {FirebaseFirestore.Firestore} db
 * @param {object} ctx  { recepcionId, uid, email, nombre, dispositivo }
 * @param {object} p    payload del cliente
 */
async function registrarConteo(db, ctx, p, { FieldValue, Timestamp }) {
  const datos = validarEntrada(p);
  const recRef = db.collection('recepciones').doc(ctx.recepcionId);
  const skuRef = recRef.collection('skus').doc(datos.sku);

  // Idempotencia: el id del evento ES la clave. Un reintento escribe el mismo
  // documento, no uno nuevo, así que el doble disparo del lector no suma dos veces.
  const idem = limpiar(p.idempotencyKey).slice(0, 80);
  if (!idem) throw new ErrorConteo('Falta la clave de idempotencia.', 'IDEM_REQUERIDA');
  const evtRef = recRef.collection('eventos').doc(idem);

  return db.runTransaction(async (tx) => {
    const [recSnap, skuSnap, evtSnap] = await Promise.all([
      tx.get(recRef), tx.get(skuRef), tx.get(evtRef),
    ]);

    if (evtSnap.exists) {
      const skuData = skuSnap.exists ? skuSnap.data() : { esperado: 0, contado: 0 };
      return { duplicado: true, ...resumenSku(datos.sku, skuData) };
    }

    if (!recSnap.exists) throw new ErrorConteo('La recepción no existe.', 'NO_ENCONTRADA');
    const rec = recSnap.data();
    if (!['ABIERTA', 'EN_VALIDACION'].includes(rec.estado)) {
      throw new ErrorConteo(
        `La recepción está ${rec.estado}: no admite más conteos.`, 'RECEPCION_CERRADA',
      );
    }

    const actual = skuSnap.exists
      ? skuSnap.data()
      : { sku: datos.sku, esperado: 0, contado: 0, pallets: {}, enPackingList: false };

    const esperado = aNumero(actual.esperado, 0);
    const contadoPrevio = aNumero(actual.contado, 0);
    const nuevoTotal = contadoPrevio + datos.cantidad;

    if (nuevoTotal < 0) {
      throw new ErrorConteo(
        `El ajuste dejaría el conteo en ${nuevoTotal}. Contado actual: ${contadoPrevio}.`,
        'AJUSTE_INVALIDO',
      );
    }

    // Sobrante: exige confirmación explícita del operario.
    if (datos.cantidad > 0 && nuevoTotal > esperado && !p.confirmarSobrante) {
      throw new ErrorConteo(
        `SOBRANTE: el packing list declara ${esperado} y ya hay ${contadoPrevio}. ` +
        `Esta cantidad genera ${nuevoTotal - esperado} de exceso. Confirme para registrarlo.`,
        'CONFIRMAR_SOBRANTE',
      );
    }

    // --- 1. Evento en el libro mayor ---
    tx.set(evtRef, {
      sku: datos.sku,
      codigoEscaneado: datos.codigoEscaneado,
      ean: datos.ean,
      cantidad: datos.cantidad,
      pallet: datos.pallet,
      palletPadre: palletPadre(datos.pallet),
      estadoFisico: datos.estadoFisico,
      tipo: datos.tipo,
      observacion: datos.observacion || null,
      fotos: datos.fotos,
      operadorUid: ctx.uid,
      operadorEmail: ctx.email,
      operadorNombre: ctx.nombre || null,
      dispositivo: limpiar(ctx.dispositivo).slice(0, 80) || null,
      creadoEn: FieldValue.serverTimestamp(),
      refEvento: p.refEvento || null,
    });

    // --- 2. Agregado en vivo ---
    const estado = estadoDe(esperado, nuevoTotal);
    tx.set(skuRef, {
      sku: datos.sku,
      esperado,
      contado: FieldValue.increment(datos.cantidad),
      [`pallets.${clavePallet(datos.pallet)}`]: FieldValue.increment(datos.cantidad),
      estado,
      tienePnc: datos.estadoFisico === 'PNC' ? true : (actual.tienePnc || false),
      ultimoOperador: ctx.nombre || ctx.email,
      actualizadoEn: FieldValue.serverTimestamp(),
    }, { merge: true });

    // --- 3. La recepción pasa a EN_VALIDACION con el primer conteo ---
    if (rec.estado === 'ABIERTA') {
      tx.update(recRef, { estado: 'EN_VALIDACION', iniciadoEn: FieldValue.serverTimestamp() });
    }

    return {
      duplicado: false,
      eventoId: idem,
      ...resumenSku(datos.sku, { esperado, contado: nuevoTotal, estado }),
      pallet: datos.pallet,
      cantidadRegistrada: datos.cantidad,
    };
  });
}

function resumenSku(sku, d) {
  const esperado = aNumero(d.esperado, 0);
  const contado = aNumero(d.contado, 0);
  return {
    sku,
    esperado,
    contado,
    pendiente: Math.max(esperado - contado, 0),
    estado: d.estado || estadoDe(esperado, contado),
  };
}

/**
 * Anula un conteo con un evento compensatorio. El original nunca se borra.
 */
async function anularConteo(db, ctx, { eventoId, motivo }, { FieldValue }) {
  if (!limpiar(motivo)) throw new ErrorConteo('Debe indicar el motivo de la anulación.', 'MOTIVO_REQUERIDO');

  const recRef = db.collection('recepciones').doc(ctx.recepcionId);
  const origRef = recRef.collection('eventos').doc(eventoId);
  const revRef = recRef.collection('eventos').doc(`anula-${eventoId}`);

  return db.runTransaction(async (tx) => {
    const [recSnap, origSnap, revSnap] = await Promise.all([
      tx.get(recRef), tx.get(origRef), tx.get(revRef),
    ]);

    if (!origSnap.exists) throw new ErrorConteo('Evento no encontrado.', 'NO_ENCONTRADO');
    if (revSnap.exists) throw new ErrorConteo('Ese conteo ya fue anulado.', 'YA_ANULADO');
    const orig = origSnap.data();
    if (orig.tipo === TIPO.ANULACION) throw new ErrorConteo('Ese evento ya es una anulación.', 'YA_ANULADO');
    if (!['ABIERTA', 'EN_VALIDACION'].includes(recSnap.data().estado)) {
      throw new ErrorConteo('La recepción está cerrada.', 'RECEPCION_CERRADA');
    }

    const skuRef = recRef.collection('skus').doc(orig.sku);
    const skuSnap = await tx.get(skuRef);
    const esperado = skuSnap.exists ? aNumero(skuSnap.get('esperado'), 0) : 0;
    const nuevoTotal = (skuSnap.exists ? aNumero(skuSnap.get('contado'), 0) : 0) - orig.cantidad;

    tx.set(revRef, {
      sku: orig.sku,
      cantidad: -orig.cantidad,
      pallet: orig.pallet,
      estadoFisico: orig.estadoFisico,
      tipo: TIPO.ANULACION,
      observacion: `ANULA ${eventoId}: ${limpiar(motivo)}`.slice(0, 500),
      fotos: [],
      operadorUid: ctx.uid,
      operadorEmail: ctx.email,
      operadorNombre: ctx.nombre || null,
      refEvento: eventoId,
      creadoEn: FieldValue.serverTimestamp(),
    });

    tx.set(skuRef, {
      contado: FieldValue.increment(-orig.cantidad),
      [`pallets.${clavePallet(orig.pallet)}`]: FieldValue.increment(-orig.cantidad),
      estado: estadoDe(esperado, nuevoTotal),
      actualizadoEn: FieldValue.serverTimestamp(),
    }, { merge: true });

    return { sku: orig.sku, contado: nuevoTotal, esperado };
  });
}

/**
 * Registra un SKU que no está en el packing list.
 *
 * Regla del cliente: NUNCA se agrega una fila a la data validada. Si el archivo
 * trae 22 filas, se entregan 22 filas. Los adicionales viven en su propia
 * colección y se exportan en una pestaña aparte.
 */
async function registrarAdicional(db, ctx, p, { FieldValue }) {
  const datos = validarEntrada({ ...p, sku: p.sku });
  if (!limpiar(p.motivo)) {
    throw new ErrorConteo('Indique por qué este código no está en el packing list.', 'MOTIVO_REQUERIDO');
  }

  const recRef = db.collection('recepciones').doc(ctx.recepcionId);
  const adicRef = recRef.collection('adicionales').doc(datos.sku);
  const skuRef = recRef.collection('skus').doc(datos.sku);

  await db.runTransaction(async (tx) => {
    const lineaSnap = await tx.get(skuRef);
    if (lineaSnap.exists && lineaSnap.get('enPackingList') === true) {
      throw new ErrorConteo(
        'Este SKU sí está en el packing list: regístrelo como conteo normal.', 'YA_EN_LISTA',
      );
    }
    tx.set(adicRef, {
      sku: datos.sku,
      descripcion: limpiar(p.descripcion).slice(0, 300) || null,
      ean: datos.ean,
      motivo: limpiar(p.motivo).slice(0, 300),
      detectadoPorUid: ctx.uid,
      detectadoPorEmail: ctx.email,
      enDepot: !!p.enDepot,
      creadoEn: FieldValue.serverTimestamp(),
    }, { merge: true });
  });

  // El conteo en sí va por el camino normal: queda en el libro mayor igual que
  // cualquier otro, con `enPackingList:false` en su agregado.
  return registrarConteo(db, ctx, { ...p, confirmarSobrante: true }, { FieldValue });
}

module.exports = {
  registrarConteo, anularConteo, registrarAdicional,
  validarEntrada, estadoDe, ErrorConteo, ESTADO, TIPO,
  decodificarPallets,
};
