"""Regression checks for redacted repository privacy diagnostics."""

import subprocess
from pathlib import Path

import pytest

from scripts.check_repository import check_file, main


def test_private_contact_details_fail_without_exposing_values() -> None:
    address = "person" + "@" + "private.invalid"
    home = "/home/" + "private-person/Music"
    findings = check_file(Path("README.md"), f"{address}\n{home}".encode())
    assert len(findings) == 2
    assert all(address not in finding and home not in finding for finding in findings)


def test_examples_and_public_commit_identity_are_allowed() -> None:
    data = b"you@example.com\nnoreply@users.noreply.github.com\n/Users/example-user/Music"
    assert check_file(Path("README.md"), data) == []


def test_binary_png_metadata_is_rejected() -> None:
    chunk = b"Author\0private-person"
    png = b"\x89PNG\r\n\x1a\n" + len(chunk).to_bytes(4, "big") + b"tEXt" + chunk + b"\0" * 4
    assert check_file(Path("screenshot.png"), png) == [
        "screenshot.png: PNG contains textual or EXIF metadata"
    ]


def test_generated_and_environment_files_are_rejected() -> None:
    for filename in [
        "dist/package.whl",
        ".env.production",
        "src/__pycache__/module.pyc",
        "venv/bin/python",
        "env/bin/python",
        "ENV/bin/python",
        ".tox/bin/python",
    ]:
        assert check_file(Path(filename), b"")
    assert check_file(Path(".env.example"), b"CONTACT=you@example.com") == []


@pytest.mark.parametrize("prefix", ["c:\\users\\", "C:\\USERS\\", "C:\\Users\\"])
def test_windows_home_paths_ignore_casing(prefix) -> None:
    assert check_file(Path("README.md"), (prefix + "private-person\\Music").encode())


def test_scans_staged_snapshot_after_worktree_changes(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "--quiet"], check=True)
    path = tmp_path / "note.txt"
    address = "person" + "@" + "private.invalid"
    path.write_text(address)
    subprocess.run(["git", "add", "note.txt"], check=True)
    path.write_text("clean unstaged content")
    assert main() == 1
    assert address not in capsys.readouterr().out
    path.unlink()
    assert main() == 1  # An unstaged deletion must not hide the indexed content.
    path.write_text("clean content")
    subprocess.run(["git", "add", "note.txt"], check=True)
    path.unlink()
    assert main() == 0  # Reading the indexed blob does not need a worktree file.
    subprocess.run(["git", "rm", "--cached", "note.txt"], check=True)
    assert main() == 0
