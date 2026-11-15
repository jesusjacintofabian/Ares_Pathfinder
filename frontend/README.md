# Frontend — Ares Pathfinder

Web interface with Leaflet to explore a grid and request routes from the backend.
The A* computation is done by the backend. MOLA mode shows a global colorized
relief, generated locally from the MOLA MEGDR product and reduced to 0.5°
per pixel, together with a mask of blocked cells of the global route grid.
The optional risk shading shows a topographic proxy based solely
on slope (`min(slope / 20°, 1)`); the same indicator is applied to the detail
and penalizes MOLA routes. It is not a probability nor does it estimate geological hazards or safety.
Points can be selected anywhere on Mars: A* uses an approximate 1° MOLA mesh
outside the detail region, and the local grid inside it.

## Run
1. Start the backend from `backend/`. For the MOLA mosaic and grid (Valles Marineris region by default; without `MARS_DATA_SOURCE` synthetic mode is used):
   ```bash
   MARS_DATA_SOURCE=mola \
   ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
2. From `frontend/`: `python3 -m http.server 5500 --bind 127.0.0.1`
3. Open http://127.0.0.1:5500

The API URL is in `js/config.js` (by default `http://127.0.0.1:8000`).
Leaflet 1.9.4 is included locally in `vendor/leaflet/` (no Internet required).
On the MOLA map, «Marte completo» ("Whole Mars") shows the planetary relief and «Ir a zona
MOLA» ("Go to MOLA zone") zooms to the highest-detail crop. The global image is generated with
`python3 data/render_mola_preview.py`; the 1° route mesh is generated with
`python3 -m data.process_mola_global` and is served as compact data by the API;
it also generates the global visualization of the slope proxy.
If both points are inside the local region, the detail is used; otherwise,
the route uses the global mesh. «Imagen orbital Viking» ("Viking orbital image") and the NASA/JPL place names are
optional layers that require Internet. Place names are not hazards; there is no
validated global hazard layer integrated into the application. The MOLA
risk proxy uses slope, not hazard observations.
When place names are activated, only large features are shown with the
global view; when zooming in, smaller features are gradually added. The permanent
labels are spaced apart to avoid overlapping and those with the largest diameter are prioritized.


## Rover trajectory layers

In MOLA mode, the left panel lets you turn on/off the trajectories of
Perseverance, Curiosity, Opportunity, Spirit and Zhurong. When one of those
missions is selected, the map centers on its region and shows the reference trajectory, the landing
site and points of interest with pop-up windows. The NASA gallery is kept
as an independent complement and both panels stay collapsed until they are
needed.

The included traverses are didactic approximations and not official telemetry. They are
overlaid on the global MOLA relief. The 1° mesh is approximate (about 59 km per
cell at the equator) and neither it nor the MOLA detail are tools for operational
navigation or guarantees of safety.


## Gale region: provenance, weights and solar alert

With the backend on `MARS_DATA_SOURCE=mola MARS_MOLA_REGION=gale`, the interface uses only what
the API already publishes (see `docs/CONTRATO_DE_DATOS.md`):

- **Provenance labels.** Next to each layer and the total cost appears the
  `provenance` label (MEDIDO, DERIVADO, MODELADO, ÍNDICE DEL PROYECTO — i.e. MEASURED, DERIVED, MODELED, PROJECT INDEX). Hovering or
  focusing on it shows the source and whether it enters the cost. They also appear in Valles Marineris, because
  the backend publishes `provenance` in all MOLA regions; in synthetic mode there are none.
- **Cost weights** (only if `/map` brings `radiation_available: true`). There is a slider from
  0 to 100 with a numeric field for `slope_weight` (0.05 by default) and another for
  `radiation_weight` (0 by default). They are sent to `POST /routes`, and the result shows the
  `cost_weights` applied. In the other regions the request does not change.
- **Shielding index · MODELED.** It is a toggleable layer, off by default. It paints
  `1 − radiation_modeled`: the inversion is done by the interface, because the API publishes the
  relative exposure. The scale is relative to the range of the region. It is not a dose nor a
  measurement, and it exaggerates the shielding by the relief because it does not include atmospheric attenuation.
- **Solar alert.** From the chosen origin it calls `POST /routes/shelter`, with the same
  weights and an optional maximum distance (`max_distance_km`). It draws in amber the route to the
  **candidate waiting zone** ("zona candidata de espera") and shows the distance, the criterion and the educational note.
  If the response is `NO_SHELTER`, it explains that it is a model result and not a failure.
  It only works with origins inside the detail zone.

Performance: Gale has 5,600 cells. The cell layers (elevation, slope, risk,
shielding, grid and the invisible click layer) are drawn with `L.canvas()`, with one
renderer per pane. The route, pins, blocked cells and missions remain in
SVG/DOM. The click layer on canvas goes below place names, route, pins and missions,
because a `<canvas>` captures the pointer over its whole surface. This way, the markers and tooltips
of missions receive the click even inside the detail zone. Where there is no marker, the
canvas finds the cell by geometry or passes the click to the map (global mesh). With `?perf=1`
in the URL the map construction is measured (`window.__marsPerf`, the console and an on-screen
box); `MarsMap.getLayerStats()` gives the visible elements per layer.

## Interface tests (jsdom)

They require Node.js (22.22+ or 24.15+). jsdom is only a development dependency: the
browser does not use it.

```bash
cd frontend
npm install     # once; installs jsdom in node_modules/ (outside Git)
npm test        # node --test: loads index.html, Leaflet and the js files with a fake fetch
```

The tests cover synthetic mode, a MOLA region without radiation (like Valles) and a reduced
Gale: labels, weights, shielding layer, solar alert (including `NO_SHELTER`
and an origin outside the zone) and the vocabulary («zona candidata de espera» — "candidate waiting zone" — never
«refugio» — "shelter"). jsdom does not paint: the real drawing time is measured in a browser with `?perf=1`.
