"""Check tracked files for private contact details, local artifacts and PNG metadata.

This is a deliberately narrow PII guard, not a replacement for Gitleaks or review.
Diagnostics identify locations and categories without echoing matched values.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
HOME_PATH = re.compile(r"(?:/(?:Users|home)/|[A-Za-z]:\\Users\\)([A-Za-z0-9_.-]+)")
EXAMPLE_DOMAINS = {"example.com", "example.net", "example.org", "example.invalid"}
PUBLIC_IDENTITY_DOMAINS = {"users.noreply.github.com", "noreply.github.com"}
GENERATED_DIRS = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".venv",
    "htmlcov",
    "build",
    "dist",
}
PNG_METADATA = {b"eXIf", b"tEXt", b"zTXt", b"iTXt"}


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
        return findings
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
    paths = subprocess.check_output(["git", "ls-files", "-z"]).split(b"\0")
    findings = []
    count = 0
    for raw_path in paths:
        if not raw_path:
            continue
        path = Path(raw_path.decode("utf-8"))
        if path.is_symlink():
            findings.append(f"{path}: tracked symlink requires manual review")
            continue
        count += 1
        findings.extend(check_file(path, path.read_bytes()))
    if findings:
        print("\n".join(findings))
        return 1
    print(f"Repository hygiene passed for {count} tracked files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
