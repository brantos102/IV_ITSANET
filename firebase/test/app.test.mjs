#!/usr/bin/env node
/**
 * Pruebas de la lógica del navegador.   node firebase/test/app.test.mjs
 *
 * Cubre lo que decide si la entrega es correcta o no: la normalización de
 * códigos y pallets, el estado de cada SKU, el resumen de la recepción y —lo
 * más delicado— que el informe entregue exactamente las filas del packing list
 * original, incluso con un SKU repetido en dos líneas.
 */
import { cargar, test, eq, ok, resumen } from './cargador.mjs';

const auth = await cargar('auth.js');
const datos = await cargar('datos.js');
const conteo = await cargar('conteo.js');
const informe = await cargar('informe.js');

// ========================== Normalización ================================= //
await test('normalizarCodigo quita guiones, puntos y espacios invisibles', () => {
  eq(datos.normalizarCodigo(' 2h0-525.345 '), '2H0525345');
  eq(datos.normalizarCodigo('6Q0 959 858 9B9'), '6Q09598589B9');
  eq(datos.normalizarCodigo('​1K0 145‍828'), '1K0145828');
  eq(datos.normalizarCodigo(null), '');
});

await test('normalizarPallet conserva el punto del subpallet', () => {
  eq(datos.normalizarPallet(' b04 . 1 '), 'B04.1');
  eq(datos.normalizarPallet('a-1'), 'A1');
});

// El guion separa nave, calle, columna y nivel: borrarlo convertía A-01-03-2 en
// A01032, que no se puede buscar en Depot ni leer de un vistazo.
// «PL-A» como clave de mapa quedaba en «PLA» con el normalizador de pallets, y
// entonces lo imputado a una lista no se podía encontrar por su nombre.
await test('claveMapa conserva el nombre de la lista y protege el punto', () => {
  eq(datos.claveMapa('PL-A'), 'PL-A');
  eq(datos.claveMapa('RB 48529'), 'RB 48529');
  eq(datos.claveMapa('v1.2'), 'V1~2', 'el punto sí, que Firestore lo usa de ruta');
  eq(datos.palletDesdeClave(datos.claveMapa('v1.2')), 'V1.2');
  eq(datos.claveMapa(''), '');
  // Y sigue siendo distinto del de pallets, que sí borra los guiones.
  eq(datos.clavePallet('PL-A'), 'PLA');
});

await test('normalizarPosicion conserva los guiones de la ubicación', () => {
  eq(datos.normalizarPosicion('a-01-03-2'), 'A-01-03-2');
  eq(datos.normalizarPosicion('  BM-BB-04-1  '), 'BM-BB-04-1');
  eq(datos.normalizarPosicion('A 01 03 2'), 'A01032', 'los espacios sí se quitan');
  eq(datos.normalizarPosicion(''), '');
  eq(datos.normalizarPosicion(null), '');
  // Y sigue siendo distinto de lo que hace el normalizador de pallets.
  eq(datos.normalizarPallet('a-01-03-2'), 'A01032');
});

await test('palletValido rechaza lo que rompería el informe', () => {
  ok(datos.palletValido('A1'));
  ok(datos.palletValido('B04.1'));
  ok(datos.palletValido('C12.3.4'));
  ok(!datos.palletValido(''), 'vacío');
  ok(!datos.palletValido('B04.'), 'punto final');
  ok(!datos.palletValido('A/1'), 'carácter especial');
  ok(!datos.palletValido('A'.repeat(41)), 'demasiado largo');
  // El pallet genérico para lo que va directo a su posición sin armar pallet.
  ok(datos.palletValido('DP'), 'directo a posición');
});

await test('aNumero resuelve los dos formatos de miles y decimales', () => {
  eq(datos.aNumero('1.234,50'), 1234.5, 'formato local');
  eq(datos.aNumero('1,234.50'), 1234.5, 'formato inglés');
  eq(datos.aNumero('1.234'), 1234, 'tres dígitos sin otro separador: miles');
  eq(datos.aNumero('1.5'), 1.5, 'un decimal');
  eq(datos.aNumero('1,5'), 1.5, 'un decimal con coma');
  eq(datos.aNumero('12.345,678'), 12345.678);
  eq(datos.aNumero('-7,25'), -7.25);
  eq(datos.aNumero('12 UN'), 12);
  eq(datos.aNumero('', 7), 7);
  eq(datos.aNumero('abc', 0), 0);
  eq(datos.aNumero(-3), -3);
  eq(datos.aNumero(NaN, 1), 1);
});

// El punto es separador de rutas en Firestore: sin codificar, el subpallet
// B04.1 crearía pallets→B04→1 y el conteo del subpallet se perdería.
await test('clavePallet y palletDesdeClave son inversas', () => {
  eq(datos.clavePallet('B04.1'), 'B04~1');
  eq(datos.palletDesdeClave('B04~1'), 'B04.1');
  eq(datos.palletDesdeClave(datos.clavePallet('C12.3.4')), 'C12.3.4');
  ok(!datos.palletValido('B04~1'), 'el separador no puede ser un pallet real');
});

await test('decodificarPallets descarta los que quedaron en cero', () => {
  eq(datos.decodificarPallets({ 'A1': 5, 'B04~1': 3, 'C2': 0 }), { A1: 5, 'B04.1': 3 });
  eq(datos.decodificarPallets(null), {});
});

// ============================ Estados ===================================== //
await test('estadoDe cubre los cinco casos', () => {
  eq(datos.estadoDe(10, 0), 'PENDIENTE', 'nadie lo ha buscado');
  eq(datos.estadoDe(10, 10), 'OK');
  eq(datos.estadoDe(10, 4), 'FALTANTE');
  eq(datos.estadoDe(10, 12), 'SOBRANTE');
  eq(datos.estadoDe(0, 0), 'OK', 'línea declarada en 0 y sin contar');
  eq(datos.estadoDe(0, 3), 'SOBRANTE', 'adicional');
});

// «Nadie lo ha buscado» y «se buscó y no apareció» son cosas distintas: la
// primera es trabajo pendiente, la segunda un faltante que ya se reclama.
await test('un cero declarado no es lo mismo que un SKU sin tocar', () => {
  eq(datos.estadoDe(10, 0, false), 'PENDIENTE');
  eq(datos.estadoDe(10, 0, true), 'NO_ENCONTRADO');
  eq(datos.estadoDe(0, 0, true), 'OK', 'declarada en 0 y confirmada en 0 cuadra');
});

await test('cada estado tiene su etiqueta para el operario', () => {
  for (const e of ['OK', 'FALTANTE', 'NO_ENCONTRADO', 'SOBRANTE', 'PENDIENTE']) {
    ok(datos.ETIQUETA_ESTADO[e], 'falta la etiqueta de ' + e);
  }
});

// ========================== Ubicaciones =================================== //
await test('ubicacionesDe ordena por cantidad y decodifica el subpallet', () => {
  eq(conteo.ubicacionesDe({ pallets: { 'A1': 2, 'B04~1': 9, 'C3': 0 } }),
    [{ pallet: 'B04.1', cantidad: 9 }, { pallet: 'A1', cantidad: 2 }]);
  eq(conteo.ubicacionesDe({}), []);
  eq(conteo.ubicacionesDe(null), []);
});

// =========================== Resumen ====================================== //
await test('resumir cuenta estados, unidades y exactitud', () => {
  const r = conteo.resumir([
    { sku: 'A', esperado: 10, contado: 10 },
    { sku: 'B', esperado: 5, contado: 3 },
    { sku: 'C', esperado: 2, contado: 0 },
    { sku: 'D', esperado: 1, contado: 4 },
    { sku: 'E', esperado: 0, contado: 6, enPackingList: false },
  ]);
  eq(r.skus, 5);
  eq(r.ok, 1);
  eq(r.faltante, 2, 'B y C');
  eq(r.sobrante, 2, 'D y E');
  eq(r.sinContar, 1, 'solo C');
  eq(r.noEncontrado, 0, 'nadie ha declarado todavía que no aparece');
  eq(r.unidadesEsperadas, 18);
  eq(r.unidadesFisicas, 23);
  eq(r.diferencia, 5);
  eq(r.adicionales, 1);
  eq(r.discrepancias.length, 4);
  eq(r.exactitud, 20);
});

await test('resumir separa lo que falta buscar de lo que no apareció', () => {
  const r = conteo.resumir([
    { sku: 'A', esperado: 5, contado: 0 },                      // nadie lo buscó
    { sku: 'B', esperado: 5, contado: 0, verificado: true },    // buscado, no está
    { sku: 'C', esperado: 5, contado: 2 },                      // faltan 3
  ]);
  eq(r.faltante, 3, 'los tres son faltantes');
  eq(r.sinContar, 1, 'solo A queda por buscar');
  eq(r.noEncontrado, 1, 'solo B está confirmado como ausente');
  eq(r.sinVerificar, 1, 'lo que bloquea el cierre');
});

await test('resumir no divide por cero con la recepción vacía', () => {
  const r = conteo.resumir([]);
  eq(r.avance, 0);
  eq(r.exactitud, 0);
});

await test('el avance no pasa de 100 aunque haya sobrantes', () => {
  eq(conteo.resumir([{ sku: 'A', esperado: 10, contado: 25 }]).avance, 100);
  eq(conteo.resumir([{ sku: 'A', esperado: 10, contado: 5 }]).avance, 50);
});

// Pasó de verdad: 221 declaradas, 385 contadas, 20 SKU faltantes, y la barra
// marcaba 100%. Un sobrante en un producto tapaba lo que faltaba en otro.
await test('un sobrante no puede tapar lo que falta en otro SKU', () => {
  const r = conteo.resumir([
    { sku: 'A', esperado: 100, contado: 300 },   // sobrante enorme
    { sku: 'B', esperado: 100, contado: 0 },     // no llegó nada
  ]);
  eq(r.unidadesEsperadas, 200);
  eq(r.unidadesFisicas, 300);
  eq(r.unidadesCubiertas, 100, 'solo A cuenta, y solo hasta lo declarado');
  eq(r.avance, 50, 'la mitad sigue sin verificarse');
  eq(r.faltante, 1);
  eq(r.sobrante, 1);
});

await test('el avance llega a 100 solo cuando todo está cubierto', () => {
  eq(conteo.resumir([
    { sku: 'A', esperado: 10, contado: 10 },
    { sku: 'B', esperado: 30, contado: 30 },
  ]).avance, 100);
});

// ===================== Reparto por línea (22 filas = 22 filas) ============ //
// La regla del cliente es literal: el archivo entregado tiene las mismas filas
// que el recibido. Con un SKU repetido hay que decidir en qué fila va cada
// unidad contada, sin inventar ni perder ninguna.
const LINEAS_VW = [
  { linea: 1, sku: '2H0525345', cantidad: 1 },
  { linea: 2, sku: '6Q09598589B9', cantidad: 2 },
  { linea: 3, sku: '2H0525345', cantidad: 3 },   // repetido: otra factura
  { linea: 4, sku: '1K0145828', cantidad: 5 },
  { linea: 5, sku: '5G0998225', cantidad: 0 },   // declarada en 0
];

await test('reparto completo devuelve una fila por línea', () => {
  const r = informe.repartirPorLinea(LINEAS_VW, {
    '2H0525345': 4, '6Q09598589B9': 2, '1K0145828': 5, '5G0998225': 0,
  });
  eq(r.length, 5, 'mismas filas que el original');
  eq(r.map((l) => l.fisica), [1, 2, 3, 5, 0]);
  eq(r.map((l) => l.diferencia), [0, 0, 0, 0, 0]);
});

await test('el SKU repetido llena la primera línea antes de la segunda', () => {
  const r = informe.repartirPorLinea(LINEAS_VW, { '2H0525345': 2 });
  eq(r[0].fisica, 1, 'la línea 1 se completa');
  eq(r[2].fisica, 1, 'el resto baja a la línea 3');
  eq(r[2].diferencia, -2);
});

await test('el sobrante del SKU repetido queda en su última línea', () => {
  const r = informe.repartirPorLinea(LINEAS_VW, { '2H0525345': 10 });
  eq(r[0].fisica, 1);
  eq(r[2].fisica, 9, 'la última carga el exceso');
  eq(r[2].diferencia, 6);
  eq(r[0].fisica + r[2].fisica, 10, 'no se pierde ni se inventa ninguna unidad');
});

await test('lo no contado queda en cero, no se omite la fila', () => {
  const r = informe.repartirPorLinea(LINEAS_VW, {});
  eq(r.length, 5);
  eq(r.map((l) => l.fisica), [0, 0, 0, 0, 0]);
  eq(r.map((l) => l.diferencia), [-1, -2, -3, -5, 0]);
});

await test('la suma por SKU del reparto coincide siempre con el conteo', () => {
  const totales = { '2H0525345': 7, '6Q09598589B9': 1, '1K0145828': 5, '5G0998225': 2 };
  const r = informe.repartirPorLinea(LINEAS_VW, totales);
  const porSku = {};
  r.forEach((l) => { porSku[l.sku] = (porSku[l.sku] || 0) + l.fisica; });
  eq(porSku, totales);
});

await test('la línea declarada en 0 admite lo que llegó físicamente', () => {
  const r = informe.repartirPorLinea(LINEAS_VW, { '5G0998225': 4 });
  eq(r[4].fisica, 4);
  eq(r[4].diferencia, 4);
});

// ============================== Acceso ==================================== //
// El operario escribe su usuario, no su correo: con guantes, en un handheld y
// en el relevo de turno, cada carácter de más es un intento fallido.
await test('normalizarAlias deja solo lo que se puede teclear con guantes', () => {
  eq(auth.normalizarAlias('  JPerez  '), 'jperez');
  eq(auth.normalizarAlias('juan.perez'), 'juan.perez');
  eq(auth.normalizarAlias('juan-perez_2'), 'juan-perez_2');
  eq(auth.normalizarAlias('Juan Pérez'), 'juanprez', 'espacios y acentos fuera');
  eq(auth.normalizarAlias('jperez@itsanet.com'), 'jperezitsanet.com');
  eq(auth.normalizarAlias(''), '');
  eq(auth.normalizarAlias(null), '');
});

await test('pareceCorreo distingue una dirección de un alias', () => {
  ok(auth.pareceCorreo('juan.perez@itsanet.com'));
  ok(auth.pareceCorreo('juan@gmail.com'), 'un gmail también vale');
  ok(!auth.pareceCorreo('jperez'), 'un alias no es un correo');
  ok(!auth.pareceCorreo('juan@itsanet'), 'sin dominio de primer nivel');
  ok(!auth.pareceCorreo('juan perez@itsanet.com'), 'con espacio');
  ok(!auth.pareceCorreo(''));
  ok(!auth.pareceCorreo(null));
});

await test('resolverCorreo devuelve tal cual lo que ya es un correo', async () => {
  // El alias se busca en Firestore; con un correo no hace falta ir a buscarlo.
  eq(await auth.resolverCorreo('Juan@Gmail.com'), 'juan@gmail.com');
  eq(await auth.resolverCorreo('  '), '');
  eq(await auth.resolverCorreo(null), '');
  // Sin base de datos de verdad, un alias no resuelve: se devuelve vacío en vez
  // de inventarse «jperez@itsanet.com», que es justo lo que no se debe hacer.
  eq(await auth.resolverCorreo('jperez'), '');
});

await test('dominioValido sigue cerrando el alta automática con Google', () => {
  ok(auth.dominioValido('jperez@itsanet.com'));
  ok(!auth.dominioValido('juan@gmail.com'), 'un gmail entra por registro, no solo');
  ok(!auth.dominioValido('jperez@itsanetXcom'), 'el punto no es un comodín');
  ok(!auth.dominioValido(null));
});

await test('tipoDeAcceso distingue la contraseña de Google', () => {
  eq(auth.tipoDeAcceso({ providerData: [{ providerId: 'password' }] }), 'CLAVE');
  eq(auth.tipoDeAcceso({ providerData: [{ providerId: 'google.com' }] }), 'GOOGLE');
  eq(auth.tipoDeAcceso({ providerData: [] }), 'DESCONOCIDO');
  eq(auth.tipoDeAcceso(null), 'DESCONOCIDO', 'sin sesión no debe reventar');
});

await test('traducirError explica qué hacer, no el código', () => {
  const m = auth.traducirError({ code: 'auth/invalid-credential' });
  ok(/incorrect/i.test(m), m);
  ok(/administrador/i.test(auth.traducirError({ code: 'auth/user-not-found' })));
  ok(/6 caracteres/.test(auth.traducirError({ code: 'auth/weak-password' })));
  // Un código desconocido no puede quedarse en blanco.
  ok(auth.traducirError({ code: 'auth/algo-nuevo', message: 'vaya' }).length > 0);
  ok(auth.traducirError(null).length > 0, 'ni siquiera con null');
});

// ============================== Imágenes ================================== //
// Una foto de handheld son varios MB; en base64 por el proxy, bastante más.
// Es lo que agotaba el tiempo al registrar un PNC.
const imagen = await cargar('imagen.js');

await test('medidas limita el lado mayor sin deformar', () => {
  eq(imagen.medidas(4000, 3000), { ancho: 1600, alto: 1200 }, 'horizontal');
  eq(imagen.medidas(3000, 4000), { ancho: 1200, alto: 1600 }, 'vertical');
  eq(imagen.medidas(4000, 4000), { ancho: 1600, alto: 1600 }, 'cuadrada');
});

await test('medidas nunca agranda una foto pequeña', () => {
  eq(imagen.medidas(800, 600), { ancho: 800, alto: 600 });
  eq(imagen.medidas(1600, 1200), { ancho: 1600, alto: 1200 }, 'justo en el límite');
});

await test('medidas aguanta una imagen sin dimensiones', () => {
  eq(imagen.medidas(0, 0), { ancho: 0, alto: 0 });
  eq(imagen.medidas(undefined, undefined), { ancho: 0, alto: 0 });
});

await test('tamanoLegible se lee de un vistazo', () => {
  eq(imagen.tamanoLegible(512), '512 B');
  eq(imagen.tamanoLegible(2048), '2 KB');
  eq(imagen.tamanoLegible(350 * 1024), '350 KB');
  eq(imagen.tamanoLegible(6 * 1024 * 1024), '6,0 MB');
  eq(imagen.tamanoLegible(0), '0 B');
  eq(imagen.tamanoLegible(undefined), '0 B');
});

// ====================== El archivo no crece ============================== //
// La regla es literal y no admite excepciones: entren 1, 22, 30 o 300 filas,
// salen las mismas. Todo lo demás —destinos, posiciones, desgloses— va dentro
// de una celda.
await test('el informe entrega exactamente las filas que entraron', () => {
  for (const n of [1, 2, 3, 22, 30, 100, 207]) {
    const lineas = [...Array(n)].map((_, i) => ({
      linea: i + 1, sku: 'SKU' + (i % 7), cantidad: (i % 4) + 1,
    }));
    const totales = {};
    lineas.forEach((l) => { totales[l.sku] = (totales[l.sku] || 0) + l.cantidad * 2; });
    eq(informe.repartirPorLinea(lineas, totales).length, n, `con ${n} filas`);
  }
});

await test('un SKU repartido entre pallet y posición no abre filas nuevas', () => {
  // 7 unidades: 5 quedan en el pallet B04 y 2 van directas a su posición.
  const lineas = [{ linea: 1, sku: 'A', cantidad: 7 }];
  const r = informe.repartirPorLinea(lineas, { A: 7 });
  eq(r.length, 1, 'sigue siendo una fila');
  eq(r[0].fisica, 7, 'con el total, venga de donde venga');
});

// ================ Cómo se escribe el conteo ============================== //
// `set()` con `merge` usa las claves TAL CUAL: 'pallets.A1' crea un campo que se
// llama literalmente «pallets.A1» en la raíz, no una entrada dentro del mapa.
// Solo `update()` interpreta el punto como separador. El síntoma era mudo: el
// total subía y la columna de pallets salía vacía — y con ella la sugerencia de
// dónde está ya ese SKU, que es la mitad del trabajo de buscar algo.
function escrituraDe(ruta) {
  return (globalThis.__escrituras || []).find((e) => (e.ruta || '').includes(ruta));
}

await test('el pallet se escribe DENTRO del mapa, no como clave con punto', async () => {
  globalThis.__documentos = {
    'recepciones/R1': { estado: 'EN_VALIDACION' },
    'recepciones/R1/skus/A': { sku: 'A', esperado: 10, contado: 0, enPackingList: true },
  };
  await conteo.registrarConteo('R1', { uid: 'u1', email: 'o@itsanet.com' }, {
    sku: 'A', cantidad: 5, pallet: 'C1', idempotencyKey: 'k1',
  });

  const w = escrituraDe('skus/A');
  ok(w, 'debe escribir el agregado del SKU');
  ok(w.datos.pallets, 'tiene que existir el mapa `pallets`');
  eq(Object.keys(w.datos.pallets), ['C1']);
  eq(w.datos.pallets.C1.__inc, 5, 'y dentro, el incremento');
  ok(!Object.keys(w.datos).some((k) => k.includes('.')),
     'ninguna clave con punto: ' + Object.keys(w.datos).join(', '));
});

await test('el subpallet se codifica para no romper el mapa', async () => {
  globalThis.__documentos = {
    'recepciones/R1': { estado: 'EN_VALIDACION' },
    'recepciones/R1/skus/A': { sku: 'A', esperado: 10, contado: 0, enPackingList: true },
  };
  await conteo.registrarConteo('R1', { uid: 'u1', email: 'o@itsanet.com' }, {
    sku: 'A', cantidad: 2, pallet: 'B04.1', idempotencyKey: 'k2',
  });
  const w = escrituraDe('skus/A');
  eq(Object.keys(w.datos.pallets), ['B04~1']);
  // Y al leerlo vuelve a ser el pallet que escribió el operario.
  eq(conteo.ubicacionesDe({ pallets: { 'B04~1': 2 } }), [{ pallet: 'B04.1', cantidad: 2 }]);
});

await test('anular descuenta del mismo pallet, también anidado', async () => {
  globalThis.__documentos = {
    'recepciones/R1': { estado: 'EN_VALIDACION' },
    'recepciones/R1/eventos/e1': { sku: 'A', cantidad: 5, pallet: 'C1', tipo: 'CONTEO' },
    'recepciones/R1/skus/A': { sku: 'A', esperado: 10, contado: 5, verificado: true },
  };
  await conteo.anularConteo('R1', { uid: 'u1', email: 'o@itsanet.com' }, 'e1', 'se contó doble');
  const w = escrituraDe('skus/A');
  eq(w.datos.pallets.C1.__inc, -5);
});

// ============== Consolidar varios packing lists ========================== //
// Validar dos embarques cortos a la vez ahorra recorrer el almacen dos veces,
// pero cada lista tiene que entregar SUS filas: 22 y 7, nunca 29 mezcladas.
await test('cada lista reparte solo contra sus propias líneas', () => {
  const lineasA = [
    { linea: 1, sku: 'X', cantidad: 5, origen: 'PL-A', orden: 1 },
    { linea: 2, sku: 'Y', cantidad: 3, origen: 'PL-A', orden: 2 },
  ];
  const lineasB = [
    { linea: 1, sku: 'Z', cantidad: 4, origen: 'PL-B', orden: 3 },
  ];

  const a = informe.repartirPorLinea(lineasA, { X: 5, Y: 1 });
  const b = informe.repartirPorLinea(lineasB, { Z: 4 });

  eq(a.length, 2, 'la lista A entrega sus dos filas');
  eq(b.length, 1, 'la lista B entrega su fila');
  eq(a.map((l) => l.fisica), [5, 1]);
  eq(b[0].fisica, 4);
  // Y nada de B aparece en A.
  ok(!a.some((l) => l.sku === 'Z'));
});

// Excel rechaza el archivo entero si una hoja pasa de 31 caracteres o lleva
// alguno de los caracteres prohibidos: el informe no se abriría.
await test('el nombre de la hoja respeta lo que Excel admite', () => {
  eq(informe.nombreDeHoja('PL-A'), 'PL-A');
  eq(informe.nombreDeHoja('PACKING-LIST-DEMASIADO-LARGO-PARA-EXCEL').length, 31);
  eq(informe.nombreDeHoja('RB/48529'), 'RB-48529', 'la barra está prohibida');
  eq(informe.nombreDeHoja('A:B\\C?D*E[F]'), 'A-B-C-D-E-F-');
  eq(informe.nombreDeHoja(''), 'LISTA');
  eq(informe.nombreDeHoja(null), 'LISTA');
});

// ====== Atribución entre packing lists: dato, no suposición ============== //
await test('lo imputado a cada lista se reparte dentro de esa lista', () => {
  // X está en las dos listas: 5 en PL-A y 4 en PL-B. El operario imputó 5 a
  // PL-A y 2 a PL-B al registrar.
  const a = informe.repartirPorLinea(
    [{ linea: 1, sku: 'X', cantidad: 5, origen: 'PL-A' }], { X: 5 });
  const b = informe.repartirPorLinea(
    [{ linea: 1, sku: 'X', cantidad: 4, origen: 'PL-B' }], { X: 2 });

  eq(a[0].fisica, 5, 'PL-A cuadra');
  eq(a[0].diferencia, 0);
  eq(b[0].fisica, 2, 'PL-B tiene su propio faltante');
  eq(b[0].diferencia, -2);
  // Y cada lista sigue entregando una fila.
  eq(a.length + b.length, 2);
});

// El registro de un conteo guarda a qué lista se imputa, para que el informe no
// tenga que adivinarlo.
await test('el conteo guarda la lista elegida y la suma en su propio mapa', async () => {
  globalThis.__documentos = {
    'recepciones/R1': { estado: 'EN_VALIDACION' },
    'recepciones/R1/skus/X': {
      sku: 'X', esperado: 9, contado: 0, enPackingList: true,
      origenes: ['PL-A', 'PL-B'],
    },
  };
  await conteo.registrarConteo('R1', { uid: 'u1', email: 'o@itsanet.com' }, {
    sku: 'X', cantidad: 5, pallet: 'A1', origen: 'PL-A', idempotencyKey: 'ko1',
  });

  const evento = (globalThis.__escrituras || []).find((e) => e.ruta.includes('eventos/'));
  eq(evento.datos.origen, 'PL-A');

  const agregado = (globalThis.__escrituras || []).find((e) => e.ruta.includes('skus/X'));
  eq(agregado.datos.porOrigen['PL-A'].__inc, 5);
});

await test('sin varias listas no se guarda imputación: no hay nada que decidir', async () => {
  globalThis.__documentos = {
    'recepciones/R1': { estado: 'EN_VALIDACION' },
    'recepciones/R1/skus/X': { sku: 'X', esperado: 9, contado: 0, enPackingList: true },
  };
  await conteo.registrarConteo('R1', { uid: 'u1', email: 'o@itsanet.com' }, {
    sku: 'X', cantidad: 3, pallet: 'A1', idempotencyKey: 'ko2',
  });
  const agregado = (globalThis.__escrituras || []).find((e) => e.ruta.includes('skus/X'));
  ok(!agregado.datos.porOrigen, 'no debe inventarse una lista');
});

// Al volver a escanear el mismo producto para otro pallet, hay que ver qué se
// hizo antes: de qué lista salió, dónde quedó y cuándo.
await test('registrosDe resume lo ya hecho con ese producto', () => {
  const t = (min) => ({ toDate: () => new Date(2026, 9, 14, 10, min) });
  const previos = conteo.registrosDe([
    { id: 'e1', sku: 'X', cantidad: 5, pallet: 'A1', origen: 'PL-A',
      operadorNombre: 'Juan Pérez', creadoEn: t(10) },
    { id: 'e2', sku: 'X', cantidad: 2, pallet: 'B04', origen: 'PL-B',
      operadorNombre: 'Ana Torres', creadoEn: t(30) },
    { id: 'e3', sku: 'OTRO', cantidad: 9, pallet: 'C1', creadoEn: t(20) },
  ], 'X');

  eq(previos.length, 2, 'solo los de ese SKU');
  eq(previos[0].pallet, 'B04', 'el más reciente primero');
  eq(previos.map((r) => r.origen), ['PL-B', 'PL-A']);
});

await test('registrosDe no cuenta lo anulado', () => {
  const previos = conteo.registrosDe([
    { id: 'e1', sku: 'X', cantidad: 5, pallet: 'A1' },
    { id: 'anula-e1', sku: 'X', cantidad: -5, pallet: 'A1',
      tipo: 'ANULACION', refEvento: 'e1' },
  ], 'X');
  eq(previos.length, 0, 'ni el original ni la reversa');
});

// ============ El catálogo viejo y el nuevo dicen lo mismo ================ //
// La ficha decía «sin existencia en bodega» mientras la línea de arriba
// mostraba «Pos. BM-BB-01-5». Dos afirmaciones contrarias en la misma pantalla,
// porque el catálogo descargado era anterior al array de posiciones.
await test('un catálogo antiguo sigue dando su ubicación', () => {
  eq(datos.ubicacionesDepot({ posicion: 'BM-BB-01-5', stock: 6 }),
     [{ posicion: 'BM-BB-01-5', stock: 6 }]);
});

await test('el catálogo nuevo manda sobre el campo suelto', () => {
  const u = datos.ubicacionesDepot({
    posicion: 'VIEJA', stock: 1,
    posiciones: [{ posicion: 'A-01', stock: 4 }, { posicion: 'B-07', stock: 6 }],
  });
  eq(u.length, 2);
  eq(u.map((x) => x.posicion), ['A-01', 'B-07']);
});

await test('sin ubicación en ninguno de los dos formatos, la lista va vacía', () => {
  eq(datos.ubicacionesDepot({ stock: 0 }), []);
  eq(datos.ubicacionesDepot({ posiciones: [] }), []);
  eq(datos.ubicacionesDepot({ posiciones: [{ posicion: '', stock: 3 }] }), [],
     'una fila sin posición no es una ubicación');
  eq(datos.ubicacionesDepot(null), []);
});

// ========================= La cámara ===================================== //
const camara = await cargar('camara.js');

/** Node trae su propio `navigator` de solo lectura; aquí se sustituye entero. */
function conEntorno(window, mediaDevices, fn) {
  const antesW = Object.getOwnPropertyDescriptor(globalThis, 'window');
  const antesN = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
  Object.defineProperty(globalThis, 'window', { value: window, configurable: true });
  Object.defineProperty(globalThis, 'navigator', {
    value: { mediaDevices }, configurable: true,
  });
  try { fn(); } finally {
    if (antesW) Object.defineProperty(globalThis, 'window', antesW);
    else delete globalThis.window;
    if (antesN) Object.defineProperty(globalThis, 'navigator', antesN);
  }
}

// Donde no hay lector en el navegador se dice y se sigue con la pistola, que es
// lo que ya funciona; no se carga un motor de respaldo de 800 KB por el camino.
await test('sin BarcodeDetector la cámara no se ofrece, y se explica', () => {
  conEntorno({}, { getUserMedia: () => {} }, () => {
    ok(!camara.camaraDisponible());
    const m = camara.motivoNoDisponible();
    ok(/Chrome/i.test(m) && /pistola|escribe/i.test(m), 'tiene que decir qué hacer: ' + m);
  });
});

await test('sin acceso a la cámara se explica que hace falta HTTPS', () => {
  conEntorno({ BarcodeDetector: function () {} }, undefined, () => {
    ok(!camara.camaraDisponible());
    ok(/HTTPS/i.test(camara.motivoNoDisponible()), camara.motivoNoDisponible());
  });
});

await test('con las dos cosas, se ofrece y no hay nada que explicar', () => {
  conEntorno({ BarcodeDetector: function () {} }, { getUserMedia: () => {} }, () => {
    ok(camara.camaraDisponible());
    eq(camara.motivoNoDisponible(), '');
  });
});

// ====================== El vocabulario ================================== //
// «Unid. sistema» no le dice nada a quien esta delante de un pallet. Si el
// glosario y las pantallas se separan, acaban conviviendo dos palabras para lo
// mismo y nadie sabe si significan igual.
const glosario = await cargar('glosario.js');

await test('cada término tiene nombre y explicación', () => {
  const todos = glosario.listaGlosario();
  ok(todos.length >= 10, 'son ' + todos.length);
  for (const t of todos) {
    ok(t.titulo && t.titulo.length > 2, JSON.stringify(t));
    ok(t.ayuda && t.ayuda.length > 20, 'sin explicación útil: ' + t.titulo);
  }
});

await test('están los términos que más confunden', () => {
  for (const clave of ['declarado', 'contado', 'verificado', 'pallet',
                       'posicionReal', 'sinBuscar', 'noAparecio', 'pnc',
                       'adicional', 'codigoRecepcion']) {
    ok(glosario.TERMINOS[clave], 'falta ' + clave);
  }
});

// El panel va FUERA de las tarjetas. Un «?» dentro de cada una descuadraba las
// alturas, y la fila de indicadores —que es lo que se mira de un vistazo—
// dejaba de leerse de un vistazo.
await test('el panel incluye los términos pedidos, y solo esos', () => {
  const h = glosario.panelGlosario(['declarado', 'contado']);
  ok(h.includes('Declarado') && h.includes('Contado'), h);
  ok(!h.includes('PNC'), 'no debe colar términos que no se pidieron');
  ok(h.includes('class="glosario"'));
});

await test('el panel ignora términos que no existen', () => {
  const h = glosario.panelGlosario(['declarado', 'inventado']);
  ok(h.includes('Declarado'));
  ok(!h.includes('undefined'), h);
});

await test('sin lista, el panel los trae todos', () => {
  const h = glosario.panelGlosario();
  ok(h.includes('Declarado') && h.includes('PNC') && h.includes('Pallet'));
});

// =============== Packing lists duplicados =============================== //
// El mismo archivo llega dos veces con nombres distintos y se valida dos veces:
// el trabajo se duplica y los informes se contradicen.
const huella = await cargar('huella.js');

const pl = (lineas, unidades) => ({
  lineas: lineas.map(([sku, cantidad], i) => ({ linea: i + 1, sku, cantidad })),
  porSku: Object.fromEntries(lineas.map(([sku, c]) => [sku, c])),
  unidades: unidades ?? lineas.reduce((a, [, c]) => a + c, 0),
});

await test('la huella no cambia si el archivo se renombra', () => {
  const a = huella.resumenDe(pl([['X', 5], ['Y', 3]]), 'VW-29-06.xlsx');
  const b = huella.resumenDe(pl([['X', 5], ['Y', 3]]), 'copia de VW (2).xlsx');
  eq(a.huella, b.huella);
  eq(huella.comparar(a, b).nivel, 'identico');
});

await test('la huella no cambia si las filas vienen en otro orden', () => {
  const a = huella.huellaDe(pl([['X', 5], ['Y', 3]]));
  const b = huella.huellaDe(pl([['Y', 3], ['X', 5]]));
  eq(a, b, 'dos exportaciones del mismo pedido pueden ordenar distinto');
});

await test('cambiar una cantidad cambia la huella', () => {
  const a = huella.huellaDe(pl([['X', 5], ['Y', 3]]));
  const b = huella.huellaDe(pl([['X', 6], ['Y', 3]]));
  ok(a !== b, 'no puede dar lo mismo: no es el mismo pedido');
});

await test('cambiar un producto cambia la huella', () => {
  ok(huella.huellaDe(pl([['X', 5]])) !== huella.huellaDe(pl([['Z', 5]])));
});

await test('mismas cifras pero distinto contenido es «probable», no «idéntico»', () => {
  // Mismas líneas, mismos productos, mismas unidades, pero repartidas distinto.
  const a = huella.resumenDe(pl([['X', 5], ['Y', 3]]), 'a.xlsx');
  const b = huella.resumenDe(pl([['X', 3], ['Y', 5]]), 'b.xlsx');
  const r = huella.comparar(a, b);
  eq(r.nivel, 'probable');
  ok(r.motivos.length >= 3, r.motivos.join(', '));
});

await test('el mismo nombre de archivo basta para pedir que lo revisen', () => {
  const a = huella.resumenDe(pl([['X', 5]]), 'GAC-01-06.xlsx');
  const b = huella.resumenDe(pl([['A', 1], ['B', 2], ['C', 3]]), 'GAC-01-06 (1).xlsx');
  eq(huella.comparar(a, b).nivel, 'revisar');
});

await test('dos packing lists de verdad distintos no se parecen', () => {
  const a = huella.resumenDe(pl([['X', 5], ['Y', 3]]), 'uno.xlsx');
  const b = huella.resumenDe(pl([['A', 1], ['B', 2], ['C', 9], ['D', 4]]), 'otro.xlsx');
  eq(huella.comparar(a, b).nivel, 'distinto');
});

await test('nombreLimpio quita la extensión y el «(2)» de las descargas', () => {
  eq(huella.nombreLimpio('VW-29-06-2026.xlsx'), 'VW-29-06-2026');
  eq(huella.nombreLimpio('VW-29-06-2026 (2).xlsx'), 'VW-29-06-2026');
  eq(huella.nombreLimpio('lista.XLSM'), 'LISTA');
  eq(huella.nombreLimpio(''), '');
  eq(huella.nombreLimpio(null), '');
});

await test('comparar aguanta que falte uno de los dos', () => {
  eq(huella.comparar(null, {}).nivel, 'distinto');
  eq(huella.comparar({}, null).nivel, 'distinto');
});

// =============== Sugerir códigos parecidos ============================== //
// REC0260002 y REC026002 son recepciones distintas a un dígito de distancia.
const sug = await cargar('sugerir.js');

await test('normalizar ignora guiones, espacios y mayúsculas', () => {
  eq(sug.normalizar('rec-026 002'), 'REC026002');
  eq(sug.normalizar(null), '');
});

await test('la distancia cuenta el dígito de más', () => {
  eq(sug.distancia('REC026002', 'REC0260002'), 1);
  eq(sug.distancia('ABC', 'ABC'), 0);
  eq(sug.distancia('', 'ABC'), 3);
  eq(sug.distancia('ABC', ''), 3);
});

await test('lo que se va tecleando encuentra el código entero', () => {
  const codigos = ['REC0260002', 'REC0260004', 'GYL20261013'];
  eq(sug.parecidos('REC026', codigos)[0], 'REC0260002');
  eq(sug.parecidos('gyl', codigos).length, 1);
});

await test('un dígito mal escrito sigue encontrando el código', () => {
  const codigos = ['REC0260002', 'GYL20261013'];
  const cerca = sug.parecidos('REC026002', codigos, { minimo: 0.5 });
  eq(cerca[0], 'REC0260002', 'un dígito de más no puede dar «sin resultados»');
});

await test('el código exacto manda sobre el que solo empieza igual', () => {
  const codigos = ['REC0260002', 'REC026'];
  eq(sug.parecidos('REC026', codigos)[0], 'REC026');
});

await test('sin texto devuelve los primeros, no nada', () => {
  eq(sug.parecidos('', ['A', 'B', 'C'], { max: 2 }).length, 2,
     'un campo recién abierto enseña lo que hay');
});

await test('busca dentro de objetos y los devuelve enteros', () => {
  // Lo que se busca es la recepción, no su código: hay que poder abrirla.
  const recs = [{ id: '1', codigo: 'REC0260002' }, { id: '2', codigo: 'GYL2026' }];
  const r = sug.parecidos('REC026', recs, { clave: (x) => x.codigo });
  eq(r.length, 1);
  eq(r[0].id, '1');
  eq(r[0].codigo, 'REC0260002');
});

await test('no sugiere nada cuando lo escrito ya existe tal cual', () => {
  eq(sug.avisoDeParecidos('REC0260002', ['REC0260002', 'REC0260004']), '');
});

await test('avisa del parecido cuando el código no existe', () => {
  const t = sug.avisoDeParecidos('REC026002', ['REC0260002', 'GYL2026']);
  ok(t.includes('REC0260002'), t);
});

await test('no inventa parecidos donde no los hay', () => {
  eq(sug.avisoDeParecidos('ZZZZ999', ['REC0260002', 'GYL2026']), '');
  eq(sug.avisoDeParecidos('', ['REC0260002']), '');
});

// =============== Avisar de que el packing list ya se cargó ============== //
const datosH = await cargar('datos.js');

const conHuellas = (filas) => { globalThis.__coleccion = { huellas: filas }; };
const huellaDe = (lineas, archivo) => ({
  ...huella.resumenDe(pl(lineas), archivo),
});

await test('reconoce el mismo packing list en otra recepción', async () => {
  conHuellas([{ id: 'REC001__PRINCIPAL', recepcionId: 'REC001', codigo: 'REC0260002',
                origen: 'PRINCIPAL', ...huellaDe([['X', 5], ['Y', 3]], 'vw.xlsx') }]);
  const r = await datosH.buscarPackingListParecido(pl([['X', 5], ['Y', 3]]),
                                                   'copia de vw (2).xlsx');
  eq(r.length, 1);
  eq(r[0].nivel, 'identico');
  eq(r[0].codigo, 'REC0260002', 'tiene que decir EN QUÉ recepción está');
});

await test('no se avisa a sí misma: la recepción en curso se excluye', async () => {
  conHuellas([{ id: 'REC001__PRINCIPAL', recepcionId: 'REC001', codigo: 'REC0260002',
                origen: 'PRINCIPAL', ...huellaDe([['X', 5]], 'vw.xlsx') }]);
  const r = await datosH.buscarPackingListParecido(pl([['X', 5]]), 'vw.xlsx',
                                                   { excluirRecepcion: 'REC001' });
  eq(r.length, 0);
});

await test('un packing list distinto no levanta ninguna alarma', async () => {
  conHuellas([{ id: 'REC001__PRINCIPAL', recepcionId: 'REC001', codigo: 'REC0260002',
                origen: 'PRINCIPAL', ...huellaDe([['X', 5], ['Y', 3]], 'vw.xlsx') }]);
  const r = await datosH.buscarPackingListParecido(
    pl([['A', 1], ['B', 2], ['C', 3], ['D', 4]]), 'gac.xlsx');
  eq(r.length, 0, 'avisar de más entrena al operario a ignorar el aviso');
});

await test('lo idéntico se ofrece antes que lo parecido', async () => {
  conHuellas([
    { id: 'R2__P', recepcionId: 'R2', codigo: 'PARECIDA', origen: 'P',
      ...huellaDe([['X', 4], ['Y', 4]], 'otro.xlsx') },      // mismas cifras
    { id: 'R3__P', recepcionId: 'R3', codigo: 'IDENTICA', origen: 'P',
      ...huellaDe([['X', 5], ['Y', 3]], 'otro.xlsx') },      // mismo contenido
  ]);
  const r = await datosH.buscarPackingListParecido(pl([['X', 5], ['Y', 3]]), 'nuevo.xlsx');
  eq(r[0].codigo, 'IDENTICA');
  eq(r[0].nivel, 'identico');
  eq(r[1].nivel, 'probable');
});

await test('sin huellas guardadas, cargar sigue funcionando', async () => {
  globalThis.__coleccion = {};
  eq((await datosH.buscarPackingListParecido(pl([['X', 1]]), 'a.xlsx')).length, 0);
});

await test('si la consulta falla, no impide cargar el packing list', async () => {
  globalThis.__coleccion = null;
  const r = await datosH.buscarPackingListParecido(pl([['X', 1]]), 'a.xlsx');
  eq(r.length, 0, 'el aviso es una ayuda, no un requisito para trabajar');
});

await test('al guardar el packing list queda su huella para la próxima vez', async () => {
  globalThis.__coleccion = {};
  globalThis.__sets = [];
  await datosH.guardarPackingList('REC0260002', {
    ...pl([['X', 5], ['Y', 3]]),
    encabezados: ['ITEM', 'CANTIDAD'], columnas: {}, hoja: 'REV', embarques: [],
    skusUnicos: 2, unidades: 8,
  }, null, { origen: 'PL-A', archivo: 'VW-29-06-2026.xlsx' });

  const h = globalThis.__sets.find((x) => x.ruta.startsWith('huellas/'));
  ok(h, 'sin esta anotación el duplicado no se detecta nunca');
  eq(h.ruta, 'huellas/REC0260002__PL-A');
  eq(h.datos.recepcionId, 'REC0260002');
  eq(h.datos.origen, 'PL-A');
  eq(h.datos.archivo, 'VW-29-06-2026', 'el nombre, sin extensión ni «(2)»');
  eq(h.datos.lineas, 2);
  eq(h.datos.huella, huella.huellaDe(pl([['X', 5], ['Y', 3]])));
});

await test('«PL-A» no se guarda como «PLA»: el guion separa listas', async () => {
  globalThis.__sets = [];
  await datosH.guardarPackingList('R1', {
    ...pl([['X', 1]]), encabezados: [], columnas: {}, hoja: '', embarques: [],
    skusUnicos: 1, unidades: 1,
  }, null, { origen: 'PL-A', archivo: 'a.xlsx' });
  const h = globalThis.__sets.find((x) => x.ruta.startsWith('huellas/'));
  eq(h.ruta, 'huellas/R1__PL-A');
});

// =============== CSV de alta masiva hacia Depot ========================= //
const csv = await cargar('csv.js');
const CANT = csv.FORMATOS_BASE[0];
const sinBom = (t) => t.replace('﻿', '').trim().split('\r\n');

await test('la plantilla vacía trae solo los encabezados', () => {
  const lineas = sinBom(csv.plantilla(CANT));
  eq(lineas.length, 1);
  ok(lineas[0].startsWith('CODIGO PRODUCTO,CANTIDAD,CODIGO UNIDAD'), lineas[0]);
});

await test('lleva BOM: sin él Excel rompe las tildes', () => {
  ok(csv.plantilla(CANT).startsWith('﻿'));
});

await test('una descripción con el separador no parte la fila', () => {
  // Una coma suelta partía la fila en dos y Depot rechazaba el archivo entero.
  eq(csv.celda('TORNILLO; HEXAGONAL', ';'), '"TORNILLO; HEXAGONAL"');
  eq(csv.celda('DE 1" NPT', ';'), '"DE 1"" NPT"');
  eq(csv.celda('NORMAL', ';'), 'NORMAL');
  eq(csv.celda(null, ';'), '');
  eq(csv.celda(0, ';'), '0');
});

await test('la posición se parte en nave, calle, columna y nivel', () => {
  eq(csv.partesDePosicion('A-01-03-2'),
     { nave: 'A', calle: '01', columna: '03', nivel: '2', profundidad:'' });
  eq(csv.partesDePosicion(''), { nave: '', calle: '', columna: '', nivel: '', profundidad:'' });
  eq(csv.partesDePosicion('A-01'), { nave: 'A', calle: '01', columna: '', nivel: '', profundidad:'' });
});

await test('cada sitio donde se dejó mercadería es una fila', () => {
  // De 30 unidades pueden ir 12 a una posición real y 18 a un pallet: cargarlo
  // como una sola fila mete en el sistema algo que no está donde dice.
  const filas = csv.agruparConteos([
    { id: '1', sku: 'X', cantidad: 12, pallet: 'A1', posicionReal: 'A-01-03-2' },
    { id: '2', sku: 'X', cantidad: 18, pallet: 'B04', posicionReal: '' },
  ]);
  eq(filas.length, 2);
  eq(filas.map((f) => f.cantidad).reduce((a, b) => a + b, 0), 30);
  eq(filas[0].posicion, 'A-01-03-2', 'lo que ya tiene posición real va primero');
  eq(filas[1].pallet, 'B04', 'lo que queda por ubicar, detrás');
});

await test('dos conteos en el mismo sitio se suman en una fila', () => {
  const filas = csv.agruparConteos([
    { id: '1', sku: 'X', cantidad: 5, pallet: 'A1', posicionReal: 'A-01' },
    { id: '2', sku: 'X', cantidad: 7, pallet: 'A1', posicionReal: 'A-01' },
  ]);
  eq(filas.length, 1);
  eq(filas[0].cantidad, 12);
});

await test('un conteo anulado no se carga', () => {
  // La anulación no guarda la posición: restarla dejaría la cantidad bien y el
  // sitio mal. Se descarta el conteo entero.
  const filas = csv.agruparConteos([
    { id: 'e1', sku: 'X', cantidad: 9, pallet: 'A1', posicionReal: 'A-01' },
    { id: 'e2', sku: 'X', cantidad: 4, pallet: 'B1', posicionReal: 'B-02' },
    { id: 'anula-e1', sku: 'X', cantidad: -9, pallet: 'A1', tipo: 'ANULACION' },
  ]);
  eq(filas.length, 1);
  eq(filas[0].pallet, 'B1');
  eq(filas[0].cantidad, 4);
});

await test('un «no apareció» no entra: cargar 0 no es cargar nada', () => {
  eq(csv.agruparConteos([{ id: '1', sku: 'X', cantidad: 0, tipo: 'CERO' }]).length, 0);
});

await test('el CSV de cantidades sale con una fila por sitio', () => {
  const r = csv.csvDeCantidades(CANT, {
    recepcion: { codigo: 'REC0260002', cliente: 'VENTURA' },
    skus: [{ sku: 'X', descripcion: 'ARANDELA' }],
    eventos: [
      { id: '1', sku: 'X', cantidad: 12, pallet: 'A1', posicionReal: 'A-01-03-2' },
      { id: '2', sku: 'X', cantidad: 18, pallet: 'B04', posicionReal: '' },
    ],
  });
  eq(r.filas, 2);
  eq(r.nombre, 'alta-cantidades-REC0260002.csv');
  const l = sinBom(r.texto);
  eq(l.length, 3, 'encabezado y dos filas');
  eq(l[1].split(',').length,18);
  eq(l[1].split(',').slice(0,6),['X','12','','','','A1']);
  eq(l[1].split(',').slice(9,13),['A','01','03','2']);
  eq(l[2].split(',').slice(0,6),['X','18','','','','B04']);
  ok(r.incidencias.some(i=>i.encabezado==='CODIGO UNIDAD'));
});

await test('el de productos nuevos sale de los adicionales', () => {
  const r = csv.csvDeProductos(csv.FORMATOS_BASE[1], {
    recepcion: { codigo: 'R1', cliente: 'VENTURA' },
    adicionales: [{ sku: 'NUEVO', descripcion: 'PIEZA', fisica: 3 }],
  });
  eq(r.filas, 1);
  const fila=sinBom(r.texto)[1].split(',');eq(fila.length,38);
  eq(fila.slice(0,4),['VENTURA','NUEVO','','PIEZA']);
  eq(fila[9],'','FAMILIA no se inventa');
  eq(fila[17],'NO','Tipo de producto segun definicion oficial');
});

await test('sin adicionales sale la plantilla sola, no un archivo roto', () => {
  const r = csv.csvDeProductos(csv.FORMATOS_BASE[1], { recepcion: {}, adicionales: [] });
  eq(r.filas, 0);
  eq(sinBom(r.texto).length, 1);
});

await test('un formato guardado a medias se completa con el de base', () => {
  const f = csv.normalizarFormato({ id: 'CANTIDADES', columnas: [] });
  eq(f.columnas.length, CANT.columnas.length);
  eq(f.separador, ',');
});

await test('el administrador puede cambiar columnas y separador', () => {
  const t = csv.plantilla({
    columnas: [{ encabezado: 'CODIGO', campo: 'sku' }, { encabezado: 'CANT', campo: 'cantidad' }],
    separador: ',',
  });
  eq(sinBom(t)[0], 'CODIGO,CANT');
});

// =============== Cómo se llaman las cosas en Drive ====================== //
// Un archivo llamado «validacion.xlsx» es inencontrable a los tres meses, y es
// justo lo que hay que sacar cuando alguien reclama.
const nom = await cargar('nombres.js');
const REC = { codigo: 'REC0260002', cliente: 'VENTURA', creadoEn: '2026-03-01T13:00:00Z' };

await test('la carpeta empieza por la fecha, para que Drive la ordene sola', () => {
  eq(nom.carpetaDeRecepcion(REC), '2026-03-01_VENTURA_REC0260002');
});

await test('dos clientes el mismo día quedan separados', () => {
  const a = nom.carpetaDeRecepcion(REC);
  const b = nom.carpetaDeRecepcion({ ...REC, cliente: 'BELIA', codigo: 'REC0260003' });
  ok(a !== b);
  ok(a.startsWith('2026-03-01') && b.startsWith('2026-03-01'), 'las dos del mismo día');
});

await test('dos recepciones del mismo cliente el mismo día, también', () => {
  const a = nom.carpetaDeRecepcion(REC);
  const b = nom.carpetaDeRecepcion({ ...REC, codigo: 'REC0260003' });
  ok(a !== b, 'el código es lo único único de verdad');
});

await test('la fecha es la de la recepción, no la de hoy', () => {
  // Una recepción del viernes que se cierra el lunes pertenece al viernes: es
  // cuando llegó la mercadería.
  eq(nom.fechaDeRecepcion(REC), '2026-03-01');
  eq(nom.carpetaDeMes(REC), '2026-03');
});

await test('sin fecha no se rompe: usa la de hoy', () => {
  eq(nom.fechaDeRecepcion({}).length, 10);
  eq(nom.fechaDeRecepcion({ creadoEn: 'vaya texto' }).length, 10);
});

await test('entiende las fechas de Firestore', () => {
  const t = { toDate: () => new Date('2026-07-09T10:00:00Z') };
  eq(nom.fechaDeRecepcion({ creadoEn: t }), '2026-07-09');
});

await test('un código con barras no crea carpetas que no existen', () => {
  // «REC/02» en Drive no es un nombre: es una ruta.
  eq(nom.limpiarNombre('REC/0260002'), 'REC0260002');
  eq(nom.limpiarNombre('VW 29 06 2026'), 'VW-29-06-2026');
  eq(nom.limpiarNombre('  a??b  '), 'ab');
  eq(nom.limpiarNombre(null), '');
});

await test('una recepción con una sola lista da un informe sin sufijos', () => {
  eq(nom.nombreDeInforme(REC), '2026-03-01_VENTURA_REC0260002');
  eq(nom.nombreDeInforme(REC, { origen: 'PRINCIPAL' }), '2026-03-01_VENTURA_REC0260002');
});

await test('consolidada, cada lista tiene su archivo y se sabe cuál es', () => {
  // Quien recibe dos adjuntos no puede abrirlos para saber cuál es cuál.
  eq(nom.nombreDeInforme(REC, { origen: 'PL-A' }), '2026-03-01_VENTURA_REC0260002_PL-A');
  eq(nom.nombreDeInforme(REC, { origen: 'PL-B' }), '2026-03-01_VENTURA_REC0260002_PL-B');
});

await test('cerrar otra vez no pisa el informe que ya se entregó', () => {
  eq(nom.nombreDeInforme(REC, { version: 2 }), '2026-03-01_VENTURA_REC0260002_v2');
  eq(nom.nombreDeInforme(REC, { origen: 'PL-A', version: 3 }),
     '2026-03-01_VENTURA_REC0260002_PL-A_v3');
});

await test('el auditable se distingue del que se manda al cliente', () => {
  eq(nom.nombreDeInforme(REC, { auditable: true }),
     '2026-03-01_VENTURA_REC0260002_AUDITABLE');
});

await test('la foto lleva el código delante, para verificarla de un vistazo', () => {
  eq(nom.nombreDeFoto('2H0525345'), '2H0525345-1.jpg');
  eq(nom.nombreDeFoto('2H0525345', 2), '2H0525345-2.jpg');
  eq(nom.nombreDeFoto('2H0525345', 1, 'image/png'), '2H0525345-1.png');
  eq(nom.nombreDeFoto('', 1), 'SIN-CODIGO-1.jpg');
});

await test('la segunda foto de un producto se numera, no pisa a la primera', () => {
  eq(nom.siguienteFoto('ABC', []), 1);
  eq(nom.siguienteFoto('ABC', ['ABC-1.jpg']), 2);
  eq(nom.siguienteFoto('ABC', ['ABC-1.jpg', 'ABC-2.jpg']), 3);
});

await test('si se borró una foto intermedia, no se reutiliza su número', () => {
  // Reutilizar el 2 pisaría a la 3, que sí está.
  eq(nom.siguienteFoto('ABC', ['ABC-1.jpg', 'ABC-3.jpg']), 4);
});

await test('las fotos de otro producto no cuentan', () => {
  eq(nom.siguienteFoto('ABC', ['OTRO-1.jpg', 'ABCD-1.jpg']), 1);
});

// =============== Entrar con Google deja usuario ========================= //
// Quien entraba con Google quedaba sin nombre de usuario: al cerrar sesión, lo
// único que le dejaba volver era el propio botón, y quien no caía en eso se
// daba por bloqueado.
const autenticacion = await cargar('auth.js');

const googleUid = (uid, email) => ({ uid, email, displayName: 'Ana Torres',
  providerData: [{ providerId: 'google.com' }] });

await test('al entrar con Google por primera vez se reserva su alias', async () => {
  globalThis.__sets = [];
  globalThis.__documentos = {};
  await autenticacion.asegurarPerfil(googleUid('u1', 'atorres@itsanet.com'));

  const alias = globalThis.__sets.find((x) => x.ruta.startsWith('alias/'));
  ok(alias, 'sin alias no tiene usuario con el que volver');
  eq(alias.ruta, 'alias/atorres', 'sale de la parte del correo antes de la arroba');
  eq(alias.datos.email, 'atorres@itsanet.com');
  eq(alias.datos.uid, 'u1');
  eq(alias.datos.tipoAcceso, 'GOOGLE',
     'el alias sí se puede leer sin entrar: es lo que permite decir «entra con Google»');
});

await test('también se crea su perfil, activo', async () => {
  globalThis.__sets = [];
  const p = await autenticacion.asegurarPerfil(googleUid('u2', 'bespinoza@itsanet.com'));
  eq(p.activo, true);
  eq(p.tipoAcceso, 'GOOGLE');
  ok(globalThis.__sets.some((x) => x.ruta === 'usuarios/u2'));
});

await test('un correo de fuera del dominio no se da de alta solo', async () => {
  globalThis.__sets = [];
  let fallo = null;
  try { await autenticacion.asegurarPerfil(googleUid('u3', 'alguien@gmail.com')); }
  catch (e) { fallo = e.message; }
  ok(fallo, 'tiene que rechazarlo');
  ok(/Registrarse/.test(fallo), fallo);
  ok(!globalThis.__sets.some((x) => x.ruta.startsWith('alias/')), 'ni alias ni perfil');
});

await test('un correo demasiado corto no genera un alias inservible', async () => {
  globalThis.__sets = [];
  await autenticacion.asegurarPerfil(googleUid('u4', 'ab@itsanet.com'));
  ok(!globalThis.__sets.some((x) => x.ruta.startsWith('alias/')),
     'con menos de 3 caracteres no se reserva nada');
  ok(globalThis.__sets.some((x) => x.ruta === 'usuarios/u4'), 'el perfil sí');
});

// =============== El usuario que se elige al entrar con Google ============= //
// Dos agujeros juntos: la ficha no llevaba el campo `usuario` —en la lista de
// usuarios salia un guion y el supervisor no sabia a quien aprobaba— y a la
// persona no se le preguntaba nunca con que iba a entrar.

await test('la ficha de Google guarda el usuario, no solo el alias', async () => {
  globalThis.__sets = [];
  globalThis.__documentos = {};
  const p = await autenticacion.asegurarPerfil(googleUid('u5', 'ctorres@itsanet.com'));
  eq(p.usuario, 'ctorres', 'sin esto la lista de usuarios ensena un guion');
  const ficha = globalThis.__sets.find((x) => x.ruta === 'usuarios/u5');
  eq(ficha.datos.usuario, 'ctorres', 'y tiene que quedar escrito, no solo devuelto');
});

await test('si se le pregunta, manda lo que eligio la persona', async () => {
  globalThis.__sets = [];
  globalThis.__documentos = {};
  let preguntado = null;
  const p = await autenticacion.asegurarPerfil(
    googleUid('u6', 'daniel.mora@itsanet.com'),
    { pedirUsuario: async (datos) => { preguntado = datos; return { usuario: 'dmora', nombre: 'Daniel Mora' }; } },
  );
  eq(preguntado.sugerido, 'daniel.mora', 'la sugerencia va puesta: aceptar es un toque');
  eq(preguntado.email, 'daniel.mora@itsanet.com');
  eq(p.usuario, 'dmora');
  eq(p.nombre, 'Daniel Mora');
  ok(globalThis.__sets.some((x) => x.ruta === 'alias/dmora'), 'el alias es el elegido');
  ok(!globalThis.__sets.some((x) => x.ruta === 'alias/daniel.mora'), 'y no el derivado');
});

await test('un usuario ya cogido por otro no se le entrega', async () => {
  globalThis.__sets = [];
  globalThis.__documentos = { 'alias/jperez': { uid: 'otro', email: 'juan@itsanet.com' } };
  const p = await autenticacion.asegurarPerfil(
    googleUid('u7', 'jose.perez@itsanet.com'),
    { pedirUsuario: async () => ({ usuario: 'jperez' }) },
  );
  ok(p.usuario !== 'jperez', 'seria entregarle la entrada de otra persona');
  eq(p.usuario, 'jose.perez',
     'el derivado del correo es mejor segunda opcion que un jperez2: se lee y no se confunde');
});

await test('cancelar el dialogo no deja a nadie sin usuario', async () => {
  globalThis.__sets = [];
  globalThis.__documentos = {};
  const p = await autenticacion.asegurarPerfil(
    googleUid('u8', 'elena.vera@itsanet.com'),
    { pedirUsuario: async () => null },
  );
  eq(p.usuario, 'elena.vera', 'queda la sugerencia: sin usuario es peor');
});

await test('si el dialogo falla tampoco', async () => {
  globalThis.__sets = [];
  globalThis.__documentos = {};
  const p = await autenticacion.asegurarPerfil(
    googleUid('u9', 'fabian.luna@itsanet.com'),
    { pedirUsuario: async () => { throw new Error('se cerro la pantalla'); } },
  );
  eq(p.usuario, 'fabian.luna');
});

await test('a las fichas viejas sin usuario se les pone al volver a entrar', async () => {
  globalThis.__sets = [];
  globalThis.__documentos = {};
  const antes = { uid: 'u10', email: 'gloria.saa@itsanet.com', rol: 'OPERADOR', activo: true };
  const p = await autenticacion.completarPerfil(
    googleUid('u10', 'gloria.saa@itsanet.com'), antes);
  eq(p.usuario, 'gloria.saa');
  const ficha = globalThis.__sets.find((x) => x.ruta === 'usuarios/u10');
  ok(ficha?.opciones?.merge, 'se completa, no se reescribe la ficha entera');
});

await test('a quien ya tiene usuario no se le toca', async () => {
  globalThis.__sets = [];
  const p = await autenticacion.completarPerfil(
    googleUid('u11', 'hugo.paz@itsanet.com'),
    { usuario: 'hpaz', rol: 'ADMIN' });
  eq(p.usuario, 'hpaz');
  eq(globalThis.__sets.length, 0, 'ni una escritura por entrar');
});

// =============== El callejon sin salida de las dos puertas =============== //
// Una cuenta de acceso que existe sin ficha cerraba las dos puertas a la vez:
// la persona entraba y le decian «no estas dada de alta»; el administrador
// intentaba darla de alta y Firebase le decia «ya existe un usuario con ese
// correo». Ninguno de los dos podia hacer nada con esa frase.

const conClave = (uid, email, nombre = '') => ({
  uid, email, displayName: nombre,
  providerData: [{ providerId: 'password' }],
});

await test('quien entra con clave y no tiene ficha entra a la cola, no a un error', async () => {
  globalThis.__sets = [];
  globalThis.__documentos = {};
  const p = await autenticacion.asegurarPerfil(conClave('c1', 'dochoa@itsanet.com', 'Danny Ochoa'));
  eq(p.activo, false, 'una contrasena no verifica quien es nadie: la aprueba un supervisor');
  eq(p.rol, 'OPERADOR', 'nadie se elige su propio rol');
  eq(p.tipoAcceso, 'CLAVE');
  eq(p.nombre, 'Danny Ochoa');
  ok(globalThis.__sets.some((x) => x.ruta === 'usuarios/c1'), 'la ficha se escribe');
});

await test('y con su usuario puesto, no con un guion', async () => {
  globalThis.__sets = [];
  globalThis.__documentos = {};
  const p = await autenticacion.asegurarPerfil(conClave('c2', 'jperez@itsanet.com'));
  eq(p.usuario, 'jperez', 'sin esto sale «—» en la lista y no tiene nada que teclear');
  const alias = globalThis.__sets.find((x) => x.ruta === 'alias/jperez');
  eq(alias.datos.tipoAcceso, 'CLAVE', 'el alias dice con que se entra');
});

await test('a una ficha vieja sin usuario tambien se le pone, entre con lo que entre', async () => {
  globalThis.__sets = [];
  globalThis.__documentos = {};
  const p = await autenticacion.completarPerfil(
    conClave('c3', 'mruiz@itsanet.com'),
    { uid: 'c3', email: 'mruiz@itsanet.com', rol: 'OPERADOR', activo: true });
  eq(p.usuario, 'mruiz');
});

await test('el alta avisa de que la cuenta existe y por donde se sale', async () => {
  globalThis.__sets = [];
  globalThis.__documentos = {};
  globalThis.__fallarAlta = 'auth/email-already-in-use';
  let fallo = null;
  try {
    await autenticacion.crearOperario({
      usuario: 'dochoa', correo: 'dochoa@itsanet.com',
      clave: '123456', nombre: 'Danny Ochoa',
    });
  } catch (e) { fallo = e; }
  globalThis.__fallarAlta = null;
  ok(fallo, 'tiene que fallar: la cuenta ya existe');
  eq(fallo.code, 'CUENTA_EXISTENTE', 'con un codigo propio, para poder ofrecer la salida');
  eq(fallo.email, 'dochoa@itsanet.com');
  ok(/esperando aprobaci/i.test(fallo.message), fallo.message);
});

await test('el correo para poner contrasena se manda a quien toca', async () => {
  globalThis.__correos = [];
  eq(await autenticacion.enviarRestablecimiento(' Dochoa@Itsanet.COM '),
     'dochoa@itsanet.com', 'el correo se normaliza antes de mandarlo');
  eq(globalThis.__correos, ['dochoa@itsanet.com']);
});

await test('y no a cualquier cosa que parezca un correo', async () => {
  globalThis.__correos = [];
  let fallo = null;
  try { await autenticacion.enviarRestablecimiento('dochoa@itsanet'); }
  catch (e) { fallo = e.message; }
  ok(fallo, 'un dominio sin punto no es un buzon');
  eq(globalThis.__correos.length, 0);
});

resumen();
