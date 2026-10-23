# URL operativa y publicador HTTPS · 23/10/2026

El usuario confirmó como URL final de trabajo:

`https://apps.flexnetuio.com:8443/app/`

Esta dirección determina protocolo, nombre, puerto y ruta; no identifica el
software que termina TLS o sirve de intermediario. La referencia a Apache en el
expediente del 18/10/2026 es histórica. El informe técnico v67 se corrigió para
dejar pendiente la identificación del publicador actual mediante evidencia del
servidor.

Desde el entorno de revisión, DNS devolvió un error de resolución y la petición
HTTPS falló porque el proxy rechazó el túnel con 403. No fue una respuesta de
ITSANET; no permite concluir que la aplicación esté caída ni identificar Apache.

En la terminal corporativa, consultar sin reiniciar ni modificar servicios:

```bash
getent hosts apps.flexnetuio.com
sudo ss -ltnp '( sport = :8443 or sport = :3002 )'
curl --connect-timeout 5 --max-time 15 -sS -I https://apps.flexnetuio.com:8443/app/
curl --connect-timeout 5 --max-time 15 -fsS https://apps.flexnetuio.com:8443/health
```

El proceso que escucha 8443, sus relaciones y la configuración del servidor
permiten identificar la entrada real. Una cabecera HTTP Server aislada es solo
indicativa. Si 8443 no escucha en esa máquina, revisar con TI el destino DNS y
la posible publicación en otra máquina o dispositivo antes de atribuirlo al
backend.

Esta revisión cambia únicamente documentación. No modifica la aplicación,
DNS, certificados, puertos, proxy ni servicio corporativo.
