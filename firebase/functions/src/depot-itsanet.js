/**
 * Adaptador para la API de Depot de Itsanet.
 *
 * Contrato real, según la documentación del WMS:
 *
 *   GET  {base}/gettoken/            → devuelve el token id
 *   GET  {base}/getstock/{codigo}    → stock de UN producto   (cabecera `token`)
 *   GET  {base}/getstock/            → el código es OPCIONAL: devuelve TODO
 *
 * Dos diferencias con lo que suele hacer una API y que importan aquí:
 *
 *   1. El token va en una cabecera llamada `token`, no en `Authorization:
 *      Bearer`. Mandarlo como Bearer da 401 sin explicar por qué.
 *   2. `getstock` sin código devuelve el catálogo entero. Eso convierte el
 *      precalentado en UNA llamada en vez de N, que es exactamente lo que hace
 *      el Centro de Control cuando pulsa "Extraer Stock desde API".
 */
'use strict';

const { DepotAdapter, DepotError, Producto, mapearProducto } = require('./depot');
const { normalizarCodigo, limpiar, aNumero } = require('./normalize');

const TIMEOUT_MS = 15000;
const TIMEOUT_BULK_MS = 120000;   // el catálogo completo tarda más

/**
 * Extrae el token de la respuesta de /gettoken/.
 *
 * La documentación no fija el formato, así que se aceptan los tres que usan
 * estas APIs: texto plano, JSON con el token en algún campo, o JSON que es
 * directamente la cadena.
 */
function extraerTokenItsanet(texto) {
  const t = limpiar(texto);
  if (!t) return null;

  if (t.startsWith('{') || t.startsWith('[')) {
    try {
      const j = JSON.parse(t);
      const d = Array.isArray(j) ? j[0] : (j.data || j.result || j);
      const v = d && (d.token || d.Token || d.token_id || d.tokenId ||
                      d.id || d.access_token || d.TOKEN);
      return v ? String(v) : null;
    } catch {
      return null;
    }
  }
  // Texto plano, a veces entre comillas.
  return t.replace(/^"+|"+$/g, '') || null;
}

/**
 * Traduce una fila de getstock a `Producto`.
 *
 * Los nombres de campo no están documentados, así que se aceptan las variantes
 * habituales. Cuando veamos una respuesta real esto se reduce al mapeo exacto.
 */
function mapearStock(fila) {
  if (!fila || typeof fila !== 'object') return null;

  const sku = fila.codigo_producto || fila.CodProducto || fila.cod_producto ||
              fila.codProducto || fila.producto_id || fila.codigo || fila.sku ||
              fila.Codigo || fila.CODIGO;
  if (!sku) return null;

  const ean = fila.codigo_barra || fila.codigoBarra || fila.CodigoBarra ||
              fila.ean || fila.EAN || fila.barcode;

  const alternos = []
    .concat(fila.codigo_alternativo || fila.codigoAlternativo || fila.CODIGO_ALTERNATIVO || [])
    .concat(fila.codigos_alternos || []);

  const prod = new Producto({
    sku,
    descripcion: fila.descripcion || fila.Descripcion || fila.DESCRIPCION ||
                 fila.nombre || fila.detalle || '',
    ean: ean && String(ean).toUpperCase() !== 'DEFAULT' && String(ean) !== '0' ? ean : null,
    codigosAlternos: Array.isArray(alternos) ? alternos : [alternos],
    unidad: fila.unidad || fila.unidad_id || fila.Unidad || fila.um,
    inactivo: fila.inactivo === 1 || fila.inactivo === true || fila.activo === false,
    crudo: fila,
  });

  // El stock no se usa para validar la recepción, pero sirve de referencia al
  // operario cuando un sobrante resulta ser un producto que ya existe.
  prod.stock = aNumero(
    fila.stock ?? fila.Stock ?? fila.cantidad ?? fila.existencia ?? fila.saldo, 0,
  );
  return prod;
}

/** Saca la lista de filas de la respuesta, venga como venga envuelta. */
function filasDe(cuerpo) {
  if (Array.isArray(cuerpo)) return cuerpo;
  if (!cuerpo || typeof cuerpo !== 'object') return [];
  for (const clave of ['data', 'result', 'stock', 'productos', 'items', 'Table', 'rows']) {
    if (Array.isArray(cuerpo[clave])) return cuerpo[clave];
  }
  // Un solo producto devuelto como objeto suelto.
  return [cuerpo];
}

class ItsanetDepotAdapter extends DepotAdapter {
  /**
   * @param {object} cfg
   * @param {string} cfg.baseUrl        p.ej. https://dominio.com/apidepot
   * @param {string} [cfg.rutaToken]    por defecto /gettoken/
   * @param {string} [cfg.rutaStock]    por defecto /getstock/
   * @param {string} [cfg.nombreCabeceraToken]  por defecto 'token'
   * @param {object} [cfg.credenciales] usuario y clave del cliente, si gettoken las pide
   * @param {object} [almacenToken]     caché compartida del token
   * @param {Function} [fetchFn]
   */
  constructor(cfg, almacenToken = null, fetchFn = null) {
    super();
    if (!cfg || !cfg.baseUrl) {
      throw new DepotError('Falta la URL base de Depot', { codigo: 'SIN_CONFIG' });
    }
    this.baseUrl = String(cfg.baseUrl).replace(/\/+$/, '');
    this.cfg = cfg;
    this.almacen = almacenToken;
    this.fetchFn = fetchFn || globalThis.fetch;
    this.tokenMemoria = null;      // { token, venceEn }
    this.metricas = { gettoken: 0, getstock: 0, aciertosCache: 0, reintentos401: 0 };
  }

  get rutaToken() { return this.cfg.rutaToken || '/gettoken/'; }
  get rutaStock() { return this.cfg.rutaStock || '/getstock/'; }
  get nombreCabecera() { return this.cfg.nombreCabeceraToken || 'token'; }
  get ttlMs() {
    const h = Number(this.cfg.ttlHoras);
    return (Number.isFinite(h) && h > 0 ? h : 12) * 3600 * 1000;
  }

  // -------------------------------------------------------------------- //
  // Token
  // -------------------------------------------------------------------- //
  vigente(reg) { return !!reg && !!reg.token && Number(reg.venceEn) > Date.now(); }

  async obtenerToken(forzar = false) {
    if (!forzar) {
      if (this.vigente(this.tokenMemoria)) {
        this.metricas.aciertosCache += 1;
        return this.tokenMemoria.token;
      }
      if (this.almacen) {
        const compartido = await this.almacen.leer();
        if (this.vigente(compartido)) {
          this.tokenMemoria = compartido;
          this.metricas.aciertosCache += 1;
          return compartido.token;
        }
      }
    }

    this.metricas.gettoken += 1;
    const url = this.baseUrl + this.rutaToken;

    // Algunas instalaciones piden las credenciales del cliente en gettoken.
    const cab = { Accept: 'application/json, text/plain, */*' };
    const cred = this.cfg.credenciales || {};
    if (cred.usuario) cab.usuario = cred.usuario;
    if (cred.clave) cab.clave = cred.clave;
    if (cred.cliente) cab.cliente = cred.cliente;

    let r;
    try {
      r = await this.conTimeout(url, { method: 'GET', headers: cab }, TIMEOUT_MS);
    } catch (e) {
      throw new DepotError(
        `No se pudo contactar a Depot para pedir el token: ${e.message}`,
        { codigo: 'NO_DISPONIBLE', reintentable: true },
      );
    }

    if (r.status === 401 || r.status === 403) {
      throw new DepotError('Depot rechazó las credenciales al pedir el token.',
                           { codigo: 'NO_AUTORIZADO' });
    }
    if (!r.ok) {
      throw new DepotError(`Depot respondió ${r.status} en ${this.rutaToken}`,
                           { codigo: 'LOGIN_FALLIDO' });
    }

    const token = extraerTokenItsanet(await r.text());
    if (!token) {
      throw new DepotError(
        `Depot respondió sin un token reconocible en ${this.rutaToken}. ` +
        'Revise el formato de la respuesta en el panel de administración.',
        { codigo: 'RESPUESTA_INESPERADA' },
      );
    }

    const reg = { token, venceEn: Date.now() + this.ttlMs, obtenidoEn: Date.now() };
    this.tokenMemoria = reg;
    if (this.almacen) {
      try { await this.almacen.guardar(reg); } catch (e) {
        console.warn('No se pudo compartir el token:', e.message);
      }
    }
    return token;
  }

  async invalidarToken() {
    this.tokenMemoria = null;
    if (this.almacen) {
      try { await this.almacen.borrar(); } catch { /* no crítico */ }
    }
  }

  async conTimeout(url, opciones, ms) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), ms);
    try {
      return await this.fetchFn(url, { ...opciones, signal: ctrl.signal });
    } finally {
      clearTimeout(t);
    }
  }

  async cabeceras() {
    return {
      Accept: 'application/json, text/plain, */*',
      [this.nombreCabecera]: await this.obtenerToken(),
    };
  }

  // -------------------------------------------------------------------- //
  // Consultas
  // -------------------------------------------------------------------- //

  /**
   * @param {string} url
   * @param {number} timeout
   * @param {boolean} yaReintento  el token puede caducar antes de su vencimiento
   */
  async pedir(url, timeout = TIMEOUT_MS, yaReintento = false) {
    let r;
    try {
      r = await this.conTimeout(url, { method: 'GET', headers: await this.cabeceras() }, timeout);
    } catch (e) {
      throw new DepotError(`Depot inalcanzable: ${e.message}`,
                           { codigo: 'NO_DISPONIBLE', reintentable: true });
    }

    if (r.status === 404) return null;
    if (r.status === 401 || r.status === 403) {
      if (!yaReintento) {
        await this.invalidarToken();
        await this.obtenerToken(true);
        this.metricas.reintentos401 += 1;
        return this.pedir(url, timeout, true);
      }
      throw new DepotError('Depot rechazó el token.', { codigo: 'NO_AUTORIZADO' });
    }
    if (!r.ok) {
      throw new DepotError(`Depot respondió ${r.status}`,
                           { codigo: 'DEPOT_ERROR', reintentable: r.status >= 500 });
    }

    const texto = await r.text();
    if (!limpiar(texto)) return null;
    try {
      return JSON.parse(texto);
    } catch {
      throw new DepotError('Depot respondió algo que no es JSON.',
                           { codigo: 'RESPUESTA_INESPERADA' });
    }
  }

  async buscarPorCodigo(codigo) {
    const c = normalizarCodigo(codigo);
    if (!c) return null;
    this.metricas.getstock += 1;

    const cuerpo = await this.pedir(this.baseUrl + this.rutaStock + encodeURIComponent(c));
    if (!cuerpo) return null;

    const filas = filasDe(cuerpo);
    if (!filas.length) return null;

    // La API puede devolver varias filas del mismo producto (una por lote o
    // ubicación). Nos quedamos con la que coincide exactamente con lo escaneado.
    const exacta = filas.find((f) => {
      const p = mapearStock(f);
      return p && (p.sku === c || p.ean === c || p.codigosAlternos.includes(c));
    });
    return mapearStock(exacta || filas[0]);
  }

  /**
   * Trae el catálogo completo en UNA llamada.
   *
   * Es lo que hace el Centro de Control con "Extraer Stock desde API". Con esto
   * el precalentado de una recepción no depende de cuántos SKU tenga.
   */
  async descargarCatalogo() {
    this.metricas.getstock += 1;
    const cuerpo = await this.pedir(this.baseUrl + this.rutaStock, TIMEOUT_BULK_MS);
    const filas = filasDe(cuerpo || []);

    const productos = [];
    const vistos = new Set();
    for (const f of filas) {
      const p = mapearStock(f);
      if (!p || !p.sku || vistos.has(p.sku)) continue;
      vistos.add(p.sku);
      productos.push(p);
    }
    return productos;
  }

  /**
   * Resuelve varios códigos.
   *
   * Si son muchos, sale más barato bajar el catálogo entero una vez que hacer
   * una llamada por código. El umbral es configurable.
   */
  async buscarLote(codigos) {
    const unicos = [...new Set(codigos.map(normalizarCodigo).filter(Boolean))];
    const salida = new Map();
    const umbral = Number(this.cfg.umbralCatalogo) || 25;

    if (unicos.length >= umbral) {
      const catalogo = await this.descargarCatalogo();
      const indice = new Map();
      for (const p of catalogo) {
        indice.set(p.sku, p);
        if (p.ean) indice.set(p.ean, p);
        for (const a of p.codigosAlternos) indice.set(a, p);
      }
      for (const c of unicos) salida.set(c, indice.get(c) || null);
      return salida;
    }

    for (const c of unicos) {
      try {
        salida.set(c, await this.buscarPorCodigo(c));
      } catch (e) {
        if (e.codigo === 'NO_AUTORIZADO') throw e;
        salida.set(c, undefined);   // undefined = no se pudo verificar
      }
    }
    return salida;
  }

  async disponible() {
    try {
      await this.obtenerToken();
      return true;
    } catch {
      return false;
    }
  }

  /** Diagnóstico para el panel. Nunca devuelve el token. */
  async diagnostico(codigoPrueba) {
    const t0 = Date.now();
    const pasos = [];
    try {
      await this.obtenerToken(true);
      pasos.push({ paso: 'gettoken', ok: true, ms: Date.now() - t0 });
    } catch (e) {
      pasos.push({ paso: 'gettoken', ok: false, ms: Date.now() - t0,
                   codigo: e.codigo, mensaje: e.message });
      return { ok: false, pasos };
    }

    const t1 = Date.now();
    try {
      const p = await this.buscarPorCodigo(codigoPrueba || '');
      pasos.push({ paso: 'getstock', ok: true, ms: Date.now() - t1,
                   encontrado: !!p,
                   producto: p ? { sku: p.sku, descripcion: p.descripcion,
                                   ean: p.ean, stock: p.stock } : null });
      return { ok: true, pasos };
    } catch (e) {
      pasos.push({ paso: 'getstock', ok: false, ms: Date.now() - t1,
                   codigo: e.codigo, mensaje: e.message });
      return { ok: false, pasos };
    }
  }
}

module.exports = {
  ItsanetDepotAdapter, extraerTokenItsanet, mapearStock, filasDe,
};
