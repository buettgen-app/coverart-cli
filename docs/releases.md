# Release and publishing guide

[Back to the README](../README.md#development)


## Verify a published release

Verification checks who published an artifact and whether its bytes changed;
it does not establish that the software is free of vulnerabilities. Use a
GitHub CLI that provides `gh release verify` and `gh release verify-asset`,
Python 3.15, Git, curl and jq. The following Bash example verifies **both**
the wheel and the uploaded source distribution for a selected release.
Review the release/tag you intend to trust before running tools from its checkout.

```bash
set -euo pipefail
release_tag=v0.7.3
release_version="${release_tag#v}"
release_repo=buettgen-app/coverart-cli
verification_dir="$(mktemp -d)"

gh release verify "$release_tag" --repo "$release_repo"
gh release download "$release_tag" --repo "$release_repo" \
  --pattern '*.whl' --pattern '*.tar.gz' --dir "$verification_dir"

git clone "https://github.com/$release_repo.git" "$verification_dir/source"
git -C "$verification_dir/source" checkout --detach "$release_tag"
git -C "$verification_dir/source" rev-parse HEAD
python3.15 -m venv "$verification_dir/verifier"
"$verification_dir/verifier/bin/python" -m pip install \
  --only-binary=:all: --require-hashes \
  -r "$verification_dir/source/requirements-attestation.txt"

for filename in "coverart_cli-$release_version-py3-none-any.whl" \
                "coverart_cli-$release_version.tar.gz"; do
  artifact="$verification_dir/$filename"
  provenance="$verification_dir/$filename.provenance.json"
  gh release verify-asset "$release_tag" "$artifact" --repo "$release_repo"
  curl --fail --silent --show-error --location --proto '=https' \
    --connect-timeout 10 --max-time 60 \
    --header 'Accept: application/vnd.pypi.integrity.v1+json' \
    "https://pypi.org/integrity/coverart-cli/$release_version/$filename/provenance" \
    --output "$provenance"
  jq -e '
    .version == 1 and (.attestation_bundles | length == 1) and
    (.attestation_bundles[0].publisher |
      .kind == "GitHub" and .repository == "buettgen-app/coverart-cli" and
      .workflow == "release.yml" and .environment == "pypi")
  ' "$provenance" > /dev/null
  "$verification_dir/verifier/bin/pypi-attestations" verify pypi \
    --repository "https://github.com/$release_repo" \
    --provenance-file "$provenance" "$artifact"
done
```

The first checks bind the local files to GitHub's immutable release. The jq
check requires the expected PyPI Trusted Publisher metadata. The pinned
`pypi-attestations` verifier then checks the actual local artifact's digest,
attestation signature, signing certificate and repository/workflow identity
using Sigstore's production trust configuration. Its trust-root refresh needs
network access; a failed refresh or unavailable check is a failed verification,
not permission to skip signature checks. The environment name above is checked
in PyPI publisher metadata; it is not an additional identity option of the CLI.
A protected annotated Git tag is not itself a cryptographically signed Git tag.
Our signed artifact provenance is a separate control. No long-lived project
signing private key needs to be downloaded or shared with users.

Use the uploaded `coverart_cli-*.tar.gz`, not GitHub's automatically generated
“Source code” archive: GitHub's asset-verification command does not cover those
automatically generated archives. Stop on a missing signature, unexpected
identity or digest mismatch. Do not install an artifact whose verification
failed. For details, see the official [GitHub release verification guide](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/verify-release-integrity)
and [PyPI attestation verifier documentation](https://pypi.org/project/pypi-attestations/).
The CLI is an experimental upstream interface, so the example deliberately uses
the release's hash-locked verifier rather than an unbounded latest version.

## Reproduce wheel and source-distribution bytes

Continue in the same shell after verification. Build the clean, detached tag
checkout, with output and the virtual environment outside it. The source tree
must be unchanged; packaging a locally edited README, an extra untracked file,
or a different source commit is not a reproduction of the release.

```bash
python3.15 -m venv "$verification_dir/builder"
"$verification_dir/builder/bin/python" -m pip install --require-hashes \
  -r "$verification_dir/source/requirements-build.txt"
"$verification_dir/builder/bin/python" -c \
  'import platform, zlib; print(platform.platform(), platform.python_version(), zlib.ZLIB_RUNTIME_VERSION)'
(
  cd "$verification_dir/source"
  SOURCE_DATE_EPOCH=1580601600 "$verification_dir/builder/bin/python" \
    -m build --no-isolation --outdir "$verification_dir/rebuilt"
)
"$verification_dir/builder/bin/python" - "$verification_dir" <<'PYCODE'
import hashlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
rebuilt = sorted((root / "rebuilt").iterdir())
if len(rebuilt) != 2:
    raise SystemExit("expected exactly one wheel and one source distribution")
for artifact in rebuilt:
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    expected = hashlib.sha256((root / artifact.name).read_bytes()).hexdigest()
    if digest != expected:
        raise SystemExit(f"reproduction failed: {artifact.name}")
    print(artifact.name, digest)
PYCODE
```

The publishing workflow specifies CPython 3.15, the checked-in build lock and
`SOURCE_DATE_EPOCH=1580601600`. Record the exact interpreter patch/build,
compression-library version, operating system, source SHA and lock alongside
the result. Use the publisher run's toolchain when investigating a mismatch:
different Python/compression versions can produce different gzip bytes even
when the tar members are identical. Equal unpacked files alone do not satisfy
bit-for-bit source-distribution reproducibility. A fresh environment or another
party reproducing both published hashes is stronger evidence than simply
building twice in one existing environment.

For release evidence, retain the source SHA, immutable release URL, two digests,
verification/rebuild toolchain and results, and the linked CI, CodeQL and Fuzz
runs that cover the candidate before publication. The release workflow also
verifies PyPI's exact non-yanked artifact set. A current green badge for a newer
commit is not evidence for an older release. Keep unresolved findings and
unavailable checks explicit; Atheris's Python input-boundary tests do not by
themselves demonstrate native-library memory-sanitizer coverage or human review.

## Maintainer publishing and recovery

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
