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
from coverart_cli.tagging import (
    supports_secure_library_traversal,
    supports_secure_sidecar_writes,
)

DEFAULT_UA = f"coverart-cli/{__version__} (+https://github.com/buettgen-app/coverart-cli)"


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be at least 0")
    return parsed


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
        allow_abbrev=False,
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
    p.add_argument("--lastfm", dest="no_lastfm", action="store_false", help=argparse.SUPPRESS)
    p.add_argument(
        "--no-itunes",
        action="store_true",
        help="disable Apple Music / iTunes Search provider",
    )
    p.add_argument("--itunes", dest="no_itunes", action="store_false", help=argparse.SUPPRESS)
    p.add_argument(
        "--no-deezer",
        action="store_true",
        help="disable Deezer provider",
    )
    p.add_argument("--deezer", dest="no_deezer", action="store_false", help=argparse.SUPPRESS)
    p.add_argument(
        "--no-musicbrainz",
        action="store_true",
        help="disable MusicBrainz / Cover Art Archive fallback",
    )
    p.add_argument(
        "--musicbrainz", dest="no_musicbrainz", action="store_false", help=argparse.SUPPRESS
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
    p.add_argument("--embed", dest="no_embed", action="store_false", help=argparse.SUPPRESS)
    p.add_argument(
        "--no-sidecar",
        action="store_true",
        help="do not write cover.jpg sidecar in album directory",
    )
    p.add_argument("--sidecar", dest="no_sidecar", action="store_false", help=argparse.SUPPRESS)
    p.add_argument(
        "--no-fallback-dirnames",
        action="store_true",
        help="do not fall back to artist/album dir names if tags are missing",
    )
    p.add_argument(
        "--fallback-dirnames",
        dest="no_fallback_dirnames",
        action="store_false",
        help=argparse.SUPPRESS,
    )
    p.add_argument(
        "--min-bytes",
        type=_nonnegative_int,
        default=0,
        metavar="N",
        help="upgrade existing covers smaller than this many bytes "
        "(applies to both sidecar and embedded; 0 = never replace, the default)",
    )
    p.add_argument(
        "--workers",
        type=_positive_int,
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
        "--keep-larger-existing",
        dest="replace_smaller",
        action="store_false",
        help=argparse.SUPPRESS,
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would happen, write nothing",
    )
    p.add_argument("--no-dry-run", dest="dry_run", action="store_false", help=argparse.SUPPRESS)
    p.add_argument(
        "--missing-csv",
        type=Path,
        default=None,
        help="path to write a CSV of albums for which no cover was found",
    )
    p.add_argument(
        "--no-missing-csv",
        dest="missing_csv",
        action="store_const",
        const=None,
        help=argparse.SUPPRESS,
    )
    p.add_argument(
        "--report-html",
        type=Path,
        default=None,
        help="write a self-contained HTML report of library coverage to this path",
    )
    p.add_argument(
        "--no-report-html",
        dest="report_html",
        action="store_const",
        const=None,
        help=argparse.SUPPRESS,
    )
    p.add_argument(
        "--no-thumbs",
        action="store_true",
        help="when generating the HTML report, skip embedding cover thumbnails",
    )
    p.add_argument("--thumbs", dest="no_thumbs", action="store_false", help=argparse.SUPPRESS)
    p.add_argument(
        "--report-only",
        action="store_true",
        help="only generate the HTML report; do not fetch or modify anything",
    )
    p.add_argument(
        "--no-report-only", dest="report_only", action="store_false", help=argparse.SUPPRESS
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


def _explicit_cli_dests(parser: argparse.ArgumentParser, argv: list[str] | None) -> set[str]:
    """Return option destinations explicitly supplied by the caller."""
    tokens = argv if argv is not None else sys.argv[1:]
    explicit: set[str] = set()
    for token in tokens:
        if token == "--":
            break
        option = token.split("=", 1)[0]
        action = parser._option_string_actions.get(option)
        if action is not None:
            explicit.add(action.dest)
    return explicit


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    explicit_dests = _explicit_cli_dests(parser, argv)
    args = parser.parse_args(argv)
    configure_logging(args.verbose)

    # Merge config file values only where the user did not pass the option.
    # Tracking presence (instead of comparing defaults) also preserves an
    # explicit built-in value such as `--workers 4` over a config value.
    cfg = load_config(args.config)
    for key, value in cfg.items():
        if not hasattr(args, key) or key in explicit_dests:
            continue
        setattr(args, key, value)

    # Environment variable takes precedence over config but is overridden by --lastfm-key.
    if "lastfm_key" not in explicit_dests:
        args.lastfm_key = os.environ.get("LASTFM_API_KEY") or args.lastfm_key

    if args.dry_run and (args.report_html or args.missing_csv):
        print(
            "error: --dry-run cannot be combined with --report-html or --missing-csv",
            file=sys.stderr,
        )
        return 2

    if args.no_embed and args.no_sidecar and not args.report_only:
        print("error: --no-embed and --no-sidecar disable every output", file=sys.stderr)
        return 2

    if not supports_secure_library_traversal():
        print(
            "error: secure no-follow library traversal is unsupported on this platform",
            file=sys.stderr,
        )
        return 2

    if not args.no_sidecar and not args.dry_run and not supports_secure_sidecar_writes():
        print(
            "error: secure sidecar writes are unsupported on this platform; "
            "use --no-sidecar to embed artwork without sidecar files",
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
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    _print_summary(stats, dry_run=args.dry_run)

    if args.report_html:
        from coverart_cli.report import write_report

        try:
            path, n = write_report(
                args.root,
                args.report_html,
                embed_thumbs=not args.no_thumbs,
            )
        except OSError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(f"\nHTML report ({n} albums) written to: {path}")
    return 1 if stats.errors else 0


def _do_report_only(args) -> int:
    from coverart_cli.report import write_report

    if not args.report_html:
        print("error: --report-only requires --report-html PATH", file=sys.stderr)
        return 2
    try:
        path, n = write_report(args.root, args.report_html, embed_thumbs=not args.no_thumbs)
    except OSError as e:
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
