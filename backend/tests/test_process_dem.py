"""Pruebas del lector GeoTIFF y de process_dem con rasters diminutos generados aquí.

Ninguna prueba accede a la red: la lectura por rangos HTTP usa una conexión simulada.
"""

import json
import math
from pathlib import Path

import numpy as np
import pytest

from app.services.map_service import _load_mola_dataset
from data.geotiff_reader import (
    TAG_BITS_PER_SAMPLE,
    TAG_COMPRESSION,
    TAG_GEO_KEY_DIRECTORY,
    TAG_SAMPLE_FORMAT,
    TAG_SAMPLES_PER_PIXEL,
    TAG_TILE_WIDTH,
    GeoTiffError,
    GeoTiffReader,
    HttpRangeSource,
    LocalFileSource,
    write_geotiff_int16,
)
from data.mola_reader import GeographicBounds, MolaWindow
from data.process_dem import aggregate_window, process_dem

RADIUS = 3_396_190.0
SCALE = 0.1  # grados por píxel: celdas de ~5,9 km, suficiente para probar la geometría
ORIGIN_LON, ORIGIN_LAT = 137.0, -4.0
CELL = RADIUS * math.radians(SCALE)


def make_dem(tmp_path: Path, values: np.ndarray | None = None, name: str = "dem.tif",
             **kwargs) -> Path:
    if values is None:
        values = np.arange(10 * 12, dtype=np.int16).reshape(10, 12) * 10 - 4000
    options = dict(origin_lon=ORIGIN_LON, origin_lat=ORIGIN_LAT,
                   pixel_scale_deg=SCALE, radius_m=RADIUS)
    options.update(kwargs)
    return write_geotiff_int16(tmp_path / name, values, **options)


def dataset_disclaimer(path: Path) -> str:
    return _load_mola_dataset(path).disclaimer


def open_reader(path: Path) -> GeoTiffReader:
    return GeoTiffReader(LocalFileSource(path))


# ----------------------------------------------------------------- parsing
@pytest.mark.parametrize("bigtiff", [False, True])
@pytest.mark.parametrize("byteorder", ["<", ">"])
def test_reader_parses_classic_and_bigtiff_in_both_byte_orders(tmp_path, bigtiff, byteorder):
    path = make_dem(tmp_path, bigtiff=bigtiff, byteorder=byteorder)
    reader = open_reader(path)
    assert reader.bigtiff is bigtiff
    assert (reader.width, reader.height) == (12, 10)
    assert reader.origin_lon == pytest.approx(ORIGIN_LON)
    assert reader.origin_lat == pytest.approx(ORIGIN_LAT)
    assert reader.pixel_scale_deg == pytest.approx(SCALE)
    assert reader.radius_m == RADIUS
    assert reader.nodata == -32768
    assert reader.cell_size_m == pytest.approx(CELL)


def test_multi_row_strips_are_read_correctly(tmp_path):
    values = np.arange(10 * 12, dtype=np.int16).reshape(10, 12)
    path = make_dem(tmp_path, values, rows_per_strip=4)
    reader = open_reader(path)
    window = reader.pixel_window(GeographicBounds(-4.95, -4.05, 137.05, 138.15))
    clip = reader.read_raw(window)
    np.testing.assert_array_equal(clip.values, values[0:10, 0:12])


@pytest.mark.parametrize(
    ("overrides", "drop", "message"),
    [
        ({TAG_COMPRESSION: (3, 5)}, set(), "Compresión"),
        ({TAG_SAMPLE_FORMAT: (3, 3), TAG_BITS_PER_SAMPLE: (3, 32)}, set(), "BitsPerSample"),
        ({TAG_SAMPLES_PER_PIXEL: (3, 3)}, set(), "una sola banda"),
        ({TAG_TILE_WIDTH: (3, 16)}, set(), "teselas"),
        ({}, {TAG_GEO_KEY_DIRECTORY}, "georreferenciado"),
        ({TAG_GEO_KEY_DIRECTORY: (3, [1, 1, 0, 1, 1024, 0, 1, 1])}, set(), "geográficos"),
        ({TAG_GEO_KEY_DIRECTORY: (3, [1, 1, 0, 2, 1024, 0, 1, 2, 2054, 0, 1, 9102])},
         set(), "semieje mayor"),
    ],
)
def test_unsupported_files_are_rejected_with_clear_errors(tmp_path, overrides, drop, message):
    path = make_dem(tmp_path, tag_overrides=overrides, drop_tags=drop)
    with pytest.raises(GeoTiffError, match=message):
        open_reader(path)


def test_non_spherical_body_is_rejected(tmp_path):
    path = make_dem(tmp_path, tag_overrides={34736: (12, [RADIUS, RADIUS - 20_000.0, 0.0])})
    with pytest.raises(GeoTiffError, match="esférico"):
        open_reader(path)


def test_writer_never_overwrites_by_default(tmp_path):
    path = make_dem(tmp_path)
    with pytest.raises(FileExistsError):
        make_dem(tmp_path)
    assert path.is_file()


# ------------------------------------------------------------------ window
def test_window_crop_matches_source_pixels_and_centers(tmp_path):
    values = np.arange(10 * 12, dtype=np.int16).reshape(10, 12)
    reader = open_reader(make_dem(tmp_path, values))
    bounds = GeographicBounds(-4.35, -4.05, 137.25, 137.65)
    window = reader.read_window(bounds)
    np.testing.assert_array_equal(window.elevation_m, values[0:4, 2:7].astype(np.float32))
    assert (window.rows, window.cols) == (4, 5)
    latitude, longitude = window.index_to_coordinate(0, 0)
    assert latitude == pytest.approx(-4.05)
    assert longitude == pytest.approx(137.25)
    assert window.coordinate_to_index(-4.25, 137.55) == (2, 3)
    assert window.bounds.north == pytest.approx(-4.0)
    assert window.bounds.west == pytest.approx(137.2)


def test_western_hemisphere_file_is_addressed_with_positive_east_longitudes(tmp_path):
    values = np.arange(10 * 12, dtype=np.int16).reshape(10, 12)
    reader = open_reader(make_dem(tmp_path, values, origin_lon=-70.0))
    window = reader.read_window(GeographicBounds(-4.35, -4.05, 290.25, 290.65))
    np.testing.assert_array_equal(window.elevation_m, values[0:4, 2:7].astype(np.float32))
    assert window.index_to_coordinate(0, 0)[1] == pytest.approx(290.25)
    assert window.coordinate_to_index(-4.25, 290.55) == (2, 3)


def test_window_outside_coverage_is_rejected(tmp_path):
    reader = open_reader(make_dem(tmp_path))
    with pytest.raises(GeoTiffError, match="longitud"):
        reader.pixel_window(GeographicBounds(-4.5, -4.1, 136.5, 137.5))
    with pytest.raises(GeoTiffError, match="latitud"):
        reader.pixel_window(GeographicBounds(-4.5, -3.5, 137.1, 137.5))


def test_alignment_extends_window_south_east_to_multiples_of_factor(tmp_path):
    reader = open_reader(make_dem(tmp_path))
    window = reader.read_window(GeographicBounds(-4.75, -4.25, 137.25, 137.85), align=3)
    assert (window.rows, window.cols) == (6, 9)
    assert (window.row_offset, window.col_offset) == (2, 2)
    assert window.index_to_coordinate(0, 0) == pytest.approx((-4.25, 137.25))


def test_grid_not_aligned_with_zero_meridian_is_supported(tmp_path):
    # El DEM real del USGS cubre 359,998°: su malla no cae en 0°E.
    values = np.arange(10 * 12, dtype=np.int16).reshape(10, 12)
    reader = open_reader(make_dem(tmp_path, values, origin_lon=137.0337, origin_lat=-4.0123))
    window = reader.read_window(GeographicBounds(-4.4, -4.1, 137.3, 137.7))
    first_lat, first_lon = window.index_to_coordinate(0, 0)
    assert first_lat == pytest.approx(-4.0123 - 0.5 * SCALE)
    assert first_lon == pytest.approx(137.0337 + 2.5 * SCALE)
    for row in range(window.rows):
        for col in range(window.cols):
            assert window.coordinate_to_index(*window.index_to_coordinate(row, col)) == (row, col)
    assert window.elevation_at(first_lat, first_lon) == float(values[0, 2])


def test_margin_is_read_but_clipped_at_file_edges(tmp_path):
    reader = open_reader(make_dem(tmp_path))
    inner = reader.pixel_window(GeographicBounds(-4.55, -4.25, 137.35, 137.65))
    clip = reader.read_raw(inner, margin=1)
    assert clip.values.shape == (inner.rows + 2, inner.cols + 2)
    edge = reader.pixel_window(GeographicBounds(-4.25, -4.0, 137.0, 137.25))
    clip = reader.read_raw(edge, margin=1)
    assert (clip.row_start, clip.col_start) == (0, 0)
    assert clip.values.shape == (edge.rows + 1, edge.cols + 1)


def test_window_larger_than_limit_is_rejected(tmp_path):
    reader = open_reader(make_dem(tmp_path))
    window = reader.pixel_window(GeographicBounds(-4.95, -4.05, 137.05, 138.15))
    with pytest.raises(GeoTiffError, match="máximo"):
        reader.read_raw(window, max_cells=50)


# ------------------------------------------------------------------- slope
def test_slope_of_known_north_south_plane(tmp_path):
    rise_per_row = 593  # metros
    values = (np.arange(10)[:, None] * -rise_per_row + np.zeros((10, 12))).astype(np.int16)
    reader = open_reader(make_dem(tmp_path, values))
    window = reader.read_window(GeographicBounds(-4.95, -4.05, 137.05, 138.15))
    expected = math.degrees(math.atan(rise_per_row / CELL))
    np.testing.assert_allclose(window.slope_deg, expected, rtol=1e-4)


def test_slope_of_known_east_west_plane_uses_latitude(tmp_path):
    rise_per_col = 400
    values = (np.arange(12)[None, :] * rise_per_col + np.zeros((10, 12))).astype(np.int16)
    reader = open_reader(make_dem(tmp_path, values))
    window = reader.read_window(GeographicBounds(-4.95, -4.05, 137.05, 138.15))
    for row in range(window.rows):
        latitude = window.index_to_coordinate(row, 0)[0]
        expected = math.degrees(math.atan(rise_per_col / (CELL * math.cos(math.radians(latitude)))))
        np.testing.assert_allclose(window.slope_deg[row], expected, rtol=1e-4)


def test_nodata_pixels_are_invalid_and_blocked(tmp_path):
    values = np.full((10, 12), -4000, dtype=np.int16)
    values[5, 6] = -32768
    reader = open_reader(make_dem(tmp_path, values))
    window = reader.read_window(GeographicBounds(-4.95, -4.05, 137.05, 138.15))
    assert not window.valid[5, 6]
    assert np.isnan(window.slope_deg[5, 6])
    assert window.valid.sum() == 10 * 12 - 1
    assert np.isfinite(window.slope_deg[window.valid]).all()


# ------------------------------------------------------------- aggregation
def make_window(elevation: np.ndarray, slope: np.ndarray, valid: np.ndarray) -> MolaWindow:
    return MolaWindow(
        elevation_m=elevation.astype(np.float32), valid=valid,
        slope_deg=slope.astype(np.float32), row_offset=3, col_offset=6,
        pixels_per_degree_x=10.0, pixels_per_degree_y=10.0,
        west_edge_deg=0.6, north_edge_deg=89.7, cell_size_m=200.0,
    )


def test_aggregation_uses_mean_elevation_max_slope_and_all_valid():
    elevation = np.arange(36, dtype=np.float64).reshape(6, 6)
    slope = np.zeros((6, 6))
    slope[1, 1] = 12.5
    slope[4, 5] = 7.0
    valid = np.ones((6, 6), dtype=bool)
    valid[3, 0] = False
    slope[3, 0] = np.nan
    coarse = aggregate_window(make_window(elevation, slope, valid), 3)
    assert (coarse.rows, coarse.cols) == (2, 2)
    assert coarse.elevation_m[0, 0] == pytest.approx(elevation[0:3, 0:3].mean())
    assert coarse.slope_deg[0, 0] == pytest.approx(12.5)
    assert coarse.slope_deg[1, 1] == pytest.approx(7.0)
    assert not coarse.valid[1, 0] and np.isnan(coarse.elevation_m[1, 0])
    assert coarse.valid.sum() == 3
    assert coarse.cell_size_m == pytest.approx(600.0)
    assert coarse.index_to_coordinate(0, 0) == pytest.approx((89.55, 0.75))
    assert coarse.coordinate_to_index(89.35, 0.95) == (1, 1)


def test_aggregation_rejects_unaligned_windows():
    window = make_window(np.zeros((5, 6)), np.zeros((5, 6)), np.ones((5, 6), dtype=bool))
    with pytest.raises(ValueError, match="múltiplo"):
        aggregate_window(window, 3)


# -------------------------------------------------------------- HTTP ranges
class FakeResponse:
    def __init__(self, status, headers, body=b""):
        self.status, self._headers, self._body = status, headers, body

    def read(self):
        return self._body

    def getheaders(self):
        return list(self._headers.items())

    def getheader(self, name, default=None):
        return self._headers.get(name, default)


class FakeServer:
    """Simulates a redirecting host and a byte-range server for one file."""

    def __init__(self, data: bytes, honour_ranges: bool = True):
        self.data, self.honour_ranges = data, honour_ranges
        self.ranges: list[tuple[int, int]] = []

    def connect(self, host):
        server = self

        class Connection:
            def request(self, method, path, headers):
                self.method, self.path, self.headers = method, path, headers

            def getresponse(self):
                if host == "redirect.example":
                    return FakeResponse(302, {"Location": "https://files.example/dem.tif"})
                if self.method == "HEAD":
                    return FakeResponse(200, {"Accept-Ranges": "bytes",
                                              "Content-Length": str(len(server.data)),
                                              "Last-Modified": "Wed, 09 Nov 2022 14:59:19 GMT"})
                if not server.honour_ranges:
                    return FakeResponse(200, {}, server.data)
                start, stop = (int(v) for v in self.headers["Range"][6:].split("-"))
                server.ranges.append((start, stop))
                return FakeResponse(
                    206, {"Content-Range": f"bytes {start}-{stop}/{len(server.data)}"},
                    server.data[start:stop + 1])

            def close(self):
                pass

        return Connection()


def test_http_range_source_reads_only_the_window(tmp_path):
    values = np.arange(10 * 12, dtype=np.int16).reshape(10, 12)
    path = make_dem(tmp_path, values, bigtiff=True)
    server = FakeServer(path.read_bytes())
    source = HttpRangeSource("https://redirect.example/dem.tif",
                             connection_factory=server.connect, retries=1)
    assert source.url == "https://files.example/dem.tif"
    assert source.last_modified == "Wed, 09 Nov 2022 14:59:19 GMT"
    reader = GeoTiffReader(source)
    bounds = GeographicBounds(-4.35, -4.05, 137.25, 137.65)
    window = reader.read_window(bounds, margin=0)
    np.testing.assert_array_equal(window.elevation_m, values[0:4, 2:7].astype(np.float32))
    pixel_reads = [r for r in server.ranges if r[1] - r[0] + 1 == 5 * 2]
    assert len(pixel_reads) == 4  # una petición por fila, solo las columnas pedidas
    assert source.bytes_read < len(server.data)


def test_http_range_source_rejects_servers_that_ignore_ranges(tmp_path):
    server = FakeServer(make_dem(tmp_path).read_bytes(), honour_ranges=False)
    source = HttpRangeSource("https://files.example/dem.tif",
                             connection_factory=server.connect, retries=1)
    with pytest.raises(GeoTiffError, match="206"):
        source.read(0, 16)


def test_http_range_source_requires_https():
    with pytest.raises(GeoTiffError, match="https"):
        HttpRangeSource("http://files.example/dem.tif", connection_factory=lambda host: None)


# ------------------------------------------------------------- process_dem
def test_process_dem_writes_loadable_grid_and_reproducible_raw_clip(tmp_path):
    rng = np.random.default_rng(7)
    values = (rng.normal(-4000, 300, (10, 12))).astype(np.int16)
    values[5, 4] = -32768
    dem = make_dem(tmp_path, values)
    bounds = GeographicBounds(-4.75, -4.25, 137.15, 137.95)
    output = tmp_path / "out" / "grid.json"
    raw = tmp_path / "raw" / "clip.tif"
    grid = process_dem(dem, bounds, output, aggregate=3, save_raw=raw, name="Prueba")

    stored = json.loads(output.read_text(encoding="utf-8"))
    assert stored == grid
    assert stored["data_source"] == "mola" and stored["is_simulated"] is False
    assert stored["name"] == "Prueba"
    assert stored["source_product"] == "dem"
    assert stored["aggregation"]["factor"] == 3
    assert "resolución de planificación, no de navegación" in stored["disclaimer"]
    assert "Fergason, Hare y Laura (2018)" in stored["disclaimer"]
    assert dataset_disclaimer(output) == stored["disclaimer"]
    assert stored["source"]["pixel_window"] == {
        "row_start": 2, "row_stop": 8, "col_start": 1, "col_stop": 10,
    }
    rows, cols = stored["grid"]["rows"], stored["grid"]["cols"]
    assert len(stored["cells"]) == rows * cols
    assert stored["grid"]["cell_size_m"] == pytest.approx(3 * CELL, rel=1e-6)
    region = stored["region"]
    assert region["south"] <= bounds.south and region["north"] >= bounds.north
    assert region["west"] <= bounds.west and region["east"] >= bounds.east
    assert any(not cell["valid"] and cell["blocked"] for cell in stored["cells"])

    dataset = _load_mola_dataset(output)
    assert (dataset.grid.rows, dataset.grid.cols) == (rows, cols)

    again = process_dem(raw, bounds, tmp_path / "again.json", aggregate=3)
    assert again["cells"] == grid["cells"]
    assert again["region"] == grid["region"]


def test_process_dem_never_overwrites(tmp_path):
    dem = make_dem(tmp_path)
    output = tmp_path / "grid.json"
    output.write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError):
        process_dem(dem, GeographicBounds(-4.85, -4.15, 137.15, 137.95), output)
    assert output.read_text(encoding="utf-8") == "{}"


# ------------------------------------------------- radiación MODELADA (F3)
FINE = 0.002  # grados por píxel: ~118 m, para que un horizonte de 1 km abarque varios píxeles
FINE_CELL = RADIUS * math.radians(FINE)


def fine_dem(tmp_path: Path, values: np.ndarray) -> Path:
    return make_dem(tmp_path, values.astype(np.int16), name="fine.tif", pixel_scale_deg=FINE)


def fine_bounds(row0: int, row1: int, col0: int, col1: int) -> GeographicBounds:
    """Bounds of file pixels [row0, row1) × [col0, col1) of `fine_dem`."""
    return GeographicBounds(
        ORIGIN_LAT - row1 * FINE + 1e-7, ORIGIN_LAT - row0 * FINE - 1e-7,
        ORIGIN_LON + col0 * FINE + 1e-7, ORIGIN_LON + col1 * FINE - 1e-7,
    )


def test_process_dem_adds_modelled_radiation_layer(tmp_path):
    values = np.full((30, 30), -4500)
    values[12:15, 12:15] = -5500  # pozo de 3 × 3 píxeles y 1 km de hondo, en el bloque central
    dem = fine_dem(tmp_path, values)
    output = tmp_path / "grid.json"
    grid = process_dem(dem, fine_bounds(9, 18, 9, 18), output, aggregate=3,
                       horizon_radius_m=1_000.0)
    assert (grid["grid"]["rows"], grid["grid"]["cols"]) == (3, 3)
    assert grid["radiation_available"] is True
    model = grid["radiation_model"]
    assert model["label"] == "MODELADO"
    assert model["index_formula"] == "radiation_modeled = sky_view_factor"
    assert model["truncated_cells"] == 0  # el margen (1 km) cabe en el archivo
    assert model["anchor"]["doi"] == "10.1126/science.1244797"
    unverified = model["anchor"]["unverified_values"]
    assert unverified["verification_status"] == "no cotejado con el artículo publicado"
    assert unverified["used_in_calculation"] is False
    assert "MODELADA" in grid["disclaimer"]
    assert "no es una medición por celda ni una dosis" in grid["disclaimer"]
    assert "radiación, geología" not in grid["disclaimer"]

    cells = {(cell["row"], cell["col"]): cell for cell in grid["cells"]}
    for cell in cells.values():
        assert cell["radiation_modeled"] == cell["sky_view_factor"]
        assert 0.0 <= cell["sky_view_factor"] <= 1.0
    assert cells[(1, 1)]["sky_view_factor"] < 0.5  # el pozo ve poco cielo
    # Las celdas vecinas ven el pozo por debajo de la horizontal: cielo completo.
    assert cells[(0, 0)]["sky_view_factor"] == 1.0
    dataset = _load_mola_dataset(output)
    assert dataset.payload["radiation_model"]["label"] == "MODELADO"


def test_margin_lets_horizons_see_beyond_the_window(tmp_path):
    values = np.full((30, 30), -4500)
    values[:, 21:] = -3500  # meseta fuera de la ventana pero dentro del radio
    dem = fine_dem(tmp_path, values)
    grid = process_dem(dem, fine_bounds(9, 18, 9, 18), tmp_path / "grid.json", aggregate=3,
                       horizon_radius_m=1_000.0)
    east = [c["sky_view_factor"] for c in grid["cells"] if c["col"] == 2]
    assert all(value < 1.0 for value in east)

    plain = process_dem(dem, fine_bounds(9, 18, 9, 18), tmp_path / "plain.json", aggregate=3,
                        horizon_radius_m=None)
    assert "radiation_model" not in plain and "radiation_available" not in plain
    assert all("sky_view_factor" not in cell for cell in plain["cells"])
    assert "radiación, geología" in plain["disclaimer"]
    assert plain["cells"] == [
        {k: v for k, v in cell.items() if k not in ("sky_view_factor", "radiation_modeled")}
        for cell in grid["cells"]
    ]


def test_horizon_truncated_at_file_edge_is_counted(tmp_path):
    dem = fine_dem(tmp_path, np.full((12, 12), -4500))
    grid = process_dem(dem, fine_bounds(0, 6, 0, 6), tmp_path / "grid.json", aggregate=3,
                       horizon_radius_m=1_000.0)
    assert grid["radiation_model"]["truncated_cells"] == 4
    assert all(cell["sky_view_factor"] == 1.0 for cell in grid["cells"])


def test_invalid_horizon_radius_is_rejected(tmp_path):
    dem = fine_dem(tmp_path, np.full((12, 12), -4500))
    with pytest.raises(ValueError, match="horizon_radius_m"):
        process_dem(dem, fine_bounds(3, 9, 3, 9), tmp_path / "grid.json", aggregate=3,
                    horizon_radius_m=0.0)


def test_build_grid_rejects_layers_with_wrong_shape_or_non_finite_values():
    from data.process_mola import build_grid
    window = aggregate_window(open_reader_window(), 1)
    with pytest.raises(ValueError, match="tamaño"):
        build_grid(window, cell_layers={"sky_view_factor": np.zeros((1, 1))})
    bad = np.zeros((window.rows, window.cols))
    bad[0, 0] = np.nan
    with pytest.raises(ValueError, match="no es finita"):
        build_grid(window, cell_layers={"sky_view_factor": bad})


def open_reader_window() -> MolaWindow:
    elevation = np.zeros((3, 3), dtype=np.float32)
    return MolaWindow(
        elevation_m=elevation, valid=np.ones((3, 3), dtype=bool),
        slope_deg=np.zeros((3, 3), dtype=np.float32), row_offset=0, col_offset=0,
        pixels_per_degree_x=10.0, pixels_per_degree_y=10.0,
        west_edge_deg=137.0, north_edge_deg=-4.0, cell_size_m=CELL,
    )
