# Dependency security repair — 2026-10-11

GitHub reported 16 open default-branch dependency alerts during push. Its
Dependabot REST endpoint was unavailable (`Forbidden`), so this repair uses a
separate public PyPI advisory scan rather than claiming an exact GitHub alert
readback or dismissal.

`pip-audit` scanned every pinned dependency in all four hash-locked requirement
files using `--no-deps --disable-pip`. This checks the complete recorded package
inventory without executing dependency resolution or installation during audit.
The baseline attestation lock reported 17 advisories across PyJWT 2.13.0 (14)
and urllib3 2.7.0 (3). Build, CI and fuzz locks reported none. Advisory counts
from different feeds need not equal GitHub's alert count.

These packages belong to the Sigstore/PyPI attestation verification toolchain;
the shipped CLI depends on Mutagen and Pillow, and its provider HTTP uses the
standard library. Package presence is confirmed, but this inventory scan does
not prove every advisory's exploit preconditions occur in the release workflow.
We upgrade regardless, without weakening signature/provenance checks.

The attestation lock now selects PyJWT 2.15.1 and urllib3 2.8.0, with explicit
minimum versions in its input. It also replaces yanked securesystemslib 1.5.0
(reported incompatible with sigstore-python by the package index) with 1.5.1.
Regeneration uses CI's uv 0.12.7, preserving canonical platform markers and
dependency extras. A repeat public scan reports zero known vulnerabilities.

Validate the generated lock, hash-enforced installation, verifier imports/CLI,
and repository CI at the final PR head. This does not verify a live PyPI
publication or prove GitHub alerts have closed; after integration, read the
default-branch state and allow GitHub's dependency graph to refresh. No alert
has been manually dismissed or ignored.
