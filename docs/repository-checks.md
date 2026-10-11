# Repository hygiene and CI gates

The repository keeps source, tests, reproducible screenshot tooling, release
configuration and hash locks. Temporary review notes belong in pull requests;
generated reports, virtual environments, build output and local credentials do
not belong in Git. Release and publishing instructions are in [releases.md](releases.md).

## Privacy checks

Run `python scripts/check_repository.py` before committing. It checks tracked
files for non-example email addresses, personal Unix/Windows home paths,
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
Python versions, macOS metadata preservation, Windows boundary checks, repository
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
