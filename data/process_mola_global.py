"""Build a compact global MOLA routing grid at one-degree resolution."""

from __future__ import annotations

import gzip
import json
import math
import struct
import zlib
from pathlib import Path
from typing import Any

import numpy as np

if __package__:
    from .mola_risk import RISK_MODEL, slope_risk
    from .mola_reader import (
        DEFAULT_IMAGE,
        GeographicBounds,
        PLANET_RADIUS_M,
        MolaReader,
        _finite_difference,
    )
else:
    from mola_risk import RISK_MODEL, slope_risk
    from mola_reader import (
        DEFAULT_IMAGE,
        GeographicBounds,
        PLANET_RADIUS_M,
        MolaReader,
        _finite_difference,
    )

GLOBAL_ROWS = 180
GLOBAL_COLS = 360
MAX_SLOPE_DEG = 20.0
DEFAULT_OUTPUT = (
    Path(__file__).resolve().parent / "processed" / "mola_global_1deg.json.gz"
)
DEFAULT_BLOCKED_OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "frontend"
    / "assets"
    / "mola-global-blocked.png"
)
DEFAULT_RISK_OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "frontend"
    / "assets"
    / "mola-global-risk.png"
)


def build_global_grid(
    reader: MolaReader,
    *,
    rows: int = GLOBAL_ROWS,
    cols: int = GLOBAL_COLS,
    max_slope_deg: float = MAX_SLOPE_DEG,
) -> dict[str, Any]:
    """Average MOLA into a global grid and derive slopes at that grid's scale."""
    if (
        isinstance(rows, bool) or not isinstance(rows, int) or rows < 2
        or isinstance(cols, bool) or not isinstance(cols, int) or cols < 2
        or not math.isfinite(max_slope_deg) or not 0 < max_slope_deg <= 90
    ):
        raise ValueError("Dimensiones o umbral de pendiente global inválidos.")

    elevations, valid = reader.read_global_preview(cols, rows)
    latitude_step = 180.0 / rows
    longitude_step = 360.0 / cols
    native_rows_per_cell = reader.rows // rows
    native_cols_per_cell = reader.cols // cols
    if (
        native_rows_per_cell < 1 or native_cols_per_cell < 1
        or reader.rows % rows or reader.cols % cols
    ):
        raise ValueError("La malla global debe dividir exactamente el raster MOLA.")

    max_slopes = np.full((rows, cols), np.nan, dtype=np.float32)
    if native_rows_per_cell >= 2 and native_cols_per_cell >= 2:
        for row in range(rows):
            north = 90.0 - row * latitude_step
            south = north - latitude_step
            window = reader.read_window(
                GeographicBounds(south, north, 0.0, 360.0)
            )
            native_slopes = window.slope_deg
            native_valid = window.valid & np.isfinite(native_slopes)
            grouped_slopes = native_slopes.reshape(
                native_rows_per_cell, cols, native_cols_per_cell
            )
            grouped_valid = native_valid.reshape(
                native_rows_per_cell, cols, native_cols_per_cell
            )
            masked = np.where(grouped_valid, grouped_slopes, -np.inf)
            row_max = masked.max(axis=(0, 2))
            row_max[~grouped_valid.any(axis=(0, 2))] = np.nan
            max_slopes[row] = row_max
        valid &= np.isfinite(max_slopes)
    else:
        dy = PLANET_RADIUS_M * math.radians(latitude_step)
        latitudes_for_dx = (
            90.0 - (np.arange(rows, dtype=np.float64) + 0.5) * latitude_step
        )
        dx = (
            PLANET_RADIUS_M
            * np.cos(np.deg2rad(latitudes_for_dx))
            * math.radians(longitude_step)
        )[:, np.newaxis]
        dz_dy = _finite_difference(elevations, valid, axis=0, spacing=dy)
        dz_dx = _finite_difference(
            elevations, valid, axis=1, spacing=dx, periodic=True
        )
        max_slopes = np.degrees(np.arctan(np.hypot(dz_dx, dz_dy))).astype(np.float32)

    latitudes = 90.0 - (np.arange(rows, dtype=np.float64) + 0.5) * latitude_step
    cells = []
    for row in range(rows):
        latitude = float(latitudes[row])
        for col in range(cols):
            is_valid = bool(valid[row, col] and math.isfinite(float(max_slopes[row, col])))
            slope = round(float(max_slopes[row, col]), 4) if is_valid else 0.0
            cells.append({
                "row": row,
                "col": col,
                "latitude": round(latitude, 6),
                "longitude": round((col + 0.5) * longitude_step, 6),
                "elevation_m": round(float(elevations[row, col]), 1) if is_valid else 0.0,
                "slope_deg": slope,
                "risk": round(slope_risk(slope), 6) if is_valid else 0.0,
                "blocked": not is_valid or slope >= max_slope_deg,
                "valid": is_valid,
            })

    return {
        "name": "MOLA global, malla de 1 grado",
        "data_source": "mola",
        "is_simulated": False,
        "risk_available": True,
        "risk_model": dict(RISK_MODEL),
        "disclaimer": (
            "Vista global aproximada derivada de MOLA: cada celda abarca 1 grado "
            "(aproximadamente 59 km en el ecuador). El índice de riesgo es un proxy "
            "educativo de pendiente (pendiente / 20°, limitado a 0–1), no una "
            "probabilidad de peligro. No es adecuado para navegación operacional."
        ),
        "source_product": "megt90n000eb",
        "grid": {
            "rows": rows,
            "cols": cols,
            "cell_size_m": round(
                PLANET_RADIUS_M * math.radians(longitude_step), 6
            ),
        },
        "region": {
            "south": -90.0,
            "north": 90.0,
            "west": 0.0,
            "east": 360.0,
            "latitude_type": "planetocentric",
            "longitude_direction": "positive_east",
        },
        "max_slope_deg": max_slope_deg,
        "cells": cells,
    }


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    content = kind + payload
    return (
        struct.pack(">I", len(payload))
        + content
        + struct.pack(">I", zlib.crc32(content) & 0xFFFFFFFF)
    )


def write_blocked_overlay(
    grid: dict[str, Any], output: Path = DEFAULT_BLOCKED_OUTPUT
) -> Path:
    """Write a transparent global mask for cells blocked by the slope threshold."""
    rows = grid["grid"]["rows"]
    cols = grid["grid"]["cols"]
    pixels = np.zeros((rows, cols, 4), dtype=np.uint8)
    for cell in grid["cells"]:
        if cell["blocked"]:
            pixels[cell["row"], cell["col"]] = (255, 54, 76, 115)
    scanlines = b"".join(
        b"\x00" + pixels[row].tobytes() for row in range(rows)
    )
    header = struct.pack(">IIBBBBB", cols, rows, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(scanlines, level=9))
        + _png_chunk(b"IEND", b"")
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(png)
    return output


def write_risk_overlay(
    grid: dict[str, Any], output: Path = DEFAULT_RISK_OUTPUT
) -> Path:
    """Write a transparent global heatmap for the slope-only risk proxy."""
    rows = grid["grid"]["rows"]
    cols = grid["grid"]["cols"]
    pixels = np.zeros((rows, cols, 4), dtype=np.uint8)
    stops = np.array(
        [[37, 196, 126], [255, 203, 61], [242, 72, 76]], dtype=np.float64
    )
    for cell in grid["cells"]:
        if not cell["valid"]:
            continue
        risk = float(cell["risk"])
        scaled = risk * (len(stops) - 1)
        stop = min(len(stops) - 2, int(scaled))
        color = stops[stop] + (stops[stop + 1] - stops[stop]) * (scaled - stop)
        pixels[cell["row"], cell["col"], :3] = np.rint(color).astype(np.uint8)
        pixels[cell["row"], cell["col"], 3] = 45 + round(100 * risk)
    scanlines = b"".join(
        b"\x00" + pixels[row].tobytes() for row in range(rows)
    )
    header = struct.pack(">IIBBBBB", cols, rows, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(scanlines, level=9))
        + _png_chunk(b"IEND", b"")
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(png)
    return output


def process_global_mola(
    output: Path = DEFAULT_OUTPUT,
    image_path: Path = DEFAULT_IMAGE,
    blocked_output: Path = DEFAULT_BLOCKED_OUTPUT,
    risk_output: Path = DEFAULT_RISK_OUTPUT,
) -> dict[str, Any]:
    """Generate the compressed global route grid and matching visual mask."""
    grid = build_global_grid(MolaReader(image_path))
    rendered = json.dumps(
        grid, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        with gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as compressed:
            compressed.write(rendered)
    write_blocked_overlay(grid, blocked_output)
    write_risk_overlay(grid, risk_output)
    return grid


if __name__ == "__main__":
    result = process_global_mola()
    print(
        f"Cuadrícula global MOLA: {result['grid']['rows']} × "
        f"{result['grid']['cols']} celdas -> {DEFAULT_OUTPUT}"
    )
