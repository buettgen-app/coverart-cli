"""Command-line interface for coverart-cli."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from coverart_cli import __version__
from coverart_cli.config import load_config
from coverart_cli.core import RunOptions, RunStats, run
from coverart_cli.providers import (
    CoverProvider,
    DeezerProvider,
    ITunesProvider,
    LastFmProvider,
    MusicBrainzProvider,
)

DEFAULT_UA = f"coverart-cli/{__version__} (+https://github.com/buettgen-app/coverart-cli)"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="coverart",
        description=(
            "Fetch missing album cover art from Last.fm, iTunes, Deezer and "
            "MusicBrainz; embed it into MP3 / M4A / FLAC / Ogg files and write "
            "a cover.jpg sidecar in one pass."
        ),
        epilog=(
            "examples:\n"
            "  coverart ~/Music                              # iTunes+Deezer+MB only\n"
            "  coverart ~/Music --lastfm-key YOUR_KEY        # all 4 providers\n"
            "  coverart ~/Music --dry-run -v\n"
            "  coverart ~/Music --report-html report.html\n"
            "  coverart ~/Music --no-embed                   # sidecars only\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("root", type=Path, help="root directory of your music library")
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        metavar="PATH",
        help="explicit config file (default lookup: ~/.config/coverart-cli/config.toml, "
             "then ./coverart.toml)",
    )
    p.add_argument(
        "--lastfm-key",
        default=None,
        help="Last.fm API key (or set $LASTFM_API_KEY). Get one at https://www.last.fm/api/account/create",
    )
    p.add_argument(
        "--no-lastfm",
        action="store_true",
        help="disable Last.fm provider (skip it even if a key is given)",
    )
    p.add_argument(
        "--no-itunes",
        action="store_true",
        help="disable Apple Music / iTunes Search provider",
    )
    p.add_argument(
        "--no-deezer",
        action="store_true",
        help="disable Deezer provider",
    )
    p.add_argument(
        "--no-musicbrainz",
        action="store_true",
        help="disable MusicBrainz / Cover Art Archive fallback",
    )
    p.add_argument(
        "--user-agent",
        default=DEFAULT_UA,
        help="HTTP User-Agent (MusicBrainz requires contact info)",
    )
    p.add_argument(
        "--no-embed",
        action="store_true",
        help="do not embed cover into audio file tags",
    )
    p.add_argument(
        "--no-sidecar",
        action="store_true",
        help="do not write cover.jpg sidecar in album directory",
    )
    p.add_argument(
        "--no-fallback-dirnames",
        action="store_true",
        help="do not fall back to artist/album dir names if tags are missing",
    )
    p.add_argument(
        "--min-bytes",
        type=int,
        default=0,
        metavar="N",
        help="upgrade existing covers smaller than this many bytes "
             "(applies to both sidecar and embedded; 0 = never replace, the default)",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=4,
        metavar="N",
        help="number of albums to process in parallel (default: 4, set 1 for serial)",
    )
    p.add_argument(
        "--replace-smaller",
        action="store_true",
        help="when an existing cover is smaller than the newly fetched one, "
             "replace it (default: keep larger existing)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would happen, write nothing",
    )
    p.add_argument(
        "--missing-csv",
        type=Path,
        default=None,
        help="path to write a CSV of albums for which no cover was found",
    )
    p.add_argument(
        "--report-html",
        type=Path,
        default=None,
        help="write a self-contained HTML report of library coverage to this path",
    )
    p.add_argument(
        "--no-thumbs",
        action="store_true",
        help="when generating the HTML report, skip embedding cover thumbnails",
    )
    p.add_argument(
        "--report-only",
        action="store_true",
        help="only generate the HTML report; do not fetch or modify anything",
    )
    p.add_argument("-v", "--verbose", action="count", default=0, help="-v for INFO, -vv for DEBUG")
    p.add_argument("--version", action="version", version=f"coverart-cli {__version__}")
    return p


def configure_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(level=level, format="%(message)s")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.verbose)

    # Merge config file values into args where the user did not pass a flag.
    # CLI-supplied (non-default) values always win.
    cfg = load_config(args.config)
    for key, value in cfg.items():
        if not hasattr(args, key):
            continue
        current = getattr(args, key)
        default = parser.get_default(key)
        if current == default or current is None:
            setattr(args, key, value)

    # Environment variable takes precedence over config but is overridden by --lastfm-key.
    if args.lastfm_key is None:
        args.lastfm_key = os.environ.get("LASTFM_API_KEY") or cfg.get("lastfm_key")

    if args.dry_run and (args.report_html or args.missing_csv):
        print(
            "error: --dry-run cannot be combined with --report-html or --missing-csv",
            file=sys.stderr,
        )
        return 2

    if args.report_only:
        return _do_report_only(args)

    providers: list[CoverProvider] = []
    if not args.no_lastfm and args.lastfm_key:
        providers.append(LastFmProvider(args.lastfm_key, user_agent=args.user_agent))
    elif not args.no_lastfm:
        print(
            "info: Last.fm skipped (no key); pass --lastfm-key or set $LASTFM_API_KEY"
            " to enable it.",
            file=sys.stderr,
        )
    if not args.no_itunes:
        providers.append(ITunesProvider(user_agent=args.user_agent))
    if not args.no_deezer:
        providers.append(DeezerProvider(user_agent=args.user_agent))
    if not args.no_musicbrainz:
        providers.append(MusicBrainzProvider(user_agent=args.user_agent))

    if not providers:
        print("error: no providers enabled — pass at least one", file=sys.stderr)
        return 2

    opts = RunOptions(
        root=args.root,
        providers=providers,
        do_embed=not args.no_embed,
        do_sidecar=not args.no_sidecar,
        dry_run=args.dry_run,
        fallback_to_dirnames=not args.no_fallback_dirnames,
        missing_csv=args.missing_csv,
        min_sidecar_bytes=args.min_bytes,
        min_embedded_bytes=args.min_bytes,
        keep_larger_existing=not args.replace_smaller,
        workers=args.workers,
    )

    try:
        stats = run(opts)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    _print_summary(stats, dry_run=args.dry_run)

    if args.report_html:
        from coverart_cli.report import write_report

        path, n = write_report(args.root, args.report_html, embed_thumbs=not args.no_thumbs)
        print(f"\nHTML report ({n} albums) written to: {path}")
    return 0


def _do_report_only(args) -> int:
    from coverart_cli.report import write_report

    if not args.report_html:
        print("error: --report-only requires --report-html PATH", file=sys.stderr)
        return 2
    try:
        path, n = write_report(args.root, args.report_html, embed_thumbs=not args.no_thumbs)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"HTML report ({n} albums) written to: {path}")
    return 0


def _print_summary(stats: RunStats, *, dry_run: bool) -> None:
    head = "=== DRY-RUN SUMMARY ===" if dry_run else "=== SUMMARY ==="
    print()
    print(head)
    print(f"  Albums scanned:         {stats.albums_total}")
    print(f"  Sidecar already there:  {stats.sidecar_already}")
    for source, n in sorted(stats.fetched_from.items()):
        print(f"  Fetched from {source:15s} {n}")
    print(f"  Not found:              {stats.not_found}")
    if not dry_run:
        print(f"  Files newly embedded:   {stats.files_embedded}")
        print(f"  Files already embedded: {stats.files_already_embedded}")
        print(f"  Errors:                 {stats.errors}")
