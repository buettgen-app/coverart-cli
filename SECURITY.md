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
Native Windows writes additionally require the destination directory owner and
namespace/policy writers to be the effective user, SYSTEM or local Administrators.
The CLI refuses broader or unrecognized write grants before staging and checks
again before committing. This excludes lower-trust directory writers from racing
destination metadata checks; concurrent namespace or ACL changes by these trusted
actors remain outside the boundary. Read-only operations do not require this guard.

## Supported versions

Only the latest minor release is supported with fixes.

## Dependencies

Runtime dependencies are `mutagen` for audio metadata and Pillow for bounded
JPEG/PNG decoding. Build, CI, fuzzing, and attestation tools use hash-locked
requirements files. Dependency vulnerabilities are tracked via GitHub's Dependabot.
CI regenerates every build, development, fuzzing and attestation lock with the
pinned uv version and fails if the checked-in files differ.

Provider requests and redirects permit only each provider's configured HTTPS
hosts on the standard HTTPS port. HTTP headers and bodies share a deadline
enforced at every underlying socket read, including chunk framing; responses
also have a byte cap. DNS and connection establishment are outside that response
deadline and retain the transport's connection-timeout behavior. Oversized Ogg picture blocks
are rejected before base64 allocation, and oversized covers bypass cache hashing.

Test coverage is measured separately for shared code and the native Windows
backend, with required line/branch gates and downloadable reports. Coverage
is evidence of executed paths, not certification of security; see the
[coverage policy](docs/repository-checks.md#test-coverage).

## Repository privacy

Tracked files are checked for non-example contact addresses, personal home paths,
local artifacts and screenshot metadata. Secret scanning uses fully redacted
Gitleaks output for PR commits and reachable Git history. These are focused
regression checks; they do not certify that arbitrary content contains no PII.
See [repository hygiene and CI gates](docs/repository-checks.md) for coverage,
synthetic examples, and the distinction between file content and historical
Git author/committer identities.

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
  publishing token or private GitHub App key is stored. The repository-scoped
  `RELEASE_SETTINGS_TOKEN` has Administration(read) access only and verifies
  immutable-release settings and tag protection. Release Please dispatches the
  separately validated `release.yml` workflow after creating a mutable draft;
  the publication workflow verifies and finalizes it before PyPI publishing.
