# Contrato de datos e integración — API v1

> Esta es la referencia vigente del contrato API v1. Los ejemplos sintéticos
> históricos siguen describiendo el comportamiento predeterminado; MOLA añade
> cobertura global y solicitudes geográficas, preservando el formato legado.

## Principios

- El **backend** calcula las rutas con A*. El **frontend** gestiona la interacción y dibuja lo que recibe; nunca recalcula ni reconstruye el camino.
- El modo predeterminado es **sintético** (`is_simulated: true`). El modo MOLA declara `data_source: "mola"` y `is_simulated: false`.
- Las celdas se representan por índices `{ "row", "col" }`; en solicitudes
  geográficas MOLA se usa `{ "latitude", "longitude" }`, nunca ambos formatos
  en una ubicación.
- Los nombres de campos están en inglés y en `snake_case`; los mensajes de error están en español.
- Los nombres de campos no cambian entre endpoints (`row`, `col`, `origin`, `destination`, `path`, `summary`).

## Convenciones generales

| Elemento | Valor |
|---|---|
| Base URL (desarrollo) | `http://127.0.0.1:8000` |
| Prefijo de versión | `/api/v1` |
| Formato | JSON, codificación UTF-8, cabecera `Content-Type: application/json` en las solicitudes POST |
| Compresión | El backend comprime respuestas de más de 1 KB con gzip cuando el cliente lo anuncia; navegadores y clientes HTTP habituales la descomprimen automáticamente |
| Origen del frontend (CORS) | `http://127.0.0.1:5500` y `http://localhost:5500` (configurable en el backend con la variable `MARS_ALLOWED_ORIGINS`) |
| Métodos CORS permitidos | `GET`, `POST`, `OPTIONS` |
| Autenticación | Ninguna (laboratorio local) |
| Documentación automática | `http://127.0.0.1:8000/docs` (Swagger UI de FastAPI) |
| Selección de datos | `MARS_DATA_SOURCE=synthetic` (predeterminado) o `mola` |
| Cuadrícula MOLA de detalle | `MARS_MOLA_GRID_FILE` (opcional), JSON de región procesada en `data/processed/`; por defecto `mola_valles_marineris.json` |
| Región MOLA de detalle por nombre | `MARS_MOLA_REGION` (opcional): `valles_marineris` (predeterminada), `ecuatorial` o `gale` (DEM MOLA+HRSC agregado a 600 m). `MARS_MOLA_GRID_FILE` tiene prioridad; un nombre desconocido produce `503 DATASET_UNAVAILABLE` |
| Cuadrícula MOLA global | `data/processed/mola_global_1deg.json.gz`, necesaria al activar MOLA |

## Endpoints

| Método | URL | Función | Respuestas |
|---|---|---|---|
| GET | `/api/v1/health` | Indica que la API funciona | 200 |
| GET | `/api/v1/map` | Metadatos de la zona, dimensiones y celdas | 200, 503 |
| POST | `/api/v1/routes` | Calcula la ruta entre un origen y un destino | 200, 400, 404, 422, 503 |
| POST | `/api/v1/routes/shelter` | Modo «alerta solar»: ruta desde un origen a la zona candidata de espera más cercana por costo (solo regiones con `sky_view_factor`) | 200, 400, 404, 422, 503 |

La fuente es una configuración del backend compartida por mapa y rutas. Se
admiten solicitudes legadas por índices y solicitudes geográficas MOLA. Un
error de configuración/archivo de datos devuelve `503 DATASET_UNAVAILABLE`.

## Coordenadas de la cuadrícula

| Aspecto | Definición |
|---|---|
| Representación | `{ "row": 2, "col": 3 }` (dos enteros) |
| Base de índices | 0. La primera fila es `row = 0` y la primera columna es `col = 0` |
| Sentido de `row` | Crece hacia abajo (la fila 0 es el borde superior del mapa) |
| Sentido de `col` | Crece hacia la derecha (la columna 0 es el borde izquierdo) |
| Zona de prueba | 10 filas × 14 columnas: `row` de 0 a 9, `col` de 0 a 13 |
| Tamaño de celda | Sintético: 100 m × 100 m simulados. MOLA: escala nominal de la proyección en el ecuador marciano |
| Latitud/longitud | Coordenadas MOLA planetocéntricas, longitud positiva este (0–360°). Se aceptan en `POST /routes`; el mapa incluye centros y región |

La conversión al plano local de Leaflet sigue siendo un detalle interno y no
forma parte del contrato. La malla global es de 180 × 360 celdas de 1°. Para
rutas geográficas, el backend usa la cuadrícula detallada si ambos puntos
pertenecen a `region`; si alguno queda fuera, usa la malla global. Los índices
de `path` son los de la cuadrícula seleccionada y cada punto incluye coordenadas
geográficas para su representación.

## Unidades

| Campo | Unidad | Rango / notas |
|---|---|---|
| `distance_m` | metros | ≥ 0. Suma de longitudes de los pasos × `cell_size_m`. En MOLA es aproximada: A* usa el tamaño nominal en el ecuador también a latitudes mayores |
| `total_cost` | `cost_units` (adimensional) | ≥ 0. Suma de los costos de cada paso (ver modelo de costos) |
| `elevation_m` | metros | Sintético o altura MOLA respecto al areoide |
| `slope_deg` | grados | Pendiente sintética o derivada del raster MOLA |
| `risk`, `mean_risk`, `max_risk` | adimensional | 0.0–1.0 si hay un indicador disponible. Sintético: riesgo simulado. MOLA: proxy de pendiente, no probabilidad de peligro |

## Formato de las celdas (campo `cells` de /map)

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `row` | entero | sí | Fila (0 = arriba) |
| `col` | entero | sí | Columna (0 = izquierda) |
| `elevation_m` | número | sí | Elevación en metros; en MOLA, respecto al areoide |
| `slope_deg` | número | sí | Pendiente en grados |
| `risk` | número 0.0–1.0 | sí | Indicador disponible; en MOLA válido es `min(slope_deg / 20, 1)`. En celdas MOLA inválidas vale 0 por compatibilidad, pero se bloquean y el indicador no está disponible |
| `blocked` | booleano | sí | `true` si la celda no es transitable |
| `valid` | booleano | solo MOLA | `false` si el valor de origen está marcado inválido; esas celdas se bloquean |
| `latitude`, `longitude` | número | solo MOLA | Centro del pixel en grados planetocéntricos, longitud positiva este |
| `sky_view_factor` | número 0.0–1.0 | no (solo regiones con capa de radiación, hoy `gale`) | Fracción del cielo no tapada por el relieve, derivada del DEM. Ausente en celdas inválidas |
| `radiation_modeled` | número 0.0–1.0 | no (igual que `sky_view_factor`) | Índice relativo de radiación **MODELADO**; no es una dosis ni una medición por celda |

`cells` es una lista plana con una entrada por celda, sin duplicados ni faltantes
(140 celdas en el ejemplo sintético). MOLA usa el tamaño de su región procesada.
La respuesta puede incluir `region` y `risk_available`. Si la región trae la capa de
radiación MODELADA, incluye además `radiation_available: true` y `radiation_model`
(etiqueta `"MODELADO"`, fórmula del índice, método, supuestos, límites y el ancla
RAD con el estado de verificación de sus cifras). Sin la capa, esos campos no aparecen.
En MOLA también incluye `risk_model` (`name`, `method`, `slope_scale_deg`,
`interpretation`) y `risk_available: true` porque publica el proxy de pendiente
para las celdas con datos válidos. No es un modelo de peligro ni una probabilidad.

## Tratamiento de celdas bloqueadas

- En sintético, `blocked: true` significa obstáculo o pendiente ≥ 20° (simulado). En MOLA, bloquea datos inválidos y pendientes iguales o mayores al umbral aplicado al procesar; el valor predeterminado 30° es demostrativo, no operacional.
- Una celda bloqueada **no puede ser origen ni destino**: el backend responde `400 CELL_BLOCKED`.
- A* nunca atraviesa celdas bloqueadas. Los movimientos diagonales no «cortan esquinas»: se exige que las dos celdas laterales estén libres.
- El frontend dibuja las celdas bloqueadas y rechaza su selección como cortesía al usuario, pero **el backend siempre valida**.
- Una celda libre puede ser inalcanzable si está rodeada de celdas bloqueadas: el backend responde `404 NO_ROUTE`.

## Modelo de costos

**Fórmula**

```
costo_paso = factor_longitud * (1 + slope_weight * slope_deg + risk_weight * risk
                                 + radiation_weight * radiation_modeled)

factor_longitud = 1.0       en movimientos ortogonales
factor_longitud = raíz(2)   en movimientos diagonales
slope_deg, risk y radiation_modeled son los de la celda de DESTINO del paso
radiation_modeled = 0       si la región no trae la capa MODELADA
slope_weight = 0.05         risk_weight = 2.0         radiation_weight = 0.0
(slope_weight y radiation_weight pueden cambiarse por solicitud, entre 0 y 100)
total_cost = suma de costo_paso de todos los pasos de la ruta
```

Todos los pesos son ≥ 0 y los valores de celda también, así que el multiplicador es ≥ 1 y
la heurística octil de A* sigue siendo admisible. Con `radiation_weight = 0.0` (valor por
defecto) los costos y las rutas son los mismos que antes de añadir la capa.

El origen no suma costo (se parte de él). Si origen y destino coinciden,
`total_cost` y `distance_m` valen 0. El backend publica los pesos en
`cost_model` de `/map`. En MOLA, `risk_weight` es 2.0 y se aplica al proxy
topográfico definido arriba; el peso y la función de costo son demostrativos,
no están calibrados para movilidad real.

## GET /api/v1/health

Sin parámetros. Respuesta `200`:

| Campo | Tipo | Descripción |
|---|---|---|
| `status` | texto | Siempre `"ok"` |
| `service` | texto | `"mars-explorer-lab-api"` |
| `version` | texto | Versión de la aplicación |
| `api_version` | texto | `"v1"` |
| `data_source` | texto | Fuente activa: `"synthetic"` o `"mola"` |

**Respuesta real de GET /api/v1/health**

```
{
  "status": "ok",
  "service": "mars-explorer-lab-api",
  "version": "1.0.0",
  "api_version": "v1",
  "data_source": "synthetic"
}
```

## GET /api/v1/map

Sin parámetros. Respuesta `200` con estos campos:

| Campo | Tipo | Descripción |
|---|---|---|
| `name` | texto | Nombre de la zona |
| `data_source` | texto | `"synthetic"` o `"mola"` |
| `is_simulated` | booleano | `true` para sintético, `false` para MOLA |
| `disclaimer` | texto | Procedencia y limitaciones (el frontend debe mostrarlo) |
| `grid` | objeto | `rows` (entero), `cols` (entero), `cell_size_m` (número) |
| `coordinate_system` | objeto | `type` = `"grid_index"`, `index_base` = 0, `row_axis` = `"down"`, `col_axis` = `"right"`, `description` |
| `cost_model` | objeto | `formula`, `slope_weight`, `risk_weight`, `radiation_weight` (opcional, ≥ 0), `diagonal_length_factor`, `cost_unit` = `"cost_units"` |
| `cells` | lista | Lista de celdas con el formato definido arriba |
| `risk_available` | booleano | Si la fuente aporta un modelo de riesgo |
| `risk_model` | objeto | Opcional; en MOLA describe el proxy topográfico y sus límites |
| `radiation_available` | booleano | Opcional; `true` si las celdas traen la capa de radiación MODELADA |
| `radiation_model` | objeto | Opcional; descripción de la capa MODELADA (ver `docs/FUENTES_DE_DATOS.md`) |
| `region` | objeto | Opcional; límites geográficos en MOLA |
| `provenance` | objeto | Opcional; solo en MOLA. Procedencia por capa presente (ver abajo) |
| `global_grid` | objeto | Solo MOLA: dimensiones, resolución, límites y lista plana de celdas globales compactas |

### Campo `provenance` (opcional)

Objeto cuyas claves son capas presentes en la respuesta y cuyo valor es
`{label, source, in_cost, note?}`. `label` es una de `MEDIDO`, `DERIVADO`,
`INDICADOR`, `MODELADO`, `INTERPRETADO`, `REFERENCIA` o `ÍNDICE DEL PROYECTO`.
`in_cost` indica si la capa entra **directamente** al costo de A*. Solo se publica
en fuentes reales (MOLA); en modo sintético no aparece. Hoy se emiten:

| Capa | `label` | `in_cost` | Presente en |
|---|---|---|---|
| `elevation_m` | MEDIDO | `false` (entra a través de la pendiente) | todas las regiones MOLA |
| `slope_deg` | DERIVADO | `true` | todas las regiones MOLA |
| `risk` | DERIVADO (proxy `min(slope_deg/20, 1)`) | `true` | todas las regiones MOLA |
| `blocked` | ÍNDICE DEL PROYECTO (regla: celda inválida o pendiente ≥ umbral demostrativo del procesado) | `false` (A* no la atraviesa) | todas las regiones MOLA |
| `sky_view_factor` | DERIVADO | `false` (solo elige zonas candidatas de espera) | regiones con capa de radiación (Gale) |
| `radiation_modeled` | MODELADO | `true` (peso 0 por defecto) | regiones con capa de radiación (Gale) |
| `total_cost` | ÍNDICE DEL PROYECTO | `false` (es el resultado) | todas las regiones MOLA |

`INDICADOR` (terreno blando), `INTERPRETADO` (geología) y `REFERENCIA` (ruta de
Curiosity) no se emiten porque el backend no sirve esas capas. Por qué
`sky_view_factor` es DERIVADO aquí y la capa de F3 es MODELADO: ver
`docs/FUENTES_DE_DATOS.md`.

Cada `global_grid.cells` registra `elevation_m`, `slope_deg`, `blocked` y
`valid`; sus índices `row`/`col` se infieren del orden fila-columna del arreglo.
La lista tiene 64.800 entradas. Las elevaciones son promedios en celdas de 1°;
la pendiente es el máximo de las pendientes nativas MOLA dentro de cada celda.
Las celdas con pendiente de 20° o más se bloquean por una regla demostrativa.
La respuesta es JSON normal y supera 4 MB sin compresión; la API ofrece gzip
para reducir el tráfico sin cambiar el contrato ni el JSON que recibe el navegador.

**Respuesta real de GET /api/v1/map (abreviada: `cells` muestra 3 de las 140 celdas)**

```
{
  "name": "Zona sintética Mars Explorer Lab",
  "data_source": "synthetic",
  "is_simulated": true,
  "disclaimer": "DATOS SIMULADOS: elevación, pendiente y riesgo son sintéticos y no provienen de NASA ni de ninguna misión real. Este laboratorio es educativo y no garantiza que una ruta sea segura en Marte.",
  "grid": {
    "rows": 10,
    "cols": 14,
    "cell_size_m": 100.0
  },
  "coordinate_system": {
    "type": "grid_index",
    "index_base": 0,
    "row_axis": "down",
    "col_axis": "right",
    "description": "Índices de cuadrícula (row, col) desde la esquina superior izquierda. No son latitud ni longitud."
  },
  "cost_model": {
    "formula": "costo_paso = factor_longitud * (1 + slope_weight * slope_deg + risk_weight * risk + radiation_weight * radiation_modeled); radiation_modeled vale 0 si la fuente no trae la capa MODELADA; se usan los valores de la celda de destino del paso",
    "slope_weight": 0.05,
    "risk_weight": 2.0,
    "radiation_weight": 0.0,
    "diagonal_length_factor": 1.4142,
    "cost_unit": "cost_units"
  },
  "cells": [
    { "row": 0, "col": 0, "elevation_m": 1000.0, "slope_deg": 16.9, "risk": 0.11, "blocked": false },
    { "row": 0, "col": 1, "elevation_m": 1030.1, "slope_deg": 15.5, "risk": 0.24, "blocked": false },
    { "row": 0, "col": 2, "elevation_m": 1055.4, "slope_deg": 11.8, "risk": 0.31, "blocked": false }
  ]
}
```

## POST /api/v1/routes — solicitud

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `origin` | objeto `{row, col}` o `{latitude, longitude}` | sí | Celda/punto de origen |
| `destination` | objeto `{row, col}` o `{latitude, longitude}` | sí | Celda/punto de destino |
| `allow_diagonal` | booleano | no (por defecto `true`) | Permite movimientos diagonales |
| `slope_weight` | número 0–100 | no (por defecto el de `cost_model`, 0.05) | Peso de la pendiente para esta solicitud |
| `radiation_weight` | número 0–100 | no (por defecto 0.0) | Peso del índice de radiación MODELADO para esta solicitud; sin efecto si la región no trae la capa |

- Usa ambos índices o ambas coordenadas para cada ubicación. No mezcles formatos
  entre origen y destino, ni incluyas campos de ambos formatos en una ubicación.
- `row` y `col` deben ser **enteros JSON** (`2`, no `"2"` ni `2.0`). Las
  coordenadas deben tener latitud entre −90° y 90° y longitud entre 0° y 360°.
  Un tipo/rango incorrecto produce `422 VALIDATION_ERROR`.
- No se admiten campos adicionales: producen `422 VALIDATION_ERROR`.
- Los pesos deben ser números JSON finitos entre 0 y 100 (no texto ni booleanos);
  si no, `422 VALIDATION_ERROR`. `risk_weight` no se puede ajustar por solicitud.
  Una solicitud sin pesos da exactamente la misma respuesta que antes de F6.
- Un índice fuera de la cuadrícula es `400 OUT_OF_BOUNDS`. Las coordenadas
  geográficas solo se aceptan con fuente MOLA; en modo sintético producen
  `400 GEOGRAPHIC_ROUTE_UNAVAILABLE`.

**Solicitud de ejemplo**

```
{
  "origin": { "row": 2, "col": 1 },
  "destination": { "row": 2, "col": 12 },
  "allow_diagonal": true
}
```

**Solicitud MOLA en coordenadas** (permite seleccionar cualquier punto del
planeta; ruta global aproximada si un extremo queda fuera de `region`):

```json
{
  "origin": { "latitude": 10.5, "longitude": 20.5 },
  "destination": { "latitude": 10.5, "longitude": 25.5 }
}
```

## POST /api/v1/routes — respuesta 200

| Campo | Tipo | Descripción |
|---|---|---|
| `status` | texto | `"ok"` |
| `data_source`, `is_simulated`, `disclaimer` | texto, booleano, texto | Identificación de fuente y limitaciones |
| `origin`, `destination` | `{row, col}` y opcionalmente latitud/longitud | Índices de la cuadrícula seleccionada y centro de celda en solicitudes geográficas |
| `allow_diagonal` | booleano | Valor aplicado |
| `path` | lista de `{row, col}` con coordenadas opcionales | Celdas en orden, **incluyendo** origen y destino; las rutas geográficas incluyen centros lat/lon para dibujar |
| `summary` | objeto | Resultados numéricos (tabla siguiente) |
| `resolution` | texto opcional | `"mola-detail"` o `"mola-global-1deg"` para solicitudes geográficas MOLA |
| `cost_weights` | objeto opcional | `slope_weight`, `risk_weight`, `radiation_weight` aplicados. **Solo aparece si la solicitud trae algún peso** |

| Campo de `summary` | Tipo | Descripción |
|---|---|---|
| `steps` | entero | Número de movimientos = `len(path) - 1` |
| `distance_m` | número | Distancia sintética en metros |
| `total_cost` | número | Costo total en `cost_units` |
| `max_slope_deg` | número | Pendiente máxima entre las celdas de la ruta |
| `mean_risk` | número | Riesgo medio de la ruta; no interpretable como evaluación si `risk_available` es falso |
| `max_risk` | número | Riesgo máximo de la ruta; no interpretable como evaluación si `risk_available` es falso |
| `nodes_expanded` | entero | Nodos expandidos por A* (informativo) |

**Respuesta real de POST /api/v1/routes**

```
{
  "status": "ok",
  "data_source": "synthetic",
  "is_simulated": true,
  "disclaimer": "DATOS SIMULADOS: elevación, pendiente y riesgo son sintéticos y no provienen de NASA ni de ninguna misión real. Este laboratorio es educativo y no garantiza que una ruta sea segura en Marte.",
  "origin": { "row": 2, "col": 1 },
  "destination": { "row": 2, "col": 12 },
  "allow_diagonal": true,
  "path": [
    { "row": 2, "col": 1 },
    { "row": 3, "col": 2 },
    { "row": 4, "col": 3 },
    { "row": 5, "col": 4 },
    { "row": 6, "col": 5 },
    { "row": 7, "col": 5 },
    { "row": 8, "col": 5 },
    { "row": 8, "col": 6 },
    { "row": 8, "col": 7 },
    { "row": 7, "col": 8 },
    { "row": 6, "col": 9 },
    { "row": 5, "col": 10 },
    { "row": 4, "col": 11 },
    { "row": 3, "col": 12 },
    { "row": 2, "col": 12 }
  ],
  "summary": {
    "steps": 14,
    "distance_m": 1772.79,
    "total_cost": 34.918,
    "max_slope_deg": 13.1,
    "mean_risk": 0.2193,
    "max_risk": 0.41,
    "nodes_expanded": 97
  }
}
```

Caso límite: si `origin` y `destination` coinciden, `path` tiene una sola celda, `steps` = 0, `distance_m` = 0 y `total_cost` = 0.

## POST /api/v1/routes/shelter — modo «alerta solar»

Dado un origen, devuelve la ruta de menor costo hasta la **zona candidata de
espera** más cercana *por costo* (no por distancia). Es una ayuda de planificación
educativa: no garantiza protección ni es una recomendación operacional.

**Zona candidata de espera** (criterio del proyecto, `ÍNDICE DEL PROYECTO`): celda
válida y libre con `slope_deg ≤ max_slope_deg` (10° por defecto) y
`sky_view_factor ≤ max_sky_view_factor` (0.90 por defecto). `sky_view_factor`
solo **elige** la zona; el costo de la ruta usa la fórmula de siempre, sin él
(correlación −0,90 con la pendiente: penalizarlo castigaría dos veces). La
justificación de los umbrales está en `docs/FUENTES_DE_DATOS.md`.

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `origin` | `{row, col}` o `{latitude, longitude}` | sí | Coordenadas solo dentro de `region` (la malla global no trae la capa) |
| `allow_diagonal` | booleano | no (`true`) | Igual que en `/routes` |
| `slope_weight`, `radiation_weight` | número 0–100 | no | Igual que en `/routes` |
| `max_slope_deg` | número 0–90 | no (10) | Pendiente máxima de la zona candidata |
| `max_sky_view_factor` | número 0–1 | no (0.90) | Cielo visible máximo de la zona candidata |
| `max_distance_km` | número > 0 | no (sin valor por defecto = sin límite) | Distancia máxima de la ruta de menor costo hasta la zona candidata |

Con `max_distance_km`, una zona candidata solo se acepta si **su ruta de menor
costo** mide como mucho esa distancia (límite inclusivo); si la más barata la
supera, se busca la siguiente. No se busca la ruta más barata entre todas las que
caben en la distancia. Si ninguna zona alcanzable queda dentro: `404 NO_SHELTER`.

No admite `destination` ni campos adicionales (`422`). La respuesta `200` tiene
los mismos campos que `/routes` (`destination` es la zona elegida; `resolution`
vale `"mola-detail"` en solicitudes geográficas) más `shelter`:

| Campo de `shelter` | Descripción |
|---|---|
| `term` | `"zona candidata de espera"` |
| `label` | `"ÍNDICE DEL PROYECTO"` |
| `criterion` | Texto con el criterio aplicado |
| `max_slope_deg`, `max_sky_view_factor` | Umbrales aplicados |
| `candidates_count` | Celdas de la región que cumplen el criterio (alcanzables o no) |
| `distance_km` | Distancia recorrida hasta la zona, en km (siempre presente; igual a `summary.distance_m` / 1000 y aproximada como ella) |
| `max_distance_km` | Límite aplicado; solo aparece si la solicitud lo trae |
| `destination_slope_deg`, `destination_sky_view_factor` | Valores de la zona elegida |
| `sky_view_factor_role` | Aclara que `sky_view_factor` no entra al costo |
| `note` | Aviso de planificación educativa y límites del modelo |

Si el origen ya cumple el criterio, `path` tiene una celda y `total_cost` = 0.
Errores propios: `400 SHELTER_LAYER_UNAVAILABLE` y `404 NO_SHELTER` (tabla de
errores). `CELL_BLOCKED` y `OUT_OF_BOUNDS` se comportan como en `/routes`, con
`field: "origin"`.

## Modo MOLA

El backend selecciona una sola fuente para `/health`, `/map` y `/routes`:

```bash
MARS_DATA_SOURCE=mola
# Opcional: sin esta variable se usa data/processed/mola_valles_marineris.json
MARS_MOLA_GRID_FILE=../data/processed/mola_valles_marineris.json
# Alternativa por nombre (MARS_MOLA_GRID_FILE tiene prioridad):
MARS_MOLA_REGION=gale
```

La región `gale` mantiene `data_source: "mola"` y el mismo formato de celdas.
Su elevación procede del DEM combinado MOLA+HRSC (ver `docs/FUENTES_DE_DATOS.md`).
El JSON incluye metadatos adicionales (`source`, `aggregation`) que la API v1 no
publica.

En MOLA, `disclaimer` (en `/map` y `/routes`) es el texto que declara el JSON de
la región activa. Si el JSON no trae uno válido, se usa el texto MOLA genérico.
El campo sigue siendo un texto obligatorio, así que el contrato v1 no cambia.
Para Gale empieza así: «DEM mezcla MOLA+HRSC 200 m agregado a 600 m; resolución
de planificación, no de navegación», y cita a Fergason, Hare y Laura (2018).
Gale es hoy la única región con la capa de radiación MODELADA (`sky_view_factor`,
`radiation_modeled`, `radiation_model`); su disclaimer lo declara.

La cuadrícula de detalle se genera desde los archivos originales PDS4/ENVI con
`data/process_mola.py`; la malla global comprimida se genera con
`python3 -m data.process_mola_global`. Ambos procesos no reemplazan archivos de
salida existentes. El mapa MOLA añade `region`, centros geográficos,
`global_grid` y el proxy de pendiente. Las celdas inválidas están bloqueadas y
su valor neutral `risk: 0.0` no indica terreno de bajo riesgo. `distance_m` se
calcula con el tamaño nominal en el ecuador marciano y es aproximada a otras
latitudes. La malla global de 1° y el proxy son educativos, no una capa
validada de movilidad o seguridad.

Sin una cuadrícula MOLA procesada, los endpoints de mapa/ruta responden
`503 DATASET_UNAVAILABLE`; el modo sintético permanece como valor
predeterminado.

## Formato de errores

Todos los errores (400, 404, 405, 422, 503) usan la misma estructura. `details` siempre es un objeto (puede estar vacío).

| HTTP | `error.code` | Cuándo ocurre | Contenido de `details` |
|---|---|---|---|
| 400 | `OUT_OF_BOUNDS` | Origen o destino fuera de la cuadrícula | `field`, `row`, `col`, `rows`, `cols` |
| 400 | `CELL_BLOCKED` | Origen o destino en una celda bloqueada | `field`, `row`, `col` |
| 400 | `SHELTER_LAYER_UNAVAILABLE` | `/routes/shelter` sin capa `sky_view_factor` (sintético, regiones sin la capa) o con origen geográfico fuera de `region` | `reason` (`no_sky_view_layer` o `outside_detail_region`), `data_source` |
| 404 | `NO_ROUTE` | No existe camino transitable | `origin`, `destination`, `nodes_expanded` |
| 404 | `NO_SHELTER` | Ninguna zona candidata de espera cumple el criterio, es alcanzable o queda dentro de `max_distance_km` | `origin`, `criterion`, `candidates_count`, `nodes_expanded` y, si se pidió, `max_distance_km` |
| 404 | `NOT_FOUND` | URL inexistente | (vacío) |
| 405 | `METHOD_NOT_ALLOWED` | Método HTTP no permitido en la URL | (vacío) |
| 422 | `VALIDATION_ERROR` | Cuerpo inválido: falta un campo, tipo incorrecto, campo extra o JSON mal formado | `problems`: lista de `{field, message}` |
| 503 | `DATASET_UNAVAILABLE` | Fuente seleccionada o región MOLA procesada no disponible | `data_source` |

`field` toma el valor `"origin"` o `"destination"`. El texto de `message` es apto para mostrarse al usuario (excepto `message` dentro de `problems`, que lo genera Pydantic en inglés y es solo para depuración).

**Ejemplo real: 400 CELL_BLOCKED  (solicitud origen (3,6), destino (2,2))**

```
{
  "error": {
    "code": "CELL_BLOCKED",
    "message": "La celda de origen (3, 6) está bloqueada.",
    "details": {
      "field": "origin",
      "row": 3,
      "col": 6
    }
  }
}
```

**Ejemplo real: 400 OUT_OF_BOUNDS  (solicitud origen (-1,0), destino (2,2))**

```
{
  "error": {
    "code": "OUT_OF_BOUNDS",
    "message": "La celda de origen está fuera de la cuadrícula (10 filas x 14 columnas).",
    "details": {
      "field": "origin",
      "row": -1,
      "col": 0,
      "rows": 10,
      "cols": 14
    }
  }
}
```

**Ejemplo real: 404 NO_ROUTE  (solicitud origen (2,1), destino (8,11))**

```
{
  "error": {
    "code": "NO_ROUTE",
    "message": "No existe una ruta transitable entre el origen y el destino.",
    "details": {
      "origin": { "row": 2, "col": 1 },
      "destination": { "row": 8, "col": 11 },
      "nodes_expanded": 123
    }
  }
}
```

**Ejemplo real: 422 VALIDATION_ERROR  (solicitud sin `destination`)**

```
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "La solicitud no tiene el formato esperado.",
    "details": {
      "problems": [
        {
          "field": "destination",
          "message": "Field required"
        }
      ]
    }
  }
}
```

## Reglas de compatibilidad

- No renombrar ni eliminar campos. Añadir campos opcionales nuevos es compatible; el frontend debe ignorar los campos que no conozca.
- No cambiar tipos (un entero no pasa a texto). No cambiar el orden de `path`.
- Todo cambio incompatible exige una nueva versión de URL (`/api/v2`).
- El frontend no debe depender del orden de `cells`; debe usar `row` y `col` de cada celda.
