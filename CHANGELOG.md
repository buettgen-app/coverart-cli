# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.2](https://github.com/buettgen-app/coverart-cli/compare/v0.7.1...v0.7.2) (2026-10-11)


### Bug Fixes

* enforce combined coverage in every gate invocation ([dc7946d](https://github.com/buettgen-app/coverart-cli/commit/dc7946d3ff1adc0b8eb1cd610896e02ac20bfb24))

## [0.7.1](https://github.com/buettgen-app/coverart-cli/compare/v0.7.0...v0.7.1) (2026-10-11)


### Bug Fixes

* enforce coverage scope and resilient library scanning ([1eba434](https://github.com/buettgen-app/coverart-cli/commit/1eba43499a19c4912e9658a9bfdec79856e8e4ac))

## [0.7.0](https://github.com/buettgen-app/coverart-cli/compare/v0.6.2...v0.7.0) (2026-10-11)


### Features

* support native Windows library processing ([a731b75](https://github.com/buettgen-app/coverart-cli/commit/a731b75bccbf8cbd6df74e14f042ed41ff86f5eb))


### Bug Fixes

* address project review findings and disable unlicensed reviews ([a0db4d7](https://github.com/buettgen-app/coverart-cli/commit/a0db4d76f1c77c657bdb33230201fcab1104a294))
* bind release publication and approve verified PR checks ([ef029bf](https://github.com/buettgen-app/coverart-cli/commit/ef029bfe10a43ee4da43310ac10a3e0bfd350469))
* bound hostile HTTP responses and enforce cross-platform coverage ([4533d42](https://github.com/buettgen-app/coverart-cli/commit/4533d42832fb01c2649a8bb7a125708c5a392c48))
* complete verified releases automatically after main pushes ([f5b8c49](https://github.com/buettgen-app/coverart-cli/commit/f5b8c49653ff1de04d1c8cc203ac4ccf1fdddc49))
* eliminate vulnerable attestation dependencies and restore canonical lock ([c9cf71b](https://github.com/buettgen-app/coverart-cli/commit/c9cf71bae2dfe15509df0b237a6c40823bbe1249))
* harden report privacy, provider retries and dependency automation ([5bea929](https://github.com/buettgen-app/coverart-cli/commit/5bea929c50399adced5c9dbcfb07def79efdc6ea))
* pin universal Python floor and preserve budgeted demo coverage ([dff5018](https://github.com/buettgen-app/coverart-cli/commit/dff501803c7ccbcc5513a774a8af2b0b98ebc019))
* preserve ID3 versions and metadata while embedding artwork ([1759116](https://github.com/buettgen-app/coverart-cli/commit/1759116e727cfd29949c7737543035a69e21afe9))
* reject unbound release drafts during automatic recovery ([b8fb70f](https://github.com/buettgen-app/coverart-cli/commit/b8fb70f89c2de45c7ed14857829bb4343ae8f812))
* repair CI lock drift and require protected gates before auto-merge ([5316417](https://github.com/buettgen-app/coverart-cli/commit/5316417b3ef16297ba8076940e928c6fd9af0e10))
* scan staged blobs and cover environment and Windows path variants ([4c85043](https://github.com/buettgen-app/coverart-cli/commit/4c85043603a1ff2d2784b7fb1a4f0713183cbda4))
* share root validation with reports and support compilation artists ([4880cd1](https://github.com/buettgen-app/coverart-cli/commit/4880cd1bc907f7a9351966e64c66c0244827d587))
* synchronize tooling hash locks with updated build requirements ([b6baf8e](https://github.com/buettgen-app/coverart-cli/commit/b6baf8ef15cbd0cc1d3d8d554d7229b0b75ac1f8))
* upgrade ID3v1-only files before embedding artwork ([dac5a2e](https://github.com/buettgen-app/coverart-cli/commit/dac5a2e2b083230c78934c727a45ba604994573f))
* validate root album identity and preserve relative-root metadata ([23bc756](https://github.com/buettgen-app/coverart-cli/commit/23bc756674223c94b970615ec9430298aba651b1))


### Documentation

* link Renovate activation and migration guide ([d3b9fc2](https://github.com/buettgen-app/coverart-cli/commit/d3b9fc2c0f9beab404fef1550d657903936b3c47))
* normalize release guide whitespace ([ca0985d](https://github.com/buettgen-app/coverart-cli/commit/ca0985d851664c3b0b71076b48c08f095aef4407))
* refresh README and separate release administration guide ([3b1d795](https://github.com/buettgen-app/coverart-cli/commit/3b1d795825c4632fc0473944bf8888f998e38591))
* select Python 3.15 locally and describe the five-version test matrix ([c975c58](https://github.com/buettgen-app/coverart-cli/commit/c975c583c18016c24f5ba7ff08cb1257fc7440ac))

## [0.6.2](https://github.com/buettgen-app/coverart-cli/compare/v0.6.0...v0.6.2) (2026-09-06)

This patch includes the fixes prepared for the unpublished 0.6.1 draft.

### Bug Fixes

* preserve artwork and dry-run integrity, including the reviewed CodeQL fixes
* redact URL userinfo from provider logs
* restore cross-platform CI gates
* bind publication to protected tags, exact artifacts, and verified provenance
* resolve draft releases before tag creation and prevent duplicate release PRs while publication is pending

## [0.6.1] (unpublished draft, 2026-08-31)


### Bug Fixes

* close CodeQL review findings ([d35f7e3](https://github.com/buettgen-app/coverart-cli/commit/d35f7e303d15c68e96cb7a37ce2d135462d2e791))
* complete artwork integrity and release hardening ([37f72cb](https://github.com/buettgen-app/coverart-cli/commit/37f72cbef812e137eb05bd4629c50bc7ea9beb1d))
* enforce artwork and dry-run integrity ([cba3131](https://github.com/buettgen-app/coverart-cli/commit/cba3131e582afd5526e9b0185e6558308dd34fbe))
* **release:** bind publication to protected tags, exact artifacts, and verified provenance
* restore cross-platform CI gates ([42f4c32](https://github.com/buettgen-app/coverart-cli/commit/42f4c32cd5b90ab54cdbeb12651be705ba66f6be))

## [0.6.0](https://github.com/buettgen-app/coverart-cli/compare/v0.5.0...v0.6.0) (2026-08-23)


### Features

* add release-please for merge-driven version bumps ([#9](https://github.com/buettgen-app/coverart-cli/issues/9)) ([28ec876](https://github.com/buettgen-app/coverart-cli/commit/28ec8768d70e22c50ebd58e6ca170fb65393eb6c))
* auto-enable squash auto-merge + CodeRabbit config ([#11](https://github.com/buettgen-app/coverart-cli/issues/11)) ([3756926](https://github.com/buettgen-app/coverart-cli/commit/37569263e397e61d34d3cd865f4935c94432e3a9))


### Bug Fixes

* add workflow_dispatch + CodeRabbit badge ([#14](https://github.com/buettgen-app/coverart-cli/issues/14)) ([ffe5bde](https://github.com/buettgen-app/coverart-cli/commit/ffe5bded3dfcbb2277df9036fe322b1778124799))
* **ci:** add guarded release recovery ([#31](https://github.com/buettgen-app/coverart-cli/issues/31)) ([151ec6f](https://github.com/buettgen-app/coverart-cli/commit/151ec6f91577b8921db4a04a3c5958cc8a2cac4e))
* **ci:** harden and separate release publishing ([#30](https://github.com/buettgen-app/coverart-cli/issues/30)) ([25c2d13](https://github.com/buettgen-app/coverart-cli/commit/25c2d1390d7a008eb2aab42eb604b9e359197e96))
* **ci:** restore PyPI publisher identity ([#33](https://github.com/buettgen-app/coverart-cli/issues/33)) ([6ab951f](https://github.com/buettgen-app/coverart-cli/commit/6ab951f5128f084ea7621938f2a22dc1d0609987))
* drop failing approve step from Dependabot auto-merge ([#12](https://github.com/buettgen-app/coverart-cli/issues/12)) ([c2f984d](https://github.com/buettgen-app/coverart-cli/commit/c2f984d7417ee811bc80e90ec9b3d2f587ffddb2))
* harden artwork writes and complete album coverage ([#43](https://github.com/buettgen-app/coverart-cli/issues/43)) ([900e3a0](https://github.com/buettgen-app/coverart-cli/commit/900e3a02a4c6c093df52528705e053b5640a1d43))
* honor local artwork quality thresholds ([d0364a2](https://github.com/buettgen-app/coverart-cli/commit/d0364a289ed364d7ac3dba7acb2105abf6b49992))
* recover draft releases by release metadata ([4663ff6](https://github.com/buettgen-app/coverart-cli/commit/4663ff6e2985edf7321fc9c533020a32293d2667))
* redact secret query params before logging ([#17](https://github.com/buettgen-app/coverart-cli/issues/17)) ([245d11f](https://github.com/buettgen-app/coverart-cli/commit/245d11fa1e5e7fd8c261736992d6501f3572762b))
* reuse and detect local artwork consistently ([1970ed8](https://github.com/buettgen-app/coverart-cli/commit/1970ed80dc6574c7d13c418105fe735a47997801))
* **security:** avoid personal path leaks in reports ([01d3742](https://github.com/buettgen-app/coverart-cli/commit/01d3742591b21e8fa202437c9dba5dce5f568fb4))
* **security:** avoid personal path leaks in reports ([#27](https://github.com/buettgen-app/coverart-cli/issues/27)) ([01d3742](https://github.com/buettgen-app/coverart-cli/commit/01d3742591b21e8fa202437c9dba5dce5f568fb4))
* use absolute URL for screenshot so PyPI renders it ([#18](https://github.com/buettgen-app/coverart-cli/issues/18)) ([8279679](https://github.com/buettgen-app/coverart-cli/commit/82796794afa1d3ad0366853d0d7b7ec1a21e43ee))
* use pepy.tech for PyPI downloads badge ([#16](https://github.com/buettgen-app/coverart-cli/issues/16)) ([84099b3](https://github.com/buettgen-app/coverart-cli/commit/84099b330b348f928d680fd2005ad8e6aa9bf184))

## [0.5.0](https://github.com/buettgen-app/coverart-cli/compare/v0.4.5...v0.5.0) (2026-08-23)


### Features

* add release-please for merge-driven version bumps ([#9](https://github.com/buettgen-app/coverart-cli/issues/9)) ([28ec876](https://github.com/buettgen-app/coverart-cli/commit/28ec8768d70e22c50ebd58e6ca170fb65393eb6c))
* auto-enable squash auto-merge + CodeRabbit config ([#11](https://github.com/buettgen-app/coverart-cli/issues/11)) ([3756926](https://github.com/buettgen-app/coverart-cli/commit/37569263e397e61d34d3cd865f4935c94432e3a9))


### Bug Fixes

* add workflow_dispatch + CodeRabbit badge ([#14](https://github.com/buettgen-app/coverart-cli/issues/14)) ([ffe5bde](https://github.com/buettgen-app/coverart-cli/commit/ffe5bded3dfcbb2277df9036fe322b1778124799))
* **ci:** add guarded release recovery ([#31](https://github.com/buettgen-app/coverart-cli/issues/31)) ([151ec6f](https://github.com/buettgen-app/coverart-cli/commit/151ec6f91577b8921db4a04a3c5958cc8a2cac4e))
* **ci:** harden and separate release publishing ([#30](https://github.com/buettgen-app/coverart-cli/issues/30)) ([25c2d13](https://github.com/buettgen-app/coverart-cli/commit/25c2d1390d7a008eb2aab42eb604b9e359197e96))
* **ci:** restore PyPI publisher identity ([#33](https://github.com/buettgen-app/coverart-cli/issues/33)) ([6ab951f](https://github.com/buettgen-app/coverart-cli/commit/6ab951f5128f084ea7621938f2a22dc1d0609987))
* drop failing approve step from Dependabot auto-merge ([#12](https://github.com/buettgen-app/coverart-cli/issues/12)) ([c2f984d](https://github.com/buettgen-app/coverart-cli/commit/c2f984d7417ee811bc80e90ec9b3d2f587ffddb2))
* harden artwork writes and complete album coverage ([#43](https://github.com/buettgen-app/coverart-cli/issues/43)) ([900e3a0](https://github.com/buettgen-app/coverart-cli/commit/900e3a02a4c6c093df52528705e053b5640a1d43))
* honor local artwork quality thresholds ([d0364a2](https://github.com/buettgen-app/coverart-cli/commit/d0364a289ed364d7ac3dba7acb2105abf6b49992))
* recover draft releases by release metadata ([4663ff6](https://github.com/buettgen-app/coverart-cli/commit/4663ff6e2985edf7321fc9c533020a32293d2667))
* redact secret query params before logging ([#17](https://github.com/buettgen-app/coverart-cli/issues/17)) ([245d11f](https://github.com/buettgen-app/coverart-cli/commit/245d11fa1e5e7fd8c261736992d6501f3572762b))
* reuse and detect local artwork consistently ([1970ed8](https://github.com/buettgen-app/coverart-cli/commit/1970ed80dc6574c7d13c418105fe735a47997801))
* **security:** avoid personal path leaks in reports ([01d3742](https://github.com/buettgen-app/coverart-cli/commit/01d3742591b21e8fa202437c9dba5dce5f568fb4))
* **security:** avoid personal path leaks in reports ([#27](https://github.com/buettgen-app/coverart-cli/issues/27)) ([01d3742](https://github.com/buettgen-app/coverart-cli/commit/01d3742591b21e8fa202437c9dba5dce5f568fb4))
* use absolute URL for screenshot so PyPI renders it ([#18](https://github.com/buettgen-app/coverart-cli/issues/18)) ([8279679](https://github.com/buettgen-app/coverart-cli/commit/82796794afa1d3ad0366853d0d7b7ec1a21e43ee))
* use pepy.tech for PyPI downloads badge ([#16](https://github.com/buettgen-app/coverart-cli/issues/16)) ([84099b3](https://github.com/buettgen-app/coverart-cli/commit/84099b330b348f928d680fd2005ad8e6aa9bf184))

## [0.4.5](https://github.com/buettgen-app/coverart-cli/compare/v0.4.4...v0.4.5) (2026-08-23)


### Bug Fixes

* honor local artwork quality thresholds ([d0364a2](https://github.com/buettgen-app/coverart-cli/commit/d0364a289ed364d7ac3dba7acb2105abf6b49992))
* reuse and detect local artwork consistently ([1970ed8](https://github.com/buettgen-app/coverart-cli/commit/1970ed80dc6574c7d13c418105fe735a47997801))

## [0.4.4](https://github.com/buettgen-app/coverart-cli/compare/v0.4.3...v0.4.4) (2026-08-23)


### Bug Fixes

* **ci:** restore PyPI publisher identity ([#33](https://github.com/buettgen-app/coverart-cli/issues/33)) ([6ab951f](https://github.com/buettgen-app/coverart-cli/commit/6ab951f5128f084ea7621938f2a22dc1d0609987))
* harden artwork writes and complete album coverage ([#43](https://github.com/buettgen-app/coverart-cli/issues/43)) ([900e3a0](https://github.com/buettgen-app/coverart-cli/commit/900e3a02a4c6c093df52528705e053b5640a1d43))

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
