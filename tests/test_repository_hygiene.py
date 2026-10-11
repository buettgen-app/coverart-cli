"""Regression checks for redacted repository privacy diagnostics."""

from pathlib import Path

from scripts.check_repository import check_file


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
    for filename in ["dist/package.whl", ".env.production", "src/__pycache__/module.pyc"]:
        assert check_file(Path(filename), b"")
    assert check_file(Path(".env.example"), b"CONTACT=you@example.com") == []
