"""Pruebas MOLA independientes con pequeños archivos PDS4/ENVI generados."""

import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from data.mola_reader import GeographicBounds, MolaDataError, MolaReader
from data.mola_risk import slope_risk
from data.process_mola import build_grid, process_mola
from data.process_mola_global import build_global_grid, write_risk_overlay
from app.main import app
from app.services.map_service import _load_active_dataset


def write_fixture(
    directory: Path,
    values: np.ndarray,
    *,
    ignore_value: int = -32768,
    data_type: str = "SignedMSB2",
) -> tuple[Path, Path, Path]:
    rows, cols = values.shape
    ppd_x = cols / 360.0
    ppd_y = rows / 180.0
    pixel_resolution_km = 2 * np.pi * 3396.0 / cols
    image_path = directory / "fixture.img"
    label_path = directory / "fixture.xml"
    header_path = directory / "fixture.hdr"
    values.astype(">i2").tofile(image_path)
    label_path.write_text(
        f"""<?xml version="1.0"?>
<Product_Observational xmlns="http://pds.nasa.gov/pds4/pds/v1"
 xmlns:cart="http://pds.nasa.gov/pds4/cart/v1">
  <Identification_Area><logical_identifier>urn:nasa:pds:mgs_mola_topography_derived:data_meg016:fixture</logical_identifier></Identification_Area>
  <Observation_Area><Discipline_Area><cart:Cartography>
    <cart:Spatial_Domain><cart:Bounding_Coordinates>
      <cart:west_bounding_coordinate unit="deg">0</cart:west_bounding_coordinate>
      <cart:east_bounding_coordinate unit="deg">360</cart:east_bounding_coordinate>
      <cart:north_bounding_coordinate unit="deg">90</cart:north_bounding_coordinate>
      <cart:south_bounding_coordinate unit="deg">-90</cart:south_bounding_coordinate>
    </cart:Bounding_Coordinates></cart:Spatial_Domain>
    <cart:Spatial_Reference_Information><cart:Horizontal_Coordinate_System_Definition>
      <cart:Planar><cart:Map_Projection>
        <cart:map_projection_name>Equirectangular</cart:map_projection_name>
        <cart:Equirectangular>
          <cart:longitude_of_central_meridian unit="deg">180</cart:longitude_of_central_meridian>
        </cart:Equirectangular>
      </cart:Map_Projection><cart:Planar_Coordinate_Information><cart:Coordinate_Representation>
        <cart:pixel_scale_x unit="pixel/deg">{ppd_x}</cart:pixel_scale_x>
        <cart:pixel_scale_y unit="pixel/deg">{ppd_y}</cart:pixel_scale_y>
      </cart:Coordinate_Representation></cart:Planar_Coordinate_Information></cart:Planar>
    <cart:Geodetic_Model>
      <cart:latitude_type>Planetocentric</cart:latitude_type>
      <cart:longitude_direction>Positive East</cart:longitude_direction>
      <cart:a_axis_radius unit="km">3396.0</cart:a_axis_radius>
      <cart:b_axis_radius unit="km">3396.0</cart:b_axis_radius>
      <cart:c_axis_radius unit="km">3396.0</cart:c_axis_radius>
    </cart:Geodetic_Model>
    </cart:Horizontal_Coordinate_System_Definition></cart:Spatial_Reference_Information>
  </cart:Cartography></Discipline_Area></Observation_Area>
  <File_Area_Observational>
    <File><file_name>fixture.img</file_name></File>
    <Array_2D_Image>
    <offset unit="byte">0</offset><axis_index_order>Last Index Fastest</axis_index_order>
    <Element_Array><data_type>{data_type}</data_type><unit>meter</unit></Element_Array>
    <Axis_Array><axis_name>Line</axis_name><elements>{rows}</elements><sequence_number>1</sequence_number></Axis_Array>
    <Axis_Array><axis_name>Sample</axis_name><elements>{cols}</elements><sequence_number>2</sequence_number></Axis_Array>
  </Array_2D_Image></File_Area_Observational>
  <cart:pixel_resolution_y unit="km/pixel">{pixel_resolution_km}</cart:pixel_resolution_y>
  <cart:pixel_resolution_x unit="km/pixel">{pixel_resolution_km}</cart:pixel_resolution_x>
</Product_Observational>
""",
        encoding="utf-8",
    )
    header_path.write_text(f"data ignore value = {ignore_value}\n", encoding="ascii")
    return image_path, label_path, header_path


def test_reader_parses_pds4_dimensions_big_endian_and_units(tmp_path):
    values = np.arange(32 * 64, dtype=np.int16).reshape(32, 64) - 100
    image, label, header = write_fixture(tmp_path, values)
    reader = MolaReader(image, label, header)

    assert (reader.rows, reader.cols) == values.shape
    assert reader.elevation_at(0.0, 0.0) == float(values[16, 0])
    assert reader.elevation_at(0.0, 360.0) == float(values[16, 0])


def test_coordinate_conversion_and_window_crop(tmp_path):
    values = np.arange(32 * 64, dtype=np.int16).reshape(32, 64)
    image, label, header = write_fixture(tmp_path, values)
    reader = MolaReader(image, label, header)
    window = reader.read_window(GeographicBounds(-11.25, 11.25, 5.625, 16.875))

    assert window.elevation_m.shape == (4, 2)
    lat, lon = window.index_to_coordinate(1, 1)
    assert window.coordinate_to_index(lat, lon) == (1, 1)
    assert window.elevation_at(lat, lon) == float(values[15, 2])
    with pytest.raises(ValueError, match="fuera"):
        window.elevation_at(60.0, 120.0)


def test_ignore_value_is_invalid_and_not_returned_as_elevation(tmp_path):
    values = np.arange(32 * 64, dtype=np.int16).reshape(32, 64)
    values[16, 0] = 0
    image, label, header = write_fixture(tmp_path, values, ignore_value=0)
    reader = MolaReader(image, label, header)

    assert reader.elevation_at(0.0, 0.0) is None
    window = reader.read_window(GeographicBounds(-5.625, 5.625, 0.0, 11.25))
    assert not window.valid[1, 0]
    assert np.isnan(window.elevation_m[1, 0])
    assert np.isnan(window.slope_deg[1, 0])


def test_global_preview_averages_pixels_and_ignores_invalid_samples(tmp_path):
    values = np.ones((32, 64), dtype=np.int16) * 8
    values[:4, :4] = 4
    values[0, 0] = 0
    image, label, header = write_fixture(tmp_path, values, ignore_value=0)
    reader = MolaReader(image, label, header)

    elevations, valid = reader.read_global_preview(8, 4)

    assert elevations.shape == (4, 8)
    assert elevations[0, 0] == pytest.approx((15 * 4 + 48 * 8) / 63)
    assert valid.all()
    with pytest.raises(MolaDataError, match="dimensiones"):
        reader.read_global_preview(7, 4)


def test_slope_risk_proxy_is_normalized_and_capped():
    assert slope_risk(0.0) == 0.0
    assert slope_risk(10.0) == 0.5
    assert slope_risk(20.0) == 1.0
    assert slope_risk(35.0) == 1.0
    with pytest.raises(ValueError):
        slope_risk(-1.0)


def test_global_routing_grid_uses_coarse_cells_and_real_slope_data(tmp_path):
    values = np.arange(32 * 64, dtype=np.int16).reshape(32, 64)
    image, label, header = write_fixture(tmp_path, values)

    grid = build_global_grid(MolaReader(image, label, header), rows=4, cols=8)

    assert grid["grid"]["rows"] == 4
    assert grid["grid"]["cols"] == 8
    assert len(grid["cells"]) == 32
    assert grid["cells"][0]["latitude"] == pytest.approx(67.5)
    assert grid["cells"][0]["longitude"] == pytest.approx(22.5)
    assert grid["cells"][0]["valid"] is True
    assert grid["cells"][0]["slope_deg"] > 0
    assert grid["risk_available"] is True
    assert grid["cells"][0]["risk"] == pytest.approx(
        min(grid["cells"][0]["slope_deg"] / 20.0, 1.0)
    )
    risk_image = write_risk_overlay(grid, tmp_path / "risk.png").read_bytes()
    assert risk_image[:8] == b"\x89PNG\r\n\x1a\n"
    assert risk_image[16:24] == (8).to_bytes(4, "big") + (4).to_bytes(4, "big")


def test_slope_for_planar_surface_is_calculated_in_degrees(tmp_path):
    rows, cols = 32, 64
    y = np.arange(rows, dtype=np.int16)[:, None]
    values = np.broadcast_to(y * 100, (rows, cols)).copy()
    image, label, header = write_fixture(tmp_path, values, ignore_value=-32768)
    reader = MolaReader(image, label, header)
    window = reader.read_window(GeographicBounds(-5.625, 5.625, 0.0, 11.25))

    expected = np.degrees(np.arctan(100.0 / reader.cell_size_m))
    assert window.slope_deg[1, 1] == pytest.approx(expected, abs=1e-4)


def test_rejects_bad_bounds_types_and_rasters(tmp_path):
    with pytest.raises(MolaDataError, match="latitud"):
        GeographicBounds(-91, 0, 0, 1).validate()
    with pytest.raises(MolaDataError, match="longitud"):
        GeographicBounds(0, 1, 359, 361).validate()
    image, label, header = write_fixture(
        tmp_path, np.zeros((32, 64), dtype=np.int16), data_type="UnsignedByte"
    )
    with pytest.raises(MolaDataError, match="no soportado"):
        MolaReader(image, label, header)
    small_dir = tmp_path / "small"
    small_dir.mkdir()
    image, label, header = write_fixture(small_dir, np.zeros((32, 64), dtype=np.int16))
    reader = MolaReader(image, label, header)
    with pytest.raises(MolaDataError, match="al menos"):
        reader.read_window(GeographicBounds(0, 0.01, 0, 0.01))


def test_missing_or_truncated_files_raise_clear_errors(tmp_path):
    with pytest.raises(FileNotFoundError, match="MOLA requerido"):
        MolaReader(tmp_path / "missing.img")

    image, label, header = write_fixture(tmp_path, np.zeros((32, 64), dtype=np.int16))
    image.write_bytes(b"short")
    with pytest.raises(MolaDataError, match="Tamaño binario"):
        MolaReader(image, label, header)


def test_processor_writes_reusable_grid_and_never_overwrites(tmp_path):
    values = np.arange(32 * 64, dtype=np.int16).reshape(32, 64)
    image, label, header = write_fixture(tmp_path, values)
    output = tmp_path / "processed.json"
    grid = process_mola(
        GeographicBounds(-11.25, 11.25, 5.625, 16.875),
        output,
        image_path=image,
        label_path=label,
        header_path=header,
    )

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["data_source"] == "mola"
    assert saved["is_simulated"] is False
    assert saved["risk_available"] is True
    assert len(saved["cells"]) == saved["grid"]["rows"] * saved["grid"]["cols"]
    assert grid["cells"][0]["valid"] is True
    assert max(cell["risk"] for cell in grid["cells"] if cell["valid"]) > 0.0
    with pytest.raises(FileExistsError):
        process_mola(
            GeographicBounds(-11.25, 11.25, 5.625, 16.875),
            output,
            image_path=image,
            label_path=label,
            header_path=header,
        )


def test_grid_blocks_invalid_cells_and_marks_proxy_risk_unavailable_there(tmp_path):
    north_south = (np.arange(32, dtype=np.int16)[:, None] + 1) * 1000
    values = np.broadcast_to(north_south, (32, 64)).copy()
    values[16, 0] = 0
    image, label, header = write_fixture(tmp_path, values, ignore_value=0)
    window = MolaReader(image, label, header).read_window(
        GeographicBounds(-5.625, 5.625, 0.0, 11.25)
    )
    grid = build_grid(window)
    cell = next(cell for cell in grid["cells"] if cell["row"] == 1 and cell["col"] == 0)

    assert cell["valid"] is False
    assert cell["blocked"] is True
    assert grid["risk_available"] is True
    assert cell["risk"] == 0.0
    assert max(cell["risk"] for cell in grid["cells"] if cell["valid"]) > 0.0


@pytest.fixture
def mola_api_grid(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    values = np.arange(32 * 64, dtype=np.int16).reshape(32, 64)
    image, label, header = write_fixture(source_dir, values)
    output = tmp_path / "mola_region.json"
    process_mola(
        GeographicBounds(-11.25, 11.25, 5.625, 16.875),
        output,
        image_path=image,
        label_path=label,
        header_path=header,
    )
    monkeypatch.setenv("MARS_DATA_SOURCE", "mola")
    monkeypatch.setenv("MARS_MOLA_GRID_FILE", str(output))
    _load_active_dataset.cache_clear()
    yield output
    _load_active_dataset.cache_clear()


def test_fastapi_serves_mola_map_health_and_routes(mola_api_grid):
    client = TestClient(app)
    map_response = client.get("/api/v1/map")
    assert map_response.status_code == 200
    assert map_response.headers["content-encoding"] == "gzip"
    map_body = map_response.json()
    assert map_body["data_source"] == "mola"
    assert map_body["is_simulated"] is False
    assert map_body["risk_available"] is True
    assert len(map_body["cells"]) == 8
    assert map_body["cells"][0]["latitude"] is not None
    assert map_body["cells"][0]["valid"] is True
    assert map_body["global_grid"]["rows"] == 180
    assert map_body["global_grid"]["cols"] == 360
    assert len(map_body["global_grid"]["cells"]) == 180 * 360
    assert map_body["global_grid"]["cells"][0]["risk"] == pytest.approx(
        min(map_body["global_grid"]["cells"][0]["slope_deg"] / 20.0, 1.0)
    )
    assert map_body["cost_model"]["risk_weight"] == 2.0

    health = client.get("/api/v1/health").json()
    assert health["data_source"] == "mola"
    response = client.post("/api/v1/routes", json={
        "origin": {"row": 0, "col": 0},
        "destination": {"row": 3, "col": 1},
    })
    assert response.status_code == 200
    body = response.json()
    assert body["data_source"] == "mola"
    assert body["is_simulated"] is False
    assert body["path"][0] == {"row": 0, "col": 0}
    assert body["path"][-1] == {"row": 3, "col": 1}
    assert set(body) == {
        "status", "data_source", "is_simulated", "disclaimer", "origin",
        "destination", "allow_diagonal", "path", "summary",
    }


def test_geographic_route_uses_global_mola_outside_detail_region(mola_api_grid):
    response = TestClient(app).post("/api/v1/routes", json={
        "origin": {"latitude": 0.25, "longitude": 0.25},
        "destination": {"latitude": 0.25, "longitude": 10.25},
    })

    assert response.status_code == 200
    body = response.json()
    assert body["resolution"] == "mola-global-1deg"
    assert body["origin"]["latitude"] == pytest.approx(0.5)
    assert body["origin"]["longitude"] == pytest.approx(0.5)
    assert body["destination"]["longitude"] == pytest.approx(10.5)
    assert all("latitude" in point and "longitude" in point for point in body["path"])
    assert body["summary"]["max_risk"] > 0


def test_geographic_route_keeps_detail_resolution_inside_active_region(mola_api_grid):
    response = TestClient(app).post("/api/v1/routes", json={
        "origin": {"latitude": -2.8, "longitude": 8.5},
        "destination": {"latitude": -2.8, "longitude": 14.5},
    })

    assert response.status_code == 200
    body = response.json()
    assert body["resolution"] == "mola-detail"
    assert body["summary"]["steps"] == 1


@pytest.mark.parametrize(
    "origin,destination",
    [
        (
            {"latitude": 0.0, "longitude": 0.0},
            {"row": 1, "col": 1},
        ),
        (
            {"row": 1, "col": 1, "latitude": 0.0, "longitude": 0.0},
            {"latitude": 0.0, "longitude": 1.0},
        ),
        (
            {"latitude": 91.0, "longitude": 0.0},
            {"latitude": 0.0, "longitude": 1.0},
        ),
    ],
)
def test_route_rejects_mixed_or_invalid_geographic_coordinates(origin, destination):
    response = TestClient(app).post(
        "/api/v1/routes",
        json={"origin": origin, "destination": destination},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_fastapi_reports_missing_mola_grid_as_service_unavailable(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MARS_DATA_SOURCE", "mola")
    monkeypatch.setenv("MARS_MOLA_GRID_FILE", str(tmp_path / "missing.json"))
    _load_active_dataset.cache_clear()

    response = TestClient(app).get("/api/v1/map")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATASET_UNAVAILABLE"
    assert "process_mola.py" in response.json()["error"]["message"]
