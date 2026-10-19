#!/usr/bin/env node
/**
 * El informe devuelve el packing list tal como llegó.
 *   node firebase/test/formato.test.mjs
 *
 * Se ejecuta contra los archivos REALES que el cliente manda a validar, no
 * contra un ejemplo inventado. Si el formato de salida deja de cuadrar con el
 * de entrada —una columna de más, otro encabezado, otro orden— quien recibe el
 * archivo tiene que rehacerlo a mano antes de subirlo al sistema, y eso no se
 * ve hasta que ya está enviado.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { cargar, test, eq, ok, resumen, estado } from './cargador.mjs';

const require = createRequire(import.meta.url);
const AQUI = path.dirname(fileURLToPath(import.meta.url));
const MUESTRAS = path.join(AQUI, 'muestras');

// SheetJS es lo que usa el navegador; aquí se carga el mismo paquete.
let XLSX;
try {
  XLSX = require('xlsx');
} catch {
  console.log('  · xlsx no instalado: `npm i -D xlsx` para ejecutar estas pruebas');
  process.exit(0);
}
globalThis.XLSX = XLSX;

const archivos = fs.existsSync(MUESTRAS)
  ? fs.readdirSync(MUESTRAS).filter((f) => f.endsWith('.xlsx'))
  : [];

if (!archivos.length) {
  console.log(`  · sin muestras en ${MUESTRAS}: copia ahí un packing list real`);
  process.exit(0);
}

const datos = await cargar('datos.js');
const informe = await cargar('informe.js');

await test('ITEM numerico no reemplaza COD. PRODUCTO y se conserva la fila original', () => {
  const libro = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(libro, XLSX.utils.aoa_to_sheet([
    ['ITEM', 'COD. PRODUCTO', 'DESCRIPCION', 'CANTIDAD'],
    [1, '10070071560001', 'PIEZA', 3],
  ]), 'PACKING');
  const bruto = XLSX.write(libro, {type: 'array', bookType: 'xlsx'});
  const leido = datos.leerPackingList(bruto);
  eq(leido.lineas[0].sku, '10070071560001');
  eq(leido.encabezados[0], 'ITEM');
  eq(leido.lineas[0].cantidad, 3);
});


for (const nombre of archivos) {
  const buf = fs.readFileSync(path.join(MUESTRAS, nombre));
  const leido = datos.leerPackingList(new Uint8Array(buf).buffer);

  await test(`${nombre}: se encuentra la tabla y sus encabezados`, () => {
    ok(leido.lineas.length > 0, 'debe tener líneas');
    ok(leido.encabezados.length > 0, 'debe guardar la cabecera original');
    ok(leido.encabezados.includes('ITEM'), leido.encabezados.join(','));
  });

  await test(`${nombre}: se localizan las columnas que rellena la validación`, () => {
    // Estas son las que el archivo trae en blanco para que las llene el almacén.
    ok(leido.columnas.fisica !== undefined, 'Cantidad Física');
    ok(leido.columnas.validacion !== undefined, 'Validación');
    ok(leido.columnas.pallet !== undefined, 'PALLET');
    ok(leido.columnas.observacion !== undefined, 'OBSERVACION');
  });

  await test(`${nombre}: cada línea guarda su fila completa`, () => {
    const ancho = leido.encabezados.length;
    for (const l of leido.lineas.slice(0, 50)) {
      eq(l.cruda.length, ancho, `la línea ${l.linea} debe tener ${ancho} celdas`);
    }
  });

  // --- El informe, con un conteo simulado --- //
  await test(`${nombre}: el informe devuelve las mismas columnas y filas`, () => {
    const detalle = leido.lineas.map((l, i) => ({
      ...l,
      fisica: l.cantidad,
      diferencia: 0,
      estado: 'OK',
      palletsSimple: i % 3 === 0 ? 'A1-B04' : 'C1',
      pallets: i % 3 === 0 ? 'A1(2)-B04(1)' : 'C1(3)',
      observacion: '',
      destino: '',
      origen: 'PL',
      pnc: '',
      posicionReal: '',
    }));

    const libro = informe.construirLibro({
      recepcion: { codigo: 'PRUEBA', formatos: {} },
      detalle,
      porOrigen: [{
        origen: 'PL',
        formato: { encabezados: leido.encabezados, columnas: leido.columnas },
        detalle,
      }],
      adicionales: [],
      eventos: [],
      auditoria: [],
    });

    const libroLeido = XLSX.read(libro.base64, { type: 'base64' });
    const hoja = libroLeido.Sheets[libroLeido.SheetNames[0]];
    const filas = XLSX.utils.sheet_to_json(hoja, { header: 1, defval: '' });

    eq(filas[0], leido.encabezados, 'la cabecera tiene que ser idéntica');
    eq(filas.length - 1, leido.lineas.length,
       `${leido.lineas.length} filas entran, ${filas.length - 1} salen`);
    for (const f of filas.slice(1)) {
      eq(f.length, leido.encabezados.length, 'cada fila con el ancho original');
    }
  });

  await test(`${nombre}: las columnas de validación quedan llenas, el resto intacto`, () => {
    const detalle = leido.lineas.map((l) => ({
      ...l,
      fisica: l.cantidad - 1,
      diferencia: -1,
      estado: 'FALTANTE',
      palletsSimple: 'H12-H48',
      observacion: 'CAJA DETERIORADA',
      destino: '', origen: 'PL', pnc: '', posicionReal: '', pallets: '',
    }));

    const libro = informe.construirLibro({
      recepcion: { codigo: 'PRUEBA', formatos: {} },
      detalle,
      porOrigen: [{ origen: 'PL',
        formato: { encabezados: leido.encabezados, columnas: leido.columnas },
        detalle }],
      adicionales: [], eventos: [], auditoria: [],
    });

    const libroLeido = XLSX.read(libro.base64, { type: 'base64' });
    const filas = XLSX.utils.sheet_to_json(
      libroLeido.Sheets[libroLeido.SheetNames[0]], { header: 1, defval: '' });

    const c = leido.columnas;
    const primera = filas[1];
    const original = leido.lineas[0];

    eq(String(primera[c.fisica]), String(original.cantidad - 1), 'cantidad física');
    eq(primera[c.validacion], 'Faltante', 'el vocabulario del cliente, no el mío');
    eq(primera[c.pallet], 'H12-H48', 'solo nombres, sin cantidades');
    eq(primera[c.observacion], 'CAJA DETERIORADA');
    if (c.desface !== undefined) eq(String(primera[c.desface]), '-1');

    // Lo que no toca la validación tiene que llegar igual.
    const intactas = leido.encabezados
      .map((_, i) => i)
      .filter((i) => !Object.values(c).includes(i));
    for (const i of intactas) {
      eq(String(primera[i]), String(original.cruda[i]),
         `la columna «${leido.encabezados[i]}» no debe cambiar`);
    }
  });

  // La version de envio lleva SOLO las hojas del packing list. Adjuntar cuatro
  // hojas mas obliga a quien da el alta a buscar la buena, y se equivoca.
  await test(`${nombre}: la versión de envío solo trae la hoja del packing list`, () => {
    const detalle = leido.lineas.map((l) => ({
      ...l, fisica: l.cantidad, diferencia: 0, estado: 'OK',
      palletsSimple: 'A1', pallets: 'A1(1)', observacion: '',
      destino: '', origen: 'PL', pnc: '', posicionReal: '',
    }));
    const base = {
      recepcion: { codigo: 'REC-1', formatos: {} },
      detalle,
      porOrigen: [{ origen: 'PL',
        formato: { encabezados: leido.encabezados, columnas: leido.columnas }, detalle }],
      adicionales: [{ sku: 'X', descripcion: 'd', fisica: 1, pallets: '', motivo: 'm',
                      detectadoPor: '', observacion: '' }],
      eventos: [], auditoria: [],
    };

    const envio = informe.construirLibro(base, { version: 'envio' });
    const auditable = informe.construirLibro(base);

    const hojasEnvio = XLSX.read(envio.base64, { type: 'base64' }).SheetNames;
    const hojasAuditable = XLSX.read(auditable.base64, { type: 'base64' }).SheetNames;

    eq(hojasEnvio, ['VALIDADA','ADICIONALES'], 'envío: packing list y adicionales separados');
    ok(hojasAuditable.includes('ADICIONALES'), hojasAuditable.join(','));
    ok(hojasAuditable.includes('BITACORA'));
    ok(!hojasAuditable.includes('AUDITORIA'));
    ok(hojasAuditable.length > hojasEnvio.length);

    // Y la hoja del packing list tiene que ser idéntica en las dos.
    const filasEnvio = XLSX.utils.sheet_to_json(
      XLSX.read(envio.base64, { type: 'base64' }).Sheets.VALIDADA, { header: 1, defval: '' });
    const filasAud = XLSX.utils.sheet_to_json(
      XLSX.read(auditable.base64, { type: 'base64' }).Sheets.VALIDADA, { header: 1, defval: '' });
    eq(filasEnvio, filasAud, 'la hoja que se entrega no cambia entre versiones');
  });

  await test(`${nombre}: el pallet nunca lleva cantidades ni paréntesis`, () => {
    eq(informe.soloPallets({ A1: 5, B04: 2 }), 'A1-B04');
    eq(informe.soloPallets({ 'A1.1': 3, C1: 9 }), 'C1-A1.1', 'de mayor a menor');
    eq(informe.soloPallets({ A1: 0, B04: 2 }), 'B04', 'lo que quedó en cero no va');
    eq(informe.soloPallets({}), '');
    ok(!/[()0-9]+\)/.test(informe.soloPallets({ A1: 5 })), 'sin paréntesis');
  });
}

// ============ Dos packing lists, dos hojas ============================== //
// Si se validan dos listas en una recepcion, el informe tiene que entregar las
// dos. Exportar solo la primera deja la mitad del trabajo sin reportar, y no se
// nota hasta que alguien busca el otro archivo.
{
  const uno = fs.readFileSync(path.join(MUESTRAS, archivos[0]));
  const dos = fs.readFileSync(path.join(MUESTRAS, archivos[archivos.length - 1]));
  const a = datos.leerPackingList(new Uint8Array(uno).buffer);
  const b = datos.leerPackingList(new Uint8Array(dos).buffer);

  const prep = (leido, origen) => leido.lineas.slice(0, 12).map((l) => ({
    ...l, origen, fisica: l.cantidad, diferencia: 0, estado: 'OK',
    palletsSimple: 'A1', pallets: 'A1(1)', observacion: '',
    destino: '', pnc: '', posicionReal: '',
  }));

  const dA = prep(a, 'PL-A');
  const dB = prep(b, 'PL-B');

  await test('dos listas consolidadas producen dos hojas, con sus filas', () => {
    const libro = informe.construirLibro({
      recepcion: { codigo: 'REC-2', formatos: {} },
      detalle: [...dA, ...dB],
      porOrigen: [
        { origen: 'PL-A', formato: { encabezados: a.encabezados, columnas: a.columnas },
          detalle: dA },
        { origen: 'PL-B', formato: { encabezados: b.encabezados, columnas: b.columnas },
          detalle: dB },
      ],
      adicionales: [], eventos: [], auditoria: [],
    }, { version: 'envio' });

    const leidoLibro = XLSX.read(libro.base64, { type: 'base64' });
    eq(leidoLibro.SheetNames, ['PL-A', 'PL-B'], 'una hoja por lista');

    const filasA = XLSX.utils.sheet_to_json(leidoLibro.Sheets['PL-A'], { header: 1, defval: '' });
    const filasB = XLSX.utils.sheet_to_json(leidoLibro.Sheets['PL-B'], { header: 1, defval: '' });
    eq(filasA.length - 1, dA.length, 'PL-A entrega sus filas');
    eq(filasB.length - 1, dB.length, 'PL-B entrega las suyas');
    eq(filasA[0], a.encabezados, 'y cada una con SU cabecera');
    eq(filasB[0], b.encabezados);
  });

  // Una lista cargada antes de que se guardara el formato original no puede
  // desaparecer del informe: sale con las columnas propias.
  await test('una lista sin formato guardado sigue saliendo', () => {
    const libro = informe.construirLibro({
      recepcion: { codigo: 'REC-3', formatos: {} },
      detalle: [...dA, ...dB],
      porOrigen: [
        { origen: 'PL-A', formato: { encabezados: a.encabezados, columnas: a.columnas },
          detalle: dA },
        { origen: 'PL-B', formato: null, detalle: dB },
      ],
      adicionales: [], eventos: [], auditoria: [],
    }, { version: 'envio' });

    const nombres = XLSX.read(libro.base64, { type: 'base64' }).SheetNames;
    eq(nombres, ['PL-A', 'PL-B'], 'las dos, aunque una no tenga formato');
  });
}

// --- Un formato que no se reconoce tiene que decir QUE trae ---------------- //
// Cada cliente manda su packing list con otras columnas. Cuando llega uno
// nuevo, «no se encontro la tabla» deja a quien lo carga sin saber si el
// problema es la hoja, la fila o el nombre de una columna.

const libroDe = (filas) => {
  const l = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(l, XLSX.utils.aoa_to_sheet(filas), 'REV');
  const b64 = XLSX.write(l, { bookType: 'xlsx', type: 'base64' });
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)).buffer;
};

const errorAlLeer = (filas) => {
  try { datos.leerPackingList(libroDe(filas)); return null; }
  catch (e) { return e.message; }
};

await test('dice en que hoja y fila esta lo mas parecido a una cabecera', () => {
  const m = errorAlLeer([
    ['INFORME DE EMBARQUE'],
    ['CODIGO INTERNO', 'DETALLE DEL BIEN', 'PIEZAS', 'PESO'],
    ['A1', 'TORNILLO', '10', '2'],
  ]);
  ok(m, 'tiene que fallar: esas columnas no se reconocen');
  ok(/hoja «REV»/.test(m), m);
  ok(/fila 2/.test(m), m);
});

await test('lista las columnas que trae, para poder darlas de alta', () => {
  const m = errorAlLeer([
    ['CODIGO INTERNO', 'DETALLE DEL BIEN', 'PIEZAS', 'PESO'],
    ['A1', 'TORNILLO', '10', '2'],
  ]);
  ok(/CODIGO INTERNO/.test(m), m);
  ok(/PIEZAS/.test(m), m);
});

await test('dice cual de los dos datos obligatorios falta', () => {
  // Trae ITEM, que si se reconoce, pero ninguna columna de cantidad.
  const m = errorAlLeer([
    ['ITEM', 'DESCRIPCION', 'PESO'],
    ['A1', 'TORNILLO', '2'],
  ]);
  ok(/la cantidad/.test(m), m);
  ok(!/el código del producto/.test(m), 'ITEM si se reconocio: ' + m);
});

await test('un archivo sin ninguna tabla lo dice de otra forma', () => {
  const m = errorAlLeer([['solo esto'], ['y esto']]);
  ok(/ninguna fila con varias columnas/.test(m), m);
});

resumen();
