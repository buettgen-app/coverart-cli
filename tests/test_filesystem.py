"""Shared filesystem behavior at a disappearing-entry boundary."""

from __future__ import annotations

import errno

import pytest

from coverart_cli import filesystem as fs


@pytest.mark.parametrize("error", [FileNotFoundError(), PermissionError(), OSError()])
def test_windows_entry_stat_failure_skips_only_that_entry(monkeypatch, error) -> None:
    class VanishedEntry:
        def stat(self, *, follow_symlinks):
            raise error

    monkeypatch.setattr(fs, "WINDOWS", True)
    assert not fs.entry_kind(VanishedEntry())


@pytest.mark.parametrize("code", [errno.EMFILE, errno.ENFILE])
def test_windows_entry_exhaustion_is_not_silently_skipped(monkeypatch, code):
    class ExhaustedEntry:
        def stat(self, *, follow_symlinks):
            raise OSError(code, "descriptor exhaustion")

    monkeypatch.setattr(fs, "WINDOWS", True)
    with pytest.raises(OSError) as caught:
        fs.entry_kind(ExhaustedEntry())
    assert caught.value.errno == code
