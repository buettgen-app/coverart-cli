# Roadmap: October 2026 through October 2027

The intended direction for the next year is a reliable local artwork tool with
clear safety boundaries on Linux, macOS and native Windows. This roadmap guides
priorities; it is not a promise of delivery dates. Confirmed security problems
and compatibility regressions take priority over planned enhancements.

## Near term: evidence and dependable operation

- Make contribution, architecture, security and release-verification instructions
  usable by someone outside the current maintainer workflow.
- Complete the technical and evidence work in the
  [OpenSSF roadmap](https://github.com/buettgen-app/coverart-cli/issues/108),
  distinguishing implemented safeguards from missing administrative or human
  evidence. Badge status follows verified criteria, not this plan.
- Improve branch coverage with meaningful error-path tests, particularly around
  native Windows handles/ACLs, media preservation and rejected network input.
  Preserve existing gates and strengthen them only with measured evidence.
- Keep supported Python versions and dependency locks current after checking
  API compatibility, wheels and actual platform support.

## Following work: usability and resilience

- Review the native Windows installation and failure messages using real,
  disposable NTFS test libraries. Keep unsafe or unsupported filesystems explicit.
- Investigate reproducible provider failures, throttling and ambiguous catalog
  matches while retaining request/image budgets and provider terms.
- Improve CLI/report accessibility: keyboard focus, meaningful control names,
  status that does not depend on color and understandable errors. Evaluate a
  proportionate internationalization design for user-facing text.
- Use measured profiles of representative synthetic libraries to prioritize
  memory, filesystem and concurrency improvements. Preserve metadata and
  deterministic failure behavior before pursuing throughput.

## Ongoing through October 2027

- Maintain normal protected integration and the single automatic publication
  path, including artifact/provenance verification and bounded recovery.
- Triage bugs, vulnerability reports and dependency advisories; keep the latest
  supported release and upgrade instructions current.
- Make small contributor tasks discoverable and support additional human
  reviewers/maintainers. Independent participation, continuity and review history
  require real people and cannot be established by adding bot accounts.
- Revisit this roadmap at least quarterly during active maintenance and when a
  material platform or project-scope decision changes the priorities. Record
  specific work in issues rather than treating every item here as a release gate.

## Non-goals for this horizon

- A hosted music service, user accounts, uploads of users' audio libraries or
  telemetry that tracks their listening/library contents.
- A general music player, transcoder, audio-content editor or full tag editor.
- Automatic destructive replacement of existing artwork or metadata without
  the user's selected policy.
- Support for unsafe path traversal or bypassing native Windows handle/ACL
  protections to accept otherwise unsupported libraries.
- Proprietary paid services as a prerequisite for developing, testing or using
  the tool, or speculative provider additions without a maintainable integration.
- Claiming universal filesystem safety, complete vulnerability absence or an
  OpenSSF badge before its required evidence exists.

Propose changes to the priorities through
[GitHub Issues](https://github.com/buettgen-app/coverart-cli/issues), with a concrete
user need and compatibility impact. See [CONTRIBUTING.md](../CONTRIBUTING.md) for
implementation and review expectations.
