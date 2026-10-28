# Servidor corporativo: referencia para nuevas migraciones

Preferencia explícita del responsable: utilizar **Apache y MySQL** como base de
la implementación de nuevos sistemas, conservando los servicios existentes.

## Evidencia recibida el 27/10/2026

Fuente: salidas de terminal compartidas por el usuario; no es una inspección
remota realizada desde este repositorio.

- Host: apps. Usuario de la terminal: enicolalde.
- Directorio de la consulta: /home/enicolalde/bryan.
- Dirección de la interfaz ens160 observada: 192.168.4.94.
- Primera captura: 2026-10-27T12:22:58-05:00.
- MySQL local: `8.0.46-0ubuntu0.24.04.4`, comentario `(Ubuntu)`.
  El resultado identifica la instancia consultada por el cliente local; no
  identifica por sí mismo la base o conexión efectiva de cada aplicativo.
- CPU lógicas disponibles para la consulta: 4 (`nproc`).
- RAM: 11 GiB totales, 9,6 GiB disponibles en la captura.
- Filesystem raíz: 73 GB totales, 19 GB usados, 50 GB disponibles, uso 28 %.

## Puertos y aplicaciones que deben conservarse

| Puerto | Servicio / ámbito observado |
| --- | --- |
| 22 TCP | SSH, IPv4/IPv6 |
| 80 TCP | Apache; itsanet-data-sync.conf |
| 443 TCP | Apache; itsanet-data-sync-ssl.conf |
| 8443 TCP | Apache; itsanet-app-8443.conf; aplicación ITSANET |
| 3002 TCP | Uvicorn; escucha 0.0.0.0 |
| 8080 TCP | itsanet-data-sync, contenedor saludable, binding 127.0.0.1 |
| 3306 TCP | MySQL, 127.0.0.1 |
| 33060 TCP | Listener adicional MySQL, 127.0.0.1 |
| 39653 / 40625 TCP | VS Code, loopback; valores puntuales |
| 53 TCP/UDP | Resolución DNS local |
| 68 UDP | DHCP en interfaz de red |

Virtual hosts del Apache compartido:

- `/etc/apache2/sites-enabled/itsanet-data-sync.conf`, puerto 80.
- `/etc/apache2/sites-enabled/itsanet-data-sync-ssl.conf`, puerto 443.
- `/etc/apache2/sites-enabled/itsanet-app-8443.conf`, puerto 8443.

No sustituir estos archivos para introducir otro sistema. Una nueva publicación
web se diseñará como virtual host con nombre y certificado apropiados, conservando
los destinos y comportamiento de los hosts actuales. Compartir 443 mediante
Apache es distinto de intentar que un segundo servidor escuche ese mismo puerto.

## Candidato para un backend adicional

`3003/TCP` no muestra escucha en la consulta proporcionada. Docker declara solo
8080 en el contenedor activo; el detenido `jovial_heyrovsky` tiene PortBindings
vacío y red bridge. Esto no reserva 3003 ni descarta configuraciones ajenas a Docker.

`pm2-root.service` está habilitado. La consulta posterior compartida de
`systemctl show` confirmó `ActiveState=inactive`, `SubState=dead` y el archivo
`/etc/systemd/system/pm2-root.service`. No está ejecutando aplicaciones en esa
captura; revisar configuraciones persistidas antes de asignar definitivamente
el puerto. Evitar comandos PM2 que puedan iniciar su daemon durante la auditoría.

## Criterio para el nuevo sistema

- Mantener Apache y MySQL existentes; no reinstalarlos ni reemplazarlos.
- Servicio y directorio propios; backend candidato ligado a loopback si es web.
- Base/schema y usuario MySQL propios con privilegios limitados a su alcance.
- Validar compatibilidad de la base y requisitos del sistema de origen antes de migrar.
- Definir dominio/ruta, certificado, respaldo, pruebas y ventana antes del pase.
- No detener ITSANET ni itsanet-data-sync para verificar un puerto.

UFW está inactivo, pero existen reglas nftables gestionadas por Docker. No vaciar
esas reglas ni inferir acceso externo a partir de un listener. Revisar conectividad
real desde la red usuaria y políticas de red antes de publicar el nuevo sistema.

Pendientes: sistema a migrar, tecnología/requisitos, configuración persistida de PM2,
reserva definitiva de puerto, publicación y capacidad bajo carga representativa.
