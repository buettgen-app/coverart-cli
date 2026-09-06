"""Exercise draft gating through the actual prepare-workflow shell script."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
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


class PrepareReleaseTests(unittest.TestCase):
    def run_guard(
        self, pages: list[list[object]], *, manifest: str = "0.6.2", api_failure: bool = False
    ) -> tuple[int, str]:
        mock = """gh() {
          case "$*" in
            *contents/*) printf '%s' "$TEST_MANIFEST" | base64 ;;
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
                    [{"tag_name": "v0.6.2", "draft": True}],
                ]
            ),
            (0, "pending=true\n"),
        )

    def test_published_current_release_allows_next_pr(self) -> None:
        self.assertEqual(
            self.run_guard([[{"tag_name": "v0.6.2", "draft": False}]]),
            (0, "pending=false\n"),
        )

    def test_old_draft_does_not_block_new_version(self) -> None:
        self.assertEqual(
            self.run_guard([[{"tag_name": "v0.6.1", "draft": True}]]),
            (0, "pending=false\n"),
        )

    def test_new_release_can_be_created(self) -> None:
        self.assertEqual(self.run_guard([[]]), (0, "pending=false\n"))

    def test_ambiguous_or_malformed_state_stops(self) -> None:
        for matches in (
            [{"tag_name": "v0.6.2", "draft": True}] * 2,
            [{"tag_name": "v0.6.2"}],
            [{"tag_name": "v0.6.2", "draft": "false"}],
        ):
            with self.subTest(matches=matches):
                code, output = self.run_guard([matches])
                self.assertNotEqual(code, 0)
                self.assertEqual(output, "")

    def test_failed_later_page_cannot_use_partial_response(self) -> None:
        code, output = self.run_guard(
            [[{"tag_name": "v0.6.2", "draft": False}]], api_failure=True
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(output, "")

    def test_invalid_manifest_stops(self) -> None:
        code, output = self.run_guard([[]], manifest="not-a-version")
        self.assertNotEqual(code, 0)
        self.assertEqual(output, "")

    def test_guard_only_suppresses_pr_preparation(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("steps.publication.outputs.pending == 'true'", workflow)
        self.assertNotIn("skip-github-release:", workflow)
        self.assertIn("steps.release.outputs.release_created == 'true'", workflow)


if __name__ == "__main__":
    unittest.main()
