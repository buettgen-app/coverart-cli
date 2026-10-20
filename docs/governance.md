# Project governance

CoverArt is a maintainer-led project. Its purpose is to fetch, validate and safely
store album artwork and to report the state of a local music library. The
[roadmap](roadmap.md) describes the intended direction and non-goals.

## Decisions and responsibilities

The current [CODEOWNERS](../.github/CODEOWNERS) routes every path to
[@WildDragonKing](https://github.com/WildDragonKing). The maintainer makes final
scope, compatibility and acceptance decisions through public issues and pull
requests. Contributors can propose alternatives and ask for reconsideration with
evidence. Security-sensitive discussion follows [SECURITY.md](../SECURITY.md)
instead of a public issue.

| Responsibility | How it is carried out |
| --- | --- |
| Scope and contribution acceptance | The maintainer considers the proposal, compatibility, tests and review findings. |
| Code review | A reviewer checks the proposed change against [CONTRIBUTING.md](../CONTRIBUTING.md); the actual reviewer and reviewed commit remain visible in the PR. |
| Security response | The maintainer owns triage, coordination and release follow-through under the security policy. |
| Release operation | The existing protected [release workflow](releases.md) publishes tested changes; the maintainer resolves failures without bypassing its protections. |
| Repository administration | Authorized administrators manage access and protection settings; administrative access is not delegated by a documentation change. |

Contributors retain credit for their work and participate through the same public
proposal and review process. The MIT license applies to contributions; existing
copyright and third-party notices must be preserved.

## Automation and human accountability

Automation assists development, testing and release operation. One coordinating
writer owns an integration package. It may delegate separate tasks to agents,
but those agents do not independently push competing packages or merge changes.
Release monitoring and schedule maintenance have separate responsibilities.

An AI review, a bot account, successful CI or a CODEOWNERS assignment is not
evidence of an additional human reviewer, maintainer or contributor. Human review
must identify the person, the examined change and the decision. The project does
not claim a particular human review percentage without an auditable record.

## Continuity and succession

A second capable maintainer, a tested succession arrangement and independent
significant contributors have not yet been documented. These are tracked in
[#97](https://github.com/buettgen-app/coverart-cli/issues/97); this document does not
claim a bus factor of two or completed OpenSSF Gold governance requirements.

Before naming a backup, obtain their agreement and verify that they can handle
issues, review and integrate changes through protection, triage security reports,
and operate the normal release path. Authorized administrators must provision
and test necessary access separately. Keep credentials and recovery material
private; public evidence should describe the procedure and its validation, not
contain secrets.

The continuity plan must demonstrate that these activities can resume within a
week of confirmation that any one maintainer is unavailable. Revisit access,
roles and continuity whenever maintainers change. A code of conduct with a real
reporting and enforcement contact also remains part of #97.

## Changes to this model

Propose governance changes in a public issue or PR, explain their effects and
obtain agreement from any person taking on responsibilities. Do not assign a
person a role merely to satisfy a badge criterion. Record accepted changes in
this document and preserve the discussion.
