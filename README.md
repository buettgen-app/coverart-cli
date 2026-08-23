# coverart-cli

> Fill the missing covers in your music library — embed and sidecar in one pass.

<p align="center">
  <img src="https://raw.githubusercontent.com/buettgen-app/coverart-cli/main/docs/screenshots/report-dark.png" alt="HTML coverage report" width="100%" />
</p>

[![CI](https://github.com/buettgen-app/coverart-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/buettgen-app/coverart-cli/actions/workflows/ci.yml)
[![CodeQL](https://github.com/buettgen-app/coverart-cli/actions/workflows/codeql.yml/badge.svg)](https://github.com/buettgen-app/coverart-cli/actions/workflows/codeql.yml)
[![CodeRabbit reviews](https://img.shields.io/coderabbit/prs/github/buettgen-app/coverart-cli?labelColor=171717&color=FF570A&label=CodeRabbit+reviews)](https://coderabbit.ai)
[![PyPI](https://img.shields.io/pypi/v/coverart-cli.svg?color=blue)](https://pypi.org/project/coverart-cli/)
[![PyPI downloads](https://static.pepy.tech/badge/coverart-cli/month)](https://pypi.org/project/coverart-cli/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## What it does

Most cover-art tools only embed _or_ only sidecar. That breaks across players —
Subsonic apps (Amperfy, Symfonium) read tags, Plex / Jellyfin prefer `cover.jpg`,
Apple Music wants embedded. `coverart-cli` does both in one pass and ships an
HTML coverage report so you can see what's still missing.

## Install

```bash
pipx install coverart-cli
```

## Use

```bash
# Fetch + embed + sidecar (free providers — no key needed)
coverart ~/Music

# Add Last.fm too (much higher hit rate)
LASTFM_API_KEY=xxx coverart ~/Music

# Just generate the coverage report
coverart ~/Music --report-only --report-html report.html

# See what would happen, change nothing
coverart ~/Music --dry-run -v
```

Run `coverart --help` for the full flag list.

## Config file

Save your defaults so you don't have to repeat flags:

```toml
# ~/.config/coverart-cli/config.toml
lastfm_key      = "your-key"
min_bytes       = 30000
replace_smaller = true
no_musicbrainz  = false
```

Lookup order (later wins): built-in → `~/.config/coverart-cli/config.toml` →
`./coverart.toml` → `--config PATH` → CLI flags → environment variables. Run
`coverart ~/Music` afterwards with no flags.

## Sources

Tried in order until a cover is found:

1. **Last.fm** — `album.getinfo` (needs a free [API key](https://www.last.fm/api/account/create))
2. **iTunes** — Apple Music's public search, no key
3. **Deezer** — public API, no key
4. **MusicBrainz** + **Cover Art Archive** — fallback for niche releases

## Supported formats

MP3 (ID3 APIC), M4A/M4B/MP4 (covr atom), FLAC (Picture block),
Ogg Vorbis / Opus (metadata_block_picture).

## Programmatic use

```python
from pathlib import Path
from coverart_cli.core import RunOptions, run
from coverart_cli.providers import ITunesProvider, DeezerProvider

stats = run(RunOptions(
    root=Path("~/Music").expanduser(),
    providers=[ITunesProvider(), DeezerProvider()],
))
print(stats.fetched_from, stats.not_found)
```

## Alternatives

| Tool                                                      | When to pick it                                                  |
| --------------------------------------------------------- | ---------------------------------------------------------------- |
| [sacad](https://github.com/desbma/sacad)                  | Best match rate; Rust binary, more sources                       |
| [get-cover-art](https://github.com/regosen/get_cover_art) | Battle-tested Python API                                         |
| [beets](https://beets.io/) `fetchart`                     | Already using beets for everything else                          |
| `coverart-cli` (this)                                     | You want the HTML report + embed/sidecar dual-output in ~700 LOC |

## Development

```bash
git clone https://github.com/buettgen-app/coverart-cli && cd coverart-cli
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ruff check . && pyrefly check && pytest
```

## Releases

Releases are prepared by [release-please](https://github.com/googleapis/release-please-action)
and published from an immutable Git tag via PyPI Trusted Publishing.
Commits to `main` follow [Conventional Commits](https://www.conventionalcommits.org/):

| Commit prefix                   | Effect on next release     |
| ------------------------------- | -------------------------- |
| `feat: …`                       | minor bump (0.3.0 → 0.4.0) |
| `fix: …`                        | patch bump (0.3.0 → 0.3.1) |
| `feat!: …` / `BREAKING CHANGE:` | major bump (0.3.0 → 1.0.0) |
| `docs:`, `refactor:`, `perf:`   | changelog entry, no bump   |
| `chore:`, `ci:`, `test:`        | hidden in changelog        |

The `Prepare release` workflow uses a short-lived GitHub App token to open and
update one rolling Release PR. Merging that PR creates the version tag and
publishes the GitHub Release. Its `published` event triggers the isolated
`Publish release` workflow, which verifies that the tag belongs to `main` and
matches the package metadata and changelog. It builds one wheel and source
distribution, attaches those exact files to the GitHub Release, and publishes
them to PyPI with OIDC attestations.

Configure a repository-scoped GitHub App with `Contents: read and write` and
`Pull requests: read and write`, then set its App ID as the repository variable
`RELEASE_APP_ID` and its private key as the repository secret
`RELEASE_APP_PRIVATE_KEY`. The repository-wide setting that lets
`GITHUB_TOKEN` create or approve pull requests can remain disabled.

The PyPI Trusted Publisher must be configured for GitHub owner `buettgen-app`,
repository `coverart-cli`, workflow `release.yml`, and environment `pypi`. That filename is the stable
publish identity even though Release Please itself runs in
`prepare-release.yml`. Do not create release tags or upload distributions by
hand. A failed publish can be rerun from the same GitHub Actions run without
introducing a second release path. Historical releases can be recovered by
manually running the same workflow from `main`; it accepts only an existing
published release tag and applies every normal validation and test gate. Pull
requests, including Release PRs and dependency updates, require an explicit
merge after branch protection passes.
GitHub Actions changes are gated by the repository's Zizmor security lint;
third-party AI review remains advisory so availability limits cannot block
security updates.

## License

[MIT](LICENSE)
