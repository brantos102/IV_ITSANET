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

resumen();
