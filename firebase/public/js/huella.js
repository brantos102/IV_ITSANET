/**
 * Identificar un packing list por lo que dice, no por cómo se llama.
 *
 * El mismo archivo llega dos veces con nombres distintos —reenviado por correo,
 * renombrado con la fecha, guardado dos veces— y se valida dos veces. El
 * trabajo se duplica, los informes se contradicen y nadie sabe cuál subir.
 *
 * La huella se calcula sobre el CONTENIDO: las parejas producto-cantidad
 * ordenadas. Renombrar el archivo no la cambia; cambiar una cantidad, sí. Así
 * «es el mismo» y «se parece pero no es» quedan separados.
 */

/**
 * Hash determinista de 64 bits, en hexadecimal.
 *
 * FNV-1a por duplicado con semillas distintas. No es criptográfico y no hace
 * falta que lo sea: aquí solo se compara con una lista corta de packing lists
 * de la misma empresa, no se defiende de nadie que quiera provocar un choque.
 * A cambio es síncrono y se puede probar, que es lo que importa.
 */
export function hash64(texto) {
  const s = String(texto);
  let a = 0x811c9dc5;
  let b = 0x01000193;

  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    a = Math.imul(a ^ c, 0x01000193) >>> 0;
    b = Math.imul(b ^ c, 0x85ebca6b) >>> 0;
    b = (b ^ (b >>> 13)) >>> 0;
  }
  return a.toString(16).padStart(8, '0') + b.toString(16).padStart(8, '0');
}

/**
 * Lo que identifica a un packing list.
 *
 * Las líneas van ordenadas por producto y cantidad: dos exportaciones del mismo
 * pedido pueden traer las filas en otro orden sin ser archivos distintos.
 */
export function huellaDe(resultado) {
  const lineas = (resultado?.lineas || []).map((l) =>
    `${l.sku}:${Number(l.cantidad) || 0}`).sort();
  return hash64(lineas.join('|'));
}

/** Las cifras con las que se detecta un «se parece mucho». */
export function resumenDe(resultado, archivo) {
  const lineas = resultado?.lineas || [];
  return {
    huella: huellaDe(resultado),
    lineas: lineas.length,
    skus: Object.keys(resultado?.porSku || {}).length,
    unidades: Number(resultado?.unidades) || 0,
    archivo: nombreLimpio(archivo),
  };
}

/** Sin la extensión ni lo que el navegador o el correo añaden al descargar. */
export function nombreLimpio(archivo) {
  return String(archivo || '')
    .replace(/\.(xlsx|xlsm|xls|csv)$/i, '')
    .replace(/\s*\(\d+\)$/, '')        // «lista (2)»
    .trim()
    .toUpperCase();
}

/**
 * Cómo de parecidos son dos packing lists.
 *
 * `identico`  — las mismas líneas con las mismas cantidades. Es el mismo.
 * `probable`  — coinciden líneas, productos y unidades, pero algo cambió de
 *               sitio. Casi seguro una versión del mismo pedido.
 * `revisar`   — coincide el nombre del archivo, o dos de las tres cifras.
 * `distinto`  — no se parecen.
 */
export function comparar(a, b) {
  if (!a || !b) return { nivel: 'distinto', motivos: [] };

  if (a.huella && a.huella === b.huella) {
    return {
      nivel: 'identico',
      motivos: ['las mismas líneas con las mismas cantidades'],
    };
  }

  const motivos = [];
  if (a.lineas === b.lineas) motivos.push(`las mismas ${a.lineas} líneas`);
  if (a.skus === b.skus) motivos.push(`los mismos ${a.skus} productos`);
  if (a.unidades === b.unidades) motivos.push(`las mismas ${a.unidades} unidades`);

  const mismoNombre = !!a.archivo && a.archivo === b.archivo;
  if (mismoNombre) motivos.push(`el mismo nombre de archivo «${a.archivo}»`);

  if (motivos.length >= 3) return { nivel: 'probable', motivos };
  if (mismoNombre || motivos.length === 2) return { nivel: 'revisar', motivos };
  return { nivel: 'distinto', motivos };
}
