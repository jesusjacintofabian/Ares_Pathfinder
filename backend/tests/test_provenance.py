"""Campo opcional provenance por capa en GET /api/v1/map (F6a)."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.map_service import _load_active_dataset
from tests.tiny_mola import mola_client, write_tiny_region

ALLOWED = {"MEDIDO", "DERIVADO", "INDICADOR", "MODELADO", "INTERPRETADO", "REFERENCIA",
           "ÍNDICE DEL PROYECTO"}
SPEC = [[(2.0, 0.9, False)] * 3] * 2


def mola_map(monkeypatch, region):
    monkeypatch.setenv("MARS_DATA_SOURCE", "mola")
    monkeypatch.setenv("MARS_MOLA_REGION", region)
    monkeypatch.delenv("MARS_MOLA_GRID_FILE", raising=False)
    _load_active_dataset.cache_clear()
    try:
        return TestClient(app).get("/api/v1/map").json()
    finally:
        _load_active_dataset.cache_clear()


def test_gale_declares_one_label_per_existing_layer(monkeypatch):
    provenance = mola_map(monkeypatch, "gale")["provenance"]
    assert {k: v["label"] for k, v in provenance.items()} == {
        "elevation_m": "MEDIDO",
        "slope_deg": "DERIVADO",
        "risk": "DERIVADO",
        "blocked": "ÍNDICE DEL PROYECTO",
        "sky_view_factor": "DERIVADO",
        "radiation_modeled": "MODELADO",
        "total_cost": "ÍNDICE DEL PROYECTO",
    }
    assert "Fergason" in provenance["elevation_m"]["source"]
    assert provenance["sky_view_factor"]["in_cost"] is False
    assert "MODELADO" in provenance["sky_view_factor"]["note"]
    assert provenance["radiation_modeled"]["in_cost"] is True
    assert "30°" in provenance["blocked"]["source"]
    assert provenance["blocked"]["in_cost"] is False


def test_region_without_radiation_layer_omits_those_entries(monkeypatch):
    provenance = mola_map(monkeypatch, "valles_marineris")["provenance"]
    assert set(provenance) == {"elevation_m", "slope_deg", "risk", "blocked", "total_cost"}
    assert "20°" in provenance["blocked"]["source"]
    assert "megt90n000eb" in provenance["elevation_m"]["source"]


def test_synthetic_map_has_no_provenance(map_data):
    assert "provenance" not in map_data


def test_labels_are_from_the_allowed_set_and_layers_exist(tmp_path, monkeypatch):
    with mola_client(monkeypatch, write_tiny_region(tmp_path / "t.json", SPEC)) as api:
        body = api.get("/api/v1/map").json()
    provenance = body["provenance"]
    assert {v["label"] for v in provenance.values()} <= ALLOWED
    cell_fields = set(body["cells"][0])
    for layer in provenance:
        assert layer == "total_cost" or layer in cell_fields
    for absent in ("INDICADOR", "INTERPRETADO", "REFERENCIA"):
        assert absent not in {v["label"] for v in provenance.values()}
