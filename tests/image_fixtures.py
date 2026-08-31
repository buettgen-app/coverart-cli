"""Small deterministic, fully decodable images used by tests."""

from __future__ import annotations

import io

from PIL import Image


def _image_bytes(fmt: str) -> bytes:
    pixels = bytes(
        channel
        for y in range(64)
        for x in range(64)
        for channel in ((x * 37 + y * 17) % 256, (x * 11) % 256, (y * 29) % 256)
    )
    image = Image.frombytes("RGB", (64, 64), pixels)
    output = io.BytesIO()
    image.save(output, format=fmt, quality=95)
    return output.getvalue()


VALID_JPEG = _image_bytes("JPEG")
VALID_PNG = _image_bytes("PNG")
