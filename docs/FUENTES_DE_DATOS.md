# Data sources

> Document here the provenance, format, terms of use and attribution of each
> scientific dataset. Do not confuse the MOLA DEM with hazard layers.

## Integrated dataset: MOLA MEGDR topography (`megt90n000eb`)

| Layer | Mission / instrument | Official source | Format and resolution | Units / reference | Attribution |
|---|---|---|---|---|---|
| Global topographic elevation | Mars Global Surveyor / MOLA | [PDS Geosciences Node, collection meg016](https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg016/) · [PDS4 label of the product](https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg016/megt90n000eb.xml) | `Array_2D_Image`, 2880 lines × 5760 samples, `SignedMSB2`; 1/16° × 1/16°. Nominal linear scale at the equator: 3.7044613374 km/pixel | Elevation in meters relative to the areoid; planetocentric latitude; east-positive longitude; equirectangular projection (spherical radius 3396 km, central meridian 180°) | Smith et al., *Mars Global Surveyor Laser Altimeter Mission Experiment Gridded Data Record*, PDS, 2003, DOI [10.17189/1519460](https://doi.org/10.17189/1519460). |

The MGS MOLA Topography Derived bundle is archived by the Geosciences Node of the
NASA Planetary Data System (PDS). The local `megt90n000eb.img` measures 33,177,600
bytes; its MD5 is `357c759ab342140d2d008443e0a68015`, equal to the one listed
in the bundle's official MD5 manifest. The PDS4 product has logical
identifier `urn:nasa:pds:mgs_mola_topography_derived:data_meg016:megt90n000eb`.

### Files and reading

For this product, the `.img` raster and its `.xml` label are required. The complementary
ENVI `.hdr` declares `data ignore value = 0`; the reader applies that value
as invalid when the header is available. The PDS4 label does not declare its own
null value. The remaining values are interpreted as signed 16-bit integers
in big-endian order, converted to meters. The label declares the
shape and type of the array; the reader rejects dimensions, types, units or
binary sizes that do not match, and does not assume that every MOLA product uses the
same format.

The PDS describes the pixel as the median of the topography observed in its cell;
when there are no observations, an interpolated value is provided. The dataset also
warns of a lower density of observations near the equator and gaps between
profiles. Do not treat interpolated elevation as a direct measurement.

The current source does not provide a validated layer of hazard, traversability
or safety. So that routes and the map can take relief into account, the
laboratory computes an **educational topographic proxy** per valid cell:
`risk = min(slope_deg / 20, 1)`. The value 0 corresponds to flat slope and 1 to a
slope of 20° or more; intermediate values are a normalized scale, not
probabilities nor calibrated levels of hazard. A* applies a weight
of 2.0 to this proxy. The method is the same for detailed and global MOLA, although the latter
uses as slope the maximum observed among the native pixels of each 1°
cell. Cells without valid data are blocked; their compatibility zero is not
a valid proxy. None of these values models geology, rocks, dust,
lighting, power, communications or mission conditions.

The map explicitly identifies the indicator as "proxy de riesgo
topográfico" ("topographic risk proxy"). **It is not a real hazard model nor a safety
or traversability assessment.** The slope threshold additionally used to block
cells is a configurable and demonstrative rule.

### Download and attribution

Use the [official directory of collection meg016](https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg016/)
and download `megt90n000eb.img`, `megt90n000eb.xml` and
`megt90n000eb.hdr` together into `data/raw/mola/`. The [PDS bundle README](https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/readme.txt)
identifies the source as MOLA-derived data archived by the PDS
Geosciences Node. The [PDS ENVI documentation](https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/document/mola_envi.htm)
describes the map's precise resolution.

No separate license was found in the product label or in the bundle README
consulted. Therefore, keep the PDS metadata, cite the product
and follow the conditions indicated by the PDS/NASA; no additional
license is attributed here. The local file does not record a verifiable download
date. The file date on the local system is not considered the acquisition date.

## Processed regions (derived from `megt90n000eb`)

Each region is a crop of the same source, processed with `data/process_mola.py`. The crop keeps the
original elevation (rounded) and adds a **derived** slope and a **demonstrative** blocking by threshold.
The statistics were computed directly from the versioned JSONs.

| File | Bounds (planetocentric lat. / east lon.) | Cells | Elevation (m) | Max. slope | Threshold | Blocked | Invalid |
|---|---|---|---|---|---|---|---|
| `mola_valles_marineris.json` | −14° to −12° / 291° to 293° | 32 × 32 | −4887 to 4441 | 32.16° | 20° | 96 | 1 |
| `mola_region.json` | −1° to 1° / 179° to 181° | 32 × 32 | −2839 to −2273 | 2.53° | 30° | 0 | 0 |

Command used for the default region:

```bash
python data/process_mola.py --bounds -14 -12 291 293 --max-slope-deg 20 \
  --output data/processed/mola_valles_marineris.json
```

The scarps of Valles Marineris split the region into **four disconnected free zones** (698, 228, 1 and 1 cells,
verified with an independent A* traversal). Choosing origin and destination in different zones produces `404 NO_ROUTE`,
which is a correct result of the model and not an error.

Valles Marineris was chosen for its strong relief (canyons and scarps) so that A* has real obstacles. The
blocking thresholds are not validated traversal limits. Each cell carries `latitude` and `longitude` of its center.

## 200 m MOLA+HRSC DEM (Gale region)

| Field | Value |
|---|---|
| Product | Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2 (USGS Astrogeology) |
| Page | https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m |
| File | https://planetarymaps.usgs.gov/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif (redirects to `asc-pds-services.s3.us-west-2.amazonaws.com`) |
| Citation | Fergason, Hare and Laura (2018) |
| Licenses | MOLA: CC0; HRSC: CC BY-SA 3.0 IGO |
| Accessed | 2026-11-14 |

**Verified metadata** (HTTP headers and TIFF tags read by ranges, without downloading the file):
11,384,463,908 bytes, `Last-Modified: Wed, 09 Nov 2022 14:59:19 GMT`, `Accept-Ranges: bytes`;
little-endian BigTIFF of 106,694 × 53,347 pixels, signed int16, uncompressed, one row per strip,
no overviews, `GDAL_NODATA = -32768`. Geographic georeference in degrees: tie point (−180°, 90°),
pixel of 0.003374120830641° on the `GCS_Mars_2000_Sphere` sphere of radius 3,396,190 m (≈ 200 m).
The total width covers 359.998°, so the mesh is not aligned with 0°E. The radius differs from that of MOLA
MEGDR (3,396,000 m); each reader uses the one its file declares.

**Not verified:** the file carries no GDAL_METADATA tag. The vertical reference of the elevation
has not been confirmed in the metadata read; the comparison with MOLA (below) indicates they are consistent.

### Processing (`data/process_dem.py`)

The global DEM is not downloaded. `data/geotiff_reader.py` reads by HTTP ranges only the span of columns of
each row of the window and saves a 200 m raw crop in `data/raw/gale/`, ignored by Git, to
reprocess without network. Since F3, a 10 km margin around the window is also read to search for the
horizon (340 × 310 pixels, ~217 KB in `gale_clip_200m_margen10km.tif`; the previous crop with 1 pixel
of margin, `gale_clip_200m.tif`, is no longer enough for the radiation layer). The slope is computed
at 200 m with 1 pixel of margin and then blocks of 3 × 3 pixels are grouped: mean elevation, **maximum**
slope of the block, and a cell valid only if its 9 pixels are.

```bash
python data/process_dem.py \
  --dem https://planetarymaps.usgs.gov/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif \
  --bounds -5.3 -4.5 137.3 138.0 --aggregate 3 \
  --name "Gale — flanco noroeste del Monte Sharp (DEM MOLA+HRSC)" \
  --save-raw data/raw/gale/gale_clip_200m_margen10km.tif \
  --output data/processed/gale_monte_sharp_600m.json
```

`--horizon-radius-km` (10 by default; 0 disables the layer) and `--azimuths` (32) control the
MODELED radiation layer described below. The versioned version was regenerated on 2026-11-14 with that command; the
reprocessing without network from the raw crop gives identical cells.

| File | Actual bounds (lat. / east lon.) | Cells | Elevation (m) | Max. slope | Threshold | Blocked | Invalid |
|---|---|---|---|---|---|---|---|
| `gale_monte_sharp_600m.json` | −5.3088° to −4.4990° / 137.2989° to 138.0075° | 80 × 70 (600 m) | −4545 to 485 | 34.93° | 30° | 15 | 0 |

The requested window (−5.3 to −4.5 / 137.3 to 138.0) is **provisional**: the *boxwork* coordinates are not
verified. The actual window is extended to the pixel edge and to a multiple of the
aggregation factor. All free cells form a single connected zone (5585 cells). The 30° threshold is
demonstrative, not a suit limit; moreover, at 200 m larger slopes appear than at the MOLA scale.

6.59 % of the cells (369 of 5600) have `risk = 1` (slope of 20° or more). Sensitivity to the blocking
threshold, informative only (the default value remains 30°). Connectivity uses A*'s rule:
diagonals do not cut corners.

| Threshold | Blocked | Free zones | Largest zone (% of free) |
|---|---|---|---|
| 15° | 1330 (23.75 %) | 26 | 4213 (98.67 %) |
| 20° | 369 (6.59 %) | 7 | 5221 (99.81 %) |
| 25° | 92 (1.64 %) | 1 | 5508 (100 %) |
| 30° | 15 (0.27 %) | 1 | 5585 (100 %) |

**Independent comparison with MOLA MEGDR** (`megt90n000eb`): in 132 MOLA pixels of 1/16° inside the
window, the mean of the Gale cells differs by +7 m (standard deviation of 122 m), with a correlation
of 0.9967. At the Curiosity landing point (4.59°S, 137.44°E), the DEM gives −4510 m and MOLA −4509 m.

## MODELED radiation (Gale region)

| Field | Value |
|---|---|
| Label | **MODELADO** (MODELED): it is not a cell-by-cell measurement nor a dose |
| Fields per cell | `sky_view_factor` and `radiation_modeled` (0–1, dimensionless; in this version they are equal) |
| Metadata | `radiation_model` and `radiation_available` in the JSON and in `GET /api/v1/map` |
| Code | `data/sky_view.py` (horizon and visible sky), `data/radiation_model.py` (assumptions, limits and anchor) |
| Weight in A* | `radiation_weight = 0.0` by default; since F6 it can be adjusted per request (0–100) in `POST /routes` and `POST /routes/shelter` |

**Measured anchor.** Hassler et al. (2014), *Mars' Surface Radiation Environment Measured with the Mars
Science Laboratory's Curiosity Rover*, Science 343 (6169), 1244797, DOI
[10.1126/science.1244797](https://doi.org/10.1126/science.1244797). According to the published abstract, the
RAD instrument of the Curiosity rover measured at the surface of Gale the absorbed dose and the equivalent
dose due to galactic cosmic rays (GCR) and solar energetic particles (SEP) for
about 300 days. That measurement is the anchor point: it corresponds to the rover's location, and the index only describes
how the exposure to the sky varies, in a relative way, between cells.

**Unchecked figures.** The brief cites 180 to 225 µGy/day, a mean of 0.21 mGy/day and a peak near
260 µGy/day during a solar event. The published abstract does not contain those figures and the full
paper could not be read (the core.ac.uk copy responded 403). They are kept as metadata with
`verification_status: "no cotejado con el artículo publicado"` ("not checked against the published paper") and `used_in_calculation: false`; they are not
used in any calculation nor published as a per-cell dose.

**Method (author's hypothesis).** For each 200 m pixel, the horizon angle H is searched in 32
azimuths up to 10 km, with nearest-pixel sampling, metric distances (the east-west pixel is
reduced by cos(latitude)) and curvature correction d²/2R with the radius declared by the GeoTIFF. Pixels
without data do not block the sky. The visible sky factor is the fraction of solid angle not blocked with an
isotropic sky: `azimuth_mean(1 − sin(max(H, 0)))`. An open plane gives 1; a pit gives less. The 600 m cell
takes the mean of its 3 × 3 pixels. Index: `radiation_modeled = sky_view_factor`.

**Assumptions.** Isotropic radiation in the visible sky; the terrain completely blocks the directions it
covers; more visible sky implies more relative exposure.

**Limits.**
- It does not model atmospheric attenuation with the zenith angle. Radiation arriving at a low angle is already
  heavily attenuated, so the index **exaggerates** the shielding by the terrain.
- It does not model secondary radiation from the ground (albedo neutrons) nor temporal variation (diurnal
  pressure cycle, solar cycle, SEP events).
- It does not model the atmospheric column according to elevation. In the window there are about 5 km of relief and it is
  probably the dominant spatial factor; it was not added because there is no verified coefficient.
- The resolution (200 m, 600 m cells) does not capture the *boxwork* relief (1 to 2 m ridges).
- Beyond 10 km no horizon is searched: the far edge of the crater may block somewhat more sky.

**Result in `gale_monte_sharp_600m.json`** (computed on the versioned JSON): 5600 cells, 0 with a
truncated horizon. `sky_view_factor` ranges from 0.7404 to 0.9957 (median 0.9227, mean 0.9209, p5 0.8540,
p95 0.9794); 1638 cells (29.25 %) are below 0.9 and 14 (0.25 %) below 0.8. The cell
of the Curiosity landing point (4.59°S, 137.44°E) gives 0.9556. No cell reaches 1, because from
every one some relief above the horizontal is seen (Mount Sharp dominates the window).

**Observation.** The Pearson correlation between `sky_view_factor` and the cell's slope is −0.90; with
elevation, −0.10. On a hillside, the slope itself blocks the sky upward, so the index largely repeats
the information of the slope, which already enters the cost. This should be kept in mind when
choosing `radiation_weight` in F6.

### Provenance: `sky_view_factor` DERIVADO, radiation layer MODELADO

In the `provenance` field of `GET /api/v1/map`, `sky_view_factor` is labeled **DERIVADO** and
`radiation_modeled` **MODELADO**, although in this version the two values are equal:

- `sky_view_factor` is **geometry** computed only from the DEM (horizon angle in 32 azimuths,
  curvature correction). All it states is what fraction of the sky the relief blocks. It makes
  no assumption about radiation, just like the slope.
- `radiation_modeled` (the F3 layer) takes that number and adds **physical hypotheses** to read it as
  exposure: isotropic sky, total blocking by the relief and the idea that more sky implies more
  exposure. Those hypotheses are what turn it into a model, with the limits listed above.

That is why the same figure carries different labels depending on what it is used for: `sky_view_factor` as terrain data
(to choose candidate waiting zones) and `radiation_modeled` as an exposure index
(in the cost, with weight 0 by default).

## Candidate waiting zone ("solar alert" mode, Gale region)

| Field | Value |
|---|---|
| Label | **ÍNDICE DEL PROYECTO** (PROJECT INDEX): laboratory criterion, not a NASA product nor a verified protection |
| Endpoint | `POST /api/v1/routes/shelter` (see `docs/CONTRATO_DE_DATOS.md`) |
| Code | `backend/app/services/shelter_service.py`, `algorithms/astar.py` (`find_nearest_target`) |
| Default criterion | valid and free cell with `slope_deg ≤ 10` and `sky_view_factor ≤ 0.90`; both thresholds can be changed per request |
| Distance limit | optional `max_distance_km`, no default value: the zone is accepted if its lowest-cost route measures at most that value; if none falls within it, `404 NO_SHELTER`. The response always carries `distance_km` |

**Method.** Dijkstra from the origin; it stops at the first cell that meets the criterion. This way the
nearest zone **by cost** is chosen (with the same formula and the same weights as `/routes`), not by
distance. `sky_view_factor` only decides which cells are candidates; **it does not penalize the cost**, because its
correlation with the slope is −0.90 and the slope already enters the cost (it would be a double punishment).

**Justification of the thresholds** (computed on the 5585 free cells of `gale_monte_sharp_600m.json`):

- **10°** is the median slope of the free cells (10.05°): the candidate zone falls in the flatter
  half and its topographic risk proxy is ≤ 0.5. The slope is the maximum of the block of 3 × 3
  pixels of 200 m.
- **0.90** is approximately the 25th percentile of `sky_view_factor` in the free cells (0.895).

| Criterion | Candidates | Separate groups (8 neighbors) | Mean `sky_view_factor` |
|---|---|---|---|
| slope ≤ 10° and SVF ≤ 0.85 | 0 | – | – |
| slope ≤ 10° and SVF ≤ 0.88 | 6 | – | – |
| **slope ≤ 10° and SVF ≤ 0.90** (default) | **64** | 20 | 0.890 |
| slope ≤ 12° and SVF ≤ 0.90 | 131 | 40 | 0.890 |

Because of the −0.90 correlation, cells with little visible sky are almost always on a hillside: stricter
thresholds leave the region without candidates.

**Executed example** (default weights): from the Curiosity landing point (4.59°S, 137.44°E;
cell 8, 13) the nearest candidate zone by cost is cell (11, 42), 29 steps
and ~18.1 km away (`total_cost` 53.69), with slope 9.84° and `sky_view_factor` 0.893.

**Limits (always state them).**
- The modeled reduction of visible sky is small: an average candidate zone sees 0.89 versus the
  median of 0.92 (≈ 3 % less). Moreover, the index does not include atmospheric attenuation and **exaggerates** the
  terrain shielding, so the real benefit may be smaller.
- At 600 m per cell, ledges, overhangs and the *boxwork* relief are not represented, which at the scale of
  a person could give more shade than what is seen here.
- The distance to the candidate zone (18 km in the example) may be greater than what a
  walk allows; `max_distance_km` allows bounding it, but the mode does not consider time, consumables or
  the duration of a solar event.
- It is an educational planning aid: it is not a verified shelter nor an operational recommendation.

## Global visual mosaic: Viking MDIM 2.1

The interface can optionally show as a base map the **Mars Viking MDIM 2.1
Color Mosaic** product, published by NASA/JPL Mars Trek as the ArcGIS ImageServer service
`Mars_Viking_MDIM21_ClrMosaic_global_232m`. The Mars Trek base-map catalog
identifies it as its global equirectangular mosaic; the service reports
a global extent of `0..360°` of longitude, `-90..90°` of latitude, three RGB bands and
sampling of `0.00390625°` per pixel (232 m nominal at the equator).

- [NASA Mars Trek](https://trek.nasa.gov/mars/)
- [Base map catalog](https://trek.nasa.gov/mars/jpl/config/basemapList.json)
- [Metadata and image service](https://trek.nasa.gov/mars/trekarcgis/rest/services/Mars_Viking_MDIM21_ClrMosaic_global_232m/ImageServer?f=pjson)

The frontend requests tiles from the image service only when the user
activates this layer; it requires an Internet connection. It is a global orbital mosaic of
Viking images, not current high-resolution images. It only works as a
visual layer and does not alter the route data. Keep the NASA/JPL Mars Trek attribution
shown in the interface; no additional unverified license is documented here.

## Global MOLA topographic view of the frontend

To give context of the whole planet without returning the 16,588,800 native pixels
through the API, `data/render_mola_preview.py` generates
`frontend/assets/mola-global.png` directly from the MEGDR raster. Each
pixel of the image represents the average of the valid data inside a
block of 8 × 8 native pixels (0.5° per pixel); the values declared as
invalid by the ENVI header are excluded from the average and left transparent.
The hypsometric palette is a visual decision of the laboratory, not a
hazard classification.

The image covers 0–360° of east longitude and −90° to 90° of latitude, and is served
locally from the frontend: it requires no tile query nor external
connection. To regenerate it (requires the local `.img` raster and NumPy):

```bash
python3 data/render_mola_preview.py
```

The global view is a lower-resolution context representation; it is not
used to select cells, compute slopes or plan routes. The
provenance of the relief remains the `megt90n000eb` product archived by
NASA PDS; the image is not an official NASA product.

## Global MOLA mesh for routes (1°)

`data/process_mola_global.py` generates `data/processed/mola_global_1deg.json.gz`
(180 × 360 cells), `frontend/assets/mola-global-blocked.png` and
`frontend/assets/mola-global-risk.png`. The elevation of
each cell is the average of the valid MOLA pixels of that 1° block.
So as not to hide scarps through averaging, the slope assigned to the cell
is the maximum slope computed over the native pixels of the block. The
processor computes the normalized proxy `min(slope_deg / 20, 1)`, marks as
invalid/blocked the cells without a computable slope and blocks those that
reach the demonstrative threshold of 20°.

The angular resolution corresponds approximately to 59 km north-south and, at the
equator, 59 km east-west; the east-west dimension shrinks with latitude.
This grid allows exploring and computing approximate routes outside the
MOLA detail region. If one or both points fall outside the local crop,
the backend plans on this mesh; if both are inside, it uses the detailed
crop. The PNG mask represents the blocked cells; `mola-global-risk.png`
represents the slope proxy with a green-yellow-red ramp. Those
images are not scientific layers of hazard or safety.

The compressed `.json.gz` and the mask are versioned so that the API can operate
without having the 33 MB raster. To regenerate them the original raster
in `data/raw/mola/` and NumPy are required:

```bash
python3 -m data.process_mola_global
```

The generator does not replace existing files. The source remains MOLA
MEGDR and the aggregation, the slope threshold and the routing are demonstrative
decisions of the laboratory, not official NASA products nor traversal
validations.

## Nomenclature of Martian geographic features

The names and types of volcanoes, craters and other features are queried from
the official `combinedNom/MapServer/0` layer of NASA/JPL Mars Trek. The response
includes the type of the feature and, when it exists, its published diameter. The
interface queries by the visible area. To reduce crowding, the diameter threshold
decreases as the map is zoomed in (≥1,000, 500, 200 and 50 km; at detail zoom
all are queried), and the permanent labels avoid overlapping by
prioritizing large features. The labels can be consulted by hovering the
cursor over the remaining markers. This layer is nomenclature, not an
assessment of hazards or traversability.

- [Layer metadata](https://trek.nasa.gov/mars/trekarcgis/rest/services/combinedNom/MapServer/0?f=pjson)
- [Feature query service](https://trek.nasa.gov/mars/trekarcgis/rest/services/combinedNom/MapServer/0/query)

## Other products to investigate

HiRISE, CTX, THEMIS and CRISM are candidates for additional layers. Their
availability for a region, formats and terms of use must be verified
in official sources before incorporating them.


## Gallery of Martian mission images

The frontend incorporates a gallery that queries the public search endpoint of the NASA Image and Video Library:

- Endpoint: `https://images-api.nasa.gov/search`
- Parameters: `q`, `media_type=image` and `page_size=12`.
- Available searches: Perseverance, HiRISE (Mars Reconnaissance Orbiter), THEMIS (Mars Odyssey), CTX (Mars Reconnaissance Orbiter) and HRSC (Mars Express).
- The user can open each preview in a new tab. The catalog provides title, date and image resource; the gallery does not download or store the originals.

This integration provides photographs from real missions for visual exploration. It must not be confused with a georeferenced cartographic layer nor with a DEM: the photographs are not automatically overlaid on the Leaflet map and do not take part in A*. The exact relevance of each result depends on the catalog search; check the title and metadata before using an image as evidence of a specific location.

Official sources:

- [NASA Image and Video Library](https://images.nasa.gov/)
- [NASA Open APIs](https://api.nasa.gov/)
- [THEMIS / ASU: Mars image maps](https://themis.mars.asu.edu/maps)
- [NASA Mars Trek](https://trek.nasa.gov/mars/)
