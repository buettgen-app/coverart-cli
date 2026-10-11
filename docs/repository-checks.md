# Repository hygiene and CI gates

The repository keeps source, tests, reproducible screenshot tooling, release
configuration and hash locks. Temporary review notes belong in pull requests;
generated reports, virtual environments, build output and local credentials do
not belong in Git. Release and publishing instructions are in [releases.md](releases.md).

## Privacy checks

Run `python scripts/check_repository.py` after staging and before committing. It
reads Git index blobs, so it checks the snapshot that will actually be committed,
even when the working copy differs or an indexed file has been locally deleted.
It checks for non-example email addresses, personal Unix/Windows home paths,
generated artifacts, environment files, symlinks and textual/EXIF PNG metadata.
Diagnostics include locations and categories, never matched personal values.
Examples use RFC-reserved example domains and the fictional `example-user` path.
GitHub noreply addresses are allowed public maintainer identities; copyright
attribution and public contributor handles are retained.

This is a narrow regression guard, not a comprehensive PII classifier. It does
not recognize arbitrary names, phone numbers, postal addresses, faces or text
inside images. Screenshots still need visual review. Gitleaks separately scans
PR commits and reachable Git history for credentials with fully redacted output.

A file cleanup cannot remove email addresses already stored in Git author or
committer metadata. For future commits, configure the verified GitHub noreply
address from your account's email settings. Historical identity changes require
a separately coordinated history rewrite, including branches, tags, clones and
forks; ordinary PRs leave that history intact.

## Merge gates

`CI gate` succeeds only if every job in `ci.yml` succeeds, including all four
Python versions, macOS metadata preservation, native Windows processing on Python 3.11 and 3.14, handle locking and junction rejection, repository
hygiene, all four canonical dependency locks, wheel smoke testing and reproducible
wheel/sdist builds. Failed, cancelled or skipped dependencies fail this gate.

Configure these exact check names as required in branch protection:

| Check | What it covers |
| --- | --- |
| `CI gate` | All jobs in the main CI workflow |
| `PR Security Baseline` | Immutable Actions references and redacted secret scans |
| `Analyze (python)` | CodeQL analysis |
| `dependency review` | New vulnerable dependencies and license changes |
| `Actions security lint` | Zizmor workflow security analysis |
| `Atheris security boundaries` | Bounded fuzzing of image and report inputs |

Fuzzing runs on every pull request so requiring its check cannot strand
documentation-only changes. Keep strict up-to-date branch checks and resolved
review threads enabled. Use GitHub Actions as the expected check source when
configuring protection; creating a job does not automatically make it a required
repository gate. Existing individual required checks can remain until a
maintainer has verified the aggregate check on a real PR. Dependabot auto-merge
is enabled only when the classic branch protection registers CI gate, PR Security
Baseline and Atheris security boundaries with GitHub Actions as their source.
Until then updates require manual integration; no missing gate is bypassed.

The existing weekly Dependabot and supply-chain workflows remain useful;
additional external review services are not needed to run these checks.

## Component review and gauntlet

Review CLI/configuration, rooted traversal and concurrency, each provider,
image validation and audio writes, report data/DOM, demo tooling, dependency
automation and release/CI boundaries against current primary documentation.
Retain working controls; a new release or recommendation is not by itself a
reason to rewrite a component. Record the source, trigger and expected behavior
for each confirmed finding in the PR.

For each correction, first reproduce the failure with an offline regression
test, apply the fix and rerun the affected tests. Then review the fix again for
boundary failures and run the full gauntlet: Ruff, formatting, Pyrefly, the full
coverage suite, bounded Atheris fuzzing, all canonical locks, dependency audit,
repository hygiene, secret checks and reproducible wheel/sdist builds. Validate
Renovate's schema and its actual dependency extraction; valid JSON does not
guarantee compatible lock headers. GitHub CI supplies the platform matrix,
CodeQL and connected workflow/advisory checks unavailable locally.

Stop when the selected checks pass and no confirmed actionable code findings
remain after re-review. Document unavailable checks and external setup needs
separately; do not treat them as passing or claim that testing proves the
absence of all vulnerabilities. Review results belong in PRs or external
reports rather than dated snapshots in the repository.

The Linux coverage gate omits the Windows-only ctypes backend. The native Windows
jobs measure that backend separately with branch coverage and the same 78% minimum;
they exercise real FFmpeg-generated MP3/M4A/FLAC/Vorbis/Opus files, installed wheel
entry points, destination ACL and stream retention, file timestamps, junctions,
ancestor locks, and write conflicts through the final replacement.
