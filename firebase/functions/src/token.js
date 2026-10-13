/**
 * Obtención y reutilización del token de la API de Depot / WMS.
 *
 * Objetivo: pedir el token UNA vez y reutilizarlo todo el día. Un login por
 * escaneo sería absurdo — y muchas APIs de WMS limitan los intentos de login,
 * así que además de lento sería arriesgado.
 *
 * Caché en dos niveles, porque Cloud Functions escala a varias instancias y
 * cada una arranca con la memoria vacía:
 *
 *   L1  memoria del proceso   → 0 ms, pero se pierde en cada arranque en frío
 *   L2  Firestore             → ~30 ms, compartido por todas las instancias
 *   L3  login contra el WMS   → ~300-800 ms, solo cuando no queda alternativa
 *
 * Con 3 operarios escaneando, lo normal es que el token salga de L1 el 99 % de
 * las veces y se pida de nuevo una sola vez al día.
 */
'use strict';

const { limpiar } = require('./normalize');

/** Documento del token. Va en `_internal`, que NINGÚN cliente puede leer. */
const RUTA_TOKEN = '_internal/depot_token';

/** Margen antes del vencimiento real: nunca usar un token a punto de expirar. */
const MARGEN_MS = 5 * 60 * 1000;         // 5 minutos

/** Tope cuando el WMS no informa vencimiento. */
const TTL_POR_DEFECTO_MS = 12 * 60 * 60 * 1000;   // 12 horas

/** Espera máxima a que otra instancia termine de renovar. */
const ESPERA_RENOVACION_MS = 6000;

class TokenError extends Error {
  constructor(mensaje, codigo = 'TOKEN_ERROR') { super(mensaje); this.codigo = codigo; }
}

/**
 * Calcula cuándo vence el token.
 *
 * Prioridad: lo que diga el WMS → el fin del día local → el tope por defecto.
 * Siempre con margen, y nunca más allá del tope.
 */
function calcularVencimiento(respuesta, { ttlMaxMs = TTL_POR_DEFECTO_MS, ahora = Date.now() } = {}) {
  const segundos = Number(
    respuesta.expires_in ?? respuesta.expiresIn ?? respuesta.expira_en ?? respuesta.ttl,
  );
  if (Number.isFinite(segundos) && segundos > 0) {
    return ahora + Math.min(segundos * 1000, ttlMaxMs) - MARGEN_MS;
  }

  // Fecha absoluta, si la API la manda así.
  const fecha = respuesta.expires_at || respuesta.expiresAt || respuesta.expiration;
  if (fecha) {
    const t = new Date(fecha).getTime();
    if (Number.isFinite(t) && t > ahora) return Math.min(t, ahora + ttlMaxMs) - MARGEN_MS;
  }

  // Sin información: se asume válido hasta el tope configurado.
  return ahora + ttlMaxMs - MARGEN_MS;
}

/** Extrae el token de la respuesta, tolerando distintos nombres de campo. */
function extraerToken(cuerpo) {
  if (!cuerpo || typeof cuerpo !== 'object') return null;
  const d = cuerpo.data || cuerpo.result || cuerpo;
  const t = d.access_token || d.accessToken || d.token || d.jwt || d.id_token || d.Token;
  return t ? String(t) : null;
}

class TokenProvider {
  /**
   * @param {object} opciones
   * @param {FirebaseFirestore.Firestore} opciones.db
   * @param {object} opciones.cfg       configuración de Depot
   * @param {Function} [opciones.fetchFn] inyectable para pruebas
   * @param {Function} [opciones.ahora]   inyectable para pruebas
   */
  constructor({ db, cfg, fetchFn = globalThis.fetch, ahora = () => Date.now() }) {
    this.db = db;
    this.cfg = cfg || {};
    this.fetchFn = fetchFn;
    this.ahora = ahora;
    this.memoria = null;            // { token, venceEn }
    this.renovacionEnCurso = null;  // promesa compartida dentro de la instancia
    this.metricas = { l1: 0, l2: 0, login: 0, reintentos401: 0 };
  }

  get ttlMaxMs() {
    const h = Number(this.cfg.ttlHoras);
    return Number.isFinite(h) && h > 0 ? h * 3600 * 1000 : TTL_POR_DEFECTO_MS;
  }

  vigente(reg) {
    return !!reg && !!reg.token && Number(reg.venceEn) > this.ahora();
  }

  /**
   * Devuelve un token válido, pidiéndolo solo si hace falta.
   * @param {boolean} forzar  ignora la caché (tras un 401)
   */
  async obtener(forzar = false) {
    // Si el WMS usa un token fijo configurado a mano, no hay nada que pedir.
    if (this.cfg.token && !this.cfg.rutaLogin) return this.cfg.token;

    if (!forzar) {
      // --- L1: memoria del proceso ---
      if (this.vigente(this.memoria)) {
        this.metricas.l1 += 1;
        return this.memoria.token;
      }

      // --- L2: Firestore, compartido entre instancias ---
      const compartido = await this.leerCompartido();
      if (this.vigente(compartido)) {
        this.metricas.l2 += 1;
        this.memoria = compartido;
        return compartido.token;
      }
    }

    // Dentro de esta instancia, una sola renovación a la vez.
    if (this.renovacionEnCurso) return this.renovacionEnCurso;
    this.renovacionEnCurso = this.renovar(forzar)
      .finally(() => { this.renovacionEnCurso = null; });
    return this.renovacionEnCurso;
  }

  async leerCompartido() {
    try {
      const snap = await this.db.doc(RUTA_TOKEN).get();
      return snap.exists ? snap.data() : null;
    } catch (e) {
      console.warn('No se pudo leer el token compartido:', e.message);
      return null;
    }
  }

  /**
   * Renueva el token.
   *
   * Entre instancias se coordina con una transacción: la primera que llega se
   * marca como renovadora y hace el login; las demás esperan y releen. Sin esto,
   * un arranque en frío con varias instancias dispararía N logins contra el WMS.
   */
  async renovar(forzar) {
    const ahora = this.ahora();
    let meTocaRenovar = false;

    try {
      meTocaRenovar = await this.db.runTransaction(async (tx) => {
        const snap = await tx.get(this.db.doc(RUTA_TOKEN));
        const reg = snap.exists ? snap.data() : null;

        if (!forzar && this.vigente(reg)) return false;   // otro ya lo renovó

        // Si alguien está renovando y no lleva demasiado, se espera.
        if (reg && reg.renovandoDesde && (ahora - reg.renovandoDesde) < ESPERA_RENOVACION_MS) {
          return false;
        }
        tx.set(this.db.doc(RUTA_TOKEN), { renovandoDesde: ahora }, { merge: true });
        return true;
      });
    } catch (e) {
      // Si la coordinación falla, se renueva igual: es peor quedarse sin token.
      console.warn('No se pudo coordinar la renovación:', e.message);
      meTocaRenovar = true;
    }

    if (!meTocaRenovar) {
      const reg = await this.esperarRenovacionAjena();
      if (reg) return reg.token;
      // La otra instancia no terminó: se renueva igual.
    }

    const { token, venceEn } = await this.login();
    this.memoria = { token, venceEn };

    try {
      await this.db.doc(RUTA_TOKEN).set({
        token, venceEn, obtenidoEn: this.ahora(), renovandoDesde: null,
      });
    } catch (e) {
      // El token sirve igual en esta instancia aunque no se haya compartido.
      console.warn('No se pudo guardar el token compartido:', e.message);
    }
    return token;
  }

  async esperarRenovacionAjena() {
    const limite = this.ahora() + ESPERA_RENOVACION_MS;
    while (this.ahora() < limite) {
      await new Promise((r) => setTimeout(r, 250));
      const reg = await this.leerCompartido();
      if (this.vigente(reg)) {
        this.memoria = reg;
        this.metricas.l2 += 1;
        return reg;
      }
    }
    return null;
  }

  /** Login contra el WMS. Única llamada que gasta credenciales. */
  async login() {
    const ruta = this.cfg.rutaLogin || '/auth/login';
    const base = String(this.cfg.baseUrl || '').replace(/\/+$/, '');
    if (!base) throw new TokenError('Falta la URL base de Depot.', 'SIN_CONFIG');
    if (!this.cfg.usuario && !this.cfg.clave && !this.cfg.apiKey) {
      throw new TokenError('No hay credenciales para pedir el token.', 'SIN_CREDENCIAL');
    }

    this.metricas.login += 1;
    const url = base + ruta;

    // Nombres de campo configurables: cada WMS usa los suyos.
    const cuerpo = {};
    cuerpo[this.cfg.campoUsuario || 'usuario'] = this.cfg.usuario;
    cuerpo[this.cfg.campoClave || 'clave'] = this.cfg.clave;
    if (this.cfg.apiKey) cuerpo[this.cfg.campoApiKey || 'apiKey'] = this.cfg.apiKey;
    if (this.cfg.cliente) cuerpo.cliente = this.cfg.cliente;

    let r;
    try {
      r = await this.fetchFn(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(cuerpo),
      });
    } catch (e) {
      throw new TokenError(`No se pudo contactar al WMS para el login: ${e.message}`, 'NO_DISPONIBLE');
    }

    if (r.status === 401 || r.status === 403) {
      throw new TokenError('El WMS rechazó el usuario o la contraseña.', 'CREDENCIAL_INVALIDA');
    }
    if (!r.ok) {
      throw new TokenError(`El WMS respondió ${r.status} al pedir el token.`, 'LOGIN_FALLIDO');
    }

    const respuesta = await r.json();
    const token = extraerToken(respuesta);
    if (!token) {
      throw new TokenError(
        'El WMS respondió sin token reconocible. Revise el nombre del campo en el panel.',
        'RESPUESTA_INESPERADA',
      );
    }

    return {
      token,
      venceEn: calcularVencimiento(respuesta, { ttlMaxMs: this.ttlMaxMs, ahora: this.ahora() }),
    };
  }

  /** Invalida ambas cachés. Se llama tras un 401 con token en mano. */
  async invalidar() {
    this.memoria = null;
    try {
      await this.db.doc(RUTA_TOKEN).set({ token: null, venceEn: 0, renovandoDesde: null });
    } catch (e) {
      console.warn('No se pudo invalidar el token compartido:', e.message);
    }
  }

  /** Estado para el panel de administración. Nunca devuelve el token. */
  async estado() {
    const reg = this.vigente(this.memoria) ? this.memoria : await this.leerCompartido();
    if (!reg || !reg.token) {
      return { hayToken: false, vigente: false, metricas: this.metricas };
    }
    const restanteMs = Number(reg.venceEn) - this.ahora();
    return {
      hayToken: true,
      vigente: restanteMs > 0,
      venceEn: new Date(Number(reg.venceEn)).toISOString(),
      minutosRestantes: Math.max(Math.round(restanteMs / 60000), 0),
      obtenidoEn: reg.obtenidoEn ? new Date(reg.obtenidoEn).toISOString() : null,
      metricas: this.metricas,
    };
  }
}

module.exports = {
  TokenProvider, TokenError, calcularVencimiento, extraerToken,
  RUTA_TOKEN, MARGEN_MS, TTL_POR_DEFECTO_MS,
};
