# Release and publishing guide

[Back to the README](../README.md#development)


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

A push to `main` starts the complete automatic release sequence. The
`Prepare release` workflow uses the repository-scoped `GITHUB_TOKEN` to open
or update one rolling Release PR and explicitly dispatches
`Complete automatic release` from main. The completion workflow then checks
that it belongs to Release Please, is based on current `main`, and changes
only the four release metadata files. It accepts only a consistent version
increase; dependencies, build configuration and Python code must be unchanged.

GitHub places bot-created PR runs behind workflow approval and suppresses
ordinary push triggers from `GITHUB_TOKEN` merges. After validating the exact
metadata-only PR, the completion workflow approves its existing CI, CodeQL,
fuzzing, dependency-review/Actions-security and secret-scan runs in the PR
context. This satisfies required checks on the test-merge commit too. It
explicitly dispatches only missing workflows as a fallback and prefers any PR
runs that subsequently appear. It waits for successful runs on that commit,
checks both source commits again and merges
with an expected-head lease using the normal protected rebase endpoint. Failed,
skipped, stale or timed-out runs stop publication; protection is never bypassed.
If another change reaches `main`, its preparation run updates the release PR and
starts a new attempt. Publication applies to releasable Conventional Commits;
changes that do not require a new version do not force an empty release.
After successful cryptographic provenance verification, a separate job explicitly
dispatches preparation on main to pick up releasable main
commits that arrived while the previous draft blocked preparation. This dispatch does not depend on a token-generated publication `workflow_run` event. With no
unreleased changes, this creates neither a PR nor another publication.

After the merge, an explicit main-only preparation dispatch creates the mutable
draft and sends an authenticated repository dispatch to the isolated
`Publish release` workflow. The publish-only flag prevents a duplicate release
PR while the draft is being published. The publisher verifies the source run,
exact release commit (including its ancestry in the trusted main preparation
run), package metadata, changelog and draft state before it creates a
protected annotated version tag and publishes an immutable GitHub Release. It
builds one wheel and source distribution, attaches those exact files to the
release, publishes them to PyPI with OIDC attestations and cryptographically
verifies the exact local artifacts against PyPI's recorded provenance.

For recovery, run `Complete automatic release` manually from `main` if the
release PR is still open. If it was already merged but publication did not start,
run `Prepare release` from `main` with `publish_only` enabled and `release_sha`
set to its merge commit. Automatic draft recovery passes the draft's exact
`source_sha`, so later product commits do not alter the version being published.
Release tests install the same FFmpeg oracle as Linux CI so audio integration
coverage cannot disappear in the publication environment. A reviewed change to
`release.yml` on protected main may repair the publisher while retaining the
exact draft source; other workflow differences still stop this recovery. Both
finalization checks use complete Git trees to require a regular-file publisher
mode and compare its blob with the running definition. A symlink (even if the
Contents API follows it), incomplete tree or later publisher change stops binding
or publication too.
Both preparation and the publisher verify automatic draft recovery against the
merged Release Please PR's version, author, branch, repository and actual merge
SHA. A rejected or mismatched draft fails closed on subsequent attempts too. For an existing
draft or immutable version, use `Publish release` with its tag as described below.

The normal release writes use only the repository-scoped `GITHUB_TOKEN`.
Configure `RELEASE_SETTINGS_TOKEN` as a fine-grained token limited to this
repository with **Administration: read**; it is used only to verify, immediately
before publication, that GitHub Immutable Releases remain enabled. In
`Settings → Actions → General → Workflow permissions`, enable **Allow GitHub
Actions to create and approve pull requests**. Release PR workflow approvals are granted automatically only after the
metadata-only boundary passes; missing runs use explicit workflow dispatches. Any configured environment approval still
applies to publication.

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
from a failed publication's Actions page using **Re-run failed jobs** once a
temporary visibility failure has cleared; matching existing files are retained
and no second upload is attempted. File and attestation lookups each allow up to
18 attempts spaced ten seconds apart to tolerate delayed CDN visibility, with
15-second request timeouts and an enclosing 30-minute job limit. Exhaustion or
mismatched provenance remains a failure. Alternatively, run the same workflow
from `main` for a named draft or a published version that already satisfies
the protected annotated-tag contract; recovery refuses product changes beyond
the explicit release repair. Pull requests and Release PRs
remain subject to branch protection and their configured merge gates.
GitHub Actions changes are checked with Zizmor. Required status checks must
match the active workflows. If an unavailable third-party reviewer is still
required by a repository rule, a maintainer must update that rule before merging;
the workflows do not bypass repository protections.
