# Orden del informe y validación de Depot · 51

19/10/2026, Ecuador. Interfaz `20261019-51`.
Etiqueta de publicación: `itsanet-20261019-columnas-depot-51`.

## Marca, Cliente y orden de columnas

**Recepción actual → Informes → Vista previa y columnas** permite organizar la
exportación de cada embarque. Elegir la posición de una columna o utilizar las
flechas mueve sus datos completos. Marca y Cliente se proponen al inicio. Hay
acciones para recuperar esa disposición o mantener el bloque del packing list
seguido de los campos adicionales.

Guardar conserva la selección por embarque. Al descargar o preparar el correo,
elegir **Cliente: informe ampliado y organizado**. La vista previa y el Excel
usan el mismo generador; conservan filas, datos, códigos con ceros y enlaces.
La opción de packing list original mantiene las posiciones exigidas para su
carga al WMS. La configuración no altera el archivo recibido ni los informes
ya emitidos. Las recepciones cerradas mantienen su protección actual.

Se registran el orden y su autor en la auditoría existente. El servidor rechaza
columnas omitidas, repetidas o desconocidas. La versión del formato y el bloqueo
de recepción evitan que dos supervisores se sobrescriban silenciosamente.

Las fórmulas locales ajustan sus referencias al mover columnas, incluidas las
referencias absolutas y los rangos que permanecen contiguos. Si el orden rompe
un rango o aparece una referencia externa/dinámica que no se puede trasladar con
seguridad, se bloquea esa generación y se indica conservar el formato original.
No se entrega un archivo con esas referencias alteradas silenciosamente.

## Columna OK de Depot y ausencia de MAESTRO

La columna se calcula con la información disponible en el servidor. No se copia
la hoja MAESTRO de aproximadamente 16 MB del archivo recibido ni se deja una
fórmula de búsqueda que dependa de esa hoja. El original recibido se conserva.

La integración actual sincroniza la **API de stock** de Depot. No equivale a una
consulta en vivo del maestro completo. Un código ausente de ese stock podría
existir sin saldo. Cuando se utiliza un maestro importado, se informa esa fuente
en lugar de afirmar que hubo una consulta API. Se muestran la fuente y la fecha
de actualización, con fecha legible en Ecuador.

| Valor | Interpretación y acción |
|---|---|
| `ok` | Producto encontrado para ese cliente en el catálogo disponible. |
| `N/D` · no encontrado | Verificar el registro en Depot. Si no existe, solicitar su creación antes de cargar cantidades en Depot. |
| `N/D` · no registrado | El dato del catálogo está marcado explícitamente como no registrado. Solicitar creación. |
| `N/D` · otro cliente | Revisar la asociación del código al cliente de la recepción. |
| `INACTIVO` | Solicitar revisión/habilitación antes de cargar cantidades. |
| `PENDIENTE` | No hay información suficiente para validar; actualizar el catálogo del cliente. |

Los alias configurados del cliente y las posiciones de stock por cliente evitan
clasificar un SKU únicamente por su entrada global cuando pertenece a varios
clientes. Registrar un código localmente no lo acredita como creado en Depot.

En el **Excel**, las observaciones conservan la nota del operario y añaden la
acción correspondiente a los productos por revisar. Los comentarios del
encabezado OK, sus celdas y las propiedades del libro documentan el método y
la ausencia de MAESTRO, sin añadir filas ni una copia del catálogo completo.

En el **correo final**, la sección **Observaciones de validación en Depot**
explica la ausencia de MAESTRO e identifica los SKU por revisar y su acción.
Las observaciones adicionales del supervisor se conservan. Si cambia el
catálogo durante la edición, se exige revisar el correo actualizado. La nueva
validación queda congelada junto al correo del cierre. Un correo confirmado
o declarado enviado manualmente conserva el contenido emitido.

Esto no impide registrar el conteo físico en ITSANET. La recomendación se refiere
a la creación o habilitación en Depot antes de cargar allí las cantidades.
La generación no hace nuevas consultas de red a Depot por SKU ni envía correo.

## Producción y PC del desarrollador

El usuario aportó el 19/10/2026 esta comprobación del servidor empresarial:

```text
ActiveState=active
SubState=running
UnitFileState=enabled
NRestarts=0
WorkingDirectory=/home/enicolalde/bryan/IV_ITSANET
http://127.0.0.1:3002/health → ok=true
```

Confirma un servicio en ejecución y habilitado para iniciar con el servidor.
No requiere mantener la terminal SSH/VS Code o la PC de desarrollo encendidas.
El acceso esperado es navegador → Apache HTTPS 8443 → servicio empresarial 3002.
La URL de pruebas trycloudflare sí depende de la PC y de su túnel.

El usuario informa que la página empresarial completa deja de abrir al apagar
su PC. La salud local no demuestra que Apache, DNS, TLS y la ruta desde otro
dispositivo estén bien. Se solicitó comprobar los destinos ProxyPass del sitio
8443, mostrando solo host/puerto/ruta. No se ha confirmado la causa de esa
interrupción ni se ha cambiado Apache, VPN, DNS o certificados en esta sesión.

El destino habitual del proxy empresarial es el servicio del propio servidor,
no una IP de la PC de desarrollo o un túnel SSH de esa PC. Después de verificar
el destino, repetir `/health` por HTTPS desde un dispositivo con acceso a la red
empresarial mientras se cierra únicamente la sesión de desarrollo. Un acceso
externo sin ruta/VPN a la red privada es una situación distinta del arranque de
la app. No reinstalar `servicio.sh` ni cambiar conexiones sin esa comprobación.

## Pase seguro al servidor

La publicación en GitHub no actualiza automáticamente la producción. Preparar
la pausa cuando los operarios hayan guardado sus fichas. La rutina existente
respalda datos/archivos/configuración de forma privada, pausa brevemente solo
iv-itsanet, aplica el commit fijado y verifica la salud. No se ejecutan pruebas,
se copian bases de desarrollo ni se reenvían informes históricos en producción.

En **Linux @apps**, una sola línea:

```bash
cd ~/bryan/IV_ITSANET && git fetch origin --tags && revision_itsanet="$(git rev-parse 'itsanet-20261019-columnas-depot-51^{commit}')" && git show "$revision_itsanet:scripts/actualizar_produccion.sh" > /tmp/itsanet-pase51.sh && bash /tmp/itsanet-pase51.sh "$PWD" "$revision_itsanet"
```

Después recargar el navegador. Verificar versión `20261019-51`, sesión, recepción
existente, conteos y fotos. Actualizar el catálogo desde la barra del supervisor
cuando corresponda y revisar su resultado antes de interpretar N/D. Confirmar
el orden y el texto de Depot antes de generar la siguiente versión del informe.

No hay tablas, columnas SQL ni dependencias nuevas. El orden utiliza el JSON y
la auditoría del formato existentes; no se duplica el catálogo ni se almacenan
fotos o la hoja MAESTRO en MySQL por esta mejora. No cambia Google/HMAC.

## Ejemplo y validación

[Excel de ejemplo · datos ficticios de una recepción de pruebas](muestras/ITSANET-informe-organizado-51.xlsx).
No es una consulta real a Depot ni un informe productivo.

Las pruebas se ejecutan en bases temporales y un MySQL propio, separados de
la empresa. Se comprobaron el cambio de orden, conflicto entre sesiones,
exportación y archivo de dos libros independientes, fórmulas locales, ceros,
comentarios, fuente de catálogo y ausencia de MAESTRO. La vista móvil de 390 px
no desborda el diálogo. El correo muestra la justificación y los pendientes;
no se enviaron correos ni se accedió al Drive operativo.

- Runner general: 1.205 aprobadas, de ellas 706 Python y 499 JavaScript.
- MySQL desechable: 26 aprobadas, incluida la condición de concurrencia que se
  omite en SQLite.
- Tras el ajuste final de protección de columnas de origen: 251 comprobaciones
  JavaScript aprobadas (gestión, formato, aplicación y páginas).
- Diagnóstico de solo lectura: 10 aprobadas y una condición omitida en ese
  entorno. Las omitidas no se cuentan como ejecutadas/aprobadas.
