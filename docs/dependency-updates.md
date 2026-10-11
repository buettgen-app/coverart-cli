# Automated dependency updates

`renovate.json` configures the hosted Renovate GitHub App for this repository.
It proposes updates on Monday before 06:00 Europe/Berlin. Actions and pre-commit
revisions wait seven days; Python updates have no release-age guarantee because
Renovate's uv integration cannot enforce age filtering for transitive resolution.
All Python updates remain subject to manual review and the full CI gates.
Ordinary PRs and vulnerability-alert PRs each have their own concurrency limit
of three; the combined maximum is six. Vulnerability alerts can
produce updates outside that window without the release-age delay. This depends
on the app's access to GitHub alerts and does not replace the security workflows.

Renovate uses its `pip-compile` manager for all four `requirements-*.txt` hash
locks. Their generated headers provide the original `uv pip compile` commands
and source files, including `pyproject.toml`; standalone Python managers are
excluded to avoid duplicate updates. The uv constraint matches CI's version.
The Python constraint and `--python-version=3.11` commands explicitly preserve
the project's oldest supported interpreter in universal resolution.
Options with values use `--option=value` in both CI and generated headers,
as required by Renovate's command parser. Schema validation alone cannot verify
this: an extraction dry run must also recognize all four lock files.
The upstream limitation is tracked in
[Renovate issue 41654](https://github.com/renovatebot/renovate/issues/41654).
Python non-major updates are grouped so shared sources and locks stay together.
GitHub Actions and pre-commit hooks have separate non-major groups; major
updates require individual review. CI checks that every lock is canonical.

## Interpreter and toolchain policy

Tooling, build, attestation and smoke jobs use Python 3.15. The Linux test
matrix also checks every supported minor from 3.11 through 3.15; native Windows
checks the oldest supported minor and 3.15. `setup-python` uses `check-latest`
so a cached older patch does not silently replace the current patch release.
The universal hash locks and Renovate resolver retain Python 3.11 as the
compatibility floor; that constraint is not the preferred runtime version.

The fuzz job uses Python 3.14 with Atheris 3.1.0 because that release provides
CPython wheels through 3.14, without a 3.15 wheel. Revisit the exception when
upstream adds support and verify both fuzz targets before changing it.
Release availability was checked against Python.org, PyPI, Go's download
metadata and upstream Git tags on 11 October 2026. CI uses Go 1.27.2, uv 0.13.0
and full commit SHAs for Actions; the pre-commit hooks track their latest stable
release tags. These versions are checked by the normal CI gates before merging.

## Activation and migration

1. Install or configure the [Renovate GitHub App](https://github.com/apps/renovate)
   for `buettgen-app/coverart-cli` using an organization administrator account.
2. Merge this configuration, inspect the Dependency Dashboard and verify the
   first Renovate PR regenerates the affected locks and passes all CI checks.
3. Once Renovate is operating, remove `.github/dependabot.yml` and
   `.github/workflows/dependabot-auto-merge.yml` together in a follow-up PR.
   Keep GitHub Dependabot alerts and security updates enabled. During migration,
   close redundant version-update PRs without disabling vulnerability alerts.

Dependabot remains configured until activation is verified so this change does
not silently remove working update coverage. Avoid leaving both version-update
bots enabled after the migration.

Renovate opens PRs automatically but automatic merging is deliberately disabled.
Before enabling it for selected low-risk updates, register the required checks
listed in [repository-checks.md](repository-checks.md), verify their expected
GitHub Actions source and require up-to-date branches. Preserve manual review
for major updates. Never bypass a missing or failed check.

Validate configuration changes with Renovate's `renovate-config-validator`
before merging. Upstream manager documentation is available at
[pip-compile](https://docs.renovatebot.com/modules/manager/pip-compile/).
