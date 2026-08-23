#!/usr/bin/env python3
"""Generate a demo HTML report with public-domain example data — used for screenshots."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from coverart_cli.providers import ITunesProvider  # noqa: E402
from coverart_cli.report import AlbumEntry, build_report  # noqa: E402
from coverart_cli.tagging import detect_image_mime  # noqa: E402


def fetch_itunes(artist: str, album: str) -> str | None:
    """Fetch a real cover from iTunes for the demo. Returns data URI or None."""
    import base64

    try:
        result = ITunesProvider(user_agent="coverart-cli-demo/1.0").fetch(artist, album)
        if result is None:
            return None
        mime = detect_image_mime(result.image_bytes)
        encoded = base64.b64encode(result.image_bytes).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    except Exception as e:
        print(f"  warn: could not fetch {artist}/{album}: {e}", file=sys.stderr)
        return None


# Famous public-domain-ish example albums (real artists, well known)
DEMO_ALBUMS = [
    ("Pink Floyd", "The Dark Side of the Moon", "lastfm", 10),
    ("Daft Punk", "Random Access Memories", "itunes", 13),
    ("Radiohead", "OK Computer", "lastfm", 12),
    ("Fleetwood Mac", "Rumours", "deezer", 11),
    ("Nirvana", "Nevermind", "musicbrainz", 13),
    ("Kendrick Lamar", "To Pimp a Butterfly", "itunes", 16),
    ("Tame Impala", "Currents", "deezer", 13),
    ("The Beatles", "Abbey Road", "lastfm", 17),
    ("Beyoncé", "Lemonade", "itunes", 12),
    ("Bon Iver", "22, A Million", "deezer", 10),
    ("Arcade Fire", "Funeral", "musicbrainz", 10),
    ("Frank Ocean", "Blonde", "itunes", 17),
    ("Lana Del Rey", "Norman Fucking Rockwell!", "lastfm", 14),
    ("Mac Miller", "Swimming", "deezer", 13),
    ("Massive Attack", "Mezzanine", "musicbrainz", 11),
    ("Aphex Twin", "Selected Ambient Works 85-92", "lastfm", 13),
    ("Some Underground Mixtape Vol. 7", "Limited Bandcamp Edition", "none", 8),
    ("Local Demo Tape", "B-Sides & Rarities", "none", 5),
]


def main() -> None:
    out_dir = REPO_ROOT / "docs" / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "demo-report.html"

    print(f"Building demo entries (fetching {len(DEMO_ALBUMS)} covers from iTunes)...")
    entries: list[AlbumEntry] = []
    for artist, album, source, file_count in DEMO_ALBUMS:
        has_cover = source != "none"
        data_uri = None
        if has_cover:
            data_uri = fetch_itunes(artist, album)
        entries.append(
            AlbumEntry(
                artist=artist,
                album=album,
                path=f"{artist}/{album}",
                has_cover=bool(data_uri),
                source=source if data_uri else "none",
                file_count=file_count,
                cover_data_uri=data_uri,
            )
        )

    html = build_report(entries, library_path="~/Music (demo)")
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote demo report: {out_path}")


if __name__ == "__main__":
    main()
