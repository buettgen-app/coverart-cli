"""Regression tests for missing measurements and unsafe coverage acceptance."""

from __future__ import annotations

import copy
import json

import pytest

from scripts.check_coverage import COMMON_FILES, check_report, main


def sample_report(profile="common"):
    summary = {
        "covered_lines": 95,
        "num_statements": 100,
        "covered_branches": 85,
        "num_branches": 100,
        "excluded_lines": 0,
    }
    names = COMMON_FILES if profile == "common" else {"_windows_filesystem.py"}
    return {
        "meta": {"branch_coverage": True},
        "totals": {key: value * len(names) for key, value in summary.items()},
        "files": {
            (name if name.startswith("scripts/") else f"src/coverart_cli/{name}"): {
                "summary": summary.copy()
            }
            for name in names
        },
    }


@pytest.mark.parametrize("profile", ["common", "windows"])
def test_complete_report_passes(tmp_path, profile):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(sample_report(profile)), encoding="utf-8")
    assert "lines 95.00%, branches 85.00%" in check_report(path, profile)
    assert main([str(path), "--profile", profile]) == 0


@pytest.mark.parametrize("kind", ["missing", "malformed", "no-branches", "missing-module", "empty"])
def test_incomplete_report_fails_closed(tmp_path, kind):
    path = tmp_path / "report.json"
    data = sample_report()
    if kind == "no-branches":
        data["meta"]["branch_coverage"] = False
    if kind == "missing-module":
        data["files"].pop("src/coverart_cli/tagging.py")
    if kind == "empty":
        data["totals"] = dict.fromkeys(data["totals"], 0)
    if kind != "missing":
        path.write_text("{" if kind == "malformed" else json.dumps(data), encoding="utf-8")
    assert main([str(path), "--profile", "common"]) == 1


@pytest.mark.parametrize("profile", ["common", "windows"])
@pytest.mark.parametrize("dimension", ["covered_lines", "covered_branches"])
def test_high_combined_score_cannot_hide_low_line_or_branch_coverage(tmp_path, profile, dimension):
    data = sample_report(profile)
    failing = {
        ("common", "covered_lines"): 89,
        ("windows", "covered_lines"): 84,
        ("common", "covered_branches"): 77,
        ("windows", "covered_branches"): 67,
    }
    for entry in data["files"].values():
        entry["summary"].update(covered_lines=100, covered_branches=100)
        entry["summary"][dimension] = failing[profile, dimension]
    for key in ("covered_lines", "num_statements", "covered_branches", "num_branches"):
        data["totals"][key] = sum(entry["summary"][key] for entry in data["files"].values())
    path = tmp_path / "report.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert main([str(path), "--profile", profile]) == 1


@pytest.mark.parametrize("value", [-1, 101, True, 95.0, "95"])
def test_invalid_counts_are_rejected(tmp_path, value):
    data = sample_report()
    data["totals"]["covered_lines"] = value
    path = tmp_path / "report.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert main([str(path), "--profile", "common"]) == 1


def test_diluting_windows_backend_with_other_modules_is_rejected(tmp_path):
    data = sample_report("windows")
    data["files"]["src/coverart_cli/cli.py"] = copy.deepcopy(next(iter(data["files"].values())))
    path = tmp_path / "report.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert main([str(path), "--profile", "windows"]) == 1


def test_excluding_uncovered_executable_lines_is_rejected(tmp_path):
    data = sample_report()
    data["files"]["src/coverart_cli/tagging.py"]["summary"]["excluded_lines"] = 1
    path = tmp_path / "report.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert main([str(path), "--profile", "common"]) == 1


def test_high_total_cannot_hide_an_untested_module(tmp_path):
    data = sample_report()
    data["files"]["src/coverart_cli/tagging.py"]["summary"]["covered_branches"] = 0
    path = tmp_path / "report.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert main([str(path), "--profile", "common"]) == 1


def test_zero_branch_module_and_windows_path_separators(tmp_path):
    data = sample_report()
    summary = data["files"]["src/coverart_cli/errors.py"]["summary"]
    summary.update(covered_branches=0, num_branches=0)
    for key in ("covered_branches", "num_branches"):
        data["totals"][key] = sum(item["summary"][key] for item in data["files"].values())
    data["files"] = {name.replace("/", "\\"): value for name, value in data["files"].items()}
    path = tmp_path / "report.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert main([str(path), "--profile", "common"]) == 0


@pytest.mark.parametrize("extra", ["tests/test_cli.py", "src/coverart_cli/tests/helper.py"])
def test_common_scope_rejects_unrelated_high_coverage(tmp_path, extra):
    data = sample_report()
    data["files"][extra] = {
        "summary": {
            "covered_lines": 10000,
            "num_statements": 10000,
            "covered_branches": 10000,
            "num_branches": 10000,
            "excluded_lines": 0,
        }
    }
    for key in ("covered_lines", "num_statements", "covered_branches", "num_branches"):
        data["totals"][key] += 10000
    path = tmp_path / "report.json"
    path.write_text(json.dumps(data))
    assert main([str(path), "--profile", "common"]) == 1


def test_aliases_cannot_measure_one_module_twice(tmp_path):
    data = sample_report()
    data["files"]["src\\coverart_cli\\cli.py"] = copy.deepcopy(
        data["files"]["src/coverart_cli/cli.py"]
    )
    path = tmp_path / "report.json"
    path.write_text(json.dumps(data))
    assert main([str(path), "--profile", "common"]) == 1


def test_report_totals_must_match_module_measurements(tmp_path):
    data = sample_report()
    data["totals"]["covered_lines"] += 1
    path = tmp_path / "report.json"
    path.write_text(json.dumps(data))
    assert main([str(path), "--profile", "common"]) == 1


@pytest.mark.parametrize("profile,lines,branches", [("common", 90, 78), ("windows", 85, 68)])
def test_independent_minima_cannot_hide_low_combined_coverage(tmp_path, profile, lines, branches):
    data = sample_report(profile)
    for entry in data["files"].values():
        entry["summary"].update(covered_lines=lines, covered_branches=branches)
    for key in ("covered_lines", "num_statements", "covered_branches", "num_branches"):
        data["totals"][key] = sum(entry["summary"][key] for entry in data["files"].values())
    path = tmp_path / "report.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="combined"):
        check_report(path, profile)


@pytest.mark.parametrize("profile,lines,branches", [("common", 96, 78), ("windows", 92, 68)])
@pytest.mark.parametrize("branch_weight", [1, 3])
def test_combined_policy_uses_weighted_counts_and_accepts_exact_floor(
    tmp_path, profile, lines, branches, branch_weight
):
    data = sample_report(profile)
    for entry in data["files"].values():
        entry["summary"].update(
            covered_lines=lines,
            covered_branches=branches * branch_weight,
            num_branches=100 * branch_weight,
        )
    for key in ("covered_lines", "num_statements", "covered_branches", "num_branches"):
        data["totals"][key] = sum(entry["summary"][key] for entry in data["files"].values())
    path = tmp_path / "report.json"
    path.write_text(json.dumps(data))
    if branch_weight == 1:
        expected = "87.00%" if profile == "common" else "80.00%"
        assert f"combined {expected}" in check_report(path, profile)
    else:
        with pytest.raises(ValueError, match="combined"):
            check_report(path, profile)
