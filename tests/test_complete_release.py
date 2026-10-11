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
        "CHANGELOG.md": f"# Changelog\n\n## [{version}]\n\nRelease notes\n",
    }


@pytest.fixture
def boundaries():
    before, after = metadata("0.6.2"), metadata("0.7.0")
    after["CHANGELOG.md"] += before["CHANGELOG.md"].split("\n\n", 1)[1]
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
    "change",
    [
        "unstable",
        "older",
        "manifest",
        "dependency",
        "init",
        "changelog",
        "base",
        "zeros",
        "history",
        "preamble",
        "extra-section",
        "no-history",
    ],
)
def test_unexpected_metadata_is_refused(boundaries, change):
    before, after, _, _ = boundaries
    if change in {"unstable", "older", "manifest", "zeros"}:
        after[".release-please-manifest.json"] = json.dumps(
            {
                ".": {
                    "unstable": "0.7.0rc1",
                    "older": "0.6.2",
                    "manifest": "0.7.0",
                    "zeros": "00.7.0",
                }[change],
                **({"extra": "1.0.0"} if change == "manifest" else {}),
            }
        )
    elif change == "no-history":
        before["CHANGELOG.md"] = "# Changelog\n"
    elif change == "history":
        after["CHANGELOG.md"] = after["CHANGELOG.md"].replace("## [0.6.2]", "## [0.6.1]")
    elif change == "preamble":
        after["CHANGELOG.md"] = after["CHANGELOG.md"].replace("# Changelog", "# Replaced")
    elif change == "extra-section":
        after["CHANGELOG.md"] = after["CHANGELOG.md"].replace(
            "## [0.6.2]", "## [0.6.3]\n\n## [0.6.2]"
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
        patch.object(release, "pr_runs", return_value={}),
        patch.object(release, "api", side_effect=responses),
        patch.object(release.time, "sleep") as sleep,
    ):
        release.wait_for_checks(80, release.BRANCH, HEAD, "2026-10-11T16:00:00Z")
        assert sleep.call_count == 4


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "skipped", "neutral", "timed_out"])
def test_failed_or_skipped_workflow_cannot_merge(conclusion):
    with (
        patch.object(release, "pr_runs", return_value={}),
        patch.object(
            release, "api", return_value={"workflow_runs": [run_record(conclusion=conclusion)]}
        ),
        pytest.raises(ValueError, match="Release check failed"),
    ):
        release.wait_for_checks(80, release.BRANCH, HEAD, "2026-10-11T16:00:00Z")


def test_wait_has_a_finite_deadline():
    with patch.object(release.time, "monotonic", side_effect=[0, 2]), pytest.raises(TimeoutError):
        release.wait_for_checks(80, release.BRANCH, HEAD, "", timeout=1)


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
            return {"merged": case != "refused", "sha": "c" * 40}
        return pr

    with (
        patch.object(release, "api", side_effect=fake_api),
        patch.object(release, "pr_runs", return_value={}),
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
            assert publication[0][1] == {
                "ref": "main",
                "inputs": {"publish_only": True, "release_sha": "c" * 40},
            }
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


def test_pr_runs_filter_workflow_commit_and_pr_identity():
    records = [
        {**run_record(), "path": ".github/workflows/ci.yml", "pull_requests": [{"number": 80}]},
        {**run_record(id=2), "path": ".github/workflows/ci.yml", "pull_requests": [{"number": 80}]},
        {**run_record(id=3), "path": ".github/workflows/ci.yml", "pull_requests": [{"number": 81}]},
        {
            **run_record(head_sha=BASE),
            "path": ".github/workflows/ci.yml",
            "pull_requests": [{"number": 80}],
        },
        {**run_record(), "path": ".github/workflows/other.yml", "pull_requests": [{"number": 80}]},
    ]
    with patch.object(release, "api", return_value={"workflow_runs": records}):
        assert release.pr_runs(80, HEAD) == {"ci.yml": records[1]}


def test_approval_gated_pr_context_is_used_instead_of_dispatched_copy():
    approved = run_record(conclusion="action_required")
    with (
        patch.object(release, "WORKFLOWS", ("ci.yml",)),
        patch.object(
            release,
            "pr_runs",
            side_effect=[{"ci.yml": approved}, {"ci.yml": approved}, {"ci.yml": run_record()}],
        ),
        patch.object(release, "api") as api,
        patch.object(release.time, "sleep"),
    ):
        release.wait_for_checks(80, release.BRANCH, HEAD, "2026-10-11T18:00:00Z")
        api.assert_called_once_with("actions/runs/1/approve", {}, method="POST")


def test_existing_pr_runs_do_not_dispatch_duplicate_workflows():
    def fake_api(path, body=None, *, method="GET"):
        if path.startswith("pulls?"):
            return [pull_request()]
        if path == "git/ref/heads/main":
            return {"object": {"sha": BASE}}
        if path.endswith("/merge"):
            return {"merged": True, "sha": "c" * 40}
        return pull_request()

    with (
        patch.object(release, "api", side_effect=fake_api) as api,
        patch.object(release, "validate", return_value=(BASE, HEAD)),
        patch.object(
            release, "pr_runs", return_value=dict.fromkeys(release.WORKFLOWS, run_record())
        ),
        patch.object(release, "wait_for_checks"),
    ):
        release.main()
        posts = [call for call in api.call_args_list if call.kwargs.get("method") == "POST"]
        assert len(posts) == 1
        assert posts[0].args[1]["inputs"]["release_sha"] == "c" * 40
