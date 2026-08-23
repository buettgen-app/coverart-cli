"""Generate a self-contained HTML report of a music library's cover coverage."""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path, PureWindowsPath

from coverart_cli import __version__
from coverart_cli.tagging import (
    AUDIO_EXTS,
    find_sidecar,
    has_embedded_cover,
)

log = logging.getLogger(__name__)

# Max size in bytes for an embedded thumbnail. Larger images are skipped
# so that the resulting HTML report stays under a few MB even for big libraries.
MAX_THUMB_BYTES = 200_000


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
    return resources.files("coverart_cli.templates").joinpath("report.html").read_text(
        encoding="utf-8"
    )


def _make_data_uri(path: Path) -> str | None:
    """Build a base64 data URI for a small image file. Returns None for big files."""
    try:
        size = path.stat().st_size
        if size > MAX_THUMB_BYTES:
            return None
        data = path.read_bytes()
    except OSError as e:
        log.debug("cannot read sidecar %s: %s", path, e)
        return None
    suffix = path.suffix.lower()
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(suffix, "image/jpeg")
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


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
    if not root.exists():
        raise FileNotFoundError(f"library root not found: {root}")

    for d in sorted(root.rglob("*")):
        if not d.is_dir() or d.is_symlink():
            continue
        try:
            rel = d.relative_to(root)
        except ValueError:
            continue
        if any(part.startswith(".") for part in rel.parts):
            continue
        try:
            audio_files = [
                f for f in d.iterdir()
                if f.is_file() and not f.is_symlink() and f.suffix.lower() in AUDIO_EXTS
            ]
        except (PermissionError, OSError) as e:
            log.warning("cannot read %s: %s", d, e)
            continue
        if not audio_files:
            continue

        sidecar = find_sidecar(d)
        has_embedded = any(has_embedded_cover(f) for f in audio_files)
        has_any_cover = bool(sidecar) or has_embedded

        cover_data_uri: str | None = None
        if embed_thumbs and sidecar:
            cover_data_uri = _make_data_uri(sidecar)

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
    out_path.write_text(html, encoding="utf-8")
    return out_path, len(entries)


__all__ = [
    "AlbumEntry",
    "MAX_THUMB_BYTES",
    "build_report",
    "scan_library",
    "write_report",
]
