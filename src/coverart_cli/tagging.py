"""Reading album metadata from audio tags and embedding cover art back."""

from __future__ import annotations

import base64
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from mutagen import File as MutagenFile
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis

log = logging.getLogger(__name__)

MP3_EXTS: frozenset[str] = frozenset({".mp3"})
MP4_EXTS: frozenset[str] = frozenset({".m4a", ".m4b", ".mp4"})
FLAC_EXTS: frozenset[str] = frozenset({".flac"})
OGG_EXTS: frozenset[str] = frozenset({".ogg", ".oga"})
OPUS_EXTS: frozenset[str] = frozenset({".opus"})
AUDIO_EXTS: frozenset[str] = MP3_EXTS | MP4_EXTS | FLAC_EXTS | OGG_EXTS | OPUS_EXTS
SIDECAR_NAMES: tuple[str, ...] = ("cover.jpg", "cover.png", "folder.jpg", "folder.png")
MIN_COVER_BYTES = 2000


@dataclass(frozen=True)
class AlbumMeta:
    """Album metadata read from an audio file's tags."""

    artist: str
    album: str

    def __str__(self) -> str:
        return f"{self.artist} / {self.album}"


def read_album_meta(path: Path) -> AlbumMeta | None:
    """Read albumartist + album from any supported audio file. None if tags missing."""
    try:
        f = MutagenFile(path, easy=True)
    except Exception as e:
        log.debug("mutagen failed on %s: %s", path, e)
        return None
    if not f:
        return None
    artist_list = f.get("albumartist") or f.get("artist") or []
    album_list = f.get("album") or []
    if not artist_list or not album_list:
        return None
    artist = artist_list[0].strip()
    album = album_list[0].strip()
    if not artist or not album:
        return None
    return AlbumMeta(artist=artist, album=album)


def find_sidecar(album_dir: Path, *, min_bytes: int = MIN_COVER_BYTES) -> Path | None:
    """Return a supported JPEG/PNG sidecar that meets the byte threshold."""
    for name in SIDECAR_NAMES:
        p = album_dir / name
        try:
            if not p.is_file() or p.is_symlink() or p.stat().st_size <= min_bytes:
                continue
            with p.open("rb") as f:
                if detect_image_mime(f.read(12)) is not None:
                    return p
        except OSError:
            continue
    return None


def existing_embedded_size(path: Path) -> int:
    """Return the byte size of the largest embedded cover, or 0 if none."""
    suffix = path.suffix.lower()
    try:
        if suffix in MP3_EXTS:
            try:
                tags = ID3(path)
            except ID3NoHeaderError:
                return 0
            sizes = [len(cast(Any, t).data) for t in tags.values() if isinstance(t, APIC)]
            return max(sizes) if sizes else 0
        if suffix in MP4_EXTS:
            audio = MP4(path)
            covers = audio.tags.get("covr") if audio.tags else None
            return max((len(bytes(c)) for c in covers), default=0) if covers else 0
        if suffix in FLAC_EXTS:
            pics = FLAC(path).pictures
            return max((len(p.data) for p in pics), default=0) if pics else 0
        if suffix in OGG_EXTS:
            return _ogg_picture_size(OggVorbis(path))
        if suffix in OPUS_EXTS:
            return _ogg_picture_size(OggOpus(path))
    except Exception as e:
        log.debug("size-check failed on %s: %s", path, e)
    return 0


def _ogg_picture_size(audio) -> int:
    """Decode metadata_block_picture (base64 Picture blocks) and return max payload size."""
    blob_list = audio.get("metadata_block_picture") or []
    best = 0
    for blob in blob_list:
        try:
            raw = base64.b64decode(blob)
            pic = Picture(raw)
            best = max(best, len(pic.data))
        except Exception:
            continue
    return best


def detect_image_mime(data: bytes) -> str | None:
    """Detect a cover MIME supported consistently by all output formats."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


def has_embedded_cover(path: Path) -> bool:
    """Check whether an audio file already has embedded cover art."""
    suffix = path.suffix.lower()
    try:
        if suffix in MP3_EXTS:
            try:
                tags = ID3(path)
            except ID3NoHeaderError:
                return False
            return any(k.startswith("APIC") for k in tags)
        if suffix in MP4_EXTS:
            audio = MP4(path)
            tags = audio.tags
            return bool(tags and "covr" in tags and tags["covr"])
        if suffix in FLAC_EXTS:
            return bool(FLAC(path).pictures)
        if suffix in OGG_EXTS:
            return bool(OggVorbis(path).get("metadata_block_picture"))
        if suffix in OPUS_EXTS:
            return bool(OggOpus(path).get("metadata_block_picture"))
    except Exception as e:
        log.debug("cover-check failed on %s: %s", path, e)
    return False


def embed_cover(
    path: Path,
    cover_bytes: bytes,
    mime: str | None = None,
    *,
    replace: bool = False,
) -> bool:
    """Embed cover art into a single audio file.

    Existing artwork is kept unless ``replace`` is true. Returns True on
    success (or skip-already-has), False on failure.
    """
    detected_mime = detect_image_mime(cover_bytes)
    if detected_mime is None or (mime is not None and mime != detected_mime):
        log.error("unsupported or mismatched cover image for %s", path)
        return False
    mime = detected_mime
    suffix = path.suffix.lower()
    try:
        if suffix in MP3_EXTS:
            return _embed_mp3(path, cover_bytes, mime, replace=replace)
        if suffix in MP4_EXTS:
            fmt = MP4Cover.FORMAT_PNG if mime == "image/png" else MP4Cover.FORMAT_JPEG
            return _embed_m4a(path, cover_bytes, fmt, replace=replace)
        if suffix in FLAC_EXTS:
            return _embed_flac(path, cover_bytes, mime, replace=replace)
        if suffix in OGG_EXTS:
            return _embed_ogg(path, cover_bytes, mime, OggVorbis, replace=replace)
        if suffix in OPUS_EXTS:
            return _embed_ogg(path, cover_bytes, mime, OggOpus, replace=replace)
    except Exception as e:
        log.error("embed failed on %s: %s", path, e)
        return False
    log.warning("unsupported audio format: %s", path)
    return False


def _embed_mp3(path: Path, cover: bytes, mime: str, *, replace: bool) -> bool:
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    if any(k.startswith("APIC") for k in tags) and not replace:
        return True
    if replace:
        tags.delall("APIC")
    tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=cover))
    tags.save(path, v2_version=3)
    return True


def _embed_m4a(path: Path, cover: bytes, fmt: int, *, replace: bool) -> bool:
    audio = MP4(path)
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags
    if tags is None:
        return False
    if "covr" in tags and tags["covr"] and not replace:
        return True
    tags["covr"] = [MP4Cover(cover, imageformat=fmt)]
    audio.save()
    return True


def _make_picture(cover: bytes, mime: str) -> Picture:
    pic = Picture()
    pic.type = 3  # front cover
    pic.mime = mime
    pic.desc = "Cover"
    pic.data = cover
    return pic


def _embed_flac(path: Path, cover: bytes, mime: str, *, replace: bool) -> bool:
    audio = FLAC(path)
    if audio.pictures and not replace:
        return True
    if replace:
        audio.clear_pictures()
    audio.add_picture(_make_picture(cover, mime))
    audio.save()
    return True


def _embed_ogg(path: Path, cover: bytes, mime: str, cls, *, replace: bool) -> bool:
    """Embed for Ogg-container formats (Vorbis, Opus) using metadata_block_picture."""
    audio = cls(path)
    if audio.get("metadata_block_picture") and not replace:
        return True
    pic = _make_picture(cover, mime)
    audio["metadata_block_picture"] = [base64.b64encode(pic.write()).decode("ascii")]
    audio.save()
    return True


def write_sidecar(album_dir: Path, cover_bytes: bytes, *, prefer_png: bool = False) -> Path:
    """Atomically write a cover sidecar without following an existing symlink."""
    mime = detect_image_mime(cover_bytes)
    if mime is None:
        raise ValueError("unsupported cover image; expected JPEG or PNG")
    if prefer_png and mime != "image/png":
        log.debug("PNG preferred but conversion is unavailable; preserving JPEG format")
    ext = ".png" if mime == "image/png" else ".jpg"
    dest = album_dir / f"cover{ext}"
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=album_dir, prefix=".coverart-", delete=False) as tmp:
            tmp.write(cover_bytes)
            temp_path = Path(tmp.name)
        os.replace(temp_path, dest)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return dest


__all__ = [
    "AUDIO_EXTS",
    "FLAC_EXTS",
    "MIN_COVER_BYTES",
    "MP3_EXTS",
    "MP4_EXTS",
    "OGG_EXTS",
    "OPUS_EXTS",
    "AlbumMeta",
    "detect_image_mime",
    "embed_cover",
    "existing_embedded_size",
    "find_sidecar",
    "has_embedded_cover",
    "read_album_meta",
    "write_sidecar",
]
