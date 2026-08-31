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

from .image_fixtures import VALID_JPEG  # pyrefly: ignore [missing-import]

FAKE_JPEG = VALID_JPEG


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
    (album_dir / "cover.jpg").write_bytes(VALID_JPEG)
    provider = FakeProvider()

    stats = run(RunOptions(root=tmp_path, providers=[provider]))

    # Provider is not needed: reuse the local sidecar for the missing embeds.
    assert provider.calls == []
    assert stats.albums_total == 1
    assert stats.files_embedded == 2
    for track in album_dir.glob("*.mp3"):
        assert any(k.startswith("APIC") for k in ID3(track))


def test_embed_only_reuses_existing_sidecar_without_network(tmp_path: Path) -> None:
    album_dir = _make_album(tmp_path, "Pink Floyd", "The Wall")
    local_cover = VALID_JPEG
    (album_dir / "cover.jpg").write_bytes(local_cover)
    provider = FakeProvider()

    stats = run(
        RunOptions(
            root=tmp_path,
            providers=[provider],
            do_sidecar=False,
        )
    )

    assert provider.calls == []
    assert stats.files_embedded == 2
    for track in album_dir.glob("*.mp3"):
        pictures = [frame for frame in ID3(track).values() if isinstance(frame, APIC)]
        assert [cast(Any, picture).data for picture in pictures] == [local_cover]


def test_embed_only_fetches_when_sidecar_misses_quality_threshold(tmp_path: Path) -> None:
    album_dir = _make_album(tmp_path, "Pink Floyd", "The Wall", tracks=1)
    (album_dir / "cover.jpg").write_bytes(VALID_JPEG)
    provider_cover = VALID_JPEG[:-2] + b"y" * 12_000 + VALID_JPEG[-2:]
    provider = FakeProvider(provider_cover)

    stats = run(
        RunOptions(
            root=tmp_path,
            providers=[provider],
            do_sidecar=False,
            min_embedded_bytes=10_000,
        )
    )

    assert provider.calls == [("Pink Floyd", "The Wall")]
    assert stats.files_embedded == 1
    pictures = [frame for frame in ID3(album_dir / "01.mp3").values() if isinstance(frame, APIC)]
    assert [cast(Any, picture).data for picture in pictures] == [provider_cover]


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


def test_audio_hardlink_outside_library_is_not_modified(tmp_path: Path) -> None:
    outside_track = tmp_path / "outside.mp3"
    tags = ID3()
    tags.add(TPE1(encoding=3, text=["Artist"]))
    tags.add(TALB(encoding=3, text=["Album"]))
    tags.save(outside_track)
    album = tmp_path / "library" / "Artist" / "Album"
    album.mkdir(parents=True)
    (album / "01.mp3").hardlink_to(outside_track)

    stats = run(
        RunOptions(
            root=tmp_path / "library",
            providers=[FakeProvider()],
            workers=1,
            do_sidecar=False,
        )
    )

    assert stats.files_embedded == 1
    assert not any(key.startswith("APIC") for key in ID3(outside_track))


def test_audio_hardlink_created_during_embed_aborts_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import coverart_cli.tagging as tagging

    library = tmp_path / "library"
    album = _make_album(library, "Artist", "Album", tracks=1)
    track = album / "01.mp3"
    outside = tmp_path / "outside.mp3"
    original_embed = tagging._embed_mp3

    def link_then_embed(*args, **kwargs):
        outside.hardlink_to(track)
        return original_embed(*args, **kwargs)

    monkeypatch.setattr(tagging, "_embed_mp3", link_then_embed)
    stats = run(RunOptions(root=library, providers=[FakeProvider()], workers=1, do_sidecar=False))

    assert stats.files_embedded == 0
    assert stats.errors == 1
    assert not any(key.startswith("APIC") for key in ID3(track))
    assert not any(key.startswith("APIC") for key in ID3(outside))


def test_subtree_move_during_embed_discards_copy_on_write_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import coverart_cli.tagging as tagging

    library = tmp_path / "library"
    artist = library / "Artist"
    _make_album(library, "Artist", "Album", tracks=1)
    outside = tmp_path / "outside"
    outside.mkdir()
    original_embed = tagging._embed_mp3

    def move_then_embed(*args, **kwargs):
        artist.rename(outside / "Artist")
        artist.symlink_to(outside / "Artist", target_is_directory=True)
        return original_embed(*args, **kwargs)

    monkeypatch.setattr(tagging, "_embed_mp3", move_then_embed)
    stats = run(RunOptions(root=library, providers=[FakeProvider()], workers=1, do_sidecar=False))

    escaped = outside / "Artist" / "Album" / "01.mp3"
    assert stats.errors == 1
    assert not any(key.startswith("APIC") for key in ID3(escaped))


def test_audio_symlink_swap_during_fetch_is_not_followed(tmp_path: Path) -> None:
    library = tmp_path / "library"
    album_dir = _make_album(library, "Pink Floyd", "The Wall", tracks=1)
    track = album_dir / "01.mp3"
    original = album_dir / "original.mp3"
    outside_album = _make_album(tmp_path / "outside", "Other", "External", tracks=1)
    outside_track = outside_album / "01.mp3"

    class SwappingProvider(FakeProvider):
        def fetch(self, artist: str, album: str) -> ProviderResult:
            track.rename(original)
            track.symlink_to(outside_track)
            result = super().fetch(artist, album)
            assert result is not None
            return result

    stats = run(RunOptions(root=library, providers=[SwappingProvider()]))

    assert stats.errors == 1
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
    small = VALID_JPEG  # below threshold of 10_000
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


def test_invalid_provider_payload_falls_back_to_valid_cover(tmp_path: Path) -> None:
    album_dir = _make_album(tmp_path, "Some Band", "Some Album", tracks=1)
    corrupt = FakeProvider(b"<!doctype html>" + b"x" * 3000)
    valid = FakeProvider()

    stats = run(RunOptions(root=tmp_path, providers=[corrupt, valid]))

    assert corrupt.calls == [("Some Band", "Some Album")]
    assert valid.calls == [("Some Band", "Some Album")]
    assert stats.fetched_from == {"fake": 1}
    assert stats.errors == 0
    assert (album_dir / "cover.jpg").read_bytes() == FAKE_JPEG
    pictures = [frame for frame in ID3(album_dir / "01.mp3").values() if isinstance(frame, APIC)]
    assert [cast(Any, picture).data for picture in pictures] == [FAKE_JPEG]


def test_invalid_sidecar_is_ignored_and_replaced(tmp_path: Path) -> None:
    album_dir = _make_album(tmp_path, "Some Band", "Some Album", tracks=1)
    (album_dir / "cover.jpg").write_bytes(b"<!doctype html>" + b"x" * 3000)
    provider = FakeProvider()

    stats = run(RunOptions(root=tmp_path, providers=[provider]))

    assert provider.calls == [("Some Band", "Some Album")]
    assert stats.fetched_from == {"fake": 1}
    assert (album_dir / "cover.jpg").read_bytes() == FAKE_JPEG


def test_all_invalid_provider_payloads_are_not_written(tmp_path: Path) -> None:
    album_dir = _make_album(tmp_path, "Some Band", "Some Album", tracks=1)

    stats = run(
        RunOptions(
            root=tmp_path,
            providers=[FakeProvider(b"<!doctype html>" + b"x" * 3000)],
        )
    )

    assert stats.not_found == 1
    assert stats.fetched_from == {}
    assert not (album_dir / "cover.jpg").exists()
    assert not any(key.startswith("APIC") for key in ID3(album_dir / "01.mp3"))


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


def test_dry_run_preserves_existing_missing_csv(tmp_path: Path) -> None:
    _make_album(tmp_path, "Some Band", "Some Album", tracks=1)
    output = tmp_path / "missing.csv"
    output.write_text("KEEP", encoding="utf-8")

    run(
        RunOptions(
            root=tmp_path,
            providers=[NeverFindProvider()],
            dry_run=True,
            missing_csv=output,
        )
    )

    assert output.read_text(encoding="utf-8") == "KEEP"


def test_successful_run_clears_stale_missing_csv(tmp_path: Path) -> None:
    _make_album(tmp_path, "Some Band", "Some Album", tracks=1)
    output = tmp_path / "missing.csv"
    output.write_text("STALE", encoding="utf-8")

    stats = run(
        RunOptions(
            root=tmp_path,
            providers=[FakeProvider()],
            missing_csv=output,
        )
    )

    assert stats.misses == []
    assert output.read_text(encoding="utf-8") == "album_path,reason\n"


def test_provider_exception_does_not_block_fallback(tmp_path: Path) -> None:
    _make_album(tmp_path, "Some Band", "Some Album", tracks=1)

    class ExplodingProvider(CoverProvider):
        name = "exploding"

        def fetch(self, artist: str, album: str) -> ProviderResult | None:
            raise TypeError(f"schema drift for {artist}/{album}")

    fallback = FakeProvider()
    stats = run(RunOptions(root=tmp_path, providers=[ExplodingProvider(), fallback]))

    assert stats.errors == 0
    assert stats.fetched_from == {"fake": 1}


def test_all_provider_exceptions_are_reported_as_errors(tmp_path: Path) -> None:
    _make_album(tmp_path, "Some Band", "Some Album", tracks=1)

    class ExplodingProvider(CoverProvider):
        name = "exploding"

        def fetch(self, artist: str, album: str) -> ProviderResult | None:
            raise RuntimeError(f"provider unavailable for {artist}/{album}")

    stats = run(RunOptions(root=tmp_path, providers=[ExplodingProvider()]))

    assert stats.errors == 1
    assert stats.not_found == 0
    assert stats.misses[0][1] == "provider failure: exploding"


def test_uppercase_embedded_mime_preserves_existing_art(tmp_path: Path) -> None:
    album = _make_album(tmp_path, "Some Band", "Some Album", tracks=1)
    track = album / "01.mp3"
    tags = ID3(track)
    tags.add(APIC(encoding=3, mime="IMAGE/JPEG", type=3, desc="Cover", data=VALID_JPEG))
    tags.save(track)
    provider = FakeProvider()

    stats = run(RunOptions(root=tmp_path, providers=[provider], do_sidecar=False, workers=1))

    assert provider.calls == []
    assert stats.files_already_embedded == 1
    assert stats.files_embedded == 0


def test_replaced_album_directory_cannot_modify_external_track(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import coverart_cli.core as core

    album = _make_album(tmp_path / "library", "Artist", "Album", tracks=1)
    outside_album = _make_album(tmp_path / "outside-root", "Artist", "Album", tracks=1)
    external_track = outside_album / "01.mp3"
    original = core.find_sidecar
    swapped = False

    def swap_then_find(path: Path, **kwargs):
        nonlocal swapped
        if not swapped:
            swapped = True
            album.rename(album.with_name("Album-original"))
            album.symlink_to(outside_album, target_is_directory=True)
        return original(path, **kwargs)

    monkeypatch.setattr(core, "find_sidecar", swap_then_find)
    stats = run(
        RunOptions(
            root=tmp_path / "library",
            providers=[FakeProvider()],
            workers=1,
            do_sidecar=False,
        )
    )

    assert stats.errors == 1
    assert not any(key.startswith("APIC") for key in ID3(external_track))


def test_replaced_intermediate_directory_cannot_escape_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import coverart_cli.core as core

    library = tmp_path / "library"
    artist = library / "Artist"
    artist.mkdir(parents=True)
    outside_album = _make_album(tmp_path / "outside", "External Artist", "Album", tracks=1)
    external_track = outside_album / "01.mp3"
    original_scandir = core.os.scandir
    calls = 0

    def swap_before_child_scan(path):
        nonlocal calls
        calls += 1
        if calls == 2:
            artist.rename(library / "Artist-original")
            artist.symlink_to(outside_album.parent, target_is_directory=True)
        return original_scandir(path)

    monkeypatch.setattr(core.os, "scandir", swap_before_child_scan)
    monkeypatch.setattr(core, "supports_secure_library_traversal", lambda: True)
    stats = run(RunOptions(root=library, providers=[FakeProvider()], workers=1))

    assert stats.albums_total == 0
    assert not any(key.startswith("APIC") for key in ID3(external_track))


def test_moved_original_subtree_cannot_escape_library_after_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import coverart_cli.core as core

    library = tmp_path / "library"
    artist = library / "Artist"
    _make_album(library, "Artist", "Album", tracks=1)
    outside = tmp_path / "outside"
    outside.mkdir()
    original_find = core._find_album_targets

    def find_then_move(root: Path):
        targets = original_find(root)
        artist.rename(outside / "Artist")
        artist.symlink_to(outside / "Artist", target_is_directory=True)
        return targets

    monkeypatch.setattr(core, "_find_album_targets", find_then_move)
    stats = run(RunOptions(root=library, providers=[FakeProvider()], workers=1))

    assert stats.errors == 1
    assert not (outside / "Artist" / "Album" / "cover.jpg").exists()
    assert not any(key.startswith("APIC") for key in ID3(outside / "Artist" / "Album" / "01.mp3"))


def test_subtree_move_immediately_before_sidecar_write_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import coverart_cli.core as core

    library = tmp_path / "library"
    artist = library / "Artist"
    _make_album(library, "Artist", "Album", tracks=1)
    outside = tmp_path / "outside"
    outside.mkdir()
    original_write = core.write_sidecar
    moved = False

    def move_then_write(*args, **kwargs):
        nonlocal moved
        if not moved:
            moved = True
            artist.rename(outside / "Artist")
            artist.symlink_to(outside / "Artist", target_is_directory=True)
        return original_write(*args, **kwargs)

    monkeypatch.setattr(core, "write_sidecar", move_then_write)
    stats = run(RunOptions(root=library, providers=[FakeProvider()], workers=1))

    escaped_album = outside / "Artist" / "Album"
    assert stats.errors >= 1
    assert not (escaped_album / "cover.jpg").exists()
    assert not any(key.startswith("APIC") for key in ID3(escaped_album / "01.mp3"))


def test_wide_library_scan_stays_within_low_file_descriptor_limit(tmp_path: Path) -> None:
    resource = pytest.importorskip("resource")
    from coverart_cli.core import _find_album_targets

    for index in range(120):
        album = tmp_path / f"album-{index:03d}"
        album.mkdir()
        (album / "01.mp3").write_bytes(b"")
    original = resource.getrlimit(resource.RLIMIT_NOFILE)
    lowered = min(64, original[1])
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (lowered, original[1]))
        assert len(_find_album_targets(tmp_path)) == 120
    finally:
        resource.setrlimit(resource.RLIMIT_NOFILE, original)


def test_deep_library_scan_stays_within_low_file_descriptor_limit(tmp_path: Path) -> None:
    resource = pytest.importorskip("resource")
    from coverart_cli.core import _find_album_targets

    current = tmp_path
    for _ in range(100):
        current /= "d"
        current.mkdir()
    (current / "01.mp3").write_bytes(b"")
    original = resource.getrlimit(resource.RLIMIT_NOFILE)
    lowered = min(64, original[1])
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (lowered, original[1]))
        assert len(_find_album_targets(tmp_path)) == 1
    finally:
        resource.setrlimit(resource.RLIMIT_NOFILE, original)


def test_missing_csv_neutralizes_spreadsheet_formulas(tmp_path: Path) -> None:
    from coverart_cli.core import _write_missing_csv

    output = tmp_path / "missing.csv"
    _write_missing_csv(
        output,
        [(Path(name), "reason") for name in ("=1+1", "+cmd", "-2+3", " @sum(A1:A2)")],
    )

    rows = output.read_text(encoding="utf-8").splitlines()[1:]
    assert all(row.startswith("'") for row in rows)


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


def test_identical_embedded_art_is_decoded_once_per_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import coverart_cli.tagging as tagging

    album = _make_album(tmp_path, "Artist", "Album", tracks=20)
    for track in album.glob("*.mp3"):
        tags = ID3(track)
        tags.add(
            APIC(
                encoding=3,
                mime="image/jpeg",
                type=3,
                desc="Cover",
                data=VALID_JPEG,
            )
        )
        tags.save(track)
    original = tagging.validate_cover_bytes
    calls = 0

    def counted(data: bytes):
        nonlocal calls
        calls += 1
        return original(data)

    monkeypatch.setattr(tagging, "validate_cover_bytes", counted)
    stats = run(RunOptions(root=tmp_path, providers=[NeverFindProvider()], do_sidecar=False))

    assert stats.files_already_embedded == 20
    assert calls == 1
