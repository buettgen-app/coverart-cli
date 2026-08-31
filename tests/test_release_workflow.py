"""Regression tests for the release workflow's trust boundaries."""

from __future__ import annotations

import base64
import copy
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

RELEASE_WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "release.yml"
CI_WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml"
RELEASE_ID = "379808429"
RELEASE_TAG = "v0.6.1"
RELEASE_SHA = "8c2e688cad72ac433fb5d91c768dbe677a6398dc"
BOUND_SHA = "b" * 40
RELEASE_BODY = "## [0.6.1] release notes"
ATTESTED_NAME = "coverart_cli-0.6.1.tar.gz"
ATTESTED_DIGEST = "b" * 64


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


def _run_dispatch_state(
    release: dict[str, object],
) -> subprocess.CompletedProcess[str]:
    jq = shutil.which("jq")
    assert jq is not None, "jq is required to verify the release workflow"
    return subprocess.run(
        [
            jq,
            "-e",
            "--arg",
            "tag",
            RELEASE_TAG,
            "--arg",
            "sha",
            RELEASE_SHA,
            _folded_env_value("DISPATCH_RELEASE_JQ"),
        ],
        input=json.dumps(release),
        check=False,
        capture_output=True,
        text=True,
    )


def _run_immutable_release_state(
    settings: dict[str, object],
) -> subprocess.CompletedProcess[str]:
    jq = shutil.which("jq")
    assert jq is not None, "jq is required to verify the release workflow"
    return subprocess.run(
        [jq, "-e", _folded_env_value("IMMUTABLE_RELEASES_JQ")],
        input=json.dumps(settings),
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


def _run_provenance_state(
    provenance: dict[str, Any],
    *,
    name: str = ATTESTED_NAME,
    digest: str = ATTESTED_DIGEST,
) -> subprocess.CompletedProcess[str]:
    jq = shutil.which("jq")
    assert jq is not None, "jq is required to verify the release workflow"
    return subprocess.run(
        [
            jq,
            "-e",
            "--arg",
            "name",
            name,
            "--arg",
            "digest",
            digest,
            _folded_env_value("PYPI_PROVENANCE_JQ"),
        ],
        input=json.dumps(provenance),
        check=False,
        capture_output=True,
        text=True,
    )


def _provenance_payload(
    *,
    repository: str = "buettgen-app/coverart-cli",
    workflow: str = "release.yml",
    environment: str = "pypi",
    kind: str = "GitHub",
    api_version: int = 1,
    attestation_version: int = 1,
    name: str = ATTESTED_NAME,
    digest: str = ATTESTED_DIGEST,
    statement_type: str = "https://in-toto.io/Statement/v1",
    predicate_type: str = "https://docs.pypi.org/attestations/publish/v1",
    predicate: object = None,
) -> dict[str, Any]:
    statement = {
        "_type": statement_type,
        "subject": [{"name": name, "digest": {"sha256": digest}}],
        "predicateType": predicate_type,
        "predicate": predicate,
    }
    encoded = base64.b64encode(json.dumps(statement, separators=(",", ":")).encode()).decode()
    return {
        "version": api_version,
        "attestation_bundles": [
            {
                "publisher": {
                    "kind": kind,
                    "repository": repository,
                    "workflow": workflow,
                    "environment": environment,
                },
                "attestations": [
                    {
                        "version": attestation_version,
                        "envelope": {"statement": encoded},
                    }
                ],
            }
        ],
    }


def _step_run(name: str) -> str:
    lines = RELEASE_WORKFLOW.read_text(encoding="utf-8").splitlines()
    start = lines.index(f"      - name: {name}")
    run = next(index for index in range(start + 1, len(lines)) if lines[index] == "        run: |")
    body: list[str] = []
    for line in lines[run + 1 :]:
        if line and not line.startswith("          "):
            break
        body.append(line[10:] if line.startswith("          ") else "")
    assert body
    return "\n".join(body)


def _shell_function(script: str, name: str) -> str:
    lines = script.splitlines()
    start = lines.index(f"{name}() {{")
    end = next(index for index in range(start + 1, len(lines)) if lines[index] == "}")
    return "\n".join(lines[start : end + 1])


def _run_dispatch_release_ref(
    release: dict[str, object],
    tag_sha: str,
) -> subprocess.CompletedProcess[str]:
    verify = _step_run("Verify GitHub release state")
    helper = _shell_function(verify, "select_dispatch_release_ref")
    script = f"""{helper}
select_dispatch_release_ref "$RELEASE_JSON" "$TAG_SHA"
"""
    env = {
        **os.environ,
        "DISPATCH_RELEASE_JQ": _folded_env_value("DISPATCH_RELEASE_JQ"),
        "RELEASE_JSON": json.dumps(release),
        "RELEASE_SHA": RELEASE_SHA,
        "RELEASE_TAG": RELEASE_TAG,
        "TAG_SHA": tag_sha,
    }
    return subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_immutable_policy(
    tmp_path: Path,
    settings: dict[str, object],
    *,
    token: str = "settings-token",
    gh_exit: int = 0,
) -> subprocess.CompletedProcess[str]:
    finalize = _step_run("Bind tag and publish exact verified draft release")
    helper = _shell_function(finalize, "verify_immutable_release_policy")
    script = f"""{helper}
gh() {{
  printf '%s' "$GH_TOKEN" > seen-token
  printf '%s' "$*" > seen-args
  printf '%s' "$SETTINGS_JSON"
  return "$GH_EXIT"
}}
verify_immutable_release_policy
"""
    env = {
        **os.environ,
        "GH_EXIT": str(gh_exit),
        "GITHUB_REPOSITORY": "buettgen-app/coverart-cli",
        "IMMUTABLE_RELEASES_JQ": _folded_env_value("IMMUTABLE_RELEASES_JQ"),
        "RELEASE_SETTINGS_TOKEN": token,
        "SETTINGS_JSON": json.dumps(settings),
    }
    return subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _assert_finalize_order(script: str) -> None:
    publication = script.index('published="$(')
    before = script[:publication]
    tag_creation = before.rfind("\nensure_annotated_release_tag\n")
    main_read = before.rfind('current_main="$(')
    release_read = before.rfind(
        'release="$(gh api "repos/$GITHUB_REPOSITORY/releases/$RELEASE_ID")"'
    )
    identity_check = before.rfind('verify_workflow_identity "$current_main"')
    state_check = before.rfind('validate_draft_release "$release"')
    ruleset_check = before.rfind("verify_release_tag_ruleset")
    tag_check = before.rfind("verify_annotated_release_tag")
    immutable_check = before.rfind("verify_immutable_release_policy")
    assert -1 not in {
        tag_creation,
        main_read,
        release_read,
        identity_check,
        state_check,
        ruleset_check,
        tag_check,
        immutable_check,
    }
    assert (
        tag_creation
        < main_read
        < release_read
        < identity_check
        < state_check
        < ruleset_check
        < tag_check
        < immutable_check
        < publication
    )
    guarded_tail = script[immutable_check + len("verify_immutable_release_policy") : publication]
    assert "--method POST" not in guarded_tail
    assert "--method PATCH" not in guarded_tail
    assert "--method DELETE" not in guarded_tail
    assert script.find("verify_annotated_release_tag", publication) > publication


def _run_ruleset_state(
    ruleset: dict[str, object],
) -> subprocess.CompletedProcess[str]:
    jq = shutil.which("jq")
    assert jq is not None, "jq is required to verify the release workflow"
    return subprocess.run(
        [jq, "-e", _folded_env_value("TAG_RULESET_JQ")],
        input=json.dumps(ruleset),
        check=False,
        capture_output=True,
        text=True,
    )


def _run_annotated_tag_guard(
    refs: list[Any],
    tag_object: dict[str, object],
) -> subprocess.CompletedProcess[str]:
    finalize = _step_run("Bind tag and publish exact verified draft release")
    helper = _shell_function(finalize, "verify_annotated_release_tag")
    script = f"""set -euo pipefail
{helper}
gh() {{
  case "$*" in
    *matching-refs*) printf '%s\\n' "$TAG_REFS" ;;
    *git/tags/*) printf '%s\\n' "$TAG_OBJECT" ;;
    *) return 64 ;;
  esac
}}
verify_annotated_release_tag
"""
    env = {
        **os.environ,
        "TAG_REFS": json.dumps(refs),
        "TAG_OBJECT": json.dumps(tag_object),
        "EXACT_TAG_JQ": _folded_env_value("EXACT_TAG_JQ"),
        "EXPECTED_RELEASE_SHA": RELEASE_SHA,
        "GITHUB_REPOSITORY": "buettgen-app/coverart-cli",
        "RELEASE_TAG": RELEASE_TAG,
    }
    return subprocess.run(
        ["bash", "-c", script],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_validate_tag_resolver(
    refs: list[Any],
    tag_object: dict[str, object],
) -> subprocess.CompletedProcess[str]:
    verify = _step_run("Verify GitHub release state")
    helper = _shell_function(verify, "resolve_annotated_release_tag")
    script = f"""set -euo pipefail
{helper}
gh() {{
  case "$*" in
    *matching-refs*) printf '%s\n' "$TAG_REFS" ;;
    *git/tags/*) printf '%s\n' "$TAG_OBJECT" ;;
    *) return 64 ;;
  esac
}}
resolve_annotated_release_tag
"""
    env = {
        **os.environ,
        "TAG_REFS": json.dumps(refs),
        "TAG_OBJECT": json.dumps(tag_object),
        "EXACT_TAG_JQ": _folded_env_value("EXACT_TAG_JQ"),
        "GITHUB_REPOSITORY": "buettgen-app/coverart-cli",
        "RELEASE_TAG": RELEASE_TAG,
    }
    return subprocess.run(
        ["bash", "-c", script],
        env=env,
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


def test_dispatch_accepts_exact_draft_and_exact_immutable_rerun() -> None:
    base: dict[str, object] = {
        "prerelease": False,
        "tag_name": RELEASE_TAG,
        "target_commitish": RELEASE_SHA,
    }

    for draft, immutable in ((True, False), (False, True)):
        release = {**base, "draft": draft, "immutable": immutable}
        result = _run_dispatch_state(release)
        assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "mutation",
    ["prerelease", "tag", "sha", "mutable-published", "immutable-draft"],
)
def test_dispatch_rejects_wrong_identity_or_unsafe_state(mutation: str) -> None:
    release: dict[str, object] = {
        "prerelease": False,
        "tag_name": RELEASE_TAG,
        "target_commitish": RELEASE_SHA,
        "draft": True,
        "immutable": False,
    }
    if mutation == "prerelease":
        release["prerelease"] = True
    elif mutation == "tag":
        release["tag_name"] = "v0.6.2"
    elif mutation == "sha":
        release["target_commitish"] = BOUND_SHA
    elif mutation == "mutable-published":
        release["draft"] = False
    else:
        release["immutable"] = True

    assert _run_dispatch_state(release).returncode != 0


@pytest.mark.parametrize(
    ("draft", "immutable", "tag_sha", "accepted"),
    [
        (True, False, "", True),
        (True, False, RELEASE_SHA, True),
        (True, False, BOUND_SHA, False),
        (False, True, RELEASE_SHA, True),
        (False, True, "", False),
        (False, True, BOUND_SHA, False),
    ],
)
def test_exact_dispatch_branch_selects_only_safe_release_ref(
    draft: bool,
    immutable: bool,
    tag_sha: str,
    accepted: bool,
) -> None:
    release: dict[str, object] = {
        "prerelease": False,
        "tag_name": RELEASE_TAG,
        "target_commitish": RELEASE_SHA,
        "draft": draft,
        "immutable": immutable,
    }

    result = _run_dispatch_release_ref(release, tag_sha)

    assert (result.returncode == 0) is accepted
    if accepted:
        assert result.stdout == f"{RELEASE_SHA}\n"


def test_validate_tag_resolver_rejects_lightweight_and_mutated_tags() -> None:
    tag_object_sha = "c" * 40
    exact = {
        "ref": f"refs/tags/{RELEASE_TAG}",
        "object": {"type": "tag", "sha": tag_object_sha},
    }
    tag_object: dict[str, object] = {
        "sha": tag_object_sha,
        "tag": RELEASE_TAG,
        "message": f"Release {RELEASE_TAG}",
        "object": {"type": "commit", "sha": RELEASE_SHA},
    }

    missing = _run_validate_tag_resolver([], tag_object)
    assert missing.returncode == 0, missing.stderr
    assert missing.stdout == ""

    accepted = _run_validate_tag_resolver([exact], tag_object)
    assert accepted.returncode == 0, accepted.stderr
    assert accepted.stdout == f"{RELEASE_SHA}\n"

    lightweight = {
        "ref": f"refs/tags/{RELEASE_TAG}",
        "object": {"type": "commit", "sha": RELEASE_SHA},
    }
    assert _run_validate_tag_resolver([lightweight], tag_object).returncode != 0

    mutated = copy.deepcopy(tag_object)
    mutated["message"] = "unexpected"
    assert _run_validate_tag_resolver([exact], mutated).returncode != 0


@pytest.mark.parametrize(
    "settings",
    [
        {"enabled": False, "enforced_by_owner": False},
        {"enforced_by_owner": False},
        {"enabled": True},
        {"enabled": "true", "enforced_by_owner": False},
        {"enabled": True, "enforced_by_owner": "false"},
    ],
)
def test_disabled_or_schema_drifted_immutable_release_setting_is_rejected(
    settings: dict[str, object],
) -> None:
    assert _run_immutable_release_state(settings).returncode != 0


def test_enabled_immutable_release_setting_is_accepted() -> None:
    for enforced_by_owner in (False, True):
        settings: dict[str, object] = {
            "enabled": True,
            "enforced_by_owner": enforced_by_owner,
        }
        result = _run_immutable_release_state(settings)
        assert result.returncode == 0, result.stderr


def test_immutable_policy_uses_scoped_token_and_exact_endpoint(
    tmp_path: Path,
) -> None:
    result = _run_immutable_policy(
        tmp_path,
        {"enabled": True, "enforced_by_owner": False},
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "seen-token").read_text() == "settings-token"
    args = (tmp_path / "seen-args").read_text()
    assert "--method GET" in args
    assert "X-GitHub-Api-Version: 2026-03-10" in args
    assert "repos/buettgen-app/coverart-cli/immutable-releases" in args


@pytest.mark.parametrize(
    ("settings", "token", "gh_exit"),
    [
        ({"enabled": True, "enforced_by_owner": False}, "", 0),
        ({"enabled": False, "enforced_by_owner": False}, "settings-token", 0),
        ({"enabled": True}, "settings-token", 0),
        ({"enabled": True, "enforced_by_owner": False}, "settings-token", 22),
    ],
)
def test_immutable_policy_fails_closed(
    tmp_path: Path,
    settings: dict[str, object],
    token: str,
    gh_exit: int,
) -> None:
    result = _run_immutable_policy(
        tmp_path,
        settings,
        token=token,
        gh_exit=gh_exit,
    )

    assert result.returncode != 0
    if not token:
        assert not (tmp_path / "seen-token").exists()


def test_draft_is_revalidated_and_published_at_the_bound_commit() -> None:
    """Finalize must not trust mutable draft state captured before build and tests."""
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert 'release_ref="$GITHUB_SHA"' in workflow
    assert 'release_ref="$tag_sha"' in workflow
    assert "target=$target_commitish" in workflow
    assert 'git merge-base --is-ancestor "$VALIDATED_DRAFT_TARGET" HEAD' in workflow
    assert "Release recovery includes changes outside the explicit release repair." in workflow
    assert "name: Resolve live release phase" in workflow
    assert '"$DISPATCH_RELEASE_JQ" <<<"$release"' in workflow
    assert workflow.count("select_dispatch_release_ref") == 2
    assert workflow.count("resolve_annotated_release_tag") == 2
    assert "Published dispatch recovery requires the exact annotated release tag." in workflow
    assert "RELEASE_SETTINGS_TOKEN: ${{ secrets.RELEASE_SETTINGS_TOKEN }}" in workflow
    assert '"repos/$GITHUB_REPOSITORY/immutable-releases"' in workflow
    assert '"X-GitHub-Api-Version: 2026-03-10"' in workflow
    assert workflow.count("verify_immutable_release_policy") == 3
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
    assert 'gh api --method POST "repos/$GITHUB_REPOSITORY/git/tags"' in workflow
    assert 'gh api --method POST "repos/$GITHUB_REPOSITORY/git/refs"' in workflow
    assert "ensure_annotated_release_tag" in workflow
    assert "verify_release_tag_ruleset" in workflow
    assert "verify_annotated_release_tag" in workflow
    assert '([.rules[].type] | index("update")) != null' in workflow
    assert 'validate_draft_release "$release"' in workflow
    assert workflow.count(".immutable == true") >= 4
    assert workflow.count('gh api "repos/$GITHUB_REPOSITORY/git/ref/heads/main"') == 3
    assert workflow.count("git/matching-refs/tags/$RELEASE_TAG") >= 4
    assert '"$EXACT_TAG_JQ" <<<"$refs"' in workflow
    assert "Plan idempotent PyPI upload" in workflow
    assert "packages-dir: pypi-dist/" in workflow
    assert "skip-existing" not in workflow
    assert '"$PYPI_EXISTING_JQ" "$response"' in workflow
    assert '"$PYPI_COMPLETE_JQ" "$response"' in workflow
    assert '"$PYPI_PROVENANCE_JQ" "$provenance"' in workflow
    assert "integrity/coverart-cli/$version/$encoded_name/provenance" in workflow
    assert "Verify PyPI provenance cryptographically" in workflow
    assert "--require-hashes -r requirements-attestation.txt" in workflow
    assert "pypi-attestations verify pypi" in workflow


def test_published_release_reuses_strict_annotated_tag_guard() -> None:
    finalize = _step_run("Bind tag and publish exact verified draft release")
    published = _step_run("Verify published release")

    assert _shell_function(finalize, "verify_annotated_release_tag") == _shell_function(
        published, "verify_annotated_release_tag"
    )
    assert published.count("\nverify_annotated_release_tag\n") == 1


@pytest.mark.parametrize(
    ("sequence", "expected", "calls"),
    [
        ("200", "200\n", "1"),
        ("ERR 200", "000\n200\n", "2"),
    ],
)
def test_pypi_http_status_preserves_success_and_transport_failure(
    tmp_path: Path,
    sequence: str,
    expected: str,
    calls: str,
) -> None:
    verify = _step_run("Verify PyPI files and attestations")
    helper = _shell_function(verify, "pypi_http_status")
    script = f"""set -euo pipefail
{helper}
printf 0 > calls
sequence=({sequence})
curl() {{
  local n token
  n="$(cat calls)"
  n=$((n + 1))
  printf '%s' "$n" > calls
  token="${{sequence[$((n - 1))]}}"
  if [ "$token" = ERR ]; then
    return 7
  fi
  printf '%s' "$token"
}}
first="$(pypi_http_status response https://example.invalid)"
printf '%s\\n' "$first"
if [ "$first" = 000 ]; then
  second="$(pypi_http_status response https://example.invalid)"
  printf '%s\\n' "$second"
fi
"""
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == expected
    assert (tmp_path / "calls").read_text() == calls


def test_immutable_recovery_matches_fresh_reproducible_artifacts() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    build_marker = "      - name: Build wheel and source distribution reproducibly\n"
    build_start = workflow.index(build_marker)
    build_end = workflow.index("      - name:", build_start + len(build_marker))
    build_block = workflow[build_start:build_end]
    download = _step_run("Download immutable release assets for recovery")
    compare = _step_run("Match immutable release assets to a fresh deterministic build")

    assert "if:" not in build_block
    assert 'SOURCE_DATE_EPOCH: "1580601600"' in build_block
    assert "python -m build --no-isolation" in build_block
    assert "--dir released-dist" in download
    assert "--dir dist" not in download
    assert 'fresh = manifest("dist")' in compare
    assert 'released = manifest("released-dist")' in compare
    assert "hashlib.sha256" in compare
    assert "len(fresh) != 2 or fresh != released" in compare


def test_ci_proves_wheel_and_sdist_reproducibility() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "reproducible-artifacts:" in workflow
    assert "name: Reproducible wheel and sdist" in workflow
    assert 'SOURCE_DATE_EPOCH: "1580601600"' in workflow
    assert "python -m build --no-isolation --outdir /tmp/repro-one" in workflow
    assert "python -m build --no-isolation --outdir /tmp/repro-two" in workflow
    assert 'first = manifest("/tmp/repro-one")' in workflow
    assert 'second = manifest("/tmp/repro-two")' in workflow
    assert "hashlib.sha256" in workflow
    assert "len(first) != 2 or first != second" in workflow


def test_release_network_calls_and_jobs_have_hard_timeouts() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    helper = _shell_function(
        _step_run("Verify PyPI files and attestations"),
        "pypi_http_status",
    )
    upload = _step_run("Revalidate and upload draft assets by release ID")

    assert "--connect-timeout 10 --max-time 15" in helper
    assert "--connect-timeout 10 --max-time 120" in upload
    assert workflow.count("timeout-minutes: 30") == 6
    assert 3 * 12 * (15 + 5) < 30 * 60


@pytest.mark.parametrize(
    ("sequence", "expected", "calls"),
    [
        ("200", "success\n", "1"),
        ("000 503 200", "success\n", "3"),
        ("503 503 503 503 503 503 503 503 503 503 503 503", "failure\n", "12"),
    ],
)
def test_pypi_poll_retries_and_exhausts_exactly(
    tmp_path: Path,
    sequence: str,
    expected: str,
    calls: str,
) -> None:
    verify = _step_run("Verify PyPI files and attestations")
    poll = _shell_function(verify, "pypi_poll_json")
    script = f"""set -euo pipefail
{poll}
printf 0 > calls
sequence=({sequence})
pypi_http_status() {{
  local n
  n="$(cat calls)"
  n=$((n + 1))
  printf '%s' "$n" > calls
  printf '%s\n' "${{sequence[$((n - 1))]}}"
}}
predicate() {{
  return 0
}}
sleep() {{
  :
}}
if pypi_poll_json response predicate https://example.invalid; then
  printf 'success\n'
else
  printf 'failure\n'
fi
"""
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == expected
    assert (tmp_path / "calls").read_text() == calls


def test_every_pypi_lookup_uses_the_tested_status_helper() -> None:
    plan = _step_run("Plan idempotent PyPI upload")
    verify = _step_run("Verify PyPI files and attestations")
    cryptographic = _step_run("Verify exact PyPI artifacts and signatures")
    tested_helper = _shell_function(verify, "pypi_http_status")

    assert _shell_function(plan, "pypi_http_status") == tested_helper
    assert _shell_function(cryptographic, "pypi_http_status") == tested_helper
    assert _shell_function(verify, "pypi_poll_json") == _shell_function(
        cryptographic, "pypi_poll_json"
    )
    assert plan.count('pypi_http_status "$') == 1
    assert verify.count('pypi_http_status "$') == 1
    assert cryptographic.count('pypi_http_status "$') == 1
    assert verify.count("pypi_poll_json") == 3
    assert cryptographic.count("pypi_poll_json") == 3


def test_finalize_revalidates_live_state_and_protected_tag_before_publish() -> None:
    script = _step_run("Bind tag and publish exact verified draft release")
    _assert_finalize_order(script)
    publication = script.index('published="$(')

    for needle in (
        'validate_draft_release "$release"',
        "verify_release_tag_ruleset",
        "verify_annotated_release_tag",
    ):
        index = script.rfind(needle, 0, publication)
        assert index >= 0
        mutated = script[:index] + script[index + len(needle) :]
        with pytest.raises(AssertionError):
            _assert_finalize_order(mutated)


def _ruleset_payload() -> dict[str, Any]:
    return {
        "name": "Baseline: immutable release tags",
        "target": "tag",
        "source_type": "Organization",
        "source": "buettgen-app",
        "enforcement": "active",
        "conditions": {
            "ref_name": {
                "exclude": [],
                "include": ["refs/tags/v*"],
            }
        },
        "rules": [
            {"type": "update"},
            {"type": "deletion"},
            {"type": "non_fast_forward"},
        ],
        "bypass_actors": [],
        "current_user_can_bypass": "never",
    }


def test_exact_no_bypass_release_tag_ruleset_is_accepted() -> None:
    result = _run_ruleset_state(_ruleset_payload())

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-update",
        "missing-deletion",
        "missing-non-fast-forward",
        "inactive",
        "excluded",
        "missing-exclude",
        "null-exclude",
        "wrong-exclude-type",
        "wrong-include",
        "missing-include",
        "null-include",
        "wrong-include-type",
        "missing-rules",
        "null-rules",
        "wrong-rules-type",
        "bypass-actor",
        "missing-bypass-actors",
        "null-bypass-actors",
        "wrong-bypass-type",
        "can-bypass",
        "wrong-source",
    ],
)
def test_weakened_release_tag_rulesets_are_rejected(mutation: str) -> None:
    ruleset = _ruleset_payload()
    if mutation in {
        "missing-update",
        "missing-deletion",
        "missing-non-fast-forward",
    }:
        missing = mutation.removeprefix("missing-").replace("-", "_")
        ruleset["rules"] = [rule for rule in ruleset["rules"] if rule["type"] != missing]
    elif mutation == "inactive":
        ruleset["enforcement"] = "evaluate"
    elif mutation == "excluded":
        ruleset["conditions"]["ref_name"]["exclude"] = ["refs/tags/v0.6.1"]
    elif mutation == "missing-exclude":
        ruleset["conditions"]["ref_name"].pop("exclude")
    elif mutation == "null-exclude":
        ruleset["conditions"]["ref_name"]["exclude"] = None
    elif mutation == "wrong-exclude-type":
        ruleset["conditions"]["ref_name"]["exclude"] = {}
    elif mutation == "wrong-include":
        ruleset["conditions"]["ref_name"]["include"] = ["refs/tags/release-*"]
    elif mutation == "missing-include":
        ruleset["conditions"]["ref_name"].pop("include")
    elif mutation == "null-include":
        ruleset["conditions"]["ref_name"]["include"] = None
    elif mutation == "wrong-include-type":
        ruleset["conditions"]["ref_name"]["include"] = {}
    elif mutation == "missing-rules":
        ruleset.pop("rules")
    elif mutation == "null-rules":
        ruleset["rules"] = None
    elif mutation == "wrong-rules-type":
        ruleset["rules"] = {}
    elif mutation == "bypass-actor":
        ruleset["bypass_actors"] = [{"actor_id": 1}]
    elif mutation == "missing-bypass-actors":
        ruleset.pop("bypass_actors")
    elif mutation == "null-bypass-actors":
        ruleset["bypass_actors"] = None
    elif mutation == "wrong-bypass-type":
        ruleset["bypass_actors"] = {}
    elif mutation == "can-bypass":
        ruleset["current_user_can_bypass"] = "always"
    else:
        ruleset["source"] = "other-org"

    result = _run_ruleset_state(ruleset)

    assert result.returncode != 0


def test_annotated_tag_guard_accepts_only_exact_bound_tag() -> None:
    tag_object_sha = "c" * 40
    prefix = {
        "ref": f"refs/tags/{RELEASE_TAG}-rc1",
        "object": {"type": "tag", "sha": "d" * 40},
    }
    exact = {
        "ref": f"refs/tags/{RELEASE_TAG}",
        "object": {"type": "tag", "sha": tag_object_sha},
    }
    tag_object: dict[str, object] = {
        "sha": tag_object_sha,
        "tag": RELEASE_TAG,
        "message": f"Release {RELEASE_TAG}",
        "object": {"type": "commit", "sha": RELEASE_SHA},
    }

    result = _run_annotated_tag_guard([prefix, exact], tag_object)
    assert result.returncode == 0, result.stderr

    for refs in (
        [],
        [prefix],
        [exact, exact],
        [
            {
                "ref": f"refs/tags/{RELEASE_TAG}",
                "object": {"type": "commit", "sha": RELEASE_SHA},
            }
        ],
    ):
        assert _run_annotated_tag_guard(refs, tag_object).returncode != 0


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("sha", "d" * 40),
        ("tag", "v0.6.2"),
        ("message", "unexpected"),
        ("object.type", "tag"),
        ("object.sha", "e" * 40),
    ],
)
def test_mutated_annotated_tag_object_is_rejected(
    path: str,
    value: str,
) -> None:
    tag_object_sha = "c" * 40
    refs = [
        {
            "ref": f"refs/tags/{RELEASE_TAG}",
            "object": {"type": "tag", "sha": tag_object_sha},
        }
    ]
    tag_object: dict[str, Any] = {
        "sha": tag_object_sha,
        "tag": RELEASE_TAG,
        "message": f"Release {RELEASE_TAG}",
        "object": {"type": "commit", "sha": RELEASE_SHA},
    }
    if "." in path:
        parent, child = path.split(".", maxsplit=1)
        tag_object[parent][child] = value
    else:
        tag_object[path] = value

    assert _run_annotated_tag_guard(refs, tag_object).returncode != 0


def test_exact_pypi_provenance_is_accepted() -> None:
    result = _run_provenance_state(_provenance_payload())

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "kwargs",
    [
        {"repository": "attacker/repo"},
        {"workflow": "other.yml"},
        {"environment": "other"},
        {"kind": "Other"},
        {"api_version": 2},
        {"attestation_version": 2},
        {"name": "other.whl"},
        {"digest": "a" * 64},
        {"statement_type": "https://in-toto.io/Statement/v0.1"},
        {"predicate_type": "https://example.invalid/predicate"},
        {"predicate": {"unexpected": True}},
    ],
)
def test_wrong_publisher_or_statement_semantics_are_rejected(
    kwargs: dict[str, Any],
) -> None:
    result = _run_provenance_state(_provenance_payload(**kwargs))

    assert result.returncode != 0


def test_provenance_cannot_mix_publisher_and_attackers_statement() -> None:
    attacker = _provenance_payload(repository="attacker/repo")
    trusted_wrong = _provenance_payload(digest="a" * 64)
    payload = {
        "version": 1,
        "attestation_bundles": [
            attacker["attestation_bundles"][0],
            trusted_wrong["attestation_bundles"][0],
        ],
    }

    assert _run_provenance_state(payload).returncode != 0


@pytest.mark.parametrize("mutation", ["missing", "malformed", "duplicate"])
def test_missing_malformed_or_ambiguous_provenance_is_rejected(
    mutation: str,
) -> None:
    payload = _provenance_payload()
    if mutation == "missing":
        payload["attestation_bundles"] = []
    elif mutation == "malformed":
        payload["attestation_bundles"][0]["attestations"][0]["envelope"]["statement"] = "%%%"
    else:
        payload["attestation_bundles"].append(copy.deepcopy(payload["attestation_bundles"][0]))

    assert _run_provenance_state(payload).returncode != 0


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
    partial: dict[str, object] = {
        "info": {"version": "0.6.1", "yanked": False},
        "urls": [
            {
                "filename": assets[0]["name"],
                "digests": {"sha256": "aaa"},
                "yanked": False,
            },
        ],
    }
    complete: dict[str, object] = {
        "info": {"version": "0.6.1", "yanked": False},
        "urls": [
            {
                "filename": asset["name"],
                "digests": {"sha256": asset["digest"]},
                "yanked": False,
            }
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
        [
            {
                "filename": "coverart_cli-0.6.1.tar.gz",
                "digests": {"sha256": "bad"},
                "yanked": False,
            }
        ],
        [
            {
                "filename": "unexpected.zip",
                "digests": {"sha256": "ccc"},
                "yanked": False,
            }
        ],
        [
            {
                "filename": "coverart_cli-0.6.1.tar.gz",
                "digests": {"sha256": "bbb"},
                "yanked": False,
            },
            {
                "filename": "coverart_cli-0.6.1.tar.gz",
                "digests": {"sha256": "bbb"},
                "yanked": False,
            },
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
    release: dict[str, object] = {
        "info": {"version": "0.6.1", "yanked": False},
        "urls": urls,
    }

    assert _run_pypi_state(release, assets, complete=False).returncode != 0


@pytest.mark.parametrize(
    "mutation",
    ["release", "file", "missing_release", "missing_file"],
)
def test_yanked_or_schema_drifted_pypi_state_is_rejected(
    mutation: str,
) -> None:
    assets = [
        {"name": "coverart_cli-0.6.1-py3-none-any.whl", "digest": "aaa"},
        {"name": "coverart_cli-0.6.1.tar.gz", "digest": "bbb"},
    ]
    release: dict[str, Any] = {
        "info": {"version": "0.6.1", "yanked": False},
        "urls": [
            {
                "filename": asset["name"],
                "digests": {"sha256": asset["digest"]},
                "yanked": False,
            }
            for asset in assets
        ],
    }
    if mutation == "release":
        release["info"]["yanked"] = True
    elif mutation == "file":
        release["urls"][0]["yanked"] = True
    elif mutation == "missing_release":
        release["info"].pop("yanked")
    else:
        release["urls"][0].pop("yanked")

    assert _run_pypi_state(release, assets, complete=False).returncode != 0
    assert _run_pypi_state(release, assets, complete=True).returncode != 0


def test_wrong_pypi_version_is_rejected() -> None:
    assets = [{"name": "coverart_cli-0.6.1.tar.gz", "digest": "bbb"}]
    release: dict[str, object] = {
        "info": {"version": "0.6.2", "yanked": False},
        "urls": [],
    }

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
