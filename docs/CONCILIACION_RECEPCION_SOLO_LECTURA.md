# Conciliar cantidades y embarques sin modificar producción

`scripts/conciliar_recepcion.py --codigo CODIGO` consulta una recepción en una
transacción MySQL/MariaDB **READ ONLY**, con snapshot consistente. No importa la
aplicación, ejecuta migraciones, crea tablas, cambia conteos ni contacta Google.
Utiliza `VAL_DATABASE_URL` del entorno del servicio; no imprime credenciales.

El resultado distingue:

- Totales guardados en la cabecera, líneas reales y esperado agregado por SKU.
- SKU distintos frente a filas del Excel: una referencia puede repetirse en
  varias facturas, contenedores y embarques sin ser una fila duplicada.
- Unidades declaradas y unidades físicas contadas, que tienen finalidades distintas.
- Listas importadas, embarques y contenedores según sus metadatos guardados.
- Identificación y cantidades recuperables de las celdas originales importadas,
  para detectar una lectura logística anterior diferente.

La suma de SKU por contenedor o por embarque no equivale necesariamente al total
de SKU distintos: un mismo SKU puede aparecer en varios grupos. Las unidades sí
se suman por fila, sin eliminar repeticiones legítimas.

Antes de corregir una diferencia, confirmar qué contenedores pertenecen a la
recepción: el archivo puede incluir mercancía no recibida. No volver a importar
el archivo completo sobre la recepción existente para intentar cuadrar cifras,
pues podría duplicar el declarado. Los conteos y evidencias deben conservarse.

El script puede extraerse del commit mediante `git show` a un archivo temporal y
ejecutarse con `systemd-run --property=EnvironmentFile=/etc/iv-itsanet.env`, como
los diagnósticos administrativos existentes. **No necesita actualizar ni reiniciar
el servicio de producción.** Se debe ejecutar con el mismo usuario de trabajo del
repositorio. La consulta produce su informe por pantalla y no escribe en MySQL.

Los libros originales y conciliaciones de clientes deben conservarse fuera del
repositorio. Las pruebas usan datos sintéticos y una base MySQL aislada.
