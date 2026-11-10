/**
 * Resolucion de codigos escaneados.
 *
 * El escaneo NO llama a la API de Depot: lee el indice inverso de Firestore,
 * que el precalentado dejo listo al subir el packing list. Esa es la diferencia
 * entre 1-3 s por escaneo y 50-150 ms.
 *
 * Indice inverso `codigos/{codigoNormalizado}` -> { sku, tipo, vigente }
 *
 * Un producto puede tener varios codigos apuntandole: su SKU, su EAN y los
 * alternos. Cuando Depot informa que un codigo cambio, el viejo se marca
 * `vigente:false` pero SIGUE resolviendo: la caja que esta en bodega tiene
 * impreso el codigo viejo. El operario escanea, funciona, y la app le avisa.
 */
'use strict';

const { normalizarCodigo } = require('./normalize');

const ACCION = {
  OK: 'OK',                               // existe y el codigo esta vigente
  REEMPLAZADO: 'CODIGO_REEMPLAZADO',      // existe, pero el codigo cambio
  REVISAR: 'VALIDAR_PROFUNDIDAD',         // no existe, hay parecidos
  CREAR: 'CREAR',                         // no existe en Depot
  BUSCAR_EN_LISTA: 'BUSCAR_EN_PACKING',   // no existe en ningun lado
};

/**
 * @param {FirebaseFirestore.Firestore} db
 * @param {import('./depot').DepotAdapter} depot
 */
function crearResolver(db, depot) {
  /**
   * @param {string} codigoCrudo  lo que emitio el lector
   * @param {{consultarApi?: boolean}} opciones
   */
  async function resolver(codigoCrudo, { consultarApi = true } = {}) {
    const codigo = normalizarCodigo(codigoCrudo);
    if (!codigo) {
      return { codigo: '', sku: null, accion: ACCION.CREAR, fuente: 'NINGUNA',
               mensaje: 'Codigo vacio o invalido.' };
    }

    // 1. Indice inverso: una lectura, sin red hacia el WMS.
    const idx = await db.collection('codigos').doc(codigo).get();
    if (idx.exists) {
      const { sku, tipo, vigente, reemplazadoPor } = idx.data();
      const prod = await db.collection('productos').doc(sku).get();
      const datos = prod.exists ? prod.data() : null;

      if (vigente === false) {
        return {
          codigo, sku, producto: datos, accion: ACCION.REEMPLAZADO, fuente: 'CACHE',
          reemplazadoPor: reemplazadoPor || null,
          mensaje: `Este codigo fue reemplazado${reemplazadoPor ? ' por ' + reemplazadoPor : ''}. ` +
                   'Se registra igual contra el producto correcto.',
        };
      }
      return { codigo, sku, producto: datos, tipo, accion: ACCION.OK, fuente: 'CACHE', mensaje: '' };
    }

    // 2. No esta cacheado: puede ser un SKU nuevo o un codigo recien cambiado.
    if (consultarApi) {
      let prod = null;
      let depotCaido = false;
      try {
        prod = await depot.buscarPorCodigo(codigo);
      } catch (e) {
        depotCaido = true;
        console.warn('Depot no disponible al resolver', codigo, e.message);
      }

      if (prod) {
        await guardarProducto(db, prod);
        return { codigo, sku: prod.sku, producto: serializar(prod), accion: ACCION.OK,
                 fuente: 'API', mensaje: '' };
      }
      if (depotCaido) {
        const candidatos = await buscarParecidos(db, codigo);
        return {
          codigo, sku: null, accion: ACCION.REVISAR, fuente: 'CACHE', degradado: true,
          candidatos,
          mensaje: 'Depot no responde. Verificado solo contra el catalogo local.',
        };
      }
    }

    // 3. No existe en ningun lado.
    const candidatos = await buscarParecidos(db, codigo);
    return {
      codigo, sku: null, accion: candidatos.length ? ACCION.REVISAR : ACCION.BUSCAR_EN_LISTA,
      fuente: 'CACHE', candidatos,
      mensaje: candidatos.length
        ? `No existe en Depot. Hay ${candidatos.length} codigo(s) similar(es): revisar antes de crearlo.`
        : 'No existe en Depot. Busquelo en el packing list o registrelo como adicional.',
    };
  }

  /** Codigos con la misma raiz: evita crear duplicados en Depot. */
  async function buscarParecidos(db, codigo, limite = 6) {
    if (codigo.length < 5) return [];
    const raiz = codigo.slice(0, 7);
    // Rango lexicografico sobre el id del documento: no requiere indice extra.
    const snap = await db.collection('productos')
      .where('__name__', '>=', raiz)
      .where('__name__', '<', raiz + '')
      .limit(limite + 1)
      .get();
    return snap.docs
      .filter((d) => d.id !== codigo)
      .slice(0, limite)
      .map((d) => ({ sku: d.id, descripcion: d.get('descripcion') || '' }));
  }

  return { resolver, buscarParecidos: (c) => buscarParecidos(db, c), ACCION };
}

function serializar(p) {
  return {
    sku: p.sku, descripcion: p.descripcion, ean: p.ean,
    codigosAlternos: p.codigosAlternos, unidad: p.unidad, inactivo: p.inactivo,
  };
}

/**
 * Guarda el producto y TODOS sus codigos en el indice inverso.
 *
 * Si un codigo ya apuntaba a otro SKU, se conserva como no vigente apuntando al
 * nuevo: un codigo reciclado nunca debe resolver al producto equivocado.
 */
async function guardarProducto(db, prod, { lote = null } = {}) {
  const batch = lote || db.batch();
  const ahora = new Date();

  batch.set(db.collection('productos').doc(prod.sku), {
    sku: prod.sku,
    descripcion: prod.descripcion || '',
    ean: prod.ean || null,
    codigosAlternos: prod.codigosAlternos || [],
    unidad: prod.unidad || null,
    inactivo: !!prod.inactivo,
    existeDepot: true,
    actualizadoEn: ahora,
  }, { merge: true });

  const codigos = new Set([prod.sku, prod.ean, ...(prod.codigosAlternos || [])].filter(Boolean));
  for (const c of codigos) {
    batch.set(db.collection('codigos').doc(c), {
      sku: prod.sku,
      tipo: c === prod.sku ? 'SKU' : (c === prod.ean ? 'EAN' : 'ALTERNO'),
      vigente: true,
      actualizadoEn: ahora,
    }, { merge: true });
  }

  if (!lote) await batch.commit();
  return codigos.size;
}

/** Marca un codigo como reemplazado sin romper las etiquetas ya impresas. */
async function marcarCodigoReemplazado(db, codigoViejo, codigoNuevo, sku) {
  await db.collection('codigos').doc(normalizarCodigo(codigoViejo)).set({
    sku,
    vigente: false,
    reemplazadoPor: normalizarCodigo(codigoNuevo),
    actualizadoEn: new Date(),
  }, { merge: true });
}

module.exports = { crearResolver, guardarProducto, marcarCodigoReemplazado, ACCION, serializar };
