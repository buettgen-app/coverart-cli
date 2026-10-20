# Architecture

`coverart-cli` is a local Python command-line application. It discovers albums,
obtains missing artwork and writes audio tags and/or an album-folder sidecar.
A separate reporting path reads the library and produces a self-contained HTML
file. There is no project-operated server, account system or background service.

## Components and dependencies

| Component | Responsibility |
| --- | --- |
| [`cli.py`](../src/coverart_cli/cli.py) | Parse options, merge configuration, validate the selected mode/platform, construct providers, run processing/reporting and return exit codes. |
| [`config.py`](../src/coverart_cli/config.py) | Read optional TOML defaults and reject unknown or invalidly typed settings. |
| [`core.py`](../src/coverart_cli/core.py) | Discover album targets, verify their identities, coordinate bounded concurrent processing, choose local/provider artwork and collect results/CSV misses. |
| [`providers/`](../src/coverart_cli/providers) | Query Last.fm, iTunes, Deezer and MusicBrainz/Cover Art Archive behind a common `CoverProvider` interface. |
| [`tagging.py`](../src/coverart_cli/tagging.py) | Read tags, validate JPEG/PNG covers with Pillow, inspect existing artwork, and use Mutagen for format-specific tag edits through staged writes. |
| [`filesystem.py`](../src/coverart_cli/filesystem.py) | Provide the common file-operation interface using POSIX operations or the native Windows backend. |
| [`_windows_filesystem.py`](../src/coverart_cli/_windows_filesystem.py) | Implement native handle, reparse-point, ACL, stream and metadata protections on supported local NTFS volumes. |
| [`report.py`](../src/coverart_cli/report.py) and [`templates/report.html`](../src/coverart_cli/templates/report.html) | Scan verified album targets, bound thumbnails, serialize report data safely and render searchable local HTML. |

The CLI imports processing and provider interfaces. Core and report scanning
share target discovery/reopening and tagging helpers; reporting does not call
providers. Tagging delegates platform-dependent file operations to the filesystem
adapter. Runtime dependencies are Mutagen and Pillow; TOML, HTTP, concurrency and
report serialization use Python's standard library. Development/release tools are
separate hash-locked dependencies described in
[dependency updates](dependency-updates.md).

## Processing flow

```text
CLI + TOML + environment
           |
      validated options
           |
 root-anchored album discovery
           |
 verified album + audio metadata
           |
 local sidecar, else enabled providers in order
           |
 bounded JPEG/PNG validation
           |
 audio copy-on-write / sidecar staging
           |
 result summary + optional misses CSV
           |
 optional independent report scan
```

Defaults are overridden in order by user TOML, working-directory TOML, an
explicit config file, the Last.fm environment key and explicit CLI flags. The
CLI remembers which flags were supplied, so an explicitly selected default still
overrides a config value. Configuration files are user-controlled inputs, not a
source of executable plugins.

Discovery records directory identities and relative paths. Processing reopens
each target from the chosen root and checks that it still identifies the intended
directory. Hidden entries, symbolic links and unsupported entries are skipped.
A directly selected root containing conflicting album identities is rejected.
Readable album tags take precedence over optional directory-name fallback.

Each album first checks which requested outputs already meet its thresholds.
A validated local sidecar can supply missing embeds without a provider download.
Otherwise, enabled providers are tried sequentially for that album: Last.fm
(when configured), iTunes, Deezer and MusicBrainz. Different albums can run in a
thread pool; at most three times the worker count are submitted at once.
Provider implementations apply their rate limits, and shared statistics are
updated under a lock.

The shared HTTP helper validates permitted HTTPS hosts/ports, rechecks redirects,
bounds responses and applies a response-read deadline. DNS and connection setup
have transport timeouts rather than that response deadline. Downloaded and local
image bytes pass dimension, decoded-format and size checks before use. Artwork
validation results may be cached within a run.

Audio changes occur on a staged copy, retaining supported file/tag metadata before
atomic replacement. Source and destination identities are checked around file
operations. Sidecars are likewise staged and replaced. Each format has a small
Mutagen adapter for its artwork field; image format determines sidecar extension.
Failures are recorded without treating missing catalog artwork as a processing
error. CSV cells with formula-like prefixes are escaped.

## Reporting and modes

Report-only mode skips provider construction and network fetching. The report
scanner reuses verified target discovery but does not modify audio or covers.
It measures whether an album has a usable sidecar **or** artwork in every supported
track. Processing completion requires every requested output, so these two
counts intentionally answer different questions.

Thumbnails use local sidecars with per-image and shared report budgets. The
report serializes album data to JSON while escaping HTML raw-text delimiters;
the browser template presents that data with safe DOM operations. Reports contain
album/artist names and optional artwork and should be reviewed before sharing.
Report output uses a temporary file and replacement. CSV and HTML output paths
are explicitly selected by the user and are distinct from library write targets.

Dry-run mode still queries providers and validates downloaded artwork; it does
not write tags or sidecars. The CLI rejects combining dry runs with report/CSV
output. Report-only is the local inspection mode when network access is unwanted.

## Boundaries and validation

The filesystem guarantees depend on the supported platform and the selected
root; they do not protect against all actions by another process with the same
trusted identity. Windows additionally checks supported volumes, handles and
directory ACLs. Read the precise assumptions in [SECURITY.md](../SECURITY.md) and
the [security assurance case](security-assurance.md).

Tests are organized by component and by failure boundary in [`tests/`](../tests).
Linux/Python, macOS and native Windows CI exercise their applicable behavior.
Coverage, fuzzing, static analysis and dependency checks provide different kinds
of evidence; none establishes that all defects have been found. See
[repository checks](repository-checks.md) for the enforced scopes.

Packaging uses Hatchling to produce a wheel and source distribution. The
automatic release pipeline handles version metadata, protected integration,
immutable releases, PyPI publication and provenance verification. Its state
transitions and recovery rules are documented separately in
[releases.md](releases.md).
