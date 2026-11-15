# Phase plan

> This plan is an **internal proposal** of the project. It is not a NASA requirement.
> It can be adjusted. The technical content of each phase is kept here; the split by
> team folders is in `docs/FLUJO_GIT.md`.

**Total: 7 phases (0 to 6).** Each phase ends with a verifiable deliverable.

| Phase | Name | Status | Verifiable deliverable |
|------|--------|--------|------------------------|
| 0 | Preparation | ✅ Done | Repository cloned, environment working, first Pull Request merged |
| 1 | GIS data | ✅ Done | Reproducible synthetic data and MOLA topography documented in `docs/FUENTES_DE_DATOS.md` |
| 2 | Base backend | ✅ Done | API with `/health`, `/map` and `/routes`; synthetic or MOLA source |
| 3 | Base frontend | ✅ Done | Leaflet map with colorized global MOLA relief, region detail for routes and optional layers |
| 4 | Route and risk | ✅ Done | A* with slope cost and simulated risk or MOLA topographic proxy; route drawn on the map |
| 5 | Testing and documentation | 🔄 In progress | Pytest, jsdom interface tests and synthetic/MOLA/Gale integration done; the technical guide (.docx) still needs updating |
| 6 | Wrap-up and lessons learned | ⏳ Pending | Document `docs/LECCIONES_APRENDIDAS.md` to arrive prepared for the real challenge |

## Detail by phase

### Phase 0: Preparation
- Repository on GitHub, virtual environment and base project working.
- Practice the workflow: commit, push and, for large changes, branch and Pull Request.

### Phase 1: GIS data
- Small study area. Two sources are used: a **synthetic** grid (learning) and a crop
  of the real **MOLA** topography (product `megt90n000eb`).
- Sources, official links, format and terms of use in `docs/FUENTES_DE_DATOS.md`.

### Phase 2: Base backend
- FastAPI structure, Pydantic models, errors with a single format and data source selection.
- Slope from elevation (in MOLA it is computed with finite differences).

### Phase 3: Base frontend
- Leaflet map, layer selector, origin and destination markers, consumption of the real endpoints.

### Phase 4: Route and risk
- A* on a grid with slope and risk cost; admissible heuristic verified against Dijkstra.
- Synthetic risk is simulated; MOLA offers an educational topographic proxy based only on slope, not a real hazard model.

### Phase 5: Testing and documentation
- Tests of the backend, the algorithm and MOLA with small temporary rasters.
- `tests/integration_check.py` against real servers (`--mola` for MOLA, `--gale` for Gale).
- Interface tests with jsdom (`frontend/tests/`) and a manual checklist in the README.
- Pending: extended technical guide (how it was built, F6 and the Gale interface). The previous
  version of the guide was withdrawn for being out of date.
- That any new person can bring the project up using only the README.

### Phase 6: Wrap-up
- Retrospective: what worked, what took longer, what would be done differently.
- List of skills and patterns learned for the real challenge.
