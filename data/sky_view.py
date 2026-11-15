"""Horizon angles and sky-view factor from a geographic DEM (NumPy only).

Used by the MODELLED radiation layer (see docs/FUENTES_DE_DATOS.md). For each
target pixel and each of `azimuths` directions, a ray is marched outwards in
steps of one north-south pixel up to `radius_m`. The horizon angle is the
maximum elevation angle of the terrain along the ray:

    H = max_k atan((z_k - z_0 - d_k² / (2 R)) / d_k)

where d_k is the horizontal distance in metres and d²/2R lowers distant
terrain for the curvature of a spherical body of radius R. Samples are taken
at the nearest pixel; pixels without data or outside the array do not block.

The sky-view factor is the fraction of the hemisphere's solid angle that is
not hidden by terrain, assuming an isotropic sky:

    SVF = mean over azimuths of (1 - sin(max(H, 0)))

A horizontal plane gives exactly 1; a pit gives less. Negative horizons (a
summit sees below the horizontal) are clipped to 0, so SVF never exceeds 1.

This is the author's hypothesis for a relative shielding index, not a dose
model: it ignores atmospheric attenuation with zenith angle (which makes the
effect of low horizons smaller than SVF suggests), albedo radiation from the
ground and the change of atmospheric column with elevation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

DEFAULT_AZIMUTHS = 32
DEFAULT_HORIZON_RADIUS_M = 10_000.0


@dataclass(frozen=True)
class SkyView:
    """Per-target-pixel results; NaN where the target pixel is invalid."""

    sky_view_factor: NDArray[np.float64]
    max_horizon_deg: NDArray[np.float64]
    # True where at least one ray left the array before reaching `radius_m`.
    truncated: NDArray[np.bool_]


def compute_sky_view(
    elevation_m: NDArray[np.floating],
    valid: NDArray[np.bool_],
    *,
    north_edge_deg: float,
    pixels_per_degree_y: float,
    cell_size_m: float,
    body_radius_m: float,
    radius_m: float = DEFAULT_HORIZON_RADIUS_M,
    azimuths: int = DEFAULT_AZIMUTHS,
    target: tuple[slice, slice] | None = None,
) -> SkyView:
    """Sky-view factor of the pixels in `target` (default: the whole array).

    `elevation_m`/`valid` may include a margin around `target` so that rays
    from the target pixels see terrain beyond it. `north_edge_deg` is the
    latitude of the array's top edge; `cell_size_m` is the north-south pixel
    size. East-west pixel size shrinks with cos(latitude) row by row.
    """
    elevation = np.asarray(elevation_m, dtype=np.float64)
    valid_mask = np.asarray(valid, dtype=np.bool_)
    if elevation.ndim != 2 or elevation.shape != valid_mask.shape:
        raise ValueError("La elevación y la máscara de validez deben ser 2D y del mismo tamaño.")
    for name, value in (("cell_size_m", cell_size_m), ("body_radius_m", body_radius_m),
                        ("radius_m", radius_m), ("pixels_per_degree_y", pixels_per_degree_y)):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} debe ser un número positivo.")
    if isinstance(azimuths, bool) or not isinstance(azimuths, int) or azimuths < 4:
        raise ValueError("azimuths debe ser un entero >= 4.")

    rows, cols = elevation.shape
    row_slice, col_slice = target if target is not None else (slice(0, rows), slice(0, cols))
    r_idx = np.arange(rows)[row_slice]
    c_idx = np.arange(cols)[col_slice]
    if r_idx.size == 0 or c_idx.size == 0:
        raise ValueError("La zona objetivo está vacía.")
    target_rows, target_cols = np.meshgrid(r_idx, c_idx, indexing="ij")

    z0 = elevation[target_rows, target_cols]
    target_valid = valid_mask[target_rows, target_cols] & np.isfinite(z0)
    # Invalid samples never block: give them -inf so they cannot raise the horizon.
    blocking = np.where(valid_mask & np.isfinite(elevation), elevation, -np.inf)

    latitude = north_edge_deg - (target_rows + 0.5) / pixels_per_degree_y
    dx_m = cell_size_m * np.cos(np.radians(latitude))  # east-west pixel size per target
    if np.any(dx_m <= 0):
        raise ValueError("La ventana toca un polo: el tamaño este-oeste del píxel es nulo.")
    steps = int(radius_m // cell_size_m)
    if steps < 1:
        raise ValueError("radius_m debe ser al menos el tamaño de un píxel.")

    sum_visible = np.zeros(z0.shape, dtype=np.float64)
    max_horizon = np.full(z0.shape, -math.pi / 2, dtype=np.float64)
    truncated = np.zeros(z0.shape, dtype=np.bool_)
    for k in range(azimuths):
        azimuth = 2.0 * math.pi * k / azimuths  # 0 = north, clockwise
        north, east = math.cos(azimuth), math.sin(azimuth)
        horizon = np.full(z0.shape, -math.pi / 2, dtype=np.float64)
        left = np.zeros(z0.shape, dtype=np.bool_)
        for step in range(1, steps + 1):
            distance = step * cell_size_m
            sample_rows = target_rows + int(round(-distance * north / cell_size_m))
            sample_cols = target_cols + np.rint(distance * east / dx_m).astype(np.int64)
            inside = ((sample_rows >= 0) & (sample_rows < rows)
                      & (sample_cols >= 0) & (sample_cols < cols))
            left |= ~inside
            if not inside.any():
                break
            z = np.full(z0.shape, -np.inf)
            z[inside] = blocking[sample_rows[inside], sample_cols[inside]]
            drop = distance * distance / (2.0 * body_radius_m)
            with np.errstate(invalid="ignore"):
                angle = np.arctan((z - z0 - drop) / distance)
            np.fmax(horizon, angle, out=horizon)
        truncated |= left
        np.fmax(max_horizon, horizon, out=max_horizon)
        sum_visible += 1.0 - np.sin(np.clip(horizon, 0.0, math.pi / 2))

    svf = sum_visible / azimuths
    svf[~target_valid] = np.nan
    max_horizon_deg = np.degrees(max_horizon)
    max_horizon_deg[~target_valid] = np.nan
    return SkyView(sky_view_factor=svf, max_horizon_deg=max_horizon_deg,
                   truncated=truncated & target_valid)


def block_mean(values: NDArray[np.floating], valid: NDArray[np.bool_],
               factor: int) -> NDArray[np.float64]:
    """Mean of `factor` × `factor` blocks; NaN unless every pixel is valid and finite."""
    if isinstance(factor, bool) or not isinstance(factor, int) or factor < 1:
        raise ValueError("El factor de agregación debe ser un entero positivo.")
    array = np.asarray(values, dtype=np.float64)
    rows, cols = array.shape
    if rows % factor or cols % factor:
        raise ValueError("La ventana debe ser múltiplo del factor de agregación.")
    ok = np.asarray(valid, dtype=np.bool_) & np.isfinite(array)
    shape = (rows // factor, factor, cols // factor, factor)
    all_ok = ok.reshape(shape).all(axis=(1, 3))
    filled = np.where(ok, array, 0.0).reshape(shape).mean(axis=(1, 3))
    return np.where(all_ok, filled, np.nan)
