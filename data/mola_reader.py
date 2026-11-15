"""Reader for PDS4-labelled MOLA MEGDR global elevation rasters.

The supported binary layout is read from the PDS4 label rather than inferred
from the filename: a row-major, signed, 16-bit big-endian image. The
accompanying ENVI header is used only for its declared ignore value.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from numpy.typing import NDArray

DEFAULT_IMAGE = Path(__file__).resolve().parent / "raw" / "mola" / "megt90n000eb.img"
PLANET_RADIUS_M = 3_396_000.0
MAX_WINDOW_CELLS = 250_000


class MolaDataError(ValueError):
    """The MOLA label, header, or requested geographic area is unsupported."""


@dataclass(frozen=True)
class GeographicBounds:
    """A non-wrapping Mars latitude/positive-east-longitude rectangle."""

    south: float
    north: float
    west: float
    east: float

    def validate(self) -> None:
        values = (self.south, self.north, self.west, self.east)
        if not all(math.isfinite(value) for value in values):
            raise MolaDataError("Los límites geográficos deben ser números finitos.")
        if not (-90.0 <= self.south < self.north <= 90.0):
            raise MolaDataError("La latitud debe cumplir -90 <= sur < norte <= 90.")
        if not (0.0 <= self.west < self.east <= 360.0):
            raise MolaDataError(
                "La longitud positiva este debe cumplir 0 <= oeste < este <= 360; "
                "las ventanas que cruzan el meridiano 0 deben dividirse."
            )

    @classmethod
    def from_sequence(cls, values: tuple[float, float, float, float]) -> "GeographicBounds":
        if len(values) != 4:
            raise MolaDataError("Se requieren cuatro límites: sur,norte,oeste,este.")
        bounds = cls(*values)
        bounds.validate()
        return bounds


@dataclass(frozen=True)
class MolaWindow:
    """A small in-memory MOLA crop and its derived slope/validity arrays."""

    elevation_m: NDArray[np.float32]
    valid: NDArray[np.bool_]
    slope_deg: NDArray[np.float32]
    row_offset: int
    col_offset: int
    pixels_per_degree_x: float
    pixels_per_degree_y: float
    west_edge_deg: float
    north_edge_deg: float
    cell_size_m: float

    @property
    def rows(self) -> int:
        return int(self.elevation_m.shape[0])

    @property
    def cols(self) -> int:
        return int(self.elevation_m.shape[1])

    @property
    def bounds(self) -> GeographicBounds:
        return GeographicBounds(
            south=self.north_edge_deg - self.rows / self.pixels_per_degree_y,
            north=self.north_edge_deg,
            west=self.west_edge_deg,
            east=self.west_edge_deg + self.cols / self.pixels_per_degree_x,
        )

    def index_to_coordinate(self, row: int, col: int) -> tuple[float, float]:
        """Return the pixel-center (planetocentric latitude, east longitude)."""
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            raise IndexError(f"Índice fuera de la ventana MOLA: ({row}, {col}).")
        latitude = self.north_edge_deg - (row + 0.5) / self.pixels_per_degree_y
        longitude = self.west_edge_deg + (col + 0.5) / self.pixels_per_degree_x
        return latitude, longitude

    def coordinate_to_index(self, latitude: float, longitude: float) -> tuple[int, int]:
        """Map a geographic coordinate in this crop to its containing cell."""
        if not math.isfinite(latitude) or not -90.0 <= latitude <= 90.0:
            raise ValueError("La latitud planetocéntrica debe estar entre -90 y 90 grados.")
        if not math.isfinite(longitude) or not -180.0 <= longitude <= 360.0:
            raise ValueError(
                "La longitud positiva este debe estar entre -180 y 360 grados."
            )
        global_row = math.floor((90.0 - latitude) * self.pixels_per_degree_y)
        normalized_longitude = longitude % 360.0
        global_col = math.floor(normalized_longitude * self.pixels_per_degree_x)
        row, col = global_row - self.row_offset, global_col - self.col_offset
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            raise ValueError("La coordenada está fuera de la ventana MOLA seleccionada.")
        return row, col

    def elevation_at(self, latitude: float, longitude: float) -> Optional[float]:
        row, col = self.coordinate_to_index(latitude, longitude)
        if not self.valid[row, col]:
            return None
        return float(self.elevation_m[row, col])

    def slope_at(self, latitude: float, longitude: float) -> Optional[float]:
        row, col = self.coordinate_to_index(latitude, longitude)
        value = float(self.slope_deg[row, col])
        return value if math.isfinite(value) else None


def _local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _first_element(root: ET.Element, name: str) -> ET.Element:
    for element in root.iter():
        if _local_name(element) == name:
            return element
    raise MolaDataError(f"El label PDS4 no contiene el campo requerido {name!r}.")


def _first_text(root: ET.Element, name: str) -> str:
    element = _first_element(root, name)
    if element.text and element.text.strip():
        return element.text.strip()
    raise MolaDataError(f"El campo requerido {name!r} está vacío en el label PDS4.")


def _child_text(element: ET.Element, name: str) -> str:
    for child in element:
        if _local_name(child) == name and child.text and child.text.strip():
            return child.text.strip()
    raise MolaDataError(f"El label PDS4 no contiene {name!r} en el descriptor de imagen.")


def _parse_ignore_value(header_path: Path) -> Optional[int]:
    if not header_path.exists():
        return None
    try:
        text = header_path.read_text(encoding="ascii", errors="strict")
    except UnicodeDecodeError as exc:
        raise MolaDataError(f"El header ENVI no es texto ASCII válido: {header_path}") from exc
    match = re.search(r"^\s*data\s+ignore\s+value\s*=\s*([+-]?\d+)\s*$",
                      text, flags=re.IGNORECASE | re.MULTILINE)
    if match is None:
        return None
    value = int(match.group(1))
    if not (-32768 <= value <= 32767):
        raise MolaDataError(f"Valor ignore fuera de int16 en {header_path}: {value}.")
    return value


class MolaReader:
    """Read a PDS4 MOLA MEGDR image without loading the global image into RAM."""

    def __init__(
        self,
        image_path: Path | str = DEFAULT_IMAGE,
        label_path: Optional[Path | str] = None,
        header_path: Optional[Path | str] = None,
    ) -> None:
        self.image_path = Path(image_path)
        self.label_path = Path(label_path) if label_path else self.image_path.with_suffix(".xml")
        self.header_path = Path(header_path) if header_path else self.image_path.with_suffix(".hdr")
        for path in (self.image_path, self.label_path):
            if not path.is_file():
                raise FileNotFoundError(f"No se encontró el archivo MOLA requerido: {path}")

        try:
            root = ET.parse(self.label_path).getroot()
        except ET.ParseError as exc:
            raise MolaDataError(f"Label PDS4 XML inválido ({self.label_path}): {exc}") from exc
        self.logical_identifier = _first_text(root, "logical_identifier")
        if (
            not self.logical_identifier.startswith("urn:nasa:pds:")
            or "mola" not in self.logical_identifier.lower()
        ):
            raise MolaDataError("El label no identifica un producto MOLA de NASA PDS.")
        declared_filename = _first_text(root, "file_name")
        if Path(declared_filename).name != self.image_path.name:
            raise MolaDataError(
                f"El label describe {declared_filename!r}, no {self.image_path.name!r}."
            )

        image = next(
            (element for element in root.iter() if _local_name(element) == "Array_2D_Image"),
            None,
        )
        if image is None:
            raise MolaDataError("El label PDS4 no contiene un Array_2D_Image.")
        element_array = next(
            (child for child in image if _local_name(child) == "Element_Array"), None
        )
        if element_array is None:
            raise MolaDataError("El descriptor PDS4 no contiene Element_Array.")
        data_type = _child_text(element_array, "data_type")
        unit = _child_text(element_array, "unit").lower()
        if data_type != "SignedMSB2":
            raise MolaDataError(
                f"Tipo de pixel PDS4 no soportado: {data_type!r}; se requiere SignedMSB2."
            )
        if unit not in {"meter", "meters", "m"}:
            raise MolaDataError(f"Unidad de elevación PDS4 no soportada: {unit!r}.")
        if _child_text(image, "axis_index_order") != "Last Index Fastest":
            raise MolaDataError("Orden de índices PDS4 no soportado.")
        offset_element = next(
            (child for child in image if _local_name(child) == "offset"), None
        )
        if offset_element is None or offset_element.attrib.get("unit") != "byte":
            raise MolaDataError("El offset del raster PDS4 debe estar expresado en bytes.")
        try:
            self.offset = int(offset_element.text or "")
        except ValueError as exc:
            raise MolaDataError("Offset binario inválido en el label PDS4.") from exc
        if self.offset < 0:
            raise MolaDataError("El offset binario PDS4 no puede ser negativo.")

        dimensions: dict[str, int] = {}
        for axis in (item for item in image if _local_name(item) == "Axis_Array"):
            axis_name = _child_text(axis, "axis_name").lower()
            elements = int(_child_text(axis, "elements"))
            dimensions[axis_name] = elements
        if "line" not in dimensions or "sample" not in dimensions:
            raise MolaDataError("El label debe declarar los ejes Line y Sample.")
        self.rows = dimensions["line"]
        self.cols = dimensions["sample"]
        expected_axis_order = {"line": 1, "sample": 2}
        for axis in (item for item in image if _local_name(item) == "Axis_Array"):
            axis_name = _child_text(axis, "axis_name").lower()
            sequence = int(_child_text(axis, "sequence_number"))
            if expected_axis_order.get(axis_name) != sequence:
                raise MolaDataError(
                    "El orden de ejes PDS4 no corresponde a filas (Line) "
                    "seguidas de muestras (Sample)."
                )

        self.pixels_per_degree_x = self._positive_measurement(
            root, "pixel_scale_x", "pixel/deg"
        )
        self.pixels_per_degree_y = self._positive_measurement(
            root, "pixel_scale_y", "pixel/deg"
        )
        self.cell_size_m = self._positive_measurement(
            root, "pixel_resolution_x", "km/pixel"
        ) * 1000.0
        pixel_resolution_y = self._positive_measurement(
            root, "pixel_resolution_y", "km/pixel"
        ) * 1000.0
        self.west_longitude = self._metadata_measurement(
            root, "west_bounding_coordinate", "deg"
        )
        self.east_longitude = self._metadata_measurement(
            root, "east_bounding_coordinate", "deg"
        )
        self.south_latitude = self._metadata_measurement(
            root, "south_bounding_coordinate", "deg"
        )
        self.north_latitude = self._metadata_measurement(
            root, "north_bounding_coordinate", "deg"
        )
        self.latitude_type = _first_text(root, "latitude_type")
        self.longitude_direction = _first_text(root, "longitude_direction")
        self.map_projection = _first_text(root, "map_projection_name")
        self.central_meridian = self._metadata_measurement(
            root, "longitude_of_central_meridian", "deg"
        )
        self.planet_radius_m = self._positive_measurement(
            root, "a_axis_radius", "km"
        ) * 1000.0
        b_axis_radius_m = self._positive_measurement(root, "b_axis_radius", "km") * 1000.0
        c_axis_radius_m = self._positive_measurement(root, "c_axis_radius", "km") * 1000.0
        if not math.isclose(self.planet_radius_m, PLANET_RADIUS_M, abs_tol=0.1):
            raise MolaDataError(
                f"Radio de Marte no soportado por el cálculo de pendiente: "
                f"{self.planet_radius_m} m."
            )
        if not math.isclose(self.planet_radius_m, b_axis_radius_m, abs_tol=0.1) or not math.isclose(
            self.planet_radius_m, c_axis_radius_m, abs_tol=0.1
        ):
            raise MolaDataError(
                "El cálculo de pendiente actual requiere el modelo esférico del producto MOLA."
            )
        if not math.isclose(self.cell_size_m, pixel_resolution_y, abs_tol=1e-3):
            raise MolaDataError("La resolución lineal x/y de MOLA no coincide.")
        if (
            self.latitude_type != "Planetocentric"
            or self.longitude_direction != "Positive East"
            or self.map_projection != "Equirectangular"
            or not math.isclose(self.central_meridian, 180.0, abs_tol=1e-8)
        ):
            raise MolaDataError(
                "Sistema de coordenadas MOLA no soportado: se requiere equirectangular, "
                "latitud planetocéntrica y longitud positiva este centrada en 180°."
            )
        if (
            not math.isclose(self.west_longitude, 0.0, abs_tol=1e-8)
            or not math.isclose(self.east_longitude, 360.0, abs_tol=1e-8)
            or not math.isclose(self.south_latitude, -90.0, abs_tol=1e-8)
            or not math.isclose(self.north_latitude, 90.0, abs_tol=1e-8)
        ):
            raise MolaDataError(
                "Este lector requiere un MEGDR global que cubra 0–360°E y -90–90°."
            )
        if not math.isclose(self.cols, 360.0 * self.pixels_per_degree_x, abs_tol=1e-6):
            raise MolaDataError("La dimensión Sample no corresponde al dominio global 0–360°.")
        if not math.isclose(self.rows, 180.0 * self.pixels_per_degree_y, abs_tol=1e-6):
            raise MolaDataError("La dimensión Line no corresponde al dominio global -90–90°.")

        self.ignore_value = _parse_ignore_value(self.header_path)
        expected_bytes = self.offset + self.rows * self.cols * 2
        actual_bytes = self.image_path.stat().st_size
        if actual_bytes != expected_bytes:
            raise MolaDataError(
                f"Tamaño binario incompatible con el label: {actual_bytes} bytes; "
                f"se esperaban {expected_bytes}."
            )
        self._array = np.memmap(
            self.image_path,
            dtype=">i2",
            mode="r",
            offset=self.offset,
            shape=(self.rows, self.cols),
            order="C",
        )

    @staticmethod
    def _metadata_measurement(root: ET.Element, name: str, expected_unit: str) -> float:
        element = _first_element(root, name)
        if element.attrib.get("unit") != expected_unit:
            raise MolaDataError(
                f"Unidad PDS4 no soportada para {name}: {element.attrib.get('unit')!r}."
            )
        try:
            value = float(element.text or "")
        except ValueError as exc:
            raise MolaDataError(f"Metadato PDS4 no numérico {name!r}.") from exc
        if not math.isfinite(value):
            raise MolaDataError(f"Metadato PDS4 inválido {name}={value!r}.")
        return value

    @staticmethod
    def _positive_measurement(root: ET.Element, name: str, expected_unit: str) -> float:
        value = MolaReader._metadata_measurement(root, name, expected_unit)
        if value <= 0.0:
            raise MolaDataError(f"Metadato PDS4 inválido {name}={value!r}.")
        return value

    def _global_index(self, latitude: float, longitude: float) -> tuple[int, int]:
        if not math.isfinite(latitude) or not -90.0 <= latitude <= 90.0:
            raise ValueError("La latitud planetocéntrica debe estar entre -90 y 90 grados.")
        if not math.isfinite(longitude) or not -180.0 <= longitude <= 360.0:
            raise ValueError(
                "La longitud positiva este debe estar entre -180 y 360 grados."
            )
        longitude = longitude % 360.0
        row = min(self.rows - 1, math.floor(
            (self.north_latitude - latitude) * self.pixels_per_degree_y
        ))
        col = min(
            self.cols - 1,
            math.floor((longitude - self.west_longitude) * self.pixels_per_degree_x),
        )
        return row, col

    def elevation_at(self, latitude: float, longitude: float) -> Optional[float]:
        """Return elevation in meters, or None when the header marks it invalid."""
        row, col = self._global_index(latitude, longitude)
        value = int(self._array[row, col])
        if self.ignore_value is not None and value == self.ignore_value:
            return None
        return float(value)

    def read_global_preview(
        self, width: int, height: int
    ) -> tuple[NDArray[np.float32], NDArray[np.bool_]]:
        """Average the global raster into a small preview, excluding ignored pixels."""
        if (
            isinstance(width, bool) or not isinstance(width, int) or width < 1
            or isinstance(height, bool) or not isinstance(height, int) or height < 1
            or self.cols % width != 0 or self.rows % height != 0
        ):
            raise MolaDataError(
                "Las dimensiones de la vista previa deben ser enteros positivos "
                "que dividan exactamente el raster global."
            )

        group_rows = self.rows // height
        group_cols = self.cols // width
        elevations = np.full((height, width), np.nan, dtype=np.float32)
        valid = np.zeros((height, width), dtype=np.bool_)
        for preview_row in range(height):
            start = preview_row * group_rows
            block = np.asarray(self._array[start:start + group_rows])
            block_valid = (
                np.ones(block.shape, dtype=np.bool_)
                if self.ignore_value is None
                else block != self.ignore_value
            )
            grouped_valid = block_valid.reshape(group_rows, width, group_cols)
            counts = grouped_valid.sum(axis=(0, 2))
            sums = np.where(block_valid, block, 0).reshape(
                group_rows, width, group_cols
            ).sum(axis=(0, 2), dtype=np.int64)
            row_valid = counts > 0
            elevations[preview_row, row_valid] = (
                sums[row_valid] / counts[row_valid]
            ).astype(np.float32)
            valid[preview_row] = row_valid
        return elevations, valid

    def read_window(
        self,
        bounds: GeographicBounds,
        *,
        max_cells: int = MAX_WINDOW_CELLS,
    ) -> MolaWindow:
        """Read only the pixels overlapping `bounds`, then derive local slopes."""
        bounds.validate()
        if max_cells < 4:
            raise ValueError("max_cells debe permitir al menos una ventana 2x2.")
        row_start = max(
            0, math.floor((self.north_latitude - bounds.north) * self.pixels_per_degree_y)
        )
        row_stop = min(
            self.rows, math.ceil((self.north_latitude - bounds.south) * self.pixels_per_degree_y)
        )
        col_start = max(
            0, math.floor((bounds.west - self.west_longitude) * self.pixels_per_degree_x)
        )
        col_stop = min(
            self.cols, math.ceil((bounds.east - self.west_longitude) * self.pixels_per_degree_x)
        )
        if row_stop - row_start < 2 or col_stop - col_start < 2:
            raise MolaDataError("La región MOLA debe incluir al menos 2 filas y 2 columnas.")
        rows, cols = row_stop - row_start, col_stop - col_start
        if rows * cols > max_cells:
            raise MolaDataError(
                f"La ventana MOLA requiere {rows * cols} celdas; el máximo es {max_cells}. "
                "Use una región menor."
            )

        raw = np.asarray(self._array[row_start:row_stop, col_start:col_stop])
        elevations = raw.astype(np.float32)
        valid = np.isfinite(elevations)
        if self.ignore_value is not None:
            valid &= raw != self.ignore_value
        elevations[~valid] = np.nan

        north_edge = self.north_latitude - row_start / self.pixels_per_degree_y
        west_edge = self.west_longitude + col_start / self.pixels_per_degree_x
        window = MolaWindow(
            elevation_m=elevations,
            valid=valid,
            slope_deg=np.full(elevations.shape, np.nan, dtype=np.float32),
            row_offset=row_start,
            col_offset=col_start,
            pixels_per_degree_x=self.pixels_per_degree_x,
            pixels_per_degree_y=self.pixels_per_degree_y,
            west_edge_deg=west_edge,
            north_edge_deg=north_edge,
            cell_size_m=self.cell_size_m,
        )
        window.slope_deg[:] = compute_slope_deg(
            elevations,
            valid,
            north_edge_deg=north_edge,
            pixels_per_degree_y=self.pixels_per_degree_y,
            cell_size_m=self.cell_size_m,
        )
        return window


def compute_slope_deg(
    elevations: NDArray[np.float32],
    valid: NDArray[np.bool_],
    *,
    north_edge_deg: float,
    pixels_per_degree_y: float,
    cell_size_m: float,
) -> NDArray[np.float32]:
    """Slope in degrees of an equirectangular crop on a sphere.

    `cell_size_m` is the north-south pixel size; the east-west spacing shrinks
    with cos(latitude) of each row center. Invalid pixels get NaN.
    """
    rows = elevations.shape[0]
    dz_dy = _finite_difference(elevations, valid, axis=0, spacing=cell_size_m)
    latitudes = north_edge_deg - (
        np.arange(rows, dtype=np.float64) + 0.5
    ) / pixels_per_degree_y
    dx = (cell_size_m * np.cos(np.deg2rad(latitudes)))[:, np.newaxis]
    dz_dx = _finite_difference(elevations, valid, axis=1, spacing=dx)
    slopes = np.degrees(np.arctan(np.hypot(dz_dx, dz_dy))).astype(np.float32)
    slopes[~valid] = np.nan
    return slopes


def _finite_difference(
    values: NDArray[np.float32],
    valid: NDArray[np.bool_],
    *,
    axis: int,
    spacing: float | NDArray[np.float64],
    periodic: bool = False,
) -> NDArray[np.float64]:
    """Use central differences where possible and one-sided differences at gaps."""
    previous = np.roll(values, 1, axis=axis)
    next_value = np.roll(values, -1, axis=axis)
    previous_valid = np.roll(valid, 1, axis=axis)
    next_valid = np.roll(valid, -1, axis=axis)
    if axis == 0:
        previous_valid[0, :] = False
        next_valid[-1, :] = False
    elif not periodic:
        previous_valid[:, 0] = False
        next_valid[:, -1] = False

    derivative = np.full(values.shape, np.nan, dtype=np.float64)
    central = valid & previous_valid & next_valid
    forward = valid & ~previous_valid & next_valid
    backward = valid & previous_valid & ~next_valid
    np.divide(next_value - previous, 2.0 * spacing, out=derivative, where=central)
    np.divide(next_value - values, spacing, out=derivative, where=forward)
    np.divide(values - previous, spacing, out=derivative, where=backward)
    return derivative
