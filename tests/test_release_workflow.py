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
BOUND_SHA = "b" * 40
RELEASE_BODY = "## [0.6.1] release notes"


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


def _run_recoverable_state(
    release: dict[str, object],
) -> subprocess.CompletedProcess[str]:
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
            "old_sha",
            RELEASE_SHA,
            "--arg",
            "sha",
            BOUND_SHA,
            _folded_env_value("RECOVERABLE_RELEASE_JQ"),
        ],
        input=json.dumps(release),
        check=False,
        capture_output=True,
        text=True,
    )


def _run_draft_assets(
    release: dict[str, object], assets: list[dict[str, str]]
) -> subprocess.CompletedProcess[str]:
    jq = shutil.which("jq")
    assert jq is not None, "jq is required to verify the release workflow"
    return subprocess.run(
        [
            jq,
            "-e",
            "--argjson",
            "assets",
            json.dumps(assets),
            _folded_env_value("DRAFT_ASSETS_JQ"),
        ],
        input=json.dumps(release),
        check=False,
        capture_output=True,
        text=True,
    )


def _run_exact_tag_lookup(refs: list[object]) -> subprocess.CompletedProcess[str]:
    jq = shutil.which("jq")
    assert jq is not None, "jq is required to verify the release workflow"
    return subprocess.run(
        [
            jq,
            "-c",
            "--arg",
            "ref",
            f"refs/tags/{RELEASE_TAG}",
            _folded_env_value("EXACT_TAG_JQ"),
        ],
        input=json.dumps(refs),
        check=False,
        capture_output=True,
        text=True,
    )


def _run_pypi_state(
    release: dict[str, object],
    assets: list[dict[str, str]],
    *,
    complete: bool,
) -> subprocess.CompletedProcess[str]:
    jq = shutil.which("jq")
    assert jq is not None, "jq is required to verify the release workflow"
    program = "PYPI_COMPLETE_JQ" if complete else "PYPI_EXISTING_JQ"
    return subprocess.run(
        [
            jq,
            "-e",
            "--arg",
            "version",
            "0.6.1",
            "--argjson",
            "assets",
            json.dumps(assets),
            _folded_env_value(program),
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

    assert 'release_ref="$GITHUB_SHA"' in workflow
    assert 'release_ref="$tag_sha"' in workflow
    assert "target=$target_commitish" in workflow
    assert 'git merge-base --is-ancestor "$VALIDATED_DRAFT_TARGET" HEAD' in workflow
    assert "Release recovery includes changes outside the explicit release repair." in workflow
    assert "name: Resolve live release phase" in workflow
    assert "name: Bind mutable draft to exact verified source" in workflow
    assert workflow.count('-f tag_name="$RELEASE_TAG"') == 2
    assert workflow.count('-f target_commitish="$EXPECTED_RELEASE_SHA"') == 2
    assert workflow.count("if: steps.live.outputs.draft == 'true'") == 3
    assert "overwrite: true" in workflow
    assert "gh release upload" not in workflow
    assert (
        '"https://uploads.github.com/repos/$GITHUB_REPOSITORY/releases/'
        '$RELEASE_ID/assets?name=$encoded_name"' in workflow
    )
    assert '-f ref="refs/tags/$RELEASE_TAG"' in workflow
    assert 'validate_draft_release "$release"' in workflow
    assert workflow.count('gh api "repos/$GITHUB_REPOSITORY/git/ref/heads/main"') == 3
    assert workflow.count("git/matching-refs/tags/$RELEASE_TAG") == 4
    assert '"$EXACT_TAG_JQ" <<<"$tag_refs"' in workflow
    assert "refusing PyPI publication" in workflow
    assert "Plan idempotent PyPI upload" in workflow
    assert "packages-dir: pypi-dist/" in workflow
    assert "skip-existing" not in workflow
    assert '"$PYPI_EXISTING_JQ" "$response"' in workflow
    assert '"$PYPI_COMPLETE_JQ" "$response"' in workflow
    assert "integrity/coverart-cli/$version/$encoded_name/provenance" in workflow
    assert "@base64d | fromjson" in workflow


def test_expected_mutable_draft_state_is_accepted() -> None:
    release: dict[str, object] = {
        "id": int(RELEASE_ID),
        "draft": True,
        "immutable": False,
        "prerelease": False,
        "tag_name": RELEASE_TAG,
        "target_commitish": RELEASE_SHA,
        "body": RELEASE_BODY,
    }

    result = _run_draft_state(release)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", 1),
        ("draft", False),
        ("immutable", True),
        ("prerelease", True),
        ("tag_name", "v0.6.2"),
        ("target_commitish", "f" * 40),
    ],
)
def test_mutated_draft_state_is_rejected(field: str, value: object) -> None:
    release: dict[str, object] = {
        "id": int(RELEASE_ID),
        "draft": True,
        "immutable": False,
        "prerelease": False,
        "tag_name": RELEASE_TAG,
        "target_commitish": RELEASE_SHA,
        "body": RELEASE_BODY,
    }
    release[field] = value

    result = _run_draft_state(release)

    assert result.returncode != 0


def test_old_bound_and_published_release_phases_are_recoverable() -> None:
    base: dict[str, object] = {
        "id": int(RELEASE_ID),
        "prerelease": False,
        "tag_name": RELEASE_TAG,
        "body": RELEASE_BODY,
    }
    releases = [
        {
            **base,
            "draft": True,
            "immutable": False,
            "target_commitish": RELEASE_SHA,
        },
        {
            **base,
            "draft": True,
            "immutable": False,
            "target_commitish": BOUND_SHA,
        },
        {
            **base,
            "draft": False,
            "immutable": True,
            "target_commitish": BOUND_SHA,
        },
    ]

    for release in releases:
        result = _run_recoverable_state(release)
        assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "release",
    [
        {
            "id": int(RELEASE_ID),
            "draft": True,
            "immutable": False,
            "prerelease": False,
            "tag_name": RELEASE_TAG,
            "target_commitish": "c" * 40,
        },
        {
            "id": int(RELEASE_ID),
            "draft": False,
            "immutable": True,
            "prerelease": False,
            "tag_name": RELEASE_TAG,
            "target_commitish": RELEASE_SHA,
        },
        {
            "id": int(RELEASE_ID),
            "draft": True,
            "immutable": True,
            "prerelease": False,
            "tag_name": RELEASE_TAG,
            "target_commitish": BOUND_SHA,
        },
        {
            "id": int(RELEASE_ID),
            "draft": False,
            "immutable": False,
            "prerelease": False,
            "tag_name": RELEASE_TAG,
            "target_commitish": BOUND_SHA,
        },
        {
            "id": int(RELEASE_ID),
            "draft": True,
            "immutable": False,
            "prerelease": True,
            "tag_name": RELEASE_TAG,
            "target_commitish": BOUND_SHA,
        },
    ],
)
def test_unrecoverable_release_phases_are_rejected(
    release: dict[str, object],
) -> None:
    result = _run_recoverable_state(release)

    assert result.returncode != 0


def test_exact_uploaded_draft_assets_are_accepted() -> None:
    assets = [
        {"name": "coverart_cli-0.6.1-py3-none-any.whl", "digest": "sha256:aaa"},
        {"name": "coverart_cli-0.6.1.tar.gz", "digest": "sha256:bbb"},
    ]
    release: dict[str, object] = {
        "assets": [
            {"id": 1, "state": "uploaded", **assets[0]},
            {"id": 2, "state": "uploaded", **assets[1]},
        ]
    }

    result = _run_draft_assets(release, assets)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "mutation",
    [
        "digest",
        "state",
        "non_numeric_id",
        "missing",
        "extra",
        "duplicate",
    ],
)
def test_mutated_draft_assets_are_rejected(mutation: str) -> None:
    assets = [
        {"name": "coverart_cli-0.6.1-py3-none-any.whl", "digest": "sha256:aaa"},
        {"name": "coverart_cli-0.6.1.tar.gz", "digest": "sha256:bbb"},
    ]
    release_assets: list[dict[str, object]] = [
        {"id": 1, "state": "uploaded", **assets[0]},
        {"id": 2, "state": "uploaded", **assets[1]},
    ]
    if mutation == "digest":
        release_assets[0]["digest"] = "sha256:poisoned"
    elif mutation == "state":
        release_assets[0]["state"] = "open"
    elif mutation == "non_numeric_id":
        release_assets[0]["id"] = "1"
    elif mutation == "missing":
        release_assets.pop()
    elif mutation == "extra":
        release_assets.append(
            {"id": 3, "state": "uploaded", "name": "extra", "digest": "sha256:ccc"}
        )
    else:
        release_assets[1] = {"id": 3, "state": "uploaded", **assets[0]}

    result = _run_draft_assets({"assets": release_assets}, assets)

    assert result.returncode != 0


def test_partial_and_complete_matching_pypi_states_are_accepted() -> None:
    assets = [
        {"name": "coverart_cli-0.6.1-py3-none-any.whl", "digest": "aaa"},
        {"name": "coverart_cli-0.6.1.tar.gz", "digest": "bbb"},
    ]
    partial = {
        "info": {"version": "0.6.1"},
        "urls": [
            {"filename": assets[0]["name"], "digests": {"sha256": "aaa"}},
        ],
    }
    complete = {
        "info": {"version": "0.6.1"},
        "urls": [
            {"filename": asset["name"], "digests": {"sha256": asset["digest"]}}
            for asset in reversed(assets)
        ],
    }

    assert _run_pypi_state(partial, assets, complete=False).returncode == 0
    assert _run_pypi_state(partial, assets, complete=True).returncode != 0
    assert _run_pypi_state(complete, assets, complete=False).returncode == 0
    assert _run_pypi_state(complete, assets, complete=True).returncode == 0


@pytest.mark.parametrize(
    "urls",
    [
        [{"filename": "coverart_cli-0.6.1.tar.gz", "digests": {"sha256": "bad"}}],
        [{"filename": "unexpected.zip", "digests": {"sha256": "ccc"}}],
        [
            {"filename": "coverart_cli-0.6.1.tar.gz", "digests": {"sha256": "bbb"}},
            {"filename": "coverart_cli-0.6.1.tar.gz", "digests": {"sha256": "bbb"}},
        ],
    ],
)
def test_poisoned_or_ambiguous_pypi_state_is_rejected(
    urls: list[dict[str, object]],
) -> None:
    assets = [
        {"name": "coverart_cli-0.6.1-py3-none-any.whl", "digest": "aaa"},
        {"name": "coverart_cli-0.6.1.tar.gz", "digest": "bbb"},
    ]
    release = {"info": {"version": "0.6.1"}, "urls": urls}

    assert _run_pypi_state(release, assets, complete=False).returncode != 0


def test_wrong_pypi_version_is_rejected() -> None:
    assets = [{"name": "coverart_cli-0.6.1.tar.gz", "digest": "bbb"}]
    release = {"info": {"version": "0.6.2"}, "urls": []}

    assert _run_pypi_state(release, assets, complete=False).returncode != 0


def test_exact_tag_lookup_ignores_prefix_matches() -> None:
    expected = {
        "ref": f"refs/tags/{RELEASE_TAG}",
        "object": {"type": "commit", "sha": RELEASE_SHA},
    }
    refs: list[object] = [
        {"ref": f"refs/tags/{RELEASE_TAG}.1"},
        expected,
        {"ref": f"refs/tags/{RELEASE_TAG}-rc1"},
    ]

    result = _run_exact_tag_lookup(refs)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == expected


@pytest.mark.parametrize(
    "refs",
    [
        [],
        [
            {"ref": f"refs/tags/{RELEASE_TAG}"},
            {"ref": f"refs/tags/{RELEASE_TAG}"},
        ],
    ],
)
def test_exact_tag_lookup_fails_closed_when_ambiguous(
    refs: list[object],
) -> None:
    result = _run_exact_tag_lookup(refs)

    if refs:
        assert result.returncode != 0
    else:
        assert result.returncode == 0
        assert json.loads(result.stdout) is None


def test_draft_release_lookup_returns_exact_match_across_pages() -> None:
    """The exact workflow program must normalize one matching draft."""
    expected = {
        "id": int(RELEASE_ID),
        "draft": True,
        "immutable": False,
        "prerelease": False,
        "tag_name": RELEASE_TAG,
        "target_commitish": RELEASE_SHA,
        "body": RELEASE_BODY,
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
