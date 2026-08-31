"""Tests for the HTML report module."""
from __future__ import annotations

import json
from pathlib import Path

from mutagen.id3 import APIC, ID3

from coverart_cli.report import (
    MAX_THUMB_BYTES,
    AlbumEntry,
    _make_data_uri,
    build_report,
    scan_library,
)

# Minimal valid JPEG (10x10 yellow) — 631 bytes
JPEG_BYTES = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb0043000806060706050807070709"
    "0908"
)


def _make_jpeg(path: Path, payload_size: int = 3000) -> None:
    """Write a JPEG-magic-byte file with given total size."""
    path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * (payload_size - 4))


def test_album_entry_to_dict() -> None:
    e = AlbumEntry(
        artist="Pink Floyd", album="The Wall", path="Pink Floyd/The Wall",
        has_cover=True, source="lastfm", file_count=12,
        cover_data_uri="data:image/jpeg;base64,xxx",
    )
    d = e.to_dict()
    assert d["artist"] == "Pink Floyd"
    assert d["source"] == "lastfm"
    assert d["cover_data_uri"].startswith("data:image/jpeg")


def test_make_data_uri_small_file(tmp_path: Path) -> None:
    img = tmp_path / "cover.jpg"
    _make_jpeg(img, 3000)
    uri = _make_data_uri(img)
    assert uri is not None
    assert uri.startswith("data:image/jpeg;base64,")


def test_make_data_uri_uses_content_type_not_extension(tmp_path: Path) -> None:
    path = tmp_path / "cover.jpg"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 3000)
    uri = _make_data_uri(path)
    assert uri is not None
    assert uri.startswith("data:image/png;base64,")


def test_make_data_uri_rejects_invalid_image(tmp_path: Path) -> None:
    path = tmp_path / "cover.jpg"
    path.write_bytes(b"<!doctype html>" + b"x" * 3000)
    assert _make_data_uri(path) is None


def test_make_data_uri_rejects_large_file(tmp_path: Path) -> None:
    img = tmp_path / "cover.jpg"
    _make_jpeg(img, MAX_THUMB_BYTES + 100)
    assert _make_data_uri(img) is None


def test_make_data_uri_missing_file(tmp_path: Path) -> None:
    assert _make_data_uri(tmp_path / "does-not-exist.jpg") is None


def test_scan_library_empty(tmp_path: Path) -> None:
    assert scan_library(tmp_path) == []


def test_scan_library_skips_hidden(tmp_path: Path) -> None:
    hidden = tmp_path / ".cache" / "Artist" / "Album"
    hidden.mkdir(parents=True)
    (hidden / "track.mp3").write_bytes(b"x")
    assert scan_library(tmp_path) == []


def test_scan_library_finds_albums(tmp_path: Path, monkeypatch) -> None:
    a = tmp_path / "Pink Floyd" / "The Wall"
    a.mkdir(parents=True)
    (a / "01.mp3").write_bytes(b"x" * 100)
    (a / "02.mp3").write_bytes(b"x" * 100)
    _make_jpeg(a / "cover.jpg", 4000)
    monkeypatch.setattr(
        "coverart_cli.report.has_embedded_cover",
        lambda _path: (_ for _ in ()).throw(AssertionError("sidecar should short-circuit scans")),
    )

    entries = scan_library(tmp_path, embed_thumbs=True)
    assert len(entries) == 1
    e = entries[0]
    assert e.artist == "Pink Floyd"
    assert e.album == "The Wall"
    assert e.file_count == 2
    assert e.has_cover is True
    assert e.cover_data_uri is not None
    assert e.source == "manual"


def test_scan_library_missing_cover(tmp_path: Path) -> None:
    a = tmp_path / "Some Artist" / "Some Album"
    a.mkdir(parents=True)
    (a / "01.mp3").write_bytes(b"x" * 100)
    entries = scan_library(tmp_path)
    assert len(entries) == 1
    assert entries[0].has_cover is False
    assert entries[0].source == "none"
    assert entries[0].cover_data_uri is None


def test_scan_library_checks_every_track_for_embedded_cover(tmp_path: Path) -> None:
    album = tmp_path / "Some Artist" / "Some Album"
    album.mkdir(parents=True)
    for index in range(1, 5):
        tags = ID3()
        if index == 4:
            tags.add(
                APIC(
                    encoding=3,
                    mime="image/jpeg",
                    type=3,
                    desc="Cover",
                    data=b"\xff\xd8\xff" + b"x" * 3000,
                )
            )
        tags.save(album / f"{index:02d}.mp3")

    entries = scan_library(tmp_path, embed_thumbs=False)

    assert len(entries) == 1
    assert entries[0].has_cover is True


def test_build_report_substitutes_data(tmp_path: Path) -> None:
    entries = [
        AlbumEntry(
            artist="A", album="B", path="A/B",
            has_cover=False, source="none", file_count=3,
        )
    ]
    tpl = "<html>__REPORT_DATA__</html>"
    html = build_report(entries, library_path="/music", template=tpl)
    assert "__REPORT_DATA__" not in html
    payload_text = html.replace("<html>", "").replace("</html>", "")
    payload = json.loads(payload_text)
    assert payload["library_label"] == "music"
    assert payload["tool_version"]
    assert payload["albums"][0]["artist"] == "A"
    assert "path" not in payload["albums"][0]


def test_build_report_strips_home_path_from_library_label() -> None:
    html = build_report([], library_path="/Users/alice/Music")
    assert "/Users/alice" not in html
    assert '"library_label": "Music"' in html


def test_build_report_strips_windows_path_from_library_label() -> None:
    html = build_report([], library_path=r"C:\Users\alice\Music")
    assert r"C:\Users\alice" not in html
    assert '"library_label": "Music"' in html


def test_build_report_escapes_closing_script_tags() -> None:
    """JSON containing </script> would break the document — we escape it."""
    entries = [
        AlbumEntry(
            artist="Hax</script><script>alert(1)</script>",
            album="x", path="x",
            has_cover=False, source="none", file_count=1,
        )
    ]
    tpl = "__REPORT_DATA__"
    html = build_report(entries, library_path=".", template=tpl)
    assert "</script>" not in html
    assert "<\\/script>" in html


def test_real_template_substitutes() -> None:
    """The bundled template must still contain the placeholder before substitution
    and not after."""
    from coverart_cli.report import _read_template

    tpl = _read_template()
    assert "__REPORT_DATA__" in tpl
    html = build_report([], library_path="/tmp")
    assert "__REPORT_DATA__" not in html
    assert "Library" in html
    assert "fonts.googleapis.com" not in html
