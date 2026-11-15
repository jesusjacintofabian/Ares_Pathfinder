"""Minimal, strict reader/writer for single-band int16 geographic GeoTIFF DEMs.

Only NumPy and the standard library are used. The supported layout is the
one verified for the USGS "Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2"
file: classic TIFF or BigTIFF, uncompressed, one band of signed 16-bit
integers stored in strips, georeferenced in degrees on a spherical body with
ModelPixelScale + ModelTiepoint. Anything else is rejected with a clear error
instead of being guessed.

Bytes come from an interchangeable source, so a window can be read from a
local file or straight from an HTTPS server that supports Range requests,
without downloading the whole (≈ 11 GB) raster.
"""

from __future__ import annotations

import http.client
import math
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Protocol
from urllib.parse import urljoin, urlsplit

import numpy as np
from numpy.typing import NDArray

if __package__:
    from .mola_reader import GeographicBounds, MAX_WINDOW_CELLS, MolaWindow, compute_slope_deg
else:
    from mola_reader import GeographicBounds, MAX_WINDOW_CELLS, MolaWindow, compute_slope_deg

# TIFF tags used by this reader.
TAG_IMAGE_WIDTH = 256
TAG_IMAGE_LENGTH = 257
TAG_BITS_PER_SAMPLE = 258
TAG_COMPRESSION = 259
TAG_PHOTOMETRIC = 262
TAG_STRIP_OFFSETS = 273
TAG_SAMPLES_PER_PIXEL = 277
TAG_ROWS_PER_STRIP = 278
TAG_STRIP_BYTE_COUNTS = 279
TAG_PLANAR_CONFIG = 284
TAG_PREDICTOR = 317
TAG_TILE_WIDTH = 322
TAG_TILE_OFFSETS = 324
TAG_SAMPLE_FORMAT = 339
TAG_MODEL_PIXEL_SCALE = 33550
TAG_MODEL_TIEPOINT = 33922
TAG_MODEL_TRANSFORMATION = 34264
TAG_GEO_KEY_DIRECTORY = 34735
TAG_GEO_DOUBLE_PARAMS = 34736
TAG_GEO_ASCII_PARAMS = 34737
TAG_GDAL_NODATA = 42113

# GeoTIFF keys.
KEY_MODEL_TYPE = 1024
KEY_RASTER_TYPE = 1025
KEY_GEOG_CITATION = 2049
KEY_GEOG_ANGULAR_UNITS = 2054
KEY_SEMI_MAJOR_AXIS = 2057
KEY_SEMI_MINOR_AXIS = 2058
KEY_INV_FLATTENING = 2059
KEY_PRIME_MERIDIAN_LONG = 2061
MODEL_TYPE_GEOGRAPHIC = 2
RASTER_PIXEL_IS_AREA = 1
ANGULAR_UNIT_DEGREE = 9102

_TYPE_FORMATS = {
    1: ("B", 1), 2: ("s", 1), 3: ("H", 2), 4: ("I", 4), 5: ("I", 8),
    6: ("b", 1), 7: ("B", 1), 8: ("h", 2), 9: ("i", 4), 10: ("i", 8),
    11: ("f", 4), 12: ("d", 8), 16: ("Q", 8), 17: ("q", 8), 18: ("Q", 8),
}
_MAX_IFD_ENTRIES = 1024
_MAX_TAG_BYTES = 1 << 20  # Metadata tags; strip arrays are read by slices.
_EDGE_EPSILON = 1e-9


class GeoTiffError(ValueError):
    """The GeoTIFF layout, georeference, or requested window is unsupported."""


class ByteSource(Protocol):
    """Random-access byte provider."""

    description: str
    size: Optional[int]

    def read(self, offset: int, length: int) -> bytes: ...


class LocalFileSource:
    """Read byte ranges from a local file."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(f"No se encontró el GeoTIFF: {self.path}")
        self.size = self.path.stat().st_size
        self.description = str(self.path)
        self.last_modified: Optional[str] = None
        self._stream = self.path.open("rb")

    def read(self, offset: int, length: int) -> bytes:
        if offset < 0 or length < 0 or offset + length > self.size:
            raise GeoTiffError(
                f"Lectura fuera del archivo ({offset}+{length} > {self.size} bytes)."
            )
        self._stream.seek(offset)
        data = self._stream.read(length)
        if len(data) != length:
            raise GeoTiffError("Lectura incompleta del GeoTIFF local.")
        return data

    def close(self) -> None:
        self._stream.close()

    def __enter__(self) -> "LocalFileSource":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


ConnectionFactory = Callable[[str], Any]


class HttpRangeSource:
    """Read byte ranges from an HTTPS URL with `Range` requests.

    Redirects are resolved once with HEAD requests; the final URL must also be
    HTTPS and must declare `Accept-Ranges: bytes`. Each read checks for
    `206 Partial Content`, the `Content-Range` start, and the exact length.
    """

    USER_AGENT = "ares-pathfinder-dem-reader"

    def __init__(
        self,
        url: str,
        *,
        timeout: float = 30.0,
        retries: int = 3,
        max_redirects: int = 5,
        connection_factory: Optional[ConnectionFactory] = None,
    ) -> None:
        self._timeout = timeout
        self._retries = max(1, retries)
        self._factory = connection_factory or (
            lambda host: http.client.HTTPSConnection(host, timeout=self._timeout)
        )
        self._connection: Any = None
        self._host = ""
        self.requested_url = url
        self.requests = 0
        self.bytes_read = 0
        self.url, headers = self._resolve(url, max_redirects)
        self.description = self.url
        accept = headers.get("accept-ranges", "").lower()
        if accept != "bytes":
            raise GeoTiffError(
                f"El servidor no declara 'Accept-Ranges: bytes' ({self.url}); "
                "no se puede leer por ventanas."
            )
        try:
            self.size: Optional[int] = int(headers["content-length"])
        except (KeyError, ValueError) as exc:
            raise GeoTiffError("El servidor no informa Content-Length.") from exc
        self.last_modified: Optional[str] = headers.get("last-modified")

    @staticmethod
    def _split(url: str) -> tuple[str, str]:
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname:
            raise GeoTiffError(f"Solo se admiten URL https: {url!r}.")
        host = parts.hostname + (f":{parts.port}" if parts.port else "")
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        return host, path

    def _resolve(self, url: str, max_redirects: int) -> tuple[str, dict[str, str]]:
        current = url
        for _ in range(max_redirects + 1):
            host, path = self._split(current)
            connection = self._factory(host)
            try:
                connection.request("HEAD", path, headers={"User-Agent": self.USER_AGENT})
                response = connection.getresponse()
                response.read()
                headers = {k.lower(): v for k, v in response.getheaders()}
            finally:
                connection.close()
            if response.status in (301, 302, 303, 307, 308):
                location = headers.get("location")
                if not location:
                    raise GeoTiffError("Redirección HTTP sin cabecera Location.")
                current = urljoin(current, location)
                continue
            if response.status != 200:
                raise GeoTiffError(f"HEAD {current} respondió HTTP {response.status}.")
            return current, headers
        raise GeoTiffError(f"Demasiadas redirecciones al resolver {url}.")

    def _connect(self) -> Any:
        host, _ = self._split(self.url)
        if self._connection is None or self._host != host:
            self.close()
            self._connection = self._factory(host)
            self._host = host
        return self._connection

    def read(self, offset: int, length: int) -> bytes:
        if offset < 0 or length <= 0 or (self.size is not None and offset + length > self.size):
            raise GeoTiffError(f"Rango inválido: {offset}+{length} (tamaño {self.size}).")
        _, path = self._split(self.url)
        last_error: Exception | None = None
        for attempt in range(self._retries):
            try:
                connection = self._connect()
                connection.request(
                    "GET",
                    path,
                    headers={
                        "Range": f"bytes={offset}-{offset + length - 1}",
                        "User-Agent": self.USER_AGENT,
                    },
                )
                response = connection.getresponse()
                data = response.read()
                if response.status != 206:
                    raise GeoTiffError(
                        f"Se esperaba HTTP 206 para un rango y se recibió {response.status}."
                    )
                content_range = response.getheader("Content-Range", "")
                if not content_range.startswith(f"bytes {offset}-"):
                    raise GeoTiffError(f"Content-Range inesperado: {content_range!r}.")
                if len(data) != length:
                    raise GeoTiffError(
                        f"Rango incompleto: {len(data)} de {length} bytes."
                    )
                self.requests += 1
                self.bytes_read += length
                return data
            except (OSError, http.client.HTTPException, GeoTiffError) as exc:
                last_error = exc
                self.close()
                if attempt + 1 < self._retries:
                    time.sleep(0.5 * (attempt + 1))
        raise GeoTiffError(f"No se pudo leer el rango tras {self._retries} intentos: {last_error}")

    def close(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            finally:
                self._connection = None

    def __enter__(self) -> "HttpRangeSource":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


@dataclass(frozen=True)
class _Entry:
    tag: int
    type: int
    count: int
    inline: Optional[bytes]
    offset: int


@dataclass(frozen=True)
class DemWindow(MolaWindow):
    """A `MolaWindow` whose coordinate lookup uses its geographic edges.

    `row_offset`/`col_offset` are the window's first pixel in the source file
    (informative); unlike MOLA MEGDR, the source grid need not align with 0°E.
    """

    def coordinate_to_index(self, latitude: float, longitude: float) -> tuple[int, int]:
        if not math.isfinite(latitude) or not -90.0 <= latitude <= 90.0:
            raise ValueError("La latitud planetocéntrica debe estar entre -90 y 90 grados.")
        if not math.isfinite(longitude) or not -180.0 <= longitude <= 360.0:
            raise ValueError("La longitud positiva este debe estar entre -180 y 360 grados.")
        row = math.floor((self.north_edge_deg - latitude) * self.pixels_per_degree_y)
        col = math.floor(((longitude - self.west_edge_deg) % 360.0) * self.pixels_per_degree_x)
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            raise ValueError("La coordenada está fuera de la ventana seleccionada.")
        return row, col


@dataclass(frozen=True)
class PixelWindow:
    """Half-open pixel ranges in the GeoTIFF's own row/column indices."""

    row_start: int
    row_stop: int
    col_start: int
    col_stop: int

    @property
    def rows(self) -> int:
        return self.row_stop - self.row_start

    @property
    def cols(self) -> int:
        return self.col_stop - self.col_start


@dataclass(frozen=True)
class RawClip:
    """Raw int16 samples copied from the file; `values[0, 0]` is file pixel (row_start, col_start)."""

    values: NDArray[np.int16]
    row_start: int
    col_start: int


class GeoTiffReader:
    """Parse and validate a single-band int16 geographic GeoTIFF."""

    def __init__(self, source: ByteSource) -> None:
        self.source = source
        header = source.read(0, 16)
        if header[:2] == b"II":
            self._bo = "<"
        elif header[:2] == b"MM":
            self._bo = ">"
        else:
            raise GeoTiffError("El archivo no es TIFF (falta la marca II/MM).")
        magic = struct.unpack_from(self._bo + "H", header, 2)[0]
        if magic == 42:
            self.bigtiff = False
            ifd_offset = struct.unpack_from(self._bo + "I", header, 4)[0]
        elif magic == 43:
            self.bigtiff = True
            offset_size, zero = struct.unpack_from(self._bo + "HH", header, 4)
            if offset_size != 8 or zero != 0:
                raise GeoTiffError("Cabecera BigTIFF inválida.")
            ifd_offset = struct.unpack_from(self._bo + "Q", header, 8)[0]
        else:
            raise GeoTiffError(f"Número mágico TIFF no soportado: {magic}.")
        self._entries = self._read_ifd(ifd_offset)
        self._validate_layout()
        self._validate_georeference()

    # ------------------------------------------------------------------ IFD
    def _read_ifd(self, offset: int) -> dict[int, _Entry]:
        count_fmt, count_size, entry_size, value_size = (
            ("Q", 8, 20, 8) if self.bigtiff else ("H", 2, 12, 4)
        )
        count = struct.unpack(self._bo + count_fmt, self.source.read(offset, count_size))[0]
        if not 0 < count <= _MAX_IFD_ENTRIES:
            raise GeoTiffError(f"Número de etiquetas TIFF no válido: {count}.")
        block = self.source.read(offset + count_size, count * entry_size)
        entries: dict[int, _Entry] = {}
        for index in range(count):
            base = index * entry_size
            if self.bigtiff:
                tag, typ, n = struct.unpack_from(self._bo + "HHQ", block, base)
            else:
                tag, typ, n = struct.unpack_from(self._bo + "HHI", block, base)
            raw_value = block[base + entry_size - value_size: base + entry_size]
            if typ not in _TYPE_FORMATS:
                continue  # Unknown types are irrelevant unless they are required tags.
            nbytes = _TYPE_FORMATS[typ][1] * n
            if nbytes <= value_size:
                entries[tag] = _Entry(tag, typ, n, raw_value[:nbytes], 0)
            else:
                pointer = struct.unpack(self._bo + ("Q" if self.bigtiff else "I"), raw_value)[0]
                entries[tag] = _Entry(tag, typ, n, None, pointer)
        return entries

    def _decode(self, entry: _Entry, data: bytes, count: int) -> tuple[Any, ...] | str:
        fmt, _ = _TYPE_FORMATS[entry.type]
        if entry.type == 2:
            return data.decode("ascii", errors="replace").rstrip("\x00")
        if entry.type in (5, 10):
            pairs = struct.unpack(self._bo + fmt * (2 * count), data)
            return tuple(pairs[i] / pairs[i + 1] if pairs[i + 1] else math.nan
                         for i in range(0, len(pairs), 2))
        return struct.unpack(self._bo + fmt * count, data)

    def _values(self, tag: int) -> tuple[Any, ...] | str:
        entry = self._entries[tag]
        size = _TYPE_FORMATS[entry.type][1]
        nbytes = size * entry.count
        if entry.inline is not None:
            data = entry.inline
        else:
            if nbytes > _MAX_TAG_BYTES:
                raise GeoTiffError(f"La etiqueta TIFF {tag} es demasiado grande ({nbytes} bytes).")
            data = self.source.read(entry.offset, nbytes)
        return self._decode(entry, data, entry.count)

    def _value_slice(self, tag: int, start: int, stop: int) -> tuple[int, ...]:
        """Read only elements [start, stop) of an integer array tag."""
        entry = self._entries[tag]
        if not 0 <= start < stop <= entry.count:
            raise GeoTiffError(f"Índice fuera de la etiqueta TIFF {tag}.")
        size = _TYPE_FORMATS[entry.type][1]
        if entry.inline is not None:
            data = entry.inline[start * size: stop * size]
        else:
            data = self.source.read(entry.offset + start * size, (stop - start) * size)
        values = self._decode(entry, data, stop - start)
        assert not isinstance(values, str)
        return tuple(int(v) for v in values)

    def _single_int(self, tag: int, name: str, default: Optional[int] = None) -> int:
        if tag not in self._entries:
            if default is None:
                raise GeoTiffError(f"Falta la etiqueta TIFF obligatoria {name} ({tag}).")
            return default
        values = self._values(tag)
        if isinstance(values, str) or len(values) != 1:
            raise GeoTiffError(f"La etiqueta TIFF {name} debe tener un único valor.")
        return int(values[0])

    # ----------------------------------------------------------- validation
    def _validate_layout(self) -> None:
        if TAG_TILE_WIDTH in self._entries or TAG_TILE_OFFSETS in self._entries:
            raise GeoTiffError("GeoTIFF en teselas no soportado: se requieren strips.")
        self.width = self._single_int(TAG_IMAGE_WIDTH, "ImageWidth")
        self.height = self._single_int(TAG_IMAGE_LENGTH, "ImageLength")
        if self.width < 2 or self.height < 2:
            raise GeoTiffError("El raster debe tener al menos 2 × 2 píxeles.")
        compression = self._single_int(TAG_COMPRESSION, "Compression", 1)
        if compression != 1:
            raise GeoTiffError(
                f"Compresión TIFF no soportada ({compression}); se requiere sin compresión (1)."
            )
        samples = self._single_int(TAG_SAMPLES_PER_PIXEL, "SamplesPerPixel", 1)
        if samples != 1:
            raise GeoTiffError(f"Se requiere una sola banda; el archivo tiene {samples}.")
        bits = self._values(TAG_BITS_PER_SAMPLE) if TAG_BITS_PER_SAMPLE in self._entries else (1,)
        if isinstance(bits, str) or tuple(bits) != (16,):
            raise GeoTiffError(f"BitsPerSample no soportado: {bits}; se requiere 16.")
        sample_format = self._single_int(TAG_SAMPLE_FORMAT, "SampleFormat", 1)
        if sample_format != 2:
            raise GeoTiffError(
                f"SampleFormat no soportado ({sample_format}); se requiere entero con signo (2)."
            )
        predictor = self._single_int(TAG_PREDICTOR, "Predictor", 1)
        if predictor != 1:
            raise GeoTiffError("Predictor TIFF no soportado.")
        planar = self._single_int(TAG_PLANAR_CONFIG, "PlanarConfiguration", 1)
        if planar not in (1, 2):
            raise GeoTiffError("PlanarConfiguration inválida.")
        for tag, name in ((TAG_STRIP_OFFSETS, "StripOffsets"),
                          (TAG_STRIP_BYTE_COUNTS, "StripByteCounts")):
            if tag not in self._entries:
                raise GeoTiffError(f"Falta la etiqueta TIFF obligatoria {name} ({tag}).")
        self.rows_per_strip = min(
            self._single_int(TAG_ROWS_PER_STRIP, "RowsPerStrip", self.height), self.height
        )
        if self.rows_per_strip < 1:
            raise GeoTiffError("RowsPerStrip debe ser positivo.")
        self.strip_count = math.ceil(self.height / self.rows_per_strip)
        for tag in (TAG_STRIP_OFFSETS, TAG_STRIP_BYTE_COUNTS):
            if self._entries[tag].count != self.strip_count:
                raise GeoTiffError(
                    "El número de strips no coincide con ImageLength/RowsPerStrip."
                )
        self.row_bytes = self.width * 2
        self.dtype = np.dtype(self._bo + "i2")

    def _geo_keys(self) -> dict[int, Any]:
        if TAG_GEO_KEY_DIRECTORY not in self._entries:
            raise GeoTiffError("El TIFF no contiene GeoKeyDirectory: no está georreferenciado.")
        directory = self._values(TAG_GEO_KEY_DIRECTORY)
        if isinstance(directory, str) or len(directory) < 4:
            raise GeoTiffError("GeoKeyDirectory inválido.")
        number = int(directory[3])
        if len(directory) < 4 + 4 * number:
            raise GeoTiffError("GeoKeyDirectory truncado.")
        doubles = (
            self._values(TAG_GEO_DOUBLE_PARAMS)
            if TAG_GEO_DOUBLE_PARAMS in self._entries else ()
        )
        ascii_params = (
            self._values(TAG_GEO_ASCII_PARAMS)
            if TAG_GEO_ASCII_PARAMS in self._entries else ""
        )
        keys: dict[int, Any] = {}
        for index in range(number):
            key, location, count, value = directory[4 + 4 * index: 8 + 4 * index]
            if location == 0:
                keys[key] = value
            elif location == TAG_GEO_DOUBLE_PARAMS:
                selected = tuple(doubles[value:value + count])
                if len(selected) != count:
                    raise GeoTiffError(f"GeoKey {key} apunta fuera de GeoDoubleParams.")
                keys[key] = selected[0] if count == 1 else selected
            elif location == TAG_GEO_ASCII_PARAMS:
                assert isinstance(ascii_params, str)
                keys[key] = ascii_params[value:value + count].rstrip("|\x00")
        return keys

    def _validate_georeference(self) -> None:
        if TAG_MODEL_TRANSFORMATION in self._entries:
            raise GeoTiffError("ModelTransformation no soportado; se requiere escala + punto de enlace.")
        keys = self._geo_keys()
        if keys.get(KEY_MODEL_TYPE) != MODEL_TYPE_GEOGRAPHIC:
            raise GeoTiffError(
                "Solo se admiten GeoTIFF geográficos (latitud/longitud en grados)."
            )
        if keys.get(KEY_RASTER_TYPE, RASTER_PIXEL_IS_AREA) != RASTER_PIXEL_IS_AREA:
            raise GeoTiffError("Solo se admite RasterPixelIsArea.")
        if keys.get(KEY_GEOG_ANGULAR_UNITS) != ANGULAR_UNIT_DEGREE:
            raise GeoTiffError("La unidad angular del GeoTIFF debe declararse en grados (9102).")
        semi_major = keys.get(KEY_SEMI_MAJOR_AXIS)
        if not isinstance(semi_major, float) or not math.isfinite(semi_major) or semi_major <= 0:
            raise GeoTiffError(
                "El GeoTIFF no declara el semieje mayor del cuerpo; no se supone un radio."
            )
        semi_minor = keys.get(KEY_SEMI_MINOR_AXIS)
        inv_flattening = keys.get(KEY_INV_FLATTENING)
        spherical = (
            (isinstance(semi_minor, float) and math.isclose(semi_minor, semi_major, abs_tol=0.1))
            or (semi_minor is None and isinstance(inv_flattening, float) and inv_flattening == 0.0)
        )
        if not spherical:
            raise GeoTiffError("El cálculo de pendiente requiere un modelo esférico.")
        prime = keys.get(KEY_PRIME_MERIDIAN_LONG, 0.0)
        if not isinstance(prime, (int, float)) or prime != 0:
            raise GeoTiffError("Solo se admite el meridiano de referencia en 0°.")
        self.radius_m = float(semi_major)
        self.citation = str(keys.get(KEY_GEOG_CITATION, ""))

        for tag, name in ((TAG_MODEL_PIXEL_SCALE, "ModelPixelScale"),
                          (TAG_MODEL_TIEPOINT, "ModelTiepoint")):
            if tag not in self._entries:
                raise GeoTiffError(f"Falta la etiqueta GeoTIFF {name}.")
        scale = self._values(TAG_MODEL_PIXEL_SCALE)
        tie = self._values(TAG_MODEL_TIEPOINT)
        if isinstance(scale, str) or len(scale) < 2 or isinstance(tie, str) or len(tie) != 6:
            raise GeoTiffError("Se requiere ModelPixelScale y exactamente un ModelTiepoint.")
        scale_x, scale_y = float(scale[0]), float(scale[1])
        if not (scale_x > 0 and scale_y > 0 and math.isfinite(scale_x) and math.isfinite(scale_y)):
            raise GeoTiffError("ModelPixelScale debe ser positivo y finito.")
        if not math.isclose(scale_x, scale_y, rel_tol=1e-9):
            raise GeoTiffError("Se requieren píxeles cuadrados en grados.")
        self.pixel_scale_deg = scale_x
        tie_i, tie_j, _, tie_x, tie_y, _ = (float(v) for v in tie)
        self.origin_lon = tie_x - tie_i * scale_x
        self.origin_lat = tie_y + tie_j * scale_y
        self.end_lon = self.origin_lon + self.width * scale_x
        self.end_lat = self.origin_lat - self.height * scale_y
        if self.origin_lat > 90.0 + 1e-6 or self.end_lat < -90.0 - 1e-6:
            raise GeoTiffError("La extensión en latitud del GeoTIFF sale de [-90, 90].")
        if self.end_lon - self.origin_lon > 360.0 + 1e-6:
            raise GeoTiffError("La extensión en longitud del GeoTIFF supera 360°.")
        self.pixels_per_degree = 1.0 / scale_x
        self.cell_size_m = self.radius_m * math.radians(scale_x)

        self.nodata: Optional[int] = None
        if TAG_GDAL_NODATA in self._entries:
            text = self._values(TAG_GDAL_NODATA)
            try:
                value = float(str(text).strip())
            except ValueError as exc:
                raise GeoTiffError(f"GDAL_NODATA no numérico: {text!r}.") from exc
            if value.is_integer() and -32768 <= value <= 32767:
                self.nodata = int(value)

    # -------------------------------------------------------------- windows
    def _longitude_shift(self, bounds: GeographicBounds) -> float:
        for shift in (0.0, -360.0, 360.0):
            if (self.origin_lon - 1e-9 <= bounds.west + shift
                    and bounds.east + shift <= self.end_lon + 1e-9):
                return shift
        raise GeoTiffError(
            "La ventana no cabe en la cobertura en longitud del GeoTIFF "
            f"({self.origin_lon}° a {self.end_lon}°) o cruza su borde."
        )

    def pixel_window(self, bounds: GeographicBounds, *, align: int = 1) -> PixelWindow:
        """File pixel ranges covering `bounds`, with sizes that are multiples of `align`.

        The window starts at the pixel containing the north-west corner and is
        extended south/east as needed. The result depends only on geography,
        so a raw clip of this file reprocessed with the same bounds gives the
        same pixels and blocks. (The verified USGS DEM spans 359.998°, so its
        grid is not aligned with 0°E and no global block lattice is assumed.)
        """
        bounds.validate()
        if isinstance(align, bool) or not isinstance(align, int) or align < 1:
            raise GeoTiffError("align debe ser un entero positivo.")
        if bounds.north > self.origin_lat + 1e-9 or bounds.south < self.end_lat - 1e-9:
            raise GeoTiffError("La ventana sale de la cobertura en latitud del GeoTIFF.")
        shift = self._longitude_shift(bounds)
        ppd = self.pixels_per_degree
        row_start = math.floor((self.origin_lat - bounds.north) * ppd + _EDGE_EPSILON)
        row_stop = math.ceil((self.origin_lat - bounds.south) * ppd - _EDGE_EPSILON)
        col_start = math.floor((bounds.west + shift - self.origin_lon) * ppd + _EDGE_EPSILON)
        col_stop = math.ceil((bounds.east + shift - self.origin_lon) * ppd - _EDGE_EPSILON)

        row_stop = row_start + -(-(row_stop - row_start) // align) * align
        col_stop = col_start + -(-(col_stop - col_start) // align) * align
        if row_start < 0 or col_start < 0 or row_stop > self.height or col_stop > self.width:
            raise GeoTiffError("La ventana alineada sale de los límites del GeoTIFF.")
        if row_stop - row_start < 2 or col_stop - col_start < 2:
            raise GeoTiffError("La ventana debe incluir al menos 2 filas y 2 columnas.")
        return PixelWindow(row_start, row_stop, col_start, col_stop)

    def read_raw(self, window: PixelWindow, *, margin: int = 0,
                 max_cells: int = MAX_WINDOW_CELLS) -> RawClip:
        """Copy raw samples of `window` plus up to `margin` pixels on each side."""
        if margin < 0:
            raise GeoTiffError("margin no puede ser negativo.")
        r0 = max(0, window.row_start - margin)
        r1 = min(self.height, window.row_stop + margin)
        c0 = max(0, window.col_start - margin)
        c1 = min(self.width, window.col_stop + margin)
        if (r1 - r0) * (c1 - c0) > max_cells:
            raise GeoTiffError(
                f"La ventana requiere {(r1 - r0) * (c1 - c0)} píxeles; el máximo es "
                f"{max_cells}. Use una región menor."
            )
        first_strip = r0 // self.rows_per_strip
        last_strip = (r1 - 1) // self.rows_per_strip
        offsets = self._value_slice(TAG_STRIP_OFFSETS, first_strip, last_strip + 1)
        counts = self._value_slice(TAG_STRIP_BYTE_COUNTS, first_strip, last_strip + 1)
        values = np.empty((r1 - r0, c1 - c0), dtype=np.int16)
        for row in range(r0, r1):
            strip = row // self.rows_per_strip
            strip_rows = min(self.rows_per_strip, self.height - strip * self.rows_per_strip)
            if counts[strip - first_strip] != strip_rows * self.row_bytes:
                raise GeoTiffError(
                    "StripByteCounts no corresponde a un raster int16 sin compresión."
                )
            start = (offsets[strip - first_strip]
                     + (row - strip * self.rows_per_strip) * self.row_bytes + c0 * 2)
            chunk = self.source.read(start, (c1 - c0) * 2)
            values[row - r0] = np.frombuffer(chunk, dtype=self.dtype)
        return RawClip(values=values, row_start=r0, col_start=c0)

    def to_mola_window(self, clip: RawClip, window: PixelWindow,
                       bounds: GeographicBounds) -> MolaWindow:
        """Derive validity and slope on the clip (margin included) and trim to `window`."""
        elevations = clip.values.astype(np.float32)
        valid = np.ones(elevations.shape, dtype=np.bool_)
        if self.nodata is not None:
            valid &= clip.values != self.nodata
        elevations[~valid] = np.nan
        clip_north = self.origin_lat - clip.row_start * self.pixel_scale_deg
        slopes = compute_slope_deg(
            elevations,
            valid,
            north_edge_deg=clip_north,
            pixels_per_degree_y=self.pixels_per_degree,
            cell_size_m=self.cell_size_m,
        )
        rs = slice(window.row_start - clip.row_start, window.row_stop - clip.row_start)
        cs = slice(window.col_start - clip.col_start, window.col_stop - clip.col_start)
        if rs.start < 0 or cs.start < 0 or rs.stop > elevations.shape[0] or cs.stop > elevations.shape[1]:
            raise GeoTiffError("El recorte no contiene la ventana solicitada.")
        shift = self._longitude_shift(bounds)
        return DemWindow(
            elevation_m=np.ascontiguousarray(elevations[rs, cs]),
            valid=np.ascontiguousarray(valid[rs, cs]),
            slope_deg=np.ascontiguousarray(slopes[rs, cs]),
            row_offset=window.row_start,
            col_offset=window.col_start,
            pixels_per_degree_x=self.pixels_per_degree,
            pixels_per_degree_y=self.pixels_per_degree,
            west_edge_deg=self.origin_lon + window.col_start * self.pixel_scale_deg - shift,
            north_edge_deg=self.origin_lat - window.row_start * self.pixel_scale_deg,
            cell_size_m=self.cell_size_m,
        )

    def read_window(self, bounds: GeographicBounds, *, align: int = 1,
                    margin: int = 1, max_cells: int = MAX_WINDOW_CELLS) -> "DemWindow":
        """Read the pixels covering `bounds` and derive slope (with a 1 px margin)."""
        window = self.pixel_window(bounds, align=align)
        clip = self.read_raw(window, margin=margin, max_cells=max_cells)
        return self.to_mola_window(clip, window, bounds)

    def clip_origin(self, clip: RawClip) -> tuple[float, float]:
        """(west longitude, north latitude) of the clip's top-left corner, in file frame."""
        return (
            self.origin_lon + clip.col_start * self.pixel_scale_deg,
            self.origin_lat - clip.row_start * self.pixel_scale_deg,
        )


# ------------------------------------------------------------------ writer
def _encode_entry_values(bo: str, typ: int, values: Any) -> tuple[int, bytes]:
    fmt, size = _TYPE_FORMATS[typ]
    if typ == 2:
        data = (values if isinstance(values, bytes) else str(values).encode("ascii")) + b"\x00"
        return len(data), data
    seq = list(values) if isinstance(values, (list, tuple)) else [values]
    return len(seq), struct.pack(bo + fmt * len(seq), *seq)


def write_geotiff_int16(
    path: Path | str,
    elevation: NDArray[np.integer],
    *,
    origin_lon: float,
    origin_lat: float,
    pixel_scale_deg: float,
    radius_m: float,
    nodata: Optional[int] = -32768,
    citation: str = "Mars sphere",
    byteorder: str = "<",
    bigtiff: bool = False,
    rows_per_strip: int = 1,
    tag_overrides: Optional[dict[int, tuple[int, Any]]] = None,
    drop_tags: frozenset[int] | set[int] = frozenset(),
    overwrite: bool = False,
) -> Path:
    """Write a minimal uncompressed single-band int16 geographic GeoTIFF.

    Used to store small raw DEM clips and to build test fixtures.
    `tag_overrides`/`drop_tags` exist so tests can create unsupported files.
    """
    if byteorder not in ("<", ">"):
        raise ValueError("byteorder debe ser '<' o '>'.")
    array = np.asarray(elevation)
    if array.ndim != 2:
        raise ValueError("Se requiere un arreglo 2D.")
    height, width = array.shape
    rows_per_strip = max(1, min(rows_per_strip, height))
    image = array.astype(byteorder + "i2").tobytes()
    row_bytes = width * 2
    strips = math.ceil(height / rows_per_strip)
    header_size = 16 if bigtiff else 8
    strip_offsets = [header_size + i * rows_per_strip * row_bytes for i in range(strips)]
    strip_counts = [min(rows_per_strip, height - i * rows_per_strip) * row_bytes
                    for i in range(strips)]
    offset_type = 16 if bigtiff else 4
    citation_text = citation + "|"
    tags: dict[int, tuple[int, Any]] = {
        TAG_IMAGE_WIDTH: (4, width),
        TAG_IMAGE_LENGTH: (4, height),
        TAG_BITS_PER_SAMPLE: (3, 16),
        TAG_COMPRESSION: (3, 1),
        TAG_PHOTOMETRIC: (3, 1),
        TAG_STRIP_OFFSETS: (offset_type, strip_offsets),
        TAG_SAMPLES_PER_PIXEL: (3, 1),
        TAG_ROWS_PER_STRIP: (4, rows_per_strip),
        TAG_STRIP_BYTE_COUNTS: (offset_type, strip_counts),
        TAG_PLANAR_CONFIG: (3, 1),
        TAG_SAMPLE_FORMAT: (3, 2),
        TAG_MODEL_PIXEL_SCALE: (12, [pixel_scale_deg, pixel_scale_deg, 0.0]),
        TAG_MODEL_TIEPOINT: (12, [0.0, 0.0, 0.0, origin_lon, origin_lat, 0.0]),
        TAG_GEO_KEY_DIRECTORY: (3, [
            1, 1, 0, 7,
            KEY_MODEL_TYPE, 0, 1, MODEL_TYPE_GEOGRAPHIC,
            KEY_RASTER_TYPE, 0, 1, RASTER_PIXEL_IS_AREA,
            KEY_GEOG_CITATION, TAG_GEO_ASCII_PARAMS, len(citation_text), 0,
            KEY_GEOG_ANGULAR_UNITS, 0, 1, ANGULAR_UNIT_DEGREE,
            KEY_SEMI_MAJOR_AXIS, TAG_GEO_DOUBLE_PARAMS, 1, 0,
            KEY_SEMI_MINOR_AXIS, TAG_GEO_DOUBLE_PARAMS, 1, 1,
            KEY_PRIME_MERIDIAN_LONG, TAG_GEO_DOUBLE_PARAMS, 1, 2,
        ]),
        TAG_GEO_DOUBLE_PARAMS: (12, [radius_m, radius_m, 0.0]),
        TAG_GEO_ASCII_PARAMS: (2, citation_text),
    }
    if nodata is not None:
        tags[TAG_GDAL_NODATA] = (2, str(int(nodata)))
    tags.update(tag_overrides or {})
    for tag in drop_tags:
        tags.pop(tag, None)

    bo = byteorder
    ifd_offset = header_size + len(image)
    ifd_offset += ifd_offset % 2
    count_fmt, count_size, entry_size, value_size, ptr_fmt = (
        ("Q", 8, 20, 8, "Q") if bigtiff else ("H", 2, 12, 4, "I")
    )
    ifd_size = count_size + len(tags) * entry_size + value_size
    extra_offset = ifd_offset + ifd_size
    entries = bytearray(struct.pack(bo + count_fmt, len(tags)))
    extra = bytearray()
    for tag in sorted(tags):
        typ, values = tags[tag]
        count, data = _encode_entry_values(bo, typ, values)
        if bigtiff:
            entries += struct.pack(bo + "HHQ", tag, typ, count)
        else:
            entries += struct.pack(bo + "HHI", tag, typ, count)
        if len(data) <= value_size:
            entries += data.ljust(value_size, b"\x00")
        else:
            entries += struct.pack(bo + ptr_fmt, extra_offset + len(extra))
            extra += data
            if len(extra) % 2:
                extra += b"\x00"
    entries += b"\x00" * value_size  # No next IFD.

    marker = b"II" if bo == "<" else b"MM"
    if bigtiff:
        header = marker + struct.pack(bo + "HHHQ", 43, 8, 0, ifd_offset)
    else:
        header = marker + struct.pack(bo + "HI", 42, ifd_offset)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = header + image + b"\x00" * (ifd_offset - header_size - len(image)) + entries + extra
    with output.open("wb" if overwrite else "xb") as stream:
        stream.write(payload)
    return output
