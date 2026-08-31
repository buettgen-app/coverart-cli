# Security Policy

## Reporting a vulnerability

If you discover a security issue in `coverart-cli`, please **do not file a public issue**.
Instead, use GitHub's private vulnerability reporting:

- <https://github.com/buettgen-app/coverart-cli/security/advisories/new>

You will receive an acknowledgement within 7 days. The maintainer keeps no
production deployment, so the realistic scope of a security issue here is
limited to: arbitrary file write under the user's music root, network calls
to unintended hosts, or denial of service via crafted audio files.

The filesystem boundary assumes that no other process with the same user
permissions concurrently moves or renames the selected library while a write
run is active. The CLI authorizes directory objects reached through
root-anchored, no-follow traversal; POSIX renames do not revoke already-open
directory descriptors. Symlink and hard-link aliases are handled defensively,
but same-user concurrent filesystem reorganization is outside the threat model.

## Supported versions

Only the latest minor release is supported with fixes.

## Dependencies

This project pins the minimum version of `mutagen` and otherwise relies on the
Python standard library. Dependency vulnerabilities are tracked via GitHub's
Dependabot.

## Supply chain controls

Security and supply chain integrity are release blockers for this repository.

- Repository Actions default token permissions are read-only. Workflows opt in
  to write or OIDC permissions only at the job that needs them.
- Dependency Review runs on pull requests and fails when new runtime,
  development, or unknown-scope dependencies introduce moderate-or-higher
  vulnerabilities.
- OpenSSF Scorecard runs on `main`, on a weekly schedule, and on demand. Results
  are uploaded to code scanning and published to Scorecard's public API.
- Every third-party GitHub Action is pinned to a full commit SHA. Zizmor audits
  the workflows as a required pull-request check.
- PyPI publishing uses Trusted Publishing with build attestations. Release jobs
  publish only after Release Please creates a GitHub Release/tag, the tagged
  source passes Ruff, Pyrefly, and the full test suite on all supported Python
  versions, and the built wheel passes a clean installation smoke test.
- PyPI trust is bound to `.github/workflows/release.yml` and the protected
  `pypi` environment; the workflow filename is part of the publisher identity.
- Verified low-risk Dependabot updates use native auto-merge only after branch
  protection passes; major and production minor updates stay manual. Release
  preparation uses the repository-scoped workflow `GITHUB_TOKEN`; no
  long-lived personal token or private GitHub App key is stored. Release Please
  dispatches the separately validated `release.yml` workflow only after it has
  created a published release.
