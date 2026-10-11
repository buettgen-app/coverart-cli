"""Exercise draft gating through the actual prepare-workflow shell script."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

WORKFLOW = Path(__file__).parents[1] / ".github/workflows/prepare-release.yml"


def publication_script() -> str:
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    start = lines.index("        run: |") + 1
    body = []
    for line in lines[start:]:
        if line and not line.startswith("          "):
            break
        body.append(line[10:])
    return "\n".join(body)


def release_commit_contract() -> str:
    lines = WORKFLOW.read_text().splitlines()
    start = lines.index("  RELEASE_COMMIT_JQ: >-") + 1
    body = []
    for line in lines[start:]:
        if not line.startswith("    "):
            break
        body.append(line.strip())
    return " ".join(body)


class PrepareReleaseTests(unittest.TestCase):
    def run_guard(
        self,
        pages: Sequence[Sequence[object]],
        *,
        manifest: str = "0.6.2",
        api_failure: bool = False,
        valid_release_commit: bool = True,
    ) -> tuple[int, str]:
        mock = """gh() {
          case "$*" in
            *contents/*) printf '%s' "$TEST_MANIFEST" | base64 ;;
            *commits/*/pulls*) printf '%s' "$TEST_RELEASE_PRS" ;;
            *releases*)
              printf '%s' "$TEST_RELEASES"
              if [ "$TEST_API_FAILURE" = 1 ]; then return 42; fi ;;
            *) return 64 ;;
          esac
        }
        """
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            env = {
                **os.environ,
                "GITHUB_REPOSITORY": "buettgen-app/coverart-cli",
                "GITHUB_SHA": "a" * 40,
                "GITHUB_OUTPUT": str(output),
                "TEST_MANIFEST": json.dumps({".": manifest}),
                "TEST_RELEASES": "\n".join(json.dumps(page) for page in pages),
                "TEST_API_FAILURE": "1" if api_failure else "0",
                "TEST_RELEASE_PRS": json.dumps(
                    [
                        {
                            "merged_at": "2026-10-11T18:00:00Z",
                            "merge_commit_sha": "a" * 40 if valid_release_commit else "b" * 40,
                            "title": f"chore(main): release {manifest}",
                            "user": {"login": "github-actions[bot]"},
                            "base": {"ref": "main"},
                            "head": {
                                "ref": "release-please--branches--main--components--coverart-cli",
                                "repo": {"full_name": "buettgen-app/coverart-cli"},
                            },
                        }
                    ]
                ),
                "RELEASE_COMMIT_JQ": release_commit_contract(),
            }
            result = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", mock + publication_script()],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            return result.returncode, output.read_text() if output.exists() else ""

    def test_current_draft_blocks_next_pr_across_pages(self) -> None:
        self.assertEqual(
            self.run_guard(
                [
                    [{"tag_name": "v0.6.0", "draft": False}],
                    [{"tag_name": "v0.6.2", "draft": True, "target_commitish": "a" * 40}],
                ]
            ),
            (0, "pending=true\ntag=v0.6.2\nsha=" + "a" * 40 + "\n"),
        )

    def test_published_current_release_allows_next_pr(self) -> None:
        self.assertEqual(
            self.run_guard([[{"tag_name": "v0.6.2", "draft": False}]]),
            (0, "pending=false\ntag=v0.6.2\n"),
        )

    def test_old_draft_does_not_block_new_version(self) -> None:
        self.assertEqual(
            self.run_guard([[{"tag_name": "v0.6.1", "draft": True}]]),
            (0, "pending=false\ntag=v0.6.2\n"),
        )

    def test_new_release_can_be_created(self) -> None:
        self.assertEqual(self.run_guard([[]]), (0, "pending=false\ntag=v0.6.2\n"))

    def test_ambiguous_or_malformed_state_stops(self) -> None:
        for matches in (
            [{"tag_name": "v0.6.2", "draft": True, "target_commitish": "a" * 40}] * 2,
            [{"tag_name": "v0.6.2"}],
            [{"tag_name": "v0.6.2", "draft": "false"}],
        ):
            with self.subTest(matches=matches):
                code, output = self.run_guard([matches])
                self.assertNotEqual(code, 0)
                self.assertEqual(output, "")

    def test_failed_later_page_cannot_use_partial_response(self) -> None:
        code, output = self.run_guard([[{"tag_name": "v0.6.2", "draft": False}]], api_failure=True)
        self.assertNotEqual(code, 0)
        self.assertEqual(output, "")

    def test_invalid_manifest_stops(self) -> None:
        code, output = self.run_guard([[]], manifest="not-a-version")
        self.assertNotEqual(code, 0)
        self.assertEqual(output, "")

    def test_invalid_pending_draft_source_stops_without_partial_outputs(self) -> None:
        for sha in (None, "main", "invalid"):
            code, output = self.run_guard(
                [[{"tag_name": "v0.6.2", "draft": True, "target_commitish": sha}]]
            )
            self.assertNotEqual(code, 0)
            self.assertEqual(output, "")

    def test_rejected_draft_cannot_be_recovered_as_a_trusted_source(self) -> None:
        code, output = self.run_guard(
            [[{"tag_name": "v0.6.2", "draft": True, "target_commitish": "a" * 40}]],
            valid_release_commit=False,
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(output, "")

    def test_guard_only_suppresses_pr_preparation(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("steps.publication.outputs.pending == 'true'", workflow)
        self.assertNotIn("skip-github-release:", workflow)
        self.assertIn("steps.release.outputs.release_created == 'true'", workflow)

    def test_recovery_uses_existing_main_only_publisher(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        recovery = workflow.split("\n  recover-publication:", 1)[1]
        self.assertIn("if: needs.release-please.outputs.pending == 'true'", recovery)
        self.assertIn("actions: write", recovery)
        self.assertNotIn("contents: write", recovery)
        self.assertIn('{ref: "main", inputs: {tag: $tag, source_sha: $sha}}', recovery)
        self.assertIn("/actions/workflows/release.yml/dispatches", recovery)
        self.assertNotIn("/releases", recovery)

    def test_draft_lookup_has_push_access_without_persisted_credentials(self) -> None:
        workflow = (WORKFLOW.parent / "release.yml").read_text(encoding="utf-8")
        validate = workflow.split("\n  validate:", 1)[1].split("\n  test:", 1)[0]
        self.assertIn("contents: write", validate)
        self.assertIn("persist-credentials: false", validate)
        self.assertNotIn("--method POST", validate)
        self.assertNotIn("--method PATCH", validate)
        self.assertNotIn("--method DELETE", validate)


if __name__ == "__main__":
    unittest.main()
