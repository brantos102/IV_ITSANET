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

    eq(hojasEnvio, ['VALIDADA'], 'envío: solo el packing list');
    ok(hojasAuditable.includes('ADICIONALES'), hojasAuditable.join(','));
    ok(hojasAuditable.includes('BITACORA'));
    ok(hojasAuditable.includes('AUDITORIA'));
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

resumen();
