"""Core workflow — iterate an album library, fetch + embed/sidecar cover art."""

from __future__ import annotations

import csv
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from coverart_cli.providers import CoverProvider, ProviderResult
from coverart_cli.tagging import (
    AUDIO_EXTS,
    MIN_COVER_BYTES,
    AlbumMeta,
    embed_cover,
    existing_embedded_size,
    find_sidecar,
    read_album_meta,
    write_sidecar,
)

log = logging.getLogger(__name__)

# Default number of parallel workers. Music libraries are mostly I/O-bound,
# so 4 threads scale well without overwhelming third-party APIs.
DEFAULT_WORKERS = 4


@dataclass
class RunStats:
    albums_total: int = 0
    sidecar_already: int = 0
    fetched_from: dict[str, int] = field(default_factory=dict)
    not_found: int = 0
    files_embedded: int = 0
    files_already_embedded: int = 0
    errors: int = 0
    misses: list[tuple[Path, str]] = field(default_factory=list)

    def record_fetch(self, source: str) -> None:
        self.fetched_from[source] = self.fetched_from.get(source, 0) + 1


@dataclass
class RunOptions:
    """Knobs for a coverart run."""

    root: Path
    providers: list[CoverProvider]
    do_embed: bool = True
    do_sidecar: bool = True
    dry_run: bool = False
    fallback_to_dirnames: bool = True
    missing_csv: Path | None = None
    # Upgrade thresholds — replace an existing cover if it's smaller than this.
    # 0 (default) disables replacement: existing covers are always kept.
    min_sidecar_bytes: int = 0
    min_embedded_bytes: int = 0
    # If the existing cover is bigger than the newly-fetched one, keep the old one.
    keep_larger_existing: bool = True
    # Parallelism — number of albums to process at once. I/O-bound, so threads.
    workers: int = DEFAULT_WORKERS


def find_album_dirs(root: Path) -> list[Path]:
    """Return all directories under root that contain audio files (depth-first)."""
    albums: list[Path] = []
    for d in sorted(root.rglob("*")):
        try:
            rel = d.relative_to(root)
        except ValueError:
            continue
        if not d.is_dir() or d.is_symlink() or any(part.startswith(".") for part in rel.parts):
            continue
        try:
            if any(_is_audio_file(f) for f in d.iterdir()):
                albums.append(d)
        except (PermissionError, OSError) as e:
            log.warning("cannot read %s: %s", d, e)
    return albums


def _is_audio_file(path: Path) -> bool:
    """Return true for regular supported audio files, never symbolic links."""
    return path.is_file() and not path.is_symlink() and path.suffix.lower() in AUDIO_EXTS


def album_meta_for(album_dir: Path, *, fallback_to_dirnames: bool) -> AlbumMeta | None:
    """Read album metadata: tags first, optional fallback to parent/dir name."""
    audio_files = sorted(f for f in album_dir.iterdir() if _is_audio_file(f))
    for f in audio_files:
        meta = read_album_meta(f)
        if meta:
            return meta
    if fallback_to_dirnames and album_dir.parent != album_dir:
        artist = album_dir.parent.name
        album = album_dir.name
        if artist and album and not artist.startswith("."):
            return AlbumMeta(artist=artist, album=album)
    return None


def process_album(
    album_dir: Path,
    opts: RunOptions,
    stats: RunStats,
    stats_lock: threading.Lock | None = None,
) -> None:
    """Fetch + apply cover art for one album directory.

    `stats_lock` serialises mutations to `stats` when called from multiple
    threads; pass None when single-threaded.
    """
    from contextlib import nullcontext

    lock = stats_lock if stats_lock is not None else nullcontext()

    with lock:
        stats.albums_total += 1

    # An album is complete only when every requested output meets its quality bar.
    sidecar_threshold = max(opts.min_sidecar_bytes, MIN_COVER_BYTES)
    existing_sidecar = (
        find_sidecar(album_dir, min_bytes=sidecar_threshold) if opts.do_sidecar else None
    )
    reusable_sidecar = existing_sidecar
    if reusable_sidecar is None and opts.do_embed and not opts.do_sidecar:
        reusable_sidecar = find_sidecar(album_dir)
    current_sidecar = None
    if opts.do_sidecar:
        current_sidecar = existing_sidecar or find_sidecar(album_dir, min_bytes=-1)
    audio_files = sorted(f for f in album_dir.iterdir() if _is_audio_file(f))
    embedded_sizes = (
        {f: existing_embedded_size(f) for f in audio_files} if opts.do_embed else {}
    )
    embeds_complete = not opts.do_embed or all(
        size > 0 and size >= opts.min_embedded_bytes for size in embedded_sizes.values()
    )
    sidecar_complete = not opts.do_sidecar or existing_sidecar is not None

    if sidecar_complete and embeds_complete:
        with lock:
            stats.sidecar_already += 1
            stats.files_already_embedded += len(embedded_sizes)
        log.info("[skip]     %s (requested artwork already present)", album_dir.name)
        return

    meta = album_meta_for(album_dir, fallback_to_dirnames=opts.fallback_to_dirnames)
    if not meta:
        log.warning("[no-meta]  %s", album_dir)
        with lock:
            stats.misses.append((album_dir, "no readable tags or directory metadata"))
            stats.not_found += 1
        return

    result: ProviderResult | None = None
    used_sidecar = False
    if reusable_sidecar is not None and not embeds_complete:
        try:
            result = ProviderResult(
                image_bytes=reusable_sidecar.read_bytes(),
                source="sidecar",
                image_url=str(reusable_sidecar),
            )
            used_sidecar = True
        except OSError as e:
            log.warning("cannot reuse sidecar %s: %s", reusable_sidecar, e)

    if result is None:
        for provider in opts.providers:
            result = provider.fetch(meta.artist, meta.album)
            if result:
                break

    if not result:
        log.info("[miss]     %s", meta)
        with lock:
            stats.misses.append((album_dir, f"not found: {meta}"))
            stats.not_found += 1
        return

    new_size = len(result.image_bytes)

    log.info("[%s] %s (%d B)", result.source, meta, new_size)
    if not used_sidecar:
        with lock:
            stats.record_fetch(result.source)

    if opts.dry_run:
        return

    if opts.do_sidecar and existing_sidecar is None:
        current_size = current_sidecar.stat().st_size if current_sidecar else 0
        if opts.keep_larger_existing and current_size > new_size:
            log.info("[keep]     %s sidecar (%d B > %d B)", meta, current_size, new_size)
            with lock:
                stats.sidecar_already += 1
        else:
            try:
                write_sidecar(album_dir, result.image_bytes)
            except OSError as e:
                log.error("sidecar write failed for %s: %s", album_dir, e)
                with lock:
                    stats.errors += 1

    if opts.do_embed:
        for f in audio_files:
            cur = embedded_sizes[f]
            replace_existing = cur > 0 and cur < opts.min_embedded_bytes
            if cur > 0 and not replace_existing:
                with lock:
                    stats.files_already_embedded += 1
                continue
            if replace_existing and opts.keep_larger_existing and cur > new_size:
                with lock:
                    stats.files_already_embedded += 1
                continue
            ok = embed_cover(f, result.image_bytes, replace=replace_existing)
            with lock:
                if ok:
                    stats.files_embedded += 1
                else:
                    stats.errors += 1


def run(opts: RunOptions) -> RunStats:
    """Top-level: walk root, process every album directory."""
    stats = RunStats()
    if not opts.root.is_dir():
        raise FileNotFoundError(f"library root not found or not a directory: {opts.root}")
    if not opts.providers:
        raise ValueError("at least one provider must be configured")

    albums = find_album_dirs(opts.root)
    workers = max(1, opts.workers)
    log.info(
        "scanning %d album directories under %s (workers=%d)",
        len(albums),
        opts.root,
        workers,
    )

    if workers == 1:
        for album_dir in albums:
            try:
                process_album(album_dir, opts, stats)
            except Exception as e:  # defensive — keep batch running
                log.exception("unexpected error on %s: %s", album_dir, e)
                stats.errors += 1
                stats.misses.append((album_dir, f"crash: {e}"))
    else:
        stats_lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(process_album, d, opts, stats, stats_lock): d for d in albums}
            for fut in as_completed(futures):
                album_dir = futures[fut]
                try:
                    fut.result()
                except Exception as e:
                    log.exception("unexpected error on %s: %s", album_dir, e)
                    with stats_lock:
                        stats.errors += 1
                        stats.misses.append((album_dir, f"crash: {e}"))

    if opts.missing_csv and stats.misses:
        _write_missing_csv(opts.missing_csv, stats.misses)
        log.info("wrote missing list: %s", opts.missing_csv)

    return stats


def _write_missing_csv(path: Path, misses: list[tuple[Path, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["album_path", "reason"])
        for album, reason in misses:
            w.writerow([str(album), reason])
