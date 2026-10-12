/**
 * Simulador de Firestore suficiente para probar la lógica de conteo.
 *
 * Implementa de verdad lo que importa para las pruebas de concurrencia:
 *   - `runTransaction` con reintento ante escritura concurrente (optimista,
 *     igual que Firestore: si un documento leído cambió, la transacción reintenta).
 *   - `FieldValue.increment()` aplicado en el commit, no al construir el payload.
 *   - Rutas con punto (`pallets.B04`) como actualización de campo anidado.
 *
 * No pretende ser Firestore completo: pretende que un fallo aquí sea un fallo real.
 */
'use strict';

const SENTINEL = Symbol('sentinel');

class FieldValueStub {
  constructor(tipo, valor) { this.tipo = tipo; this.valor = valor; this[SENTINEL] = true; }
  static increment(n) { return new FieldValueStub('increment', n); }
  static serverTimestamp() { return new FieldValueStub('serverTimestamp'); }
  static delete() { return new FieldValueStub('delete'); }
  static arrayUnion(...v) { return new FieldValueStub('arrayUnion', v); }
}
const esSentinel = (v) => v instanceof FieldValueStub;

function clonar(v) {
  if (v === null || typeof v !== 'object') return v;
  if (v instanceof Date) return new Date(v);
  if (Array.isArray(v)) return v.map(clonar);
  const o = {};
  for (const k of Object.keys(v)) o[k] = clonar(v[k]);
  return o;
}

function fijarRuta(obj, ruta, valor) {
  const partes = ruta.split('.');
  let cur = obj;
  for (let i = 0; i < partes.length - 1; i++) {
    if (typeof cur[partes[i]] !== 'object' || cur[partes[i]] === null) cur[partes[i]] = {};
    cur = cur[partes[i]];
  }
  cur[partes[partes.length - 1]] = valor;
}

function leerRuta(obj, ruta) {
  return ruta.split('.').reduce((a, k) => (a === undefined || a === null ? undefined : a[k]), obj);
}

/** Aplica un payload (con sentinels) sobre el estado actual del documento. */
function aplicar(actual, payload, merge) {
  const base = merge && actual ? clonar(actual) : {};
  for (const [clave, valor] of Object.entries(payload)) {
    if (esSentinel(valor)) {
      if (valor.tipo === 'increment') {
        const previo = Number(leerRuta(base, clave) ?? leerRuta(actual || {}, clave) ?? 0);
        fijarRuta(base, clave, previo + valor.valor);
      } else if (valor.tipo === 'serverTimestamp') {
        fijarRuta(base, clave, new Date());
      } else if (valor.tipo === 'delete') {
        fijarRuta(base, clave, undefined);
      } else if (valor.tipo === 'arrayUnion') {
        const previo = leerRuta(base, clave) || [];
        fijarRuta(base, clave, [...new Set([...previo, ...valor.valor])]);
      }
    } else {
      fijarRuta(base, clave, clonar(valor));
    }
  }
  return base;
}

class Snapshot {
  constructor(ref, datos, version) {
    this.ref = ref; this.id = ref.id; this._datos = datos; this._version = version;
  }
  get exists() { return this._datos !== undefined; }
  data() { return this._datos === undefined ? undefined : clonar(this._datos); }
  get(campo) { return this._datos === undefined ? undefined : leerRuta(this._datos, campo); }
}

class DocRef {
  constructor(db, ruta) { this.db = db; this.path = ruta; this.id = ruta.split('/').pop(); }
  collection(nombre) { return new ColRef(this.db, `${this.path}/${nombre}`); }
  async get() { return this.db._leer(this.path); }
  async set(datos, opciones = {}) { return this.db._escribir(this.path, datos, !!opciones.merge); }
  async update(datos) {
    if (!this.db.docs.has(this.path)) throw new Error('No existe: ' + this.path);
    return this.db._escribir(this.path, datos, true);
  }
  async delete() { this.db.docs.delete(this.path); }
}

class Query {
  constructor(col, filtros = [], limite = null) { this.col = col; this.filtros = filtros; this.limite = limite; }
  where(campo, op, valor) { return new Query(this.col, [...this.filtros, { campo, op, valor }], this.limite); }
  limit(n) { return new Query(this.col, this.filtros, n); }
  orderBy() { return this; }
  async get() {
    const prefijo = this.col.path + '/';
    let docs = [...this.col.db.docs.entries()]
      .filter(([ruta]) => ruta.startsWith(prefijo) && !ruta.slice(prefijo.length).includes('/'))
      .map(([ruta, reg]) => new Snapshot(new DocRef(this.col.db, ruta), reg.datos, reg.version));

    for (const f of this.filtros) {
      docs = docs.filter((d) => {
        const v = f.campo === '__name__' ? d.id : d.get(f.campo);
        switch (f.op) {
          case '==': return v === f.valor;
          case '>=': return v >= f.valor;
          case '<': return v < f.valor;
          case '>': return v > f.valor;
          case '<=': return v <= f.valor;
          case 'in': return Array.isArray(f.valor) && f.valor.includes(v);
          default: throw new Error('operador no soportado: ' + f.op);
        }
      });
    }
    docs.sort((a, b) => (a.id < b.id ? -1 : 1));
    if (this.limite) docs = docs.slice(0, this.limite);
    return { docs, empty: docs.length === 0, size: docs.length, forEach: (fn) => docs.forEach(fn) };
  }
}

class ColRef extends Query {
  constructor(db, ruta) { super(null); this.db = db; this.path = ruta; this.col = this; }
  doc(id) { return new DocRef(this.db, `${this.path}/${id || 'auto-' + (++this.db.contador)}`); }
}

class ConflictoTransaccion extends Error {}

class Transaction {
  constructor(db) { this.db = db; this.leidos = new Map(); this.escrituras = []; }
  async get(ref) {
    const snap = this.db._leer(ref.path);
    this.leidos.set(ref.path, snap._version);
    return snap;
  }
  set(ref, datos, opciones = {}) {
    this.escrituras.push({ ruta: ref.path, datos, merge: !!opciones.merge, tipo: 'set' });
  }
  update(ref, datos) {
    this.escrituras.push({ ruta: ref.path, datos, merge: true, tipo: 'update' });
  }
  delete(ref) { this.escrituras.push({ ruta: ref.path, tipo: 'delete' }); }
}

class Batch {
  constructor(db) { this.db = db; this.ops = []; }
  set(ref, datos, opciones = {}) { this.ops.push({ ruta: ref.path, datos, merge: !!opciones.merge }); return this; }
  update(ref, datos) { this.ops.push({ ruta: ref.path, datos, merge: true }); return this; }
  delete(ref) { this.ops.push({ ruta: ref.path, borrar: true }); return this; }
  async commit() {
    for (const op of this.ops) {
      if (op.borrar) this.db.docs.delete(op.ruta);
      else this.db._escribir(op.ruta, op.datos, op.merge);
    }
    return this.ops.length;
  }
}

class FirestoreStub {
  constructor() {
    this.docs = new Map();      // ruta -> { datos, version }
    this.contador = 0;
    this.transaccionesReintentadas = 0;
    /** Gancho para forzar una carrera en las pruebas. */
    this.alLeerEnTransaccion = null;
  }

  collection(nombre) { return new ColRef(this, nombre); }
  doc(ruta) { return new DocRef(this, ruta); }
  batch() { return new Batch(this); }

  _leer(ruta) {
    const reg = this.docs.get(ruta);
    return new Snapshot(new DocRef(this, ruta), reg ? reg.datos : undefined, reg ? reg.version : 0);
  }

  _escribir(ruta, datos, merge) {
    const reg = this.docs.get(ruta);
    const nuevos = aplicar(reg ? reg.datos : undefined, datos, merge);
    this.docs.set(ruta, { datos: nuevos, version: (reg ? reg.version : 0) + 1 });
  }

  /**
   * Transacción optimista con reintento, como la real: si algún documento leído
   * cambió entre la lectura y el commit, se descarta y se vuelve a ejecutar.
   */
  async runTransaction(fn, { maxIntentos = 12 } = {}) {
    let ultimoError;
    for (let intento = 0; intento < maxIntentos; intento++) {
      const tx = new Transaction(this);
      let resultado;
      try {
        resultado = await fn(tx);
      } catch (e) {
        throw e;   // error de negocio: no se reintenta
      }

      if (this.alLeerEnTransaccion && intento === 0) {
        const hook = this.alLeerEnTransaccion;
        this.alLeerEnTransaccion = null;
        await hook();
      }

      let conflicto = false;
      for (const [ruta, version] of tx.leidos) {
        const actual = this.docs.get(ruta);
        if ((actual ? actual.version : 0) !== version) { conflicto = true; break; }
      }
      if (conflicto) {
        this.transaccionesReintentadas++;
        ultimoError = new ConflictoTransaccion('conflicto de escritura');
        // Espera creciente, como el reintento del cliente real.
        await new Promise((r) => setTimeout(r, Math.min(2 ** intento, 50)));
        continue;
      }

      for (const w of tx.escrituras) {
        if (w.tipo === 'delete') this.docs.delete(w.ruta);
        else this._escribir(w.ruta, w.datos, w.merge);
      }
      return resultado;
    }
    throw ultimoError || new ConflictoTransaccion('transacción agotó reintentos');
  }

  /** Volcado legible para depurar una prueba. */
  volcar(prefijo = '') {
    const o = {};
    for (const [ruta, reg] of this.docs) if (ruta.startsWith(prefijo)) o[ruta] = reg.datos;
    return o;
  }
}

module.exports = { FirestoreStub, FieldValueStub, ConflictoTransaccion, clonar };
