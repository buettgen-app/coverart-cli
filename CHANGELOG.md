# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.3](https://github.com/buettgen-app/coverart-cli/compare/v0.4.1...v0.4.3) (2026-07-13)


### Bug Fixes

* **ci:** add guarded release recovery ([#31](https://github.com/buettgen-app/coverart-cli/pull/31)) ([151ec6f](https://github.com/buettgen-app/coverart-cli/commit/151ec6f))
* **ci:** harden and separate release publishing ([#30](https://github.com/buettgen-app/coverart-cli/pull/30)) ([25c2d13](https://github.com/buettgen-app/coverart-cli/commit/25c2d13))
* **security:** avoid personal path leaks in reports ([#27](https://github.com/buettgen-app/coverart-cli/issues/27)) ([01d3742](https://github.com/buettgen-app/coverart-cli/commit/01d3742591b21e8fa202437c9dba5dce5f568fb4))

## [0.4.1](https://github.com/buettgen-app/coverart-cli/compare/v0.4.0...v0.4.1) (2026-05-18)


### Bug Fixes

* add workflow_dispatch + CodeRabbit badge ([#14](https://github.com/buettgen-app/coverart-cli/issues/14)) ([ffe5bde](https://github.com/buettgen-app/coverart-cli/commit/ffe5bded3dfcbb2277df9036fe322b1778124799))
* redact secret query params before logging ([#17](https://github.com/buettgen-app/coverart-cli/issues/17)) ([245d11f](https://github.com/buettgen-app/coverart-cli/commit/245d11fa1e5e7fd8c261736992d6501f3572762b))
* use absolute URL for screenshot so PyPI renders it ([#18](https://github.com/buettgen-app/coverart-cli/issues/18)) ([8279679](https://github.com/buettgen-app/coverart-cli/commit/82796794afa1d3ad0366853d0d7b7ec1a21e43ee))
* use pepy.tech for PyPI downloads badge ([#16](https://github.com/buettgen-app/coverart-cli/issues/16)) ([84099b3](https://github.com/buettgen-app/coverart-cli/commit/84099b330b348f928d680fd2005ad8e6aa9bf184))

## [0.4.0](https://github.com/buettgen-app/coverart-cli/compare/v0.3.0...v0.4.0) (2026-05-17)


### Features

* add release-please for merge-driven version bumps ([#9](https://github.com/buettgen-app/coverart-cli/issues/9)) ([28ec876](https://github.com/buettgen-app/coverart-cli/commit/28ec8768d70e22c50ebd58e6ca170fb65393eb6c))
* auto-enable squash auto-merge + CodeRabbit config ([#11](https://github.com/buettgen-app/coverart-cli/issues/11)) ([3756926](https://github.com/buettgen-app/coverart-cli/commit/37569263e397e61d34d3cd865f4935c94432e3a9))


### Bug Fixes

* drop failing approve step from Dependabot auto-merge ([#12](https://github.com/buettgen-app/coverart-cli/issues/12)) ([c2f984d](https://github.com/buettgen-app/coverart-cli/commit/c2f984d7417ee811bc80e90ec9b3d2f587ffddb2))

## [0.3.0] - 2026-05-17

### Added

- **TOML config file** support — `~/.config/coverart-cli/config.toml`,
  `./coverart.toml`, or `--config PATH`. CLI flags still override the config.
- **`py.typed`** marker file for PEP 561 — type checkers can now see our types.
- **Public library API** explicitly defined via `__all__` in
  `coverart_cli/__init__.py`. You can now do
  `from coverart_cli import RunOptions, run, ITunesProvider`.
- **`.editorconfig`** for cross-IDE consistency.
- **`.pre-commit-config.yaml`** with ruff + ruff-format + standard checks.
- **`SECURITY.md`** with private vulnerability reporting link.
- **PyPI release workflow** (`.github/workflows/release.yml`) — push a
  `v*` tag and the package is built and uploaded via PyPI Trusted Publishing.
  Includes a **`needs: test`** gate so a red main can't ship a release.
- **Dependabot** monthly checks for GitHub Actions and pip.

### Changed

- Minimum Python is now **3.11** (was 3.10) — needed for stdlib `tomllib`.
- Metadata now uses **PEP 639 SPDX** (`license = "MIT"` + `license-files`),
  no more deprecated `License ::` classifier.
- Description and CLI help text now reflect the actual provider and format
  coverage (4 providers, 5 formats).
- All providers share a single `_default_user_agent()` derived from
  `__version__` — no more stale `0.1.0` strings hard-coded in defaults.
- `iTunesProvider` and `DeezerProvider` correctly accept `user_agent=`
  (was silently ignored, broke library usage).
- `MusicBrainzProvider` dead `release` fallback branch removed.
- Size threshold for accepted covers unified across providers via
  `tagging.MIN_COVER_BYTES`.
- `scan_library` path-traversal logic simplified to `relative_to` +
  `ValueError` guard.

## [0.2.0] - 2026-05-17

### Added

- **iTunes provider** (Apple Music public search) — no API key required.
- **Deezer provider** — no API key required.
- **FLAC, Ogg Vorbis, and Opus** file format support (read + embed).
- HTML report shows iTunes / Deezer / Embedded filter chips and badges.
- Demo report generator (`docs/make_demo_report.py`).
- **`--min-bytes N`**: upgrade existing covers smaller than N bytes. Default 0
  (keep all existing). Setting e.g. `--min-bytes 50000` causes the tool to
  re-fetch covers for any album whose current artwork is below 50 KB.
- **`--replace-smaller`**: when the freshly fetched cover is larger than the
  existing one, replace it. Default is to keep the larger existing cover when
  both qualify.
- `existing_embedded_size()` helper in `coverart_cli.tagging` for inspecting
  in-tag artwork sizes across all five formats.

### Changed

- Last.fm is now optional — if no key is supplied, the tool runs with the three
  free providers instead of failing.
- README rewritten — significantly shorter, with screenshots and an
  alternatives table.

## [0.1.0] - 2026-05-17

### Added

- Initial release.
- Tag-first album metadata reading via `mutagen`, directory-name fallback.
- Last.fm `album.getinfo` provider with placeholder-image rejection.
- MusicBrainz + Cover Art Archive fallback provider with rate limiting.
- Embed into MP3 (`ID3 APIC`) and M4A (`covr` atom).
- Sidecar `cover.jpg` / `cover.png` writing with magic-byte MIME detection.
- CLI: `--lastfm-key`, `--no-lastfm`, `--no-musicbrainz`, `--no-embed`,
  `--no-sidecar`, `--dry-run`, `--missing-csv`, `-v`/`-vv`.
- **HTML coverage report**: `--report-html PATH`, `--report-only`, `--no-thumbs`.
  Self-contained single-file output with embedded thumbnails, dark/light theme,
  searchable + filterable album grid. Editorial/liner-notes aesthetic with
  Fraunces, Geist, and JetBrains Mono typography.
- Pytest smoke suite (25 tests) for tagging, provider helpers, and report module.
- GitHub Actions CI for lint + tests on Python 3.10–3.13.
