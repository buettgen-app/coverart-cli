# coverart-cli

**Album artwork in your audio tags, beside your tracks, and in a searchable report.**

[![CI](https://github.com/buettgen-app/coverart-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/buettgen-app/coverart-cli/actions/workflows/ci.yml)
[![CodeQL](https://github.com/buettgen-app/coverart-cli/actions/workflows/codeql.yml/badge.svg)](https://github.com/buettgen-app/coverart-cli/actions/workflows/codeql.yml)
[![PyPI](https://img.shields.io/pypi/v/coverart-cli)](https://pypi.org/project/coverart-cli/)
[![Python](https://img.shields.io/pypi/pyversions/coverart-cli)](https://pypi.org/project/coverart-cli/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Fill missing artwork from iTunes, Deezer, MusicBrainz / Cover Art Archive, and
optionally Last.fm. One run embeds artwork into supported audio files and writes
a sidecar for players that read covers from the album folder. Existing local
artwork is reused where possible.

<picture>
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/buettgen-app/coverart-cli/main/docs/screenshots/report-light.png">
  <img src="https://raw.githubusercontent.com/buettgen-app/coverart-cli/main/docs/screenshots/report-dark.png" alt="Coverart HTML report with album artwork, coverage statistics, search, and filters" width="100%">
</picture>

[Quick start](#quick-start) · [Workflows](#common-workflows) ·
[Configuration](#configuration) · [Reports](#html-report) ·
[Development](#development) · [Changelog](CHANGELOG.md)

## Install

Requires **Python 3.11+ on Linux or macOS**. Windows library processing is currently
unsupported: it requires directory-relative, no-follow filesystem APIs.

Install in an isolated tool environment with either
[pipx](https://pipx.pypa.io/) or [uv](https://docs.astral.sh/uv/):

```bash
pipx install coverart-cli
# Or:
uv tool install coverart-cli

coverart --version
```

Upgrade with `pipx upgrade coverart-cli` or `uv tool upgrade coverart-cli`.
PyPI contains the latest published release; this README also documents repository
changes that may be awaiting release.

## Quick start

```bash
# Preview fetching and planned changes without writing files.
coverart ~/Music --dry-run -v

# Fill missing embedded artwork and album-folder sidecars.
coverart ~/Music

# Inspect coverage locally without contacting any provider.
coverart ~/Music --report-only --report-html report.html
```

Open `report.html` in your browser. The default providers require no API key.
To enable Last.fm as the first provider, set `LASTFM_API_KEY` in your environment;
get a key from [Last.fm](https://www.last.fm/api/account/create).

Dry runs still contact providers and download candidate images. They write
neither tags nor sidecars and cannot be combined with `--report-html` or
`--missing-csv`. Use a separate report-only run for a local coverage check.

## How it works

1. Discover supported audio files in album directories, including the selected
   root when it is itself an album folder.
2. Read album artist and album tags; fall back to `Artist/Album/` directory names
   when readable tags are absent.
3. Reuse a suitable local sidecar to fill missing embeds, or try enabled providers
   in order until valid artwork is found.
4. Write the requested outputs, retaining existing artwork unless an upgrade
   threshold is configured.

```text
Music/
└── Artist/
    └── Album/
        ├── 01 - Track.mp3
        ├── 02 - Track.mp3
        └── cover.jpg
```

A root with conflicting album identities, or a mix of readable and unreadable
identities, is excluded from writing and reports. Compilations may have different
track artists when their album identity agrees. Organize loose tracks into album
directories before processing them. By default,
processing skips an album only when a usable sidecar exists **and every supported
track has embedded artwork**. Disabling an output removes that requirement from
the completion check.

## Common workflows

| Goal | Command |
| --- | --- |
| Preview a library | `coverart ~/Music --dry-run -v` |
| Process one album | `coverart "$HOME/Music/Artist/Album"` |
| Write sidecars only | `coverart ~/Music --no-embed` |
| Embed artwork only | `coverart ~/Music --no-sidecar` |
| Upgrade artwork below 30,000 bytes | `coverart ~/Music --min-bytes 30000` |
| Use tags without directory fallback | `coverart ~/Music --no-fallback-dirnames` |
| Export misses and processing failures | `coverart ~/Music --missing-csv missing.csv` |
| Generate a report after processing | `coverart ~/Music --report-html report.html` |
| Generate a report without fetching | `coverart ~/Music --report-only --report-html report.html` |
| Omit report thumbnails | `coverart ~/Music --report-only --report-html report.html --no-thumbs` |
| Process albums serially | `coverart ~/Music --workers 1` |

`--min-bytes` applies to embedded artwork and sidecars. Byte size is an upgrade
heuristic, not a resolution or visual-quality score. Larger existing artwork is
kept by default; `--replace-smaller` disables that protection, allowing a
below-threshold cover to be replaced even by a smaller downloaded image.

Four workers run by default. MusicBrainz requests are rate-limited internally.
Use `-v` for progress, `-vv` for debugging, and `coverart --help` for all options.

## HTML report

The self-contained HTML report includes album search, source filters, coverage
statistics, and light/dark themes. Viewing it requires no server. Thumbnails come
from local sidecars and have a shared size budget; embedded-only albums can have
coverage without a thumbnail.

Report coverage means an album has **a usable sidecar or artwork embedded in every
supported track**. This is broader than the default processing completion check,
which requires both. Provider provenance is not stored per album: existing
artwork is classified as covered with an unknown origin. Reports contain library,
artist and album names plus optional artwork; review their contents before sharing.

## Configuration

Store defaults in `~/.config/coverart-cli/config.toml` (or under
`$XDG_CONFIG_HOME/coverart-cli/config.toml`):

```toml
workers = 4
min_bytes = 30000
no_embed = false
no_sidecar = false
no_musicbrainz = false
# Optional: identify yourself when contacting MusicBrainz.
user_agent = "coverart-cli (mailto:you@example.com)"
```

Configuration is merged in this order; later values win:

```text
Built-in defaults → user config → ./coverart.toml → --config PATH
                  → LASTFM_API_KEY (key only) → explicit CLI flags
```

Keys match CLI option names with underscores: `no_embed`, `min_bytes`,
`report_html`, and so on. Unknown keys and invalid values are ignored with a
warning. Keep API keys out of committed project configuration.

Explicit flags override configured values even when equal to the built-in
default. Use `--embed`, `--sidecar`, `--no-dry-run`, `--no-report-html`, or
`--no-missing-csv` to clear the corresponding configured action.

## Providers and formats

Providers are tried in the following order; Last.fm is skipped without a key.

| Provider | API key | Disable with |
| --- | --- | --- |
| [Last.fm](https://www.last.fm/api) | Required | `--no-lastfm` |
| [iTunes Search](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/) | None | `--no-itunes` |
| [Deezer](https://developers.deezer.com/api) | None | `--no-deezer` |
| [MusicBrainz](https://musicbrainz.org/doc/Cover_Art_Archive) / Cover Art Archive | None | `--no-musicbrainz` |

| Audio formats | Embedded artwork |
| --- | --- |
| MP3 | ID3 APIC |
| M4A, M4B, MP4 | `covr` atom |
| FLAC | Picture block |
| Ogg Vorbis, Opus | `metadata_block_picture` |

Recognized local sidecars are `cover.jpg`, `cover.png`, `folder.jpg`, and
`folder.png`. Artwork is validated as JPEG or PNG before use: at most 20 MiB,
4,096 pixels per dimension, and 16,777,216 total pixels. The normal minimum
usable cover size is 2,000 bytes. Sidecar output follows the validated image
format (`cover.jpg` or `cover.png`).

## File safety and privacy

Album and artist names are sent to enabled providers over HTTPS. Provider
downloads and redirects are restricted to their permitted API/image hosts.
Report-only mode makes no provider requests.

Library traversal skips hidden entries and does not follow symbolic links to
album folders, tracks, or covers. Tag writes use verified file identities and
copy-on-write replacement. Keep a backup before bulk metadata changes and avoid
moving or renaming the library while a run is writing: a POSIX directory rename
does not revoke an already-open descriptor.

Read [SECURITY.md](SECURITY.md) for trust boundaries and vulnerability reporting.

## Automation and Python API

CLI exit codes are `0` for a completed run (ordinary cover misses are allowed),
`1` for processing or I/O errors, and `2` for invalid options or unsupported
platform capabilities. Use `--missing-csv` to assess missing artwork separately.

```python
from pathlib import Path
from coverart_cli.core import RunOptions, run
from coverart_cli.providers import DeezerProvider, ITunesProvider

stats = run(
    RunOptions(
        root=Path.home() / "Music",
        providers=[ITunesProvider(), DeezerProvider()],
        dry_run=True,
    )
)
print(stats.fetched_from, stats.not_found, stats.errors)
```

## Development

Dependency updates are configured through [Renovate](docs/dependency-updates.md),
including Python hash locks, GitHub Actions and pre-commit hooks.

Use the checked-in hash locks and the same editable-install approach as CI:

```bash
git clone https://github.com/buettgen-app/coverart-cli.git
cd coverart-cli
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-ci.txt
python -m pip install --no-deps --no-build-isolation -e .

ruff check .
ruff format --check .
pyrefly check
pytest --cov=coverart_cli --cov-report=term-missing --cov-fail-under=78
```

Install FFmpeg to enable the audio-stream preservation oracle used in CI.
The Linux test matrix covers Python 3.11–3.14; additional jobs check macOS
metadata preservation and rejection of unsupported Windows operations.
CodeQL, Zizmor, dependency review, fuzzing, and reproducible artifact builds
provide separate checks.

Run `python scripts/check_repository.py` to check tracked files for private
contact details and local artifacts. See [repository hygiene and CI gates](docs/repository-checks.md)
for privacy-check limits and the required-check configuration.

Report bugs or request features in [GitHub Issues](https://github.com/buettgen-app/coverart-cli/issues).
For releases, protected tags, PyPI Trusted Publishing, and recovery procedures,
see the [release and publishing guide](docs/releases.md).

## License

[MIT](LICENSE)
