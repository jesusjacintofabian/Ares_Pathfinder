# Laboratory architecture

```text
data/raw/mola/
  .img + .xml + .hdr ──▶ data/mola_reader.py (mmap)
                             ├── data/process_mola.py ─────▶ detail JSON
                             ├── data/process_mola_global.py ▶ global JSON.gz (1°)
                             └── data/render_mola_preview.py ▶ global PNG (0.5°)
                                      │                 │              │
                                      └─────────────────┴──────────────┘
                                                        ▼
                                                   FastAPI
                               /api/v1/map, /routes and /routes/shelter
                                                        │
                                                        ▼
                                                Leaflet frontend
                              ├── local global MOLA relief (0.5°)
                              ├── global route mesh (1°) + blocked cells
                              ├── optional Viking (NASA Mars Trek)
                              ├── visible nomenclature (NASA/JPL)
                              ├── local MOLA detail + A* route (cell layers on canvas)
                              ├── per-layer provenance labels (provenance)
                              └── Gale: weights, shielding index and solar alert
```

## MOLA topographic flow

1. Obtain the `megt90n000eb` product and keep the original raster, the PDS4
   `.xml` label and the ENVI `.hdr` header unmodified under `data/raw/mola/`.
2. `data/mola_reader.py` reads the dimensions and binary type from the PDS4 label,
   validates the raster and uses `numpy.memmap` to avoid loading the whole globe.
   The local processor reads the requested crop; the global one averages elevations to
   1° and keeps, as each cell's slope, the maximum of the native MOLA slopes
   it contains. Longitudinal periodicity is taken into account when
   deriving slopes on the global mesh.
3. `data/process_mola.py` converts the crop into a small JSON grid
   in `data/processed/`. Cells without data are marked invalid and blocked.
   `data/render_mola_preview.py` generates the global equirectangular PNG of
   `720 × 360` pixels (0.5° per pixel). `data/process_mola_global.py` generates
   the compressed route mesh and its PNG mask of blocked cells.
4. The backend loads both MOLA grids when
   `MARS_DATA_SOURCE=mola` is configured. A* uses the same `Grid`/`GridCell`; the
   algorithm is not modified and the synthetic dataset is not removed.
5. `/api/v1/map` exposes the local crop and the compact global mesh.
   `/api/v1/routes` accepts legacy local indices or geographic coordinates:
   it uses the detail if both endpoints are inside the active region; otherwise it
   computes on the global mesh. Geographic routes include cell centers so they
   can be drawn directly in Leaflet.

## Source selection

- With no configuration, `MARS_DATA_SOURCE=synthetic` is the default value.
- For MOLA, `MARS_DATA_SOURCE=mola` is enough: with no further configuration the
  **Valles Marineris** region is used (`data/processed/mola_valles_marineris.json`, 32 × 32 cells, 96 blocked
  with a 20° threshold). For another region, process it and point `MARS_MOLA_GRID_FILE` to the JSON
  inside `data/processed/`. The flat equatorial sample (`mola_region.json`) is kept as a control.
- Routes outside the active region use
  `data/processed/mola_global_1deg.json.gz`, with 180 × 360 cells. The API loads it
  when starting the MOLA dataset; therefore that versioned file is necessary
  for MOLA operation, even if the original raster is not included.
- The crop allows up to 250,000 cells; this prevents exposing the native
  global matrix of 16,588,800 cells to the JSON response and the planner.
  The 1° mesh has 64,800 compact entries.
- Route requests accept the legacy index format and MOLA
  geographic coordinates. The client does not need to send a source selector: map and
  routes use the backend configuration.

## Frontend

- `js/api.js` only communicates. `postRoute` adds `slope_weight` and `radiation_weight` only
  if they are passed; `postShelter` calls `/routes/shelter`. The backend computes all routes.
- `js/app.js` shows the `provenance` labels (source and role in the cost, in the title).
  If `/map` brings `radiation_available`, it also shows:
  - the weights card;
  - the shielding index layer;
  - the solar alert.

  For the other sources the interface and the requests do not change. `NO_SHELTER` is presented
  as a model result, not as an error.
- `js/map.js` draws the cell layers with `L.canvas()`, with one renderer per pane:
  elevation, slope, risk, shielding, grid and the invisible click layer.
  The route, pins, blocked cells and missions remain in SVG/DOM. A `<canvas>`
  captures the pointer over its whole surface, so the click layer (pane 452) sits
  below place names, route, pins and missions. Where there is no marker on top, the canvas
  finds the cell by geometry or passes the click to the map (global mesh).
- The shielding index is `1 − radiation_modeled`, computed in the interface only to
  paint it. Its scale is relative to the actual range of the region.
- With `?perf=1`, the interface measures the map construction (`window.__marsPerf`).

## Scientific and geometric limits

- MOLA provides topography relative to the areoid, not a hazard layer. MOLA's
  `risk` is an educational topographic proxy: `min(slope_deg / 20, 1)`.
  It is published in the global and detail cells and has weight 2.0 in A*; it is not
  a probability nor does it estimate geological hazards or safety. Invalid
  MOLA cells are blocked and their proxy is not available.
- The default 30° slope threshold is a configurable demonstration
  rule, not a validated traversal limit for a mission.
- The slope computation uses the Martian radius declared by the product and
  corrects the east-west scale by latitude. A* keeps the original scalar
  `cell_size_m`; the reported distance uses the nominal size at the equator
  and is approximate away from it.
- In MOLA mode, Leaflet represents latitude/longitude on an equirectangular
  grid, with east-positive longitudes from 0° to 360°. The planetary
  view is an image derived from the MOLA product, sampled at 0.5° per
  pixel; an independent 1° mesh allows selecting and computing approximate
  routes across the whole planet. The «Marte completo» ("Whole Mars") button shows the globe
  and «Ir a zona MOLA» ("Go to MOLA zone") zooms to the highest-detail crop.
- The Viking MDIM 2.1 base map has a nominal resolution of 232 m/pixel at the
  equator; it is not equivalent to current high-resolution orbital imagery.
  It is loaded on demand and requires Internet. Synthetic mode keeps its local
  grid.
- Place names are queried by visible extent from `combinedNom` of
  NASA/JPL Mars Trek. The diameter filter changes progressively with zoom
  (1,000, 500, 200 and 50 km; at detail zoom all are admitted); for each view,
  large features and non-overlapping labels are prioritized. These
  data are nomenclature; they are not a hazard layer.
- A route is the optimum of the configured cost model; it does not guarantee
  safety, communication, energy or rover/person traversability.

## Tests and contracts

The reader tests build small PDS4/ENVI rasters in temporary files. The
API tests verify the legacy format, global geographic routes and detail
selection in an active region. In addition, `test_mola_default_region.py` checks
the default region (relief, blocked cells and routes that avoid them).
`tests/integration_check.py` validates, against real servers, synthetic mode, MOLA
(`--mola`) and Gale (`--gale`: provenance, radiation layer and `/routes/shelter`).

The interface is tested with jsdom (`cd frontend && npm test`). The tests load
`index.html`, Leaflet and the real scripts with a fake `fetch` and a fake 2D context:
- request bodies;
- labels, weights, layers and checkboxes;
- solar alert and vocabulary;
- clicks and hover by coordinates over the canvas.

jsdom does not paint; real painting is checked with the manual checklist in the README.

- **Data and API:** `docs/CONTRATO_DE_DATOS.md`
- **Provenance:** `docs/FUENTES_DE_DATOS.md`
- **Automatic FastAPI documentation:** `/docs`

## Alignment with the challenge

The architecture allows gradually combining layers from different missions.
MOLA is the first integrated topographic layer; other missions and any
risk model require independent sources, metadata and validation.
