"""coverart-cli — fetch missing album covers from Last.fm / iTunes / Deezer / MusicBrainz
and embed them into MP3 / M4A / FLAC / Ogg files (plus a cover.jpg sidecar).

Public API for library consumers:
    >>> from coverart_cli import RunOptions, run, ITunesProvider
    >>> stats = run(RunOptions(root=Path("~/Music"), providers=[ITunesProvider()]))

Anything not exported from this top-level package may change without notice.
"""

__version__ = "0.5.0"  # x-release-please-version

# Re-exports come after __version__ so submodules can import it safely.
from coverart_cli.core import RunOptions, RunStats, run  # noqa: E402
from coverart_cli.providers import (  # noqa: E402
    CoverProvider,
    DeezerProvider,
    ITunesProvider,
    LastFmProvider,
    MusicBrainzProvider,
    ProviderResult,
)
from coverart_cli.report import AlbumEntry, scan_library, write_report  # noqa: E402
from coverart_cli.tagging import AlbumMeta, embed_cover, has_embedded_cover  # noqa: E402

__all__ = [
    "__version__",
    # core
    "RunOptions",
    "RunStats",
    "run",
    # providers
    "CoverProvider",
    "ProviderResult",
    "LastFmProvider",
    "ITunesProvider",
    "DeezerProvider",
    "MusicBrainzProvider",
    # tagging
    "AlbumMeta",
    "embed_cover",
    "has_embedded_cover",
    # report
    "AlbumEntry",
    "scan_library",
    "write_report",
]
