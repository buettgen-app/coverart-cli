# Coverage evidence for OpenSSF

[Repository coverage policy](repository-checks.md#test-coverage) defines the
enforced platform gates. This guide explains how to assess the separate OpenSSF
coverage criteria without hiding platform-specific code or counting the same
module repeatedly.

OpenSSF Gold requires at least
[90% statement and 80% branch coverage](https://www.bestpractices.dev/en/criteria/2?details=true)
where FLOSS measurement tools are available. A passing repository gate is not
itself proof of those results: the native Windows backend has a lower enforced
baseline. Work remaining toward the complete claim is tracked in
[issue #103](https://github.com/buettgen-app/coverart-cli/issues/103).

## Collect evidence from one source revision

1. Select a completed CI run for the intended source revision. Record its URL,
   head SHA, actual checked-out SHA (PR runs may use a test-merge commit), base
   SHA and tool versions. Confirm the checked-out code is the code being assessed.
2. Download all eight `coverage-*` artifacts from that run: Linux Python
   3.11–3.15, macOS Python 3.15 and Windows Python 3.11/3.15. Verify artifact
   digests during download and require each JSON, XML and HTML report.
3. Run `scripts/check_coverage.py` with the matching `common` or `windows`
   profile against the reports from the same checkout. Do not replace missing,
   expired or malformed reports with a green job conclusion.
4. Record covered/total statement and branch counts, plus the independent
   percentages and combined percentage, for every profile. Include per-module
   results so a large well-tested module cannot conceal an untested boundary.
5. Save the evidence in the relevant PR/issue or durable release evidence,
   including report digests and limitations. CI artifacts currently expire after
   seven days; a link to an expired artifact does not preserve its contents.

Coverage runs execute tests. Use an isolated checkout and the checked-in tools;
do not run an untrusted artifact's scripts merely to read its JSON or HTML.

## Keep scopes explicit

The common profile measures shared Python runtime modules and repository
scripts. It omits `_windows_filesystem.py` because that implementation requires
native Windows; both Windows jobs separately measure that entire module.
This is platform separation, not permission to discard it from a project-wide
claim. Preserve all current profile, combined and per-module gates even when
also calculating a project-level result.

State which delivered files and languages the badge claim covers. Runtime-only
Python totals must omit repository tooling consistently from both numerator and
denominator and list that scope decision; report the repository-script
measurements separately. The report template also contains JavaScript:
Python coverage and HTML string assertions do not measure execution of its
browser-side statements or branches. Assess that code with an appropriate FLOSS
tool before claiming coverage of all delivered executable code. Tests that check
rendered markup remain useful evidence, but are not a JavaScript coverage report.

## Combine counts, not percentages

For disjoint scopes measured once:

```text
statement coverage = 100 × sum(covered statements) / sum(total statements)
branch coverage    = 100 × sum(covered branches)   / sum(total branches)
combined coverage  = 100 × (covered statements + covered branches)
                         / (total statements + total branches)
```

Do not average percentages or add all eight report totals: the common modules
appear in six reports and the Windows backend appears in two. That would
overweight shared code and duplicate denominators.

A reproducible conservative calculation can select one complete common report
and one complete native Windows report from the same source, verify their
module sets are disjoint, and add their counts. State the selected platforms and
retain all other profile results. That calculation describes those two scopes;
it does not establish that every platform independently reaches the same result.

If combining execution across platforms instead, form unions of covered
statements and branches by canonical module and executable location, counting
each possible location only once. Verify identical source and compatible
measurement semantics first; interpreter/tool changes can alter branch
denominators. A maximum of per-file percentages is not such a union. Document
any incompatibility rather than silently mixing it away.

## Improve coverage without weakening the claim

Use missed-line/branch reports to choose behavior tests with meaningful
assertions, particularly rejected inputs, I/O failures, Windows ACL and handle
boundaries, metadata preservation and report interactions. Native Windows tests
must execute on native Windows; a Linux skip does not validate them.

Raise a profile's threshold only after supported runners demonstrate the result.
The common branch floor is 80%; Windows retains its existing baseline until
additional tests support a higher floor. Never add exclusions, remove required
reports or lower another threshold just to reach a percentage. Full Gold
coverage remains unproven until its complete applicable scope and the measured
results are evidenced.
