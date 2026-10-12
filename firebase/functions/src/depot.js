/**
 * Adaptador de la API de Depot / WMS.
 *
 * Toda la app habla con la interfaz `DepotAdapter`, nunca con la API directa.
 * Cuando lleguen los endpoints reales basta implementar `HttpDepotAdapter`
 * ajustando `RUTAS` y `mapearProducto`; nada más del sistema cambia.
 *
 * Las credenciales viven en Secret Manager y solo se leen aquí, del lado
 * servidor. Nunca viajan al dispositivo del operario.
 */
'use strict';

const { normalizarCodigo, limpiar } = require('./normalize');

/**
 * Rutas de la API. PENDIENTE: confirmar contra la documentación del WMS.
 * Se sobrescriben por variable de entorno sin tocar código.
 */
const RUTAS = {
  producto: process.env.DEPOT_RUTA_PRODUCTO || '/productos/{codigo}',
  porEan: process.env.DEPOT_RUTA_EAN || '/productos/barcode/{codigo}',
  lote: process.env.DEPOT_RUTA_LOTE || '/productos/batch',
  crear: process.env.DEPOT_RUTA_CREAR || '/productos',
};

const TIMEOUT_MS = Number(process.env.DEPOT_TIMEOUT_MS || 8000);
const LOTE_MAX = Number(process.env.DEPOT_LOTE_MAX || 100);

/** Resultado normalizado, independiente de cómo responda el WMS. */
class Producto {
  constructor({ sku, descripcion, ean, codigosAlternos, unidad, inactivo, crudo }) {
    this.sku = normalizarCodigo(sku);
    this.descripcion = limpiar(descripcion);
    this.ean = ean ? normalizarCodigo(ean) : null;
    this.codigosAlternos = (codigosAlternos || []).map(normalizarCodigo).filter(Boolean);
    this.unidad = limpiar(unidad) || null;
    this.inactivo = !!inactivo;
    this.crudo = crudo || null;   // respuesta original, para diagnóstico
  }
}

class DepotError extends Error {
  constructor(mensaje, { codigo = 'DEPOT_ERROR', reintentable = false } = {}) {
    super(mensaje);
    this.codigo = codigo;
    this.reintentable = reintentable;
  }
}

/** Interfaz. Toda implementación debe cumplir estos cuatro métodos. */
class DepotAdapter {
  /** @returns {Promise<Producto|null>} null si el código no existe. */
  async buscarPorCodigo(_codigo) { throw new Error('no implementado'); }
  /** @returns {Promise<Map<string, Producto|null>>} codigo -> producto */
  async buscarLote(_codigos) { throw new Error('no implementado'); }
  async crearProducto(_datos) { throw new Error('no implementado'); }
  async disponible() { return true; }
}

// ------------------------------------------------------------------------ //
// Implementación HTTP
// ------------------------------------------------------------------------ //

/**
 * Corta la espera sin dejar la petición colgada.
 * En bodega, una API lenta no puede congelar el escáner.
 */
async function fetchConTimeout(url, opciones, ms) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), ms);
  try {
    return await fetch(url, { ...opciones, signal: ctrl.signal });
  } finally {
    clearTimeout(t);
  }
}

/** Evita castigar cada escaneo cuando el WMS está caído. */
class CircuitBreaker {
  constructor(umbral = 4, enfriamientoMs = 30000) {
    this.umbral = umbral;
    this.enfriamientoMs = enfriamientoMs;
    this.fallos = 0;
    this.abiertoHasta = 0;
  }
  get abierto() { return Date.now() < this.abiertoHasta; }
  exito() { this.fallos = 0; this.abiertoHasta = 0; }
  fallo() {
    this.fallos += 1;
    if (this.fallos >= this.umbral) this.abiertoHasta = Date.now() + this.enfriamientoMs;
  }
}

class HttpDepotAdapter extends DepotAdapter {
  /**
   * @param {object} cfg
   * @param {string} cfg.baseUrl
   * @param {string} [cfg.token]        Bearer, si la API usa token fijo
   * @param {string} [cfg.usuario]      Basic, si usa usuario y contraseña
   * @param {string} [cfg.clave]
   * @param {string} [cfg.cliente]      Identificador del cliente en el WMS
   */
  constructor(cfg) {
    super();
    if (!cfg || !cfg.baseUrl) throw new DepotError('Falta la URL base de Depot', { codigo: 'SIN_CONFIG' });
    this.baseUrl = String(cfg.baseUrl).replace(/\/+$/, '');
    this.cfg = cfg;
    this.breaker = new CircuitBreaker();
  }

  cabeceras() {
    const h = { Accept: 'application/json', 'Content-Type': 'application/json' };
    if (this.cfg.token) {
      h.Authorization = `Bearer ${this.cfg.token}`;
    } else if (this.cfg.usuario) {
      const b64 = Buffer.from(`${this.cfg.usuario}:${this.cfg.clave || ''}`).toString('base64');
      h.Authorization = `Basic ${b64}`;
    }
    return h;
  }

  url(plantilla, codigo) {
    const ruta = plantilla.replace('{codigo}', encodeURIComponent(codigo));
    const sep = ruta.includes('?') ? '&' : '?';
    return this.cfg.cliente
      ? `${this.baseUrl}${ruta}${sep}cliente=${encodeURIComponent(this.cfg.cliente)}`
      : `${this.baseUrl}${ruta}`;
  }

  async disponible() { return !this.breaker.abierto; }

  async buscarPorCodigo(codigo) {
    const c = normalizarCodigo(codigo);
    if (!c) return null;
    if (this.breaker.abierto) {
      throw new DepotError('Depot no responde (circuito abierto)', {
        codigo: 'NO_DISPONIBLE', reintentable: true,
      });
    }

    // Primero como SKU; si no está, como código de barras.
    for (const plantilla of [RUTAS.producto, RUTAS.porEan]) {
      const res = await this.pedir(this.url(plantilla, c));
      if (res) return res;
    }
    return null;
  }

  async pedir(url) {
    let r;
    try {
      r = await fetchConTimeout(url, { method: 'GET', headers: this.cabeceras() }, TIMEOUT_MS);
    } catch (e) {
      this.breaker.fallo();
      throw new DepotError(`Depot inalcanzable: ${e.message}`, {
        codigo: 'NO_DISPONIBLE', reintentable: true,
      });
    }

    if (r.status === 404) { this.breaker.exito(); return null; }
    if (r.status === 401 || r.status === 403) {
      // Credencial mala: reintentar no lo arregla y no debe abrir el circuito.
      throw new DepotError('Depot rechazó las credenciales', { codigo: 'NO_AUTORIZADO' });
    }
    if (!r.ok) {
      this.breaker.fallo();
      throw new DepotError(`Depot respondió ${r.status}`, {
        codigo: 'DEPOT_ERROR', reintentable: r.status >= 500,
      });
    }

    this.breaker.exito();
    const cuerpo = await r.json();
    return mapearProducto(cuerpo);
  }

  /**
   * Consulta en lote. Si el WMS no la ofrece, cae a llamadas individuales
   * con concurrencia limitada: el precalentado sigue funcionando, más lento.
   */
  async buscarLote(codigos) {
    const unicos = [...new Set(codigos.map(normalizarCodigo).filter(Boolean))];
    const salida = new Map();

    if (RUTAS.lote && process.env.DEPOT_SOPORTA_LOTE === '1') {
      for (let i = 0; i < unicos.length; i += LOTE_MAX) {
        const tanda = unicos.slice(i, i + LOTE_MAX);
        const r = await fetchConTimeout(
          `${this.baseUrl}${RUTAS.lote}`,
          { method: 'POST', headers: this.cabeceras(), body: JSON.stringify({ codigos: tanda }) },
          TIMEOUT_MS * 3,
        );
        if (!r.ok) throw new DepotError(`Depot respondió ${r.status} en consulta por lote`);
        const cuerpo = await r.json();
        const lista = Array.isArray(cuerpo) ? cuerpo : (cuerpo.productos || cuerpo.data || []);
        for (const item of lista) {
          const p = mapearProducto(item);
          if (p) salida.set(p.sku, p);
        }
        for (const c of tanda) if (!salida.has(c)) salida.set(c, null);
      }
      return salida;
    }

    await enParalelo(unicos, 8, async (c) => {
      try {
        salida.set(c, await this.buscarPorCodigo(c));
      } catch (e) {
        if (e.codigo === 'NO_AUTORIZADO') throw e;
        salida.set(c, undefined);   // undefined = no se pudo verificar
      }
    });
    return salida;
  }

  async crearProducto(datos) {
    const r = await fetchConTimeout(
      `${this.baseUrl}${RUTAS.crear}`,
      { method: 'POST', headers: this.cabeceras(), body: JSON.stringify(datos) },
      TIMEOUT_MS * 2,
    );
    if (!r.ok) throw new DepotError(`Depot respondió ${r.status} al crear el producto`);
    return mapearProducto(await r.json());
  }
}

/**
 * Traduce la respuesta del WMS a `Producto`.
 *
 * Acepta varios nombres de campo porque todavía no tenemos el contrato real.
 * Cuando llegue, esto se reduce al mapeo exacto.
 */
function mapearProducto(cuerpo) {
  if (!cuerpo || typeof cuerpo !== 'object') return null;
  const d = cuerpo.producto || cuerpo.data || cuerpo;
  const sku = d.producto_id || d.sku || d.codigo || d.codigo_producto || d.itemCode;
  if (!sku) return null;

  const alternos = []
    .concat(d.codigos_alternos || d.codigosAlternos || d.alternateCodes || [])
    .concat(d.CODIGO_ALTERNATIVO ? [d.CODIGO_ALTERNATIVO] : []);

  const ean = d.codigo_barra || d.codigoBarra || d.ean || d.barcode;

  return new Producto({
    sku,
    descripcion: d.descripcion || d.description || d.nombre || '',
    ean: ean && String(ean).toUpperCase() !== 'DEFAULT' && String(ean) !== '0' ? ean : null,
    codigosAlternos: alternos,
    unidad: d.unidad_id || d.unidad || d.uom,
    inactivo: d.inactivo === 1 || d.inactivo === true || d.activo === false,
    crudo: d,
  });
}

/** Ejecuta `fn` sobre `items` con como mucho `limite` en vuelo a la vez. */
async function enParalelo(items, limite, fn) {
  const cola = [...items];
  const obreros = Array.from({ length: Math.min(limite, cola.length) }, async () => {
    while (cola.length) {
      const item = cola.shift();
      await fn(item);
    }
  });
  await Promise.all(obreros);
}

// ------------------------------------------------------------------------ //
// Implementación simulada: permite construir y probar sin la API real
// ------------------------------------------------------------------------ //
class MockDepotAdapter extends DepotAdapter {
  /** @param {Array<object>} productos semilla */
  constructor(productos = []) {
    super();
    this.porCodigo = new Map();
    this.llamadas = { buscarPorCodigo: 0, buscarLote: 0, crearProducto: 0 };
    for (const p of (productos || [])) this.registrar(p);
  }

  registrar(datos) {
    const p = datos instanceof Producto ? datos : new Producto(datos);
    this.porCodigo.set(p.sku, p);
    if (p.ean) this.porCodigo.set(p.ean, p);
    for (const c of p.codigosAlternos) this.porCodigo.set(c, p);
    return p;
  }

  async buscarPorCodigo(codigo) {
    this.llamadas.buscarPorCodigo += 1;
    return this.porCodigo.get(normalizarCodigo(codigo)) || null;
  }

  async buscarLote(codigos) {
    this.llamadas.buscarLote += 1;
    const m = new Map();
    for (const c of codigos) {
      const n = normalizarCodigo(c);
      if (n) m.set(n, this.porCodigo.get(n) || null);
    }
    return m;
  }

  async crearProducto(datos) {
    this.llamadas.crearProducto += 1;
    return this.registrar(datos);
  }
}

/**
 * Construye el adaptador según la configuración disponible.
 *
 * Sin `baseUrl` devuelve el mock, para poder construir y probar todo el sistema
 * antes de tener la API real. El `|| []` importa: un `null` no dispara el valor
 * por defecto del parámetro, solo un `undefined`.
 */
function crearAdaptador(cfg) {
  if (!cfg || !cfg.baseUrl) return new MockDepotAdapter((cfg && cfg.semilla) || []);
  return new HttpDepotAdapter(cfg);
}

module.exports = {
  DepotAdapter, HttpDepotAdapter, MockDepotAdapter,
  Producto, DepotError, crearAdaptador, mapearProducto, enParalelo, RUTAS,
};
