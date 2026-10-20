# Copyright (c) 2026 WildDragonKing
# SPDX-License-Identifier: MIT
"""Native Windows end-to-end and handle boundary regression tests."""

from __future__ import annotations

import getpass
import os
import subprocess
import sys
from pathlib import Path

import pytest
from mutagen.id3 import ID3, TALB, TPE1

from coverart_cli import filesystem as fs
from coverart_cli.cli import main
from coverart_cli.core import RunOptions, find_album_dirs, run
from coverart_cli.report import write_report
from coverart_cli.tagging import embed_cover, existing_embedded_size, write_sidecar

from .image_fixtures import VALID_JPEG
from .test_integration import FakeProvider

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="native Windows boundary")


def _track(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tags = ID3()
    tags.add(TPE1(encoding=3, text=["Artist"]))
    tags.add(TALB(encoding=3, text=["Album"]))
    tags.save(path)


def _saved_acl(path: Path) -> list[str]:
    # SE_DACL_AUTO_INHERITED records how Windows computed an ACL; for a
    # protected DACL it does not alter access. CreateFile clears this bookkeeping
    # bit. Compare protection and every ACE, including inherited-ACE flags.
    return [
        line.replace("D:PAI(", "D:P(")
        for line in path.read_text(encoding="utf-16-le").splitlines()[1:]
    ]


def _junction(link: Path, target: Path) -> None:
    # mklink /J requires no elevation or Developer Mode, unlike symbolic links.
    subprocess.run(
        ["cmd", "/d", "/c", "mklink", "/J", str(link), str(target)],
        check=True,
        capture_output=True,
    )


def test_native_library_embed_sidecar_report_and_idempotence(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    library = tmp_path / "🎵 Müsik with spaces"
    album = library / "Artist" / "Album"
    track = album / "01.mp3"
    _track(track)
    # Replacement must retain the existing destination's named streams.
    stream = str(track) + ":coverart-test"
    Path(stream).write_bytes(b"retain this stream")
    before = track.stat().st_mtime_ns
    # Give the source a non-inherited DACL so replacing it with a freshly
    # created sibling would change permissions unless its DACL is copied at creation.
    subprocess.run(
        ["icacls", str(track), "/inheritance:r", "/grant:r", f"{getpass.getuser()}:(F)"],
        check=True,
        capture_output=True,
    )
    acl_before = tmp_path / "acl-before.txt"
    acl_after = tmp_path / "acl-after.txt"
    subprocess.run(
        ["icacls", str(track), "/save", str(acl_before), "/q"], check=True, capture_output=True
    )
    stats = run(RunOptions(root=library, providers=[FakeProvider()], workers=2))
    assert stats.errors == 0
    assert stats.files_embedded == 1
    assert existing_embedded_size(track) == len(VALID_JPEG)
    assert (album / "cover.jpg").read_bytes() == VALID_JPEG
    assert Path(stream).read_bytes() == b"retain this stream"
    assert track.stat().st_mtime_ns == before
    subprocess.run(
        ["icacls", str(track), "/save", str(acl_after), "/q"], check=True, capture_output=True
    )
    assert _saved_acl(acl_after) == _saved_acl(acl_before)
    second = run(RunOptions(root=library, providers=[FakeProvider()]))
    assert second.errors == 0 and second.files_embedded == 0
    output, count = write_report(library, tmp_path / "report.html")
    assert count == 1 and output.is_file()
    assert main([str(library), "--report-only", "--report-html", str(output)]) == 0


def test_junctions_are_skipped_and_rejected_as_root(tmp_path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    outside = tmp_path / "outside"
    _track(outside / "01.mp3")
    link = library / "linked album"
    _junction(link, outside)
    assert find_album_dirs(library) == []
    with pytest.raises(OSError, match="reparse"):
        find_album_dirs(link)
    assert not (outside / "cover.jpg").exists()


def test_open_directory_pins_ancestors_after_parent_descriptor_closed(tmp_path) -> None:
    parent = tmp_path / "parent"
    child = parent / "album"
    child.mkdir(parents=True)
    parent_fd = fs.open(parent, os.O_RDONLY | fs.DIRECTORY | fs.NOFOLLOW)
    child_fd = fs.open("album", os.O_RDONLY | fs.DIRECTORY | fs.NOFOLLOW, dir_fd=parent_fd)
    fs.close(parent_fd)
    try:
        with pytest.raises(PermissionError):
            parent.rename(tmp_path / "moved")
        with pytest.raises(PermissionError):
            child.rename(parent / "moved album")
        assert fs.fstat(child_fd).st_ino == child.stat().st_ino
    finally:
        fs.close(child_fd)
    parent.rename(tmp_path / "moved")


def test_locked_source_prevents_external_writer(tmp_path) -> None:
    track = tmp_path / "01.mp3"
    _track(track)
    fd = fs.open(track, os.O_RDONLY | fs.NOFOLLOW)
    try:
        with pytest.raises(PermissionError):
            track.write_bytes(b"changed")
    finally:
        fs.close(fd)
    assert embed_cover(track, VALID_JPEG)


def test_read_only_track_fails_without_corrupting_original(tmp_path) -> None:
    track = tmp_path / "01.mp3"
    _track(track)
    original = track.read_bytes()
    track.chmod(0o444)
    try:
        assert not embed_cover(track, VALID_JPEG)
        assert track.read_bytes() == original
        assert not list(tmp_path.glob(".coverart-audio-*"))
    finally:
        track.chmod(0o666)


def test_duplicate_directory_handle_keeps_lock_until_last_close(tmp_path) -> None:
    album = tmp_path / "album"
    album.mkdir()
    fd = fs.open(album, os.O_RDONLY | fs.DIRECTORY)
    duplicate = fs.dup(fd)
    fs.close(fd)
    try:
        with pytest.raises(PermissionError):
            album.rename(tmp_path / "moved")
        assert write_sidecar(album, VALID_JPEG, directory_fd=duplicate).is_file()
    finally:
        fs.close(duplicate)
    album.rename(tmp_path / "moved")


@pytest.mark.parametrize("name", ["..", "../outside", "sub/track.mp3", "track.mp3:secret", ""])
def test_directory_relative_names_cannot_escape_or_select_streams(tmp_path, name) -> None:
    fd = fs.open(tmp_path, os.O_RDONLY | fs.DIRECTORY)
    try:
        with pytest.raises(OSError, match="directory-relative"):
            unexpected_fd = fs.open(name, os.O_RDONLY, dir_fd=fd)
            fs.close(unexpected_fd)
    finally:
        fs.close(fd)


def test_exclusive_creation_never_truncates_existing_file(tmp_path) -> None:
    path = tmp_path / "keep.txt"
    path.write_bytes(b"KEEP")
    with pytest.raises(FileExistsError):
        unexpected_fd = fs.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        fs.close(unexpected_fd)
    assert path.read_bytes() == b"KEEP"


def test_unc_paths_rejected_without_network_access() -> None:
    with pytest.raises(OSError, match="local drive"):
        unexpected_fd = fs.open(r"\\server\share\music", os.O_RDONLY | fs.DIRECTORY)
        fs.close(unexpected_fd)


def test_leaf_symlinks_never_modify_external_files(tmp_path) -> None:
    outside = tmp_path / "outside.mp3"
    _track(outside)
    original = outside.read_bytes()
    link = tmp_path / "link.mp3"
    link.symlink_to(outside)
    assert not embed_cover(link, VALID_JPEG)
    assert outside.read_bytes() == original
    album = tmp_path / "album"
    album.mkdir()
    (album / "cover.jpg").symlink_to(outside)
    written = write_sidecar(album, VALID_JPEG)
    assert written.read_bytes() == VALID_JPEG
    assert not written.is_symlink()
    assert outside.read_bytes() == original


def test_wheel_cli_can_generate_report_from_unicode_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    library = tmp_path / "音楽 with spaces"
    _track(library / "Artist" / "Album" / "01.mp3")
    output = tmp_path / "coverage.html"
    python = os.environ.get("COVERART_SMOKE_PYTHON", sys.executable)
    result = subprocess.run(
        [python, "-m", "coverart_cli", str(library), "--report-only", "--report-html", str(output)],
        capture_output=True,
        check=True,
        timeout=30,
    )
    assert b"HTML report (1 albums)" in result.stdout
    assert output.is_file()


def test_unsupported_unc_cli_returns_usage_error(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert main([r"\\server\share\music", "--dry-run"]) == 2
    assert main([r"\\server\share\music", "--report-only", "--report-html", "out.html"]) == 2


def test_source_stays_write_locked_until_replacement(tmp_path, monkeypatch) -> None:
    track = tmp_path / "01.mp3"
    _track(track)
    original = track.read_bytes()
    replace = fs.replace
    calls = []

    def checked_replace(src, dst, *, src_dir_fd, dst_dir_fd, source_fd):
        with pytest.raises(PermissionError):
            track.write_bytes(b"concurrent modification")
        assert track.read_bytes() == original
        calls.append(dst)
        return replace(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd, source_fd=source_fd)

    monkeypatch.setattr(fs, "replace", checked_replace)
    assert embed_cover(track, VALID_JPEG)
    assert calls == [track.name]
    assert existing_embedded_size(track) == len(VALID_JPEG)


def test_mapped_network_drive_rejected_before_volume_access(tmp_path, monkeypatch) -> None:
    from coverart_cli import _windows_filesystem as win

    monkeypatch.setattr(win, "_GetDriveType", lambda _root: 4)

    def unexpected_volume_access(*_args):
        raise AssertionError("network volume must not be queried")

    monkeypatch.setattr(win, "_GetVolume", unexpected_volume_access)
    with pytest.raises(OSError, match="local drive"):
        fs.validate_root(tmp_path)


def test_library_under_traverse_only_parent_is_accessible(tmp_path) -> None:
    parent = tmp_path / "restricted"
    library = parent / "library"
    album = library / "Artist" / "Album"
    _track(album / "01.mp3")
    user = getpass.getuser()
    subprocess.run(
        ["icacls", str(library), "/inheritance:r", "/grant:r", f"{user}:(OI)(CI)(F)"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["icacls", str(parent), "/inheritance:r", "/grant:r", f"{user}:(X,RA)"],
        check=True,
        capture_output=True,
    )
    # Hosted Windows runners retain additional explicit administrator ACEs;
    # an explicit deny proves the test cannot enumerate this ancestor.
    subprocess.run(
        ["icacls", str(parent), "/deny", f"{user}:(RD)"],
        check=True,
        capture_output=True,
    )
    try:
        with pytest.raises(PermissionError):
            list(parent.iterdir())
        assert find_album_dirs(library) == [album]
        stats = run(RunOptions(root=library, providers=[FakeProvider()]))
        assert stats.errors == 0 and stats.files_embedded == 1
    finally:
        subprocess.run(
            ["icacls", str(parent), "/remove:d", user, "/grant:r", f"{user}:(F)"],
            check=True,
            capture_output=True,
        )


@pytest.mark.parametrize("sidecar", [False, True])
def test_failed_atomic_rename_keeps_original(tmp_path, monkeypatch, sidecar):
    from coverart_cli import _windows_filesystem as win

    target = tmp_path / ("cover.jpg" if sidecar else "01.mp3")
    if sidecar:
        target.write_bytes(VALID_JPEG)
    else:
        _track(target)
    original = target.read_bytes()

    actual_nt_set_info = win._NtSetInfo

    def failed_rename(handle, status, buffer, size, kind):
        if kind != 65:
            return actual_nt_set_info(handle, status, buffer, size, kind)
        return -1073741790  # STATUS_ACCESS_DENIED

    monkeypatch.setattr(win, "_NtSetInfo", failed_rename)
    if sidecar:
        with pytest.raises(OSError):
            write_sidecar(tmp_path, VALID_JPEG)
    else:
        assert not embed_cover(target, VALID_JPEG)
    assert target.read_bytes() == original
    assert not list(tmp_path.glob(".coverart-*"))


@pytest.mark.parametrize("sidecar", [False, True])
def test_destination_substitution_never_follows_external_symlink(tmp_path, monkeypatch, sidecar):
    target = tmp_path / ("cover.jpg" if sidecar else "01.mp3")
    outside = tmp_path / "outside"
    outside.mkdir()
    external = outside / target.name
    if sidecar:
        target.write_bytes(VALID_JPEG)
        external.write_bytes(b"external cover")
    else:
        _track(target)
        _track(external)
    original = external.read_bytes()
    # Probe availability before entering the operation under test.
    probe = tmp_path / "probe"
    try:
        probe.symlink_to(external)
    except OSError as error:
        pytest.skip(f"symbolic links unavailable: {error}")
    probe.unlink()
    actual_replace = fs.replace

    def substituted(src, dst, **kwargs):
        target.rename(tmp_path / "saved-original")
        target.symlink_to(external)
        return actual_replace(src, dst, **kwargs)

    monkeypatch.setattr(fs, "replace", substituted)
    if sidecar:
        write_sidecar(tmp_path, VALID_JPEG)
    else:
        assert embed_cover(target, VALID_JPEG)
    assert not target.is_symlink()
    assert external.read_bytes() == original


def test_audio_staging_dacl_matches_private_source_before_copy(tmp_path, monkeypatch):
    from coverart_cli import tagging

    target = tmp_path / "01.mp3"
    _track(target)
    subprocess.run(
        ["icacls", str(target), "/inheritance:r", "/grant:r", f"{getpass.getuser()}:(F)"],
        check=True,
        capture_output=True,
    )
    source_acl = tmp_path / "source-acl"
    subprocess.run(
        ["icacls", str(target), "/save", str(source_acl), "/q"], check=True, capture_output=True
    )
    actual_copy = tagging._copy_audio_file
    checked = []

    def inspect_stage(source_fd, target_fd, size):
        (stage,) = tmp_path.glob(".coverart-audio-*")
        stage_acl = tmp_path / "stage-acl"
        subprocess.run(
            ["icacls", str(stage), "/save", str(stage_acl), "/q"], check=True, capture_output=True
        )
        # icacls output starts with the differing basename; the descriptor follows it.
        assert _saved_acl(stage_acl) == _saved_acl(source_acl)
        checked.append(True)
        actual_copy(source_fd, target_fd, size)

    monkeypatch.setattr(tagging, "_copy_audio_file", inspect_stage)
    assert embed_cover(target, VALID_JPEG)
    assert checked == [True]


def _security_identity(path: Path) -> str:
    import ctypes
    import ctypes.wintypes as wintypes

    from coverart_cli import _windows_filesystem as win

    descriptor = ctypes.c_void_p()
    fd = fs.open(path, os.O_RDONLY | fs.NOFOLLOW)
    try:
        result = win._GetSecurity(
            win._crt.get_osfhandle(fd), 1, 3, None, None, None, None, ctypes.byref(descriptor)
        )
        if result:
            raise win._ctypes.WinError(result)
        convert = win._advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW
        convert.argtypes = [
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        convert.restype = wintypes.BOOL
        rendered = ctypes.c_void_p()
        try:
            if not convert(descriptor, 1, 3, ctypes.byref(rendered), None):
                raise win._ctypes.WinError(win._ctypes.get_last_error())
            return ctypes.wstring_at(rendered)
        finally:
            if rendered:
                win._LocalFree(rendered)
    finally:
        if descriptor:
            win._LocalFree(descriptor)
        fs.close(fd)


def test_creation_time_and_security_identity_survive_embedding(tmp_path):
    from coverart_cli import _windows_filesystem as win

    target = tmp_path / "01.mp3"
    _track(target)
    fd = fs.open(target, os.O_RDWR | fs.NOFOLLOW)
    try:
        created = 132223104000000000  # An old FILETIME, visibly different from staging creation.
        win.preserve_times(
            fd, ns=(target.stat().st_atime_ns, target.stat().st_mtime_ns), creation=created
        )
    finally:
        fs.close(fd)
    identity = _security_identity(target)
    assert embed_cover(target, VALID_JPEG)
    assert _security_identity(target) == identity
    fd = fs.open(target, os.O_RDONLY | fs.NOFOLLOW)
    try:
        assert fs.creation_time(fd) == created
    finally:
        fs.close(fd)


def test_foreign_owner_is_retained_or_replacement_refused(tmp_path):
    target = tmp_path / "01.mp3"
    _track(target)
    result = subprocess.run(["icacls", str(target), "/setowner", "*S-1-5-18"], capture_output=True)
    if result.returncode:
        pytest.skip("runner cannot assign SYSTEM ownership")
    identity = _security_identity(target)
    original = target.read_bytes()
    updated = embed_cover(target, VALID_JPEG)
    assert _security_identity(target) == identity
    if not updated:
        assert target.read_bytes() == original
    assert not list(tmp_path.glob(".coverart-*"))


def test_encrypted_audio_is_rejected_without_plaintext_staging(tmp_path):
    target = tmp_path / "01.mp3"
    _track(target)
    subprocess.run(["cipher", "/e", "/a", str(target)], capture_output=True, timeout=30)
    if not target.stat().st_file_attributes & 0x4000:
        pytest.skip("EFS is unavailable on this runner")
    original = target.read_bytes()
    assert not embed_cover(target, VALID_JPEG)
    assert target.stat().st_file_attributes & 0x4000
    assert target.read_bytes() == original
    assert not list(tmp_path.glob(".coverart-*"))


def test_reparse_volume_boundary_is_an_unsupported_root(tmp_path):
    from coverart_cli.errors import UnsupportedPlatformError

    outside = tmp_path / "outside"
    _track(outside / "01.mp3")
    mount = tmp_path / "mounted-volume"
    _junction(mount, outside)
    with pytest.raises(UnsupportedPlatformError, match="reparse"):
        find_album_dirs(mount)
    assert main([str(mount), "--report-only"]) == 2
    assert not (outside / "cover.jpg").exists()


@pytest.mark.parametrize("sidecar", [False, True])
def test_verified_staging_handle_blocks_name_substitution(tmp_path, monkeypatch, sidecar):
    target = tmp_path / ("cover.jpg" if sidecar else "01.mp3")
    if sidecar:
        target.write_bytes(VALID_JPEG)
    else:
        _track(target)
    actual_replace = fs.replace
    attempts = []

    def cannot_substitute(src, dst, **kwargs):
        assert kwargs["source_fd"] >= 0
        stage = tmp_path / src
        with pytest.raises(PermissionError):
            stage.rename(tmp_path / "stolen-stage")
        with pytest.raises(PermissionError):
            stage.write_bytes(b"substituted data")
        attempts.append(True)
        return actual_replace(src, dst, **kwargs)

    monkeypatch.setattr(fs, "replace", cannot_substitute)
    if sidecar:
        write_sidecar(tmp_path, VALID_JPEG)
        assert target.read_bytes() == VALID_JPEG
    else:
        assert embed_cover(target, VALID_JPEG)
        assert existing_embedded_size(target) == len(VALID_JPEG)
    assert attempts == [True]
    assert not list(tmp_path.glob(".coverart-*"))


def test_encrypted_sidecar_is_not_replaced_with_plaintext(tmp_path):
    target = tmp_path / "cover.jpg"
    target.write_bytes(VALID_JPEG)
    subprocess.run(["cipher", "/e", "/a", str(target)], capture_output=True, timeout=30)
    if not target.stat().st_file_attributes & 0x4000:
        pytest.skip("EFS is unavailable on this runner")
    original = target.read_bytes()
    with pytest.raises(OSError, match="EFS"):
        write_sidecar(tmp_path, VALID_JPEG)
    assert target.stat().st_file_attributes & 0x4000
    assert target.read_bytes() == original
    assert not list(tmp_path.glob(".coverart-*"))


def test_windows_before_1709_is_rejected_before_volume_access(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from coverart_cli import _windows_filesystem as win
    from coverart_cli.errors import UnsupportedPlatformError

    monkeypatch.setattr(win._system, "getwindowsversion", lambda: SimpleNamespace(build=15063))

    def unexpected_volume_call(*args):
        pytest.fail("unsupported Windows must be rejected before volume access")

    monkeypatch.setattr(win, "_GetVolume", unexpected_volume_call)
    with pytest.raises(UnsupportedPlatformError, match="1709"):
        fs.validate_root(tmp_path)
    assert main([str(tmp_path), "--report-only"]) == 2


def test_audio_retains_hidden_system_indexing_and_compression_attributes(tmp_path):
    import ctypes
    import ctypes.wintypes as wintypes

    from coverart_cli import _windows_filesystem as win

    target = tmp_path / "01.mp3"
    _track(target)
    fd = fs.open(target, os.O_RDWR | fs.NOFOLLOW)
    try:
        native = win._crt.get_osfhandle(fd)
        compression = wintypes.WORD(1)
        returned = wintypes.DWORD()
        assert win._DeviceControl(
            native,
            0x9C040,
            ctypes.byref(compression),
            ctypes.sizeof(compression),
            None,
            0,
            ctypes.byref(returned),
            None,
        )
        attributes = win._BasicInfo()
        attributes.attributes = 0x2 | 0x4 | 0x20 | 0x2000
        assert win._SetInfo(native, 0, ctypes.byref(attributes), ctypes.sizeof(attributes))
        before = win._attributes(native)
        assert before & (0x2 | 0x4 | 0x800 | 0x2000) == 0x2 | 0x4 | 0x800 | 0x2000
    finally:
        fs.close(fd)
    assert embed_cover(target, VALID_JPEG)
    assert target.stat().st_file_attributes == before
    assert existing_embedded_size(target) == len(VALID_JPEG)


def test_hardlinked_audio_is_refused_without_breaking_links(tmp_path):
    target = tmp_path / "01.mp3"
    _track(target)
    alias = tmp_path / "linked.mp3"
    os.link(target, alias)
    original = target.read_bytes()
    assert not embed_cover(target, VALID_JPEG)
    assert target.read_bytes() == alias.read_bytes() == original
    assert target.stat().st_ino == alias.stat().st_ino
    assert target.stat().st_nlink == 2
    assert not list(tmp_path.glob(".coverart-*"))


def test_directory_fstat_uses_handle_after_path_substitution(tmp_path, monkeypatch):
    library = tmp_path / "library"
    library.mkdir()
    fd = fs.open(library, os.O_RDONLY | fs.DIRECTORY | fs.NOFOLLOW)
    original_stat = os.stat

    def forbidden_path_stat(path, *args, **kwargs):
        if not isinstance(path, int):
            pytest.fail("directory fstat must never resolve a pathname")
        return original_stat(path, *args, **kwargs)

    try:
        identity = fs.fstat(fd)
        monkeypatch.setattr(os, "stat", forbidden_path_stat)
        actual = fs.fstat(fd)
        assert (actual.st_dev, actual.st_ino) == (identity.st_dev, identity.st_ino)
    finally:
        fs.close(fd)


def test_substituted_drive_is_rejected_before_volume_access(tmp_path, monkeypatch):
    from coverart_cli import _windows_filesystem as win
    from coverart_cli.errors import UnsupportedPlatformError

    def substituted(_drive, target, _length):
        target.value = "\\??\\C:\\outside"
        return len(target.value) + 1

    monkeypatch.setattr(win, "_QueryDevice", substituted)
    monkeypatch.setattr(win, "_GetVolume", lambda *args: pytest.fail("alias queried as volume"))
    with pytest.raises(UnsupportedPlatformError, match="substituted"):
        fs.validate_root(tmp_path)
    assert main([str(tmp_path), "--report-only"]) == 2


def test_integrity_label_survives_audio_replacement(tmp_path):
    import ctypes
    import ctypes.wintypes as wintypes

    from coverart_cli import _windows_filesystem as win

    target = tmp_path / "01.mp3"
    _track(target)
    subprocess.run(
        ["icacls", str(target), "/setintegritylevel", "H"], check=True, capture_output=True
    )

    def label():
        fd = fs.open(target, os.O_RDONLY | fs.NOFOLLOW)
        try:
            with win.security_descriptor(fd) as descriptor:
                convert = win._advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW
                convert.argtypes = [
                    ctypes.c_void_p,
                    wintypes.DWORD,
                    wintypes.DWORD,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                ]
                convert.restype = wintypes.BOOL
                result = ctypes.c_void_p()
                try:
                    assert convert(descriptor, 1, 0x18, ctypes.byref(result), None)
                    return ctypes.wstring_at(result)
                finally:
                    if result:
                        win._LocalFree(result)
        finally:
            fs.close(fd)

    before = label()
    assert "ML" in before and "HI" in before
    assert embed_cover(target, VALID_JPEG)
    assert label() == before


def test_unreadable_sacl_policy_keeps_original_and_creates_no_stage(tmp_path, monkeypatch):
    from coverart_cli import _windows_filesystem as win

    target = tmp_path / "01.mp3"
    _track(target)
    original = target.read_bytes()

    def unavailable(*args):
        win._ctypes.set_last_error(1300)  # ERROR_NOT_ALL_ASSIGNED
        return True

    monkeypatch.setattr(win, "_AdjustPrivileges", unavailable)
    assert not embed_cover(target, VALID_JPEG)
    assert target.read_bytes() == original
    assert not list(tmp_path.glob(".coverart-*"))


def test_handle_directory_enumeration_reads_unicode_inventory(tmp_path):
    library = tmp_path / "library"
    library.mkdir()
    expected = {"🎵 track.mp3", "音楽.flac", "Album"}
    (library / "Album").mkdir()
    for name in expected - {"Album"}:
        (library / name).write_bytes(b"fixture")
    fd = fs.open(library, os.O_RDONLY | fs.DIRECTORY | fs.NOFOLLOW)
    try:
        for _ in range(2):
            with fs.scandir(fd) as entries:
                found = {entry.name: entry.stat(follow_symlinks=False) for entry in entries}
            assert set(found) == expected
            assert found["🎵 track.mp3"].st_size == 7
    finally:
        fs.close(fd)


def test_failed_child_canonicalization_releases_directory_lock(tmp_path, monkeypatch):
    from coverart_cli import _windows_filesystem as win

    album = tmp_path / "album"
    album.mkdir()
    parent_fd = fs.open(tmp_path, os.O_RDONLY | fs.DIRECTORY | fs.NOFOLLOW)
    try:

        def fail(_handle):
            raise OSError("injected canonicalization failure")

        monkeypatch.setattr(win, "_final_nt_path", fail)
        with pytest.raises(OSError, match="canonicalization"):
            child_fd = fs.open("album", os.O_RDONLY | fs.DIRECTORY | fs.NOFOLLOW, dir_fd=parent_fd)
            fs.close(child_fd)  # Also release an unexpected success before pytest fails.
        album.rename(tmp_path / "renamed")
    finally:
        fs.close(parent_fd)
    tmp_path.rename(tmp_path.with_name(tmp_path.name + "-released"))


def test_extended_attributes_survive_audio_replacement(tmp_path):
    import ctypes
    import ctypes.wintypes as wintypes
    import struct

    from coverart_cli import _windows_filesystem as win

    target = tmp_path / "01.mp3"
    _track(target)
    name, value = b"COVERARTPROBE", b"private-metadata"
    payload = struct.pack("<IBBH", 0, 0, len(name), len(value)) + name + b"\0" + value
    set_ea = win._ntdll.NtSetEaFile
    set_ea.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, wintypes.ULONG]
    set_ea.restype = ctypes.c_long
    query_ea = win._ntdll.NtQueryEaFile
    query_ea.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.ULONG,
        ctypes.c_ubyte,
        ctypes.c_void_p,
        wintypes.ULONG,
        ctypes.c_void_p,
        ctypes.c_ubyte,
    ]
    query_ea.restype = ctypes.c_long
    fd = os.open(target, os.O_RDWR | getattr(os, "O_BINARY", 0))
    try:
        status = win._IoStatus()
        data = ctypes.create_string_buffer(payload)
        code = set_ea(win._crt.get_osfhandle(fd), ctypes.byref(status), data, len(payload))
        assert code >= 0, win._nt_error(code)
    finally:
        os.close(fd)

    def attributes():
        fd = fs.open(target, os.O_RDONLY | fs.NOFOLLOW)
        try:
            data = ctypes.create_string_buffer(65536)
            status = win._IoStatus()
            code = query_ea(
                win._crt.get_osfhandle(fd),
                ctypes.byref(status),
                data,
                len(data),
                False,
                None,
                0,
                None,
                True,
            )
            assert code >= 0, win._nt_error(code)
            return data.raw[: status.information]
        finally:
            fs.close(fd)

    before = attributes()
    assert name in before and value in before
    assert embed_cover(target, VALID_JPEG)
    assert attributes() == before


def test_case_sensitive_directory_keeps_distinct_tracks(tmp_path):
    library = tmp_path / "library"
    library.mkdir()
    subprocess.run(
        ["fsutil", "file", "setCaseSensitiveInfo", str(library), "enable"],
        check=True,
        capture_output=True,
    )
    upper, lower = library / "Track.mp3", library / "track.mp3"
    _track(upper)
    _track(lower)
    assert upper.stat().st_ino != lower.stat().st_ino
    lower_before = lower.read_bytes()
    assert embed_cover(upper, VALID_JPEG)
    assert existing_embedded_size(upper) == len(VALID_JPEG)
    assert lower.read_bytes() == lower_before
    assert existing_embedded_size(lower) == 0
    assert embed_cover(lower, VALID_JPEG)
    assert existing_embedded_size(lower) == len(VALID_JPEG)


def test_object_identity_metadata_is_refused_without_changing_source(tmp_path):
    target = tmp_path / "01.mp3"
    _track(target)
    subprocess.run(["fsutil", "objectid", "create", str(target)], check=True, capture_output=True)
    before = target.read_bytes()
    identity = subprocess.run(
        ["fsutil", "objectid", "query", str(target)], check=True, capture_output=True
    ).stdout
    assert not embed_cover(target, VALID_JPEG)
    assert target.read_bytes() == before
    assert (
        subprocess.run(
            ["fsutil", "objectid", "query", str(target)], check=True, capture_output=True
        ).stdout
        == identity
    )
    assert not list(tmp_path.glob(".coverart-*"))


def test_case_sensitive_tracks_are_independent_through_batch_and_report(tmp_path):
    from coverart_cli.report import scan_library

    library = tmp_path / "library"
    library.mkdir()
    subprocess.run(
        ["fsutil", "file", "setCaseSensitiveInfo", str(library), "enable"],
        check=True,
        capture_output=True,
    )
    upper, lower = library / "Track.mp3", library / "track.mp3"
    _track(upper)
    _track(lower)
    assert upper.stat().st_ino != lower.stat().st_ino
    stats = run(RunOptions(root=library, providers=[FakeProvider()], do_sidecar=False))
    assert stats.errors == 0 and stats.files_embedded == 2
    assert existing_embedded_size(upper) == existing_embedded_size(lower) == len(VALID_JPEG)
    entries = scan_library(library)
    assert len(entries) == 1 and entries[0].file_count == 2 and entries[0].has_cover
    second = run(RunOptions(root=library, providers=[FakeProvider()], do_sidecar=False))
    assert second.errors == 0 and second.files_embedded == 0
    assert second.files_already_embedded == 2


def test_strict_redirected_stderr_preserves_unicode_error_exit(tmp_path):
    missing = tmp_path / "音楽 does not exist"
    script = (
        "import sys; sys.stderr.reconfigure(encoding='cp1252', errors='strict'); "
        "from coverart_cli.cli import main; sys.exit(main(sys.argv[1:]))"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(missing),
            "--report-only",
            "--report-html",
            str(tmp_path / "report.html"),
        ],
        capture_output=True,
    )
    assert result.returncode == 1
    assert b"\\u97f3\\u697d" in result.stderr
    assert b"Traceback" not in result.stderr and b"UnicodeEncodeError" not in result.stderr
    assert not (tmp_path / "report.html").exists()


@pytest.mark.parametrize("legacy", [False, True])
def test_ordinary_library_accepts_different_path_casing(tmp_path, monkeypatch, legacy):
    from types import SimpleNamespace

    from coverart_cli import _windows_filesystem as win
    from coverart_cli.report import scan_library

    library = tmp_path / "MyMusic"
    target = library / "01.mp3"
    _track(target)
    if legacy:
        monkeypatch.setattr(win._system, "getwindowsversion", lambda: SimpleNamespace(build=16299))
        original_info = win._GetInfo

        def legacy_info(handle, kind, *args):
            if kind == 23:
                pytest.fail("Windows 1709 must not query unavailable case-sensitive info")
            return original_info(handle, kind, *args)

        monkeypatch.setattr(win, "_GetInfo", legacy_info)
    alternate = Path(str(library).swapcase())
    stats = run(RunOptions(root=alternate, providers=[FakeProvider()], do_sidecar=False))
    assert stats.errors == 0 and stats.files_embedded == 1
    assert existing_embedded_size(target) == len(VALID_JPEG)
    entries = scan_library(alternate)
    assert len(entries) == 1 and entries[0].file_count == 1 and entries[0].has_cover


def test_token_restoration_failure_closes_stage_and_retains_source(tmp_path, monkeypatch):
    import ctypes
    import ctypes.wintypes as wintypes

    from coverart_cli import _windows_filesystem as win

    # This test starts without impersonation and must restore that state even
    # after deliberately making the normal restore operation fail.
    previous = wintypes.HANDLE()
    assert not win._OpenThreadToken(win._GetThread(), 8, True, ctypes.byref(previous))
    assert win._ctypes.get_last_error() == 1008
    target = tmp_path / "01.mp3"
    _track(target)
    before = target.read_bytes()
    original_set = win._SetThreadToken
    restores = 0

    def fail_restore(thread, token):
        nonlocal restores
        if not getattr(token, "value", token):
            restores += 1
            win._ctypes.set_last_error(5)
            return False
        return original_set(thread, token)

    monkeypatch.setattr(win, "_SetThreadToken", fail_restore)
    try:
        assert not embed_cover(target, VALID_JPEG)
    finally:
        assert original_set(None, None)
    assert restores == 1
    assert target.read_bytes() == before
    assert not list(tmp_path.glob(".coverart-*"))
    tmp_path.rename(tmp_path.with_name(tmp_path.name + "-released"))


@pytest.mark.parametrize("permission", ["WD", "DC", "WDAC"])
def test_shared_write_directory_is_refused_before_staging(tmp_path, permission) -> None:
    track = tmp_path / "01.mp3"
    _track(track)
    original = track.read_bytes()
    subprocess.run(
        ["icacls", str(tmp_path), "/grant", f"*S-1-1-0:({permission})"],
        check=True,
        capture_output=True,
    )
    assert not embed_cover(track, VALID_JPEG)
    assert track.read_bytes() == original
    with pytest.raises(PermissionError, match="untrusted writers"):
        write_sidecar(tmp_path, VALID_JPEG)
    assert not list(tmp_path.glob(".coverart-*"))
    output, count = write_report(tmp_path, tmp_path / "report.html")
    assert count == 1 and output.is_file()


def test_shared_read_directory_allows_native_writes(tmp_path) -> None:
    track = tmp_path / "01.mp3"
    _track(track)
    subprocess.run(
        ["icacls", str(tmp_path), "/grant", "*S-1-1-0:(RX)"],
        check=True,
        capture_output=True,
    )
    assert embed_cover(track, VALID_JPEG)
    write_sidecar(tmp_path, VALID_JPEG)
    assert existing_embedded_size(track) == len(VALID_JPEG)


@pytest.mark.parametrize("sidecar", [False, True])
def test_custom_ntfs_short_alias_survives_successful_replacement(tmp_path, sidecar) -> None:
    track = tmp_path / ("cover.jpg" if sidecar else "VeryLongMusicTitle.mp3")
    if sidecar:
        track.write_bytes(VALID_JPEG)
    else:
        _track(track)
    subprocess.run(
        ["fsutil", "file", "setshortname", str(track), "LEGACY.MP3"],
        check=True,
        capture_output=True,
    )
    alias = tmp_path / "LEGACY.MP3"
    # GetShortPathName may return an already-8.3-compatible long name even
    # when it has a different custom alias. Exercise the alias itself.
    assert alias.samefile(track)
    if sidecar:
        assert write_sidecar(tmp_path, VALID_JPEG) == track
    else:
        assert embed_cover(track, VALID_JPEG)
        assert existing_embedded_size(track) == len(VALID_JPEG)
    assert alias.samefile(track)
    assert alias.read_bytes() == track.read_bytes()
    assert not list(tmp_path.glob(".coverart-audio-*"))


@pytest.mark.parametrize("sidecar", [False, True])
def test_new_directory_write_grant_before_commit_retains_destination(
    tmp_path, monkeypatch, sidecar
):
    target = tmp_path / ("cover.jpg" if sidecar else "01.mp3")
    if sidecar:
        target.write_bytes(VALID_JPEG)
    else:
        _track(target)
    original = target.read_bytes()
    replace = fs.replace

    def changed_policy(src, dst, **kwargs):
        subprocess.run(
            ["icacls", str(tmp_path), "/grant", "*S-1-1-0:(WD)"],
            check=True,
            capture_output=True,
        )
        return replace(src, dst, **kwargs)

    monkeypatch.setattr(fs, "replace", changed_policy)
    if sidecar:
        with pytest.raises(PermissionError, match="untrusted writers"):
            write_sidecar(tmp_path, VALID_JPEG)
    else:
        assert not embed_cover(target, VALID_JPEG)
    assert target.read_bytes() == original
    assert not list(tmp_path.glob(".coverart-*"))


@pytest.mark.parametrize("sidecar", [False, True])
def test_destination_in_place_writes_are_blocked_at_native_commit(tmp_path, monkeypatch, sidecar):
    from coverart_cli import _windows_filesystem as win

    target = tmp_path / ("cover.jpg" if sidecar else "01.mp3")
    if sidecar:
        target.write_bytes(b"original cover")
    else:
        _track(target)
    original = target.read_bytes()
    actual = win._NtSetInfo
    attempts = []

    def checked_commit(handle, status, buffer, size, kind):
        if kind == 65:
            with pytest.raises(PermissionError):
                target.write_bytes(b"concurrent in-place change")
            assert target.read_bytes() == original
            attempts.append(True)
        return actual(handle, status, buffer, size, kind)

    monkeypatch.setattr(win, "_NtSetInfo", checked_commit)
    if sidecar:
        assert write_sidecar(tmp_path, VALID_JPEG).read_bytes() == VALID_JPEG
    else:
        assert embed_cover(target, VALID_JPEG)
        assert existing_embedded_size(target) == len(VALID_JPEG)
    assert attempts == [True]
    assert not list(tmp_path.glob(".coverart-*"))
