# Correos independientes por packing list y descarga del informe vigente

19/10/2026, Ecuador. Interfaz `20261019-52`.
Publicación: `itsanet-20261019-correos-embarques-52`.

## Uso para supervisores

1. Abre la recepción y selecciona **Finalizar**. Si tiene varios packing lists,
   se muestran sus nombres y se explica que habrá un correo por embarque.
   Confirma que deseas continuar. Si hay adicionales, asigna cada SKU al embarque
   al que pertenece antes de continuar. El cierre sigue siendo de la recepción
   completa; no se implementa un cierre parcial de embarques.
2. Revisa las referencias pendientes, los resultados y las fotos. Elige el
   informe original o ampliado: ambos entregan un Excel independiente por packing
   list. El informe auditable global sigue disponible en **Descargar informe**.
3. Indica los destinatarios propuestos. Se usan para inicializar los borradores
   que aún no tienen destino; se conserva lo editado por embarque.
4. Elige envío automático, preparación manual o declaración de correos enviados.
   Revisa cada correo por separado: asunto, destinatarios, novedades, imágenes y
   su documento. **Aprobar este correo de embarque** abre el siguiente.
5. Se cierra una sola recepción. En **Entregas** se puede consultar el estado de
   cada correo. Un mensaje confirmado no se vuelve a enviar en un reintento.
   Si Google no confirma el resultado, revisa Enviados antes de decidir.

### Descargas sin repetición

El cierre guarda los documentos sin iniciar descargas automáticas. Puedes
seleccionar **Descargar documentos finales** o ir a **Informes → Descargar
informe** en cualquier momento, con la recepción abierta o cerrada.

- Si no cambiaron los datos, formato o metadatos relevantes, se reutiliza la
  generación vigente: no hay otro Excel almacenado por cada clic.
- Si cambiaron, se genera una versión numerada actualizada y se conserva la anterior.
- Para varios packing lists se pregunta: **todos en un ZIP** o **un embarque**.
  Cada elección produce una sola descarga. El ZIP se arma temporalmente y no se
  almacena en la base de datos ni como otro informe.
- **Historial de informes** permite descargar versiones anteriores; el historial
  registra quién solicitó la descarga. Cancelar el selector no descarga nada.

### Envío manual

En **Correo final editable** se presenta una tarjeta por embarque. Abre cada
correo, copia el contenido o descarga el HTML y adjunta únicamente su documento.
Preparar la copia manual detiene los envíos automáticos pendientes de la recepción.
Los mensajes ya confirmados se conservan.

Una vez enviados todos los pendientes, selecciona **Registrar todos los correos
enviados manualmente** o la opción equivalente en Entregas. Debes confirmar cada
packing list después de verificar su mensaje y adjunto en Enviados. La declaración
queda atribuida al supervisor; no se presenta como acuse de Google.

## Separación de información y concurrencia

- Las cantidades declaradas se calculan desde las líneas del packing list y las
  físicas desde sus eventos activos. Los conteos anulados no participan.
- Las observaciones, pallets e incidencias se filtran por el origen del conteo.
  Se incluyen las correcciones de calidad del evento correspondiente.
- Un conteo antiguo de SKU compartido sin embarque bloquea el envío: se debe
  corregir su origen; no se reparte arbitrariamente entre correos.
- Un adicional se informa únicamente en el embarque asignado. Si la asignación
  contradice el origen explícito de su conteo, se pide corregirla.
- Las fotos con embarque se muestran en su correo. Las panorámicas generales
  pueden servir de contexto a varios embarques. Las fotos sin embarque de un SKU
  repetido se conservan en Drive y no se incluyen automáticamente: evita
  atribuirlas a una novedad de otro embarque.
- El cierre comprueba las versiones revisadas de cada borrador, el informe,
  destinatarios, fotos y eventos actuales, con bloqueo de la recepción. Si otro
  usuario modifica los datos, se solicita revisarlos de nuevo.
- Se conserva una sola entrega y una sola instantánea comprimida de datos por
  cierre. Las filas de cada correo guardan su redacción final y acuse, sin
  duplicar fotos binarias ni la instantánea completa de recepción.
- Cada correo usa una clave estable de 32 caracteres hexadecimales derivada de
  entrega y embarque. Es compatible con el puente Google actual. Si el primer
  embarque se confirma y falla el segundo, el reintento omite el primero.
- La recuperación explícita conserva los correos ya confirmados y exige revisar
  todos los pendientes. Una entrega declarada manualmente no se vuelve a programar.

## Compatibilidad y pase al servidor

No requiere nuevas tablas, credenciales, claves HMAC ni cambios de Apache/TLS.
Se conserva el puente Google con capacidad `correoEditable` ya exigido por la
versión anterior. No convierte entregas históricas agregadas en varios correos
ni las reenvía. La separación se aplica a los nuevos cierres con varios packing
lists. Las versiones antiguas de informe sin huella de contenido necesitan una
primera generación nueva antes de poder reutilizarse automáticamente.

El pase debe hacerse desde Linux **@apps**, con una pausa coordinada para que no
haya operadores registrando. Esta línea usa el respaldo privado y la comprobación
de salud del procedimiento existente; no copia la base ni credenciales de pruebas:

```bash
cd ~/bryan/IV_ITSANET && git fetch origin --tags && revision_itsanet="$(git rev-parse 'itsanet-20261019-correos-embarques-52^{commit}')" && git show "$revision_itsanet:scripts/actualizar_produccion.sh" > /tmp/itsanet-pase52.sh && bash /tmp/itsanet-pase52.sh "$PWD" "$revision_itsanet"
```

Después recarga el navegador y verifica sesión, recepción existente y versión
`20261019-52`. Revisa un correo de cada embarque antes de autorizar sus envíos.
La publicación del código en GitHub no actualiza por sí sola el servicio empresarial.

## Verificación

Suite general: 1.216 pruebas correctas. Comprobaciones MySQL complementarias:
54 correctas; pasada final de los casos de embarques: 11 correctas, incluyendo
dos finalizaciones simultáneas y un acuse incompleto. Verificación final de
páginas: 64 correctas. La comprobación
con Chromium y MySQL aislado cubre supervisor, permisos del operador, cierre
manual, revisión independiente, móvil de 390 px, ausencia de descarga automática
y recuperación del mismo informe en ZIP o por embarque. No usa correos ni
carpetas reales de producción.
