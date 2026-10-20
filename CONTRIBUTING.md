# Contributing to coverart-cli

Small fixes, regression tests, documentation improvements and bug reports are
welcome. Discuss a substantial behavior or dependency change in
[GitHub Issues](https://github.com/buettgen-app/coverart-cli/issues) first so the
scope and compatibility expectations are clear. Use English for shared project
documentation and reports. Report security vulnerabilities privately through
[SECURITY.md](SECURITY.md), not a public issue.

## From an issue to a pull request

1. Check existing issues and pull requests to avoid duplicating work. Describe
   the user-visible problem and a reproducible example using synthetic data.
2. Create a branch from current `main` in your fork or authorized checkout. Keep
   one pull request focused on one coherent change.
3. Implement and verify the change. For a bug fix, first add a regression that
   fails for the original behavior where practical. Major new functionality
   **must** include automated tests for its behavior and important failure paths.
   Tests should assert outcomes, not just exercise implementation details.
4. Update affected help text, examples and documentation. Explain compatibility,
   security boundaries and any platform-specific limits.
5. Open a pull request with the problem, resulting behavior, related issue,
   commands/results, relevant source references and checks you could not run.
   Use a [Conventional Commit](https://www.conventionalcommits.org/) title such
   as `fix: preserve existing artwork when a provider fails` or
   `docs: clarify report-only usage`. The [release guide](docs/releases.md)
   explains which prefixes cause releases.
6. Address review findings and rerun affected checks. New commits invalidate
   conclusions about code they change; identify the final tested/reviewed SHA.

Do not commit credentials, real music files, private reports, personal paths,
generated coverage/build output or virtual environments. Use synthetic fixtures
and the privacy conventions in [repository checks](docs/repository-checks.md).
Preserve copyright and third-party license notices. Submit only material you
have the right to contribute under this project's [MIT license](LICENSE);
identify the origin and license of reused material in the pull request.
The repository does not currently enforce DCO sign-offs or require a CLA.
The decision on a formal contribution attestation mechanism is tracked in
[issue #99](https://github.com/buettgen-app/coverart-cli/issues/99); do not invent
sign-offs for other contributors or rewrite published history.

## Development environment

Use a supported Python interpreter and the checked-in hash locks. The
[README development setup](README.md#development) gives the install, lint,
type-check and branch-coverage commands. On PowerShell, activate the virtual
environment with `.\.venv\Scripts\Activate.ps1` instead of the POSIX activation
command, or invoke its Python executable directly.

Install FFmpeg for the audio-stream preservation tests. Run the full suite before
submitting a product change; use a targeted `pytest tests/test_<component>.py`
run while iterating. Native Windows tests need Windows and macOS metadata tests
need macOS. A successful Linux run cannot substitute for those CI jobs.
Missing or skipped required checks do not count as passing.

## Coding style and test expectations

- Python follows [PEP 8](https://peps.python.org/pep-0008/) with the repository's
  explicit 100-character line length and Ruff formatter. The checked-in
  `pyproject.toml` is authoritative for Ruff rules and supported syntax.
- Run `ruff check .`, `ruff format --check .` and `pyrefly check`. Preserve
  compatibility with the documented Python minimum; a newer development
  interpreter does not authorize newer-only runtime syntax or APIs.
- Keep boundary checks explicit and failure behavior testable. Retain the
  no-follow filesystem protections, copy-on-write metadata preservation,
  network/image budgets and HTML/CSV injection defenses.
- Add offline, deterministic tests using synthetic data. Provider tests should
  mock transport responses rather than depend on live catalogs or API keys.
  Exercise success, rejection and cleanup when the change affects a boundary.
- Treat warnings as findings to investigate. Do not add broad warning filters,
  blanket lint/type suppressions, weakened coverage floors or exclusions to make
  a change pass. A necessary narrow exception needs a reason and review.
- Preserve all platform coverage reports and the
  [coverage policy](docs/repository-checks.md#test-coverage). Coverage is evidence
  of executed paths, not proof that assertions are sufficient.

Documentation-only changes need relevant example, link and consistency checks;
do not add tests that merely assert the exact wording of prose. CI still applies
the repository's required checks.

## Review and acceptance

Review the final diff for usefulness, correctness, backwards compatibility,
maintainability, privacy, trust boundaries and test quality. For filesystem,
network, media or release changes, inspect the relevant failure/race paths as
well as the successful path. Follow the
[component review and gauntlet](docs/repository-checks.md#component-review-and-gauntlet)
and record findings with a concrete trigger and expected result.

A pull request is ready for integration only when its applicable checks pass on
the final head, actionable findings are resolved with evidence, documentation
matches behavior and all configured repository protections are satisfied.
Unreachable checks and outstanding requested reviews remain open. Maintainers
use normal protected merges; contributors must not bypass checks or force-push
`main`. Version metadata, release tags and publication belong to the automatic
release process.

Distinguish an automated or AI-assisted review from a human's review. Record the
reviewer, reviewed commit, scope and decision; do not assign a person's approval
to a bot's output. The OpenSSF Gold goal of human review by someone other than
the author for at least half of proposed modifications needs actual pre-release
history. [Issue #98](https://github.com/buettgen-app/coverart-cli/issues/98) tracks
that evidence and reviewer availability; this policy does not claim that the
historical target has already been met.

## Small tasks for new contributors

These are bounded ways to contribute to the open documentation work in
[issue #100](https://github.com/buettgen-app/coverart-cli/issues/100). Comment on
the issue before starting so another contributor does not duplicate your work:

- **PowerShell quick-start check:** follow the README with the current published
  package and a disposable synthetic library. Report the Python/Windows/package
  versions, exact failing command if any, and a minimal documentation correction.
  Do not use a personal library as a test fixture.
- **Keyboard report check:** generate a report with `docs/make_demo_report.py`
  and check tab focus, search, filters and theme controls without a mouse.
  Record reproducible problems and propose one small fix; preserve report
  escaping and keep personal data out of screenshots.
- **Screen-reader report check:** inspect the same synthetic report's controls
  and coverage status using a screen reader. Report missing names or ambiguous
  status in one control at a time, including browser and assistive-technology
  versions.

The [architecture](docs/architecture.md) explains where changes belong, and the
[roadmap](docs/roadmap.md) describes the intended direction. The
[governance document](docs/governance.md) identifies the current maintainer and
which continuity and reviewer roles still need to be filled.
