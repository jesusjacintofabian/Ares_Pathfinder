"""Regiones MOLA diminutas escritas por las pruebas (sin datos versionados)."""

import json
from contextlib import contextmanager

from fastapi.testclient import TestClient

from algorithms.astar import Grid, GridCell
from app.main import app
from app.services.map_service import _load_active_dataset


def write_tiny_region(path, rows_spec, with_radiation=True, cell_size_m=600.0):
    """Escribe un JSON de región MOLA a partir de una matriz de tuplas por celda.

    Cada celda es (slope_deg, sky_view_factor, blocked); radiation_modeled = sky_view_factor.
    """
    rows, cols = len(rows_spec), len(rows_spec[0])
    cells = []
    for r, row in enumerate(rows_spec):
        for c, (slope, svf, blocked) in enumerate(row):
            cell = {"row": r, "col": c, "elevation_m": -4500.0 + 10 * r,
                    "slope_deg": slope, "blocked": blocked, "valid": True,
                    "latitude": -4.0 - 0.01 * r, "longitude": 137.0 + 0.01 * c}
            if with_radiation:
                cell.update(sky_view_factor=svf, radiation_modeled=svf)
            cells.append(cell)
    data = {
        "name": "Región diminuta de prueba",
        "data_source": "mola",
        "is_simulated": False,
        "disclaimer": "Región diminuta generada por las pruebas.",
        "source_product": "DEM de prueba",
        "grid": {"rows": rows, "cols": cols, "cell_size_m": cell_size_m},
        "region": {"south": -4.0 - 0.01 * rows, "north": -4.0,
                   "west": 137.0, "east": 137.0 + 0.01 * cols},
        "coordinate_system": {"type": "grid_index", "index_base": 0, "row_axis": "down",
                              "col_axis": "right", "description": "Índices de prueba."},
        "cells": cells,
    }
    if with_radiation:
        data["radiation_available"] = True
        data["radiation_model"] = {"label": "MODELADO", "index": "radiation_modeled"}
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def grid_from_spec(rows_spec, cell_size_m=600.0):
    """Grid de A* equivalente a write_tiny_region (riesgo = pendiente / 20, máx. 1)."""
    return Grid([[GridCell(0.0, s, min(s / 20.0, 1.0), b, radiation=v, sky_view_factor=v)
                  for s, v, b in row] for row in rows_spec], cell_size_m)


@contextmanager
def mola_client(monkeypatch, grid_file):
    monkeypatch.setenv("MARS_DATA_SOURCE", "mola")
    monkeypatch.setenv("MARS_MOLA_GRID_FILE", str(grid_file))
    monkeypatch.delenv("MARS_MOLA_REGION", raising=False)
    _load_active_dataset.cache_clear()
    try:
        yield TestClient(app)
    finally:
        _load_active_dataset.cache_clear()
