/** Fechas de Firestore y de la API local comparten el mismo criterio. */
export function fechaDe(valor) {
  if (valor == null || valor === '') return null;
  let fecha;
  if (typeof valor.toDate === 'function') fecha = valor.toDate();
  else if (typeof valor === 'object' && typeof valor.seconds === 'number') fecha = new Date(valor.seconds * 1000);
  else fecha = new Date(valor);
  return Number.isNaN(fecha.getTime()) ? null : fecha;
}
export function recientes(recepciones, dias = 15, ahora = Date.now()) {
  const desde = ahora - dias * 86400000;
  return recepciones.filter(r => { const f = fechaDe(r.creadoEn); return f && f.getTime() >= desde; });
}
