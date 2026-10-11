"""Exercise automatic release boundaries without dispatching or publishing."""

from __future__ import annotations

import json
from unittest.mock import Mock, patch

import pytest

from scripts import complete_release as release

BASE, HEAD = "a" * 40, "b" * 40


def pull_request() -> dict:
    return {
        "number": 80,
        "state": "open",
        "draft": False,
        "user": {"login": "github-actions[bot]"},
        "base": {"sha": BASE, "ref": "main"},
        "head": {"sha": HEAD, "ref": release.BRANCH, "repo": {"full_name": release.REPOSITORY}},
        "labels": [{"name": "autorelease: pending"}],
        "changed_files": 4,
        "title": "chore(main): release 0.7.0",
    }


def metadata(version: str) -> dict[str, str]:
    return {
        "pyproject.toml": f'[project]\nversion = "{version}"\ndependencies = []\n',
        ".release-please-manifest.json": json.dumps({".": version}),
        "src/coverart_cli/__init__.py": f'__version__ = "{version}"\n',
        "CHANGELOG.md": f"## [{version}]\n\nRelease notes\n",
    }


@pytest.fixture
def boundaries():
    before, after = metadata("0.6.2"), metadata("0.7.0")
    files = [{"filename": path, "status": "modified"} for path in release.FILES]
    compare = {"behind_by": 0, "status": "ahead"}
    with (
        patch.object(
            release,
            "api",
            side_effect=lambda path: compare if path.startswith("compare/") else files,
        ),
        patch.object(
            release,
            "content",
            side_effect=lambda path, ref: (before if ref == BASE else after)[path],
        ),
    ):
        yield before, after, files, compare


def test_metadata_only_release_is_accepted(boundaries):
    assert release.validate(pull_request(), BASE) == (BASE, HEAD)


@pytest.mark.parametrize(
    "field,value",
    [
        ("state", "closed"),
        ("draft", True),
        ("user", {"login": "other"}),
        ("labels", []),
        ("changed_files", 5),
        ("title", "release"),
        ("base", {"sha": BASE, "ref": "other"}),
        ("base", {"sha": "c" * 40, "ref": "main"}),
        (
            "head",
            {"sha": "invalid", "ref": release.BRANCH, "repo": {"full_name": release.REPOSITORY}},
        ),
        ("head", {"sha": HEAD, "ref": "other", "repo": {"full_name": release.REPOSITORY}}),
        ("head", {"sha": HEAD, "ref": release.BRANCH, "repo": {"full_name": "other/repo"}}),
    ],
)
def test_untrusted_or_stale_pr_is_refused(boundaries, field, value):
    pr = pull_request()
    pr[field] = value
    with pytest.raises(ValueError):
        release.validate(pr, BASE)


@pytest.mark.parametrize("change", ["behind", "diverged", "filename", "status", "missing"])
def test_unexpected_diff_is_refused(boundaries, change):
    _, _, files, compare = boundaries
    if change == "behind":
        compare["behind_by"] = 1
    elif change == "diverged":
        compare["status"] = "diverged"
    elif change == "filename":
        files[0]["filename"] = "src/coverart_cli/cli.py"
    elif change == "status":
        files[0]["status"] = "added"
    else:
        files.pop()
    with pytest.raises(ValueError):
        release.validate(pull_request(), BASE)


@pytest.mark.parametrize(
    "change", ["unstable", "older", "manifest", "dependency", "init", "changelog", "base"]
)
def test_unexpected_metadata_is_refused(boundaries, change):
    before, after, _, _ = boundaries
    if change in {"unstable", "older", "manifest"}:
        after[".release-please-manifest.json"] = json.dumps(
            {
                ".": {"unstable": "0.7.0rc1", "older": "0.6.2", "manifest": "0.7.0"}[change],
                **({"extra": "1.0.0"} if change == "manifest" else {}),
            }
        )
    elif change == "dependency":
        after["pyproject.toml"] = after["pyproject.toml"].replace("[]", '["malicious"]')
    elif change == "base":
        before["pyproject.toml"] = before["pyproject.toml"].replace("0.6.2", "0.5.0")
    else:
        after[{"init": "src/coverart_cli/__init__.py", "changelog": "CHANGELOG.md"}[change]] = (
            "unexpected"
        )
    with pytest.raises(ValueError):
        release.validate(pull_request(), BASE)


def run_record(status="completed", conclusion="success", **kwargs):
    return {
        "head_sha": HEAD,
        "created_at": "2026-10-11T17:00:00Z",
        "id": 1,
        "status": status,
        "conclusion": conclusion,
        "html_url": "https://github.com/example",
        **kwargs,
    }


def test_wait_uses_only_fresh_runs_for_the_tested_commit():
    responses = [
        {"workflow_runs": []},
        {"workflow_runs": [run_record(head_sha=BASE)]},
        {"workflow_runs": [run_record(created_at="2020-01-01T00:00:00Z")]},
        {"workflow_runs": [run_record(status="in_progress")]},
        {"workflow_runs": [run_record()]},
    ]
    with (
        patch.object(release, "WORKFLOWS", ("ci.yml",)),
        patch.object(release, "api", side_effect=responses),
        patch.object(release.time, "sleep") as sleep,
    ):
        release.wait_for_checks(release.BRANCH, HEAD, "2026-10-11T16:00:00Z")
        assert sleep.call_count == 4


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "skipped", "neutral", "timed_out"])
def test_failed_or_skipped_workflow_cannot_merge(conclusion):
    with (
        patch.object(
            release, "api", return_value={"workflow_runs": [run_record(conclusion=conclusion)]}
        ),
        pytest.raises(ValueError, match="Release check failed"),
    ):
        release.wait_for_checks(release.BRANCH, HEAD, "2026-10-11T16:00:00Z")


def test_wait_has_a_finite_deadline():
    with patch.object(release.time, "monotonic", side_effect=[0, 2]), pytest.raises(TimeoutError):
        release.wait_for_checks(release.BRANCH, HEAD, "", timeout=1)


@pytest.mark.parametrize("case", ["none", "ambiguous", "success", "changed", "refused"])
def test_main_dispatches_checks_before_protected_merge_and_publication(case):
    pr = pull_request()
    calls = []

    def fake_api(path, body=None, *, method="GET"):
        calls.append((path, body, method))
        if path.startswith("pulls?"):
            return [] if case == "none" else [pr, pr] if case == "ambiguous" else [pr]
        if path == "git/ref/heads/main":
            return {"object": {"sha": BASE}}
        if path.endswith("/merge"):
            return {"merged": case != "refused"}
        return pr

    with (
        patch.object(release, "api", side_effect=fake_api),
        patch.object(
            release,
            "validate",
            side_effect=[(BASE, HEAD), (BASE, BASE) if case == "changed" else (BASE, HEAD)],
        ),
        patch.object(release, "wait_for_checks") as wait,
    ):
        if case in {"ambiguous", "changed", "refused"}:
            with pytest.raises(ValueError):
                release.main()
        else:
            release.main()
        publication = [call for call in calls if "prepare-release.yml/dispatches" in call[0]]
        assert bool(publication) == (case == "success")
        if case == "success":
            assert len([call for call in calls if call[2] == "POST"]) == 6
            assert ("pulls/80/merge", {"sha": HEAD, "merge_method": "rebase"}, "PUT") in calls
            assert publication[0][1] == {"ref": "main", "inputs": {"publish_only": True}}
            wait.assert_called_once()


def test_api_requests_preserve_structured_payload_and_failures():
    with patch.object(release.subprocess, "run", return_value=Mock(stdout='{"ok": true}')) as run:
        assert release.api("example", {"value": "literal\ntext"}, method="POST") == {"ok": True}
        assert json.loads(run.call_args.kwargs["input"]) == {"value": "literal\ntext"}
        assert run.call_args.kwargs["check"] is True
    with patch.object(release.subprocess, "run", return_value=Mock(stdout="")):
        assert release.api("example") is None


def test_content_decodes_api_payload():
    with patch.object(release, "api", return_value={"content": "aGVsbG8="}):
        assert release.content("example", BASE) == "hello"
