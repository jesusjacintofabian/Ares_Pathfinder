"""Load the selected route grid and build the API map response."""

import json
import gzip
import math
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, TypeGuard

from algorithms.astar import CostModel, Grid, GridCell
from app.errors import ApiError
from data.mola_reader import MAX_WINDOW_CELLS
from data.mola_risk import RISK_MODEL, RISK_SCALE_SLOPE_DEG, slope_risk

DATA_FILE = Path(__file__).resolve().parents[3] / "data" / "processed" / "synthetic_grid.json"
# Región MOLA predeterminada: Valles Marineris (latitud -14 a -12, longitud 291 a 293 este).
# Tiene relieve real (pendientes de hasta 32 grados y unos 9 km de desnivel), por lo que
# A* debe rodear celdas bloqueadas. La muestra ecuatorial plana sigue disponible en
# data/processed/mola_region.json (se usa con MARS_MOLA_GRID_FILE).
PROCESSED_DIR = Path(__file__).resolve().parents[3] / "data" / "processed"
DEFAULT_MOLA_GRID_FILE = PROCESSED_DIR / "mola_valles_marineris.json"
# Regiones de detalle seleccionables con MARS_MOLA_REGION (MARS_MOLA_GRID_FILE tiene prioridad).
DEFAULT_MOLA_REGION = "valles_marineris"
MOLA_REGIONS: Dict[str, Path] = {
    "valles_marineris": DEFAULT_MOLA_GRID_FILE,
    "ecuatorial": PROCESSED_DIR / "mola_region.json",
    # Cráter Gale, flanco noroeste del Monte Sharp: DEM MOLA+HRSC agregado a ~600 m.
    "gale": PROCESSED_DIR / "gale_monte_sharp_600m.json",
}
DEFAULT_MOLA_GLOBAL_GRID_FILE = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "processed"
    / "mola_global_1deg.json.gz"
)

DISCLAIMER = (
    "DATOS SIMULADOS: elevación, pendiente y riesgo son sintéticos y no provienen "
    "de NASA ni de ninguna misión real. Este laboratorio es educativo y no "
    "garantiza que una ruta sea segura en Marte."
)

COST_MODEL = CostModel(slope_weight=0.05, risk_weight=2.0, radiation_weight=0.0)
COST_FORMULA = (
    "costo_paso = factor_longitud * (1 + slope_weight * slope_deg + risk_weight * risk "
    "+ radiation_weight * radiation_modeled); radiation_modeled vale 0 si la fuente no "
    "trae la capa MODELADA; "
    "se usan los valores de la celda de destino del paso"
)
MOLA_DISCLAIMER = (
    "Topografía MOLA real respecto al areoide. La pendiente se deriva del raster. "
    "El índice de riesgo es un proxy educativo derivado solo de la pendiente "
    f"(pendiente / {RISK_SCALE_SLOPE_DEG:g}°, limitado a 0–1); no representa una "
    "probabilidad de peligro ni modela geología, iluminación, comunicaciones o "
    "condiciones operacionales. No es una recomendación de seguridad."
)


# Campos opcionales por celda de la capa de radiación MODELADA (data/radiation_model.py).
RADIATION_CELL_FIELDS = ("sky_view_factor", "radiation_modeled")


@dataclass(frozen=True)
class ActiveDataset:
    """Grid and provenance shared by map and route endpoints."""

    payload: Dict[str, Any]
    grid: Grid
    data_source: str
    is_simulated: bool
    disclaimer: str
    risk_available: bool
    cost_model: CostModel
    global_grid: Grid | None = None
    global_grid_region: Dict[str, Any] | None = None


class DatasetConfigurationError(ValueError):
    """The configured data source or prepared region is unavailable."""


def _is_finite_number(value: Any) -> TypeGuard[int | float]:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


@lru_cache(maxsize=1)
def load_dataset() -> Dict[str, Any]:
    """Lee y valida data/processed/synthetic_grid.json (se carga una sola vez)."""
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"No se encontró {DATA_FILE}. Ejecuta: python3 data/generate_synthetic_grid.py"
        )
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    rows, cols = data["rows"], data["cols"]
    positions = {(c["row"], c["col"]) for c in data["cells"]}
    expected = {(r, c) for r in range(rows) for c in range(cols)}
    if len(data["cells"]) != rows * cols or positions != expected:
        raise ValueError("El conjunto de datos no cubre exactamente la cuadrícula declarada.")
    return data


@lru_cache(maxsize=1)
def get_grid() -> Grid:
    """Construye el objeto Grid que usa el algoritmo A*."""
    data = load_dataset()
    matrix = [[None] * data["cols"] for _ in range(data["rows"])]
    for c in data["cells"]:
        matrix[c["row"]][c["col"]] = GridCell(
            elevation_m=c["elevation_m"],
            slope_deg=c["slope_deg"],
            risk=c["risk"],
            blocked=c["blocked"],
        )
    return Grid(matrix, data["cell_size_m"])


def get_configured_data_source() -> str:
    """Return and validate the application-wide source selector."""
    source = os.getenv("MARS_DATA_SOURCE", "synthetic").strip().lower()
    if source not in {"synthetic", "mola"}:
        raise ApiError(
            503,
            "DATASET_UNAVAILABLE",
            "MARS_DATA_SOURCE debe ser 'synthetic' o 'mola'.",
            {"data_source": source},
        )
    return source


def get_configured_mola_grid_file() -> Path:
    """MARS_MOLA_GRID_FILE if set; otherwise the MARS_MOLA_REGION entry (Valles by default)."""
    explicit = os.getenv("MARS_MOLA_GRID_FILE", "").strip()
    if explicit:
        return Path(explicit)
    region = os.getenv("MARS_MOLA_REGION", DEFAULT_MOLA_REGION).strip().lower()
    if region not in MOLA_REGIONS:
        raise ApiError(
            503,
            "DATASET_UNAVAILABLE",
            "MARS_MOLA_REGION debe ser una de: " + ", ".join(sorted(MOLA_REGIONS)) + ".",
            {"data_source": "mola"},
        )
    return MOLA_REGIONS[region]


def get_active_dataset() -> ActiveDataset:
    """Load one bounded grid; existing clients default to the synthetic dataset."""
    source = get_configured_data_source()
    if source == "synthetic":
        return _load_active_dataset(source, "")
    grid_file = get_configured_mola_grid_file()
    try:
        return _load_active_dataset(source, str(grid_file.resolve()))
    except DatasetConfigurationError as exc:
        raise ApiError(
            503, "DATASET_UNAVAILABLE", str(exc), {"data_source": source}
        ) from exc


@lru_cache(maxsize=4)
def _load_active_dataset(source: str, grid_file: str) -> ActiveDataset:
    if source == "synthetic":
        data = load_dataset()
        return ActiveDataset(
            payload=_build_synthetic_map_payload(data),
            grid=get_grid(),
            data_source="synthetic",
            is_simulated=True,
            disclaimer=DISCLAIMER,
            risk_available=True,
            cost_model=COST_MODEL,
        )
    local_dataset = _load_mola_dataset(Path(grid_file))
    global_dataset = _load_mola_dataset(DEFAULT_MOLA_GLOBAL_GRID_FILE)
    global_grid = global_dataset.payload
    payload = {
        **local_dataset.payload,
        "global_grid": {
            "rows": global_grid["grid"]["rows"],
            "cols": global_grid["grid"]["cols"],
            "cell_size_m": global_grid["grid"]["cell_size_m"],
            "region": global_grid["region"],
            "cells": [
                {
                    "elevation_m": cell["elevation_m"],
                    "slope_deg": cell["slope_deg"],
                    "risk": cell["risk"],
                    "blocked": cell["blocked"],
                    "valid": cell["valid"],
                }
                for cell in global_grid["cells"]
            ],
        },
    }
    return ActiveDataset(
        payload=payload,
        grid=local_dataset.grid,
        data_source=local_dataset.data_source,
        is_simulated=local_dataset.is_simulated,
        disclaimer=local_dataset.disclaimer,
        risk_available=local_dataset.risk_available,
        cost_model=local_dataset.cost_model,
        global_grid=global_dataset.grid,
        global_grid_region=global_grid["region"],
    )


def _load_mola_dataset(path: Path) -> ActiveDataset:
    if not path.is_file():
        raise DatasetConfigurationError(
            f"No se encontró la cuadrícula MOLA procesada: {path}. "
            "Genérela con data/process_mola.py y vuelva a iniciar la API."
        )
    try:
        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                data = json.load(stream)
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetConfigurationError(f"No se pudo leer la cuadrícula MOLA {path}: {exc}") from exc

    if data.get("data_source") != "mola" or data.get("is_simulated") is not False:
        raise DatasetConfigurationError(
            f"{path} no declara una cuadrícula topográfica MOLA real."
        )
    grid_info = data.get("grid")
    cells = data.get("cells")
    if not isinstance(grid_info, dict) or not isinstance(cells, list):
        raise DatasetConfigurationError(f"Formato de cuadrícula MOLA inválido en {path}.")
    rows, cols = grid_info.get("rows"), grid_info.get("cols")
    cell_size_m = grid_info.get("cell_size_m")
    if (
        isinstance(rows, bool) or not isinstance(rows, int) or rows < 2
        or isinstance(cols, bool) or not isinstance(cols, int) or cols < 2
        or rows * cols > MAX_WINDOW_CELLS
        or not isinstance(cell_size_m, (int, float))
        or not math.isfinite(cell_size_m) or cell_size_m <= 0
        or len(cells) != rows * cols
    ):
        raise DatasetConfigurationError(f"Dimensiones inválidas en la cuadrícula MOLA {path}.")

    matrix: list[list[GridCell | None]] = [[None] * cols for _ in range(rows)]
    positions: set[tuple[int, int]] = set()
    radiation_cells = 0
    for cell in cells:
        if not isinstance(cell, dict):
            raise DatasetConfigurationError(f"Celda inválida en la cuadrícula MOLA {path}.")
        row, col = cell.get("row"), cell.get("col")
        if (
            isinstance(row, bool) or not isinstance(row, int) or not 0 <= row < rows
            or isinstance(col, bool) or not isinstance(col, int) or not 0 <= col < cols
            or (row, col) in positions
        ):
            raise DatasetConfigurationError(
                f"Índice inválido o duplicado en cuadrícula MOLA {path}: ({row}, {col})."
            )
        positions.add((row, col))
        elevation, slope = cell.get("elevation_m"), cell.get("slope_deg")
        valid = cell.get("valid") is True
        if not valid:
            elevation, slope = 0.0, 0.0
        if not (
            _is_finite_number(elevation)
            and _is_finite_number(slope)
        ):
            raise DatasetConfigurationError(
                f"Elevación o pendiente inválidas en ({row}, {col}) de {path}."
            )
        if slope < 0.0:
            raise DatasetConfigurationError(
                f"Pendiente inválida en ({row}, {col}) de {path}."
            )
        risk = slope_risk(float(slope)) if valid else 0.0
        cell["risk"] = risk
        if not isinstance(cell.get("blocked"), bool):
            raise DatasetConfigurationError(f"Campo blocked inválido en ({row}, {col}) de {path}.")
        radiation = 0.0
        sky_view: float | None = None
        layer_values = [cell.get(key) for key in RADIATION_CELL_FIELDS if key in cell]
        if layer_values:
            if not valid or len(layer_values) != len(RADIATION_CELL_FIELDS) or not all(
                _is_finite_number(value) and 0.0 <= value <= 1.0 for value in layer_values
            ):
                raise DatasetConfigurationError(
                    f"Capa de radiación MODELADA inválida en ({row}, {col}) de {path}."
                )
            radiation = float(cell["radiation_modeled"])
            sky_view = float(cell["sky_view_factor"])
            radiation_cells += 1
        matrix[row][col] = GridCell(
            elevation_m=float(elevation),
            slope_deg=float(slope),
            risk=float(risk),
            blocked=cell["blocked"] or not valid,
            radiation=radiation,
            sky_view_factor=sky_view,
        )

    if len(positions) != rows * cols:
        raise DatasetConfigurationError(f"Faltan celdas en la cuadrícula MOLA {path}.")
    complete_matrix: list[list[GridCell]] = []
    for row_cells in matrix:
        if any(cell is None for cell in row_cells):
            raise DatasetConfigurationError(f"Faltan celdas en la cuadrícula MOLA {path}.")
        complete_matrix.append([cell for cell in row_cells if cell is not None])
    grid = Grid(complete_matrix, float(cell_size_m))
    radiation_model = data.get("radiation_model")
    valid_cells = sum(1 for cell in cells if cell.get("valid") is True)
    if radiation_cells and not (
        isinstance(radiation_model, dict) and radiation_model.get("label") == "MODELADO"
        and radiation_cells == valid_cells
    ):
        raise DatasetConfigurationError(
            f"{path} trae radiación por celda sin un radiation_model MODELADO completo."
        )
    radiation_available = radiation_cells > 0
    # Cada región procesada declara su propia procedencia (MOLA MEGDR, DEM MOLA+HRSC…);
    # si el JSON no trae disclaimer se usa el texto MOLA genérico.
    file_disclaimer = data.get("disclaimer")
    disclaimer = (
        file_disclaimer.strip()
        if isinstance(file_disclaimer, str) and file_disclaimer.strip()
        else MOLA_DISCLAIMER
    )
    payload = {
        **data,
        "disclaimer": disclaimer,
        "risk_available": True,
        "risk_model": dict(RISK_MODEL),
        "radiation_available": radiation_available if radiation_available else None,
        "radiation_model": radiation_model if radiation_available else None,
        "cost_model": _cost_model_payload(),
        "provenance": build_provenance(data, radiation_available),
    }
    return ActiveDataset(
        payload=payload,
        grid=grid,
        data_source="mola",
        is_simulated=False,
        disclaimer=disclaimer,
        risk_available=True,
        cost_model=COST_MODEL,
    )


SKY_VIEW_PROVENANCE_NOTE = (
    "Es DERIVADO porque es geometría calculada solo desde el DEM (ángulo de horizonte "
    "en 32 acimuts), sin supuestos físicos sobre la radiación. La capa de F3 se "
    "etiqueta MODELADO porque radiation_modeled añade hipótesis (cielo isótropo, "
    "bloqueo total por el relieve, más cielo = más exposición) para interpretarla "
    "como radiación. Aquí solo se usa para elegir zonas candidatas de espera; no entra "
    "al costo (correlación -0,90 con la pendiente)."
)


def _elevation_source(data: Dict[str, Any]) -> str:
    source = data.get("source")
    if isinstance(source, dict) and source.get("dataset"):
        citation = source.get("citation")
        return f"{source['dataset']}" + (f" ({citation})" if citation else "")
    if data.get("source_product") == "megt90n000eb":
        return "MOLA MEGDR megt90n000eb, PDS (Smith et al., 2003)"
    product = data.get("source_product")
    return str(product) if product else "Producto MOLA declarado por la región"


def build_provenance(data: Dict[str, Any], radiation_available: bool) -> Dict[str, Any]:
    """Procedencia por capa de una región MOLA; solo capas presentes en la respuesta.

    No se emiten INDICADOR (terreno blando), INTERPRETADO (geología) ni REFERENCIA
    (ruta de Curiosity) porque el backend no sirve esas capas.
    """
    provenance: Dict[str, Any] = {
        "elevation_m": {
            "label": "MEDIDO",
            "source": _elevation_source(data),
            "in_cost": False,
            "note": "Entra al costo solo a través de la pendiente derivada. "
                    "Los productos MOLA incluyen valores interpolados donde no hubo "
                    "observaciones.",
        },
        "slope_deg": {
            "label": "DERIVADO",
            "source": "Calculada desde la elevación de la región.",
            "in_cost": True,
        },
        "risk": {
            "label": "DERIVADO",
            "source": f"Proxy topográfico min(slope_deg / {RISK_SCALE_SLOPE_DEG:g}, 1).",
            "in_cost": True,
            "note": "No es una probabilidad de peligro.",
        },
    }
    threshold = data.get("max_slope_deg")
    rule = (
        f"pendiente >= {threshold:g}° (umbral demostrativo del procesado)"
        if _is_finite_number(threshold) else "pendiente >= umbral demostrativo del procesado"
    )
    provenance["blocked"] = {
        "label": "ÍNDICE DEL PROYECTO",
        "source": f"Regla del laboratorio: celda inválida o {rule}.",
        "in_cost": False,
        "note": "No suma costo: A* no atraviesa celdas bloqueadas. El umbral no es el "
                "límite validado de un traje ni de un vehículo.",
    }
    if radiation_available:
        provenance["sky_view_factor"] = {
            "label": "DERIVADO",
            "source": "Fracción de cielo visible calculada desde el DEM (data/sky_view.py).",
            "in_cost": False,
            "note": SKY_VIEW_PROVENANCE_NOTE,
        }
        provenance["radiation_modeled"] = {
            "label": "MODELADO",
            "source": "Índice relativo desde sky_view_factor con supuestos declarados en "
                      "radiation_model; ancla RAD (Hassler et al., 2014).",
            "in_cost": True,
            "note": "radiation_weight vale 0 por defecto; ajustable por solicitud.",
        }
    provenance["total_cost"] = {
        "label": "ÍNDICE DEL PROYECTO",
        "source": "Combinación ponderada de las capas con in_cost = true (cost_model).",
        "in_cost": False,
        "note": "Es el resultado del costo: una puntuación de planificación educativa, "
                "no una probabilidad.",
    }
    return provenance


def _cost_model_payload() -> Dict[str, Any]:
    return {
        "formula": COST_FORMULA,
        "slope_weight": COST_MODEL.slope_weight,
        "risk_weight": COST_MODEL.risk_weight,
        "radiation_weight": COST_MODEL.radiation_weight,
        "diagonal_length_factor": 1.4142,
        "cost_unit": "cost_units",
    }


def build_map_payload() -> Dict[str, Any]:
    """Diccionario compatible con el modelo MapResponse."""
    return get_active_dataset().payload


def _build_synthetic_map_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": data["name"],
        "data_source": "synthetic",
        "is_simulated": True,
        "disclaimer": DISCLAIMER,
        "risk_available": True,
        "grid": {
            "rows": data["rows"],
            "cols": data["cols"],
            "cell_size_m": data["cell_size_m"],
        },
        "coordinate_system": {
            "type": "grid_index",
            "index_base": 0,
            "row_axis": "down",
            "col_axis": "right",
            "description": (
                "Índices de cuadrícula (row, col) desde la esquina superior izquierda. "
                "No son latitud ni longitud."
            ),
        },
        "cost_model": _cost_model_payload(),
        "cells": data["cells"],
    }
