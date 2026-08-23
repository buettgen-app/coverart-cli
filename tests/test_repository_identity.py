from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATED_FILES = (
    "README.md",
    "pyproject.toml",
    "CHANGELOG.md",
    "SECURITY.md",
    "src/coverart_cli/providers/base.py",
    "src/coverart_cli/cli.py",
    "src/coverart_cli/templates/report.html",
)


def test_legacy_repository_identity_is_not_reintroduced() -> None:
    legacy_identity = "WildDragonKing/coverart-cli"
    offenders = [
        relative_path
        for relative_path in MIGRATED_FILES
        if legacy_identity in (ROOT / relative_path).read_text(encoding="utf-8")
    ]

    assert offenders == []
