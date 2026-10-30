"""Guía operativa ilustrada y editable: un paso, una imagen o espacio de captura."""
from pathlib import Path
import argparse
import base64
import csv
import json
from html import escape as E

ROOT=Path(__file__).resolve().parents[1]
IMAGENES={
 'inicio':('v65/catalogo-confirmado.png','Inicio de supervisor · pruebas v65'),
 'recepciones':('v67/recepciones-fecha-filtros.png','Listado y filtros · pruebas v67'),
 'ficha':('v69/Cantidad-movil-sin-flechas.png','Ficha de validación móvil · pruebas v69'),
 'foto':('v64/camara-390x844.png','Captura de evidencia · pruebas v64'),
 'cero':('v69/Cero-guardado-escritorio.png','Ficha de un SKU con cero registrado · pruebas v69'),
 'pnc':('v65/avisos-supervisor-movil.png','Revisión de PNC sin imagen · pruebas v65'),
 'adjuntos':('v65/adjuntos-nombres-conservados.png','Documentos y nombres por adjunto · pruebas v65'),
 'destino':('v62/foto-destino-movil.png','Destino de una fotografía · pruebas v62')}


def pasos():
    # rol, título, pantalla/captura, acciones, resultado, atención, captura existente opcional
    return [
    ('Todos','Preparar el equipo y abrir el aplicativo','Navegador con la URL corporativa visible',[
      'Conecta el computador o handheld a la red autorizada de la bodega o VPN institucional. Abre Chrome compatible o el navegador aprobado.',
      'Escribe https://apps.flexnetuio.com:8443/app/ y espera la pantalla de acceso. En móvil, mantén el equipo con batería suficiente.',
      'Si vas a usar cámara, comprueba que el sitio tenga certificado confiable. El lector físico debe funcionar como teclado en el campo de código.'],
      'Se muestra Acceso, sin advertencias de certificado.','Si la URL no abre, ve al paso 38. No omitas una advertencia de seguridad del navegador.',None),
    ('Todos','Entrar con la cuenta propia','Acceso: Usuario o correo, Contraseña y Entrar',[
      'Escribe tu usuario o correo y la contraseña del aplicativo. Pulsa Entrar.',
      'Si tu organización tiene habilitado el acceso Google, usa la opción autorizada para tu cuenta. Iniciar sesión no autoriza por sí solo el envío desde Gmail.',
      'Si aún no tienes cuenta, solicita el alta o utiliza Registrarse según el procedimiento de la bodega; espera aprobación cuando corresponda.'],
      'Aparece Sesión iniciada con tu nombre y rol.','No compartas cuentas ni muestres contraseñas en las capturas. Si no puedes ingresar, solicita revisión de acceso.',None),
    ('Todos','Reconocer el inicio y elegir la tarea','Sesión iniciada: Recepciones, Validar y Mi cuenta y correo',[
      'Comprueba el nombre y rol mostrado. Si no corresponde a tu cuenta, cierra la sesión e ingresa correctamente.',
      'Para contar, abre Validar. Para revisar o preparar el ingreso, abre Recepciones. El supervisor puede ver acciones adicionales según permisos.',
      'Revisa Avisos cuando aparezca una cantidad pendiente. No cambies configuraciones que no correspondan a tu función.'],
      'Se abre la tarea elegida con la identidad correcta.','Si falta un botón esperado, consulta al supervisor o administrador. No intentes usar otra cuenta para obtener permisos.','inicio'),
    ('Operario','Buscar la recepción que vas a validar','Recepciones: filtros y acción Validar',[
      'Busca por código, cliente, descripción o embarque. Ajusta Estado y fechas si la recepción no aparece.',
      'Confirma el código completo y el cliente con la documentación física; no elijas una recepción solo por la fecha.',
      'Pulsa Validar en la recepción correcta. También puedes buscarla desde Validar → ¿Qué recepción vas a validar?'],
      'Se abre la recepción elegida y el campo Escanear.','Si la recepción está cerrada o el packing no está cargado, consulta al supervisor antes de registrar.','recepciones'),
    ('Operario','Consultar un producto con el lector físico','Campo Escanear y ficha del producto',[
      'Toca o haz clic en Escanear para dejar el cursor en el campo. Apunta el lector al código de barras de la pieza.',
      'Lee una vez y revisa el código recibido. Si el equipo no consulta automáticamente, pulsa Consultar o Enter según la pantalla.',
      'Comprueba que se abrió la ficha del SKU correcto. Escanear consulta el producto; todavía no registra unidades.'],
      'La ficha muestra SKU, descripción y cantidades.','No dispares varias lecturas para sumar unidades. La cantidad se escribe y se guarda explícitamente en el paso 12.',None),
    ('Operario','Consultar un producto con la cámara','Lector de cámara: Leer ahora y Apagar cámara',[
      'En el panel de lectura, pulsa Cámara y permite el uso de la cámara cuando lo solicite el navegador.',
      'Encuadra el código con buena luz y sin reflejos. Usa Leer ahora si está disponible; espera que aparezca la ficha del producto.',
      'Comprueba el SKU antes de continuar y utiliza Apagar cámara cuando termines de leer.'],
      'Se reconoce el código y se consulta el producto.','La cámara para leer códigos y la fotografía de evidencia son acciones distintas. Si falla, revisa el paso 39.',None),
    ('Operario','Revisar SKU, cantidades y packing de origen','Ficha: SKU, Declarado, Contado, Falta y origen',[
      'Compara SKU y descripción con la pieza. Lee Declarado, Contado y Falta antes de añadir un nuevo registro.',
      'Si aparece ¿De qué packing list es esta cantidad?, selecciona la lista a la que pertenecen las unidades que estás contando.',
      'Revisa los registros previos y ubicaciones. Si el SKU está en varias listas, no lo asignes por intuición.'],
      'Quedan identificados el producto y el origen del nuevo conteo.','Contado es un acumulado. La nueva cantidad se agrega mediante un registro; no se introduce el total anterior de nuevo.','ficha'),
    ('Operario','Escribir cantidad, pallet y posición reales','Cantidad a registrar, Pallet / subpallet y Posición real asignada',[
      'Cuenta físicamente las unidades de este registro y escribe solo esas unidades en Cantidad a registrar. Comprueba el valor; la ficha puede iniciar en 1.',
      'Escribe el identificador real en Pallet / subpallet y la Posición real asignada. Si el trabajo se distribuye en varios pallets, registra por separado las unidades de cada uno.',
      'Revisa la ubicación sugerida y confirma la ubicación real. Usa DP · directo a posición únicamente si corresponde a la operación física.'],
      'La cantidad queda asociada a su pallet/posición, lista y SKU.','No repitas todas las ubicaciones del SKU en un registro de un solo pallet. Para cero, utiliza el paso 13.','ficha'),
    ('Operario','Registrar una incidencia o producto no conforme','Estado físico: Registrar incidencia / PNC y unidades afectadas',[
      'Si hay unidades afectadas, elige Registrar incidencia / PNC y selecciona el Tipo de incidencia disponible.',
      'Indica el Pallet específico de la novedad y las Unidades con esta incidencia. La cantidad afectada debe ser mayor que cero y no superar la cantidad del conteo que registras.',
      'Describe lo observado. Ejemplo de trabajo: de 6 unidades, 2 PNC y 4 conformes en el mismo pallet. Si las otras unidades están en otro pallet, realiza otro registro.'],
      'Quedan diferenciadas las unidades conformes y las afectadas.','Faltantes y sobrantes se calculan respecto de lo esperado; no marques todo como PNC para representar un faltante. Adjunta evidencia cuando corresponda.',None),
    ('Operario','Tomar una fotografía para justificar la novedad','Fotos para este conteo → Tomar foto o Elegir de la galería',[
      'Despliega Fotos para este conteo. Pulsa Tomar foto para capturar una imagen nueva o Elegir de la galería para seleccionar un archivo.',
      'Encuadra la pieza y la condición que justifica la novedad. En la cámara de evidencia, confirma con Tomar y usar foto cuando se muestre esa opción.',
      'Revisa la vista previa y que la evidencia corresponde al SKU/registro actual. Continúa con Guardar conteo para registrar unidades y fotos juntas.'],
      'La foto seleccionada queda lista para registrarse con el conteo.','Una vista previa no confirma el guardado ni la copia Drive. Evita rostros, documentos personales y pantallas ajenas.','foto'),
    ('Operario','Guardar únicamente fotografías, sin añadir unidades','Guardar solo fotos · sin unidades',[
      'Abre el SKU correcto y selecciona o toma las fotografías que faltan para una novedad ya registrada.',
      'Pulsa Guardar solo fotos · sin unidades. Espera la confirmación; no pulses Guardar conteo si no vas a añadir unidades.',
      'En Ver fotos guardadas, comprueba que aparecen las evidencias y revisa su clasificación.'],
      'Se registran fotos sin incrementar la cantidad contada.','No vuelvas a introducir la cantidad del registro original para añadir una imagen: duplicaría unidades si se acepta un nuevo conteo.',None),
    ('Operario','Guardar el conteo y comprobar la confirmación','Guardar conteo y resultado del registro',[
      'Revisa una última vez SKU, lista, cantidad, pallet, posición, condición y fotografías.',
      'Pulsa Guardar conteo una sola vez y espera la respuesta. Comprueba el mensaje y el valor Contado actualizado.',
      'Si la respuesta se interrumpe, revisa la bitácora antes de repetir. Si el aplicativo ofrece reintentar el mismo registro, conserva esa identidad.'],
      'El registro aparece en el acumulado y en la bitácora con su autoría.','Una foto puede seguir pendiente de Drive después del guardado del conteo. No dupliques el registro para intentar resolver la foto.','ficha'),
    ('Operario','Declarar cero cuando no se encontraron unidades','Cantidad 0, Observación y confirmación',[
      'Busca físicamente la mercadería y consulta con el responsable antes de declarar ausencia.',
      'En la ficha del SKU escribe 0 y añade una observación que explique la revisión. Pulsa Guardar conteo y confirma la declaración cuando se solicite.',
      'Comprueba que el SKU quedó revisado. El cero no requiere pallet ni posición y no elimina cantidades registradas anteriormente.'],
      'Queda una declaración explícita de cero con motivo y autoría.','Un campo vacío no equivale a cero. Si ya hay cantidades erróneas, solicita corrección del registro; declarar cero no las resta.',None),
    ('Operario','Resolver un código que no se encuentra','Código no encontrado y búsqueda en packing list',[
      'Comprueba que el lector no añadió caracteres extra. Busca parte del SKU o la descripción en el packing list.',
      'Si identificas una etiqueta alternativa de un producto existente, consulta al supervisor antes de asociar códigos. La opción depende de permisos.',
      'Si es mercadería adicional, informa al supervisor y usa Registrar como adicional solo cuando esté autorizado y con la identificación/motivo correctos.'],
      'Se identifica el SKU existente o se deriva el caso para registrar el adicional correctamente.','No sustituyas el SKU por uno parecido ni crees un adicional para eludir una búsqueda fallida.',None),
    ('Operario','Consultar el avance y las novedades de la recepción','Recepción actual, filtros e indicadores',[
      'Abre Recepción actual para consultar las referencias y sus cantidades. Filtra por SKU o descripción.',
      'Revisa los estados e indicadores; una referencia revisada puede tener faltante o sobrante. Avance de revisión no significa que la cantidad sea correcta.',
      'Abre Novedades para revisar incidencias registradas y comunicar lo pendiente al supervisor.'],
      'Puedes distinguir trabajo revisado, diferencias y referencias pendientes.','Los faltantes de una recepción abierta son provisionales mientras otros operarios continúan registrando.',None),
    ('Operario','Revisar bitácora, registros y fotos guardadas','Bitácora, Historial y Ver fotos guardadas',[
      'Abre Bitácora desde Recepción actual o Historial desde la ficha, según la pantalla disponible.',
      'Comprueba fecha, usuario, cantidad, pallet/posición y origen del registro. Usa los filtros para localizarlo.',
      'Pulsa Ver fotos guardadas para revisar la evidencia del producto. Si detectas un error, identifica el registro concreto y solicita revisión.'],
      'El registro queda localizado para consulta o corrección autorizada.','No agregues un conteo negativo o un cero para compensar un error por tu cuenta.',None),
    ('Operario','Coordinar un SKU que otra persona está validando','Aviso de presencia en el SKU y revisión de datos',[
      'Lee el aviso y confirma con la otra persona qué unidades, pallets o listas está trabajando.',
      'Distribuyan físicamente el trabajo antes de guardar para evitar que ambos cuenten la misma mercadería.',
      'Si aparece un conflicto porque el registro cambió, actualiza la vista y revisa los datos vigentes antes de volver a confirmar.'],
      'Cada persona registra unidades distintas y conoce el estado actual.','El aviso de presencia ayuda a coordinar; no sustituye la comprobación física ni garantiza exclusividad sobre el SKU.',None),
    ('Operario','Terminar el turno y cerrar la sesión','Pendientes del registro y Cerrar sesión',[
      'Comprueba que tus últimos conteos aparecen en la bitácora y revisa si quedan fotos o borradores pendientes.',
      'Comunica al supervisor las novedades, evidencias pendientes y registros que requieren revisión.',
      'Cierra la ficha con cuidado si hay datos sin guardar y pulsa Cerrar sesión cuando corresponda. No borres los datos del navegador para limpiar el equipo.'],
      'El trabajo guardado queda identificado y los pendientes entregados al supervisor.','Si una ficha pregunta si deseas descartar un borrador, revisa antes de confirmar: sus campos o fotos podrían no estar guardados.',None),
    ('Supervisor','Revisar avisos y actualizar el catálogo','Avisos y Catálogo de Depot → Descargar catálogo',[
      'Al iniciar la jornada, revisa Avisos y la fecha de actualización del catálogo para el alcance autorizado.',
      'En Recepciones, usa Descargar catálogo si tienes permiso y la conexión está configurada. Espera la confirmación.',
      'Si falla la actualización o faltan productos, informa a ADMIN; no consideres actualizado un catálogo por haber pulsado el botón.'],
      'La consulta de productos usa el maestro disponible y sus pendientes están identificados.','No es una carga automática de mercancía en Depot. Configurar credenciales y reglas corresponde a ADMIN.',None),
    ('Supervisor','Crear una recepción','Nueva recepción y Crear recepción',[
      'En Recepciones, escribe un Código de recepción único y selecciona el Cliente correcto.',
      'Completa N° de bultos cuando corresponda y una Descripción que permita identificar los embarques.',
      'Verifica los datos antes de pulsar Crear recepción. Conserva el código para coordinar el trabajo de los operarios.'],
      'Se crea la cabecera y se habilita la carga del packing list.','El código no debe repetirse ni elegirse provisionalmente. El código y el cliente identifican registros existentes.',None),
    ('Supervisor','Seleccionar el archivo de packing list','Packing list: Archivo .xlsx y Embarque / nombre de la lista',[
      'En el panel de carga, selecciona el archivo Excel recibido y confirma a qué recepción pertenece.',
      'Revisa Embarque / nombre de la lista y los códigos detectados. Un archivo puede contener varios embarques.',
      'Espera el análisis y revisa la vista previa antes de guardar. No tomes una hoja auxiliar por la hoja de productos.'],
      'Se muestra una vista previa de las líneas del archivo correcto.','Si el sistema detecta contenido ya cargado, revisa la recepción y el origen antes de repetir la importación.',None),
    ('Supervisor','Revisar hoja, encabezado y columnas del archivo','Revisar qué columnas se leerán',[
      'Despliega Revisar qué columnas se leerán. Selecciona la Hoja y la Fila de encabezado en Excel.',
      'Verifica Código SKU y Cantidad declarada; revisa Descripción, Embarque y Contenedor cuando existan.',
      'Si cambiaste el mapeo, pulsa Aplicar formato y volver a analizar. Contrasta varias filas y totales con el archivo original.'],
      'El SKU y las cantidades de la vista previa corresponden al packing original.','No asumas que la primera fila o la primera hoja siempre son correctas. No guardes si las columnas están desplazadas.',None),
    ('Supervisor','Guardar el packing y habilitar la validación','Guardar packing list y resumen de recepción',[
      'Confirma nombre de lista, embarques, referencias y cantidades de la vista previa.',
      'Pulsa Guardar packing list y espera la respuesta. Comprueba la recepción en el listado y abre Validar para una revisión de muestra.',
      'Comunica a los operarios el código de recepción y el alcance de la lista que deben trabajar.'],
      'Las líneas esperadas quedan guardadas y disponibles para comparar con el conteo físico.','Las columnas y el orden original se conservan. Si detectas una carga incorrecta, utiliza la revisión autorizada; no borres registros sin analizar su impacto.',None),
    ('Supervisor','Agregar embarques y revisar datos de recepción','+ Embarque y Gestionar → Editar recepción / embarques',[
      'Usa + Embarque para añadir otra lista a la misma recepción cuando corresponda al flujo aprobado.',
      'Para cambiar datos permitidos, abre Gestionar → Editar recepción / embarques y revisa la descripción, embarques o total de bultos.',
      'Guarda y vuelve a consultar el listado. Si otro usuario modificó la recepción, actualiza y revisa la versión antes de repetir.'],
      'La recepción refleja los datos guardados y las listas correctas.','Retirar o separar un embarque puede afectar conteos/evidencias vinculadas: no lo uses como una edición rutinaria sin revisión.',None),
    ('Supervisor','Revisar bultos y corregir su total físico','Gestionar → Bultos y fotos; Total de bultos',[
      'Abre Bultos y fotos desde la recepción. Comprueba el total declarado y las unidades logísticas registradas.',
      'Si debes corregir el total físico, usa la edición disponible del total y escribe la cantidad real consolidada.',
      'Guarda y vuelve a abrir para comprobar la persistencia. Si una reducción afecta bultos ocupados, resuelve la distribución antes de insistir.'],
      'El total de bultos coincide con lo físico y con los registros conservados.','Solo se pueden retirar bultos finales vacíos y sin vínculos que lo impidan. No fuerces una reducción borrando evidencia.',None),
    ('Supervisor','Imprimir etiquetas completas o una selección','Etiquetas de bultos: formato, selección y vista previa',[
      'Abre Etiquetas de bultos y revisa Literal y Total confirmado. Selecciona el tamaño disponible: 100 × 50 o 100 × 150 mm.',
      'Para una impresión parcial, elige Solo números o rangos seleccionados y escribe, por ejemplo, 1-5, 8. Verifica la vista previa y la numeración original.',
      'Confirma el destino y la impresión según las opciones disponibles. Imprime al 100 %, sin márgenes ni encabezados, y prueba lectura de una etiqueta antes de continuar el lote.'],
      'Se imprimen únicamente las etiquetas elegidas, con código escaneable.','La selección de impresión no cambia el total de bultos. La ficha del SKU tiene una opción Etiqueta independiente cuando está disponible.',None),
    ('Supervisor','Monitorear avance y operarios trabajando','Recepciones: Avance; ficha del SKU y presencia',[
      'Filtra la recepción por código, estado o fecha de registro. Revisa referencias, declarado, contado y avance.',
      'Abre la validación para consultar los SKU y las personas que intervienen. Revisa el aviso de presencia cuando varias personas trabajan un mismo código.',
      'Coordina unidades/pallets y pendientes con el equipo. Si el tablero no se actualiza, comprueba conexión y estado antes de tomar una decisión.'],
      'El seguimiento combina avance de revisión, cantidades y responsables.','Un 100 % revisado puede incluir faltantes o sobrantes; no significa coincidencia exacta de cantidades.','recepciones'),
    ('Supervisor','Revisar faltantes, sobrantes y PNC','Avisos / Novedades y detalle del SKU',[
      'Abre Avisos o Novedades y filtra la condición que vas a revisar.',
      'Contrasta esperado, contado y registros por origen/pallet. En PNC, confirma unidades afectadas, observación y evidencia.',
      'Si no hay imágenes, solicita su registro. Marcar un aviso como revisado no corrige cantidades ni elimina la novedad.'],
      'La diferencia está explicada y tiene responsable y evidencia cuando corresponde.','Mientras la recepción siga abierta, revisa si otro operario está registrando antes de confirmar una diferencia definitiva.','pnc'),
    ('Supervisor','Corregir un registro de conteo autorizado','Corregir conteo → ¿Qué registro corregir? → Guardar corrección',[
      'Localiza el SKU y su historial. Si hay varios conteos, selecciona el registro específico por cantidad, pallet, origen, usuario y fecha.',
      'Edita los datos necesarios y completa Motivo de corrección. Revisa también condición, unidades afectadas y ubicación.',
      'Pulsa Guardar corrección y comprueba la bitácora y el acumulado. El registro original queda trazable en auditoría.'],
      'Se sustituye el registro elegido conservando el historial del cambio.','No se corrige el total de todos los pallets como si fuera un solo registro. Ante conflicto de versión, actualiza y revisa otra vez.',None),
    ('Supervisor','Clasificar imágenes de recepción y novedades','Fotos: recepción, embarque, tipo y SKU/bulto',[
      'Abre las fotos desde la recepción o desde el SKU, según la evidencia que vas a registrar o revisar.',
      'Al seleccionar nuevas imágenes, confirma recepción/embarque, tipo de foto, SKU y bulto/caja cuando correspondan. Revisa cada destino antes de guardar.',
      'Conserva PRE-INGRESO para prerecepción, la categoría de producto/incidencia correcta y fotos finales para el estado final. Si no puedes asignar un embarque, resuelve el pendiente sin adivinarlo.'],
      'Cada evidencia queda vinculada al contexto que realmente documenta.','Una fotografía general no debe atribuirse a un SKU concreto sin justificación. Revisa las variantes de la pantalla actual.','destino'),
    ('Supervisor','Comprobar carpeta, fotos finales y enlaces Drive','Comprobar carpetas e imágenes / Ver fotos guardadas / Drive',[
      'Comprueba los estados de copia y abre el enlace de carpeta de la recepción o del grupo correcto.',
      'Revisa fotos finales y evidencias de las novedades; verifica que sus enlaces abren con los permisos del destinatario autorizado.',
      'Confirma el árbol lógico: recepción → embarque → categoría → SKU, cuando aplique. INFORMES queda bajo la recepción; las categorías se crean al usarse.'],
      'Las evidencias necesarias están confirmadas y vinculadas al informe correcto.','No precrees carpetas ni borres rutas históricas para limpiar la vista. Una carga fallida puede dejar una ruta vacía que requiere revisión.',None),
    ('Supervisor','Conectar la cuenta que enviará el correo','Mi cuenta y correo → Conectar con Google',[
      'Abre Mi cuenta y correo y comprueba el correo vinculado a tu usuario.',
      'Pulsa Conectar con Google y selecciona esa cuenta. Revisa los permisos requeridos y completa la autorización institucional.',
      'Usa la comprobación de acceso a Gmail disponible. Si el cliente OAuth no está configurado o la cuenta no corresponde, solicita revisión de ADMIN.'],
      'La cuenta correcta queda autorizada para la operación de correo.','La conexión central no exige crear un Apps Script por supervisor. Escribir otro remitente no autoriza enviar desde otro buzón.',None),
    ('Supervisor','Elegir cómo separar los correos','Organizar correos: packing list, embarque o recepción',[
      'En el flujo de informes/cierre, revisa cómo se agruparán los correos: uno por packing list, por embarque o uno consolidado.',
      'Comprueba que las filas y los adicionales pertenecen al grupo correcto. Resuelve asignaciones sin embarque antes de continuar.',
      'Abre cada borrador para revisar destinatarios, novedades y documentos de su propio grupo.'],
      'Cada informe y correo contienen solo el alcance seleccionado.','Un packing list puede contener varios embarques. No confundir el archivo original con el criterio de agrupación del correo.',None),
    ('Supervisor','Preparar y descargar los informes para revisión','Documentos finales y envío → Preparar y descargar documentos',[
      'Abre Correo final editable desde Informes o el borrador del grupo que vas a preparar.',
      'Pulsa Preparar y descargar documentos o la opción de preparación que muestre la revisión. Espera el resultado y abre el archivo descargado.',
      'Comprueba SKU, cantidades numéricas, novedades, pallet/posición y evidencia. El ejecutivo recibe identificadores limpios y detalle final de unidades/PNC; el informe de auditoría puede tener mayor desglose.'],
      'El documento revisado corresponde al grupo y a los datos vigentes.','Si el navegador bloquea descargas, usa el botón individual del archivo. CSV para Depot es otro formato autorizado, no el CSV de comparación de tiempos de la presentación.','adjuntos'),
    ('Supervisor','Seleccionar adjuntos y editar su nombre final','Adjuntar informe y Nombre para descargar y enviar',[
      'Marca Adjuntar informe únicamente en los documentos que deben acompañar ese correo.',
      'Edita el nombre en la casilla de cada archivo, conservando la extensión .xlsx. Si hay dos informes, revisa ambos nombres por separado.',
      'Usa Descargar seleccionados o la descarga individual para comprobar los archivos. Revisa otra vez la selección antes del envío.'],
      'Se conservan los nombres finales de los adjuntos elegidos.','Renombrar una descarga no cambia los datos originales. Si preparas una revisión nueva, comprueba qué documentos están vigentes y seleccionados.','adjuntos'),
    ('Supervisor','Revisar destinatarios, novedades y cuerpo del correo','Editor del correo: destinatarios, asunto y contenido',[
      'Confirma los destinatarios y el asunto. Revisa las novedades del grupo y los enlaces de evidencia; no incluyas información de otro embarque o cliente.',
      'Si corresponde responder al correo original, busca o vincula el mensaje correcto con las opciones disponibles y comprueba el hilo.',
      'Guarda los cambios del editor y verifica que la selección de informes y sus nombres siguen siendo correctos.'],
      'El borrador está listo para su revisión final y envío.','El correo puede abrirse como nuevo si no se vinculó un original. Un borrador guardado todavía no es un mensaje enviado.',None),
    ('Supervisor','Enviar, verificar la entrega y cerrar correctamente','Enviar correo / Finalizar / Entregas',[
      'Desde el flujo autorizado pulsa Enviar correo o continúa con Finalizar cuando hayas completado la revisión que solicita la pantalla.',
      'Si quedan referencias sin revisar, regístralas incluyendo cero con observación cuando corresponda. Revisa las confirmaciones antes de aceptar el cierre/envío.',
      'Comprueba el resultado en Entregas. Si queda pendiente, aplica el paso 40. Para correos ya enviados fuera del aplicativo, usa Cerrar · correos ya enviados solo con evidencia y confirmación real de todos los grupos.'],
      'La entrega confirmada y el estado de recepción son coherentes con lo realizado.','Cerrar · correos ya enviados registra un cierre externo y detiene automatismos pendientes; no envía otro correo. No lo uses como sustituto de una entrega fallida.',None),
    ('Ayuda','Resolver falta de conexión o una vista desactualizada','Mensaje de conexión, sesión y recepción actual',[
      'Comprueba la red autorizada y si otros equipos pueden abrir la URL. Si la sesión venció, vuelve a ingresar.',
      'Conserva borradores y fotos pendientes. Revisa si el último registro ya aparece antes de repetir una acción de guardado.',
      'Actualiza la vista cuando sea seguro hacerlo y comunica al supervisor hora, recepción/SKU y mensaje observado. No reinicies servicios ni cambies la configuración del equipo por tu cuenta.'],
      'Se identifica el alcance del problema y se conserva el trabajo pendiente.','Una pantalla de acceso visible puede provenir de caché; no demuestra por sí sola que el servidor esté respondiendo.',None),
    ('Ayuda','Resolver problemas de cámara o botones en handheld','Permisos de cámara y Comprobar cámara y versión en este dispositivo',[
      'Comprueba el certificado HTTPS, el permiso de cámara del navegador y que otra aplicación no esté utilizando la cámara.',
      'Desde Información del escáner, abre Comprobar cámara y versión en este dispositivo si está disponible. Revisa el resultado y comunícalo al supervisor.',
      'Si no puedes leer, usa el lector físico o la entrada manual autorizada. Si el problema es de captura, conserva el conteo y sigue el procedimiento para añadir fotos después.'],
      'El problema queda identificado sin perder los registros ya guardados.','No instales aplicaciones ni habilites depuración del equipo sin autorización. Guardar solo fotos sirve para completar evidencia sin repetir unidades.',None),
    ('Ayuda','Resolver fotografías o correos pendientes','Entregas e imágenes pendientes / Revisar fotos pendientes',[
      'Abre el seguimiento de pendientes y distingue foto guardada localmente, copia en proceso, revisión y copia confirmada.',
      'Conserva la imagen original y revisa cuenta, destino y mensaje. Usa el reintento del mismo elemento cuando esté habilitado; si requiere configuración, escala a ADMIN.',
      'Para correo pendiente, revisa la entrega y Enviados de la cuenta antes de repetir. Conserva la referencia, hora y mensaje para seguimiento.'],
      'El pendiente se recupera o queda escalado con información suficiente.','No vuelvas a contar unidades ni envíes el correo como uno nuevo para ocultar un pendiente. Una miniatura no confirma Drive.',None)
    ]


CSS='''
:root{--ink:#17324d;--blue:#225de2;--line:#dce5ef;--soft:#edf4ff;--muted:#526781}*{box-sizing:border-box}body{margin:0;background:#eef2f7;color:var(--ink);font:16px/1.55 system-ui,Arial,sans-serif}a{color:var(--blue)}header{padding:28px;background:#102b46;color:white}h1{font-size:36px;line-height:1.15}h2{font-size:26px;line-height:1.25}button,.file{padding:10px 13px;border:1px solid var(--line);border-radius:8px;background:white;color:var(--ink);font:600 13px system-ui;cursor:pointer}button:focus-visible,a:focus-visible{outline:3px solid #85b2ff}.toolbar{display:flex;gap:8px;flex-wrap:wrap}.layout{display:grid;grid-template-columns:260px minmax(0,1fr);max-width:1350px;margin:22px auto;gap:22px;padding:0 18px}nav{align-self:start;position:sticky;top:12px;max-height:95vh;overflow:auto;background:white;padding:18px;border-radius:12px}nav a{display:block;text-decoration:none;font-size:13px;padding:6px 0}nav input{width:100%;padding:10px;font:inherit;border:1px solid var(--line);border-radius:6px}.content{min-width:0}.cover,.indice,.step{background:white;padding:28px;border:1px solid var(--line);border-radius:12px;margin:0 0 22px;scroll-margin-top:15px}.tag{color:#176b79;text-transform:uppercase;letter-spacing:1px;font-size:12px;font-weight:700}.screen{background:var(--soft);padding:12px;border-radius:8px}li{margin:10px 0}.result,.attention{padding:12px 15px;margin:12px 0;border-left:4px solid #15977a;background:#f0faf6}.attention{border-color:#c08000;background:#fff8e6}.visual{border:1px solid var(--line);border-radius:10px;margin:18px 0;padding:12px;text-align:center}.visual img{max-width:100%;max-height:420px;object-fit:contain}.placeholder{display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:300px;border:2px dashed #a7b9d1;background:#f8fafc;padding:20px;color:var(--muted)}.placeholder strong{font-size:20px;margin:10px}.placeholder p{max-width:620px}figcaption{font-size:12px;color:var(--muted);margin:8px}.edit{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:10px 0}.edit input{max-width:100%}.links{display:flex;justify-content:space-between;gap:10px;margin:18px 0;font-size:13px}.indice a{display:block;padding:4px 0;font-size:13px}.columns{columns:2;column-gap:28px}.small{font-size:13px;color:var(--muted)}.checklist li{margin:6px 0}.printonly{display:none}[hidden]{display:none!important}footer{font-size:12px;color:var(--muted);padding:20px;text-align:center}@media(max-width:850px){.layout{grid-template-columns:1fr}nav{position:static;max-height:none}.columns{columns:1}.step{padding:20px}h1{font-size:30px}}@media print{@page{size:A4;margin:14mm 13mm 17mm}body{background:white;font:10pt/1.45 Arial,sans-serif;color:#142d46}header,nav,.toolbar,.edit,.links,.noprint,footer{display:none!important}.layout{display:block;max-width:none;margin:0;padding:0}.cover,.indice,.step{border:0;border-radius:0;padding:0;margin:0;break-after:page}.step:last-child{break-after:auto}.step{break-before:page;break-inside:avoid}h1{font-size:27pt}h2{font-size:18pt;line-height:1.2;margin:4mm 0}h3{font-size:13pt}.tag{font-size:8pt}.screen{padding:2.5mm;font-size:9pt}li{margin:3mm 0}.result,.attention{padding:2.5mm;margin:3mm 0;font-size:9pt}.visual{padding:2mm;margin:4mm 0;break-inside:avoid}.visual img{width:auto;max-width:100%;height:92mm;object-fit:contain}.placeholder{min-height:92mm;font-size:9pt}.placeholder strong{font-size:14pt}.placeholder p{margin:3mm 0}.placeholder small{font-size:8pt}figcaption{font-size:8pt;margin:2mm}.small{font-size:8.5pt}.columns{columns:2;column-gap:9mm}.indice a{font-size:9pt;padding:1.1mm 0;text-decoration:none;color:inherit}.printonly{display:block}.cover .checklist{font-size:11pt}.cover{padding-top:12mm}.cover p{font-size:11pt}}
'''

JS=r'''
const pasos=[...document.querySelectorAll('.step')];
const estado=document.querySelector('#estado');
const norm=t=>t.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
document.querySelector('#buscar').oninput=e=>{const q=norm(e.target.value);for(const s of pasos)s.hidden=!norm(s.textContent).includes(q);};
document.querySelector('#ver-todo').onclick=()=>{document.querySelector('#buscar').value='';pasos.forEach(s=>s.hidden=false);};
document.querySelector('#imprimir').onclick=()=>window.print();let ocultos;
addEventListener('beforeprint',()=>{ocultos=pasos.map(x=>x.hidden);pasos.forEach(x=>x.hidden=false);});addEventListener('afterprint',()=>{if(ocultos)pasos.forEach((x,i)=>x.hidden=ocultos[i]);});
document.querySelectorAll('[data-captura]').forEach(input=>input.onchange=async()=>{const s=input.closest('.step'),f=input.files[0];if(!f)return;if(!['image/png','image/jpeg','image/webp'].includes(f.type)||f.size>8*1024*1024){estado.textContent='Usa PNG, JPG o WebP de hasta 8 MB.';return;}const data=await new Promise((res,rej)=>{const r=new FileReader();r.onload=()=>res(r.result);r.onerror=rej;r.readAsDataURL(f);});const img=s.querySelector('.visual img');img.src=data;img.hidden=false;s.querySelector('.placeholder').hidden=true;s.querySelector('figcaption').textContent='Captura añadida por el responsable para este paso. Revisar información antes de distribuir.';estado.textContent='Captura incorporada al paso '+s.dataset.paso+'. Descarga el HTML para conservar los cambios.';});
document.querySelector('#descargar').onclick=()=>{const d=document.documentElement.cloneNode(true);d.querySelectorAll('.step').forEach(x=>x.hidden=false);d.querySelector('#buscar').setAttribute('value','');d.querySelectorAll('input[type=file]').forEach(x=>x.removeAttribute('value'));d.querySelector('#estado').textContent='Revisa las capturas antes de distribuir: no incluir contraseñas, tokens ni datos ajenos al procedimiento.';const u=URL.createObjectURL(new Blob(['<!doctype html>\n'+d.outerHTML],{type:'text/html;charset=utf-8'})),a=document.createElement('a');a.href=u;a.download='Manual-usuario-completo-IV-ITSANET.html';a.click();setTimeout(()=>URL.revokeObjectURL(u),5000);estado.textContent='HTML descargado con las imágenes incorporadas. Ábrelo para imprimir el PDF completo.';};
'''


def main():
    p=argparse.ArgumentParser();p.add_argument('--salida',type=Path,required=True);a=p.parse_args();a.salida.mkdir(parents=True,exist_ok=True);(a.salida/'capturas').mkdir(exist_ok=True)
    src=ROOT/'docs/manual-usuario-completo-20261030/capturas'
    img={}
    for key,(path,caption) in IMAGENES.items():
        target=a.salida/'capturas'/Path(path).name
        if not target.exists():
            original=src/Path(path).name
            if not original.exists():original=Path('/workspace/revisiones')/path
            target.write_bytes(original.read_bytes())
        img[key]=('data:image/png;base64,'+base64.b64encode(target.read_bytes()).decode(),caption)
    datos=pasos();assert len(datos)==40
    indice=''.join('<a href="#paso-'+str(i)+'">'+str(i).zfill(2)+' · '+E(x[1])+'</a>' for i,x in enumerate(datos,1))
    cuerpo='';inventario=[]
    for i,(rol,titulo,pantalla,acciones,resultado,atencion,key) in enumerate(datos,1):
        ident='paso-'+str(i);has=key is not None
        image,caption=img[key] if has else ('','Captura pendiente de incorporar para este paso.')
        inventario.append({'paso':i,'rol':rol,'titulo':titulo,'capturaSolicitada':pantalla,'incluida':has,'archivo':Path(IMAGENES[key][0]).name if has else ''})
        cuerpo+='<section class="step" id="'+ident+'" data-paso="'+str(i)+'"><div class="tag">Paso '+str(i).zfill(2)+' de 40 · '+E(rol)+'</div><h2>'+E(titulo)+'</h2><p class="screen"><b>Dónde:</b> '+E(pantalla)+'</p><ol>'+''.join('<li>'+E(t)+'</li>' for t in acciones)+'</ol><div class="result"><b>Comprueba:</b> '+E(resultado)+'</div><figure class="visual"><img '+('src="'+image+'"' if has else 'hidden')+' alt="'+E(pantalla)+'"><div class="placeholder" '+('hidden' if has else '')+'><span>IV ITSANET · GUÍA VISUAL</span><strong>Espacio para captura · paso '+str(i).zfill(2)+'</strong><p>'+E(pantalla)+'</p><small>Mostrar los controles utilizados y su resultado. Evitar datos personales, contraseñas y contenido de otros clientes.</small></div><figcaption>'+E(caption)+'</figcaption></figure><div class="attention"><b>Ten en cuenta:</b> '+E(atencion)+'</div><div class="edit"><label>Agregar o reemplazar captura <input data-captura type="file" accept="image/png,image/jpeg,image/webp"></label></div><div class="links"><a href="#'+('paso-'+str(i-1) if i>1 else 'indice')+'">← Anterior</a><a href="#indice">Índice</a><a href="#'+('paso-'+str(i+1) if i<40 else 'indice')+'">Siguiente →</a></div></section>'
    portada='''<section class="cover"><div class="tag">Guía operativa · 30/10/2026 · edición 2.0</div><h1>IV ITSANET</h1><h2>Ingreso &amp; Validación Itsanet</h2><h3>Manual de usuario paso a paso</h3><p>Guía para operarios y supervisores: desde el acceso y el conteo hasta la revisión de evidencias y la entrega del informe.</p><ul class="checklist"><li><b>Todos:</b> pasos 01–03, acceso y orientación.</li><li><b>Operario:</b> pasos 04–18, consulta, conteo, novedad y evidencia.</li><li><b>Supervisor:</b> pasos 19–37, recepción, packing, revisión e informes.</li><li><b>Ayuda:</b> pasos 38–40, conexión, cámara y pendientes.</li></ul><p><b>Una guía visual por paso.</b> Se incluyen capturas de pruebas cuando están disponibles. Los espacios restantes indican exactamente qué pantalla incorporar; no representan una pantalla inexistente del aplicativo.</p><p>En el HTML puedes agregar una captura en cada paso y descargar la versión completada. Después usa Imprimir / PDF. Los archivos se procesan en tu equipo y no se suben al servidor.</p><p class="small">Referencia funcional: v69 · recursos 20261024-69. Los nombres y opciones corresponden al código revisado; su disponibilidad depende del rol y permisos. Las capturas existentes son de pruebas con datos sintéticos y señalan su versión. No es un manual de administración del servidor.</p><p><b>Acceso:</b> https://apps.flexnetuio.com:8443/app/</p></section>'''
    h='<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>IV ITSANET · Manual de usuario completo</title><style>'+CSS+'</style></head><body><header><b>IV ITSANET · Manual de usuario completo</b><p>Guía visual para operarios y supervisores</p><div class="toolbar"><button id="imprimir">Imprimir / PDF</button><button id="descargar">Descargar HTML con mis capturas</button></div><p class="small" id="estado" style="color:#d3e3f4">Revisa las capturas antes de distribuir: no incluir contraseñas, tokens ni datos ajenos al procedimiento.</p></header><main class="layout"><nav><b>Buscar en la guía</b><input id="buscar" type="search" aria-label="Buscar pasos" placeholder="Ej.: cero, PNC, correo"><button id="ver-todo">Ver todos los pasos</button><a href="#portada">Inicio</a>'+indice+'</nav><div class="content"><div id="portada">'+portada+'</div><section class="indice" id="indice"><h2>Índice de pasos</h2><div class="columns">'+indice+'</div></section>'+cuerpo+'</div></main><footer>IV ITSANET · Guía operativa · 30 de octubre de 2026</footer><script>'+JS+'</script></body></html>'
    (a.salida/'Manual-usuario-completo-IV-ITSANET.html').write_text(h)
    (a.salida/'Inventario-de-capturas.json').write_text(json.dumps(inventario,ensure_ascii=False,indent=2))
    with (a.salida/'Lista-capturas-por-completar.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(['Paso','Rol','Tema','Pantalla a capturar'])
        for x in inventario:
            if not x['incluida']:w.writerow([x['paso'],x['rol'],x['titulo'],x['capturaSolicitada']])
    print(json.dumps({'pasos':len(datos),'conCaptura':sum(x['incluida'] for x in inventario),'conEspacio':sum(not x['incluida'] for x in inventario),'salida':str(a.salida)}))


if __name__=='__main__':main()
