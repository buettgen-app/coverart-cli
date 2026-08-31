"""Core workflow — iterate an album library, fetch + embed/sidecar cover art."""

from __future__ import annotations

import csv
import errno
import logging
import os
import threading
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from coverart_cli.providers import CoverProvider, ProviderResult
from coverart_cli.tagging import (
    AUDIO_EXTS,
    MIN_COVER_BYTES,
    AlbumMeta,
    CoverValidationCache,
    ValidatedCover,
    embed_cover,
    existing_embedded_size,
    file_identity,
    find_sidecar,
    find_sidecars,
    read_album_meta,
    read_cover_file,
    supports_secure_library_traversal,
    validate_cover_bytes,
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


@dataclass(frozen=True)
class AlbumTarget:
    """An album path bound to the identity seen during rooted traversal."""

    path: Path
    identity: tuple[int, int]
    relative: tuple[str, ...]
    root_identity: tuple[int, int]


def _find_album_targets(root: Path) -> list[AlbumTarget]:
    """Traverse beneath an opened root without following replaceable components."""
    if not supports_secure_library_traversal():
        raise OSError("secure no-follow library traversal is unsupported on this platform")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    root_fd = os.open(root, flags)
    root_info = os.fstat(root_fd)
    root_identity = (root_info.st_dev, root_info.st_ino)
    targets: list[AlbumTarget] = []
    pending: list[tuple[str, ...]] = [()]
    try:
        while pending:
            relative = pending.pop()
            directory_fd = os.dup(root_fd)
            try:
                for component in relative:
                    next_fd = os.open(component, flags, dir_fd=directory_fd)
                    os.close(directory_fd)
                    directory_fd = next_fd
                child_dirs: list[str] = []
                has_audio = False
                try:
                    with os.scandir(directory_fd) as entries:
                        for entry in entries:
                            if entry.name.startswith("."):
                                continue
                            try:
                                if entry.is_dir(follow_symlinks=False):
                                    child_dirs.append(entry.name)
                                elif (
                                    entry.is_file(follow_symlinks=False)
                                    and Path(entry.name).suffix.lower() in AUDIO_EXTS
                                ):
                                    has_audio = True
                            except OSError as error:
                                if error.errno in {errno.EMFILE, errno.ENFILE}:
                                    raise
                                path = root.joinpath(*relative, entry.name)
                                log.warning("cannot inspect %s: %s", path, error)
                except (PermissionError, OSError) as error:
                    if error.errno in {errno.EMFILE, errno.ENFILE}:
                        raise
                    log.warning("cannot read %s: %s", root.joinpath(*relative), error)
                else:
                    if relative and has_audio:
                        info = os.fstat(directory_fd)
                        targets.append(
                            AlbumTarget(
                                path=root.joinpath(*relative),
                                identity=(info.st_dev, info.st_ino),
                                relative=relative,
                                root_identity=root_identity,
                            )
                        )
                    pending.extend((*relative, name) for name in sorted(child_dirs, reverse=True))
            finally:
                os.close(directory_fd)
    finally:
        os.close(root_fd)
    return sorted(targets, key=lambda target: target.path)


@contextmanager
def _open_album_target(root: Path, target: AlbumTarget):
    """Reopen a target through its root without following moved components."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    current_fd = os.open(root, flags)
    try:
        info = os.fstat(current_fd)
        if (info.st_dev, info.st_ino) != target.root_identity:
            raise OSError("library root identity changed")
        for component in target.relative:
            next_fd = os.open(component, flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        info = os.fstat(current_fd)
        if (info.st_dev, info.st_ino) != target.identity:
            raise OSError("album directory identity changed")
        yield current_fd
    finally:
        os.close(current_fd)


def find_album_dirs(root: Path) -> list[Path]:
    """Return album paths discovered by rooted, no-follow traversal."""
    return [target.path for target in _find_album_targets(root)]


def _is_audio_file(path: Path) -> bool:
    """Return true for regular supported audio files, never symbolic links."""
    return path.is_file() and not path.is_symlink() and path.suffix.lower() in AUDIO_EXTS


def album_meta_for(
    album_dir: Path,
    *,
    fallback_to_dirnames: bool,
    audio_files: list[Path] | None = None,
    audio_identities: dict[Path, tuple[int, int] | None] | None = None,
    album_identity: tuple[int, int] | None = None,
    album_fd: int | None = None,
) -> AlbumMeta | None:
    """Read album metadata: tags first, optional fallback to parent/dir name."""
    if audio_files is None:
        audio_files = sorted(f for f in album_dir.iterdir() if _is_audio_file(f))
    for f in audio_files:
        meta = read_album_meta(
            f,
            expected_identity=audio_identities.get(f) if audio_identities else None,
            expected_parent_identity=album_identity,
            parent_fd=album_fd,
        )
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
    validation_cache: CoverValidationCache | None = None,
    expected_album_identity: tuple[int, int] | None = None,
    album_fd: int | None = None,
    album_guard: Callable[[], bool] | None = None,
) -> None:
    """Fetch + apply cover art for one album directory.

    `stats_lock` serialises mutations to `stats` when called from multiple
    threads; pass None when single-threaded.
    """
    from contextlib import nullcontext

    lock = stats_lock if stats_lock is not None else nullcontext()

    with lock:
        stats.albums_total += 1

    if album_fd is not None:
        album_info = os.fstat(album_fd)
        album_identity = (album_info.st_dev, album_info.st_ino)
    else:
        album_identity = file_identity(album_dir, directory=True)
    if album_identity is None or (
        expected_album_identity is not None and album_identity != expected_album_identity
    ):
        log.warning("[unsafe]   album directory changed: %s", album_dir)
        with lock:
            stats.errors += 1
        return

    # An album is complete only when every requested output meets its quality bar.
    sidecar_threshold = max(opts.min_sidecar_bytes, MIN_COVER_BYTES)
    existing_sidecar: Path | None = None
    current_sidecar: Path | None = None
    if opts.do_sidecar:
        existing_sidecar, current_sidecar = find_sidecars(
            album_dir,
            min_bytes=sidecar_threshold,
            expected_parent_identity=album_identity,
            directory_fd=album_fd,
        )
    reusable_sidecar = existing_sidecar
    if reusable_sidecar is None and opts.do_embed and not opts.do_sidecar:
        embed_threshold = max(opts.min_embedded_bytes, MIN_COVER_BYTES)
        reusable_sidecar = find_sidecar(
            album_dir,
            min_bytes=embed_threshold,
            expected_parent_identity=album_identity,
            directory_fd=album_fd,
        )
    current_sidecar = existing_sidecar or current_sidecar
    current_info = os.fstat(album_fd) if album_fd is not None else None
    current_identity = (
        (current_info.st_dev, current_info.st_ino)
        if current_info is not None
        else file_identity(album_dir, directory=True)
    )
    if current_identity != album_identity:
        log.warning("[unsafe]   album directory changed: %s", album_dir)
        with lock:
            stats.errors += 1
        return
    if album_fd is not None:
        with os.scandir(album_fd) as entries:
            audio_candidates = sorted(
                album_dir / entry.name
                for entry in entries
                if not entry.name.startswith(".")
                and entry.is_file(follow_symlinks=False)
                and Path(entry.name).suffix.lower() in AUDIO_EXTS
            )
    else:
        audio_candidates = sorted(f for f in album_dir.iterdir() if _is_audio_file(f))
    current_info = os.fstat(album_fd) if album_fd is not None else None
    current_identity = (
        (current_info.st_dev, current_info.st_ino)
        if current_info is not None
        else file_identity(album_dir, directory=True)
    )
    if current_identity != album_identity:
        log.warning("[unsafe]   album directory changed during scan: %s", album_dir)
        with lock:
            stats.errors += 1
        return
    audio_identities = {f: file_identity(f, dir_fd=album_fd) for f in audio_candidates}
    audio_files = [f for f in audio_candidates if audio_identities[f] is not None]
    embedded_sizes = (
        {
            f: existing_embedded_size(
                f,
                expected_identity=audio_identities[f],
                expected_parent_identity=album_identity,
                validation_cache=validation_cache,
                parent_fd=album_fd,
            )
            for f in audio_files
        }
        if opts.do_embed
        else {}
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

    meta = album_meta_for(
        album_dir,
        fallback_to_dirnames=opts.fallback_to_dirnames,
        audio_files=audio_files,
        audio_identities=audio_identities,
        album_identity=album_identity,
        album_fd=album_fd,
    )
    if not meta:
        log.warning("[no-meta]  %s", album_dir)
        with lock:
            stats.misses.append((album_dir, "no readable tags or directory metadata"))
            stats.not_found += 1
        return

    result: ProviderResult | None = None
    validated_cover: ValidatedCover | None = None
    used_sidecar = False
    provider_failures: list[str] = []
    if reusable_sidecar is not None and not embeds_complete:
        try:
            sidecar_identity = file_identity(reusable_sidecar)
            image_bytes = read_cover_file(
                reusable_sidecar,
                expected_identity=sidecar_identity,
                expected_parent_identity=album_identity,
                parent_fd=album_fd,
            )
            validated_cover = validate_cover_bytes(image_bytes) if image_bytes is not None else None
            if validated_cover is not None:
                assert image_bytes is not None
                result = ProviderResult(
                    image_bytes=image_bytes,
                    source="sidecar",
                    image_url=str(reusable_sidecar),
                )
                used_sidecar = True
            else:
                log.warning("ignoring unsupported sidecar: %s", reusable_sidecar)
        except OSError as e:
            log.warning("cannot reuse sidecar %s: %s", reusable_sidecar, e)

    if result is None:
        for provider in opts.providers:
            try:
                candidate = provider.fetch(meta.artist, meta.album)
            except Exception as error:
                log.warning("provider %s failed for %s: %s", provider.name, meta, error)
                provider_failures.append(provider.name)
                continue
            if candidate is None:
                continue
            validated_cover = validate_cover_bytes(candidate.image_bytes)
            if validated_cover is None:
                log.warning(
                    "ignoring unsupported cover payload from %s for %s",
                    candidate.source,
                    meta,
                )
                continue
            result = candidate
            if result is not None:
                break

    if not result:
        with lock:
            if provider_failures:
                failed = ", ".join(provider_failures)
                log.error("[failure]  %s (providers: %s)", meta, failed)
                stats.misses.append((album_dir, f"provider failure: {failed}"))
                stats.errors += 1
            else:
                log.info("[miss]     %s", meta)
                stats.misses.append((album_dir, f"not found: {meta}"))
                stats.not_found += 1
        return

    if validated_cover is None:
        validated_cover = validate_cover_bytes(result.image_bytes)
    if validated_cover is None:  # defensive: every assignment above validates first
        with lock:
            stats.errors += 1
        return

    new_size = len(result.image_bytes)

    log.info("[%s] %s (%d B)", result.source, meta, new_size)
    if not used_sidecar:
        with lock:
            stats.record_fetch(result.source)

    if opts.dry_run:
        return

    if album_guard is not None and not album_guard():
        log.warning("[unsafe]   album path left the library: %s", album_dir)
        with lock:
            stats.errors += 1
        return

    if opts.do_sidecar and existing_sidecar is None:
        current_data = (
            read_cover_file(
                current_sidecar,
                expected_identity=file_identity(current_sidecar),
                expected_parent_identity=album_identity,
                parent_fd=album_fd,
            )
            if current_sidecar
            else None
        )
        current_size = len(current_data) if current_data is not None else 0
        if opts.keep_larger_existing and current_size > new_size:
            log.info("[keep]     %s sidecar (%d B > %d B)", meta, current_size, new_size)
            with lock:
                stats.sidecar_already += 1
        else:
            try:
                write_sidecar(
                    album_dir,
                    validated_cover,
                    expected_dir_identity=album_identity,
                    directory_fd=album_fd,
                    path_guard=album_guard,
                )
            except (OSError, ValueError) as e:
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
            ok = embed_cover(
                f,
                validated_cover,
                replace=replace_existing,
                expected_identity=audio_identities[f],
                expected_parent_identity=album_identity,
                parent_fd=album_fd,
                path_guard=album_guard,
            )
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

    albums = _find_album_targets(opts.root)
    validation_cache = CoverValidationCache()
    workers = max(1, opts.workers)
    log.info(
        "scanning %d album directories under %s (workers=%d)",
        len(albums),
        opts.root,
        workers,
    )

    def process_target(
        target: AlbumTarget,
        stats_lock: threading.Lock | None = None,
    ) -> None:
        with _open_album_target(opts.root, target) as album_fd:

            def album_guard() -> bool:
                try:
                    with _open_album_target(opts.root, target) as checked_fd:
                        checked = os.fstat(checked_fd)
                        current = os.fstat(album_fd)
                        return (checked.st_dev, checked.st_ino) == (
                            current.st_dev,
                            current.st_ino,
                        )
                except OSError:
                    return False

            process_album(
                target.path,
                opts,
                stats,
                stats_lock,
                validation_cache,
                target.identity,
                album_fd,
                album_guard,
            )

    if workers == 1:
        for target in albums:
            try:
                process_target(target)
            except Exception as e:  # defensive — keep batch running
                log.exception("unexpected error on %s: %s", target.path, e)
                stats.errors += 1
                stats.misses.append((target.path, f"crash: {e}"))
    else:
        stats_lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=workers) as ex:
            album_iter = iter(albums)
            futures: dict[Future[None], Path] = {}

            def submit_next() -> bool:
                try:
                    target = next(album_iter)
                except StopIteration:
                    return False
                futures[
                    ex.submit(
                        process_target,
                        target,
                        stats_lock,
                    )
                ] = target.path
                return True

            for _ in range(min(len(albums), workers * 3)):
                submit_next()
            while futures:
                done, _ = wait(futures, return_when=FIRST_COMPLETED)
                for fut in done:
                    album_dir = futures.pop(fut)
                    try:
                        fut.result()
                    except Exception as e:
                        log.exception("unexpected error on %s: %s", album_dir, e)
                        with stats_lock:
                            stats.errors += 1
                            stats.misses.append((album_dir, f"crash: {e}"))
                    submit_next()

    if not opts.dry_run and opts.missing_csv:
        _write_missing_csv(opts.missing_csv, stats.misses)
        log.info("wrote missing list: %s", opts.missing_csv)

    return stats


def _write_missing_csv(path: Path, misses: list[tuple[Path, str]]) -> None:
    def safe_cell(value: object) -> str:
        text = str(value)
        first = text.lstrip(" \t\r\n\v\f")[:1]
        return f"'{text}" if first in {"=", "+", "-", "@"} else text

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["album_path", "reason"])
        for album, reason in misses:
            w.writerow([safe_cell(album), safe_cell(reason)])
