"""CLI contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from coverart_cli.cli import main


@pytest.mark.parametrize("report_only", [False, True])
def test_dry_run_rejects_html_output_and_preserves_file(
    tmp_path: Path, report_only: bool
) -> None:
    library = tmp_path / "library"
    library.mkdir()
    output = tmp_path / "report.html"
    output.write_text("KEEP", encoding="utf-8")
    args = [str(library), "--dry-run", "--report-html", str(output)]
    if report_only:
        args.append("--report-only")

    assert main(args) == 2
    assert output.read_text(encoding="utf-8") == "KEEP"


def test_dry_run_rejects_missing_csv_and_preserves_file(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    output = tmp_path / "missing.csv"
    output.write_text("KEEP", encoding="utf-8")

    assert main([str(library), "--dry-run", "--missing-csv", str(output)]) == 2
    assert output.read_text(encoding="utf-8") == "KEEP"
