"""Render a compact, colorized global MOLA preview for the frontend."""

from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path

import numpy as np

if __package__:
    from .mola_reader import DEFAULT_IMAGE, MolaReader
else:
    from mola_reader import DEFAULT_IMAGE, MolaReader

PREVIEW_WIDTH = 720
PREVIEW_HEIGHT = 360
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "frontend" / "assets" / "mola-global.png"
COLOR_STOPS = (
    (-8000, (75, 0, 190)),
    (-5000, (32, 54, 255)),
    (-2500, (0, 174, 255)),
    (-700, (0, 220, 165)),
    (0, (154, 231, 40)),
    (1800, (255, 218, 0)),
    (4000, (255, 111, 20)),
    (6500, (235, 35, 25)),
    (8000, (255, 245, 226)),
)


def _chunk(kind: bytes, payload: bytes) -> bytes:
    content = kind + payload
    return struct.pack(">I", len(payload)) + content + struct.pack(
        ">I", zlib.crc32(content) & 0xFFFFFFFF
    )


def _colorize(elevations: np.ndarray, valid: np.ndarray) -> np.ndarray:
    stops = np.asarray([stop[0] for stop in COLOR_STOPS], dtype=np.float32)
    colors = np.asarray([stop[1] for stop in COLOR_STOPS], dtype=np.float32)
    pixels = np.zeros((*elevations.shape, 4), dtype=np.uint8)
    values = np.nan_to_num(elevations, nan=0.0)
    for channel in range(3):
        pixels[:, :, channel] = np.interp(
            values, stops, colors[:, channel]
        ).astype(np.uint8)
    pixels[:, :, 3] = np.where(valid, 245, 0).astype(np.uint8)
    return pixels


def render_preview(
    output: Path = DEFAULT_OUTPUT,
    image_path: Path = DEFAULT_IMAGE,
) -> Path:
    """Write the full-planet preview, averaging native MOLA pixels into 0.5° cells."""
    reader = MolaReader(image_path)
    elevations, valid = reader.read_global_preview(PREVIEW_WIDTH, PREVIEW_HEIGHT)
    pixels = _colorize(elevations, valid)
    scanlines = b"".join(
        b"\x00" + pixels[row].tobytes() for row in range(PREVIEW_HEIGHT)
    )
    header = struct.pack(">IIBBBBB", PREVIEW_WIDTH, PREVIEW_HEIGHT, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(scanlines, level=9))
        + _chunk(b"IEND", b"")
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(png)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    args = parser.parse_args()
    output = render_preview(args.output, args.image)
    print(
        f"Vista global MOLA generada: {output} "
        f"({PREVIEW_WIDTH} × {PREVIEW_HEIGHT}, 0,5°/píxel)"
    )


if __name__ == "__main__":
    main()
