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

await test('palletValido rechaza lo que rompería el informe', () => {
  ok(datos.palletValido('A1'));
  ok(datos.palletValido('B04.1'));
  ok(datos.palletValido('C12.3.4'));
  ok(!datos.palletValido(''), 'vacío');
  ok(!datos.palletValido('B04.'), 'punto final');
  ok(!datos.palletValido('A/1'), 'carácter especial');
  ok(!datos.palletValido('A'.repeat(41)), 'demasiado largo');
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
await test('estadoDe cubre los cuatro casos', () => {
  eq(datos.estadoDe(10, 0), 'PENDIENTE');
  eq(datos.estadoDe(10, 10), 'OK');
  eq(datos.estadoDe(10, 4), 'FALTANTE');
  eq(datos.estadoDe(10, 12), 'SOBRANTE');
  eq(datos.estadoDe(0, 0), 'OK', 'línea declarada en 0 y sin contar');
  eq(datos.estadoDe(0, 3), 'SOBRANTE', 'adicional');
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
  eq(r.unidadesEsperadas, 18);
  eq(r.unidadesFisicas, 23);
  eq(r.diferencia, 5);
  eq(r.adicionales, 1);
  eq(r.discrepancias.length, 4);
  eq(r.exactitud, 20);
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
await test('aCorreo completa el usuario suelto al dominio', () => {
  eq(auth.aCorreo('jperez'), 'jperez@itsanet.com');
  eq(auth.aCorreo('  JPerez  '), 'jperez@itsanet.com');
  eq(auth.aCorreo('jperez@itsanet.com'), 'jperez@itsanet.com');
  eq(auth.aCorreo('JPEREZ@ITSANET.COM'), 'jperez@itsanet.com', 'minúsculas');
  eq(auth.aCorreo(''), '', 'vacío sigue vacío, no "@itsanet.com"');
  eq(auth.aCorreo(null), '');
});

await test('aCorreo no toca un correo de otro dominio', () => {
  // Que lo rechace es tarea de dominioValido, no de aquí: completar a ciegas
  // convertiría «juan@gmail.com» en algo que parece corporativo.
  eq(auth.aCorreo('juan@gmail.com'), 'juan@gmail.com');
  ok(!auth.dominioValido('juan@gmail.com'));
  ok(auth.dominioValido('jperez@itsanet.com'));
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

resumen();
