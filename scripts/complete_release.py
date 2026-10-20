# Copyright (c) 2026 WildDragonKing
# SPDX-License-Identifier: MIT

"""Complete a metadata-only Release Please PR using normal protected merges."""

from __future__ import annotations

import base64
import json
import re
import subprocess
import time
import tomllib
from datetime import UTC, datetime
from typing import Any

REPOSITORY = "buettgen-app/coverart-cli"
BRANCH = "release-please--branches--main--components--coverart-cli"
FILES = {
    "pyproject.toml",
    "src/coverart_cli/__init__.py",
    ".release-please-manifest.json",
    "CHANGELOG.md",
}
WORKFLOWS = ("ci.yml", "codeql.yml", "fuzz.yml", "supply-chain.yml", "pr-security-baseline.yml")


def api(path: str, body: dict | None = None, *, method: str = "GET") -> Any:
    command = ["gh", "api", f"repos/{REPOSITORY}/{path}", "--method", method]
    if body is not None:
        command += ["--input", "-"]
    result = subprocess.run(
        command,
        input=json.dumps(body) if body is not None else None,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return json.loads(result.stdout) if result.stdout.strip() else None


def content(path: str, ref: str) -> str:
    return base64.b64decode(api(f"contents/{path}?ref={ref}")["content"]).decode("utf-8")


def validate(pr: dict, main: str) -> tuple[str, str]:
    base, head = pr["base"]["sha"], pr["head"]["sha"]
    if (
        pr["state"] != "open"
        or pr["draft"]
        or pr["user"]["login"] != "github-actions[bot]"
        or pr["base"]["ref"] != "main"
        or base != main
        or pr["head"]["ref"] != BRANCH
        or pr["head"]["repo"]["full_name"] != REPOSITORY
        or "autorelease: pending" not in {label["name"] for label in pr["labels"]}
        or not all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in (base, head))
    ):
        raise ValueError("Not a current, same-repository Release Please PR")
    compare = api(f"compare/{base}...{head}")
    changed = api(f"pulls/{pr['number']}/files?per_page=100")
    if (
        compare["behind_by"] != 0
        or compare["status"] != "ahead"
        or pr["changed_files"] != len(changed)
        or len(changed) != len(FILES)
        or {file["filename"] for file in changed} != FILES
        or any(file["status"] != "modified" for file in changed)
    ):
        raise ValueError("Release PR must change only the four existing metadata files")
    before = {path: content(path, base) for path in FILES}
    after = {path: content(path, head) for path in FILES}
    old = json.loads(before[".release-please-manifest.json"])
    new = json.loads(after[".release-please-manifest.json"])
    version = new["."]
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version):
        raise ValueError("Release version must be stable SemVer")
    if tuple(map(int, version.split("."))) <= tuple(map(int, old["."].split("."))):
        raise ValueError("Release version must increase")
    previous_section = re.search(r"^## \[", before["CHANGELOG.md"], re.MULTILINE)
    if previous_section is None:
        raise ValueError("Existing changelog has no version history")
    prefix, history = (
        before["CHANGELOG.md"][: previous_section.start()],
        before["CHANGELOG.md"][previous_section.start() :],
    )
    changelog = after["CHANGELOG.md"]
    if not changelog.startswith(prefix) or not changelog.endswith(history):
        raise ValueError("Release must preserve the changelog preamble and history")
    section = changelog[len(prefix) : -len(history)]
    if (
        not section.startswith(f"## [{version}]")
        or len(re.findall(r"^## \[", section, re.MULTILINE)) != 1
    ):
        raise ValueError("Release must add exactly one new changelog version section")
    expected = {**old, ".": version}
    project_before, project_after = (
        tomllib.loads(value) for value in (before["pyproject.toml"], after["pyproject.toml"])
    )
    if project_before["project"]["version"] != old["."]:
        raise ValueError("Main manifest and project version disagree")
    project_before["project"]["version"] = version
    if (
        new != expected
        or project_before != project_after
        or after["src/coverart_cli/__init__.py"]
        != before["src/coverart_cli/__init__.py"].replace(
            f'__version__ = "{old["."]}"',
            f'__version__ = "{version}"',
        )
        or f'__version__ = "{version}"' not in after["src/coverart_cli/__init__.py"]
        or f"## [{version}]" not in after["CHANGELOG.md"]
        or pr["title"] != f"chore(main): release {version}"
    ):
        raise ValueError("Release metadata contains unexpected changes or inconsistent versions")
    return base, head


def pr_runs(number: int, head: str) -> dict[str, dict]:
    runs = api(f"actions/runs?event=pull_request&head_sha={head}&per_page=100")["workflow_runs"]
    selected: dict[str, dict] = {}
    for run in runs:
        workflow = run["path"].removeprefix(".github/workflows/")
        if (
            workflow in WORKFLOWS
            and run["head_sha"] == head
            and any(pr["number"] == number for pr in run["pull_requests"])
            and (workflow not in selected or run["id"] > selected[workflow]["id"])
        ):
            selected[workflow] = run
    return selected


def wait_for_checks(
    number: int, branch: str, head: str, started: str, *, timeout: int = 2100
) -> None:
    deadline = time.monotonic() + timeout
    approved: set[int] = set()
    while time.monotonic() < deadline:
        ready = True
        contextual = pr_runs(number, head)
        for workflow in WORKFLOWS:
            run = contextual.get(workflow)
            if run is None:
                runs = api(
                    f"actions/workflows/{workflow}/runs?event=workflow_dispatch&branch={branch}"
                    f"&head_sha={head}&per_page=100"
                )["workflow_runs"]
                matching = [
                    run for run in runs if run["head_sha"] == head and run["created_at"] >= started
                ]
                if not matching:
                    ready = False
                    continue
                run = max(matching, key=lambda item: item["id"])
            if run["conclusion"] == "action_required":
                # Only after validating this exact metadata-only PR. Normal PR
                # runs satisfy protection on the test-merge commit as well.
                if run["id"] not in approved:
                    api(f"actions/runs/{run['id']}/approve", {}, method="POST")
                    approved.add(run["id"])
                ready = False
            elif run["status"] != "completed":
                ready = False
            elif run["conclusion"] != "success":
                raise ValueError(f"Release check failed: {workflow} ({run['html_url']})")
        if ready:
            return
        time.sleep(20)
    raise TimeoutError("Release checks did not complete within 35 minutes")


def main() -> None:
    prs = api(f"pulls?state=open&base=main&head=buettgen-app:{BRANCH}&per_page=100")
    if not prs:
        print("No pending release PR; no publication needed.")
        return
    if len(prs) != 1:
        raise ValueError("Ambiguous release PRs")
    number = prs[0]["number"]
    main_sha = api("git/ref/heads/main")["object"]["sha"]
    base, head = validate(api(f"pulls/{number}"), main_sha)
    started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    contextual = pr_runs(number, head)
    for workflow in WORKFLOWS:
        if workflow in contextual:
            continue
        inputs = (
            {"base_sha": base, "head_sha": head}
            if workflow
            in (
                "supply-chain.yml",
                "pr-security-baseline.yml",
            )
            else {}
        )
        api(
            f"actions/workflows/{workflow}/dispatches",
            {"ref": BRANCH, "inputs": inputs},
            method="POST",
        )
    wait_for_checks(number, BRANCH, head, started)
    # Check both leases again: newer main changes or release edits require a new run.
    if validate(api(f"pulls/{number}"), api("git/ref/heads/main")["object"]["sha"]) != (base, head):
        raise ValueError("Release source changed while checks were running")
    result = api(f"pulls/{number}/merge", {"sha": head, "merge_method": "rebase"}, method="PUT")
    if result["merged"] is not True:
        raise ValueError("Protected release merge was refused")
    # GITHUB_TOKEN merges do not emit new workflow-triggering push events.
    # Explicit dispatch is exempt and retains the single verified publisher.
    api(
        "actions/workflows/prepare-release.yml/dispatches",
        {
            "ref": "main",
            "inputs": {"publish_only": True, "release_sha": result["sha"]},
        },
        method="POST",
    )
    print(f"Merged release PR #{number}; verified publication dispatched.")


if __name__ == "__main__":
    main()
