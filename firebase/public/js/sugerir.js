/**
 * Buscar un código sin saberlo de memoria.
 *
 * Los códigos de recepción se parecen entre sí hasta confundirse: REC0260002 y
 * REC026002 son dos recepciones distintas y un dígito de diferencia. Quien
 * busca un informe escribe lo que recuerda, no el código exacto, y hasta ahora
 * un carácter de más devolvía «sin resultados» sin decir que había algo a un
 * dígito de distancia.
 *
 * Aquí se ordena por parecido en vez de exigir coincidencia exacta.
 */

/** Para comparar: sin espacios, guiones ni mayúsculas. REC-026 002 = rec026002. */
export const normalizar = (v) =>
  String(v ?? '').toUpperCase().replace(/[^A-Z0-9]/g, '');

/**
 * Distancia de edición: cuántos cambios de un carácter separan dos textos.
 * Un dígito tecleado de más, de menos o cambiado de sitio cuesta 1.
 */
export function distancia(a, b) {
  if (a === b) return 0;
  if (!a.length) return b.length;
  if (!b.length) return a.length;

  let fila = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    let anterior = fila[0];
    fila[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const guardado = fila[j];
      fila[j] = Math.min(
        fila[j] + 1,                                       // borrar
        fila[j - 1] + 1,                                   // insertar
        anterior + (a[i - 1] === b[j - 1] ? 0 : 1),         // sustituir
      );
      anterior = guardado;
    }
  }
  return fila[b.length];
}

/**
 * Cuánto se parece lo escrito a un candidato, de 0 a 1.
 *
 * Mandan, por este orden: es igual, empieza igual (lo normal mientras se
 * teclea), lo contiene, y por último se parece aunque haya un error.
 */
export function parecido(texto, candidato) {
  const a = normalizar(texto);
  const b = normalizar(candidato);
  if (!a || !b) return 0;
  if (a === b) return 1;
  if (b.startsWith(a)) return 0.95 - (0.1 * (1 - a.length / b.length));
  if (b.includes(a)) return 0.8 - (0.1 * (1 - a.length / b.length));

  const d = distancia(a, b);
  const cerca = 1 - d / Math.max(a.length, b.length);
  return cerca > 0 ? cerca * 0.75 : 0;
}

/**
 * Los candidatos que más se parecen, de mayor a menor.
 *
 * `clave` saca el texto a comparar de cada candidato, para poder pasar objetos
 * enteros y recuperarlos. Con el texto vacío devuelve los primeros tal cual:
 * un campo recién abierto enseña lo que hay, no nada.
 */
export function parecidos(texto, candidatos, opciones = {}) {
  const { max = 8, minimo = 0.45, clave = (c) => c } = opciones;
  const lista = candidatos || [];
  if (!normalizar(texto)) return lista.slice(0, max);

  return lista
    .map((c) => ({ c, p: parecido(texto, clave(c)) }))
    .filter((x) => x.p >= minimo)
    .sort((x, y) => y.p - x.p)
    .slice(0, max)
    .map((x) => x.c);
}

/**
 * Lo que se dice cuando no hay coincidencia exacta pero sí algo parecido.
 * Devuelve '' si lo escrito es exactamente uno de los candidatos: entonces no
 * hay nada que sugerir.
 */
export function avisoDeParecidos(texto, candidatos, clave = (c) => c) {
  const a = normalizar(texto);
  if (!a) return '';
  const lista = candidatos || [];
  if (lista.some((c) => normalizar(clave(c)) === a)) return '';

  const cerca = parecidos(texto, lista, { max: 3, minimo: 0.6, clave });
  if (!cerca.length) return '';
  return `¿Quisiste decir ${cerca.map((c) => `«${clave(c)}»`).join(' o ')}?`;
}
