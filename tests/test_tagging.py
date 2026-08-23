"""Smoke tests for tagging module."""
from __future__ import annotations

from pathlib import Path

import pytest

from coverart_cli.tagging import (
    AlbumMeta,
    detect_image_mime,
    find_sidecar,
)


def test_album_meta_str() -> None:
    m = AlbumMeta(artist="Pink Floyd", album="The Wall")
    assert str(m) == "Pink Floyd / The Wall"


@pytest.mark.parametrize(
    ("magic", "expected"),
    [
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 8, "image/png"),
        (b"\xff\xd8\xff\xe0\x00\x10JFIF", "image/jpeg"),
        (b"GIF89a" + b"\x00" * 10, "image/gif"),
        (b"RIFFxxxxWEBP" + b"\x00" * 20, "image/webp"),
        (b"garbage", "image/jpeg"),  # fallback
    ],
)
def test_detect_image_mime(magic: bytes, expected: str) -> None:
    assert detect_image_mime(magic) == expected


def test_find_sidecar_present(tmp_path: Path) -> None:
    cover = tmp_path / "cover.jpg"
    cover.write_bytes(b"x" * 3000)
    assert find_sidecar(tmp_path) == cover


def test_find_sidecar_too_small(tmp_path: Path) -> None:
    cover = tmp_path / "cover.jpg"
    cover.write_bytes(b"x" * 500)  # below MIN_COVER_BYTES
    assert find_sidecar(tmp_path) is None


def test_find_sidecar_missing(tmp_path: Path) -> None:
    assert find_sidecar(tmp_path) is None


def test_find_sidecar_ignores_symlink(tmp_path: Path) -> None:
    target = tmp_path / "real.jpg"
    target.write_bytes(b"x" * 3000)
    (tmp_path / "cover.jpg").symlink_to(target)
    assert find_sidecar(tmp_path) is None


def test_find_sidecar_respects_min_bytes(tmp_path: Path) -> None:
    cover = tmp_path / "cover.jpg"
    cover.write_bytes(b"x" * 10_000)
    # default threshold: this one is fine
    assert find_sidecar(tmp_path) == cover
    # tightened threshold rejects it
    assert find_sidecar(tmp_path, min_bytes=20_000) is None
    assert find_sidecar(tmp_path, min_bytes=5_000) == cover
