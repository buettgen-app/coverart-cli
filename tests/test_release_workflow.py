"""Regression tests for the release workflow's trust boundaries."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RELEASE_WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "release.yml"
RELEASE_ID = "379808429"
RELEASE_TAG = "v0.6.1"
RELEASE_SHA = "8c2e688cad72ac433fb5d91c768dbe677a6398dc"


def _folded_env_value(name: str) -> str:
    lines = RELEASE_WORKFLOW.read_text(encoding="utf-8").splitlines()
    marker = f"  {name}: >-"
    start = lines.index(marker) + 1
    program: list[str] = []
    for line in lines[start:]:
        if not line.startswith("    "):
            break
        program.append(line.strip())
    assert program
    return " ".join(program)


def _run_release_lookup(
    pages: list[list[object]], tag: str = RELEASE_TAG
) -> subprocess.CompletedProcess[str]:
    jq = shutil.which("jq")
    assert jq is not None, "jq is required to verify the release workflow"
    payload = "\n".join(json.dumps(page) for page in pages)
    return subprocess.run(
        [jq, "-s", "--arg", "tag", tag, _folded_env_value("RELEASE_LOOKUP_JQ")],
        input=payload,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_draft_state(release: dict[str, object]) -> subprocess.CompletedProcess[str]:
    jq = shutil.which("jq")
    assert jq is not None, "jq is required to verify the release workflow"
    return subprocess.run(
        [
            jq,
            "-e",
            "--arg",
            "id",
            RELEASE_ID,
            "--arg",
            "tag",
            RELEASE_TAG,
            "--arg",
            "sha",
            RELEASE_SHA,
            _folded_env_value("DRAFT_RELEASE_JQ"),
        ],
        input=json.dumps(release),
        check=False,
        capture_output=True,
        text=True,
    )


def test_draft_release_lookup_uses_authenticated_paginated_collection() -> None:
    """Draft lookup must not require the tag ref that publication creates later."""
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert 'gh release view "$RELEASE_TAG"' not in workflow
    assert (
        'release_pages="$(\n'
        "            gh api --paginate \\\n"
        '              "repos/$GITHUB_REPOSITORY/releases?per_page=100"' in workflow
    )
    assert (
        'jq -s --arg tag "$RELEASE_TAG" "$RELEASE_LOOKUP_JQ" \\\n'
        '              <<<"$release_pages"' in workflow
    )


def test_paginated_api_failure_stops_before_release_selection() -> None:
    """A failed later page must not leave a usable partial release response."""
    script = "\n".join(
        [
            'release_pages="$(printf \'[%s]\\n\' \'{"tag_name":"v0.6.1"}\'; exit 42)"',
            "printf '%s' \"$release_pages\"",
        ]
    )
    result = subprocess.run(
        ["bash", "-e", "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 42
    assert result.stdout == ""


def test_draft_is_revalidated_and_published_at_the_bound_commit() -> None:
    """Finalize must not trust mutable draft state captured before build and tests."""
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert workflow.count('"$DRAFT_RELEASE_JQ" <<<"$release"') == 2
    assert "gh release upload" not in workflow
    assert (
        '"https://uploads.github.com/repos/$GITHUB_REPOSITORY/releases/'
        '$RELEASE_ID/assets?name=$encoded_name"' in workflow
    )
    assert '-f tag_name="$RELEASE_TAG"' in workflow
    assert '-f target_commitish="$EXPECTED_RELEASE_SHA"' in workflow
    assert 'gh api "repos/$GITHUB_REPOSITORY/commits/$RELEASE_TAG" --jq .sha' in workflow
    assert 'if [ "$published_sha" != "$EXPECTED_RELEASE_SHA" ]; then' in workflow


def test_expected_mutable_draft_state_is_accepted() -> None:
    release: dict[str, object] = {
        "id": int(RELEASE_ID),
        "draft": True,
        "immutable": False,
        "tag_name": RELEASE_TAG,
        "target_commitish": RELEASE_SHA,
    }

    result = _run_draft_state(release)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", 1),
        ("draft", False),
        ("immutable", True),
        ("tag_name", "v0.6.2"),
        ("target_commitish", "f" * 40),
    ],
)
def test_mutated_draft_state_is_rejected(field: str, value: object) -> None:
    release: dict[str, object] = {
        "id": int(RELEASE_ID),
        "draft": True,
        "immutable": False,
        "tag_name": RELEASE_TAG,
        "target_commitish": RELEASE_SHA,
    }
    release[field] = value

    result = _run_draft_state(release)

    assert result.returncode != 0


def test_draft_release_lookup_returns_exact_match_across_pages() -> None:
    """The exact workflow program must normalize one matching draft."""
    expected = {
        "id": int(RELEASE_ID),
        "draft": True,
        "immutable": False,
        "tag_name": RELEASE_TAG,
        "target_commitish": RELEASE_SHA,
    }
    pages: list[list[object]] = [
        [{"id": 1, "tag_name": "v0.6.0"}],
        [expected, {"id": 2, "tag_name": "v0.5.0"}],
    ]

    result = _run_release_lookup(pages)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == expected


@pytest.mark.parametrize(
    "pages",
    [
        [],
        [
            [{"id": 1, "tag_name": "v0.6.1"}],
            [{"id": 2, "tag_name": "v0.6.1"}],
        ],
    ],
)
def test_draft_release_lookup_fails_closed_without_one_match(
    pages: list[list[object]],
) -> None:
    """Missing or ambiguous releases must stop publication."""
    result = _run_release_lookup(pages)

    assert result.returncode != 0
