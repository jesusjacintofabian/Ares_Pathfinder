"""Modo «alerta solar»: POST /api/v1/routes/shelter (F6a).

Regiones diminutas generadas aquí; la ruta devuelta se contrasta con un Dijkstra
multi-destino de referencia escrito en las pruebas.
"""

import json
import math
import random
import re

import pytest
from fastapi.testclient import TestClient

from algorithms.astar import SQRT2, CostModel
from app.main import app
from app.services.map_service import _load_active_dataset
from app.services.shelter_service import (
    DEFAULT_SHELTER_MAX_SKY_VIEW_FACTOR,
    DEFAULT_SHELTER_MAX_SLOPE_DEG,
)
from tests.test_nearest_target import reference_nearest_cost
from tests.tiny_mola import grid_from_spec, mola_client, write_tiny_region

URL = "/api/v1/routes/shelter"
OPEN = (2.0, 0.97, False)      # llano y expuesto
STEEP = (18.0, 0.80, False)    # poco cielo pero pendiente: NO es candidata
SPOT = (4.0, 0.86, False)      # llano y con poco cielo: candidata con el criterio por defecto
WALL = (40.0, 0.70, True)

# 5 × 7. Candidatas en (0, 6) y (4, 0); el muro obliga a rodear.
SPEC = [
    [OPEN, OPEN, OPEN, OPEN, OPEN, OPEN, SPOT],
    [OPEN, STEEP, STEEP, WALL, OPEN, OPEN, OPEN],
    [OPEN, OPEN, OPEN, WALL, OPEN, OPEN, OPEN],
    [OPEN, OPEN, OPEN, WALL, OPEN, OPEN, OPEN],
    [SPOT, OPEN, OPEN, OPEN, OPEN, OPEN, OPEN],
]


def candidates(spec, max_slope=DEFAULT_SHELTER_MAX_SLOPE_DEG,
               max_svf=DEFAULT_SHELTER_MAX_SKY_VIEW_FACTOR):
    return [(r, c) for r, row in enumerate(spec) for c, (s, v, b) in enumerate(row)
            if not b and s <= max_slope and v <= max_svf]


def path_cost(spec, path, model):
    grid = grid_from_spec(spec)
    total = 0.0
    for a, b in zip(path, path[1:]):
        factor = SQRT2 if a[0] != b[0] and a[1] != b[1] else 1.0
        total += factor * model.cell_multiplier(grid.cell(*b))
    return total


@pytest.fixture()
def tiny(tmp_path, monkeypatch):
    with mola_client(monkeypatch, write_tiny_region(tmp_path / "tiny.json", SPEC)) as api:
        yield api


def as_cells(body):
    return [(p["row"], p["col"]) for p in body["path"]]


@pytest.mark.parametrize("origin", [(2, 2), (2, 4), (0, 0), (4, 6), (3, 1)])
@pytest.mark.parametrize("allow_diagonal", [True, False])
def test_route_to_nearest_candidate_matches_dijkstra(tiny, origin, allow_diagonal):
    body = tiny.post(URL, json={"origin": {"row": origin[0], "col": origin[1]},
                                "allow_diagonal": allow_diagonal}).json()
    assert body["status"] == "ok"
    model = CostModel()
    targets = candidates(SPEC)
    expected = reference_nearest_cost(grid_from_spec(SPEC), origin, targets, model,
                                      allow_diagonal)
    path = as_cells(body)
    assert path[0] == origin and path[-1] in targets
    assert body["summary"]["total_cost"] == pytest.approx(expected, abs=1e-4)
    assert path_cost(SPEC, path, model) == pytest.approx(expected, abs=1e-4)
    assert body["destination"] == {"row": path[-1][0], "col": path[-1][1]}
    assert body["shelter"]["candidates_count"] == len(targets) == 2


@pytest.mark.parametrize("seed", range(12))
def test_random_regions_match_dijkstra(tmp_path, monkeypatch, seed):
    rng = random.Random(seed)
    spec = [[(rng.uniform(0, 25), rng.uniform(0.75, 1.0), rng.random() < 0.15)
             for _ in range(7)] for _ in range(6)]
    spec[0][0] = (3.0, 0.99, False)
    weights = {"slope_weight": rng.uniform(0, 2), "radiation_weight": rng.uniform(0, 10)}
    model = CostModel(weights["slope_weight"], 2.0, weights["radiation_weight"])
    targets = candidates(spec)
    expected = reference_nearest_cost(grid_from_spec(spec), (0, 0), targets, model, True)
    with mola_client(monkeypatch, write_tiny_region(tmp_path / "r.json", spec)) as api:
        response = api.post(URL, json={"origin": {"row": 0, "col": 0}, **weights})
    if expected is None:
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NO_SHELTER"
        return
    body = response.json()
    assert as_cells(body)[-1] in targets
    assert body["summary"]["total_cost"] == pytest.approx(expected, abs=1e-4)
    assert body["cost_weights"]["radiation_weight"] == pytest.approx(weights["radiation_weight"])


def test_sky_view_factor_chooses_but_does_not_cost(tiny):
    """El costo devuelto es el de la fórmula sin sky_view_factor."""
    body = tiny.post(URL, json={"origin": {"row": 2, "col": 4}}).json()
    model = CostModel(0.05, 2.0, 0.0)
    assert body["summary"]["total_cost"] == pytest.approx(
        path_cost(SPEC, as_cells(body), model), abs=1e-4)
    assert body["shelter"]["destination_sky_view_factor"] <= 0.90
    assert body["shelter"]["destination_slope_deg"] <= 10.0


def test_origin_that_is_a_candidate_gives_single_cell(tiny):
    body = tiny.post(URL, json={"origin": {"row": 4, "col": 0}}).json()
    assert as_cells(body) == [(4, 0)]
    assert body["summary"]["total_cost"] == 0 and body["summary"]["steps"] == 0


def test_thresholds_are_configurable(tiny):
    # Más estricto: ninguna candidata.
    strict = tiny.post(URL, json={"origin": {"row": 2, "col": 2},
                                  "max_sky_view_factor": 0.85})
    assert strict.status_code == 404
    details = strict.json()["error"]["details"]
    assert strict.json()["error"]["code"] == "NO_SHELTER"
    assert details["candidates_count"] == 0
    # Admitir pendiente 20°: las celdas STEEP de (1, 1) y (1, 2) pasan a ser candidatas.
    loose = tiny.post(URL, json={"origin": {"row": 2, "col": 2}, "max_slope_deg": 20}).json()
    assert loose["shelter"]["candidates_count"] == 4
    assert loose["shelter"]["max_slope_deg"] == 20
    assert as_cells(loose)[-1] in {(1, 1), (1, 2)}


def test_unreachable_candidates_give_no_shelter(tmp_path, monkeypatch):
    spec = [[OPEN, WALL, SPOT], [OPEN, WALL, OPEN]]
    with mola_client(monkeypatch, write_tiny_region(tmp_path / "u.json", spec)) as api:
        response = api.post(URL, json={"origin": {"row": 0, "col": 0}})
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "NO_SHELTER"
    assert error["details"]["candidates_count"] == 1


@pytest.mark.parametrize("origin, code", [
    ({"row": 1, "col": 3}, "CELL_BLOCKED"),
    ({"row": 9, "col": 0}, "OUT_OF_BOUNDS"),
])
def test_invalid_origin(tiny, origin, code):
    response = tiny.post(URL, json={"origin": origin})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["details"]["field"] == "origin"


def test_blocked_origin_is_reported_even_without_candidates(tiny):
    response = tiny.post(URL, json={"origin": {"row": 1, "col": 3},
                                    "max_sky_view_factor": 0.1})
    assert response.json()["error"]["code"] == "CELL_BLOCKED"


def test_geographic_origin_inside_region(tiny):
    body = tiny.post(URL, json={"origin": {"latitude": -4.025, "longitude": 137.045}}).json()
    assert body["resolution"] == "mola-detail"
    assert body["origin"]["row"] == 2 and body["origin"]["col"] == 4
    assert all("latitude" in p and "longitude" in p for p in body["path"])


def test_geographic_origin_outside_region(tiny):
    response = tiny.post(URL, json={"origin": {"latitude": 10.0, "longitude": 20.0}})
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "SHELTER_LAYER_UNAVAILABLE"
    assert error["details"]["reason"] == "outside_detail_region"


def test_sources_without_the_layer_are_rejected(client, tmp_path, monkeypatch):
    synthetic = client.post(URL, json={"origin": {"row": 2, "col": 1}})
    assert synthetic.status_code == 400
    assert synthetic.json()["error"]["code"] == "SHELTER_LAYER_UNAVAILABLE"
    no_layer = write_tiny_region(tmp_path / "n.json", SPEC, with_radiation=False)
    with mola_client(monkeypatch, no_layer) as api:
        response = api.post(URL, json={"origin": {"row": 0, "col": 0}})
    assert response.json()["error"]["details"]["reason"] == "no_sky_view_layer"


@pytest.mark.parametrize("extra", [
    {"max_sky_view_factor": 1.5}, {"max_slope_deg": -1}, {"max_slope_deg": "10"},
    {"radiation_weight": 101}, {"destination": {"row": 0, "col": 0}}, {"unknown": 1},
])
def test_validation_errors(tiny, extra):
    response = tiny.post(URL, json={"origin": {"row": 0, "col": 0}, **extra})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_texts_use_planning_language(tiny):
    body = tiny.post(URL, json={"origin": {"row": 2, "col": 2}}).json()
    shelter = body["shelter"]
    assert shelter["term"] == "zona candidata de espera"
    assert shelter["label"] == "ÍNDICE DEL PROYECTO"
    assert "educativa" in shelter["note"]
    shelter_text = json.dumps(shelter, ensure_ascii=False).lower()
    assert not re.search(r"segur[oa]", shelter_text)
    assert not re.search(r"refugio seguro|zona segura|ruta segura",
                         json.dumps(body, ensure_ascii=False).lower())


def test_gale_candidate_count(monkeypatch):
    """Con los datos versionados de Gale y el criterio por defecto hay 64 candidatas."""
    monkeypatch.setenv("MARS_DATA_SOURCE", "mola")
    monkeypatch.setenv("MARS_MOLA_REGION", "gale")
    monkeypatch.delenv("MARS_MOLA_GRID_FILE", raising=False)
    _load_active_dataset.cache_clear()
    try:
        body = TestClient(app).post(URL, json={
            "origin": {"latitude": -4.59, "longitude": 137.44}}).json()
    finally:
        _load_active_dataset.cache_clear()
    assert body["shelter"]["candidates_count"] == 64
    assert body["shelter"]["destination_sky_view_factor"] <= 0.90
    assert not math.isnan(body["summary"]["total_cost"])


# ------------------------------------------------------------ max_distance_km
def reference_within_distance(grid, start, targets, model, allow_diagonal, max_cells):
    """Dijkstra completo: costo y longitud de la ruta de menor costo a cada celda;
    devuelve el menor costo entre los objetivos cuya ruta mide <= max_cells."""
    moves = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0)]
    if allow_diagonal:
        moves += [(-1, -1, SQRT2), (-1, 1, SQRT2), (1, -1, SQRT2), (1, 1, SQRT2)]
    import heapq
    dist, length = {start: 0.0}, {start: 0.0}
    heap = [(0.0, start)]
    while heap:
        d, cur = heapq.heappop(heap)
        if d > dist[cur]:
            continue
        for dr, dc, f in moves:
            r, c = cur[0] + dr, cur[1] + dc
            if not grid.in_bounds(r, c) or grid.cell(r, c).blocked:
                continue
            if dr and dc and (grid.cell(cur[0] + dr, cur[1]).blocked
                              or grid.cell(cur[0], cur[1] + dc).blocked):
                continue
            nd = d + f * model.cell_multiplier(grid.cell(r, c))
            if nd < dist.get((r, c), math.inf):
                dist[(r, c)], length[(r, c)] = nd, length[cur] + f
                heapq.heappush(heap, (nd, (r, c)))
    inside = [dist[t] for t in targets if t in dist and length[t] <= max_cells + 1e-9]
    return min(inside) if inside else None


# Candidata A en (0, 0) a 2 celdas tras una celda muy pendiente; B en (0, 7) a 5 celdas en llano.
CLIFF = (60.0, 1.0, False)  # costo de entrada 6: (0, 0) sale más cara que (0, 7)
# El cargador exige >= 2 filas: la segunda es un muro.
LINE = [[SPOT, CLIFF, OPEN, OPEN, OPEN, OPEN, OPEN, SPOT], [WALL] * 8]


@pytest.fixture()
def line(tmp_path, monkeypatch):
    with mola_client(monkeypatch, write_tiny_region(tmp_path / "line.json", LINE)) as api:
        yield api


def test_distance_is_always_reported(line):
    body = line.post(URL, json={"origin": {"row": 0, "col": 2}, "allow_diagonal": False}).json()
    assert as_cells(body)[-1] == (0, 7)  # más cercana por costo
    assert body["shelter"]["distance_km"] == pytest.approx(3.0)  # 5 celdas de 600 m
    assert body["summary"]["distance_m"] == pytest.approx(3000.0)
    assert "max_distance_km" not in body["shelter"]


def test_max_distance_picks_a_costlier_zone_within_the_limit(line):
    body = line.post(URL, json={"origin": {"row": 0, "col": 2}, "allow_diagonal": False,
                                "max_distance_km": 2.0}).json()
    assert as_cells(body)[-1] == (0, 0)
    assert body["shelter"]["distance_km"] == pytest.approx(1.2)
    assert body["shelter"]["max_distance_km"] == 2.0
    assert "2 km" in body["shelter"]["criterion"]


def test_max_distance_boundary_is_inclusive(line):
    body = line.post(URL, json={"origin": {"row": 0, "col": 2}, "allow_diagonal": False,
                                "max_distance_km": 1.2}).json()
    assert as_cells(body)[-1] == (0, 0)


def test_no_zone_within_max_distance_gives_no_shelter(line):
    response = line.post(URL, json={"origin": {"row": 0, "col": 2}, "allow_diagonal": False,
                                    "max_distance_km": 1.0})
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "NO_SHELTER"
    assert error["details"]["max_distance_km"] == 1.0
    assert error["details"]["candidates_count"] == 2


@pytest.mark.parametrize("value", [0, -1, "2", True])
def test_max_distance_must_be_positive_number(line, value):
    response = line.post(URL, json={"origin": {"row": 0, "col": 2}, "max_distance_km": value})
    assert response.status_code == 422


@pytest.mark.parametrize("seed", range(12))
@pytest.mark.parametrize("max_km", [1.0, 2.5, 4.0])
def test_max_distance_matches_reference(tmp_path, monkeypatch, seed, max_km):
    rng = random.Random(500 + seed)
    spec = [[(rng.uniform(0, 25), rng.uniform(0.75, 1.0), rng.random() < 0.15)
             for _ in range(8)] for _ in range(7)]
    spec[3][3] = (3.0, 0.99, False)
    model = CostModel()
    expected = reference_within_distance(grid_from_spec(spec), (3, 3), candidates(spec),
                                         model, True, max_km * 1000 / 600.0)
    with mola_client(monkeypatch, write_tiny_region(tmp_path / "d.json", spec)) as api:
        response = api.post(URL, json={"origin": {"row": 3, "col": 3},
                                       "max_distance_km": max_km})
    if expected is None:
        assert response.json()["error"]["code"] == "NO_SHELTER"
        return
    body = response.json()
    assert body["summary"]["total_cost"] == pytest.approx(expected, abs=1e-4)
    assert body["shelter"]["distance_km"] <= max_km + 1e-6


def test_max_length_matches_reference_on_many_grids():
    """find_nearest_target con max_length frente a la referencia, en 300 cuadrículas.

    Comprueba además que la muestra incluye casos en los que el límite cambia la zona
    elegida y casos sin zona dentro del límite (si no, la prueba no diría nada).
    """
    from algorithms.astar import NoTargetReachableError, find_nearest_target

    outcomes = {"changed": 0, "none": 0, "same": 0}
    for seed in range(300):
        rng = random.Random(9000 + seed)
        spec = [[(rng.choice([rng.uniform(0, 3), rng.uniform(60, 80)]),
                  rng.uniform(0.88, 1.0), rng.random() < 0.1)
                 for _ in range(9)] for _ in range(7)]
        spec[3][4] = (3.0, 0.99, False)
        grid = grid_from_spec(spec)
        targets = candidates(spec)
        max_cells = rng.uniform(1.0, 6.0)
        model = CostModel()
        free = reference_within_distance(grid, (3, 4), targets, model, True, math.inf)
        expected = reference_within_distance(grid, (3, 4), targets, model, True, max_cells)

        def is_target(pos, cell, targets=frozenset(targets)):
            return pos in targets

        if expected is None:
            outcomes["none"] += 1
            with pytest.raises(NoTargetReachableError):
                find_nearest_target(grid, (3, 4), is_target, model, True, max_length=max_cells)
            continue
        outcomes["changed" if abs(expected - free) > 1e-9 else "same"] += 1
        result = find_nearest_target(grid, (3, 4), is_target, model, True, max_length=max_cells)
        assert result.total_cost == pytest.approx(expected)
        assert result.distance_m / grid.cell_size_m <= max_cells + 1e-9
    assert outcomes["changed"] > 0 and outcomes["none"] > 0 and outcomes["same"] > 0
