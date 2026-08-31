"""Smoke tests for tagging module."""

from __future__ import annotations

import base64
import errno
import os
import shutil
import stat
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path
from typing import Any, cast

import pytest
from mutagen.id3 import APIC, ID3
from mutagen.mp4 import MP4, MP4Cover

from coverart_cli.tagging import (
    MAX_COVER_BYTES,
    AlbumMeta,
    detect_image_mime,
    embed_cover,
    existing_embedded_size,
    find_sidecar,
    read_album_meta,
    supports_secure_sidecar_writes,
    write_sidecar,
)

from .image_fixtures import VALID_JPEG, VALID_PNG  # pyrefly: ignore [missing-import]


def test_album_meta_str() -> None:
    m = AlbumMeta(artist="Pink Floyd", album="The Wall")
    assert str(m) == "Pink Floyd / The Wall"


@pytest.mark.parametrize(
    ("magic", "expected"),
    [
        (VALID_PNG, "image/png"),
        (VALID_JPEG, "image/jpeg"),
        (b"GIF89a" + b"\x00" * 10, None),
        (b"RIFFxxxxWEBP" + b"\x00" * 20, None),
        (b"garbage", None),
        (b"\xff\xd8\xff<!doctype html>" + b"x" * 3000, None),
        (b"\x89PNG\r\n\x1a\n" + b"x" * 3000, None),
    ],
)
def test_detect_image_mime(magic: bytes, expected: str | None) -> None:
    assert detect_image_mime(magic) == expected


def test_find_sidecar_present(tmp_path: Path) -> None:
    cover = tmp_path / "cover.jpg"
    cover.write_bytes(VALID_JPEG)
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
    cover.write_bytes(VALID_JPEG[:-2] + b"x" * 7000 + VALID_JPEG[-2:])
    # default threshold: this one is fine
    assert find_sidecar(tmp_path) == cover
    # tightened threshold rejects it
    assert find_sidecar(tmp_path, min_bytes=20_000) is None
    assert find_sidecar(tmp_path, min_bytes=5_000) == cover


def test_find_sidecar_rejects_oversized_image(tmp_path: Path) -> None:
    cover = tmp_path / "cover.jpg"
    with cover.open("wb") as handle:
        handle.write(VALID_JPEG[:-2])
        handle.seek(MAX_COVER_BYTES)
        handle.write(VALID_JPEG[-2:])

    assert find_sidecar(tmp_path, min_bytes=-1) is None


def test_write_sidecar_rejects_replaced_album_directory(tmp_path: Path) -> None:
    from coverart_cli.tagging import file_identity

    album = tmp_path / "album"
    outside = tmp_path / "outside"
    album.mkdir()
    outside.mkdir()
    expected = file_identity(album, directory=True)
    album.rename(tmp_path / "original")
    album.symlink_to(outside, target_is_directory=True)

    with pytest.raises(OSError):
        write_sidecar(album, VALID_JPEG, expected_dir_identity=expected)
    assert not (outside / "cover.jpg").exists()


def test_write_sidecar_rejects_invalid_image(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported cover image"):
        write_sidecar(tmp_path, b"<!doctype html>" + b"x" * 3000)
    assert not list(tmp_path.glob("cover.*"))


@pytest.mark.skipif(
    not supports_secure_sidecar_writes(),
    reason="secure directory-relative replacement is unavailable",
)
def test_write_sidecar_never_mislabels_jpeg_as_png(tmp_path: Path) -> None:
    cover = VALID_JPEG
    written = write_sidecar(tmp_path, cover, prefer_png=True)
    assert written.name == "cover.jpg"
    assert written.read_bytes() == cover


@pytest.mark.parametrize("declared", ["IMAGE/JPEG", " image/jpeg ", "image/jpg"])
def test_embedded_mime_comparison_is_case_insensitive_and_accepts_jpg_alias(
    tmp_path: Path, declared: str
) -> None:
    track = tmp_path / "track.mp3"
    tags = ID3()
    tags.add(APIC(encoding=3, mime=declared, type=3, desc="Cover", data=VALID_JPEG))
    tags.save(track)

    assert existing_embedded_size(track) == len(VALID_JPEG)


def test_embed_cover_rejects_invalid_image(tmp_path: Path) -> None:
    track = tmp_path / "track.mp3"
    ID3().save(track)

    assert not embed_cover(track, b"<!doctype html>" + b"x" * 3000)
    assert not any(key.startswith("APIC") for key in ID3(track))


def test_embed_cover_preserves_mode_and_extended_attributes(tmp_path: Path) -> None:
    if not all(hasattr(os, name) for name in ("getxattr", "setxattr")):
        pytest.skip("extended attributes are unavailable")
    track = tmp_path / "track.mp3"
    ID3().save(track)
    track.chmod(0o640)
    try:
        os.setxattr(track, "user.coverart-test", b"preserve")
    except OSError as error:
        if error.errno in {errno.ENOTSUP, errno.EPERM, getattr(errno, "EOPNOTSUPP", -1)}:
            pytest.skip("extended attributes are unsupported by this filesystem")
        raise

    assert embed_cover(track, VALID_JPEG)
    assert stat.S_IMODE(track.stat().st_mode) == 0o640
    assert os.getxattr(track, "user.coverart-test") == b"preserve"


def test_embed_cover_temp_open_failure_does_not_leak_fds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc_fds = Path("/proc/self/fd")
    if not proc_fds.is_dir():
        pytest.skip("fd accounting requires procfs")
    import coverart_cli.tagging as tagging

    track = tmp_path / "track.mp3"
    ID3().save(track)
    original_bytes = track.read_bytes()
    original_open = tagging.os.open

    def fail_temp_open(path, *args, **kwargs):
        if isinstance(path, str) and path.startswith(".coverart-audio-"):
            raise PermissionError("injected temp failure")
        return original_open(path, *args, **kwargs)

    before = len(list(proc_fds.iterdir()))
    monkeypatch.setattr(tagging.os, "open", fail_temp_open)
    for _ in range(20):
        assert not embed_cover(track, VALID_JPEG)

    assert len(list(proc_fds.iterdir())) == before
    assert track.read_bytes() == original_bytes
    assert not list(tmp_path.glob(".coverart-audio-*"))


def test_embed_cover_identity_mismatch_does_not_double_close_fd(tmp_path: Path) -> None:
    proc_fds = Path("/proc/self/fd")
    track = tmp_path / "track.mp3"
    ID3().save(track)
    before = len(list(proc_fds.iterdir())) if proc_fds.is_dir() else None

    assert not embed_cover(track, VALID_JPEG, expected_identity=(0, 0))

    if before is not None:
        assert len(list(proc_fds.iterdir())) == before
    assert not list(tmp_path.glob(".coverart-audio-*"))


def test_embed_cover_falls_back_when_kernel_copy_is_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import coverart_cli.tagging as tagging

    if not hasattr(tagging.os, "copy_file_range"):
        pytest.skip("copy_file_range is unavailable")
    track = tmp_path / "track.mp3"
    ID3().save(track)
    calls = 0

    def unsupported_copy(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise OSError(errno.EXDEV, "injected cross-device copy")

    monkeypatch.setattr(tagging.os, "copy_file_range", unsupported_copy)
    assert embed_cover(track, VALID_JPEG)
    assert calls == 1
    assert existing_embedded_size(track) == len(VALID_JPEG)


@pytest.mark.skipif(os.name == "nt", reason="POSIX concurrent same-inode mutation oracle")
def test_embed_cover_rejects_same_inode_change_after_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mutagen.id3 import TXXX

    import coverart_cli.tagging as tagging

    track = tmp_path / "track.mp3"
    ID3().save(track)
    original_copy = tagging._copy_audio_file

    def copy_then_change(source_fd: int, target_fd: int, size: int) -> None:
        original_copy(source_fd, target_fd, size)
        tags = ID3(track)
        tags.add(TXXX(encoding=3, desc="concurrent", text=["keep"]))
        tags.save(track)

    monkeypatch.setattr(tagging, "_copy_audio_file", copy_then_change)
    assert not embed_cover(track, VALID_JPEG)
    updated = ID3(track)
    assert updated.getall("TXXX:concurrent")[0].text == ["keep"]
    assert not updated.getall("APIC")


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS metadata contract")
def test_embed_cover_preserves_macos_extended_attributes(tmp_path: Path) -> None:
    track = tmp_path / "track.mp3"
    ID3().save(track)
    attribute = "com.buettgen.coverart-test"
    subprocess.run(["xattr", "-w", attribute, "preserve", str(track)], check=True)
    birthtime = cast(Any, track.stat()).st_birthtime
    time.sleep(2.0)

    assert embed_cover(track, VALID_JPEG)
    assert subprocess.check_output(["xattr", "-p", attribute, str(track)]).strip() == b"preserve"
    assert cast(Any, track.stat()).st_birthtime == pytest.approx(birthtime, abs=0.1)


def test_rejects_crc_valid_png_with_invalid_deflate_stream() -> None:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)

    invalid = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", b"not-zlib" + b"x" * 3000)
        + chunk(b"IEND", b"")
    )
    assert detect_image_mime(invalid) is None


def test_rejects_truncated_jpeg_without_entropy_data() -> None:
    assert detect_image_mime(VALID_JPEG[:100] + b"\xff\xd9") is None


def test_rejects_decodable_jpeg_without_end_marker() -> None:
    assert detect_image_mime(VALID_JPEG[:-2]) is None


def test_rejects_decodable_png_without_iend_chunk() -> None:
    assert detect_image_mime(VALID_PNG[:-12]) is None


def test_broken_png_chunk_is_a_clean_miss() -> None:
    payload = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAAKUlEQVR4nO3NMQEAAAjD"
        "sIFypGMCvlRAU8nks369AwD//////////////wAAAAAAAACAwxafCQDAf5FpRQAAAABJ"
        "RU5ErkJggg=="
    )
    assert detect_image_mime(payload) is None


def test_decompression_bomb_dimensions_are_a_clean_miss() -> None:
    payload = bytes.fromhex(
        "0000010a05070700ff0100fff5faf8f8010a05070700ff0100fff5faf8f8eedd07eedd070007"
    )
    assert detect_image_mime(payload) is None


def test_highly_compressible_8k_png_is_rejected_before_full_decode() -> None:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)

    compressor = zlib.compressobj(level=9)
    compressed = bytearray()
    row = b"\x00" + b"\x00\x00\x00" * 8192
    for _ in range(8192):
        compressed.extend(compressor.compress(row))
    compressed.extend(compressor.flush())
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 8192, 8192, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", bytes(compressed))
        + chunk(b"IEND", b"")
    )

    assert len(payload) < 200_000
    assert detect_image_mime(payload) is None


@pytest.mark.parametrize(
    ("extension", "codec"),
    [
        ("mp3", "libmp3lame"),
        ("m4a", "aac"),
        ("flac", "flac"),
        ("ogg", "libvorbis"),
        ("opus", "libopus"),
    ],
)
def test_real_audio_metadata_and_embedding_roundtrip(
    tmp_path: Path, extension: str, codec: str
) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("ffmpeg is required for the real-format integration matrix")
    track = tmp_path / f"track.{extension}"
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=8000:cl=mono",
            "-t",
            "0.15",
            "-metadata",
            "album_artist=Tagged Artist",
            "-metadata",
            "artist=Track Artist",
            "-metadata",
            "album=Tagged Album",
            "-c:a",
            codec,
            str(track),
        ],
        check=True,
    )

    assert read_album_meta(track) == AlbumMeta("Tagged Artist", "Tagged Album")
    assert embed_cover(track, VALID_JPEG)
    assert existing_embedded_size(track) == len(VALID_JPEG)
    assert read_album_meta(track) == AlbumMeta("Tagged Artist", "Tagged Album")
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(track), "-f", "null", "-"],
        check=True,
    )


def test_m4a_replaces_mismatched_existing_cover_flag(tmp_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("ffmpeg is required for the real-format integration matrix")
    track = tmp_path / "track.m4a"
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=8000:cl=mono",
            "-t",
            "0.15",
            "-c:a",
            "aac",
            str(track),
        ],
        check=True,
    )
    audio = MP4(track)
    if audio.tags is None:
        audio.add_tags()
    assert audio.tags is not None
    audio.tags["covr"] = [MP4Cover(VALID_PNG, imageformat=MP4Cover.FORMAT_JPEG)]
    audio.save()

    assert existing_embedded_size(track) == 0
    assert embed_cover(track, VALID_JPEG)
    updated = MP4(track)
    assert updated.tags is not None
    cover = updated.tags["covr"][0]
    assert bytes(cover) == VALID_JPEG
    assert cover.imageformat == MP4Cover.FORMAT_JPEG
    assert existing_embedded_size(track) == len(VALID_JPEG)


def test_sidecar_fallback_fails_closed_without_directory_handles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import coverart_cli.tagging as tagging

    monkeypatch.setattr(tagging.os, "supports_dir_fd", set())
    with pytest.raises(OSError, match="unsupported"):
        write_sidecar(tmp_path, VALID_JPEG)
