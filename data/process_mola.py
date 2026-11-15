"""Create a bounded JSON grid from an official PDS4-labelled MOLA MEGDR raster.

Example:
    python3 data/process_mola.py --bounds -1 1 179 181 \
        --output data/processed/mola_equatorial_sample.json
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

if __package__:
    from .mola_reader import DEFAULT_IMAGE, GeographicBounds, MolaReader, MolaWindow
    from .mola_risk import RISK_MODEL, slope_risk
else:
    from mola_reader import DEFAULT_IMAGE, GeographicBounds, MolaReader, MolaWindow
    from mola_risk import RISK_MODEL, slope_risk

DEFAULT_MAX_SLOPE_DEG = 30.0
MOLA_DISCLAIMER = (
    "Topografía MOLA real expresada respecto al areoide. La pendiente se deriva "
    "numéricamente de este raster. El índice de riesgo mostrado es un proxy "
    "educativo derivado solo de la pendiente (pendiente / 20°, limitado a 0–1); "
    "no representa probabilidad de peligro ni modela geología, iluminación, "
    "comunicaciones o condiciones operacionales. No es una recomendación de seguridad."
)


def build_grid(
    window: MolaWindow,
    *,
    max_slope_deg: float = DEFAULT_MAX_SLOPE_DEG,
    name: str = "Región MOLA MEGDR",
    source_product: str = "megt90n000eb",
    disclaimer: str = MOLA_DISCLAIMER,
    extra: dict[str, Any] | None = None,
    cell_layers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert a bounded elevation crop into the API's row/column grid representation.

    The defaults describe the MOLA MEGDR product; other DEMs (for example the
    MOLA+HRSC blend processed by `process_dem.py`) pass their own provenance.
    `extra` adds optional top-level metadata placed before `cells`.
    `cell_layers` maps an optional per-cell field name to a (rows, cols) array;
    the value (rounded to 6 decimals) is added only to valid cells and must be
    finite there.
    """
    if not math.isfinite(max_slope_deg) or not 0.0 < max_slope_deg <= 90.0:
        raise ValueError("max_slope_deg debe ser mayor que 0 y como máximo 90.")
    layers = dict(cell_layers or {})
    for key, layer in layers.items():
        if getattr(layer, "shape", None) != (window.rows, window.cols):
            raise ValueError(f"La capa {key!r} no tiene el tamaño de la ventana.")

    cells = []
    for row in range(window.rows):
        for col in range(window.cols):
            valid = bool(window.valid[row, col]) and math.isfinite(
                float(window.slope_deg[row, col])
            )
            latitude, longitude = window.index_to_coordinate(row, col)
            slope = round(float(window.slope_deg[row, col]), 5) if valid else 0.0
            cells.append({
                "row": row,
                "col": col,
                "latitude": round(latitude, 8),
                "longitude": round(longitude, 8),
                "elevation_m": round(float(window.elevation_m[row, col]), 3)
                if valid else 0.0,
                "slope_deg": slope,
                "risk": round(slope_risk(slope), 6) if valid else 0.0,
                "blocked": not valid or float(window.slope_deg[row, col]) >= max_slope_deg,
                "valid": valid,
            })
            if valid:
                for key, layer in layers.items():
                    value = float(layer[row, col])
                    if not math.isfinite(value):
                        raise ValueError(f"La capa {key!r} no es finita en ({row}, {col}).")
                    cells[-1][key] = round(value, 6)

    bounds = window.bounds
    grid: dict[str, Any] = {
        "name": name,
        "data_source": "mola",
        "is_simulated": False,
        "risk_available": True,
        "risk_model": dict(RISK_MODEL),
        "disclaimer": disclaimer,
        "source_product": source_product,
        "grid": {
            "rows": window.rows,
            "cols": window.cols,
            "cell_size_m": round(window.cell_size_m, 6),
        },
        "region": {
            "south": round(bounds.south, 8),
            "north": round(bounds.north, 8),
            "west": round(bounds.west, 8),
            "east": round(bounds.east, 8),
            "latitude_type": "planetocentric",
            "longitude_direction": "positive_east",
        },
        "coordinate_system": {
            "type": "grid_index",
            "index_base": 0,
            "row_axis": "down",
            "col_axis": "right",
            "description": (
                "Fila/columna locales de la ventana MOLA. Cada celda incluye su "
                "centro en latitud planetocéntrica y longitud positiva este."
            ),
        },
        "max_slope_deg": max_slope_deg,
    }
    for key, value in (extra or {}).items():
        if key in grid or key == "cells":
            raise ValueError(f"El metadato adicional {key!r} reemplazaría un campo existente.")
        grid[key] = value
    grid["cells"] = cells
    return grid


def process_mola(
    bounds: GeographicBounds,
    output: Path | str,
    *,
    image_path: Path | str | None = None,
    label_path: Path | str | None = None,
    header_path: Path | str | None = None,
    max_slope_deg: float = DEFAULT_MAX_SLOPE_DEG,
) -> dict[str, Any]:
    """Read/process a region and create a new output file without replacing one."""
    reader = MolaReader(
        image_path=image_path or DEFAULT_IMAGE,
        label_path=label_path,
        header_path=header_path,
    )
    grid = build_grid(reader.read_window(bounds), max_slope_deg=max_slope_deg)
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(grid, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8") as stream:
        stream.write(rendered)
    return grid


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bounds", nargs=4, type=float, required=True,
        metavar=("SUR", "NORTE", "OESTE", "ESTE"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", type=Path)
    parser.add_argument("--label", type=Path)
    parser.add_argument("--header", type=Path)
    parser.add_argument("--max-slope-deg", type=float, default=DEFAULT_MAX_SLOPE_DEG)
    args = parser.parse_args()
    bounds = GeographicBounds.from_sequence(tuple(args.bounds))
    grid = process_mola(
        bounds,
        args.output,
        image_path=args.image,
        label_path=args.label,
        header_path=args.header,
        max_slope_deg=args.max_slope_deg,
    )
    print(
        f"Recorte MOLA procesado: {grid['grid']['rows']} x {grid['grid']['cols']} "
        f"celdas -> {args.output}"
    )


if __name__ == "__main__":
    main()
