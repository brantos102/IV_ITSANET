# API

Documentación interactiva en `/docs` (OpenAPI) con el servidor corriendo.

La sesión va en una cookie `val_session` (o `Authorization: Bearer <token>`).

## Autenticación

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| POST | `/api/auth/login` | — | `{usuario, pin}` → token + cookie |
| POST | `/api/auth/logout` | cualquiera | Cierra la sesión |
| GET | `/api/auth/yo` | cualquiera | Operador de la sesión actual |
| GET | `/api/auth/operadores` | supervisor | Lista operadores |
| POST | `/api/auth/operadores` | supervisor | Crea un operador |

## Recepciones

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/api/recepciones` | cualquiera | Lista con avance |
| POST | `/api/recepciones` | cualquiera | Crea la recepción |
| POST | `/api/recepciones/{id}/packing-list` | cualquiera | Sube el `.xlsx` (multipart) |
| GET | `/api/recepciones/{id}` | cualquiera | Resumen + detalle por SKU |
| GET | `/api/recepciones/{id}/items` | cualquiera | Líneas del packing list |
| GET | `/api/recepciones/{id}/pallets` | cualquiera | Pallets y subpallets |
| GET | `/api/recepciones/{id}/pendientes` | cualquiera | SKU por crear en Depot |
| PATCH | `/api/recepciones/{id}/pendientes/{pid}` | supervisor | Resuelve un pendiente |
| POST | `/api/recepciones/{id}/cerrar` | supervisor | Cierra la validación |
| POST | `/api/recepciones/{id}/reabrir` | supervisor | Reabre con motivo |
| GET | `/api/recepciones/{id}/export` | cualquiera | Descarga el packing list final |
| GET | `/api/recepciones/{id}/auditoria` | supervisor | Bitácora de la recepción |

## Escaneo

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| POST | `/api/recepciones/{id}/lookup` | cualquiera | Paso 1: valida y sugiere pallet |
| POST | `/api/recepciones/{id}/scans` | cualquiera | Paso 2: registra la cantidad física |
| GET | `/api/recepciones/{id}/scans` | cualquiera | Historial (filtra por `sku`, `pallet`) |
| POST | `/api/recepciones/{id}/scans/{eid}/anular` | autor o supervisor | Anula con motivo |
| POST | `/api/recepciones/{id}/ajustes` | supervisor | Ajuste manual (+/-) |
| GET | `/api/recepciones/{id}/sku/{sku}` | cualquiera | Estado de un SKU |

### `POST /lookup`

```json
{ "codigo": "6EA853651H9B9" }
```

```json
{
  "sku": "6EA853651H9B9",
  "en_packing_list": true,
  "esperado": 5, "contado": 3, "pendiente": 2, "estado": "FALTANTE",
  "descripcion": "CALANDRA DEL",
  "depot": { "existe": true, "accion": "OK", "fuente": "CACHE", "degradado": false },
  "ubicaciones": [ { "pallet": "B03", "cantidad": 3, "eventos": 1 } ],
  "pallet_sugerido": "B03",
  "avisos": ["Este SKU ya fue guardado en: B03 (3). Use el mismo pallet si es posible."]
}
```

`depot.accion` vale `OK`, `VALIDAR_PROFUNDIDAD` (hay códigos similares) o `CREAR`
(no existe). Con `degradado: true` la API de Depot no respondió y la verificación
se hizo solo contra el maestro local.

### `POST /scans`

```json
{
  "codigo": "6EA853651H9B9", "cantidad": 2, "pallet": "B03.1",
  "estado_fisico": "BUENO", "ean": "7501234567890",
  "observacion": null, "confirmar_sobrante": false,
  "idempotency_key": "f47ac10b-58cc-4372-a567",
  "dispositivo": "disp-a1b2c3"
}
```

Envíe siempre `idempotency_key` (un UUID por intento): si la respuesta se pierde
y el cliente reintenta, el conteo no se duplica y la respuesta trae
`"duplicado": true`.

## Errores de negocio

Llegan como `{"detail": {"codigo": "...", "mensaje": "..."}}`.

| Código | HTTP | Significado |
|---|---|---|
| `CONFIRMAR_SOBRANTE` | 409 | Supera lo declarado; reenviar con `confirmar_sobrante: true` |
| `RECEPCION_CERRADA` | 409 | No admite más conteos |
| `PALLET_INVALIDO` | 400 | Formato distinto de `A1` / `A1.1` |
| `OBSERVACION_REQUERIDA` | 400 | Mal estado físico sin observación |
| `CANTIDAD_INVALIDA` | 400 | Cantidad 0 |
| `AJUSTE_REQUERIDO` | 400 | Negativo fuera de `/ajustes` |
| `YA_ANULADO` | 409 | Ese conteo ya fue anulado |

## Catálogo y KPIs

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/api/catalogo/estado` | cualquiera | Modo de integración y tamaño del caché |
| GET | `/api/catalogo/buscar?q=` | cualquiera | Busca en el maestro local |
| POST | `/api/catalogo/maestro` | supervisor | Carga el maestro (multipart) |
| GET | `/api/kpi/resumen` | cualquiera | Globales + por recepción (`desde`, `hasta`) |
| GET | `/api/kpi/operadores` | cualquiera | Productividad por operador |
| GET | `/api/kpi/skus` | cualquiera | Histórico por SKU (`solo_problematicos`) |
| GET | `/api/kpi/serie` | cualquiera | Serie diaria (`dias`) |
| GET | `/api/kpi/pendientes` | cualquiera | SKU por crear en Depot |
