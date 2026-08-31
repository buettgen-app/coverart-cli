"""Regression tests for the release workflow's trust boundaries."""

from __future__ import annotations

from pathlib import Path

RELEASE_WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "release.yml"


def test_draft_release_lookup_does_not_require_a_tag_ref() -> None:
    """Draft releases must be discovered through the authenticated collection.

    GitHub does not create the tag ref until a draft is published, so
    ``gh release view <tag>`` cannot resolve the draft that Release Please just
    created.
    """
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert 'gh release view "$RELEASE_TAG"' not in workflow
    assert "releases?per_page=100" in workflow
    assert "--paginate" in workflow
    assert "select(.tag_name == $tag)" in workflow
    assert "length == 1" in workflow
