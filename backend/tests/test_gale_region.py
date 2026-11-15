"""Región Gale (flanco noroeste del Monte Sharp) servida con MARS_MOLA_REGION=gale."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.map_service import MOLA_REGIONS, _load_active_dataset

ROUTE = "/api/v1/routes"
CURIOSITY_LANDING = {"latitude": -4.59, "longitude": 137.44}


@pytest.fixture()
def gale_client(monkeypatch):
    monkeypatch.setenv("MARS_DATA_SOURCE", "mola")
    monkeypatch.setenv("MARS_MOLA_REGION", "gale")
    monkeypatch.delenv("MARS_MOLA_GRID_FILE", raising=False)
    _load_active_dataset.cache_clear()
    yield TestClient(app)
    _load_active_dataset.cache_clear()


def test_gale_file_is_versioned_with_the_backend():
    assert MOLA_REGIONS["gale"].is_file()


def test_gale_map_covers_requested_window_at_600_m(gale_client):
    body = gale_client.get("/api/v1/map").json()
    assert body["data_source"] == "mola" and body["is_simulated"] is False
    assert body["name"].startswith("Gale")
    assert (body["grid"]["rows"], body["grid"]["cols"]) == (80, 70)
    assert body["grid"]["cell_size_m"] == pytest.approx(600.0, abs=0.01)
    assert len(body["cells"]) == 80 * 70
    region = body["region"]
    assert region["south"] <= -5.3 and region["north"] >= -4.5
    assert region["west"] <= 137.3 and region["east"] >= 138.0
    assert all(cell["valid"] for cell in body["cells"])
    assert any(cell["blocked"] for cell in body["cells"])
    assert all(0.0 <= cell["risk"] <= 1.0 for cell in body["cells"])


GALE_DISCLAIMER_START = (
    "DEM mezcla MOLA+HRSC 200 m agregado a 600 m; "
    "resolución de planificación, no de navegación"
)


def test_gale_disclaimer_declares_blend_resolution_and_citation(gale_client):
    map_disclaimer = gale_client.get("/api/v1/map").json()["disclaimer"]
    route_disclaimer = gale_client.post(ROUTE, json={
        "origin": CURIOSITY_LANDING,
        "destination": {"latitude": -4.6, "longitude": 137.45},
    }).json()["disclaimer"]
    for disclaimer in (map_disclaimer, route_disclaimer):
        assert disclaimer.startswith(GALE_DISCLAIMER_START)
        assert "Fergason, Hare y Laura (2018)" in disclaimer
        assert "No es una recomendación de seguridad" in disclaimer
        assert "Topografía MOLA real" not in disclaimer


def test_route_inside_gale_uses_detail_grid(gale_client):
    response = gale_client.post(ROUTE, json={
        "origin": CURIOSITY_LANDING,
        "destination": {"latitude": -4.9, "longitude": 137.6},
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["resolution"] == "mola-detail"
    assert body["summary"]["steps"] == len(body["path"]) - 1 > 0
    assert all(-5.31 <= p["latitude"] <= -4.49 for p in body["path"])


def test_gale_serves_modelled_radiation_layer(gale_client):
    body = gale_client.get("/api/v1/map").json()
    assert body["radiation_available"] is True
    model = body["radiation_model"]
    assert model["label"] == "MODELADO"
    assert model["horizon_radius_m"] == 10_000.0 and model["azimuths"] == 32
    assert model["truncated_cells"] == 0
    assert model["anchor"]["unverified_values"]["used_in_calculation"] is False
    assert "MODELADA" in body["disclaimer"]
    values = [c["radiation_modeled"] for c in body["cells"]]
    assert len(values) == 5600
    assert all(c["radiation_modeled"] == c["sky_view_factor"] for c in body["cells"])
    assert 0.0 < min(values) < max(values) < 1.0
    assert body["cost_model"]["radiation_weight"] == 0.0
