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

Requires Python 3.11 or newer. Upgrade an existing installation with
`pipx upgrade coverart-cli`.

## Quick start

```bash
# 1. Preview the exact library first; this performs no writes
coverart ~/Music --dry-run -v

# 2. Fetch + embed + sidecar (free providers, no key needed)
coverart ~/Music

# Optional: add Last.fm as the first provider
LASTFM_API_KEY=your-key coverart ~/Music

# Just generate the coverage report
coverart ~/Music --report-only --report-html report.html

# Only write cover.jpg files; leave audio tags unchanged
coverart ~/Music --no-embed
```

Run `coverart --help` for the full flag list.

`--dry-run` never writes files and therefore cannot be combined with
`--report-html` or `--missing-csv`; generate those outputs in a separate run.

By default, an album is complete only when it has a usable sidecar **and every
supported audio file has embedded artwork**. If a local sidecar already exists,
it is reused to fill missing embeds without a network request. Symbolic links to
album directories, audio files, or sidecars are ignored, so writes stay inside
the selected library.

Before the first non-dry run, keep a backup of irreplaceable music files. Tag
writes are handled by [Mutagen](https://mutagen.readthedocs.io/), but any bulk
metadata operation deserves a recovery path. Do not move or rename library
directories concurrently with a write run. Root-anchored traversal rejects
symlink swaps, but on POSIX a directory rename by another process does not
revoke a directory descriptor that is already open.

## Config file

Save your defaults so you don't have to repeat flags:

```toml
# ~/.config/coverart-cli/config.toml
lastfm_key      = "your-key"
min_bytes       = 30000
replace_smaller = true
no_musicbrainz  = false
```

Lookup order (later wins): built-in defaults →
`~/.config/coverart-cli/config.toml` → `./coverart.toml` → `--config PATH` →
CLI flags. `LASTFM_API_KEY` overrides the configured key unless
`--lastfm-key` is supplied. Run `coverart ~/Music` afterwards with no repeated
flags. An explicit CLI value always wins, even when it equals the built-in
default. Use `--embed`, `--sidecar`, `--no-dry-run`, `--no-report-html`, or
`--no-missing-csv` to temporarily clear the corresponding configured action.

## Sources

Tried in order until a cover is found:

1. **Last.fm** — `album.getinfo` (needs a free [API key](https://www.last.fm/api/account/create))
2. **iTunes** — Apple Music's public search, no key
3. **Deezer** — public API, no key
4. **MusicBrainz** + **Cover Art Archive** — fallback for niche releases

Album and artist names are sent to the enabled providers over HTTPS. Download
URLs and redirects are restricted to the providers' API and image hosts;
arbitrary hosts and non-HTTPS URLs are rejected.

## Supported formats

MP3 (ID3 APIC), M4A/M4B/MP4 (covr atom), FLAC (Picture block),
Ogg Vorbis / Opus (metadata_block_picture).

Library traversal and mutation require directory-relative, no-follow file APIs
available on Linux and macOS. The CLI rejects unsupported platforms before
contacting any provider, rather than risk following a replaced path component.

Cover inputs are accepted only when Pillow can fully decode them as JPEG or PNG, up to 20 MiB
and within the documented dimension limits. Report thumbnails also use a global size budget so
very large libraries cannot make the self-contained HTML grow without bound.
Malformed, oversized, or unrecognized provider payloads and local sidecars are
ignored instead of being written into tags.

## Common workflows

| Goal | Command |
| --- | --- |
| Preview all changes | `coverart ~/Music --dry-run -v` |
| Upgrade small artwork | `coverart ~/Music --min-bytes 30000 --replace-smaller` |
| Embed only | `coverart ~/Music --no-sidecar` |
| Sidecars only | `coverart ~/Music --no-embed` |
| Disable directory-name fallback | `coverart ~/Music --no-fallback-dirnames` |
| Export misses | `coverart ~/Music --missing-csv missing.csv` |
| Build an HTML report | `coverart ~/Music --report-only --report-html report.html` |

Use `--workers 1` for deterministic serial processing or when a provider is
rate-limiting heavily. MusicBrainz requests are always rate-limited internally.

## Programmatic use

```python
from pathlib import Path
from coverart_cli.core import RunOptions, run
from coverart_cli.providers import ITunesProvider, DeezerProvider

stats = run(
    RunOptions(
        root=Path("~/Music").expanduser(),
        providers=[ITunesProvider(), DeezerProvider()],
    )
)
print(stats.fetched_from, stats.not_found)
```

## Alternatives

| Tool                                                      | When to pick it                                                  |
| --------------------------------------------------------- | ---------------------------------------------------------------- |
| [sacad](https://github.com/desbma/sacad)                  | Best match rate; Rust binary, more sources                       |
| [get-cover-art](https://github.com/regosen/get_cover_art) | Battle-tested Python API                                         |
| [beets](https://beets.io/) `fetchart`                     | Already using beets for everything else                          |
| `coverart-cli` (this)                                     | You want an HTML report plus embed/sidecar dual output            |

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
| `feat!: …` / `BREAKING CHANGE:` | minor before 1.0; major from 1.0 |
| `perf:`, `docs:`, `refactor:` | patch bump (0.3.0 → 0.3.1) |
| `chore:`, `ci:`, `test:`        | hidden in changelog        |

The `Prepare release` workflow uses the repository-scoped `GITHUB_TOKEN` to
open and update one rolling Release PR. Merging that PR creates a mutable draft
release and sends an authenticated repository dispatch to the isolated
`Publish release` workflow. That workflow verifies the source run, exact
commit, package metadata, changelog, and draft state before it creates a
protected annotated version tag and publishes an immutable GitHub Release. It
builds one wheel and source distribution, attaches those exact files to the
release, publishes them to PyPI with OIDC attestations, and cryptographically
verifies the exact local artifacts against PyPI's recorded provenance.

The normal release writes use only the repository-scoped `GITHUB_TOKEN`.
Configure `RELEASE_SETTINGS_TOKEN` as a fine-grained token limited to this
repository with **Administration: read**; it is used only to verify, immediately
before publication, that GitHub Immutable Releases remain enabled. In
`Settings → Actions → General → Workflow permissions`, enable **Allow GitHub
Actions to create and approve pull requests**. GitHub may hold checks on a
Release Please PR until a maintainer selects **Approve workflows to run**.

The PyPI Trusted Publisher must be configured for GitHub owner `buettgen-app`,
repository `coverart-cli`, workflow `release.yml`, and environment `pypi`.
Enable GitHub Immutable Releases for the repository. The active
`refs/tags/v*` ruleset must block tag updates, deletion, and non-fast-forward
changes without bypass actors; publication fails closed if either repository
protection is missing or weakened. That filename is the stable
publish identity even though Release Please itself runs in
`prepare-release.yml`. Do not create release tags or upload distributions by
hand. A failed publish can be retried without introducing a second release
path: the workflow accepts only the exact mutable draft or immutable release,
rebuilds wheel and sdist deterministically from the bound source and requires
their SHA-256 values to match any immutable GitHub assets, uploads only missing
PyPI files, and verifies provenance. The same workflow can be run manually
from `main` for a named draft or a published version that already satisfies
the protected annotated-tag contract; recovery refuses product changes beyond
the explicit release repair. Pull requests and Release PRs
remain subject to branch protection and their configured merge gates.
GitHub Actions changes are gated by the repository's Zizmor security lint;
third-party AI review remains advisory so availability limits cannot block
security updates.

## License

[MIT](LICENSE)
