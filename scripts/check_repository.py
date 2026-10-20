# Copyright (c) 2026 WildDragonKing
# SPDX-License-Identifier: MIT

"""Check tracked files for privacy, local artifacts and source license notices.

This is a deliberately narrow PII guard, not a replacement for Gitleaks or review.
Diagnostics identify locations and categories without echoing matched values.
Source notices cover Python (including stubs) and HTML with embedded CSS/JavaScript.
New source languages or third-party licenses require an explicit inventory review.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
HOME_PATH = re.compile(r"(?:/(?:Users|home)/|(?i:[A-Za-z]:\\Users\\))([A-Za-z0-9_.-]+)")
EXAMPLE_DOMAINS = {"example.com", "example.net", "example.org", "example.invalid"}
PUBLIC_IDENTITY_DOMAINS = {"users.noreply.github.com", "noreply.github.com"}
GENERATED_DIRS = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".venv",
    "venv",
    "env",
    "ENV",
    ".tox",
    "htmlcov",
    "build",
    "dist",
}
PNG_METADATA = {b"eXIf", b"tEXt", b"zTXt", b"iTXt"}
SOURCE_SUFFIXES = {".py", ".pyi", ".html"}
COPYRIGHT_NOTICE = re.compile(r"Copyright \(c\) \d{4}(?:-\d{4})? \S.*")


def check_source_notices(path: Path, text: str) -> list[str]:
    """Require actual header comments, not matching strings in executable code."""
    if path.suffix not in SOURCE_SUFFIXES:
        return []
    lines = []
    if path.suffix in {".py", ".pyi"}:
        for line in text.splitlines()[:20]:
            if not line.strip():
                continue
            if not line.startswith("#"):
                break
            lines.append(line[1:].strip())
    else:
        header = re.match(r"\s*(?:<!doctype html>\s*)?<!--(.*?)-->", text, re.I | re.S)
        if header:
            lines = [line.strip() for line in header.group(1).splitlines()[:20]]
    findings = []
    if not any(COPYRIGHT_NOTICE.fullmatch(line) for line in lines):
        findings.append(f"{path}: missing source-header copyright notice")
    if "SPDX-License-Identifier: MIT" not in lines:
        findings.append(f"{path}: missing or unreviewed source-header SPDX license")
    return findings


def check_file(path: Path, data: bytes) -> list[str]:
    """Return redacted diagnostics for one repository-relative file."""
    findings = []
    if (
        any(part in GENERATED_DIRS or part.endswith(".egg-info") for part in path.parts)
        or path.suffix in {".pyc", ".pyo", ".log"}
        or path.name in {".coverage", "id_rsa", "id_ed25519", ".env", ".envrc"}
        or (path.name.startswith(".env.") and path.name != ".env.example")
    ):
        findings.append(f"{path}: local/generated or sensitive file is tracked")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        if path.suffix in SOURCE_SUFFIXES:
            findings.append(f"{path}: source file contains PNG data")
        position = 8
        while position + 12 <= len(data):
            size = int.from_bytes(data[position : position + 4], "big")
            chunk = data[position + 4 : position + 8]
            if position + 12 + size > len(data):
                findings.append(f"{path}: malformed PNG chunk")
                break
            if chunk in PNG_METADATA:
                findings.append(f"{path}: PNG contains textual or EXIF metadata")
            position += size + 12
            if chunk == b"IEND":
                break
        return findings
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        if path.suffix in SOURCE_SUFFIXES:
            findings.append(f"{path}: source file is not valid UTF-8")
        return findings
    findings.extend(check_source_notices(path, text))
    for number, line in enumerate(text.splitlines(), 1):
        for match in EMAIL.finditer(line):
            domain = match.group(1).lower()
            if domain not in EXAMPLE_DOMAINS | PUBLIC_IDENTITY_DOMAINS:
                findings.append(f"{path}:{number}: non-example email address")
        for match in HOME_PATH.finditer(line):
            if match.group(1) != "example-user":
                findings.append(f"{path}:{number}: personal home-directory path")
    return findings


def main() -> int:
    entries = subprocess.check_output(["git", "ls-files", "--stage", "-z"]).split(b"\0")
    findings = []
    count = 0
    for entry in entries:
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, object_id, stage = metadata.split()
        path = Path(raw_path.decode("utf-8"))
        if stage != b"0":
            findings.append(f"{path}: unresolved index entry")
            continue
        if mode not in {b"100644", b"100755"}:
            findings.append(f"{path}: tracked symlink or submodule requires manual review")
            continue
        count += 1
        data = subprocess.check_output(["git", "cat-file", "blob", object_id.decode("ascii")])
        findings.extend(check_file(path, data))
    if findings:
        print("\n".join(findings))
        return 1
    print(f"Repository hygiene passed for {count} tracked files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
