"""Pruebas de la región MOLA predeterminada (Valles Marineris) y de la muestra plana."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.map_service import (
    DEFAULT_MOLA_GRID_FILE,
    _load_active_dataset,
    _load_mola_dataset,
)

ROUTE = "/api/v1/routes"


@pytest.fixture()
def default_mola_client(monkeypatch):
    """Cliente con MARS_DATA_SOURCE=mola y SIN MARS_MOLA_GRID_FILE (usa la región por defecto)."""
    monkeypatch.setenv("MARS_DATA_SOURCE", "mola")
    monkeypatch.delenv("MARS_MOLA_GRID_FILE", raising=False)
    _load_active_dataset.cache_clear()
    yield TestClient(app)
    _load_active_dataset.cache_clear()


def test_default_region_is_valles_marineris():
    assert DEFAULT_MOLA_GRID_FILE.name == "mola_valles_marineris.json"
    assert DEFAULT_MOLA_GRID_FILE.is_file()


def test_default_region_map_has_real_relief(default_mola_client):
    body = default_mola_client.get("/api/v1/map").json()
    assert body["data_source"] == "mola"
    assert body["is_simulated"] is False
    assert body["risk_available"] is True
    assert all(0.0 <= cell["risk"] <= 1.0 for cell in body["cells"])
    assert max(cell["risk"] for cell in body["cells"]) == 1.0
    assert body["cost_model"]["risk_weight"] == 2.0
    assert body["grid"]["rows"] == 32 and body["grid"]["cols"] == 32
    region = body["region"]
    assert (region["south"], region["north"], region["west"], region["east"]) == (-14.0, -12.0, 291.0, 293.0)
    blocked = sum(cell["blocked"] for cell in body["cells"])
    assert 50 <= blocked <= 200            # hay obstáculos reales (pendiente >= 20 grados)
    assert max(cell["slope_deg"] for cell in body["cells"]) > 25
    elevations = [cell["elevation_m"] for cell in body["cells"] if cell["valid"]]
    assert max(elevations) - min(elevations) > 5000


def test_default_region_route_avoids_blocked_cells(default_mola_client):
    cells = {(c["row"], c["col"]): c for c in default_mola_client.get("/api/v1/map").json()["cells"]}
    response = default_mola_client.post(ROUTE, json={
        "origin": {"row": 16, "col": 2}, "destination": {"row": 16, "col": 29}})
    assert response.status_code == 200
    body = response.json()
    assert body["data_source"] == "mola"
    assert body["summary"]["steps"] == 27
    assert all(not cells[(p["row"], p["col"])]["blocked"] for p in body["path"])
    assert body["summary"]["max_risk"] == pytest.approx(
        max(cells[(p["row"], p["col"])]["risk"] for p in body["path"])
    )


def test_default_region_blocked_cell_is_rejected(default_mola_client):
    blocked = next(c for c in default_mola_client.get("/api/v1/map").json()["cells"] if c["blocked"])
    response = default_mola_client.post(ROUTE, json={
        "origin": {"row": blocked["row"], "col": blocked["col"]},
        "destination": {"row": 16, "col": 29}})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CELL_BLOCKED"


def test_flat_equatorial_sample_is_still_valid():
    flat = DEFAULT_MOLA_GRID_FILE.parent / "mola_region.json"
    dataset = _load_mola_dataset(flat)
    assert dataset.data_source == "mola"
    assert dataset.grid.rows == 32 and dataset.grid.cols == 32


def _free_components(cells):
    """Componentes conexas de celdas libres (8 vecinos, sin cortar esquinas). Referencia independiente de A*."""
    from collections import deque
    blocked = {(c["row"], c["col"]): c["blocked"] for c in cells}
    seen, sizes, owner = set(), [], {}
    for start in blocked:
        if blocked[start] or start in seen:
            continue
        queue, size = deque([start]), 0
        seen.add(start)
        while queue:
            r, c = queue.popleft()
            owner[(r, c)] = len(sizes)
            size += 1
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    n = (r + dr, c + dc)
                    if (dr == 0 and dc == 0) or n not in blocked or blocked[n] or n in seen:
                        continue
                    if dr and dc and (blocked[(r + dr, c)] or blocked[(r, c + dc)]):
                        continue
                    seen.add(n)
                    queue.append(n)
        sizes.append(size)
    return sizes, owner


def test_default_region_has_disconnected_free_zones_and_no_route_between_them(default_mola_client):
    cells = default_mola_client.get("/api/v1/map").json()["cells"]
    sizes, owner = _free_components(cells)
    assert sorted(sizes, reverse=True) == [698, 228, 1, 1]   # los escarpes separan la región en zonas
    assert owner[(2, 2)] != owner[(29, 29)]                  # origen y destino en zonas distintas
    response = default_mola_client.post(ROUTE, json={
        "origin": {"row": 2, "col": 2}, "destination": {"row": 29, "col": 29}})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NO_ROUTE"
