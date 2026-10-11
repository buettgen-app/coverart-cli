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
GitHub Actions changes are checked with Zizmor. Required status checks must
match the active workflows. If an unavailable third-party reviewer is still
required by a repository rule, a maintainer must update that rule before merging;
the workflows do not bypass repository protections.

