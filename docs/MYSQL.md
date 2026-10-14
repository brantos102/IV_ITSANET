# Pasar al servidor de la empresa, con MySQL

Lo que hay hoy corre sobre Firebase porque no había servidor. Ahora lo hay. Este
documento es el camino de un sitio al otro, en orden, con lo que tiene que salir
en cada paso.

La aplicación local ya existe: es la de `app/` (FastAPI + SQLAlchemy). Hasta
ahora guardaba en SQLite. Lo único que cambia para usar MySQL es a dónde apunta,
y el cuidado de la conexión.

> **Lo que NO se puede traer: las contraseñas.** Firebase guarda hashes que no
> salen del navegador, y el formato tampoco es el de aquí. Los operarios se
> importan para que sus conteos sigan teniendo autor, pero entran desactivados
> y sin PIN. Hay que dárselo uno a uno. No hay forma de evitarlo, así que mejor
> saberlo antes de empezar y no la mañana del cambio.

---

## 1. MySQL instalado y la base creada

Vale MySQL 8 o MariaDB 10.5 en adelante.

Edita `mysql/01-crear-base.sql` y cambia `CAMBIA-ESTA-CLAVE`. Luego:

```bash
mysql -u root -p < mysql/01-crear-base.sql
```

La última línea del script imprime el juego de caracteres de la base.

- [ ] Dice `utf8mb4` y `utf8mb4_unicode_ci`

Si dice otra cosa, páralo aquí. Con `latin1` o con el `utf8` de MySQL —que son
tres bytes y no es UTF-8 completo— las tildes y las eñes de las descripciones se
guardan rotas, y eso no se arregla después: hay que volver a importar.

---

## 2. La aplicación apuntando a MySQL

```bash
pip install -r requirements.txt

export VAL_DATABASE_URL="mysql+pymysql://val:LA-CLAVE@127.0.0.1:3306/val_ventura?charset=utf8mb4"
python scripts/preparar_base.py
```

El `?charset=utf8mb4` no es decorativo: sin él, el conector negocia `latin1` y
se rompe lo mismo que en el paso anterior, esta vez sin que la base tenga la
culpa.

Tiene que decir:

```
Motor    : mysql 8.x.x
Juego    : utf8mb4 / utf8mb4_unicode_ci
Tablas   : 9 (9 creadas: auditoria, operadores, ...)
```

- [ ] El motor dice **mysql**, no sqlite

Ese aviso está puesto a propósito. El fallo más caro de este paso no es que
falle: es que funcione contra el SQLite de pruebas mientras todo el mundo cree
que está escribiendo en MySQL, y descubrirlo una semana después.

En Windows, en vez de `export`, `set VAL_DATABASE_URL=...`. Y conviene dejarlo
en las variables de entorno del servicio, no en una consola que alguien cierra.

---

## 3. Sacar el histórico de la nube

En `https://iv-itsanet.web.app/admin.html`, entrando como **ADMIN**:

**Llevar el histórico al servidor local** → *Exportar para el servidor local*.

Baja un `val-ventura-AAAA-MM-DD.json` y enseña unas cifras.

- [ ] **Apunta esas cifras.** Son las que hay que cuadrar en el paso 5.

Tarda: son cuatro lecturas por recepción. Deja la pestaña abierta.

---

## 4. Meterlo en la base

Copia el `.json` al servidor y, primero en seco:

```bash
python scripts/importar_firestore.py val-ventura-2026-10-14.json --ensayo
```

Hace la importación entera y la deshace al final. Sirve para ver qué entraría y
qué avisos salen sin tocar nada.

- [ ] Los avisos que salgan tienen sentido

Cuando cuadre, sin `--ensayo`:

```bash
python scripts/importar_firestore.py val-ventura-2026-10-14.json
```

Se puede lanzar las veces que haga falta. Cada conteo conserva la clave de
idempotencia que tenía en Firestore, así que repetir no duplica: ni conteos, ni
líneas, ni recepciones. Si se corta a mitad, se vuelve a lanzar y ya está.

---

## 5. Cuadrar

Compara lo que dijo el exportador (paso 3) con lo que dice el importador.

```sql
SELECT (SELECT COUNT(*) FROM recepciones)   AS recepciones,
       (SELECT COUNT(*) FROM packing_items) AS lineas,
       (SELECT COUNT(*) FROM scan_events)   AS conteos;
```

- [ ] Los tres números coinciden con los de la pantalla de exportación

Y que las unidades cuadren con lo que se validó:

```sql
SELECT r.codigo,
       SUM(CASE WHEN e.tipo <> 'ANULACION' THEN e.cantidad ELSE 0 END) AS contado
  FROM recepciones r
  LEFT JOIN scan_events e ON e.recepcion_id = r.id
 GROUP BY r.codigo
 ORDER BY r.codigo;
```

- [ ] Para una recepción que conozcas, el total es el que tenía

---

## 6. Los PIN

El importador termina imprimiendo una línea por operario. Son los que entraron
desactivados y sin PIN:

```bash
python scripts/crear_operador.py ana "Ana Torres" 4821 --rol OPERADOR
```

- [ ] Cada operario entra con su usuario y su PIN
- [ ] Hay **al menos dos** con rol ADMIN

---

## 7. Antes de dejar de usar la nube

- [ ] Una recepción nueva de principio a fin en el servidor local
- [ ] El informe final sale con las mismas filas que el packing list
- [ ] Hay copia de seguridad automática (`mysqldump` diario, y comprobado que
      el archivo se puede restaurar — una copia que nadie ha restaurado nunca
      no es una copia)
- [ ] Las fotos de las novedades siguen accesibles donde estén

> **No apagues el proyecto de Firebase el mismo día.** Deja la aplicación de la
> nube en marcha y en solo lectura unas semanas. Si falta algo en el servidor, lo
> vas a descubrir usándolo, no antes.

---

## Lo que cambió en el modelo para esto

Cuatro columnas que en la nube existían y aquí no tenían sitio. Sin ellas la
importación se habría llevado los datos por delante en silencio:

| Columna | Por qué |
|---|---|
| `packing_items.origen` | Una recepción puede consolidar varios packing lists, y cada uno tiene su línea 1. Sin esto, la segunda lista pisaba a la primera fila por fila. |
| `scan_events.posicion_real` | Dónde quedó en bodega, que no es lo mismo que el pallet: de 30 unidades pueden ir 12 a una posición y 18 quedarse por ubicar. |
| `scan_events.origen` | Contra qué lista se contó, cuando hay varias. |
| `scan_events.fotos` | Un producto no conforme suele llevar más de una. |

Y dos cambios de tipo, que es lo que se arregla aprovechando que se migra:

- **Cantidades y precios en `DECIMAL`, no en coma flotante.** Un `FLOAT` de MySQL
  son cuatro bytes y unos siete dígitos significativos; suma 300 líneas y el
  total deja de cuadrar con el papel.
- **Fechas con milésimas.** `DATETIME` a secas redondea al segundo, y dos
  escaneos del mismo segundo quedaban empatados: el libro mayor dejaba de tener
  un orden.

---

## Si algo falla

| Lo que dice | Qué pasa |
|---|---|
| `MySQL server has gone away` | Conexión que MySQL cerró por ociosa. Ya se reciclan cada hora; si sigue, baja `VAL_DB_POOL_RECYCLE` por debajo del `wait_timeout` del servidor. |
| `Data too long for column` | Modo estricto haciendo su trabajo. El importador recorta lo que no cabe, así que esto viene de otro sitio: mira qué columna nombra. |
| `Incorrect string value: '\xF0\x9F...'` | La tabla no está en utf8mb4. Paso 1. |
| `Access denied for user 'val'` | La clave del `GRANT` no es la de `VAL_DATABASE_URL`. |
| `No module named 'pymysql'` | Falta `pip install -r requirements.txt`. |
