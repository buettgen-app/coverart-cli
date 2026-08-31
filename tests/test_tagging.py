"""Smoke tests for tagging module."""
from __future__ import annotations

from pathlib import Path

import pytest
from mutagen.id3 import ID3

from coverart_cli.tagging import (
    AlbumMeta,
    detect_image_mime,
    embed_cover,
    find_sidecar,
    write_sidecar,
)


def test_album_meta_str() -> None:
    m = AlbumMeta(artist="Pink Floyd", album="The Wall")
    assert str(m) == "Pink Floyd / The Wall"


@pytest.mark.parametrize(
    ("magic", "expected"),
    [
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 8, "image/png"),
        (b"\xff\xd8\xff\xe0\x00\x10JFIF", "image/jpeg"),
        (b"GIF89a" + b"\x00" * 10, None),
        (b"RIFFxxxxWEBP" + b"\x00" * 20, None),
        (b"garbage", None),
    ],
)
def test_detect_image_mime(magic: bytes, expected: str | None) -> None:
    assert detect_image_mime(magic) == expected


def test_find_sidecar_present(tmp_path: Path) -> None:
    cover = tmp_path / "cover.jpg"
    cover.write_bytes(b"\xff\xd8\xff" + b"x" * 3000)
    assert find_sidecar(tmp_path) == cover


def test_find_sidecar_rejects_invalid_image(tmp_path: Path) -> None:
    cover = tmp_path / "cover.jpg"
    cover.write_bytes(b"<!doctype html>" + b"x" * 3000)
    assert find_sidecar(tmp_path) is None


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
    cover.write_bytes(b"\xff\xd8\xff" + b"x" * 10_000)
    # default threshold: this one is fine
    assert find_sidecar(tmp_path) == cover
    # tightened threshold rejects it
    assert find_sidecar(tmp_path, min_bytes=20_000) is None
    assert find_sidecar(tmp_path, min_bytes=5_000) == cover


def test_write_sidecar_rejects_invalid_image(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported cover image"):
        write_sidecar(tmp_path, b"<!doctype html>" + b"x" * 3000)
    assert not list(tmp_path.glob("cover.*"))


def test_write_sidecar_never_mislabels_jpeg_as_png(tmp_path: Path) -> None:
    cover = b"\xff\xd8\xff" + b"x" * 3000
    written = write_sidecar(tmp_path, cover, prefer_png=True)
    assert written.name == "cover.jpg"
    assert written.read_bytes() == cover


def test_embed_cover_rejects_invalid_image(tmp_path: Path) -> None:
    track = tmp_path / "track.mp3"
    ID3().save(track)

    assert not embed_cover(track, b"<!doctype html>" + b"x" * 3000)
    assert not any(key.startswith("APIC") for key in ID3(track))
