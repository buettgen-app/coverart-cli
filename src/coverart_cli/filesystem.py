# Copyright (c) 2026 WildDragonKing
# SPDX-License-Identifier: MIT

"""No-follow filesystem operations, with a native Windows handle backend.

POSIX uses directory-relative descriptors. Windows pins every directory in the
path with non-delete-sharing handles and rejects all reparse points. Public
integers representing Windows directories are private to this module; regular
file descriptors remain ordinary Python descriptors.
"""

from __future__ import annotations

import errno
import os
import stat as statmod

DIRECTORY = getattr(os, "O_DIRECTORY", 0x10000000)
NOFOLLOW = getattr(os, "O_NOFOLLOW", 0x20000000)
WINDOWS = os.name == "nt"

if WINDOWS:
    from coverart_cli import _windows_filesystem as _win

    close = _win.close
else:
    close = os.close


def open(
    path,
    flags: int,
    mode: int = 0o600,
    *,
    dir_fd: int | None = None,
    share_delete: bool = False,
    security_source_fd: int | None = None,
) -> int:
    if WINDOWS:
        return _win.open(
            path,
            flags,
            mode,
            dir_fd=dir_fd,
            directory=bool(flags & DIRECTORY),
            share_delete=share_delete,
            security_source_fd=security_source_fd,
        )
    return os.open(path, flags, mode, dir_fd=dir_fd)


def dup(fd: int) -> int:
    return _win.dup(fd) if WINDOWS else os.dup(fd)


def fstat(fd: int) -> os.stat_result:
    return _win.fstat(fd) if WINDOWS else os.fstat(fd)


def stat(path, *, dir_fd: int | None = None, follow_symlinks: bool = False) -> os.stat_result:
    if WINDOWS:
        return _win.stat(path, dir_fd=dir_fd)
    return os.stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)


def scandir(fd: int):
    return _win.scandir(fd) if WINDOWS else os.scandir(fd)


def replace(src, dst, *, src_dir_fd: int, dst_dir_fd: int, source_fd: int | None = None) -> None:
    if WINDOWS:
        _win.replace(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd, source_fd=source_fd)
    else:
        os.replace(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)


def unlink(path, *, dir_fd: int) -> None:
    if WINDOWS:
        _win.unlink(path, dir_fd=dir_fd)
    else:
        os.unlink(path, dir_fd=dir_fd)


def preserve_mode(fd: int, mode: int) -> None:
    # Windows audio staging files receive the source DACL at creation.
    if not WINDOWS:
        os.fchmod(fd, mode)


def preserve_times(fd: int, *, ns: tuple[int, int], creation: int | None = None) -> None:
    if WINDOWS:
        _win.preserve_times(fd, ns=ns, creation=creation)
    else:
        os.utime(fd, ns=ns)


def is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & 0x400)


def entry_kind(entry) -> str | None:
    """Classify a single no-follow stat, skipping only inaccessible entries."""
    try:
        info = entry.stat(follow_symlinks=False)
        if is_reparse(info):
            return None
        if statmod.S_ISDIR(info.st_mode):
            return "directory"
        if statmod.S_ISREG(info.st_mode):
            return "file"
        return None
    except OSError as error:
        if error.errno in {errno.EMFILE, errno.ENFILE}:
            raise
        return None


def validate_root(path) -> None:
    if WINDOWS:
        _win.validate_root(path)


def copy_streams(source_fd: int, target_fd: int) -> None:
    if WINDOWS:
        _win.copy_streams(source_fd, target_fd)


def creation_time(fd: int) -> int | None:
    return _win.creation_time(fd) if WINDOWS else None


def preserve_attributes(source_fd: int, target_fd: int) -> None:
    if WINDOWS:
        _win.preserve_attributes(source_fd, target_fd)


def reject_encrypted_destination(path, *, dir_fd: int) -> None:
    if WINDOWS:
        _win.reject_encrypted_destination(path, dir_fd=dir_fd)
