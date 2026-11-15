# Data and integration contract — API v1

> This is the current reference for the API v1 contract. The historical synthetic
> examples still describe the default behavior; MOLA adds global
> coverage and geographic requests, preserving the legacy format.

## Principles

- The **backend** computes routes with A*. The **frontend** manages interaction and draws what it receives; it never recomputes or rebuilds the path.
- The default mode is **synthetic** (`is_simulated: true`). MOLA mode declares `data_source: "mola"` and `is_simulated: false`.
- Cells are represented by indices `{ "row", "col" }`; in MOLA geographic requests
  `{ "latitude", "longitude" }` is used, never both formats
  in one location.
- Field names are in English and in `snake_case`; error messages are in Spanish.
- Field names do not change between endpoints (`row`, `col`, `origin`, `destination`, `path`, `summary`).

## General conventions

| Element | Value |
|---|---|
| Base URL (development) | `http://127.0.0.1:8000` |
| Version prefix | `/api/v1` |
| Format | JSON, UTF-8 encoding, `Content-Type: application/json` header on POST requests |
| Compression | The backend gzip-compresses responses larger than 1 KB when the client advertises it; browsers and common HTTP clients decompress it automatically |
| Frontend origin (CORS) | `http://127.0.0.1:5500` and `http://localhost:5500` (configurable in the backend with the variable `MARS_ALLOWED_ORIGINS`) |
| Allowed CORS methods | `GET`, `POST`, `OPTIONS` |
| Authentication | None (local laboratory) |
| Automatic documentation | `http://127.0.0.1:8000/docs` (FastAPI Swagger UI) |
| Data selection | `MARS_DATA_SOURCE=synthetic` (default) or `mola` |
| MOLA detail grid | `MARS_MOLA_GRID_FILE` (optional), processed region JSON in `data/processed/`; by default `mola_valles_marineris.json` |
| MOLA detail region by name | `MARS_MOLA_REGION` (optional): `valles_marineris` (default), `ecuatorial` or `gale` (MOLA+HRSC DEM aggregated to 600 m). `MARS_MOLA_GRID_FILE` takes priority; an unknown name produces `503 DATASET_UNAVAILABLE` |
| Global MOLA grid | `data/processed/mola_global_1deg.json.gz`, required when activating MOLA |

## Endpoints

| Method | URL | Function | Responses |
|---|---|---|---|
| GET | `/api/v1/health` | Indicates that the API works | 200 |
| GET | `/api/v1/map` | Metadata of the zone, dimensions and cells | 200, 503 |
| POST | `/api/v1/routes` | Computes the route between an origin and a destination | 200, 400, 404, 422, 503 |
| POST | `/api/v1/routes/shelter` | "Solar alert" mode: route from an origin to the nearest candidate waiting zone by cost (only regions with `sky_view_factor`) | 200, 400, 404, 422, 503 |

The source is a backend setting shared by map and routes. Legacy index requests and MOLA
geographic requests are supported. A configuration/data file
error returns `503 DATASET_UNAVAILABLE`.

## Grid coordinates

| Aspect | Definition |
|---|---|
| Representation | `{ "row": 2, "col": 3 }` (two integers) |
| Index base | 0. The first row is `row = 0` and the first column is `col = 0` |
| Direction of `row` | Grows downward (row 0 is the top edge of the map) |
| Direction of `col` | Grows to the right (column 0 is the left edge) |
| Test zone | 10 rows × 14 columns: `row` from 0 to 9, `col` from 0 to 13 |
| Cell size | Synthetic: 100 m × 100 m simulated. MOLA: nominal scale of the projection at the Martian equator |
| Latitude/longitude | Planetocentric MOLA coordinates, east-positive longitude (0–360°). Accepted in `POST /routes`; the map includes centers and region |

The conversion to Leaflet's local plane remains an internal detail and is not
part of the contract. The global mesh is 180 × 360 cells of 1°. For
geographic routes, the backend uses the detailed grid if both points
belong to `region`; if either falls outside, it uses the global mesh. The indices
in `path` are those of the selected grid and each point includes geographic
coordinates for its representation.

## Units

| Field | Unit | Range / notes |
|---|---|---|
| `distance_m` | meters | ≥ 0. Sum of step lengths × `cell_size_m`. In MOLA it is approximate: A* uses the nominal size at the equator also at higher latitudes |
| `total_cost` | `cost_units` (dimensionless) | ≥ 0. Sum of the cost of each step (see cost model) |
| `elevation_m` | meters | Synthetic or MOLA height relative to the areoid |
| `slope_deg` | degrees | Synthetic slope or derived from the MOLA raster |
| `risk`, `mean_risk`, `max_risk` | dimensionless | 0.0–1.0 if an indicator is available. Synthetic: simulated risk. MOLA: slope proxy, not probability of hazard |

## Cell format (`cells` field of /map)

| Field | Type | Required | Description |
|---|---|---|---|
| `row` | integer | yes | Row (0 = top) |
| `col` | integer | yes | Column (0 = left) |
| `elevation_m` | number | yes | Elevation in meters; in MOLA, relative to the areoid |
| `slope_deg` | number | yes | Slope in degrees |
| `risk` | number 0.0–1.0 | yes | Available indicator; in valid MOLA it is `min(slope_deg / 20, 1)`. In invalid MOLA cells it is 0 for compatibility, but they are blocked and the indicator is not available |
| `blocked` | boolean | yes | `true` if the cell is not traversable |
| `valid` | boolean | MOLA only | `false` if the source value is marked invalid; those cells are blocked |
| `latitude`, `longitude` | number | MOLA only | Pixel center in planetocentric degrees, east-positive longitude |
| `sky_view_factor` | number 0.0–1.0 | no (only regions with a radiation layer, today `gale`) | Fraction of the sky not blocked by the terrain, derived from the DEM. Absent in invalid cells |
| `radiation_modeled` | number 0.0–1.0 | no (same as `sky_view_factor`) | Relative **MODELADO** (MODELED) radiation index; it is not a dose nor a per-cell measurement |

`cells` is a flat list with one entry per cell, without duplicates or gaps
(140 cells in the synthetic example). MOLA uses the size of its processed region.
The response may include `region` and `risk_available`. If the region carries the
MODELED radiation layer, it also includes `radiation_available: true` and `radiation_model`
(label `"MODELADO"`, index formula, method, assumptions, limits and the RAD
anchor with the verification status of its figures). Without the layer, those fields do not appear.
In MOLA it also includes `risk_model` (`name`, `method`, `slope_scale_deg`,
`interpretation`) and `risk_available: true` because it publishes the slope proxy
for cells with valid data. It is not a hazard model nor a probability.

## Handling of blocked cells

- In synthetic, `blocked: true` means an obstacle or slope ≥ 20° (simulated). In MOLA, it blocks invalid data and slopes equal to or greater than the threshold applied during processing; the default value 30° is demonstrative, not operational.
- A blocked cell **cannot be an origin or destination**: the backend responds `400 CELL_BLOCKED`.
- A* never crosses blocked cells. Diagonal moves do not "cut corners": both side cells must be free.
- The frontend draws the blocked cells and rejects their selection as a courtesy to the user, but **the backend always validates**.
- A free cell may be unreachable if it is surrounded by blocked cells: the backend responds `404 NO_ROUTE`.

## Cost model

**Formula**

```
step_cost = length_factor * (1 + slope_weight * slope_deg + risk_weight * risk
                                 + radiation_weight * radiation_modeled)

length_factor = 1.0       on orthogonal moves
length_factor = sqrt(2)   on diagonal moves
slope_deg, risk and radiation_modeled are those of the step's DESTINATION cell
radiation_modeled = 0     if the region does not carry the MODELED layer
slope_weight = 0.05         risk_weight = 2.0         radiation_weight = 0.0
(slope_weight and radiation_weight can be changed per request, between 0 and 100)
total_cost = sum of step_cost of all the steps of the route
```

All weights are ≥ 0 and the cell values also are, so the multiplier is ≥ 1 and
A*'s octile heuristic remains admissible. With `radiation_weight = 0.0` (default
value) the costs and routes are the same as before adding the layer.

The origin adds no cost (the route starts from it). If origin and destination coincide,
`total_cost` and `distance_m` are 0. The backend publishes the weights in
`cost_model` of `/map`. In MOLA, `risk_weight` is 2.0 and is applied to the topographic
proxy defined above; the weight and the cost function are demonstrative,
not calibrated for real mobility.

## GET /api/v1/health

No parameters. Response `200`:

| Field | Type | Description |
|---|---|---|
| `status` | text | Always `"ok"` |
| `service` | text | `"mars-explorer-lab-api"` |
| `version` | text | Application version |
| `api_version` | text | `"v1"` |
| `data_source` | text | Active source: `"synthetic"` or `"mola"` |

**Real response of GET /api/v1/health**

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

No parameters. Response `200` with these fields:

| Field | Type | Description |
|---|---|---|
| `name` | text | Name of the zone |
| `data_source` | text | `"synthetic"` or `"mola"` |
| `is_simulated` | boolean | `true` for synthetic, `false` for MOLA |
| `disclaimer` | text | Provenance and limitations (the frontend must show it) |
| `grid` | object | `rows` (integer), `cols` (integer), `cell_size_m` (number) |
| `coordinate_system` | object | `type` = `"grid_index"`, `index_base` = 0, `row_axis` = `"down"`, `col_axis` = `"right"`, `description` |
| `cost_model` | object | `formula`, `slope_weight`, `risk_weight`, `radiation_weight` (optional, ≥ 0), `diagonal_length_factor`, `cost_unit` = `"cost_units"` |
| `cells` | list | List of cells with the format defined above |
| `risk_available` | boolean | Whether the source provides a risk model |
| `risk_model` | object | Optional; in MOLA it describes the topographic proxy and its limits |
| `radiation_available` | boolean | Optional; `true` if the cells carry the MODELED radiation layer |
| `radiation_model` | object | Optional; description of the MODELED layer (see `docs/FUENTES_DE_DATOS.md`) |
| `region` | object | Optional; geographic bounds in MOLA |
| `provenance` | object | Optional; MOLA only. Provenance per layer present (see below) |
| `global_grid` | object | MOLA only: dimensions, resolution, bounds and flat list of compact global cells |

### `provenance` field (optional)

An object whose keys are layers present in the response and whose value is
`{label, source, in_cost, note?}`. `label` is one of `MEDIDO`, `DERIVADO`,
`INDICADOR`, `MODELADO`, `INTERPRETADO`, `REFERENCIA` or `ÍNDICE DEL PROYECTO`.
`in_cost` indicates whether the layer enters A*'s cost **directly**. It is only published
for real sources (MOLA); in synthetic mode it does not appear. Today the following are emitted:

| Layer | `label` | `in_cost` | Present in |
|---|---|---|---|
| `elevation_m` | MEDIDO | `false` (enters through the slope) | all MOLA regions |
| `slope_deg` | DERIVADO | `true` | all MOLA regions |
| `risk` | DERIVADO (proxy `min(slope_deg/20, 1)`) | `true` | all MOLA regions |
| `blocked` | ÍNDICE DEL PROYECTO (rule: invalid cell or slope ≥ demonstrative processing threshold) | `false` (A* does not cross it) | all MOLA regions |
| `sky_view_factor` | DERIVADO | `false` (only chooses candidate waiting zones) | regions with a radiation layer (Gale) |
| `radiation_modeled` | MODELADO | `true` (weight 0 by default) | regions with a radiation layer (Gale) |
| `total_cost` | ÍNDICE DEL PROYECTO | `false` (it is the result) | all MOLA regions |

`INDICADOR` (soft terrain), `INTERPRETADO` (geology) and `REFERENCIA` (Curiosity
route) are not emitted because the backend does not serve those layers. Why
`sky_view_factor` is DERIVADO here and the F3 layer is MODELADO: see
`docs/FUENTES_DE_DATOS.md`.

Each `global_grid.cells` records `elevation_m`, `slope_deg`, `blocked` and
`valid`; its `row`/`col` indices are inferred from the row-column order of the array.
The list has 64,800 entries. The elevations are averages over 1° cells;
the slope is the maximum of the native MOLA slopes inside each cell.
Cells with a slope of 20° or more are blocked by a demonstrative rule.
The response is normal JSON and exceeds 4 MB uncompressed; the API offers gzip
to reduce traffic without changing the contract or the JSON the browser receives.

**Real response of GET /api/v1/map (abbreviated: `cells` shows 3 of the 140 cells)**

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

*(The API's literal texts, such as `disclaimer` and `formula`, are kept in Spanish exactly as the API returns them.)*

## POST /api/v1/routes — request

| Field | Type | Required | Description |
|---|---|---|---|
| `origin` | object `{row, col}` or `{latitude, longitude}` | yes | Origin cell/point |
| `destination` | object `{row, col}` or `{latitude, longitude}` | yes | Destination cell/point |
| `allow_diagonal` | boolean | no (default `true`) | Allows diagonal moves |
| `slope_weight` | number 0–100 | no (default that of `cost_model`, 0.05) | Slope weight for this request |
| `radiation_weight` | number 0–100 | no (default 0.0) | Weight of the MODELED radiation index for this request; no effect if the region does not carry the layer |

- Use both indices or both coordinates for each location. Do not mix formats
  between origin and destination, nor include fields of both formats in one location.
- `row` and `col` must be **JSON integers** (`2`, not `"2"` nor `2.0`). Coordinates
  must have latitude between −90° and 90° and longitude between 0° and 360°.
  A wrong type/range produces `422 VALIDATION_ERROR`.
- Additional fields are not allowed: they produce `422 VALIDATION_ERROR`.
- Weights must be finite JSON numbers between 0 and 100 (not text or booleans);
  otherwise, `422 VALIDATION_ERROR`. `risk_weight` cannot be adjusted per request.
  A request without weights gives exactly the same response as before F6.
- An index outside the grid is `400 OUT_OF_BOUNDS`. Geographic coordinates
  are only accepted with a MOLA source; in synthetic mode they produce
  `400 GEOGRAPHIC_ROUTE_UNAVAILABLE`.

**Example request**

```
{
  "origin": { "row": 2, "col": 1 },
  "destination": { "row": 2, "col": 12 },
  "allow_diagonal": true
}
```

**MOLA request in coordinates** (allows selecting any point on the
planet; approximate global route if an endpoint falls outside `region`):

```json
{
  "origin": { "latitude": 10.5, "longitude": 20.5 },
  "destination": { "latitude": 10.5, "longitude": 25.5 }
}
```

## POST /api/v1/routes — 200 response

| Field | Type | Description |
|---|---|---|
| `status` | text | `"ok"` |
| `data_source`, `is_simulated`, `disclaimer` | text, boolean, text | Identification of source and limitations |
| `origin`, `destination` | `{row, col}` and optionally latitude/longitude | Indices of the selected grid and cell center in geographic requests |
| `allow_diagonal` | boolean | Applied value |
| `path` | list of `{row, col}` with optional coordinates | Cells in order, **including** origin and destination; geographic routes include lat/lon centers for drawing |
| `summary` | object | Numerical results (next table) |
| `resolution` | optional text | `"mola-detail"` or `"mola-global-1deg"` for MOLA geographic requests |
| `cost_weights` | optional object | `slope_weight`, `risk_weight`, `radiation_weight` applied. **Only appears if the request carries any weight** |

| `summary` field | Type | Description |
|---|---|---|
| `steps` | integer | Number of moves = `len(path) - 1` |
| `distance_m` | number | Synthetic distance in meters |
| `total_cost` | number | Total cost in `cost_units` |
| `max_slope_deg` | number | Maximum slope among the route's cells |
| `mean_risk` | number | Mean risk of the route; not interpretable as an assessment if `risk_available` is false |
| `max_risk` | number | Maximum risk of the route; not interpretable as an assessment if `risk_available` is false |
| `nodes_expanded` | integer | Nodes expanded by A* (informative) |

**Real response of POST /api/v1/routes**

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

Edge case: if `origin` and `destination` coincide, `path` has a single cell, `steps` = 0, `distance_m` = 0 and `total_cost` = 0.

## POST /api/v1/routes/shelter — "solar alert" mode

Given an origin, it returns the lowest-cost route to the nearest **candidate waiting
zone** *by cost* (not by distance). It is an educational planning aid:
it does not guarantee protection nor is it an operational recommendation.

**Candidate waiting zone** (project criterion, `ÍNDICE DEL PROYECTO`): a valid and free
cell with `slope_deg ≤ max_slope_deg` (10° by default) and
`sky_view_factor ≤ max_sky_view_factor` (0.90 by default). `sky_view_factor`
only **chooses** the zone; the route cost uses the usual formula, without it
(−0.90 correlation with the slope: penalizing it would punish twice). The
justification of the thresholds is in `docs/FUENTES_DE_DATOS.md`.

| Field | Type | Required | Description |
|---|---|---|---|
| `origin` | `{row, col}` or `{latitude, longitude}` | yes | Coordinates only inside `region` (the global mesh does not carry the layer) |
| `allow_diagonal` | boolean | no (`true`) | Same as in `/routes` |
| `slope_weight`, `radiation_weight` | number 0–100 | no | Same as in `/routes` |
| `max_slope_deg` | number 0–90 | no (10) | Maximum slope of the candidate zone |
| `max_sky_view_factor` | number 0–1 | no (0.90) | Maximum visible sky of the candidate zone |
| `max_distance_km` | number > 0 | no (no default value = no limit) | Maximum distance of the lowest-cost route to the candidate zone |

With `max_distance_km`, a candidate zone is only accepted if **its lowest-cost
route** measures at most that distance (inclusive limit); if the cheapest one
exceeds it, the next one is searched. The cheapest route among all those that
fit in the distance is not searched. If no reachable zone is within it: `404 NO_SHELTER`.

It does not accept `destination` or additional fields (`422`). The `200` response has
the same fields as `/routes` (`destination` is the chosen zone; `resolution`
is `"mola-detail"` in geographic requests) plus `shelter`:

| `shelter` field | Description |
|---|---|
| `term` | `"zona candidata de espera"` (candidate waiting zone) |
| `label` | `"ÍNDICE DEL PROYECTO"` |
| `criterion` | Text with the criterion applied |
| `max_slope_deg`, `max_sky_view_factor` | Thresholds applied |
| `candidates_count` | Cells of the region that meet the criterion (reachable or not) |
| `distance_km` | Distance traveled to the zone, in km (always present; equal to `summary.distance_m` / 1000 and approximate like it) |
| `max_distance_km` | Limit applied; only appears if the request carries it |
| `destination_slope_deg`, `destination_sky_view_factor` | Values of the chosen zone |
| `sky_view_factor_role` | Clarifies that `sky_view_factor` does not enter the cost |
| `note` | Educational planning notice and limits of the model |

If the origin already meets the criterion, `path` has one cell and `total_cost` = 0.
Own errors: `400 SHELTER_LAYER_UNAVAILABLE` and `404 NO_SHELTER` (error
table). `CELL_BLOCKED` and `OUT_OF_BOUNDS` behave as in `/routes`, with
`field: "origin"`.

## MOLA mode

The backend selects a single source for `/health`, `/map` and `/routes`:

```bash
MARS_DATA_SOURCE=mola
# Optional: without this variable data/processed/mola_valles_marineris.json is used
MARS_MOLA_GRID_FILE=../data/processed/mola_valles_marineris.json
# Alternative by name (MARS_MOLA_GRID_FILE takes priority):
MARS_MOLA_REGION=gale
```

The `gale` region keeps `data_source: "mola"` and the same cell format.
Its elevation comes from the combined MOLA+HRSC DEM (see `docs/FUENTES_DE_DATOS.md`).
The JSON includes additional metadata (`source`, `aggregation`) that API v1 does not
publish.

In MOLA, `disclaimer` (in `/map` and `/routes`) is the text declared by the JSON of
the active region. If the JSON carries no valid one, the generic MOLA text is used.
The field remains a required text, so the v1 contract does not change.
For Gale it begins: «DEM mezcla MOLA+HRSC 200 m agregado a 600 m; resolución
de planificación, no de navegación» ("MOLA+HRSC blended 200 m DEM aggregated to 600 m;
planning resolution, not navigation"), and cites Fergason, Hare and Laura (2018).
Gale is today the only region with the MODELED radiation layer (`sky_view_factor`,
`radiation_modeled`, `radiation_model`); its disclaimer declares it.

The detail grid is generated from the original PDS4/ENVI files with
`data/process_mola.py`; the compressed global mesh is generated with
`python3 -m data.process_mola_global`. Neither process replaces existing
output files. The MOLA map adds `region`, geographic centers,
`global_grid` and the slope proxy. Invalid cells are blocked and
their neutral value `risk: 0.0` does not indicate low-risk terrain. `distance_m` is
computed with the nominal size at the Martian equator and is approximate at other
latitudes. The 1° global mesh and the proxy are educational, not a validated
mobility or safety layer.

Without a processed MOLA grid, the map/route endpoints respond
`503 DATASET_UNAVAILABLE`; synthetic mode remains the
default.

## Error format

All errors (400, 404, 405, 422, 503) use the same structure. `details` is always an object (it may be empty).

| HTTP | `error.code` | When it occurs | Content of `details` |
|---|---|---|---|
| 400 | `OUT_OF_BOUNDS` | Origin or destination outside the grid | `field`, `row`, `col`, `rows`, `cols` |
| 400 | `CELL_BLOCKED` | Origin or destination on a blocked cell | `field`, `row`, `col` |
| 400 | `SHELTER_LAYER_UNAVAILABLE` | `/routes/shelter` without a `sky_view_factor` layer (synthetic, regions without the layer) or with a geographic origin outside `region` | `reason` (`no_sky_view_layer` or `outside_detail_region`), `data_source` |
| 404 | `NO_ROUTE` | No traversable path exists | `origin`, `destination`, `nodes_expanded` |
| 404 | `NO_SHELTER` | No candidate waiting zone meets the criterion, is reachable or falls within `max_distance_km` | `origin`, `criterion`, `candidates_count`, `nodes_expanded` and, if requested, `max_distance_km` |
| 404 | `NOT_FOUND` | Nonexistent URL | (empty) |
| 405 | `METHOD_NOT_ALLOWED` | HTTP method not allowed on the URL | (empty) |
| 422 | `VALIDATION_ERROR` | Invalid body: missing field, wrong type, extra field or malformed JSON | `problems`: list of `{field, message}` |
| 503 | `DATASET_UNAVAILABLE` | Selected source or processed MOLA region not available | `data_source` |

`field` takes the value `"origin"` or `"destination"`. The `message` text is suitable for showing to the user (except `message` inside `problems`, which Pydantic generates in English and is for debugging only).

**Real example: 400 CELL_BLOCKED  (request origin (3,6), destination (2,2))**

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

**Real example: 400 OUT_OF_BOUNDS  (request origin (-1,0), destination (2,2))**

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

**Real example: 404 NO_ROUTE  (request origin (2,1), destination (8,11))**

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

**Real example: 422 VALIDATION_ERROR  (request without `destination`)**

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

## Compatibility rules

- Do not rename or remove fields. Adding new optional fields is compatible; the frontend must ignore fields it does not know.
- Do not change types (an integer does not become text). Do not change the order of `path`.
- Any incompatible change requires a new URL version (`/api/v2`).
- The frontend must not depend on the order of `cells`; it must use `row` and `col` of each cell.
