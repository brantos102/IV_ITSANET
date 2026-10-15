# ITSANET en tu PC Windows, con MySQL independiente

La misma API FastAPI y la misma interfaz de producción se ejecutan con Python
3.12 y MySQL 8.4 en Docker. La versión exacta de MySQL de producción se puede
comprobar con el diagnóstico; si es distinta, ajustar la imagen de pruebas y
volver a validar antes de publicar. No se copian usuarios, datos, imágenes ni
conexiones reales. La base nueva sirve para construir las próximas mejoras.

## 1. Docker Desktop, una sola vez

En **PowerShell de tu PC**, fuera de la terminal SSH:

```powershell
docker --version
docker compose version
```

Si no existe Docker:

```powershell
winget install --exact --id Docker.DockerDesktop
```

Abrir Docker Desktop desde Inicio, completar la instalación y esperar
**Engine running**. Usar **Linux containers** y el motor WSL2. Si el instalador
solicita reiniciar Windows o habilitar virtualización/WSL, completar ese paso
antes de continuar. Verificar con `docker info`. Necesita Internet para la
primera descarga de imágenes y dependencias. No hace falta instalar Python,
MySQL, Node ni Firebase CLI en el PC para arrancar esta copia.

## 2. Copia independiente y primer arranque

En una carpeta **nueva** del PC, por ejemplo `$HOME\source`. Requiere Git:

```powershell
New-Item -ItemType Directory -Force "$HOME\source" | Out-Null
Set-Location "$HOME\source"
git clone --branch pr_bep/serene-thompson-10qlxd --single-branch https://github.com/brantos102/IV_ITSANET.git IV_ITSANET-desarrollo
Set-Location IV_ITSANET-desarrollo
git switch -c desarrollo-local
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\local.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\local.ps1 -Accion acceso
```

El Bypass afecta únicamente ese proceso de PowerShell. No modifica la política
del equipo. La terminal no debe mostrar `enicolalde@apps` ni la ventana VS Code
indicar conexión SSH. Si la carpeta ya existe, abrirla y comprobar `git status`
antes de actualizar; no volver a clonar encima ni sobrescribir cambios.

Abrir VS Code sobre esta carpeta (`code .`) y, tras confirmar salud, abrir en
el navegador la dirección local **localhost:3003/app/**. El usuario es `admin`;
el comando `-Accion acceso` muestra la contraseña inicial generada en el PC.
Si se cambia desde la app, se conserva la nueva. No se restablece al reiniciar.

El puerto 3003 evita el reenvío SSH habitual 3002. Si está ocupado:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\local.ps1 -Puerto 3013
```

Elegir uno libre. Solo se publica el puerto de la app en 127.0.0.1; MySQL
permanece en la red privada de Docker. Los puertos del servidor empresarial
no se modifican. El arranque local rechaza otra base, usuario o host MySQL.

## 3. Editar y comprobar

- Python en `app/`: el servidor recarga al guardar. Esperar su salud antes de
  continuar una prueba; un formulario abierto puede necesitar recarga.
- HTML/CSS/JS en `firebase/public/`: se sirven desde la copia local. Recargar
  el navegador. El nombre de la carpeta no implica usar Firebase: `/app/`
  consulta la API y MySQL locales. Los cambios de bibliotecas/frontend deben
  seguir el build y versionado del proyecto antes de la entrega.
- Registrar usuarios de prueba, aprobarlos y crear una recepción pequeña.
  Validar packing list, conteos, códigos alternativos, imágenes, diferencias,
  exportaciones, etiquetas y cierre antes de probar un lote mayor.
- Las imágenes de prueba se guardan en el volumen local hasta enviarse a
  Drive; MySQL conserva solo metadatos y relaciones. La app arranca sin puentes
  Google ni credenciales WMS. Las conexiones se configuran solo desde ADMIN.
  Usar cuenta, Drive y destinatarios de prueba; nunca copiar `app_config` ni
  una cola de entregas reales. Sin puente, la entrega queda pendiente.

Consultar estado, logs o detener conservando los registros:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\local.ps1 -Accion estado
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\local.ps1 -Accion logs
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\local.ps1 -Accion detener
```

Volver a ejecutar sin `-Accion` para iniciar. La primera compilación tarda más;
las siguientes reutilizan la imagen y los volúmenes. Si cambia requirements,
el mismo comando reconstruye dependencias. Los archivos en `.local/` contienen
claves exclusivas de desarrollo y están excluidos de Git y del build. Conservar
esa carpeta: regenerar sus claves no cambia las ya guardadas por MySQL.

Los datos viven en los volúmenes Docker
`iv-itsanet-desarrollo_mysql_pruebas` y
`iv-itsanet-desarrollo_archivos_pruebas`. `stop` los conserva. No usar `down -v`,
limpiar volúmenes ni restablecer Docker Desktop si se quieren conservar pruebas.
No ejecutar `scripts/servicio.sh` para este entorno. No ejecutar fixtures de
pytest sobre la base operativa ni sobre la de desarrollo que se desea conservar.

Este arranque escucha únicamente en tu PC. Para pruebas desde el handheld
se necesita un acceso de pruebas en LAN y HTTPS confiable para la cámara;
no se abre esa conexión automáticamente ni se alteran firewall/certificados.
La cámara en el navegador del propio PC puede funcionar en localhost.

## 4. Entrega a producción

Guardar y revisar los cambios en la rama de desarrollo. Publicar un commit
probado, con respaldo recuperable y una ventana acordada para producción.
Aplicar solo código y migraciones revisadas; conservar su MySQL, configuración,
archivos pendientes y sesiones según la compatibilidad de la versión. No
sustituirlos con los volúmenes locales. No iniciar pruebas destructivas allí.
Ver [flujo y diagnóstico de producción](PRUEBAS_Y_ESTADO_PRODUCCION.md).

Este repositorio prepara el instalador y el entorno; la instalación en tu PC
solo queda confirmada cuando el script termina y puedes entrar desde tu navegador.
