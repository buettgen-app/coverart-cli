"""Atheris target for untrusted JPEG/PNG container validation."""

from __future__ import annotations

import sys

import atheris  # type: ignore[missing-import]

with atheris.instrument_imports():  # pyrefly: ignore [missing-attribute]
    from coverart_cli.tagging import detect_image_mime


def TestOneInput(data: bytes) -> None:  # noqa: N802 - Atheris convention
    mime = detect_image_mime(data)
    if mime not in {None, "image/jpeg", "image/png"}:
        raise AssertionError("image validator returned an unsupported MIME")
    if mime == "image/jpeg" and not (data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9")):
        raise AssertionError("JPEG classification violated its framing invariant")
    if mime == "image/png" and not (
        data.startswith(b"\x89PNG\r\n\x1a\n") and data.endswith(b"\x00\x00\x00\x00IEND\xaeB`\x82")
    ):
        raise AssertionError("PNG classification violated its framing invariant")


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
