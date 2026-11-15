"""Selección de la región MOLA de detalle con MARS_MOLA_REGION y MARS_MOLA_GRID_FILE."""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.map_service import (
    DEFAULT_MOLA_GRID_FILE,
    MOLA_DISCLAIMER,
    MOLA_REGIONS,
    _load_active_dataset,
    _load_mola_dataset,
)


@pytest.fixture()
def mola_env(monkeypatch):
    monkeypatch.setenv("MARS_DATA_SOURCE", "mola")
    monkeypatch.delenv("MARS_MOLA_GRID_FILE", raising=False)
    monkeypatch.delenv("MARS_MOLA_REGION", raising=False)
    _load_active_dataset.cache_clear()
    yield monkeypatch
    _load_active_dataset.cache_clear()


def test_region_table_keeps_valles_marineris_as_default():
    assert MOLA_REGIONS["valles_marineris"] == DEFAULT_MOLA_GRID_FILE
    assert set(MOLA_REGIONS) == {"valles_marineris", "ecuatorial", "gale"}


def test_without_region_variable_valles_marineris_is_served(mola_env):
    region = TestClient(app).get("/api/v1/map").json()["region"]
    assert (region["south"], region["north"], region["west"], region["east"]) == (
        -14.0, -12.0, 291.0, 293.0,
    )


def test_region_variable_selects_equatorial_sample(mola_env):
    mola_env.setenv("MARS_MOLA_REGION", " Ecuatorial ")
    region = TestClient(app).get("/api/v1/map").json()["region"]
    assert (region["south"], region["north"], region["west"], region["east"]) == (
        -1.0, 1.0, 179.0, 181.0,
    )


def test_grid_file_variable_has_priority_over_region(mola_env):
    mola_env.setenv("MARS_MOLA_REGION", "ecuatorial")
    mola_env.setenv("MARS_MOLA_GRID_FILE", str(DEFAULT_MOLA_GRID_FILE))
    region = TestClient(app).get("/api/v1/map").json()["region"]
    assert region["west"] == 291.0


def test_region_disclaimer_comes_from_its_json(mola_env):
    stored = json.loads(DEFAULT_MOLA_GRID_FILE.read_text(encoding="utf-8"))["disclaimer"]
    assert TestClient(app).get("/api/v1/map").json()["disclaimer"] == stored


@pytest.mark.parametrize("value", [None, "", "   ", 7])
def test_missing_or_invalid_json_disclaimer_falls_back_to_mola_text(tmp_path, value):
    data = json.loads(DEFAULT_MOLA_GRID_FILE.read_text(encoding="utf-8"))
    if value is None:
        del data["disclaimer"]
    else:
        data["disclaimer"] = value
    path = tmp_path / "region.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    dataset = _load_mola_dataset(path)
    assert dataset.disclaimer == MOLA_DISCLAIMER
    assert dataset.payload["disclaimer"] == MOLA_DISCLAIMER


def test_unknown_region_is_dataset_unavailable(mola_env):
    mola_env.setenv("MARS_MOLA_REGION", "olympus")
    client = TestClient(app)
    for response in (
        client.get("/api/v1/map"),
        client.post("/api/v1/routes", json={
            "origin": {"latitude": -13.5, "longitude": 291.5},
            "destination": {"latitude": -13.4, "longitude": 291.6},
        }),
    ):
        assert response.status_code == 503
        error = response.json()["error"]
        assert error["code"] == "DATASET_UNAVAILABLE"
        assert "MARS_MOLA_REGION" in error["message"]
        assert error["details"] == {"data_source": "mola"}
