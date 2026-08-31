"""Reading album metadata from audio tags and embedding cover art back."""

from __future__ import annotations

import base64
import errno
import hashlib
import io
import logging
import os
import secrets
import shutil
import stat
import sys
import threading
import warnings
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, cast

from mutagen import File as MutagenFile
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis
from PIL import Image, UnidentifiedImageError

log = logging.getLogger(__name__)

MP3_EXTS: frozenset[str] = frozenset({".mp3"})
MP4_EXTS: frozenset[str] = frozenset({".m4a", ".m4b", ".mp4"})
FLAC_EXTS: frozenset[str] = frozenset({".flac"})
OGG_EXTS: frozenset[str] = frozenset({".ogg", ".oga"})
OPUS_EXTS: frozenset[str] = frozenset({".opus"})
AUDIO_EXTS: frozenset[str] = MP3_EXTS | MP4_EXTS | FLAC_EXTS | OGG_EXTS | OPUS_EXTS
SIDECAR_NAMES: tuple[str, ...] = ("cover.jpg", "cover.png", "folder.jpg", "folder.png")
MIN_COVER_BYTES = 2000
MAX_COVER_BYTES = 20 * 1024 * 1024
MAX_IMAGE_DIMENSION = 4_096
MAX_IMAGE_PIXELS = 16_777_216
FileIdentity = tuple[int, int]


@dataclass(frozen=True)
class AlbumMeta:
    """Album metadata read from an audio file's tags."""

    artist: str
    album: str

    def __str__(self) -> str:
        return f"{self.artist} / {self.album}"


@dataclass(frozen=True)
class ValidatedCover:
    """Image bytes validated once at an untrusted-input boundary."""

    data: bytes
    mime: str


@dataclass(frozen=True)
class SidecarProbe:
    """A sidecar path and image decoded once during the directory probe."""

    path: Path
    cover: ValidatedCover


class CoverValidationCache:
    """Small thread-safe MIME cache keyed by content digest, without retaining image bytes."""

    def __init__(self, max_entries: int = 256) -> None:
        self.max_entries = max_entries
        self._values: OrderedDict[tuple[int, bytes], str | None] = OrderedDict()
        self._lock = threading.Lock()

    def mime(self, data: bytes) -> str | None:
        key = (len(data), hashlib.sha256(data).digest())
        with self._lock:
            if key in self._values:
                value = self._values.pop(key)
                self._values[key] = value
                return value
        cover = validate_cover_bytes(data)
        value = cover.mime if cover is not None else None
        with self._lock:
            self._values[key] = value
            while len(self._values) > self.max_entries:
                self._values.popitem(last=False)
        return value


def _detected_mime(data: bytes, cache: CoverValidationCache | None) -> str | None:
    return cache.mime(data) if cache is not None else detect_image_mime(data)


def _mime_matches(detected: str | None, declared: str | None) -> bool:
    """Compare media types case-insensitively and accept the common JPEG alias."""
    if detected is None or declared is None:
        return False
    aliases = {"image/jpg": "image/jpeg"}
    left = aliases.get(detected.strip().casefold(), detected.strip().casefold())
    right = aliases.get(declared.strip().casefold(), declared.strip().casefold())
    return left == right


def supports_secure_sidecar_writes() -> bool:
    """Return whether directory-relative atomic sidecar replacement is available."""
    return os.open in os.supports_dir_fd and os.rename in os.supports_dir_fd


def supports_secure_library_traversal() -> bool:
    """Return whether mutation targets can be traversed through anchored dirfds."""
    return (
        bool(getattr(os, "O_DIRECTORY", 0))
        and bool(getattr(os, "O_NOFOLLOW", 0))
        and os.open in os.supports_dir_fd
        and os.scandir in os.supports_fd
    )


def read_album_meta(
    path: Path,
    *,
    expected_identity: FileIdentity | None = None,
    expected_parent_identity: FileIdentity | None = None,
    parent_fd: int | None = None,
) -> AlbumMeta | None:
    """Read albumartist + album from any supported audio file. None if tags missing."""
    try:
        with _open_verified_file(
            path,
            expected_identity=expected_identity,
            expected_parent_identity=expected_parent_identity,
            parent_fd=parent_fd,
            writable=False,
        ) as handle:
            f = MutagenFile(handle, easy=True)
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


def find_sidecar(
    album_dir: Path,
    *,
    min_bytes: int = MIN_COVER_BYTES,
    expected_parent_identity: FileIdentity | None = None,
    directory_fd: int | None = None,
) -> Path | None:
    """Return a supported JPEG/PNG sidecar that meets the byte threshold."""
    qualified, _ = find_sidecars(
        album_dir,
        min_bytes=min_bytes,
        expected_parent_identity=expected_parent_identity,
        directory_fd=directory_fd,
    )
    return qualified


def find_sidecars(
    album_dir: Path,
    *,
    min_bytes: int = MIN_COVER_BYTES,
    expected_parent_identity: FileIdentity | None = None,
    directory_fd: int | None = None,
) -> tuple[Path | None, Path | None]:
    """Return the first qualifying and first valid sidecar in one bounded scan."""
    qualified, current = probe_sidecars(
        album_dir,
        min_bytes=min_bytes,
        expected_parent_identity=expected_parent_identity,
        directory_fd=directory_fd,
    )
    return (
        qualified.path if qualified is not None else None,
        current.path if current is not None else None,
    )


def probe_sidecars(
    album_dir: Path,
    *,
    min_bytes: int = MIN_COVER_BYTES,
    expected_parent_identity: FileIdentity | None = None,
    directory_fd: int | None = None,
) -> tuple[SidecarProbe | None, SidecarProbe | None]:
    """Return qualifying/current sidecars while retaining one validated decode."""
    qualified: SidecarProbe | None = None
    current: SidecarProbe | None = None
    for name in SIDECAR_NAMES:
        p = album_dir / name
        try:
            identity = file_identity(p, dir_fd=directory_fd)
            if identity is None:
                continue
            size = (
                os.stat(name, dir_fd=directory_fd, follow_symlinks=False).st_size
                if directory_fd is not None
                else p.stat(follow_symlinks=False).st_size
            )
            if size > MAX_COVER_BYTES:
                continue
            parent_identity = expected_parent_identity or file_identity(
                album_dir,
                directory=True,
            )
            data = read_cover_file(
                p,
                expected_identity=identity,
                expected_parent_identity=parent_identity,
                parent_fd=directory_fd,
            )
            cover = validate_cover_bytes(data) if data is not None else None
            if cover is not None:
                probe = SidecarProbe(path=p, cover=cover)
                if current is None:
                    current = probe
                if qualified is None and size > min_bytes:
                    qualified = probe
        except OSError:
            continue
    return qualified, current


def file_identity(
    path: Path,
    *,
    directory: bool = False,
    dir_fd: int | None = None,
) -> FileIdentity | None:
    """Return a no-follow device/inode identity for a regular file or directory."""
    try:
        info = (
            os.stat(path.name, dir_fd=dir_fd, follow_symlinks=False)
            if dir_fd is not None
            else path.stat(follow_symlinks=False)
        )
    except OSError:
        return None
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_type(info.st_mode):
        return None
    return (info.st_dev, info.st_ino)


@contextmanager
def _open_verified_file(
    path: Path,
    *,
    expected_identity: FileIdentity | None,
    expected_parent_identity: FileIdentity | None = None,
    parent_fd: int | None = None,
    writable: bool,
) -> Iterator[BinaryIO]:
    if expected_identity is None:
        expected_identity = file_identity(path, dir_fd=parent_fd)
    if expected_identity is None:
        raise OSError("file is not a stable regular file")
    flags = os.O_RDWR if writable else os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    dir_fd = -1
    if parent_fd is not None:
        parent_info = os.fstat(parent_fd)
        if expected_parent_identity is not None and (
            not stat.S_ISDIR(parent_info.st_mode)
            or (parent_info.st_dev, parent_info.st_ino) != expected_parent_identity
        ):
            raise OSError("parent directory identity changed")
        fd = os.open(path.name, flags, dir_fd=parent_fd)
    elif expected_parent_identity is not None and os.open in os.supports_dir_fd:
        dir_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        dir_fd = os.open(path.parent, dir_flags)
        parent_info = os.fstat(dir_fd)
        if (
            not stat.S_ISDIR(parent_info.st_mode)
            or (parent_info.st_dev, parent_info.st_ino) != expected_parent_identity
        ):
            os.close(dir_fd)
            raise OSError("parent directory identity changed")
        try:
            fd = os.open(path.name, flags, dir_fd=dir_fd)
        except Exception:
            os.close(dir_fd)
            raise
    else:
        if (
            expected_parent_identity is not None
            and file_identity(path.parent, directory=True) != expected_parent_identity
        ):
            raise OSError("parent directory identity changed")
        fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        identity = (info.st_dev, info.st_ino)
        if not stat.S_ISREG(info.st_mode) or identity != expected_identity:
            raise OSError("file identity changed")
        if writable and info.st_nlink != 1:
            raise OSError("refusing to modify a multiply linked audio file")
        with os.fdopen(fd, "r+b" if writable else "rb") as handle:
            fd = -1
            yield handle
    finally:
        if fd >= 0:
            os.close(fd)
        if dir_fd >= 0:
            os.close(dir_fd)


def read_cover_file(
    path: Path,
    *,
    expected_identity: FileIdentity | None = None,
    expected_parent_identity: FileIdentity | None = None,
    parent_fd: int | None = None,
) -> bytes | None:
    """Read a bounded regular file without following a replaced leaf symlink."""
    try:
        with _open_verified_file(
            path,
            expected_identity=expected_identity,
            expected_parent_identity=expected_parent_identity,
            parent_fd=parent_fd,
            writable=False,
        ) as handle:
            size = os.fstat(handle.fileno()).st_size
            if size > MAX_COVER_BYTES:
                return None
            data = handle.read(MAX_COVER_BYTES + 1)
    except OSError:
        return None
    return data if len(data) <= MAX_COVER_BYTES else None


def existing_embedded_size(
    path: Path,
    *,
    expected_identity: FileIdentity | None = None,
    expected_parent_identity: FileIdentity | None = None,
    validation_cache: CoverValidationCache | None = None,
    parent_fd: int | None = None,
) -> int:
    """Return the byte size of the largest embedded cover, or 0 if none."""
    suffix = path.suffix.lower()
    try:
        with _open_verified_file(
            path,
            expected_identity=expected_identity,
            expected_parent_identity=expected_parent_identity,
            parent_fd=parent_fd,
            writable=False,
        ) as handle:
            if suffix in MP3_EXTS:
                try:
                    tags = ID3(handle)
                except ID3NoHeaderError:
                    return 0
                sizes = [
                    len(cast(Any, t).data)
                    for t in tags.values()
                    if isinstance(t, APIC)
                    and _mime_matches(
                        _detected_mime(cast(Any, t).data, validation_cache),
                        cast(Any, t).mime,
                    )
                ]
                return max(sizes) if sizes else 0
            if suffix in MP4_EXTS:
                audio = MP4(handle)
                covers = audio.tags.get("covr") if audio.tags else None
                expected_formats = {
                    "image/jpeg": MP4Cover.FORMAT_JPEG,
                    "image/png": MP4Cover.FORMAT_PNG,
                }

                def valid_mp4_cover(item: Any) -> bool:
                    detected = _detected_mime(bytes(item), validation_cache)
                    return detected is not None and expected_formats[detected] == getattr(
                        item, "imageformat", None
                    )

                return (
                    max(
                        (len(bytes(c)) for c in covers if valid_mp4_cover(c)),
                        default=0,
                    )
                    if covers
                    else 0
                )
            if suffix in FLAC_EXTS:
                pics = FLAC(handle).pictures
                return max(
                    (
                        len(p.data)
                        for p in pics
                        if _mime_matches(_detected_mime(p.data, validation_cache), p.mime)
                    ),
                    default=0,
                )
            if suffix in OGG_EXTS:
                return _ogg_picture_size(OggVorbis(handle), validation_cache)
            if suffix in OPUS_EXTS:
                return _ogg_picture_size(OggOpus(handle), validation_cache)
    except Exception as e:
        log.debug("size-check failed on %s: %s", path, e)
    return 0


def _ogg_picture_size(audio, cache: CoverValidationCache | None = None) -> int:
    """Decode metadata_block_picture (base64 Picture blocks) and return max payload size."""
    blob_list = audio.get("metadata_block_picture") or []
    best = 0
    for blob in blob_list:
        try:
            raw = base64.b64decode(blob)
            pic = Picture(raw)
            if _mime_matches(_detected_mime(pic.data, cache), pic.mime):
                best = max(best, len(pic.data))
        except Exception:
            continue
    return best


def validate_cover_bytes(data: bytes) -> ValidatedCover | None:
    """Fully decode a bounded JPEG/PNG payload and return its trusted representation."""
    if not data or len(data) > MAX_COVER_BYTES:
        return None
    if data.startswith(b"\xff\xd8") and not data.endswith(b"\xff\xd9"):
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n") and not data.endswith(
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    ):
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in {"JPEG", "PNG"}:
                    return None
                width, height = image.size
                if (
                    not width
                    or not height
                    or width > MAX_IMAGE_DIMENSION
                    or height > MAX_IMAGE_DIMENSION
                    or width * height > MAX_IMAGE_PIXELS
                ):
                    return None
                image.load()
                mime = "image/jpeg" if image.format == "JPEG" else "image/png"
    except (
        OSError,
        SyntaxError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ):
        return None
    return ValidatedCover(data=data, mime=mime)


def detect_image_mime(data: bytes) -> str | None:
    """Fully validate JPEG/PNG image data and return its MIME type."""
    cover = validate_cover_bytes(data)
    return cover.mime if cover is not None else None


def _coerce_cover(cover: bytes | ValidatedCover, mime: str | None = None) -> ValidatedCover | None:
    validated = cover if isinstance(cover, ValidatedCover) else validate_cover_bytes(cover)
    if validated is None or (mime is not None and not _mime_matches(validated.mime, mime)):
        return None
    return validated


def has_embedded_cover(path: Path) -> bool:
    """Check whether an audio file already has embedded cover art."""
    return existing_embedded_size(path) > 0


def _copy_audio_file(source_fd: int, target_fd: int, size: int) -> None:
    """Copy one regular file, using the kernel fast path when it is available."""
    if sys.platform == "darwin":
        _darwin_copy_audio_file(source_fd, target_fd)
        return
    copy_file_range = getattr(os, "copy_file_range", None)
    if copy_file_range is not None:
        try:
            remaining = size
            while remaining:
                copied = copy_file_range(source_fd, target_fd, min(remaining, 8 * 1024 * 1024))
                if copied == 0:
                    raise OSError(errno.EIO, "copy_file_range ended before the source file")
                remaining -= copied
            return
        except OSError as error:
            unsupported = {
                errno.EINVAL,
                errno.ENOSYS,
                errno.EXDEV,
                getattr(errno, "EOPNOTSUPP", errno.EINVAL),
            }
            if error.errno not in unsupported:
                raise
            os.lseek(source_fd, 0, os.SEEK_SET)
            os.ftruncate(target_fd, 0)
            os.lseek(target_fd, 0, os.SEEK_SET)

    with os.fdopen(os.dup(source_fd), "rb") as source, os.fdopen(os.dup(target_fd), "wb") as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)


def _darwin_copy_audio_file(source_fd: int, target_fd: int) -> None:
    """Copy data and metadata through macOS fcopyfile(3)."""
    import ctypes
    import ctypes.util

    library = ctypes.util.find_library("System") or "libSystem.B.dylib"
    libc = ctypes.CDLL(library, use_errno=True)
    fcopyfile = libc.fcopyfile
    fcopyfile.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint]
    fcopyfile.restype = ctypes.c_int
    copyfile_all = 0x0000000F
    if fcopyfile(source_fd, target_fd, None, copyfile_all) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def embed_cover(
    path: Path,
    cover_bytes: bytes | ValidatedCover,
    mime: str | None = None,
    *,
    replace: bool = False,
    expected_identity: FileIdentity | None = None,
    expected_parent_identity: FileIdentity | None = None,
    parent_fd: int | None = None,
    path_guard: Callable[[], bool] | None = None,
) -> bool:
    """Embed cover art into a single audio file.

    Existing artwork is kept unless ``replace`` is true. Returns True on
    success (or skip-already-has), False on failure.
    """
    cover = _coerce_cover(cover_bytes, mime)
    if cover is None:
        log.error("unsupported or mismatched cover image for %s", path)
        return False
    mime = cover.mime
    suffix = path.suffix.lower()
    if suffix not in AUDIO_EXTS:
        log.warning("unsupported audio format: %s", path)
        return False
    directory_fd = -1
    source_fd = -1
    temp_fd = -1
    temp_name = f".coverart-audio-{secrets.token_hex(12)}"
    try:
        if parent_fd is not None:
            directory_fd = os.dup(parent_fd)
        else:
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            directory_fd = os.open(path.parent, flags)
        parent_info = os.fstat(directory_fd)
        parent_identity = (parent_info.st_dev, parent_info.st_ino)
        if expected_parent_identity is not None and parent_identity != expected_parent_identity:
            raise OSError("parent directory identity changed")
        source_fd = os.open(
            path.name,
            os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory_fd,
        )
        source_info = os.fstat(source_fd)
        source_identity = (source_info.st_dev, source_info.st_ino)
        if expected_identity is None:
            expected_identity = source_identity
        if not stat.S_ISREG(source_info.st_mode) or source_identity != expected_identity:
            raise OSError("file identity changed")
        temp_fd = os.open(
            temp_name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL,
            stat.S_IMODE(source_info.st_mode),
            dir_fd=directory_fd,
        )
        temp_info = os.fstat(temp_fd)
        if hasattr(os, "fchown") and (
            source_info.st_uid != temp_info.st_uid or source_info.st_gid != temp_info.st_gid
        ):
            os.fchown(temp_fd, source_info.st_uid, source_info.st_gid)
        os.fchmod(temp_fd, stat.S_IMODE(source_info.st_mode))
        _copy_audio_file(source_fd, temp_fd, source_info.st_size)
        with ExitStack() as stack:
            source = stack.enter_context(os.fdopen(source_fd, "rb"))
            source_fd = -1
            handle = stack.enter_context(os.fdopen(temp_fd, "r+b"))
            temp_fd = -1
            if hasattr(os, "listxattr"):
                for attribute in os.listxattr(source.fileno()):
                    os.setxattr(
                        handle.fileno(),
                        attribute,
                        os.getxattr(source.fileno(), attribute),
                    )
            handle.flush()
            handle.seek(0)
            if suffix in MP3_EXTS:
                updated = _embed_mp3(handle, cover.data, mime, replace=replace)
            elif suffix in MP4_EXTS:
                fmt = MP4Cover.FORMAT_PNG if mime == "image/png" else MP4Cover.FORMAT_JPEG
                updated = _embed_m4a(handle, cover.data, fmt, replace=replace)
            elif suffix in FLAC_EXTS:
                updated = _embed_flac(handle, cover.data, mime, replace=replace)
            elif suffix in OGG_EXTS:
                updated = _embed_ogg(handle, cover.data, mime, OggVorbis, replace=replace)
            else:
                updated = _embed_ogg(handle, cover.data, mime, OggOpus, replace=replace)
            if not updated:
                return False
            handle.flush()
            os.utime(
                handle.fileno(),
                ns=(source_info.st_atime_ns, source_info.st_mtime_ns),
            )
            os.fsync(handle.fileno())
        if path_guard is not None and not path_guard():
            raise OSError("album path left the library")
        current = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            (current.st_dev, current.st_ino) != expected_identity
            or current.st_size != source_info.st_size
            or current.st_mtime_ns != source_info.st_mtime_ns
            or current.st_ctime_ns != source_info.st_ctime_ns
        ):
            raise OSError("file identity changed")
        os.replace(temp_name, path.name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        return True
    except Exception as e:
        log.error("embed failed on %s: %s", path, e)
        return False
    finally:
        if source_fd >= 0:
            os.close(source_fd)
        if temp_fd >= 0:
            os.close(temp_fd)
        if directory_fd >= 0:
            with suppress(FileNotFoundError):
                os.unlink(temp_name, dir_fd=directory_fd)
            os.close(directory_fd)


def _embed_mp3(path, cover: bytes, mime: str, *, replace: bool) -> bool:
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    pictures = [cast(Any, t) for t in tags.values() if isinstance(t, APIC)]
    if (
        any(_mime_matches(detect_image_mime(picture.data), picture.mime) for picture in pictures)
        and not replace
    ):
        return True
    if replace or pictures:
        tags.delall("APIC")
    tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=cover))
    tags.save(path, v2_version=3)
    return True


def _embed_m4a(path, cover: bytes, fmt: int, *, replace: bool) -> bool:
    audio = MP4(path)
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags
    if tags is None:
        return False
    covers = tags.get("covr") or []
    expected_formats = {
        "image/jpeg": MP4Cover.FORMAT_JPEG,
        "image/png": MP4Cover.FORMAT_PNG,
    }

    def valid_existing(item: Any) -> bool:
        detected = detect_image_mime(bytes(item))
        return detected is not None and expected_formats[detected] == getattr(
            item, "imageformat", None
        )

    if any(valid_existing(item) for item in covers) and not replace:
        return True
    tags["covr"] = [MP4Cover(cover, imageformat=fmt)]
    path.seek(0)
    audio.save(path)
    return True


def _make_picture(cover: bytes, mime: str) -> Picture:
    pic = Picture()
    pic.type = 3  # front cover
    pic.mime = mime
    pic.desc = "Cover"
    pic.data = cover
    return pic


def _embed_flac(path, cover: bytes, mime: str, *, replace: bool) -> bool:
    audio = FLAC(path)
    if (
        any(_mime_matches(detect_image_mime(pic.data), pic.mime) for pic in audio.pictures)
        and not replace
    ):
        return True
    if replace or audio.pictures:
        audio.clear_pictures()
    audio.add_picture(_make_picture(cover, mime))
    path.seek(0)
    audio.save(path)
    return True


def _embed_ogg(path, cover: bytes, mime: str, cls, *, replace: bool) -> bool:
    """Embed for Ogg-container formats (Vorbis, Opus) using metadata_block_picture."""
    audio = cls(path)
    existing = audio.get("metadata_block_picture") or []
    if not replace:
        for blob in existing:
            try:
                pic = Picture(base64.b64decode(blob))
                if _mime_matches(detect_image_mime(pic.data), pic.mime):
                    return True
            except Exception:
                continue
    pic = _make_picture(cover, mime)
    audio["metadata_block_picture"] = [base64.b64encode(pic.write()).decode("ascii")]
    path.seek(0)
    audio.save(path)
    return True


def write_sidecar(
    album_dir: Path,
    cover_bytes: bytes | ValidatedCover,
    *,
    prefer_png: bool = False,
    expected_dir_identity: FileIdentity | None = None,
    directory_fd: int | None = None,
    path_guard: Callable[[], bool] | None = None,
) -> Path:
    """Atomically write a cover sidecar without following an existing symlink."""
    cover = _coerce_cover(cover_bytes)
    if cover is None:
        raise ValueError("unsupported cover image; expected JPEG or PNG")
    mime = cover.mime
    if prefer_png and mime != "image/png":
        log.debug("PNG preferred but conversion is unavailable; preserving JPEG format")
    ext = ".png" if mime == "image/png" else ".jpg"
    dest = album_dir / f"cover{ext}"
    if expected_dir_identity is None:
        if directory_fd is not None:
            info = os.fstat(directory_fd)
            expected_dir_identity = (info.st_dev, info.st_ino)
        else:
            expected_dir_identity = file_identity(album_dir, directory=True)
    if expected_dir_identity is None:
        raise OSError("album directory is not a stable directory")

    if supports_secure_sidecar_writes():
        dir_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        dir_fd = os.dup(directory_fd) if directory_fd is not None else os.open(album_dir, dir_flags)
        temp_name = f".coverart-{secrets.token_hex(12)}"
        try:
            info = os.fstat(dir_fd)
            if (info.st_dev, info.st_ino) != expected_dir_identity:
                raise OSError("album directory identity changed")
            temp_fd = os.open(
                temp_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=dir_fd,
            )
            with os.fdopen(temp_fd, "wb") as handle:
                handle.write(cover.data)
            if path_guard is not None and not path_guard():
                raise OSError("album path left the library")
            os.replace(temp_name, dest.name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        finally:
            with suppress(FileNotFoundError):
                os.unlink(temp_name, dir_fd=dir_fd)
            os.close(dir_fd)
        return dest

    raise OSError("secure directory-relative sidecar writes are unsupported on this platform")


__all__ = [
    "AUDIO_EXTS",
    "FLAC_EXTS",
    "MAX_COVER_BYTES",
    "MIN_COVER_BYTES",
    "MP3_EXTS",
    "MP4_EXTS",
    "OGG_EXTS",
    "OPUS_EXTS",
    "AlbumMeta",
    "CoverValidationCache",
    "ValidatedCover",
    "SidecarProbe",
    "detect_image_mime",
    "embed_cover",
    "existing_embedded_size",
    "file_identity",
    "find_sidecar",
    "find_sidecars",
    "probe_sidecars",
    "has_embedded_cover",
    "read_album_meta",
    "read_cover_file",
    "supports_secure_sidecar_writes",
    "supports_secure_library_traversal",
    "validate_cover_bytes",
    "write_sidecar",
]
