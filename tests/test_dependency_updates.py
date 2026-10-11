"""Cross-file contracts needed for Renovate to regenerate the canonical locks."""

from __future__ import annotations

import json
import shlex
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize("kind", ["attestation", "ci", "build", "fuzz"])
def test_lock_header_is_renovate_compatible_and_matches_ci(kind: str) -> None:
    path = ROOT / f"requirements-{kind}.txt"
    command = path.read_text().splitlines()[1].removeprefix("#    ")
    args = shlex.split(command)
    assert args[:3] == ["uv", "pip", "compile"]
    assert f"--output-file={path.name}" in args
    assert "--generate-hashes" in args and "--universal" in args
    assert not {"--extra", "--output-file"}.intersection(args)
    if kind == "ci":
        assert "pyproject.toml" in args and "--extra=dev" in args
    assert command in (ROOT / ".github/workflows/ci.yml").read_text()


def test_renovate_compiler_constraint_matches_ci() -> None:
    config = json.loads((ROOT / "renovate.json").read_text())
    version = config["constraints"]["uv"].removeprefix("==")
    assert f'version: "{version}"' in (ROOT / ".github/workflows/ci.yml").read_text()
