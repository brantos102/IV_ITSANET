/** Esquemas de ambas hojas de los modelos Depot entregados. Sin filas de ejemplo. */
export const MODELOS_DEPOT = [
  {
    "id": "CANTIDADES",
    "nombre": "Alta masiva de cantidades",
    "descripcion": "Modelo oficial: 18 columnas. Completar obligatorios antes de cargar en Depot.",
    "archivo": "alta-cantidades",
    "separador": ",",
    "hoja": "Modelo a Utilizar",
    "columnas": [
      {
        "encabezado": "CODIGO PRODUCTO",
        "campo": "sku",
        "obligatorio": true,
        "tipo": "Alfanumérico",
        "longitud": 30.0,
        "ayuda": "Indica el codigo del Producto ingresado, debe estar previamente cargado.",
        "valor": ""
      },
      {
        "encabezado": "CANTIDAD",
        "campo": "cantidad",
        "obligatorio": true,
        "tipo": "Numérico",
        "longitud": "20 (para enteros)   5 (para decimales)",
        "ayuda": "Indica la cantidad de existencia de un producto que tengan algún atributo en particular y que se encuentra en una posición.",
        "valor": ""
      },
      {
        "encabezado": "CODIGO UNIDAD",
        "campo": "unidad",
        "obligatorio": true,
        "tipo": "Alfanumérico",
        "longitud": 5.0,
        "ayuda": "Indica el codigo de unidad. El dato a cargar en este campo debe estar previamente cargado en el Maestro de Producto",
        "valor": ""
      },
      {
        "encabezado": "NRO LOTE",
        "campo": "lote",
        "obligatorio": false,
        "tipo": "Alfanumérico",
        "longitud": 50.0,
        "ayuda": "Información transaccional que indica un atributo para determinada mercadería en stock",
        "valor": ""
      },
      {
        "encabezado": "LOTE PROVEEDOR",
        "campo": "loteProveedor",
        "obligatorio": false,
        "tipo": "Alfanumérico",
        "longitud": 50.0,
        "ayuda": "Información transaccional que indica un atributo para determinada mercadería en stock",
        "valor": ""
      },
      {
        "encabezado": "NRO PALLET",
        "campo": "pallet",
        "obligatorio": false,
        "tipo": "Alfanumérico",
        "longitud": 100.0,
        "ayuda": "Información transaccional que indica un atributo para determinada mercadería en stock",
        "valor": ""
      },
      {
        "encabezado": "FECHA VENCIMIENTO",
        "campo": "vencimiento",
        "obligatorio": false,
        "tipo": "Date",
        "longitud": "ddmmaaaa",
        "ayuda": "Información transaccional que indica un atributo para determinada mercadería en stock",
        "valor": ""
      },
      {
        "encabezado": "CODIGO CATEGORIA LÓGICA",
        "campo": "categoria",
        "obligatorio": true,
        "tipo": "Alfanumérico",
        "longitud": 50.0,
        "ayuda": "Indica la Categoría Lógica que posee el producto en stock. La categoría logica a ingresar tiene que estar previamente cargada en la tabla de Categoría Lógica",
        "valor": ""
      },
      {
        "encabezado": "CODIGO ESTADO DE LA MERCADERIA",
        "campo": "estado",
        "obligatorio": true,
        "tipo": "Alfanumérico",
        "longitud": 15.0,
        "ayuda": "Indica el Estado de la Mercadería que posee el producto en stock. El Estado de Mercadería a ingresar tiene que estar previamente cargado en la tabla de Estado de Mercadería",
        "valor": ""
      },
      {
        "encabezado": "NAVE",
        "campo": "nave",
        "obligatorio": true,
        "tipo": "Alfanumérico",
        "longitud": 15.0,
        "ayuda": "Informar en que Nave se encuentra el producto",
        "valor": ""
      },
      {
        "encabezado": "CALLE",
        "campo": "calle",
        "obligatorio": true,
        "tipo": "Alfanumérico",
        "longitud": 15.0,
        "ayuda": "Informar en que Calle se encuentra el producto",
        "valor": ""
      },
      {
        "encabezado": "COLUMNA",
        "campo": "columna",
        "obligatorio": true,
        "tipo": "Numerico",
        "longitud": "20(solo nros enteros)",
        "ayuda": "Intormar en que Columna se encuentra el producto",
        "valor": ""
      },
      {
        "encabezado": "NIVEL",
        "campo": "nivel",
        "obligatorio": false,
        "tipo": "Numerico",
        "longitud": "20(solo nros enteros)",
        "ayuda": "Informar en que nivel se encuentra el producto",
        "valor": ""
      },
      {
        "encabezado": "PROFUNDIDAD",
        "campo": "profundidad",
        "obligatorio": false,
        "tipo": "Numerico",
        "longitud": "9(solo nros enteros)",
        "ayuda": "Informar en que profundidad se encuentra el producto. ",
        "valor": ""
      },
      {
        "encabezado": "PROP 3",
        "campo": "prop3",
        "obligatorio": false,
        "tipo": "Alfanumérico",
        "longitud": 100.0,
        "ayuda": "Información transaccional que indica un atributo para determinada mercadería en stock",
        "valor": ""
      },
      {
        "encabezado": "NRO CONTENEDORA",
        "campo": "contenedora",
        "obligatorio": false,
        "tipo": "Alfanumérico",
        "longitud": 50.0,
        "ayuda": "Información transaccional que indica un atributo para determinada mercadería en stock",
        "valor": ""
      },
      {
        "encabezado": "NRO PARTIDA",
        "campo": "partida",
        "obligatorio": false,
        "tipo": "Alfanumérico",
        "longitud": 50.0,
        "ayuda": "Información transaccional que indica un atributo para determinada mercadería en stock",
        "valor": ""
      },
      {
        "encabezado": "NRO SERIE",
        "campo": "serie",
        "obligatorio": false,
        "tipo": "Alfanumérico",
        "longitud": 50.0,
        "ayuda": "Información transaccional que indica un atributo para determinada mercadería en stock",
        "valor": ""
      }
    ]
  },
  {
    "id": "PRODUCTOS",
    "nombre": "Alta de productos nuevos",
    "descripcion": "Modelo oficial: 38 columnas. Completar obligatorios antes de cargar en Depot.",
    "archivo": "alta-productos",
    "separador": ",",
    "hoja": "Modelo a Utilizar",
    "columnas": [
      {
        "encabezado": "CODIGO CLIENTE",
        "campo": "cliente",
        "obligatorio": true,
        "tipo": "Alfanumérico",
        "longitud": 15.0,
        "ayuda": "Indica el codigo de cliente Depot WMS, debe estar previamente cargado.",
        "valor": ""
      },
      {
        "encabezado": "CODIGO PRODUCTO",
        "campo": "sku",
        "obligatorio": true,
        "tipo": "Alfanumérico",
        "longitud": 30.0,
        "ayuda": "Indica el codigo de producto que se desea ingresar.",
        "valor": ""
      },
      {
        "encabezado": "VALIDACION VTO.",
        "campo": "",
        "obligatorio": false,
        "tipo": "Numérico",
        "longitud": 20.0,
        "ayuda": "Indica la anticipacion con la que se validaran los vencimientos.",
        "valor": ""
      },
      {
        "encabezado": "DESCRIPCION",
        "campo": "descripcion",
        "obligatorio": true,
        "tipo": "Alfanumérico",
        "longitud": 200.0,
        "ayuda": "Descripcion del producto.",
        "valor": ""
      },
      {
        "encabezado": "FRACCIONABLE",
        "campo": "",
        "obligatorio": true,
        "tipo": "Alfanumérico",
        "longitud": 1.0,
        "ayuda": "Indica con 0 si no es fraccionable, 1 para que sea fraccionable.",
        "valor": ""
      },
      {
        "encabezado": "CODIGO UNIDAD FRACCION",
        "campo": "",
        "obligatorio": false,
        "tipo": "Alfanumérico",
        "longitud": 5.0,
        "ayuda": "Indica el codigo de unidad de fraccion. El dato a cargar en este campo debe estar previamente cargado en la tabla de Medidas",
        "valor": ""
      },
      {
        "encabezado": "CODIGO UNIDAD",
        "campo": "unidad",
        "obligatorio": true,
        "tipo": "Alfanumérico",
        "longitud": 5.0,
        "ayuda": "Indica el codigo de unidad. El dato a cargar en este campo debe estar previamente cargado en la tabla de Medidas",
        "valor": ""
      },
      {
        "encabezado": "CODIGO GRUPO PRODUCTO",
        "campo": "",
        "obligatorio": false,
        "tipo": "Alfanumérico",
        "longitud": 5.0,
        "ayuda": "Indica la agrupación a nivel general de productos. (Dejar siempre en blanco el campo salvo que indique lo contrario el equipo de Globaltech",
        "valor": ""
      },
      {
        "encabezado": "CODIGO PAIS",
        "campo": "",
        "obligatorio": true,
        "tipo": "Alfanumérico",
        "longitud": 5.0,
        "ayuda": "Se debe ingresar el Pais correspondiente al producto ó donde estará ubicado el producto. El dato a cargar en este campo debe estar previamente cargado en la tabla de Pais",
        "valor": ""
      },
      {
        "encabezado": "CODIGO FAMILIA",
        "campo": "familia",
        "obligatorio": true,
        "tipo": "Alfanumérico",
        "longitud": 30.0,
        "ayuda": "Indica el codigo de familia del producto. El dato a cargar en este campo debe estar previamente cargado en la tabla de Familia",
        "valor": ""
      },
      {
        "encabezado": "OBSERVACIONES",
        "campo": "observacion",
        "obligatorio": false,
        "tipo": "Alfanumérico",
        "longitud": 400.0,
        "ayuda": "Observaciones del producto",
        "valor": ""
      },
      {
        "encabezado": "POSICIONES PURAS",
        "campo": "",
        "obligatorio": true,
        "tipo": "Numérico",
        "longitud": 1.0,
        "ayuda": "Indica con 0 si no desea mantener posiciones puras, 1 para indicar que dicho producto no debe poder compartir una misma posición con otro producto. ",
        "valor": ""
      },
      {
        "encabezado": "LOTE AUTOMATICO",
        "campo": "",
        "obligatorio": true,
        "tipo": "Numérico",
        "longitud": 1.0,
        "ayuda": "Indica con 0 si no usa Lote automatico, 1 si requiere que la aplicación genere un lote automatico",
        "valor": ""
      },
      {
        "encabezado": "PALLET AUTOMATICO",
        "campo": "",
        "obligatorio": true,
        "tipo": "Numérico",
        "longitud": 1.0,
        "ayuda": "Indica con 0 si no genera Pallet Automatico, 1 para indicar que se genere pallet automatico al ingreso de dicho producto al depósito.",
        "valor": ""
      },
      {
        "encabezado": "CODIGO CATEGORIA LOGICA INGRESO",
        "campo": "",
        "obligatorio": true,
        "tipo": "Alfanumérico",
        "longitud": 50.0,
        "ayuda": "Indica la categoria logica al ingreso. El dato a cargar en este campo debe estar previamente cargado en la tabla de Categoría Lógica.",
        "valor": ""
      },
      {
        "encabezado": "CODIGO SUB-FAMILIA",
        "campo": "",
        "obligatorio": true,
        "tipo": "Alfanumérico",
        "longitud": 30.0,
        "ayuda": "Indica la sub-familia del producto. El dato a cargar en este campo debe estar previamente cargado en la tabla de Sub-Familia",
        "valor": ""
      },
      {
        "encabezado": "TIPO CONTENEDORA",
        "campo": "",
        "obligatorio": false,
        "tipo": "Alfanumérico",
        "longitud": 100.0,
        "ayuda": "Indicar el tipo de contenedora específica. (Dejar siempre en blanco el campo salvo que indique lo contrario el equipo de Globaltech)",
        "valor": ""
      },
      {
        "encabezado": "CODIGO TIPO PRODUCTO",
        "campo": "",
        "obligatorio": true,
        "tipo": "Alfanumérico",
        "longitud": 5.0,
        "ayuda": "Indica el Tipo de producto al cual pertenecera. Por default siempre poner NO, sino tener presente que el dato a cargar en este campo debe estar previamente cargado en la tabla de Tipo Producto",
        "valor": "NO"
      },
      {
        "encabezado": "ENVASE",
        "campo": "",
        "obligatorio": true,
        "tipo": "Numérico",
        "longitud": 1.0,
        "ayuda": "Indicar con 0 si no es un envase, 1 si el producto a configurar será tenido en cuenta como un envase (Por ejemplo: un pallet que se egresa y se requiera tener un control de donde se encuentra para registrar el ingreso cuando retorne).",
        "valor": ""
      },
      {
        "encabezado": "ING. PARTIDA",
        "campo": "",
        "obligatorio": true,
        "tipo": "Numérico",
        "longitud": 1.0,
        "ayuda": "Indica 0 si no se desea registrar al ingreso la partida, 1 si desea ingresarla.",
        "valor": ""
      },
      {
        "encabezado": "SERIE ING.",
        "campo": "",
        "obligatorio": true,
        "tipo": "Numérico",
        "longitud": 1.0,
        "ayuda": "Indica 0 si no desea serializar al ingreso, 1 si desea hacerlo.",
        "valor": ""
      },
      {
        "encabezado": "SERIE EGR",
        "campo": "",
        "obligatorio": true,
        "tipo": "Numérico",
        "longitud": 1.0,
        "ayuda": "Indicar 0 si no desea serializar al egreso, 1 si desea hacerlo.",
        "valor": ""
      },
      {
        "encabezado": "VAL. COD. ING.",
        "campo": "",
        "obligatorio": true,
        "tipo": "Numérico",
        "longitud": 1.0,
        "ayuda": "Indicar con 0 si no desea validar los codigos de barra al ingreso, 1 si desea hacerlo. (relacionado a los códigos EAN13 y/o DUN 14)",
        "valor": ""
      },
      {
        "encabezado": "VAL. COD. EGR.",
        "campo": "",
        "obligatorio": true,
        "tipo": "Numérico",
        "longitud": 1.0,
        "ayuda": "Indicar con 0 si no desea validar codigos al egreso, 1 si desea hacerlo (relacionado a los códigos EAN13 y/o DUN 14).",
        "valor": ""
      },
      {
        "encabezado": "LARGO",
        "campo": "",
        "obligatorio": false,
        "tipo": "Float",
        "longitud": "20 (para enteros)   5 (para decimales)",
        "ayuda": "Identifcar el Largo del producto (tener en cuenta que se debe tomar el largo referido a la unidad logistica definida). El dato a ingresar deberá estar expresado en cm.",
        "valor": ""
      },
      {
        "encabezado": "ALTO",
        "campo": "",
        "obligatorio": false,
        "tipo": "Float",
        "longitud": "20 (para enteros)   5 (para decimales)",
        "ayuda": "Identifcar el Alto del producto (tener en cuenta que se debe tomar el Alto referido a la unidad logistica definida). El dato a ingresar deberá estar expresado en cm.",
        "valor": ""
      },
      {
        "encabezado": "ANCHO",
        "campo": "",
        "obligatorio": false,
        "tipo": "Float",
        "longitud": "20 (para enteros)   5 (para decimales)",
        "ayuda": "Identifcar el Ancho del producto (tener en cuenta que se debe tomar el Ancho referido a la unidad logistica definida). El dato a ingresar deberá estar expresado en cm.",
        "valor": ""
      },
      {
        "encabezado": "PESO",
        "campo": "",
        "obligatorio": false,
        "tipo": "Float",
        "longitud": "20 (para enteros)   5 (para decimales)",
        "ayuda": "Identificar el Peso del producto según la unidad logistica definida para dicho producto. El valor tiene que estar expresado en kg.",
        "valor": ""
      },
      {
        "encabezado": "BACK ORDER",
        "campo": "",
        "obligatorio": true,
        "tipo": "Numérico",
        "longitud": 1.0,
        "ayuda": "Indica con 0 si no desea genera Back Order, 1 si desea poder realizar ingresos parciales sobre las Ordenes de Compras que se estarán recibiendo.",
        "valor": ""
      },
      {
        "encabezado": "TOLERANCIA MIN.",
        "campo": "",
        "obligatorio": false,
        "tipo": "Numérico",
        "longitud": 3.0,
        "ayuda": "Indicar el porcentaje de tolerancia mínima al ingreso.",
        "valor": ""
      },
      {
        "encabezado": "TOLERANCIA MAX.",
        "campo": "",
        "obligatorio": false,
        "tipo": "Numérico",
        "longitud": 3.0,
        "ayuda": "Indicar el porcentaje de tolerancia máxima al egreso.",
        "valor": ""
      },
      {
        "encabezado": "CLASIFICACION COT",
        "campo": "",
        "obligatorio": false,
        "tipo": "Alfanumérico",
        "longitud": 100.0,
        "ayuda": "Indica el codigo de Clasificacion COT. (solo utilizar cuando el equipo de Globaltech así lo indique)",
        "valor": ""
      },
      {
        "encabezado": "NO AGRUPA ITEMS",
        "campo": "",
        "obligatorio": true,
        "tipo": "Numérico",
        "longitud": 1.0,
        "ayuda": "Indica con 0 si desea agrupar items cuando en un pedido de egreso se carguen varias lineas con el mismo código de producto, 1 sino desea hacerlo.",
        "valor": ""
      },
      {
        "encabezado": "CODIGO ROTACION",
        "campo": "",
        "obligatorio": false,
        "tipo": "Alfanumérico",
        "longitud": 20.0,
        "ayuda": "Indica el Codigo de rotacion. El dato a ingresar en este campo tiene que estar previamente cargado en la tabla de Rotacion",
        "valor": ""
      },
      {
        "encabezado": "COSTO",
        "campo": "",
        "obligatorio": false,
        "tipo": "Numérico",
        "longitud": 5.0,
        "ayuda": "Indica el costo de la mercaderia.",
        "valor": ""
      },
      {
        "encabezado": "CODIGO MONEDA",
        "campo": "",
        "obligatorio": false,
        "tipo": "Alfanumérico",
        "longitud": 5.0,
        "ayuda": "Indica la moneda del costo del producto El dato a ingresar en este campo tiene que estar previamente cargado en la tabla de moneda",
        "valor": ""
      },
      {
        "encabezado": "ING. LOTE PROVEEDOR",
        "campo": "",
        "obligatorio": true,
        "tipo": "Numérico",
        "longitud": 1.0,
        "ayuda": "Indica con 0 sino desea exigir el codigo de lote al ingreso, 1 si desea hacerlo.",
        "valor": ""
      },
      {
        "encabezado": "PICKING DE MAS",
        "campo": "",
        "obligatorio": false,
        "tipo": "Numérico",
        "longitud": 1.0,
        "ayuda": "Indica con 0 sino desea que se pueda pickear de mas al egreso, 1 si desea hacerlo.",
        "valor": ""
      }
    ]
  }
];
