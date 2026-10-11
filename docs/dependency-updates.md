# Automated dependency updates

`renovate.json` configures the hosted Renovate GitHub App for this repository.
It proposes updates on Monday before 06:00 Europe/Berlin, waits seven days for
ordinary releases and limits concurrent PRs to three. Vulnerability alerts can
produce updates outside that window without the release-age delay. This depends
on the app's access to GitHub alerts and does not replace the security workflows.

Renovate uses its `pip-compile` manager for all four `requirements-*.txt` hash
locks. Their generated headers provide the original `uv pip compile` commands
and source files, including `pyproject.toml`; standalone Python managers are
excluded to avoid duplicate updates. The uv constraint matches CI's version.
Python non-major updates are grouped so shared sources and locks stay together.
GitHub Actions and pre-commit hooks have separate non-major groups; major
updates require individual review. CI checks that every lock is canonical.

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
