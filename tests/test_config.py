"""Tests for the TOML config file loader."""
from __future__ import annotations

from pathlib import Path

from coverart_cli.config import ALLOWED_KEYS, load_config


def test_load_config_empty(tmp_path: Path) -> None:
    assert load_config(tmp_path / "missing.toml") == {}


def test_load_config_explicit(tmp_path: Path) -> None:
    p = tmp_path / "c.toml"
    p.write_text(
        'lastfm_key = "abc"\n'
        "min_bytes = 30000\n"
        "no_deezer = true\n"
    )
    cfg = load_config(p)
    assert cfg == {"lastfm_key": "abc", "min_bytes": 30000, "no_deezer": True}


def test_load_config_strips_unknown_keys(tmp_path: Path, caplog) -> None:
    p = tmp_path / "c.toml"
    p.write_text(
        'lastfm_key = "abc"\n'
        'not_a_real_flag = "xx"\n'
    )
    cfg = load_config(p)
    assert "lastfm_key" in cfg
    assert "not_a_real_flag" not in cfg


def test_load_config_ignores_malformed(tmp_path: Path) -> None:
    p = tmp_path / "c.toml"
    p.write_text("this is = not valid toml [ }")
    assert load_config(p) == {}


def test_load_config_normalizes_paths_and_rejects_invalid_types(tmp_path: Path) -> None:
    p = tmp_path / "c.toml"
    p.write_text(
        'report_html = "reports/library.html"\n'
        'workers = "many"\n'
        'no_embed = "yes"\n'
        "min_bytes = -1\n"
    )

    assert load_config(p) == {"report_html": Path("reports/library.html")}


def test_allowed_keys_match_argparse_dests() -> None:
    """The keys we accept must match argparse argument dests."""
    from coverart_cli.cli import build_parser

    dests = {a.dest for a in build_parser()._actions if a.dest != "help"}
    unknown = ALLOWED_KEYS - dests
    assert unknown == set(), f"config keys not present as CLI dests: {unknown}"
