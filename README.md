# Ares Pathfinder 🚀

Planning map for a surface walk (EVA) on Mars, developed for the **NASA Space Apps Challenge 2026**: *Interplanetary Survival Guide: Martian Map*.

> **Important:** this is a NASA Space Apps Challenge participants' project. It is not an official NASA product nor an operational safety recommendation: it is an educational and planning prototype.

*Note: this README was translated from Spanish to English. The app's interface is in Spanish, so interface labels are quoted in Spanish with an English gloss in parentheses where needed.*

## 🎯 Problem and solution

**Problem.** An astronaut on a walk across the Martian surface must reach a valuable scientific target and return to the habitat without being exposed to slopes their suit does not allow or to avoidable exposure, and needs to be able to change plans if space weather worsens during the outing.

**Study region.** Gale Crater, northwest flank of Mount Sharp (Aeolis Mons), where Curiosity has studied *boxwork* formations. The window used (≈ 47 × 41 km) is provisional and **does not mark the location of *boxwork* formations**: their coordinates are not verified in this repository.

**Solution.** An API (FastAPI + A*) and an interactive map (Leaflet) that compute routes over a 600 m grid of the region and show where each layer comes from:

| Layer | Label | Origin |
|---|---|---|
| Elevation | MEDIDO (MEASURED) | 200 m MOLA+HRSC DEM (USGS), aggregated to 600 m |
| Slope | DERIVADO (DERIVED) | Computed at 200 m from elevation; the block maximum is stored |
| Topographic shielding index | MODELADO (MODELED) | Fraction of sky visible from the DEM; **it is not a dose** |
| Total route cost | ÍNDICE DEL PROYECTO (PROJECT INDEX) | Combination with adjustable weights; **it is not a probability or a guarantee** |

- **Solar alert:** `POST /api/v1/routes/shelter` computes the lowest-cost route to the nearest "candidate waiting zone" (low slope and terrain that blocks part of the sky, according to the model). If there is none nearby, it responds `NO_SHELTER`: this is a model result, not a failure.
- **Optical context image:** Viking MDIM 2.1 mosaic from NASA Mars Trek (optional layer, requires Internet).
- **Adjustable weights** for slope and modeled radiation per request.

**What this prototype does NOT yet include** (so as not to overstate it): thermal data (THEMIS), the USGS geologic map, Curiosity's proposed path georeferenced, soft terrain, elevation in the radiation model, or real-time space weather data. Radiation is an educational model with assumptions documented in `docs/FUENTES_DE_DATOS.md`, conceptually anchored in the measurements of Curiosity's RAD instrument (whose figures were not verified against the full paper and are not used in the calculation).

## 👥 Team

| Member | Responsibility |
|---|---|
| **Jesús** | Backend, A* algorithm, data processing, tests and documentation |
| **Aldo** | Frontend (web interface with Leaflet) |

## 🤖 Use of AI

This project was developed with AI assistance, and we declare it as NASA Space Apps requires:

- **Code, tests and documentation** were written with the help of Claude (Anthropic), through chat and Claude Code. Commits made with that assistance carry the line `Co-Authored-By: Claude` in their message.
- The team defined the problem, chose the region and the resources, reviewed the results and is responsible for the content.
- The **scientific data** come from the sources cited in `docs/FUENTES_DE_DATOS.md`, not from the AI.
- The map images (`frontend/assets/`) are generated with scripts from the MOLA raster (`data/render_mola_preview.py`, `data/process_mola_global.py`), not with generative AI.
- There is a support agent for GitHub Copilot in `.github/agents/`.

## 🧰 Technologies

- **Frontend:** HTML, CSS and JavaScript without frameworks.
- **Interactive map:** Leaflet 1.9.4 (included in `frontend/vendor/`, no CDN).
- **Backend:** Python, FastAPI, Uvicorn and Pydantic.
- **Algorithms:** A* for route finding (`algorithms/astar.py`, standard library only).
- **Data:** reproducible synthetic grid and MOLA topography (PDS4/ENVI, read with NumPy).
- **Version control:** Git and GitHub.
- **Tests:** Pytest, an integration script and interface tests with jsdom (`cd frontend && npm test`; see `frontend/README.md`).

## 📁 Repository structure

```text
Ares_Pathfinder/
├── frontend/                 # Web interface and Leaflet map
│   ├── index.html
│   ├── css/styles.css
│   ├── js/ (config.js, api.js, map.js, app.js)
│   ├── assets/mola-global.png   # global MOLA relief, 0.5° preview
│   └── vendor/leaflet/       # Local Leaflet 1.9.4
├── backend/                  # FastAPI API
│   ├── app/ (main.py, errors.py, api/, models/, services/)
│   ├── tests/
│   ├── pytest.ini
│   └── requirements.txt
├── algorithms/               # A* algorithm and route costs
├── data/
│   ├── generate_synthetic_grid.py   # generates the synthetic data
│   ├── mola_reader.py               # MOLA raster reader (PDS4/ENVI)
│   ├── process_mola.py              # crops a MOLA region to JSON
│   ├── geotiff_reader.py            # int16 GeoTIFF reader (local or via HTTP ranges)
│   ├── process_dem.py               # crops the 200 m MOLA+HRSC DEM to JSON (Gale)
│   ├── render_mola_preview.py       # generates the lightweight global map view
│   ├── raw/mola/                    # originals (.xml and .hdr versioned; .img is downloaded)
│   ├── raw/gale/                    # raw crop of the Gale DEM (not versioned)
│   └── processed/                   # JSON grids ready for the API
├── docs/
│   ├── PLAN_DE_FASES.md
│   ├── ARQUITECTURA.md
│   ├── FUENTES_DE_DATOS.md
│   ├── CONTRATO_DE_DATOS.md
│   └── FLUJO_GIT.md
├── tests/                    # Integration check (real servers)
├── .github/agents/           # Ares.AI agent for GitHub Copilot
├── .gitignore
└── README.md
```

## 🗺️ Features

1. Show an area on an interactive map (synthetic grid or global MOLA relief view with a detail region).
2. Turn information layers on and off.
3. Select an origin point and a destination anywhere on the MOLA globe.
4. Compute a route with A* in the backend: approximate 1° global mesh or local detail.
5. Consider distance costs, slope and the MOLA slope proxy (or simulated risk in synthetic mode).
6. Draw the computed route on the map.
7. Show a summary: distance, cost, steps, maximum slope and risk.

Synthetic mode identifies its risks as simulated. In MOLA mode, an educational
topographic-risk proxy derived solely from slope is shown:
`min(slope / 20°, 1)`. It is computed for the global mesh and the detail, and it also
penalizes routes. It is not a probability and does not model geological hazards or mission
conditions; it must not be interpreted as a safety assessment.

## 🛠️ Work plan and status

| Phase | Name | Status | Deliverable |
|---|---|---|---|
| 0 | Preparation | ✅ Done | Organized repository and prepared environment. |
| 1 | Data and initial map | ✅ Done | Synthetic data and MOLA region documented in `docs/FUENTES_DE_DATOS.md`. |
| 2 | Basic backend | ✅ Done | API with `/health`, `/map` and `/routes`. |
| 3 | Basic frontend | ✅ Done | Leaflet map with layers and controls. jsdom tests and headless Firefox verification; the manual checklist (below) remains for other browsers and touch. |
| 4 | Routes and risks | ✅ Done | A* with slope costs and simulated risk or MOLA topographic proxy. |
| 5 | Testing and integration | 🔄 In progress | 445 Pytest tests, 29 jsdom tests and synthetic/MOLA/Gale integration done; an extended technical guide is missing. |
| 6 | Wrap-up and delivery | ⏳ Pending | Demo, Space Apps form and lessons learned. |

Phases may change if technical difficulties arise or if a technology needs to be learned before continuing.

## 🚀 Getting started

### 1. Clone the repository

```bash
git clone https://github.com/<user>/Ares_Pathfinder.git
cd Ares_Pathfinder
```

### 2. Prepare the backend (from the root, once)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

`requirements.txt` includes FastAPI, Uvicorn, Pydantic, Pytest, httpx2 and **NumPy** (needed by the MOLA reader; it is imported even in synthetic mode). Versions are pinned; they were verified with Python 3.12.3 (the author's environment uses Python 3.14).

### 3. Check that everything works

```bash
cd backend
python -m pytest -q          # 445 tests should pass
```

Interface tests (jsdom, require Node.js 22.22+ or 24.15+):

```bash
cd frontend
npm install                  # once; jsdom is a development-only dependency
npm test                     # 29 tests should pass
```

### 4. Run backend and frontend

```bash
# Terminal 1 — backend (from backend/, with the environment activated)
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2 — frontend (from frontend/)
python3 -m http.server 5500 --bind 127.0.0.1
# Open http://127.0.0.1:5500
```

Interactive API documentation at http://127.0.0.1:8000/docs.

### 5. Integration check (from the root, with both servers running)

```bash
python3 tests/integration_check.py            # synthetic mode: 26 checks
python3 tests/integration_check.py --mola     # backend with MARS_DATA_SOURCE=mola (Valles Marineris): 30 checks
python3 tests/integration_check.py --gale     # backend with MARS_DATA_SOURCE=mola MARS_MOLA_REGION=gale: 39 checks
```

Each mode checks that the backend started as expected: for example, `--mola` against a
Gale backend fails on purpose.

### 6. Manual browser checklist

Automated tests (jsdom) do not render, and headless Firefox verification does not cover
real screens, touch or other browsers. Before a demo, check by hand, with
both servers running (tick each item):

**Synthetic mode** (backend without variables)
- [ ] The banner says «DATOS SIMULADOS» ("SIMULATED DATA") and no provenance labels, weights or solar alert appear.
- [ ] Origin at row 2, col 1 and destination at row 2, col 12 → «Ruta calculada: 14 pasos, 1772.8 m» ("Route computed: 14 steps, 1772.8 m").
- [ ] A click on a blocked cell shows the warning and does not select it.

**MOLA, Valles Marineris** (`MARS_DATA_SOURCE=mola`)
- [ ] Layers carry labels (MEDIDO, DERIVADO, ÍNDICE DEL PROYECTO) and hovering shows the source.
- [ ] «Ir a zona MOLA» ("Go to MOLA zone"): a click on a cell selects it; a click outside the zone uses the global mesh.
- [ ] Slope and grid toggle on and off; zoom and drag are smooth.
- [ ] Perseverance layer: clicking a marker opens its window and hovering over the trajectory shows its tooltip.
- [ ] With Internet: Viking image and place names.

**MOLA, Gale** (`MARS_DATA_SOURCE=mola MARS_MOLA_REGION=gale`)
- [ ] «Pesos del costo» ("Cost weights"), «Alerta solar» ("Solar alert") and the «Índice de apantallamiento» ("Shielding index", MODELADO) checkbox appear.
- [ ] The slider and the numeric field of each weight stay in sync; 150 shows an error and disables «Calcular ruta» ("Compute route"); «Restablecer» ("Reset") returns to 0.05 and 0.
- [ ] A route shows «Pesos aplicados» ("Applied weights"); with radiation 5 the cost goes up.
- [ ] The shielding layer paints the zone and its legend explains `1 − radiation_modeled` and its limits.
- [ ] Solar alert from a free origin: dashed amber route, «Zona candidata de espera» ("Candidate waiting zone") marker, distance, criterion and educational notice.
- [ ] With maximum distance 5 km from lat −4.79°, lon E 137.75° the informational message appears saying there is no candidate zone (not an error).
- [ ] An origin outside the detail zone explains that the solar alert only works inside it.
- [ ] Curiosity layer: markers inside Gale open their window without selecting the cell.
- [ ] The word «refugio» ("shelter") does not appear in any text and no protection is promised.

**General**
- [ ] Chrome, Firefox and Safari (or whichever you will use in the demo).
- [ ] Mobile or touch screen: tap cells, drag and pinch-zoom.
- [ ] High-density screen: canvas layers look sharp.
- [ ] `?perf=1` in the URL shows the measurement box with `canvases` and the paint time.

## 🌐 Geospatial data

Before using real data:

1. Select a small study area.
2. Record the source, format, query date and license or terms of use.
3. Check that they can be processed with the project's tools.
4. Document how they were prepared.

Large files are not added to the repository: the MOLA raster `megt90n000eb.img` (33 MB) is in `.gitignore` and is downloaded from PDS (see below). The `.xml` label, the `.hdr` header, the processed regions (small JSONs) and the optimized global view (PNG) are versioned.

## 🛰️ MOLA topographic mode

The source is the `megt90n000eb` product from the PDS4 MOLA MEGDR archive: a global matrix of 2880 × 5760 `SignedMSB2` elevations (big-endian int16), in meters relative to the areoid. Its resolution is 1/16°; 3.704461 km/pixel is the nominal scale at the Martian equator. The reader uses memory mapping and only extracts the geographic window requested for routes.

The map includes a global context image (0.5°/pixel) and a global MOLA
navigation mesh of 1° (180 × 360), stored compressed in
`data/processed/mola_global_1deg.json.gz`. When two points are selected inside the
active crop (Valles Marineris by default), A* uses the local detail; if one
falls outside, it uses the approximate global mesh. The global mesh blocks cells with
a native maximum slope of 20° or more. This is an educational rule and does not represent
a real safety or traversability assessment. The map also shows
a mask of those blocks over the planet.
The API automatically gzip-compresses the global JSON response to reduce
traffic; the browser decompresses it without additional steps.

The colorized view is regenerated with `python3 data/render_mola_preview.py`. The
route mesh and the mask are generated together with `python3 -m data.process_mola_global`; they require the original MOLA raster, and the generator
does not overwrite existing files.

### Included regions

| File | Region (lat. / east lon.) | Cells | Max. slope | Blocked cells | Use |
|---|---|---|---|---|---|
| `data/processed/mola_valles_marineris.json` | −14° to −12° / 291° to 293° | 32 × 32 | 32.2° | 96 (20° threshold) | **Default in MOLA mode.** It has about 9 km of relief, so A* has to go around obstacles. |
| `data/processed/mola_region.json` | −1° to 1° / 179° to 181° | 32 × 32 | 2.5° | 0 (30° threshold) | Flat equatorial sample, useful as a control. |
| `data/processed/gale_monte_sharp_600m.json` | −5.31° to −4.50° / 137.30° to 138.01° | 80 × 70 (600 m) | 34.9° | 15 (30° threshold) | Gale Crater, northwest flank of Mount Sharp. **200 m MOLA+HRSC DEM**, aggregated to 600 m (block maximum slope). Provisional window. Includes the **MODELED** radiation layer (sky visible from the DEM; not a measurement). |

`POST /api/v1/routes` accepts the optional weights `slope_weight` and `radiation_weight` (between 0 and 100).
In regions with `sky_view_factor` (today, Gale), `POST /api/v1/routes/shelter` ("solar alert" mode) computes
the route to the nearest **candidate waiting zone** by cost. In MOLA, `GET /api/v1/map` publishes
`provenance` with the label of each layer. The frontend shows those labels and, in Gale, the weights, the
shielding index layer and the solar alert (see `frontend/README.md`). Details in `docs/CONTRATO_DE_DATOS.md`. This is educational planning: no
route or zone is presented as safe.

### Download the original raster (only if you want to process other regions)

Get the `.img`, `.xml` and `.hdr` from the [official PDS Geosciences Node directory](https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg016/) and save them unmodified in `data/raw/mola/` (the `.xml` and `.hdr` are already in the repository; only the `.img` is missing). Check the MD5 given in `docs/FUENTES_DE_DATOS.md`.

### Process a new region

```bash
python data/process_mola.py \
  --bounds -14 -12 291 293 \
  --max-slope-deg 20 \
  --output data/processed/mola_my_region.json
```

The destination must be new: the processor does not overwrite existing files. `--bounds` takes `south north west east` in degrees (planetocentric latitude, positive east longitude between 0° and 360°). The window cannot cross the 0 meridian and is limited to 250,000 cells. Cells without data are marked invalid and blocked. The slope blocking threshold (30° by default) is for demonstration.

### Process a window of the MOLA+HRSC DEM (200 m)

The global USGS GeoTIFF is about 11 GB and is **not downloaded**. `data/process_dem.py` reads over
HTTP ranges only the requested window and saves a small raw crop so it can be reprocessed without network. It adds no
dependencies: it only uses NumPy.

```bash
python data/process_dem.py \
  --dem https://planetarymaps.usgs.gov/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif \
  --bounds -5.3 -4.5 137.3 138.0 --aggregate 3 \
  --save-raw data/raw/gale/my_crop.tif \
  --output data/processed/gale_my_window.json

# MODELED radiation: the horizon is searched up to 10 km (this is also the read margin).
# --horizon-radius-km 0 disables it.

# Reprocess later without network, from the raw crop:
python data/process_dem.py --dem data/raw/gale/my_crop.tif \
  --bounds -5.3 -4.5 137.3 138.0 --aggregate 3 --output data/processed/other.json
```

`--aggregate 3` groups 3 × 3 pixels (600 m cells): mean of the elevation and maximum of the slope
computed at 200 m. Neither the output nor the crop overwrites existing files. The provenance and
verification are in `docs/FUENTES_DE_DATOS.md`.

### Enable MOLA mode in the API

```bash
cd backend
MARS_DATA_SOURCE=mola uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Without further configuration, Valles Marineris is used. To choose an included region by name, use `MARS_MOLA_REGION=gale` (or `ecuatorial` or `valles_marineris`). For another file, add `MARS_MOLA_GRID_FILE=../data/processed/mola_my_region.json`, which takes priority. If the file is missing, the API responds `503 DATASET_UNAVAILABLE`.

The **NASA mission images** section ("Imágenes de misiones NASA") queries the public [NASA Image and Video Library](https://images.nasa.gov/) catalog in real time and lets you explore images by Perseverance, HiRISE, THEMIS, CTX and HRSC. It requires an Internet connection. The images are catalog results and are opened in their preview resource; the specific attribution is kept in NASA's records. This gallery is independent of the MOLA grid and does not modify the data used by A*.

In MOLA mode the frontend shows the colorized global relief generated locally from the MOLA product; it does not need Internet. Use «Marte completo» ("Whole Mars") for the global view and «Ir a zona MOLA» ("Go to MOLA zone") to zoom into the highest-detail crop. You can select points across the whole map and compute approximate global routes; routes inside the crop use its detail resolution. The Viking MDIM 2.1 image from [NASA Mars Trek](https://trek.nasa.gov/mars/) is available as an optional online layer. The mission layers and the gallery are initially collapsed to keep the panel clearer.

Route requests can use local `{row, col}` indices or geographic `{latitude, longitude}` coordinates in MOLA. Distance uses a nominal cell size and is approximate; global routes have 1° cells (about 59 km at the equator). The result **does not** assess safety, geological hazards or mission conditions.

## 🔌 Frontend–backend integration

The frontend sends geographic coordinates to the backend for MOLA and receives the georeferenced route ready to draw. The exact format is in `docs/CONTRATO_DE_DATOS.md`; any change to fields must be reflected there and in the technical documentation.

## 🔀 Git and GitHub workflow

Individual work: `main` is kept stable and progress is made with small, descriptive commits (`type(scope): description`). For large or experimental changes, a short branch and a Pull Request to `main` are recommended. Details in `docs/FLUJO_GIT.md`.

## 📋 Project rules

- Do not upload passwords, tokens, private keys or credentials (`.gitignore` excludes `.env`, `*.pem` and `*.key`).
- Do not upload `.venv/`, `__pycache__/` or large data files.
- Document the sources of the data used.
- Clearly identify synthetic data and simulated results.
- Do not claim that a route is safe for a real mission: this prototype is educational.
- Keep the documentation up to date when the architecture or data format changes.
- Respect the rules of the NASA Space Apps Challenge: list all external resources used and declare the use of AI.
- Data derived from the MOLA+HRSC DEM keep their attribution and license (MOLA: CC0; HRSC: CC BY-SA 3.0 IGO; see `docs/FUENTES_DE_DATOS.md`).

## 📚 Documentation

- **`docs/PLAN_DE_FASES.md`:** stages and status of the work.
- **`docs/ARQUITECTURA.md`:** components and data flow, including MOLA.
- **`docs/FUENTES_DE_DATOS.md`:** provenance and terms of use of the data.
- **`docs/CONTRATO_DE_DATOS.md`:** exchange format of API v1.
- **`docs/FLUJO_GIT.md`:** branches, commits and Pull Requests.

## 🎓 Purpose

Ares Pathfinder is an educational prototype to show how NASA data (topography, orbital imagery and an exposure model) can be combined to plan a surface outing on Mars, always making clear what is measured data, what is derived and what is modeled.

---

**Team:** Jesús (backend, data and algorithms) and Aldo (frontend)  
**Repository:** Ares_Pathfinder  
**Status:** Functional prototype for NASA Space Apps Challenge 2026.


## Rover trajectory layers

In MOLA mode, the **Exploración de rovers** ("Rover exploration") panel lets you turn layers on and off for
Perseverance (Jezero), Curiosity (Gale), Opportunity (Meridiani), Spirit (Gusev) and
Zhurong (Utopia Planitia). Each layer draws a reference polyline, the landing
site and highlighted geographic points. When one of these missions is chosen in the
selector, the map centers on its region and turns on its layer; the NASA image query
remains available as a complementary function.

**Note on rigor:** the polyline coordinates included in this prototype are
approximate reference traces for interaction and cartographic demonstration; they
are not telemetry records or complete official traverses. They are shown over
the global MOLA topographic view, with the local detail grid when it coincides
with the available region. The global view does not turn that local coverage into
detailed topographic coverage for route computation.
