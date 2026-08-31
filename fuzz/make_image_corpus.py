"""Create deterministic valid JPEG/PNG seeds for the binary image fuzzer."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: make_image_corpus.py OUTPUT_DIR")
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (32, 32), "navy")
    image.save(output / "valid.jpg", format="JPEG")
    image.save(output / "valid.png", format="PNG")


if __name__ == "__main__":
    main()
