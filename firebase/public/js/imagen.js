/**
 * Reduce las fotos antes de subirlas.
 *
 * La cámara de un handheld entrega entre 3 y 8 MB por foto. Codificarla en
 * base64 para mandarla por el proxy la infla un tercio más, así que una sola
 * evidencia puede acercarse a los 10 MB. Eso tarda lo suyo por el WiFi del
 * almacén, y el proxy de Apps Script se queda sin tiempo antes de terminar:
 * es el «el proxy tardó demasiado» que se ve al registrar un PNC.
 *
 * Para documentar un golpe o una caja mojada no hacen falta 8 MB. A 1600 px de
 * lado mayor y calidad 0,72 la foto pesa entre 200 y 400 KB —veinte veces
 * menos— y el daño se ve exactamente igual.
 */

const LADO_MAX = 1600;
const CALIDAD = 0.72;

/** Lee un archivo como data URL. */
function leerComoDataURL(archivo) {
  return new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(String(fr.result));
    fr.onerror = () => rej(new Error('No se pudo leer la imagen.'));
    fr.readAsDataURL(archivo);
  });
}

function cargarImagen(url) {
  return new Promise((res, rej) => {
    const img = new Image();
    img.onload = () => res(img);
    img.onerror = () => rej(new Error('El archivo no es una imagen válida.'));
    img.src = url;
  });
}

/** Lado mayor limitado a `lado`, manteniendo la proporción. Nunca agranda. */
export function medidas(ancho, alto, lado = LADO_MAX) {
  if (!ancho || !alto) return { ancho: 0, alto: 0 };
  const mayor = Math.max(ancho, alto);
  if (mayor <= lado) return { ancho, alto };
  const f = lado / mayor;
  return { ancho: Math.round(ancho * f), alto: Math.round(alto * f) };
}

/**
 * Comprime una imagen y la devuelve en base64, sin la cabecera `data:`.
 *
 * Si algo falla —un formato que el navegador no sabe dibujar, un canvas
 * bloqueado— se devuelve el original. Más vale una foto grande que ninguna.
 */
export async function comprimir(archivo, { lado = LADO_MAX, calidad = CALIDAD } = {}) {
  const original = await leerComoDataURL(archivo);
  const base64Original = original.split(',')[1] || '';

  try {
    const img = await cargarImagen(original);
    const m = medidas(img.naturalWidth, img.naturalHeight, lado);
    if (!m.ancho) return { base64: base64Original, tipo: archivo.type, comprimida: false };

    const lienzo = document.createElement('canvas');
    lienzo.width = m.ancho;
    lienzo.height = m.alto;
    const ctx = lienzo.getContext('2d');
    ctx.drawImage(img, 0, 0, m.ancho, m.alto);

    const reducida = lienzo.toDataURL('image/jpeg', calidad);
    const base64 = reducida.split(',')[1] || '';

    // Un PNG pequeño puede engordar al pasar a JPEG: en ese caso no se toca.
    if (!base64 || base64.length >= base64Original.length) {
      return { base64: base64Original, tipo: archivo.type, comprimida: false };
    }

    return {
      base64,
      tipo: 'image/jpeg',
      comprimida: true,
      bytesOriginal: Math.round(base64Original.length * 0.75),
      bytes: Math.round(base64.length * 0.75),
      ancho: m.ancho,
      alto: m.alto,
    };
  } catch {
    return { base64: base64Original, tipo: archivo.type, comprimida: false };
  }
}

/** Para los mensajes: «2,4 MB» en vez de 2516582. */
export function tamanoLegible(bytes) {
  if (!bytes || bytes < 1024) return (bytes || 0) + ' B';
  if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1).replace('.', ',') + ' MB';
}
