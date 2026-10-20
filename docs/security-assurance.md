# Security assurance case

This document explains the intended security properties of `coverart-cli`,
the implementation supporting them and the limits of that evidence.
It supports the OpenSSF `documentation_security`, `implement_secure_design`,
`assurance_case` and `input_validation` criteria.

**Review status:** engineering documentation pending human security review.
No human reviewer, completed review date, finding-free result or badge attainment
is asserted here. AI-assisted analysis and automated tests do not establish the
human review required by the [Gold security-review criterion](https://www.bestpractices.dev/en/criteria/2?details=true).
Record the reviewed commit, reviewer, date, findings and disposition in the
review PR or linked report; see
[the review work item](https://github.com/buettgen-app/coverart-cli/issues/101).

## Scope and trust model

The product is a local Python CLI and Python API that reads a music library,
contacts artwork providers and optionally writes audio tags, image sidecars,
HTML and CSV reports. It runs with the operator's account permissions.

Assets are the original audio bytes and metadata, filesystem namespace and
security metadata, Last.fm credentials, private library information, available
CPU/memory/storage and the authenticity of installed releases.

Potential adversaries include suppliers of crafted audio, images, tags or
provider responses; attackers controlling an unexpected URL or redirect;
lower-trust local filesystem writers; and contributors or dependencies trying
to alter the build/release path. Network providers can observe the album and
artist queries sent to them even when TLS works correctly.

The trusted computing base includes the operator's CLI/configuration choices,
current working directory, installed Python/OS and CA store, Mutagen, Pillow
and its native codecs, and any custom Python provider/template supplied by the
caller. TLS proxy and CA configuration inherited from the environment are also
operator-controlled. The CLI is not a sandbox for executing untrusted Python.
Repository maintainers, authorized release infrastructure and hosting services
are separate operational trust boundaries, not properties proved by unit tests.

## Requirements, arguments and evidence

The links identify implementation and regression evidence; they do not assert
that a particular CI run passed. Reviewers must bind results to the same commit
and inspect skipped/failed tests and findings.

| Requirement and design argument | Implementation | Regression evidence and limit |
| --- | --- | --- |
| R1: Library traversal and media writes must not follow substituted symlinks or write through unintended file aliases. Reopen directories relative to verified roots and compare identities; deny unsupported paths instead of falling back to unsafe writes. | [`core.py`](../src/coverart_cli/core.py): `_find_album_targets`, `_open_album_target`; [`tagging.py`](../src/coverart_cli/tagging.py): `_open_verified_file`, `embed_cover`, `write_sidecar`; [`filesystem.py`](../src/coverart_cli/filesystem.py). | [`test_integration.py`](../tests/test_integration.py): `test_replaced_intermediate_directory_cannot_escape_library`, `test_audio_symlink_swap_during_fetch_is_not_followed`, `test_audio_hardlink_outside_library_is_not_modified`; [`test_tagging.py`](../tests/test_tagging.py). POSIX descriptors do not prevent a trusted same-user process from renaming a directory after verification. |
| R2: An unsuccessful embed must preserve the original destination, and successful writes must retain supported audio metadata and filesystem policy. Stage a copy, validate identities and replace only after modification succeeds. | [`tagging.py`](../src/coverart_cli/tagging.py): `embed_cover`, `_copy_audio_file`, `_darwin_copy_audio_file`; [`_windows_filesystem.py`](../src/coverart_cli/_windows_filesystem.py): security metadata, streams and handle-bound replacement. | [`test_tagging.py`](../tests/test_tagging.py): `test_real_audio_metadata_and_embedding_roundtrip`, `test_embed_cover_rejects_same_inode_change_after_copy`; [`test_windows.py`](../tests/test_windows.py): `test_integrity_label_survives_audio_replacement`, `test_unreadable_sacl_policy_keeps_original_and_creates_no_stage`. Tests include FFmpeg stream comparisons, but this is not a power-loss durability or backup guarantee. |
| R3: Native Windows writes must reject lower-trust directory writers, unsupported roots and policies that cannot be retained. Use native handles and check directory ownership/write grants before staging and commit. | [`_windows_filesystem.py`](../src/coverart_cli/_windows_filesystem.py): `_assert_trusted_write_directory`, `security_policy_access`, `security_descriptor`, `validate_root`, `_pin`, `replace`. | [`test_windows.py`](../tests/test_windows.py): `test_shared_write_directory_is_refused_before_staging`, `test_new_directory_write_grant_before_commit_retains_destination`, `test_destination_in_place_writes_are_blocked_at_native_commit`, `test_token_restoration_failure_closes_stage_and_retains_source`. Actual Windows execution is required; Linux mocks do not prove native behavior. |
| R4: Built-in providers must use authenticated HTTPS to configured hosts on port 443, including redirects, and bound individual responses. Validate before request/redirect, retain default certificate verification and limit parsing reads/retries. | [`providers/base.py`](../src/coverart_cli/providers/base.py): `_is_allowed_https_url`, `_RestrictedRedirectHandler`, `_DeadlineHTTPSHandler`, `_DeadlineResponse`, `_http_get`; provider-specific `allowed_hosts`. | [`test_providers.py`](../tests/test_providers.py): URL/redirect/size tests; [`test_security_boundaries.py`](../tests/test_security_boundaries.py): `test_https_deadline_handler_keeps_certificate_and_hostname_verification`, `test_real_http_parser_cannot_hide_trickle_reads_inside_one_call`, `test_response_length_header_cannot_override_actual_byte_budget`. Host allowlisting does not pin DNS addresses or make an allowed provider trustworthy. |
| R5: Artwork must pass bounded JPEG/PNG validation before embedding, sidecar use or thumbnails. Content and dimensions, not filename/claimed MIME alone, determine acceptance. | [`tagging.py`](../src/coverart_cli/tagging.py): `validate_cover_bytes`, `_decode_picture_block`, `CoverValidationCache`; [`report.py`](../src/coverart_cli/report.py): `_make_data_uri`, `scan_library`. | [`test_tagging.py`](../tests/test_tagging.py): malformed/truncated/decompression tests; [`test_security_boundaries.py`](../tests/test_security_boundaries.py): oversized Ogg/cache tests; [`test_report.py`](../tests/test_report.py): thumbnail budget tests; [`fuzz_images.py`](../fuzz/fuzz_images.py). The native image decoders remain dependencies, not isolated processes. |
| R6: Generated report data must stay data rather than executable HTML or spreadsheet formulas. Escape HTML script boundaries before inserting JSON, use text DOM APIs and neutralize dangerous CSV cell prefixes. | [`report.py`](../src/coverart_cli/report.py): `build_report`; [`report.html`](../src/coverart_cli/templates/report.html): `textContent` and generated image URIs; [`core.py`](../src/coverart_cli/core.py): `_write_missing_csv`. | [`test_report.py`](../tests/test_report.py): `test_report_payload_cannot_enter_html_script_escape_states`; [`test_integration.py`](../tests/test_integration.py): `test_missing_csv_neutralizes_spreadsheet_formulas`; [`fuzz_report.py`](../fuzz/fuzz_report.py). Custom templates and caller-supplied Python report objects are trusted; output files contain private library information. |
| R7: Provider diagnostics must not expose URL credentials, query strings or fragments; configuration must permit separate, replaceable credentials. | [`providers/base.py`](../src/coverart_cli/providers/base.py): `_safe_url_for_log`, exception logging; [`config.py`](../src/coverart_cli/config.py): `load_config`; [`cli.py`](../src/coverart_cli/cli.py): configuration/environment precedence. | [`test_providers.py`](../tests/test_providers.py): `test_network_error_log_does_not_leak_query_credentials`, `test_safe_url_for_log_strips_userinfo`; [`test_config.py`](../tests/test_config.py) and [`test_cli.py`](../tests/test_cli.py). Local file permissions and arbitrary third-party logs are outside this redaction guarantee. |
| R8: Published distributions must be bound to the intended reviewed source and publisher, with immutable artifacts verified before the release is considered complete. | [`release.yml`](../.github/workflows/release.yml), [`automatic-release.yml`](../.github/workflows/automatic-release.yml), [`complete_release.py`](../scripts/complete_release.py); [release guide](releases.md). | [`test_release_workflow.py`](../tests/test_release_workflow.py), [`test_complete_release.py`](../tests/test_complete_release.py) plus actual release runs, protection readbacks, hashes and cryptographic verification. Workflow source alone does not prove current account protection, deployment settings or successful publication. |

These controls apply fail-safe defaults, mediation at filesystem/network
boundaries, small explicit allowlists and separation of build, verification and
publication privileges. Copy-on-write limits the effect of parser/write failure.
Input bounds, supported-format restrictions and platform-specific checks add
defense in depth; none makes arbitrary parsing or concurrent filesystem activity
universally safe.

## Resource and platform limits

- HTTP responses default to a 20 MiB cap. Socket reads during header/body
  parsing have deadlines; retries make total request processing longer than
  one timeout. DNS and connection establishment retain the transport's
  connection-timeout behavior rather than a single end-to-end wall-clock bound.
- Covers are limited to 20 MiB, 4,096 pixels per dimension and 16,777,216 pixels.
  Encoded Ogg picture sizes are checked before base64 allocation. Report
  thumbnails have per-image and aggregate byte budgets.
- These limits are not a bound on total library size, all audio metadata parsing,
  disk usage or complete scan duration. Audio parsing uses Mutagen; image parsing
  uses Pillow/native codecs. Keep dependencies current and process unfamiliar
  libraries with backups and appropriate operating-system isolation if needed.
- POSIX same-user or privileged concurrent renames/reorganization remain outside
  the stable-library assumption. A directory descriptor authorizes an object,
  not a promise that its pathname can never change.
- Windows support requires Windows 10 1709+ and local NTFS. Reparse boundaries,
  network/UNC paths, SUBST mappings and unsupported file/security attributes are
  refused. Audio writes reject EFS encryption and multiple hard links. The
  effective user, SYSTEM and local Administrators are trusted directory writers.
- Windows security-policy copying requires an already assigned
  `SeSecurityPrivilege`. It is enabled on a temporary private thread token and
  restored afterwards; the CLI does not grant it or elevate the process. If
  complete security policy cannot be retained, the write fails closed.
- HTML/CSV destinations use ordinary operator-selected paths, not the
  music-library handle/ACL protocol. Keep their parent directories private.
  Configuration files and the current working directory are trusted: a local
  `coverart.toml` can change actions and output paths.
- Reports and logs may identify library entries. Report-only mode avoids
  provider queries, but does not anonymize outputs. Dry-run still contacts
  providers; it is a write preview, not an offline privacy mode.

## Cryptography and credentials

The product delegates TLS to Python's `ssl`/OpenSSL implementation through
`ssl.create_default_context()`, preserving certificate and hostname checks.
Supported Python versions use a TLS 1.2-or-newer default minimum in that context;
the runtime's OpenSSL/CA installation and supported cipher suites remain part
of the platform dependency. See the
[Python SSL documentation](https://docs.python.org/3/library/ssl.html#ssl.create_default_context).
The application does not implement a cryptographic protocol or custom cipher.
TLS verification occurs during connection setup before the HTTP request is sent.

Last.fm credentials can live in a secrets-only TOML file supplied by `--config`,
separate from ordinary settings. Rotation requires replacing the file value and
removing any overriding environment/CLI value; it requires no rebuild.
The operator must protect the file and directory permissions. The application
does not provide a password-authentication service or store external users'
password databases; hosted GitHub/PyPI account controls must be assessed
separately.

SHA-256 is used for release artifact comparisons and the bounded cover-validation
cache; the latter is not a digital signature. Temporary file names use Python
`secrets`. Release authenticity depends on signature/provenance verification and
trusted publisher identity, not solely on a matching hash or protected Git tag.
Algorithm agility, hosted-site headers and the full badge applicability
assessment remain tracked in
[#107](https://github.com/buettgen-app/coverart-cli/issues/107).

## Evidence maintenance and remaining work

For each security-relevant change, the reviewer should identify the affected
requirement above, inspect the implementation and meaningful regressions, run
the required checks and record their source SHA and limitations. New provider
hosts, writable output types, Windows support changes and release identities
require revisiting the model rather than merely rerunning existing tests.

The current Atheris targets exercise image validation and report/URL invariants.
They do not establish sanitizer instrumentation of Pillow's native libraries or
coverage of every memory-safety boundary. CodeQL, lint, secret checks and
dependency checks also have separate scopes. A skipped, inaccessible or stale
check is not a successful result.

The following evidence still needs explicit owner/reviewer confirmation:

- A human security review of the requirements, design and boundaries, dated
  within the period required by the badge and bound to a reviewed source.
- Human secure-development knowledge and independent human code-review records;
  AI-generated text and tests do not certify those facts.
- Current security advisories, dependency alerts and private report dispositions,
  including response times, reporter consent/credit and fix-release evidence.
- Live repository/organization 2FA, required checks, tag/release protections and
  hosting-service hardening. Documents cannot configure or verify those settings.

Track the human review in [#101](https://github.com/buettgen-app/coverart-cli/issues/101),
response evidence in [#102](https://github.com/buettgen-app/coverart-cli/issues/102)
and administrative controls in [#105](https://github.com/buettgen-app/coverart-cli/issues/105).
Confirmed vulnerabilities belong in the private process described in
[SECURITY.md](../SECURITY.md), with a public sanitized summary when appropriate.
