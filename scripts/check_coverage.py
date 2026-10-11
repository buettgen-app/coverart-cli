"""Fail closed on absent, incomplete or below-policy branch coverage reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

POLICIES = {"common": (90.0, 78.0), "windows": (85.0, 68.0)}
PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "coverart_cli"
COMMON_FILES = {
    path.relative_to(PACKAGE_ROOT).as_posix()
    for path in PACKAGE_ROOT.rglob("*.py")
    if path.name != "_windows_filesystem.py"
}
COMMON_FILES |= {"scripts/" + path.name for path in Path(__file__).resolve().parent.glob("*.py")}


def percentages(summary: dict) -> tuple[float, float]:
    values = []
    for covered_key, total_key in (
        ("covered_lines", "num_statements"),
        ("covered_branches", "num_branches"),
    ):
        covered, total = summary[covered_key], summary[total_key]
        if type(covered) is not int or type(total) is not int or not 0 <= covered <= total:
            raise ValueError("invalid coverage counts")
        values.append(100.0 * covered / total if total else 100.0)
    return values[0], values[1]


def check_report(path: Path, profile: str) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data["meta"]["branch_coverage"] is not True:
        raise ValueError("branch measurement is required")
    files = data["files"]
    names = {name.replace("\\", "/").split("coverart_cli/", 1)[-1] for name in files}
    required = COMMON_FILES if profile == "common" else {"_windows_filesystem.py"}
    if missing := required - names:
        raise ValueError("unmeasured modules: " + ", ".join(sorted(missing)))
    if profile == "windows" and names != required:
        raise ValueError("Windows backend coverage must be measured independently")
    for name, entry in files.items():
        # The scope must describe executed code, including its missed branches.
        module_lines, module_branches = percentages(entry["summary"])
        if entry["summary"].get("excluded_lines", 0):
            raise ValueError(f"excluded executable lines in {name}")
        if module_lines < 75 or module_branches < 50:
            raise ValueError(f"module below 75% lines / 50% branches: {name}")
    lines, branches = percentages(data["totals"])
    if not data["totals"]["num_statements"] or not data["totals"]["num_branches"]:
        raise ValueError("empty coverage report")
    minimum_lines, minimum_branches = POLICIES[profile]
    if lines < minimum_lines or branches < minimum_branches:
        raise ValueError(
            f"{profile}: lines {lines:.2f}% / required {minimum_lines:.0f}%; "
            f"branches {branches:.2f}% / required {minimum_branches:.0f}%"
        )
    return f"{profile}: lines {lines:.2f}%, branches {branches:.2f}%"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--profile", choices=POLICIES, required=True)
    args = parser.parse_args(argv)
    try:
        result = check_report(args.report, args.profile)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Coverage gate failed: {error}")
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
