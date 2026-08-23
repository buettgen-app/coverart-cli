"""End-to-end integration tests using a deterministic mock provider.

These verify the full pipeline works:
  - scan a fixture library
  - call a provider (mocked, no network)
  - embed in MP3, write cover.jpg sidecar
  - generate HTML report
  - skip-already-covered semantics
  - --min-bytes upgrade behaviour
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, TPE2

from coverart_cli.core import RunOptions, run
from coverart_cli.providers.base import CoverProvider, ProviderResult
from coverart_cli.report import write_report

# Real JPEG SOI bytes followed by enough padding to pass the MIN_COVER_BYTES check.
FAKE_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 3000


class FakeProvider(CoverProvider):
    """Returns a fixed JPEG for any artist/album. Recorded for assertions."""

    name = "fake"

    def __init__(self, image_bytes: bytes = FAKE_JPEG) -> None:
        self.image_bytes = image_bytes
        self.calls: list[tuple[str, str]] = []
        self.user_agent = "test/1.0"

    def fetch(self, artist: str, album: str) -> ProviderResult | None:
        self.calls.append((artist, album))
        return ProviderResult(
            image_bytes=self.image_bytes,
            source=self.name,
            image_url="file:///fake",
        )


class NeverFindProvider(CoverProvider):
    """A provider that never returns anything — for miss-path testing."""

    name = "never"

    def __init__(self) -> None:
        self.user_agent = "test/1.0"

    def fetch(self, artist: str, album: str) -> ProviderResult | None:  # noqa: ARG002
        return None


def _make_album(tmp: Path, artist: str, album: str, tracks: int = 2) -> Path:
    album_dir = tmp / artist / album
    album_dir.mkdir(parents=True, exist_ok=True)
    for i in range(1, tracks + 1):
        track = album_dir / f"{i:02d}.mp3"
        # Minimal MP3-ish payload: frame sync + silence padding.
        track.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 1000)
        tags = ID3()
        tags.add(TPE1(encoding=3, text=[artist]))
        tags.add(TPE2(encoding=3, text=[artist]))
        tags.add(TALB(encoding=3, text=[album]))
        tags.add(TIT2(encoding=3, text=[f"Track {i}"]))
        tags.save(str(track))
    return album_dir


def test_end_to_end_fetch_embed_sidecar(tmp_path: Path) -> None:
    album_dir = _make_album(tmp_path, "Pink Floyd", "The Wall", tracks=3)
    provider = FakeProvider()

    stats = run(RunOptions(root=tmp_path, providers=[provider]))

    # Provider was called exactly once per album.
    assert provider.calls == [("Pink Floyd", "The Wall")]
    assert stats.albums_total == 1
    assert stats.fetched_from == {"fake": 1}
    assert stats.files_embedded == 3
    assert stats.errors == 0

    # Sidecar written next to the tracks.
    sidecar = album_dir / "cover.jpg"
    assert sidecar.exists()
    assert sidecar.read_bytes() == FAKE_JPEG

    # Each MP3 now has an APIC frame.
    for track in sorted(album_dir.glob("*.mp3")):
        tags = ID3(track)
        assert any(k.startswith("APIC") for k in tags), f"missing APIC in {track.name}"


def test_existing_sidecar_fills_missing_embeds_without_network(tmp_path: Path) -> None:
    album_dir = _make_album(tmp_path, "Pink Floyd", "The Wall")
    (album_dir / "cover.jpg").write_bytes(b"\xff\xd8\xff" + b"x" * 4000)
    provider = FakeProvider()

    stats = run(RunOptions(root=tmp_path, providers=[provider]))

    # Provider is not needed: reuse the local sidecar for the missing embeds.
    assert provider.calls == []
    assert stats.albums_total == 1
    assert stats.files_embedded == 2
    for track in album_dir.glob("*.mp3"):
        assert any(k.startswith("APIC") for k in ID3(track))


def test_atomic_sidecar_write_replaces_symlink_without_touching_target(tmp_path: Path) -> None:
    library = tmp_path / "library"
    album_dir = _make_album(library, "Pink Floyd", "The Wall")
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"keep me")
    sidecar = album_dir / "cover.jpg"
    sidecar.symlink_to(outside)

    run(
        RunOptions(
            root=library,
            providers=[FakeProvider()],
            do_embed=False,
        )
    )

    assert outside.read_bytes() == b"keep me"
    assert not sidecar.is_symlink()
    assert sidecar.read_bytes() == FAKE_JPEG


def test_audio_symlink_is_not_modified(tmp_path: Path) -> None:
    library = tmp_path / "library"
    album_dir = _make_album(library, "Pink Floyd", "The Wall", tracks=1)
    outside_album = _make_album(tmp_path / "outside", "Other", "External", tracks=1)
    outside_track = outside_album / "01.mp3"
    (album_dir / "02.mp3").symlink_to(outside_track)

    stats = run(RunOptions(root=library, providers=[FakeProvider()]))

    assert stats.files_embedded == 1
    assert not any(k.startswith("APIC") for k in ID3(outside_track))


def test_directory_symlink_is_not_scanned(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    outside_album = _make_album(tmp_path / "outside", "Other", "External", tracks=1)
    (library / "linked-album").symlink_to(outside_album, target_is_directory=True)

    stats = run(RunOptions(root=library, providers=[FakeProvider()]))

    assert stats.albums_total == 0
    assert not any(k.startswith("APIC") for k in ID3(outside_album / "01.mp3"))


def test_hidden_tree_is_not_scanned(tmp_path: Path) -> None:
    _make_album(tmp_path / ".cache", "Artist", "Album", tracks=1)
    stats = run(RunOptions(root=tmp_path, providers=[FakeProvider()]))
    assert stats.albums_total == 0


def test_upgrade_replaces_small_existing_sidecar(tmp_path: Path) -> None:
    album_dir = _make_album(tmp_path, "Pink Floyd", "The Wall")
    small = b"\xff\xd8\xff" + b"x" * 3000  # 3007 bytes, below threshold of 10_000
    (album_dir / "cover.jpg").write_bytes(small)
    provider = FakeProvider()

    stats = run(
        RunOptions(
            root=tmp_path,
            providers=[provider],
            min_sidecar_bytes=10_000,
            min_embedded_bytes=10_000,
            keep_larger_existing=False,
        )
    )

    assert provider.calls == [("Pink Floyd", "The Wall")]
    assert stats.fetched_from == {"fake": 1}
    assert (album_dir / "cover.jpg").read_bytes() == FAKE_JPEG


def test_upgrade_replaces_embedded_cover_in_one_save(tmp_path: Path) -> None:
    album_dir = _make_album(tmp_path, "Pink Floyd", "The Wall", tracks=1)
    track = album_dir / "01.mp3"
    tags = ID3(track)
    tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=b"old"))
    tags.save(track, v2_version=3)

    stats = run(
        RunOptions(
            root=tmp_path,
            providers=[FakeProvider()],
            do_sidecar=False,
            min_embedded_bytes=100,
        )
    )

    pictures = [frame for frame in ID3(track).values() if isinstance(frame, APIC)]
    assert stats.files_embedded == 1
    assert [cast(Any, picture).data for picture in pictures] == [FAKE_JPEG]


def test_provider_fallback_chain(tmp_path: Path) -> None:
    _make_album(tmp_path, "Some Band", "Some Album")
    miss = NeverFindProvider()
    hit = FakeProvider()

    stats = run(RunOptions(root=tmp_path, providers=[miss, hit]))

    assert stats.fetched_from == {"fake": 1}


def test_all_providers_miss_records_not_found(tmp_path: Path) -> None:
    _make_album(tmp_path, "Some Band", "Some Album")
    miss = NeverFindProvider()

    stats = run(RunOptions(root=tmp_path, providers=[miss]))

    assert stats.not_found == 1
    assert stats.fetched_from == {}
    assert len(stats.misses) == 1


def test_html_report_after_run(tmp_path: Path) -> None:
    _make_album(tmp_path, "Pink Floyd", "The Wall")
    run(RunOptions(root=tmp_path, providers=[FakeProvider()]))

    out = tmp_path / "report.html"
    written, n_albums = write_report(tmp_path, out)
    assert written == out
    assert n_albums == 1
    html = out.read_text(encoding="utf-8")
    assert "Pink Floyd" in html
    assert "The Wall" in html
    # The cover should be embedded as a base64 data URI in the report.
    assert "data:image/jpeg;base64" in html


def test_dry_run_changes_nothing(tmp_path: Path) -> None:
    album_dir = _make_album(tmp_path, "Pink Floyd", "The Wall")
    provider = FakeProvider()

    stats = run(RunOptions(root=tmp_path, providers=[provider], dry_run=True))

    # Provider was consulted (so we know what would happen)…
    assert provider.calls == [("Pink Floyd", "The Wall")]
    # …but nothing was written.
    assert not (album_dir / "cover.jpg").exists()
    assert stats.files_embedded == 0


@pytest.mark.parametrize("flag", ["do_embed", "do_sidecar"])
def test_partial_output_modes(tmp_path: Path, flag: str) -> None:
    album_dir = _make_album(tmp_path, "Pink Floyd", "The Wall")

    run(
        RunOptions(
            root=tmp_path,
            providers=[FakeProvider()],
            do_embed=flag == "do_embed",
            do_sidecar=flag == "do_sidecar",
        )
    )

    if flag == "do_embed":
        assert not (album_dir / "cover.jpg").exists()
        for track in album_dir.glob("*.mp3"):
            tags = ID3(track)
            assert any(k.startswith("APIC") for k in tags)
    else:
        assert (album_dir / "cover.jpg").exists()


def test_parallel_processing_correctness(tmp_path: Path) -> None:
    """20 albums processed by 8 workers must give the same stats as serial."""
    for i in range(20):
        _make_album(tmp_path, f"Artist {i:02d}", f"Album {i:02d}", tracks=2)

    provider_parallel = FakeProvider()
    stats_p = run(RunOptions(root=tmp_path, providers=[provider_parallel], workers=8))

    # Wipe sidecars so the second run actually does work.
    for sidecar in tmp_path.rglob("cover.jpg"):
        sidecar.unlink()
    # Strip embedded APIC frames.
    for track in tmp_path.rglob("*.mp3"):
        tags = ID3(track)
        tags.delall("APIC")
        tags.save(str(track), v2_version=3)

    provider_serial = FakeProvider()
    stats_s = run(RunOptions(root=tmp_path, providers=[provider_serial], workers=1))

    assert stats_p.albums_total == stats_s.albums_total == 20
    assert stats_p.fetched_from == stats_s.fetched_from == {"fake": 20}
    assert stats_p.files_embedded == stats_s.files_embedded == 40
    assert stats_p.errors == stats_s.errors == 0
    assert sorted(provider_parallel.calls) == sorted(provider_serial.calls)
