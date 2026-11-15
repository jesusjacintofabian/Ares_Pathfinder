# Brief: exploration mission map at Gale (Mount Sharp)

> Context file for whoever implements (Claude Code in VS Code or another tool).
> It contains the decisions already made, the verified sources and what is **not yet verified**.
> Do not invent data, links or results: if something is not here or you cannot check it, say so.

## 1. Context of the existing project
Mars Explorer Lab: FastAPI API + A* algorithm + Leaflet frontend. Data modes `synthetic` and `mola`
(`MARS_DATA_SOURCE`). Contract in `docs/CONTRATO_DE_DATOS.md` (API v1). Also read `README.md`,
`docs/ARQUITECTURA.md` and `docs/FUENTES_DE_DATOS.md` before starting.

Rules that already govern the project:
- Simulated data are identified as such; no route is presented as "safe".
- Do not upload large files or credentials. `main` requires a Pull Request: work on a branch.
- Pytest before every commit; small commits `type(scope): description`.

## 2. Defined problem
An astronaut on a walk across the Martian surface must reach a valuable scientific target and
return to the habitat without being exposed to slopes the suit does not allow, to soft terrain or to avoidable
radiation, and needs to be able to change plans if space weather worsens during the outing.

Hackathon criteria (NASA Space Apps 2026, "Interplanetary Survival Guide: Martian Map"):
Impact, Creativity, Validity, Relevance, Presentation (1 to 5). At least 3 types of data
combined are requested. Priority: astronaut safety.

## 3. Decisions made
- **Region:** Gale Crater, northwest flank of Mount Sharp (Aeolis Mons). Scientific target: *boxwork*
  formations (1 to 2 m ridges with sandy hollows, in a sulfate-rich layer).
- **Provisional window** (to be confirmed): `--bounds -5.3 -4.5 137.3 138.0` (≈ 47 × 41 km; ≈ 237 × 206 cells of 200 m).
  Curiosity landing: 4.59°S, 137.44°E. Gale: 5.4°S, 137.8°E. The *boxwork* coordinates **are not verified**.
- **Option A** for soft terrain: Mars Trek is used as **visual context**; the A* cost comes from numerical
  data. The soft-terrain indicator enters with weight 0 by default.
- **Challenge resources (initial plan: 3 of 5):** Mars Trek (JPL), USGS geologic map and Curiosity's proposed path.
  **Final status:** only Mars Trek (Viking orbital layer) was integrated. The USGS geologic map and Curiosity's path
  were planned but **not implemented** (see "Phase status").
  Not used: NASA Worldview (it is about Earth) or the Perseverance images as Gale data (Jezero, not Gale).

### Mandatory labels per layer (visible in the interface and in the API)
| Layer | Label | Origin | Enters the cost? |
|---|---|---|---|
| Elevation | MEDIDO (MEASURED) | 200 m MOLA+HRSC DEM (USGS) | Yes |
| Slope | DERIVADO (DERIVED) | Computed from elevation | Yes |
| Soft terrain | INDICADOR (INDICATOR) | THEMIS (qualitative mosaic) / TES | Yes, low and adjustable weight (0 by default) |
| Radiation | MODELADO (MODELED) | RAD-measured anchor (Curiosity) + model | Yes, as a declared model |
| Geologic units | INTERPRETADO (INTERPRETED) | USGS map (Tanaka et al., 2014) | No (context) |
| Curiosity route | REFERENCIA (REFERENCE) | NASA animation | No (comparison) |
| Total cost | ÍNDICE DEL PROYECTO (PROJECT INDEX) | Combination of the above | It is the result |

The total cost is a planning score with adjustable weights: it is not a probability nor a
guarantee of safety.

### Cost formula
```
step_cost = length × (1 + w_slope·slope + w_soft·soft_indicator + w_radiation·modeled_radiation)
```
All weights ≥ 0 (so the A* heuristic remains admissible). Document the default weights.

## 4. Phases
| Phase | Task | Acceptance criterion |
|---|---|---|
| **F1** | `data/process_dem.py`: crops a window of the DEM (GeoTIFF), computes slope and generates a JSON of cells with the format of `mola_valles_marineris.json`. Region integrated into the backend as one more source | Tests with tiny GeoTIFF rasters generated in the tests; existing tests keep passing |
| **F2** | Visual layers from Mars Trek (WMTS) and USGS qualitative THEMIS mosaic (weight 0 in the cost) | Toggleable layers; labeled INDICADOR |
| **F3** | Modeled radiation: rate measured by RAD as an anchor + how much sky each cell sees (computable from the DEM) | Labeled MODELADO; document assumptions |
| **F4** | USGS geologic units layer (FeatureServer) | Labeled INTERPRETADO; warn about the coarse scale |
| **F5** | Curiosity route georeferenced by hand from the GIF | Labeled REFERENCIA and marked as approximate |
| **F6** | A* costs with adjustable weights, "solar alert" mode (route to the nearest shelter) and a per-layer `provenance` field in the API | New fields optional; do not break the v1 contract |
| **F7** | Tests, integration (`tests/integration_check.py`) and update of the technical guide | Everything documented, nothing claimed without running it |

Start only with **F1** and stop for review.

### Phase status (updated at project close)
> This file is the original brief. This note reflects what actually ended up in the repository.

| Phase | Status |
|---|---|
| F1 | Done: Gale MOLA+HRSC DEM at 600 m |
| F2 | **Partial:** Mars Trek Viking layer (optional, requires Internet). The THEMIS mosaic was **not** integrated as a layer |
| F3 | Done: MODELED radiation (`sky_view_factor`) |
| F4 | **Not implemented:** USGS geologic units layer |
| F5 | **Not implemented:** georeferenced Curiosity route |
| F6 | Done: adjustable weights, solar alert (`/routes/shelter`) and `provenance` |
| F7 | Done: tests and integration |

## 5. Verified sources
- **200 m MOLA+HRSC DEM (global, GeoTIFF ≈ 11 GB):**
  https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m
  File: https://planetarymaps.usgs.gov/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif
  Licenses: MOLA CC0 and HRSC CC BY-SA 3.0 IGO. Cite: Fergason, Hare and Laura (2018).
- **Mars Trek, WMTS services:** https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars
  (tiled images; if a tile is missing, there is no coverage).
- **Geologic map of Mars (Tanaka et al., 2014, scale 1:20,000,000, public domain):**
  https://services.arcgis.com/nzS0F0zdNLvs7nc8/ArcGIS/rest/services/Mars_Geology_feature_layer/FeatureServer
  It is very coarse for a ~40 km window.
- **THEMIS thermal inertia mosaic (qualitative, 8-bit, ≈ 100 m, ±60° latitude, public domain):**
  https://astrogeology.usgs.gov/search/map/themis_thermal_inertia_mosaic_qualitative_30n300e_100_mpp
  (this is a sample tile; **the tile covering Gale must be identified**).
- **Numerical TES thermal inertia (20 pixels/degree ≈ 3 km):** https://pds-geosciences.wustl.edu/missions/mgs/tes-timap.html
  Too coarse to decide routes; useful as regional context.
- **Curiosity's proposed path (GIF 1041 × 586, credits NASA/JPL-Caltech/ESA/UArizona/JHUAPL/MSSS/USGS):**
  https://science.nasa.gov/resource/curiositys-proposed-path-up-mount-sharp/
- **Measured radiation (RAD):** Hassler et al. (2014), Science 343 (6169), 1244797. Dose rate measured at
  Gale: 180 to 225 micrograys per day, with a peak near 260 during a solar event.

## 6. What is NOT verified (do not take it for granted)
- The *boxwork* coordinates and the final window.
- Whether a downloadable local geologic map of Gale exists with more detail than the global one.
- Whether the USGS server allows reading the DEM by windows (remote reading) or whether the 11 GB must be downloaded.
- Whether the THEMIS mosaic carries calibrated values: it was verified that it is **qualitative/relative**.
- Which tile of the THEMIS mosaic covers Gale and which THEMIS products Mars Trek offers today.
- How costly it is to adapt `mola_reader.py` (reads PDS4/ENVI) to GeoTIFF, or whether a new library is preferable
  (for example `rasterio`). **Warn before adding dependencies.**

## 7. Rules for whoever implements
1. New branch (`feature/gale-dem`); do not push to `main`.
2. Do not invent data or URLs. Cite each source in `docs/FUENTES_DE_DATOS.md`.
3. The raw DEM goes to `data/raw/` and must stay out of Git (`.gitignore`).
4. Do not change the existing API contract: new fields are optional.
5. Before installing a dependency, say which one and why.
6. Use Manual or Plan mode: ask for permission before large downloads or commands with side effects.
7. Never paste tokens or credentials.

## 8. What to report at the end of each phase
- Which files you changed and why (`git diff main --stat`).
- What you **ran** and what result it gave (copy the actual `pytest` output).
- What you **could not** check.
- Which decisions remain open for the user.
