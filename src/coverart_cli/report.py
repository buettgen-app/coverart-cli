"""Generate a self-contained HTML report of a music library's cover coverage."""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path, PureWindowsPath

from PIL import Image

from coverart_cli import __version__
from coverart_cli.tagging import (
    AUDIO_EXTS,
    CoverValidationCache,
    ValidatedCover,
    existing_embedded_size,
    file_identity,
    probe_sidecars,
    read_cover_file,
    validate_cover_bytes,
)

log = logging.getLogger(__name__)

# Per-image and whole-report budgets prevent untrusted libraries from forcing
# unbounded base64/JSON allocation.
MAX_THUMB_BYTES = 200_000
MAX_REPORT_THUMB_BYTES = 4 * 1024 * 1024
MAX_THUMB_DIMENSION = 512


@dataclass(frozen=True)
class AlbumEntry:
    """A single album row used to build the report."""

    artist: str
    album: str
    path: str
    has_cover: bool
    source: str  # "lastfm", "musicbrainz", "manual", or "none"
    file_count: int
    cover_data_uri: str | None = None

    def to_dict(self) -> dict:
        return {
            "artist": self.artist,
            "album": self.album,
            "has_cover": self.has_cover,
            "source": self.source,
            "file_count": self.file_count,
            "cover_data_uri": self.cover_data_uri,
        }


def _read_template() -> str:
    """Load the bundled HTML template."""
    return (
        resources.files("coverart_cli.templates")
        .joinpath("report.html")
        .read_text(encoding="utf-8")
    )


def _make_data_uri(
    path: Path,
    *,
    expected_parent_identity: tuple[int, int] | None = None,
    validated_cover: ValidatedCover | None = None,
) -> str | None:
    """Build a base64 data URI for a small image file. Returns None for big files."""
    cover = validated_cover
    if cover is None:
        try:
            identity = file_identity(path)
            data = read_cover_file(
                path,
                expected_identity=identity,
                expected_parent_identity=expected_parent_identity,
            )
        except OSError as e:
            log.debug("cannot read sidecar %s: %s", path, e)
            return None
        cover = validate_cover_bytes(data) if data is not None else None
    if cover is None:
        return None
    try:
        with Image.open(io.BytesIO(cover.data)) as image:
            image.thumbnail(
                (MAX_THUMB_DIMENSION, MAX_THUMB_DIMENSION),
                Image.Resampling.LANCZOS,
            )
            output = io.BytesIO()
            if cover.mime == "image/jpeg":
                image.convert("RGB").save(output, format="JPEG", quality=82)
            else:
                image.save(output, format="PNG", optimize=True)
    except (OSError, ValueError):
        return None
    thumbnail = output.getvalue()
    if len(thumbnail) > MAX_THUMB_BYTES:
        return None
    b64 = base64.b64encode(thumbnail).decode("ascii")
    return f"data:{cover.mime};base64,{b64}"


def _detect_source(album_dir: Path, has_any_cover: bool) -> str:
    """Best-effort source classification. We don't persist provenance per-album yet,
    so 'manual' is used as a generic 'covered but origin unknown'.
    """
    return "manual" if has_any_cover else "none"


def _public_library_label(library_path: str) -> str:
    """Return a report-safe library label without exposing absolute paths."""
    if "\\" in library_path or ":" in library_path:
        label = PureWindowsPath(library_path).name
    else:
        label = Path(library_path).name
    return label or "Music library"


def scan_library(root: Path, *, embed_thumbs: bool = True) -> list[AlbumEntry]:
    """Walk a music library and produce one AlbumEntry per album directory found."""
    entries: list[AlbumEntry] = []
    thumbnail_bytes = 0
    validation_cache = CoverValidationCache()
    if not root.is_dir():
        raise FileNotFoundError(f"library root not found or not a directory: {root}")

    from coverart_cli.core import _find_album_targets, _open_album_target

    for target in _find_album_targets(root):
        d = target.path
        try:
            rel = d.relative_to(root)
        except ValueError:
            continue
        if any(part.startswith(".") for part in rel.parts):
            continue
        try:
            with _open_album_target(root, target) as album_fd:
                with os.scandir(album_fd) as scanned:
                    audio_files = [
                        d / entry.name
                        for entry in scanned
                        if entry.is_file(follow_symlinks=False)
                        and Path(entry.name).suffix.lower() in AUDIO_EXTS
                    ]
                if not audio_files:
                    continue

                info = os.fstat(album_fd)
                album_identity = (info.st_dev, info.st_ino)
                if album_identity != target.identity:
                    continue
                sidecar_probe, _ = probe_sidecars(
                    d,
                    expected_parent_identity=album_identity,
                    directory_fd=album_fd,
                )
                sidecar = sidecar_probe.path if sidecar_probe is not None else None
                all_embedded = sidecar is None and all(
                    existing_embedded_size(
                        f,
                        expected_identity=file_identity(f, dir_fd=album_fd),
                        expected_parent_identity=album_identity,
                        validation_cache=validation_cache,
                        parent_fd=album_fd,
                    )
                    > 0
                    for f in audio_files
                )
                has_any_cover = bool(sidecar) or all_embedded

                cover_data_uri: str | None = None
                if embed_thumbs and sidecar and thumbnail_bytes < MAX_REPORT_THUMB_BYTES:
                    assert sidecar_probe is not None
                    candidate_uri = _make_data_uri(
                        sidecar,
                        expected_parent_identity=album_identity,
                        validated_cover=sidecar_probe.cover,
                    )
                    if candidate_uri is not None:
                        candidate_size = len(candidate_uri.encode("ascii"))
                        if thumbnail_bytes + candidate_size <= MAX_REPORT_THUMB_BYTES:
                            cover_data_uri = candidate_uri
                            thumbnail_bytes += candidate_size

                # Path heuristic: <root>/<artist>/<album>/  →  parent name = artist
                artist = d.parent.name if d.parent != root else "Unknown Artist"
                album = d.name

                entries.append(
                    AlbumEntry(
                        artist=artist,
                        album=album,
                        path=str(rel),
                        has_cover=has_any_cover,
                        source=_detect_source(d, has_any_cover),
                        file_count=len(audio_files),
                        cover_data_uri=cover_data_uri,
                    )
                )
        except (PermissionError, OSError) as e:
            log.warning("cannot read %s: %s", d, e)
    return entries


def build_report(
    entries: list[AlbumEntry],
    *,
    library_path: str,
    template: str | None = None,
) -> str:
    """Render the HTML report from a list of album entries."""
    payload = {
        "library_label": _public_library_label(library_path),
        "generated_at": datetime.now(UTC).isoformat(),
        "tool_version": __version__,
        "albums": [e.to_dict() for e in entries],
    }
    # json.dumps is safe to inline into a <script type="application/json"> block
    # as long as we keep "</" sequences out — escape just in case.
    json_payload = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    tpl = template if template is not None else _read_template()
    return tpl.replace("__REPORT_DATA__", json_payload)


def write_report(
    root: Path,
    out_path: Path,
    *,
    embed_thumbs: bool = True,
) -> tuple[Path, int]:
    """End-to-end: scan library + render template + write HTML file.

    Returns (out_path, num_albums).
    """
    entries = scan_library(root, embed_thumbs=embed_thumbs)
    html = build_report(entries, library_path=str(root))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = out_path.with_name(f".{out_path.name}.{secrets.token_hex(8)}.tmp")
    try:
        temp_path.write_text(html, encoding="utf-8")
        os.replace(temp_path, out_path)
    finally:
        temp_path.unlink(missing_ok=True)
    return out_path, len(entries)


__all__ = [
    "AlbumEntry",
    "MAX_THUMB_BYTES",
    "MAX_THUMB_DIMENSION",
    "MAX_REPORT_THUMB_BYTES",
    "build_report",
    "scan_library",
    "write_report",
]
