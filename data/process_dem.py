"""Crop a geographic int16 GeoTIFF DEM window into the API's JSON grid format.

Designed for the USGS MOLA+HRSC blended DEM (200 m/pixel). The DEM can be a
local file or an HTTPS URL: with a URL only the window's rows are requested
(HTTP Range), so the ≈ 11 GB global file is never downloaded.

Slope is computed at native resolution (with a 1-pixel margin so edge cells
use central differences) and can then be aggregated into coarser cells:
elevation = block mean, slope = block maximum, and a block is valid only if
all its pixels are valid.

By default it also derives the MODELLED radiation layer: the sky-view factor
of each native pixel (horizon search up to `--horizon-radius-km`, read as an
extra margin around the window) averaged per block. See data/sky_view.py and
data/radiation_model.py for the assumptions and limits.

Example (Gale crater, provisional window, 600 m cells):
    python3 data/process_dem.py --dem https://planetarymaps.usgs.gov/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif \\
        --bounds -5.3 -4.5 137.3 138.0 --aggregate 3 \\
        --name "Gale — flanco noroeste del Monte Sharp" \\
        --save-raw data/raw/gale/gale_clip_200m.tif \\
        --output data/processed/gale_monte_sharp_600m.json
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Optional

import numpy as np

if __package__:
    from .geotiff_reader import (
        ByteSource, DemWindow, GeoTiffReader, HttpRangeSource, LocalFileSource,
        write_geotiff_int16,
    )
    from .mola_reader import GeographicBounds, MAX_WINDOW_CELLS, MolaWindow
    from .process_mola import DEFAULT_MAX_SLOPE_DEG, build_grid
    from .radiation_model import radiation_metadata
    from .sky_view import DEFAULT_AZIMUTHS, DEFAULT_HORIZON_RADIUS_M, block_mean, compute_sky_view
else:
    from geotiff_reader import (
        ByteSource, DemWindow, GeoTiffReader, HttpRangeSource, LocalFileSource,
        write_geotiff_int16,
    )
    from mola_reader import GeographicBounds, MAX_WINDOW_CELLS, MolaWindow
    from process_mola import DEFAULT_MAX_SLOPE_DEG, build_grid
    from radiation_model import radiation_metadata
    from sky_view import DEFAULT_AZIMUTHS, DEFAULT_HORIZON_RADIUS_M, block_mean, compute_sky_view

DEFAULT_AGGREGATE = 3
DEFAULT_NAME = "Región DEM MOLA+HRSC"
# Provenance of the USGS MOLA+HRSC blended DEM (see docs/FUENTES_DE_DATOS.md).
HRSC_MOLA_DATASET = "Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2 (USGS Astrogeology)"
HRSC_MOLA_PAGE = (
    "https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m"
)
HRSC_MOLA_CITATION = "Fergason, Hare y Laura (2018)"
HRSC_MOLA_LICENSE = "MOLA: CC0; HRSC: CC BY-SA 3.0 IGO"


def dem_disclaimer(cell_size_m: float, aggregate: int, *, radiation: bool = False) -> str:
    """Disclaimer stored in the JSON and served by the API for this region."""
    resolution = (
        f"agregado a {cell_size_m:.0f} m" if aggregate > 1 else "sin agregar"
    )
    aggregation = (
        f" Cada celda agrupa {aggregate} × {aggregate} píxeles: elevación media y "
        "pendiente máxima del bloque, calculada a resolución nativa."
        if aggregate > 1 else " La pendiente se calcula a resolución nativa."
    )
    not_modelled = (
        "terreno blando, geología o condiciones operacionales" if radiation
        else "terreno blando, radiación, geología o condiciones operacionales"
    )
    radiation_text = (
        " La capa de radiación es MODELADA: un índice relativo de cielo visible derivado "
        "del DEM (hipótesis del autor, anclada en las mediciones de RAD en Gale); no es una "
        "medición por celda ni una dosis."
        if radiation else ""
    )
    return (
        f"DEM mezcla MOLA+HRSC 200 m {resolution}; resolución de planificación, no de "
        f"navegación. Fuente: {HRSC_MOLA_CITATION}, USGS Astrogeology.{aggregation} El índice de riesgo "
        "es un proxy educativo derivado solo de la pendiente (pendiente / 20°, limitado "
        f"a 0–1); no representa probabilidad de peligro ni modela {not_modelled}."
        f"{radiation_text} No es una recomendación de seguridad."
    )


def aggregate_window(window: MolaWindow, factor: int) -> MolaWindow:
    """Aggregate `factor` × `factor` blocks: mean elevation, max slope, all-valid."""
    if isinstance(factor, bool) or not isinstance(factor, int) or factor < 1:
        raise ValueError("El factor de agregación debe ser un entero positivo.")
    if factor == 1:
        return window
    rows, cols = window.rows, window.cols
    if rows % factor or cols % factor:
        raise ValueError("La ventana debe ser múltiplo del factor de agregación.")
    out_rows, out_cols = rows // factor, cols // factor

    def blocks(array: np.ndarray) -> np.ndarray:
        return array.reshape(out_rows, factor, out_cols, factor)

    valid = blocks(window.valid).all(axis=(1, 3))
    elevation = np.full((out_rows, out_cols), np.nan, dtype=np.float32)
    slope = np.full((out_rows, out_cols), np.nan, dtype=np.float32)
    if valid.any():
        block_elevation = blocks(window.elevation_m.astype(np.float64))
        block_slope = blocks(window.slope_deg.astype(np.float64))
        with np.errstate(invalid="ignore"):
            elevation[valid] = block_elevation.mean(axis=(1, 3))[valid]
            slope[valid] = block_slope.max(axis=(1, 3))[valid]
    # A valid block can still have a NaN slope if a neighbour was missing at native scale.
    valid &= np.isfinite(slope)
    # DemWindow locates coordinates from its edges, so blocks need no global alignment.
    return DemWindow(
        elevation_m=elevation,
        valid=valid,
        slope_deg=slope,
        row_offset=window.row_offset,
        col_offset=window.col_offset,
        pixels_per_degree_x=window.pixels_per_degree_x / factor,
        pixels_per_degree_y=window.pixels_per_degree_y / factor,
        west_edge_deg=window.west_edge_deg,
        north_edge_deg=window.north_edge_deg,
        cell_size_m=window.cell_size_m * factor,
    )


def open_source(dem: str) -> ByteSource:
    if dem.startswith(("https://", "http://")):
        return HttpRangeSource(dem)
    return LocalFileSource(dem)


def process_dem(
    dem: str | Path,
    bounds: GeographicBounds,
    output: Path | str,
    *,
    aggregate: int = DEFAULT_AGGREGATE,
    max_slope_deg: float = DEFAULT_MAX_SLOPE_DEG,
    name: str = DEFAULT_NAME,
    save_raw: Optional[Path | str] = None,
    source: Optional[ByteSource] = None,
    max_cells: int = MAX_WINDOW_CELLS,
    horizon_radius_m: Optional[float] = DEFAULT_HORIZON_RADIUS_M,
    azimuths: int = DEFAULT_AZIMUTHS,
) -> dict[str, Any]:
    """Process one window and write a new JSON grid (existing files are never replaced).

    `horizon_radius_m=None` skips the modelled radiation layer; otherwise that
    radius is also read as margin around the window so horizons see beyond it.
    """
    if horizon_radius_m is not None and (
        not math.isfinite(horizon_radius_m) or horizon_radius_m <= 0
    ):
        raise ValueError("horizon_radius_m debe ser positivo o None.")
    output_path = Path(output)
    if output_path.exists():
        raise FileExistsError(f"El destino ya existe y no se sobrescribe: {output_path}")
    if save_raw is not None and Path(save_raw).exists():
        raise FileExistsError(f"El recorte crudo ya existe y no se sobrescribe: {save_raw}")
    dem_text = str(dem)
    byte_source = source if source is not None else open_source(dem_text)
    try:
        reader = GeoTiffReader(byte_source)
        pixel_window = reader.pixel_window(bounds, align=aggregate)
        margin = 1
        if horizon_radius_m is not None:
            margin = max(1, math.ceil(horizon_radius_m / reader.cell_size_m))
        clip = reader.read_raw(pixel_window, margin=margin, max_cells=max_cells)
        native = reader.to_mola_window(clip, pixel_window, bounds)
    finally:
        close = getattr(byte_source, "close", None)
        if callable(close):
            close()
    window = aggregate_window(native, aggregate)

    cell_layers: dict[str, Any] = {}
    radiation_model: Optional[dict[str, Any]] = None
    if horizon_radius_m is not None:
        clip_valid = np.ones(clip.values.shape, dtype=np.bool_)
        if reader.nodata is not None:
            clip_valid &= clip.values != reader.nodata
        target = (
            slice(pixel_window.row_start - clip.row_start, pixel_window.row_stop - clip.row_start),
            slice(pixel_window.col_start - clip.col_start, pixel_window.col_stop - clip.col_start),
        )
        sky = compute_sky_view(
            clip.values.astype(np.float64),
            clip_valid,
            north_edge_deg=reader.clip_origin(clip)[1],
            pixels_per_degree_y=reader.pixels_per_degree,
            cell_size_m=reader.cell_size_m,
            body_radius_m=reader.radius_m,
            radius_m=horizon_radius_m,
            azimuths=azimuths,
            target=target,
        )
        svf = block_mean(sky.sky_view_factor, native.valid, aggregate)
        truncated = sky.truncated.reshape(
            window.rows, aggregate, window.cols, aggregate
        ).any(axis=(1, 3))
        cell_layers = {"sky_view_factor": svf, "radiation_modeled": svf}
        radiation_model = radiation_metadata(
            horizon_radius_m=float(horizon_radius_m),
            azimuths=azimuths,
            native_cell_size_m=reader.cell_size_m,
            aggregate=aggregate,
            body_radius_m=reader.radius_m,
            truncated_cells=int((truncated & window.valid).sum()),
        )

    if save_raw is not None:
        clip_west, clip_north = reader.clip_origin(clip)
        write_geotiff_int16(
            save_raw,
            clip.values,
            origin_lon=clip_west,
            origin_lat=clip_north,
            pixel_scale_deg=reader.pixel_scale_deg,
            radius_m=reader.radius_m,
            nodata=reader.nodata,
            citation=reader.citation or "Mars sphere",
        )

    is_url = dem_text.startswith(("https://", "http://"))
    source_metadata: dict[str, Any] = {
        "dataset": HRSC_MOLA_DATASET,
        "page": HRSC_MOLA_PAGE,
        "citation": HRSC_MOLA_CITATION,
        "license": HRSC_MOLA_LICENSE,
        "file": Path(dem_text.split("?", 1)[0]).name,
        "url": dem_text if is_url else None,
        "file_size_bytes": getattr(byte_source, "size", None),
        "last_modified": getattr(byte_source, "last_modified", None),
        "pixel_window": {
            "row_start": pixel_window.row_start,
            "row_stop": pixel_window.row_stop,
            "col_start": pixel_window.col_start,
            "col_stop": pixel_window.col_stop,
        },
        "pixel_scale_deg": reader.pixel_scale_deg,
        "native_cell_size_m": round(reader.cell_size_m, 6),
        "body_radius_m": reader.radius_m,
        "nodata": reader.nodata,
        "requested_bounds": {
            "south": bounds.south, "north": bounds.north,
            "west": bounds.west, "east": bounds.east,
        },
    }
    aggregation = {
        "factor": aggregate,
        "elevation_m": "media de los píxeles del bloque",
        "slope_deg": "máximo de las pendientes nativas del bloque",
        "valid": "todos los píxeles del bloque son válidos",
    }
    extra: dict[str, Any] = {"source": source_metadata, "aggregation": aggregation}
    if radiation_model is not None:
        aggregation["sky_view_factor"] = "media de los píxeles del bloque"
        extra["radiation_available"] = True
        extra["radiation_model"] = radiation_model
    grid = build_grid(
        window,
        max_slope_deg=max_slope_deg,
        name=name,
        source_product=Path(source_metadata["file"]).stem,
        disclaimer=dem_disclaimer(
            window.cell_size_m, aggregate, radiation=radiation_model is not None
        ),
        extra=extra,
        cell_layers=cell_layers,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(grid, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with output_path.open("x", encoding="utf-8") as stream:
        stream.write(rendered)
    return grid


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dem", required=True, help="Ruta local o URL https del GeoTIFF.")
    parser.add_argument(
        "--bounds", nargs=4, type=float, required=True,
        metavar=("SUR", "NORTE", "OESTE", "ESTE"),
        help="Grados: latitud planetocéntrica y longitud positiva este (0–360).",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--aggregate", type=int, default=DEFAULT_AGGREGATE,
                        help="Píxeles por lado de cada celda de salida (1 = nativa).")
    parser.add_argument("--max-slope-deg", type=float, default=DEFAULT_MAX_SLOPE_DEG)
    parser.add_argument("--name", default=DEFAULT_NAME)
    parser.add_argument("--horizon-radius-km", type=float,
                        default=DEFAULT_HORIZON_RADIUS_M / 1000.0,
                        help="Radio de búsqueda del horizonte para la radiación MODELADA "
                             "(también margen de lectura); 0 la desactiva.")
    parser.add_argument("--azimuths", type=int, default=DEFAULT_AZIMUTHS)
    parser.add_argument("--save-raw", type=Path,
                        help="Guarda el recorte crudo (GeoTIFF pequeño) para reprocesar sin red.")
    args = parser.parse_args()
    bounds = GeographicBounds.from_sequence(tuple(args.bounds))
    grid = process_dem(
        args.dem, bounds, args.output,
        aggregate=args.aggregate, max_slope_deg=args.max_slope_deg,
        name=args.name, save_raw=args.save_raw,
        horizon_radius_m=args.horizon_radius_km * 1000.0 if args.horizon_radius_km > 0 else None,
        azimuths=args.azimuths,
    )
    cells = grid["cells"]
    valid = sum(1 for cell in cells if cell["valid"])
    blocked = sum(1 for cell in cells if cell["blocked"])
    slopes = [cell["slope_deg"] for cell in cells if cell["valid"]]
    print(
        f"DEM procesado: {grid['grid']['rows']} x {grid['grid']['cols']} celdas de "
        f"{grid['grid']['cell_size_m']:.1f} m -> {args.output}\n"
        f"Válidas: {valid}/{len(cells)} · bloqueadas: {blocked} · "
        f"pendiente máx.: {max(slopes) if slopes else 'n/d'}°"
    )
    sky = [cell["sky_view_factor"] for cell in cells if "sky_view_factor" in cell]
    if sky:
        print(
            f"Cielo visible (MODELADO): {min(sky):.4f} a {max(sky):.4f} · celdas con "
            f"horizonte truncado: {grid['radiation_model']['truncated_cells']}"
        )


if __name__ == "__main__":
    main()
