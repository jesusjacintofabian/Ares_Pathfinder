"""Pesos ajustables por solicitud en POST /api/v1/routes (F6a)."""

import pytest
from pydantic import ValidationError

from algorithms.astar import CostModel
from app.models.schemas import RouteRequest
from tests.test_astar import dijkstra_cost
from tests.tiny_mola import grid_from_spec, mola_client, write_tiny_region

LEGACY_REQUEST = {"origin": {"row": 2, "col": 1}, "destination": {"row": 2, "col": 12},
                  "allow_diagonal": True}


def test_legacy_request_gives_the_documented_response(client):
    """Petición v1 sin pesos: misma respuesta que el ejemplo real del contrato."""
    body = client.post("/api/v1/routes", json=LEGACY_REQUEST).json()
    assert "cost_weights" not in body
    assert body["summary"]["total_cost"] == 34.918
    assert body["summary"]["steps"] == 14
    assert body["summary"]["nodes_expanded"] == 97
    assert body["path"][:3] == [{"row": 2, "col": 1}, {"row": 3, "col": 2},
                                {"row": 4, "col": 3}]


def test_explicit_default_weights_only_add_the_applied_weights(client):
    legacy = client.post("/api/v1/routes", json=LEGACY_REQUEST).json()
    explicit = client.post("/api/v1/routes", json={
        **LEGACY_REQUEST, "slope_weight": 0.05, "radiation_weight": 0}).json()
    assert explicit.pop("cost_weights") == {
        "slope_weight": 0.05, "risk_weight": 2.0, "radiation_weight": 0.0}
    assert explicit == legacy


def test_slope_weight_changes_cost(client):
    heavier = client.post("/api/v1/routes", json={**LEGACY_REQUEST, "slope_weight": 1.0}).json()
    assert heavier["cost_weights"]["slope_weight"] == 1.0
    assert heavier["summary"]["total_cost"] > 34.918


@pytest.mark.parametrize("field", ["slope_weight", "radiation_weight"])
@pytest.mark.parametrize("value", [-0.1, 100.01, "1", True, [1]])
def test_out_of_range_or_wrong_type_weights_are_rejected(client, field, value):
    response = client.post("/api/v1/routes", json={**LEGACY_REQUEST, field: value})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("value", [float("inf"), float("nan")])
def test_non_finite_weights_are_rejected(value):
    with pytest.raises(ValidationError):
        RouteRequest(**LEGACY_REQUEST, radiation_weight=value)


@pytest.mark.parametrize("value", [0, 0.0, 100, 3.5])
def test_weights_between_0_and_100_are_accepted(value):
    assert RouteRequest(**LEGACY_REQUEST, slope_weight=value).slope_weight == value


# Fila central muy expuesta (cielo visible alto) y filas laterales con menos cielo.
EXPOSED = [
    [(2.0, 0.1, False)] * 5,
    [(2.0, 0.1, False)] + [(2.0, 1.0, False)] * 3 + [(2.0, 0.1, False)],
    [(2.0, 0.1, False)] * 5,
]


@pytest.mark.parametrize("radiation_weight", [0.0, 5.0])
@pytest.mark.parametrize("allow_diagonal", [True, False])
def test_radiation_weight_matches_dijkstra_on_tiny_region(
        tmp_path, monkeypatch, radiation_weight, allow_diagonal):
    grid_file = write_tiny_region(tmp_path / "tiny.json", EXPOSED)
    with mola_client(monkeypatch, grid_file) as api:
        body = api.post("/api/v1/routes", json={
            "origin": {"row": 1, "col": 0}, "destination": {"row": 1, "col": 4},
            "allow_diagonal": allow_diagonal, "radiation_weight": radiation_weight}).json()
    expected = dijkstra_cost(grid_from_spec(EXPOSED), (1, 0), (1, 4),
                             CostModel(0.05, 2.0, radiation_weight), allow_diagonal)
    assert body["summary"]["total_cost"] == pytest.approx(expected, abs=1e-4)
    inner = [(p["row"], p["col"]) for p in body["path"][1:-1]]
    if radiation_weight == 0.0 and not allow_diagonal:
        assert inner == [(1, 1), (1, 2), (1, 3)]
    if radiation_weight > 0:
        assert all(r != 1 for r, _ in inner)
