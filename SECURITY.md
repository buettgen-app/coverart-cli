# Security Policy

## Reporting a vulnerability

If you discover a security issue in `coverart-cli`, please **do not file a public issue**.
Instead, use GitHub's private vulnerability reporting:

- <https://github.com/buettgen-app/coverart-cli/security/advisories/new>

The acknowledgement target is 7 days. Include the affected version/platform,
reproduction steps, expected impact and a minimal synthetic sample where possible.
Do not attach a private music library, real API key or unrelated personal data.
If acknowledgement is overdue, follow up in the same private report. A public
issue asking the maintainer to check private reports may omit all vulnerability
details.

The application runs locally with the operator's privileges. Security concerns
include unintended file access or modification, malicious media or metadata,
unintended network requests, credential disclosure, unsafe generated reports,
resource exhaustion and release supply-chain compromise. There is no project
production service whose isolation can protect a user's local machine.

### Response and disclosure

The maintainer handling the private report is responsible for the following
steps, with a named owner recorded in the report:

1. Acknowledge receipt, agree on a private communication channel and identify
   affected/supported versions. Ask whether the reporter wants attribution.
2. Reproduce with synthetic data, assess impact, prerequisites, severity and
   exploitability, and record the assessment. An unreproduced report stays open
   for investigation; lack of an accessible scan does not establish safety.
3. Agree on next actions and a disclosure plan with the reporter. Prioritize
   critical issues promptly, give progress updates when the assessment or plan
   changes, and reassess if exploitation is reported. Track publicly known
   medium-or-higher vulnerabilities so they do not remain unpatched beyond
   60 days; this is a remediation policy, not a claim about historical results.
4. Prepare the correction privately when disclosure would expose users. Add an
   appropriate regression, review the change and run the applicable platform,
   security and release checks. Coordinate upstream dependency fixes if needed;
   a rejected exploitability claim needs a documented technical reason.
5. Publish the fix through the existing protected release process. Publish an
   advisory with affected/fixed versions, impact, mitigations and available
   CVE/GHSA identifiers; include applicable identifiers in release notes.
   Credit consenting reporters and collaborators, respecting anonymity.
6. Verify the published artifacts and link the fix, tests, release and advisory
   in the report before closure. Record remaining work and update security
   documentation if the trust boundary or supported behavior changed.

Use [GitHub repository security advisories](https://docs.github.com/en/code-security/concepts/vulnerability-reporting-and-management/repository-security-advisories)
for private coordination and public disclosure. Publication timing must account
for user exposure and reporter coordination; an acknowledgement is not a
guarantee of a fix by a particular date.

Response timing, reporter credit, open findings and remediation history must be
checked against actual authorized records. This policy does not attest that no
private reports or unresolved vulnerabilities exist.

## Security requirements and operating assumptions

The [security assurance case](docs/security-assurance.md) maps the requirements
to implementation, tests and limitations. It is engineering documentation
pending human security review, not a badge or an independent audit.

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

Choose a trusted working directory and review all configuration files:
`coverart.toml` in the current directory can select write behavior and report
destinations. Config files, the Python runtime, installed plugins/custom Python
providers and an explicitly supplied report template are trusted inputs.
The HTML and CSV output paths are operator-selected destinations; they do not
have the music-library writer's handle/ACL boundary. Use a private output
directory that untrusted users cannot modify.

Album/artist names are sent to enabled providers. Generated reports, CSV files
and logs can contain library names, album identities, paths and artwork.
They are not anonymous exports. Inspect them before sharing; `--report-only`
avoids provider requests, and `--no-thumbs` omits report artwork.

### API credentials

Last.fm is optional. Keep its key out of shared configuration, command history
and committed files. A separate TOML file containing only `lastfm_key` can be
supplied with `--config /path/to/private-secrets.toml`; other defaults continue
to come from the normal configuration files. Restrict that file and its parent
directory to your account (for example, owner-only permissions on POSIX or an
appropriate Windows ACL). The CLI does not set or audit those permissions.

The key can be replaced in that file without changing code. `LASTFM_API_KEY`
overrides configuration, and an explicit `--lastfm-key` overrides both; clear
stale overrides when rotating a key. Environment variables remain visible to
processes with sufficient local privileges. The tool redacts query strings,
fragments and URL user information in its provider URL logging, but this is
not a guarantee that arbitrary logs or external tooling contain no secrets.

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
