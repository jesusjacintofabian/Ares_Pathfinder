"""Pruebas del ángulo de horizonte y del factor de cielo visible con rasters diminutos."""

import math

import numpy as np
import pytest

from data.sky_view import block_mean, compute_sky_view

CELL = 100.0
MARS_RADIUS = 3_396_190.0
PPD = MARS_RADIUS * math.pi / 180.0 / CELL  # píxeles por grado para celdas de 100 m


def sky(elevation, valid=None, **kwargs):
    elevation = np.asarray(elevation, dtype=np.float64)
    if valid is None:
        valid = np.ones(elevation.shape, dtype=bool)
    options = dict(north_edge_deg=0.0, pixels_per_degree_y=PPD, cell_size_m=CELL,
                   body_radius_m=MARS_RADIUS, radius_m=2_000.0)
    options.update(kwargs)
    return compute_sky_view(elevation, valid, **options)


def distance_px(size):
    rows, cols = np.indices((size, size))
    center = size // 2
    return np.hypot(rows - center, cols - center), center


def test_open_plane_sees_the_whole_sky():
    result = sky(np.full((25, 25), -4500.0))
    assert np.all(result.sky_view_factor == 1.0)
    # La curvatura hace que el horizonte de un plano quede por debajo de la horizontal.
    assert np.all(result.max_horizon_deg < 0.0)


def test_deep_pit_sees_less_sky_than_the_plane():
    dist, c = distance_px(41)
    elevation = np.where(dist <= 5, -1000.0, 0.0)  # pozo de 500 m de radio y 1 km de hondo
    result = sky(elevation)
    center = result.sky_view_factor[c, c]
    # Pared entre 500 y 700 m del centro según el acimut (muestreo al píxel más cercano).
    assert 1 - math.sin(math.atan2(1000, 500)) <= center <= 1 - math.sin(math.atan2(1000, 700))
    assert center < 0.5
    assert result.sky_view_factor[0, 0] == 1.0  # el borde del raster es llano y abierto


def test_isolated_summit_sees_the_whole_sky():
    dist, c = distance_px(31)
    elevation = 2000.0 - 100.0 * dist  # cono
    result = sky(elevation)
    assert result.sky_view_factor[c, c] == 1.0
    assert result.sky_view_factor[c, c + 3] < 1.0  # en la ladera, la cima tapa parte del cielo


def test_curvature_lowers_distant_terrain():
    elevation = np.zeros((61, 11))
    elevation[0, :] = 100.0  # muro 50 píxeles (5 km) al norte del punto (50, 5)
    radius = 1_000_000.0  # cuerpo pequeño para que la caída d²/2R se note: 12,5 m
    result = sky(elevation, body_radius_m=radius, radius_m=6_000.0,
                 target=(slice(50, 51), slice(5, 6)))
    expected = math.degrees(math.atan((100.0 - 5000.0 ** 2 / (2 * radius)) / 5000.0))
    assert result.max_horizon_deg[0, 0] == pytest.approx(expected, abs=1e-9)


def test_pixels_without_data_do_not_block_and_invalid_targets_are_nan():
    dist, c = distance_px(21)
    elevation = np.where(dist <= 3, 0.0, 5000.0)
    valid = dist <= 3  # todo lo alto es «sin datos»
    valid[0, 0] = True
    elevation[0, 0] = np.nan  # válido pero no finito: tampoco cuenta
    result = sky(elevation, valid)
    assert result.sky_view_factor[c, c] == 1.0
    assert np.isnan(result.sky_view_factor[c, c + 5])
    assert np.isnan(result.sky_view_factor[0, 0])


def test_margin_outside_target_is_used_and_truncation_is_reported():
    elevation = np.zeros((30, 30))
    elevation[:, 25:] = 1000.0  # meseta en el margen, a 1 km al este del objetivo
    target = (slice(10, 20), slice(10, 20))
    result = sky(elevation, target=target)
    assert result.sky_view_factor.shape == (10, 10)
    assert np.all(result.sky_view_factor < 1.0)
    assert result.truncated.all()  # el radio (2 km) sale de un raster de 3 km
    wide = sky(np.zeros((61, 61)), target=(slice(30, 31), slice(30, 31)))
    assert not wide.truncated.any()


def test_east_west_spacing_follows_latitude():
    # A 60° de latitud un píxel mide 50 m de este a oeste: la pared a 10 columnas está a 500 m.
    elevation = np.zeros((5, 41))
    elevation[:, 30] = 500.0
    lat60 = sky(elevation, north_edge_deg=60.0 + 2.5 / PPD, radius_m=1_500.0,
                target=(slice(2, 3), slice(20, 21)))
    assert lat60.max_horizon_deg[0, 0] == pytest.approx(45.0, abs=0.5)


@pytest.mark.parametrize("kwargs, message", [
    ({"cell_size_m": 0.0}, "cell_size_m"),
    ({"radius_m": -1.0}, "radius_m"),
    ({"radius_m": 50.0}, "al menos"),
    ({"azimuths": 2}, "azimuths"),
    ({"target": (slice(3, 3), slice(0, 2))}, "vacía"),
])
def test_invalid_parameters_are_rejected(kwargs, message):
    with pytest.raises(ValueError, match=message):
        sky(np.zeros((4, 4)), **kwargs)


def test_block_mean_requires_all_pixels_valid():
    values = np.arange(16, dtype=float).reshape(4, 4)
    valid = np.ones((4, 4), dtype=bool)
    valid[3, 3] = False
    means = block_mean(values, valid, 2)
    assert means[0, 0] == pytest.approx((0 + 1 + 4 + 5) / 4)
    assert np.isnan(means[1, 1])
    with pytest.raises(ValueError, match="múltiplo"):
        block_mean(values[:3], valid[:3], 2)
