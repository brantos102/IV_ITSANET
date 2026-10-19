/**
 * Sacar el histórico de Firestore para llevarlo al servidor de la empresa.
 *
 * Esto se montó sobre Firebase porque no había servidor. Ahora lo hay, y lo que
 * se ha validado tiene que acabar en MySQL. No hay forma de hacerlo del lado
 * servidor —en el plan gratuito no hay funciones, y el Apps Script no habla con
 * Firestore—, así que se arma aquí, en el navegador de un administrador, que es
 * quien tiene permiso para leerlo todo.
 *
 * Se lleva lo que no se puede volver a obtener: recepciones, sus líneas, el
 * libro mayor de conteos y la auditoría. NO se lleva el catálogo de productos,
 * que es una copia del maestro de Depot y se vuelve a descargar en un minuto.
 *
 * El formato lo lee scripts/importar_firestore.py. Si cambia, hay que subir
 * VERSION y enseñarle la nueva al importador.
 */
import {
  collection, getDocs, query, orderBy,
} from '../vendor/firebase-sdk.js?v=20261019-50';
import { db } from './auth.js?v=20261019-50';

export const VERSION = 1;

/**
 * Una fecha de Firestore, en texto.
 *
 * Los Timestamp no sobreviven a JSON.stringify: salen como {seconds, nanoseconds}
 * y al otro lado no hay forma de saber que eso era una fecha. En ISO sí.
 */
export function aIso(valor) {
  if (!valor) return null;
  if (typeof valor.toDate === 'function') return valor.toDate().toISOString();
  if (valor instanceof Date) return valor.toISOString();
  if (typeof valor.seconds === 'number') return new Date(valor.seconds * 1000).toISOString();
  return typeof valor === 'string' ? valor : null;
}

/** Convierte las fechas de un documento, a cualquier profundidad. */
export function limpiarDoc(d) {
  const salida = {};
  for (const [k, v] of Object.entries(d || {})) {
    if (v && typeof v === 'object' && typeof v.toDate === 'function') salida[k] = aIso(v);
    else if (Array.isArray(v)) salida[k] = v;
    else if (v && typeof v === 'object') salida[k] = limpiarDoc(v);
    else salida[k] = v;
  }
  return salida;
}

const leerSub = async (recepcionId, nombre, ordenar) => {
  const ref = collection(db, 'recepciones', recepcionId, nombre);
  const snap = await getDocs(ordenar ? query(ref, orderBy(ordenar, 'asc')) : ref);
  return snap.docs.map((d) => ({ id: d.id, ...limpiarDoc(d.data()) }));
};

/**
 * Todo lo que hay que llevarse.
 *
 * `alAvanzar(hechas, total, que)` se llama por recepción: son cuatro lecturas de
 * colección cada una y con treinta recepciones esto tarda, así que la pantalla
 * tiene que poder decir por dónde va en vez de quedarse en blanco.
 */
export async function reunirTodo(usuario, alAvanzar) {
  const usuarios = (await getDocs(collection(db, 'usuarios')))
    .docs.map((d) => ({ uid: d.id, ...limpiarDoc(d.data()) }));

  const recepcionesSnap = await getDocs(
    query(collection(db, 'recepciones'), orderBy('creadoEn', 'asc')));

  const recepciones = [];
  let hechas = 0;
  for (const d of recepcionesSnap.docs) {
    const base = { id: d.id, ...limpiarDoc(d.data()) };
    const [lineas, eventos, adicionales, auditoria] = await Promise.all([
      leerSub(d.id, 'lineas'),
      // En orden: el libro mayor sin orden deja de ser un libro mayor.
      leerSub(d.id, 'eventos', 'creadoEn'),
      leerSub(d.id, 'adicionales'),
      leerSub(d.id, 'auditoria').catch(() => []),
    ]);
    recepciones.push({ ...base, lineas, eventos, adicionales, auditoria });
    hechas++;
    if (alAvanzar) alAvanzar(hechas, recepcionesSnap.docs.length, base.codigo || d.id);
  }

  return {
    version: VERSION,
    exportadoEn: new Date().toISOString(),
    exportadoPor: usuario?.email || null,
    // El catálogo no va: se vuelve a bajar de Depot y traerlo solo sirve para
    // arrastrar datos viejos al servidor nuevo.
    usuarios,
    recepciones,
  };
}

/** Cuántas cosas trae, para poder comprobar al otro lado que llegó todo. */
export function contar(datos) {
  const r = datos.recepciones || [];
  const suma = (campo) => r.reduce((a, x) => a + (x[campo] || []).length, 0);
  return {
    usuarios: (datos.usuarios || []).length,
    recepciones: r.length,
    lineas: suma('lineas'),
    conteos: suma('eventos'),
    adicionales: suma('adicionales'),
    auditoria: suma('auditoria'),
  };
}

export function descargarJson(datos, nombre) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(datos, null, 1)], { type: 'application/json' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = nombre;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 8000);
}
