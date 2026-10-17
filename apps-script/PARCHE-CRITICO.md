# Parche crítico — ITSANET IMS (Apps Script)

Tres defectos rompen el ciclo principal de la app en producción. Los tres están
reproducidos en `repro-bugs.js`. Este documento trae el reemplazo exacto de cada
uno para pegar en el editor de Apps Script.

> Aplicar en este orden. El #1 es el que impide que se guarden los escaneos.

---

## 1. `playSound` no existe — ningún escaneo se guarda

**Gravedad: crítica.** Se invoca 7 veces y no está definida en ninguna parte del
archivo.

En `manejarEscaneo`, el orden es:

```js
input.value = ""; limpiarBuscador();
var f = ...; var e = ...;
if(f === e) { playSound('beep'); speak("Completado"); }   // ← ReferenceError
...
guardarLocal(idx, false); sincronizarCelda(idx);          // ← nunca se ejecuta
```

Las tres ramas del `if` llaman a `playSound`, así que **el 100 % de los escaneos
lanza `ReferenceError` antes de llegar a `sincronizarCelda`**. El número sube en
pantalla porque `inFisica.value` ya se asignó antes, pero no se escribe nada en
el Google Sheet: al recargar, lo escaneado desapareció.

### Corrección

Pegar esta función junto a `speak()` (después de la línea 434):

```js
    function playSound(tipo) {
        // El audio es accesorio: jamas debe interrumpir el ciclo de escaneo.
        try {
            if (audioCtx.state === 'suspended') audioCtx.resume();
            var dur = (tipo === 'error') ? 0.35 : 0.12;
            var osc = audioCtx.createOscillator();
            var gain = audioCtx.createGain();
            osc.connect(gain); gain.connect(audioCtx.destination);
            osc.type = (tipo === 'error') ? 'square' : 'sine';
            osc.frequency.value = (tipo === 'error') ? 220 : 950;
            gain.gain.setValueAtTime(0.08, audioCtx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + dur);
            osc.start();
            osc.stop(audioCtx.currentTime + dur);
            if (navigator.vibrate) navigator.vibrate(tipo === 'error' ? [60, 50, 60] : 40);
        } catch (e) {
            console.warn('Audio no disponible:', e);
        }
    }
```

El `try/catch` es parte de la corrección, no un adorno: en bodega el navegador
puede bloquear `AudioContext` hasta que haya interacción del usuario, y eso
volvería a tumbar el escaneo por la misma vía.

Conviene además blindar `speak()` igual, por el mismo motivo:

```js
    function speak(text) {
        if(!voiceEnabled) return;
        try {
            if ('speechSynthesis' in window) {
                var msg = new SpeechSynthesisUtterance(text);
                msg.lang = 'es-ES'; msg.rate = 1.1;
                window.speechSynthesis.speak(msg);
            }
        } catch (e) { console.warn('Voz no disponible:', e); }
    }
```

---

## 2. `calcularKPIs` escribe en elementos que no existen — progreso congelado en 0 %

**Gravedad: alta.** Explica el `PROGRESO DE RECEPCIÓN 0%` y el `0 / 0 Refs` de
las capturas, con filas ya validadas.

`calcularKPIs` (línea 854) hace:

```js
document.getElementById('kpiTotal').innerText = totales;
document.getElementById('kpiUnidadesEsperadas').innerText = uEsperadas;
```

Ninguno de esos dos `id` existe en el HTML. El dashboard solo define `kpiOk`,
`kpiPend` y `kpiUnidadesFisicas`. Resultado: `TypeError: Cannot set properties
of null`, y todo lo que viene después nunca corre — barra de progreso, texto
`x / y`, gráfico donut y la celebración del 100 %.

Peor: `guardarLocal` llama a `calcularKPIs()` antes de `filtrarTabla()`, así que
el filtro tampoco se reaplica al escribir una cantidad.

### Corrección — parte A: acceso defensivo

Reemplazar el bloque de asignaciones por un helper que no reviente si falta un
elemento. Que un `id` renombrado degrade un número en pantalla es aceptable; que
congele el progreso de toda la recepción, no.

```js
    function setTxt(id, val) {
        var el = document.getElementById(id);
        if (el) el.innerText = val;
    }
```

Y dentro de `calcularKPIs`, cambiar:

```js
      document.getElementById('kpiTotal').innerText = totales; document.getElementById('kpiOk').innerText = completadas;
      document.getElementById('kpiPend').innerText = pendientes; document.getElementById('kpiUnidadesEsperadas').innerText = uEsperadas;
      document.getElementById('kpiUnidadesFisicas').innerText = uFisicas;
```

por:

```js
      setTxt('kpiTotal', totales);
      setTxt('kpiOk', completadas);
      setTxt('kpiPend', pendientes);
      setTxt('kpiUnidadesEsperadas', uEsperadas);
      setTxt('kpiUnidadesFisicas', uFisicas);
```

### Corrección — parte B: mostrar los dos KPI que faltaban

Son datos útiles que el dashboard debería tener. Agregar estas dos tarjetas
dentro de `<div class="kpi-row">` (línea 349):

```html
                <div class="kpi-card" style="border-left: 6px solid var(--secondary);">
                    <div><div class="kpi-label"><span class="material-icons" style="font-size: 16px;">list_alt</span> LÍNEAS TOTALES</div>
                    <div class="kpi-val" id="kpiTotal">0</div></div>
                </div>
                <div class="kpi-card" style="border-left: 6px solid var(--secondary);">
                    <div><div class="kpi-label"><span class="material-icons" style="font-size: 16px;">inventory_2</span> UNID. ESPERADAS</div>
                    <div class="kpi-val" id="kpiUnidadesEsperadas">0</div></div>
                </div>
```

---

## 3. `.find()` sobre SKU repetidos — solo se cuenta la primera línea

**Gravedad: alta.** El packing list real tiene 5 SKU en más de una línea.

```js
var itemFila = currentData.find(i => String(i.referencia).toUpperCase() === codigo);
```

`find()` devuelve **solo la primera coincidencia**. Con `6Q09598589B9`, que
ocupa las filas 16, 17 y 18 del archivo real (2 + 1 + 1 = 4 unidades), la app
siempre incrementa la fila 16 y compara contra un esperado de 2. A partir del
tercer escaneo marca sobrante cuando en realidad faltan unidades, y las filas 17
y 18 quedan en 0 para siempre: faltantes fantasma en el reporte final.

### Corrección

Agregar esta función y usarla en `manejarEscaneo`:

```js
    // Un SKU puede ocupar varias lineas del packing list (distinta factura o
    // referencia de pedido). El escaneo debe llenarlas en orden, no siempre la
    // primera. Cuando todas estan completas, el excedente cae en la ultima y
    // queda marcado como sobrante.
    function buscarFilaParaEscaneo(codigo) {
        var filas = currentData.filter(function(i) {
            return String(i.referencia).toUpperCase() === codigo;
        });
        if (filas.length === 0) return null;
        var pendiente = filas.find(function(i) {
            return (parseFloat(i.fisica) || 0) < (parseFloat(i.esperada) || 0);
        });
        return pendiente || filas[filas.length - 1];
    }

    // Total esperado y contado del SKO completo, no de una sola linea.
    function totalesDelSku(codigo) {
        var esp = 0, fis = 0;
        currentData.forEach(function(i) {
            if (String(i.referencia).toUpperCase() === codigo) {
                esp += parseFloat(i.esperada) || 0;
                fis += parseFloat(i.fisica) || 0;
            }
        });
        return { esperado: esp, fisico: fis };
    }
```

En `manejarEscaneo`, reemplazar la línea del `find` por:

```js
            var itemFila = buscarFilaParaEscaneo(codigo);
```

y el bloque de voz/sonido, que debe comparar contra el total del SKU:

```js
                var t = totalesDelSku(codigo);
                if (t.fisico === t.esperado) { playSound('beep'); speak("Completado"); }
                else if (t.fisico > t.esperado) { playSound('error'); speak("Alerta, sobrante detectado"); }
                else { playSound('beep'); speak("Faltan " + (t.esperado - t.fisico)); }
```

Nota: `guardarLocal(idx, false)` debe llamarse **antes** de leer los totales,
porque es quien actualiza `item.fisica` en `currentData`.

---

## Verificación después de aplicar

1. Escanear un SKU, **recargar la página** y confirmar que la cantidad persiste.
   Es la prueba de que el #1 quedó resuelto; antes se perdía siempre.
2. Confirmar que la barra de progreso y `x / y Refs` se mueven (#2).
3. Escanear 4 veces `6Q09598589B9` (o cualquier SKU repetido) y verificar que se
   reparten entre sus líneas y que ninguna queda en 0 (#3).

---

## Lo que este parche NO resuelve

Son límites del modelo de datos, no bugs; están detallados en
[`ANALISIS.md`](ANALISIS.md):

- Validación contra Depot y captura de EAN al escanear.
- Un mismo SKU en varios pallets, con sugerencia de dónde ya se guardó.
- Sobrantes de SKU que no estaban en el packing list.
- Distinguir "no contado" de "faltante confirmado".
- Escritura concurrente de varios operadores sin pisarse.
- KPIs históricos entre recepciones.
