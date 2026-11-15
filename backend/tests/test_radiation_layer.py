"""Capa de radiación MODELADA (F3): costo de A*, carga de la región y campos opcionales de la API."""

import json
import math
import random

import numpy as np
import pytest
from fastapi.testclient import TestClient

from algorithms.astar import CostModel, Grid, GridCell, NoRouteError, find_path
from app.main import app
from app.services.map_service import (
    DatasetConfigurationError,
    _load_active_dataset,
    _load_mola_dataset,
)
from data.geotiff_reader import write_geotiff_int16
from data.mola_reader import GeographicBounds
from data.process_dem import process_dem
from tests.test_astar import dijkstra_cost

RADIATION_FIELDS = {"sky_view_factor", "radiation_modeled"}


# ------------------------------------------------------------------- A*
@pytest.mark.parametrize("weight", [-0.1, math.nan, math.inf])
def test_radiation_weight_must_be_finite_and_non_negative(weight):
    with pytest.raises(ValueError, match=">= 0"):
        CostModel(radiation_weight=weight)


def test_default_radiation_weight_leaves_cost_unchanged():
    cell = GridCell(0.0, 10.0, 0.5, False, radiation=1.0)
    assert CostModel().radiation_weight == 0.0
    assert CostModel().cell_multiplier(cell) == pytest.approx(1 + 0.05 * 10 + 2.0 * 0.5)
    assert CostModel(radiation_weight=3.0).cell_multiplier(cell) == pytest.approx(
        1 + 0.05 * 10 + 2.0 * 0.5 + 3.0
    )


@pytest.mark.parametrize("seed", range(15))
@pytest.mark.parametrize("allow_diagonal", [True, False])
def test_astar_with_radiation_weight_stays_optimal(seed, allow_diagonal):
    """Con peso de radiación > 0, A* sigue dando el costo de Dijkstra (heurística admisible)."""
    rng = random.Random(1000 + seed)
    rows, cols = 8, 9
    cells = [[GridCell(0.0, rng.uniform(0, 20), rng.random(), rng.random() < 0.2,
                       radiation=rng.random()) for _ in range(cols)] for _ in range(rows)]
    cells[0][0] = GridCell(0.0, 3.0, 0.1, False, radiation=0.5)
    cells[rows - 1][cols - 1] = GridCell(0.0, 3.0, 0.1, False, radiation=0.5)
    grid = Grid(cells, 100.0)
    model = CostModel(0.05, 2.0, radiation_weight=4.0)
    expected = dijkstra_cost(grid, (0, 0), (rows - 1, cols - 1), model, allow_diagonal)
    if expected is None:
        with pytest.raises(NoRouteError):
            find_path(grid, (0, 0), (rows - 1, cols - 1), model, allow_diagonal)
    else:
        result = find_path(grid, (0, 0), (rows - 1, cols - 1), model, allow_diagonal)
        assert result.total_cost == pytest.approx(expected)


def test_radiation_weight_steers_route_away_from_exposed_cells():
    # Fila central muy expuesta: con peso > 0 la ruta la rodea; con peso 0, no.
    def cell(r, c):
        return GridCell(0.0, 0.0, 0.0, False, radiation=1.0 if r == 1 and 1 <= c <= 3 else 0.0)
    grid = Grid([[cell(r, c) for c in range(5)] for r in range(3)], 100.0)
    straight = find_path(grid, (1, 0), (1, 4), CostModel(0.0, 0.0), allow_diagonal=False)
    avoiding = find_path(grid, (1, 0), (1, 4), CostModel(0.0, 0.0, radiation_weight=5.0),
                         allow_diagonal=False)
    assert straight.path == [(1, c) for c in range(5)]
    assert all(grid.cell(*p).radiation == 0.0 for p in avoiding.path)


# --------------------------------------------------- región con la capa
@pytest.fixture(scope="module")
def radiation_grid(tmp_path_factory):
    """Región procesada desde un raster diminuto con un pozo en el centro."""
    tmp = tmp_path_factory.mktemp("rad")
    scale, radius = 0.002, 3_396_190.0
    values = np.full((40, 40), -4500, dtype=np.int16)
    values[12:15, 12:15] = -5500  # pozo en el bloque (1, 1) de una ventana de 6 × 6 celdas
    dem = write_geotiff_int16(tmp / "dem.tif", values, origin_lon=137.0, origin_lat=-4.0,
                              pixel_scale_deg=scale, radius_m=radius)
    bounds = GeographicBounds(-4.0 - 27 * scale + 1e-7, -4.0 - 9 * scale - 1e-7,
                              137.0 + 9 * scale + 1e-7, 137.0 + 27 * scale - 1e-7)
    output = tmp / "grid.json"
    process_dem(dem, bounds, output, aggregate=3, horizon_radius_m=1_000.0)
    return output


@pytest.fixture()
def radiation_client(radiation_grid, monkeypatch):
    monkeypatch.setenv("MARS_DATA_SOURCE", "mola")
    monkeypatch.setenv("MARS_MOLA_GRID_FILE", str(radiation_grid))
    monkeypatch.delenv("MARS_MOLA_REGION", raising=False)
    _load_active_dataset.cache_clear()
    yield TestClient(app)
    _load_active_dataset.cache_clear()


def test_map_serves_modelled_radiation_as_optional_fields(radiation_client):
    body = radiation_client.get("/api/v1/map").json()
    assert body["radiation_available"] is True
    model = body["radiation_model"]
    assert model["label"] == "MODELADO"
    assert model["anchor"]["unverified_values"]["verification_status"] == (
        "no cotejado con el artículo publicado"
    )
    assert body["cost_model"]["radiation_weight"] == 0.0
    cells = {(c["row"], c["col"]): c for c in body["cells"]}
    assert all(RADIATION_FIELDS <= set(c) for c in cells.values())
    assert len(cells) == 36
    assert cells[(1, 1)]["radiation_modeled"] < 0.5
    assert cells[(5, 5)]["radiation_modeled"] == 1.0


def test_route_cost_is_unchanged_while_radiation_weight_is_zero(radiation_client):
    body = radiation_client.post("/api/v1/routes", json={
        "origin": {"row": 5, "col": 0}, "destination": {"row": 3, "col": 5},
    }).json()
    assert body["status"] == "ok"
    cells = {(c["row"], c["col"]): c
             for c in radiation_client.get("/api/v1/map").json()["cells"]}
    expected = 0.0
    for prev, step in zip(body["path"], body["path"][1:]):
        factor = math.sqrt(2) if prev["row"] != step["row"] and prev["col"] != step["col"] else 1
        cell = cells[(step["row"], step["col"])]
        expected += factor * (1 + 0.05 * cell["slope_deg"] + 2.0 * cell["risk"])
    assert body["summary"]["total_cost"] == pytest.approx(expected, abs=1e-3)


def test_regions_without_the_layer_do_not_expose_it(client, monkeypatch):
    synthetic = client.get("/api/v1/map").json()
    assert "radiation_model" not in synthetic and "radiation_available" not in synthetic
    assert all(not RADIATION_FIELDS & set(c) for c in synthetic["cells"])
    assert synthetic["cost_model"]["radiation_weight"] == 0.0

    monkeypatch.setenv("MARS_DATA_SOURCE", "mola")
    monkeypatch.delenv("MARS_MOLA_GRID_FILE", raising=False)
    monkeypatch.delenv("MARS_MOLA_REGION", raising=False)
    _load_active_dataset.cache_clear()
    try:
        valles = TestClient(app).get("/api/v1/map").json()
    finally:
        _load_active_dataset.cache_clear()
    assert "radiation_model" not in valles
    assert all(not RADIATION_FIELDS & set(c) for c in valles["cells"])


# --------------------------------------------------- validación al cargar
def corrupt(source, tmp_path, change):
    data = json.loads(source.read_text(encoding="utf-8"))
    change(data)
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.mark.parametrize("change", [
    lambda d: d["cells"][0].update(radiation_modeled=1.5),
    lambda d: d["cells"][0].update(sky_view_factor=-0.1),
    lambda d: d["cells"][0].update(radiation_modeled="0.5"),
    lambda d: d["cells"][0].pop("sky_view_factor"),
    lambda d: d["cells"][0].pop("radiation_modeled"),
    lambda d: d.pop("radiation_model"),
    lambda d: d["radiation_model"].update(label="MEDIDO"),
], ids=["above-1", "negative", "text", "partial-svf", "partial-rad", "no-model", "bad-label"])
def test_loader_rejects_inconsistent_radiation_layers(radiation_grid, tmp_path, change):
    with pytest.raises(DatasetConfigurationError, match="radiación|radiation_model"):
        _load_mola_dataset(corrupt(radiation_grid, tmp_path, change))


def test_loader_passes_radiation_to_astar_cells(radiation_grid):
    dataset = _load_mola_dataset(radiation_grid)
    stored = json.loads(radiation_grid.read_text(encoding="utf-8"))
    for cell in stored["cells"]:
        assert dataset.grid.cell(cell["row"], cell["col"]).radiation == cell["radiation_modeled"]
