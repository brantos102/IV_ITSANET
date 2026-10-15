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
 *
 * NOTA SOBRE EL MAPA DE PALLETS
 * -----------------------------
 * Se escribe anidado —`{ pallets: { A1: increment(5) } }`— y no con una clave
 * con punto. `set()` con `merge` usa las claves TAL CUAL: `'pallets.A1'` crea un
 * campo que se llama literalmente «pallets.A1» en la raíz del documento, no una
 * entrada dentro del mapa `pallets`. Solo `update()` interpreta el punto como
 * separador de ruta.
 *
 * El síntoma era mudo: el conteo se guardaba bien, el total subía, y la columna
 * de pallets salía vacía — con ella, la sugerencia de dónde está ya ese SKU,
 * que es la mitad del trabajo de buscar algo en un almacén.
 */
import {
  doc, collection, runTransaction, increment, serverTimestamp, setDoc,
  query, orderBy, limit, getDocs, arrayUnion,
} from '../vendor/firebase-sdk.js?v=20261015-25';
import { db } from './auth.js?v=20261015-25';
import * as local from './local.js?v=20261015-25';
import {
  normalizarCodigo, normalizarPallet, normalizarPosicion, palletValido,
  limpiar, aNumero, clavePallet, claveMapa, decodificarPallets, estadoDe,
} from './datos.js?v=20261015-25';

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

  // El cero solo vale declarándolo: «lo busqué y no está» es un dato, un cero
  // por descuido no lo es.
  const cantidad = aNumero(p.cantidad, 0);
  if (!Number.isFinite(cantidad) || cantidad < 0) {
    throw new ErrorConteo('No se admiten cantidades negativas. Si no apareció, declara 0.', 'CANTIDAD_INVALIDA');
  }
  if (cantidad === 0 && p.tipo !== 'CERO') {
    throw new ErrorConteo('La cantidad no puede ser 0.', 'CANTIDAD_INVALIDA');
  }
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

  // Lo mismo con un faltante: sin motivo no se puede reclamar a nadie.
  if (p.tipo === 'CERO' && !limpiar(p.observacion)) {
    throw new ErrorConteo(
      'Declarar que no apareció requiere una nota: dónde se buscó, o qué se vio.',
      'OBSERVACION_REQUERIDA',
    );
  }

  return {
    sku, cantidad, pallet, estadoFisico, fotos,
    observacion: limpiar(p.observacion).slice(0, 500) || null,
    codigoEscaneado: normalizarCodigo(p.codigoEscaneado) || sku,
    // Dónde quedó de verdad en el almacén. Es información del almacén, no del
    // packing list, así que no se valida contra nada: se registra tal cual y
    // viaja al informe en su propia columna.
    posicionReal: normalizarPosicion(p.posicionReal) || null,
    // De qué packing list sale esta cantidad. Cuando una recepción consolida
    // varias listas y el SKU está en más de una, lo elige el operario: así deja
    // de ser una suposición del informe y pasa a ser un dato.
    origen: limpiar(p.origen).toUpperCase().slice(0, 40) || null,
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
  if (local.modoLocal()) return local.registrarConteo(recepcionId, usuario, p);
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
    // Verificado = alguien ya lo buscó. Un cero declarado también lo marca.
    const verificado = actual.verificado === true || d.cantidad !== 0 || p.tipo === 'CERO';

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
      origen: d.origen,
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
      pallets: { [clavePallet(d.pallet)]: increment(d.cantidad) },
      // Cuánto se ha imputado a cada lista. El informe reparte con esto, no
      // adivinando.
      ...(d.origen ? { porOrigen: { [claveMapa(d.origen)]: increment(d.cantidad) } } : {}),
      estado: estadoDe(esperado, total, verificado),
      verificado,
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

    // --- 4. Estado de la recepción y quién ha trabajado en ella --- //
    //
    // La lista de operarios se guarda en la recepción, no se deduce de los
    // eventos: «qué he validado yo» es una consulta que el operario hace al
    // entrar, y recorrer la bitácora de todas las recepciones para responderla
    // costaría una lectura por conteo de la jornada.
    const cambios = {};
    if (estadoRec === 'ABIERTA') {
      cambios.estado = 'EN_VALIDACION';
      cambios.iniciadoEn = serverTimestamp();
    }
    if (!(snapRec.get('operarios') || []).includes(usuario.uid)) {
      cambios.operarios = arrayUnion(usuario.uid);
    }
    if (Object.keys(cambios).length) tx.update(refRec, cambios);

    return {
      duplicado: false, eventoId: idem, sku: d.sku,
      cantidadRegistrada: d.cantidad, pallet: d.pallet,
      esperado, contado: total,
      pendiente: Math.max(esperado - total, 0),
      estado: estadoDe(esperado, total, verificado),
      esAdicional: !actual.enPackingList && esperado === 0,
    };
  });
}

/** Reversa un conteo con un evento compensatorio. El original nunca se borra. */
export async function anularConteo(recepcionId, usuario, eventoId, motivo) {
  if (local.modoLocal()) return local.anularConteo(recepcionId, usuario, eventoId, motivo);
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
      origen: orig.origen || null,
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

    // Anular no «des-verifica»: alguien ya buscó ese producto, y eso no se
    // deshace. Vuelve a PENDIENTE solo si se anula el único registro que había.
    const verificado = snapSku.get('verificado') === true && total !== 0;

    tx.set(refSku, {
      contado: increment(-orig.cantidad),
      pallets: { [clavePallet(orig.pallet)]: increment(-orig.cantidad) },
      ...(orig.origen
        ? { porOrigen: { [claveMapa(orig.origen)]: increment(-orig.cantidad) } }
        : {}),
      estado: estadoDe(esperado, total, verificado),
      verificado,
      actualizadoEn: serverTimestamp(),
    }, { merge: true });

    return { sku: orig.sku, contado: total, esperado };
  });
}

/**
 * Declara que un SKU se buscó y no apareció.
 *
 * Es un conteo de cero con su firma y su motivo, no una marca aparte: así
 * queda en el mismo libro que todo lo demás y se puede anular igual. La
 * diferencia con no haber hecho nada es la que separa «me queda trabajo» de
 * «esto hay que reclamarlo».
 */
export async function declararNoEncontrado(recepcionId, usuario, p) {
  if (local.modoLocal()) return local.declararNoEncontrado(recepcionId, usuario, p);
  return registrarConteo(recepcionId, usuario, {
    ...p,
    cantidad: 0,
    tipo: 'CERO',
    pallet: p.pallet || 'NA',
    confirmarSobrante: true,
  });
}

/**
 * Deja constancia de un cierre o de una exportación.
 *
 * Quién cerró, cuándo, con qué cifras y qué archivo salió. Sin esto, «el
 * informe decía otra cosa» no se puede resolver: el agregado se puede volver a
 * calcular, pero lo que se entregó aquel día no.
 */
export async function registrarAuditoria(recepcionId, usuario, tipo, detalle = {}) {
  if (local.modoLocal()) return local.registrarAuditoria(recepcionId, usuario, tipo, detalle);
  const ref = doc(collection(db, 'recepciones', recepcionId, 'auditoria'));
  await setDoc(ref, {
    tipo,                                   // CIERRE | EXPORTACION | CORREO
    detalle,
    usuarioUid: usuario.uid,
    usuarioEmail: usuario.email,
    usuarioNombre: usuario.displayName || null,
    creadoEn: serverTimestamp(),
  });
  return ref.id;
}

/** Historial de cierres y exportaciones, el más reciente primero. */
export async function leerAuditoria(recepcionId, max = 40) {
  if (local.modoLocal()) return local.leerAuditoria(recepcionId, max);
  const q = query(
    collection(db, 'recepciones', recepcionId, 'auditoria'),
    orderBy('creadoEn', 'desc'),
    limit(max),
  );
  const snap = await getDocs(q);
  return snap.docs.map((d) => ({ id: d.id, ...d.data() }));
}

/** Historial de conteos, el más reciente primero. */
export async function leerBitacora(recepcionId, max = 60) {
  if (local.modoLocal()) return local.leerBitacora(recepcionId, max);
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

/**
 * Lo ya registrado de un SKU, con su lista, su pallet y quién lo puso.
 *
 * Al volver a escanear el mismo producto en otro pallet, lo primero que hay que
 * saber es qué se hizo antes con él: de qué packing list salió lo que ya está
 * contado, dónde quedó y cuándo. Sin eso, el segundo registro se hace a ciegas.
 */
export function registrosDe(eventos, sku) {
  const anulados = new Set(eventos.filter((e) => e.refEvento).map((e) => e.refEvento));
  return eventos
    .filter((e) => e.sku === sku && e.tipo !== 'ANULACION' && !anulados.has(e.id))
    .map((e) => ({
      id: e.id,
      cantidad: aNumero(e.cantidad, 0),
      pallet: e.pallet || '',
      posicionReal: e.posicionReal || '',
      origen: e.origen || null,
      operador: e.operadorNombre || e.operadorEmail || '',
      cuando: e.creadoEn?.toDate ? e.creadoEn.toDate() : null,
    }))
    .sort((a, b) => (b.cuando?.getTime() || 0) - (a.cuando?.getTime() || 0));
}

/** Lo contado por cada packing list, con la clave ya decodificada. */
export const porOrigenDe = (skuDoc) => decodificarPallets(skuDoc?.porOrigen);

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
  let ok = 0, faltante = 0, sobrante = 0, pendiente = 0, noEncontrado = 0;
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

    // Haber contado algo ya implica haberlo buscado. El campo explícito existe
    // para el otro caso: se buscó, no apareció, y se declaró el cero.
    const verificado = s.verificado === true || f !== 0;

    const estado = f === e ? 'Ok' : (f < e ? 'Faltante' : 'Sobrante');
    if (estado === 'Ok') ok++;
    else if (estado === 'Faltante') {
      faltante++;
      // Sin buscar todavía frente a buscado y no encontrado: lo primero es
      // trabajo que queda, lo segundo es un faltante que ya se puede reclamar.
      if (!verificado) pendiente++;
      else if (f === 0) noEncontrado++;
    } else sobrante++;

    if (e !== f) {
      discrepancias.push({ sku: s.sku, esperado: e, fisico: f, diferencia: f - e, estado });
    }
  }

  const total = skus.length;
  return {
    skus: total, ok, faltante, sobrante, sinContar: pendiente, noEncontrado,
    // Lo que de verdad bloquea el cierre: ningún SKU puede quedarse sin dato.
    sinVerificar: pendiente,
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
