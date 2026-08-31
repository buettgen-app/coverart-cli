"""CLI contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from coverart_cli.cli import main
from coverart_cli.core import RunStats


@pytest.fixture(autouse=True)
def isolate_default_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep CLI tests independent of developer config and working directory."""
    config_home = tmp_path / "config-home"
    config_home.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.chdir(tmp_path)
    # CLI contract tests exercise platform-independent argument behavior. The
    # platform capability boundary has dedicated tests below.
    monkeypatch.setattr("coverart_cli.cli.supports_secure_sidecar_writes", lambda: True)
    monkeypatch.setattr("coverart_cli.cli.supports_secure_library_traversal", lambda: True)


@pytest.mark.parametrize("report_only", [False, True])
def test_dry_run_rejects_html_output_and_preserves_file(tmp_path: Path, report_only: bool) -> None:
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


def test_processing_errors_return_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("coverart_cli.cli.run", lambda _opts: RunStats(errors=1))
    assert main([str(tmp_path)]) == 1


def test_combined_run_report_write_failure_returns_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("coverart_cli.cli.run", lambda _opts: RunStats())

    def fail_report(*_args, **_kwargs):
        raise OSError("report destination denied")

    monkeypatch.setattr("coverart_cli.report.write_report", fail_report)

    assert main([str(tmp_path), "--report-html", str(tmp_path / "report.html")]) == 1
    assert "report destination denied" in capsys.readouterr().err


def test_rejects_run_with_both_outputs_disabled(tmp_path: Path) -> None:
    assert main([str(tmp_path), "--no-embed", "--no-sidecar"]) == 2


def test_rejects_both_outputs_disabled_by_config(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("no_embed = true\nno_sidecar = true\n", encoding="utf-8")
    assert main([str(tmp_path), "--config", str(config)]) == 2


def test_cli_can_clear_configured_actions_and_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        "dry_run = true\n"
        'report_html = "report.html"\n'
        'missing_csv = "missing.csv"\n'
        "no_embed = true\n"
        "no_sidecar = true\n",
        encoding="utf-8",
    )
    captured = None

    def fake_run(opts):
        nonlocal captured
        captured = opts
        return RunStats()

    monkeypatch.setattr("coverart_cli.cli.run", fake_run)

    result = main(
        [
            str(tmp_path),
            "--config",
            str(config),
            "--no-dry-run",
            "--no-report-html",
            "--no-missing-csv",
            "--embed",
            "--sidecar",
        ]
    )

    assert result == 0
    assert captured is not None
    assert captured.dry_run is False
    assert captured.missing_csv is None
    assert captured.do_embed is True
    assert captured.do_sidecar is True


def test_explicit_builtin_value_beats_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config.toml"
    config.write_text("workers = 8\n", encoding="utf-8")
    captured = None

    def fake_run(opts):
        nonlocal captured
        captured = opts
        return RunStats()

    monkeypatch.setattr("coverart_cli.cli.run", fake_run)

    assert main([str(tmp_path), "--config", str(config), "--workers", "4"]) == 0
    assert captured is not None
    assert captured.workers == 4


def test_rejects_abbreviated_long_option(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as error:
        main([str(tmp_path), "--work", "4"])
    assert error.value.code == 2


@pytest.mark.parametrize(("option", "value"), [("--workers", "0"), ("--min-bytes", "-1")])
def test_rejects_invalid_numeric_boundaries(tmp_path: Path, option: str, value: str) -> None:
    with pytest.raises(SystemExit) as error:
        main([str(tmp_path), option, value])
    assert error.value.code == 2


def test_rejects_unsupported_sidecar_before_processing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("coverart_cli.cli.supports_secure_sidecar_writes", lambda: False)
    monkeypatch.setattr(
        "coverart_cli.cli.run",
        lambda _opts: (_ for _ in ()).throw(AssertionError("processing must not start")),
    )

    assert main([str(tmp_path)]) == 2
    assert "use --no-sidecar" in capsys.readouterr().err


def test_unsupported_platform_can_use_embed_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("coverart_cli.cli.supports_secure_sidecar_writes", lambda: False)
    monkeypatch.setattr("coverart_cli.cli.run", lambda _opts: RunStats())

    assert main([str(tmp_path), "--no-sidecar"]) == 0


def test_rejects_unsupported_library_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("coverart_cli.cli.supports_secure_library_traversal", lambda: False)
    monkeypatch.setattr(
        "coverart_cli.cli.run",
        lambda _opts: (_ for _ in ()).throw(AssertionError("processing must not start")),
    )

    assert main([str(tmp_path), "--no-sidecar"]) == 2
    assert "no-follow library traversal" in capsys.readouterr().err
