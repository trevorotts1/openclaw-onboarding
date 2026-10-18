# Council of Wise Elders (77): Changelog

## 1.0.7 - 2026-10-18

Integrate four supplied Oprah and Les book mappings, partial source qualification and governance discovery. Publish the verified 105-persona index. Preserve the landed 1.0.5 queue/supervisor and 1.0.6 route-snapshot/installed-CLI implementations; regenerate the combined distributable.

## v1.0.6: wave-2 cohort (frozen route snapshot, installed-CLI bridge)

- Freezes the normalized route snapshot contract (`runtime/src/providers/`, schema `wise-elders.route-snapshot/v1`): session owner, route and account reference, host/config selection, API family, requested model or combination alias, permitted members and fallbacks, requested / supported / applied reasoning kept distinct, capability version, policy hash and rate/concurrency limits. Configured identity and transport-reported identity are separate fields, and an unreported provider member stays explicitly `UNKNOWN` rather than being assumed. The snapshot carries a stable hash that WER-007, WER-008 and WER-009 consume instead of inventing their own route shapes.
- Pins the member **set** while excluding per-member transport evidence from the pin body, so recording evidence later can never move the pin on a combination route. `withTransportReportedIdentity` now also recomputes authoritatively rather than re-asserting the stale published stamp.
- Resolves the installed Council CLI through the WER-004 release receipt (`runtime/src/bridges/`), independent of the current working directory or a checkout's `dist` folder, and propagates route-discovery diagnostics and the real route catalog through the bridge wrapper instead of swallowing them. A missing or invalid receipt fails with a concrete recovery action, and a failed browser open preserves the usable URL.
- Replaces a frozen `readdirSync` directory literal in the bridges test with a membership check that still fails on a missing module and on a stray file, so a deliberate addition no longer breaks it.

## v1.0.5: wave-1 repair cohort (supervisor, installer, durable producer)

- Adds the engineering supervisor bootstrap (`scripts/supervisor/`): a deterministic ~60s health observer, a 600s full-sweep planner written as a pure function over injected time, durable leader/fencing-generation state, and the STARTING/HEALTHY/DEGRADED/PAUSED/STOPPING/STOPPED machine with the explicit-stop fence. Policy ships as `wise-elders.hybrid-supervisor-policy/v2` with `binding_status: TEMPLATE_NOT_BOUND`. Native-adapter binding is deliberately left `UNKNOWN` rather than invented.
- Rewrites `scripts/install-runtime.mjs` so the exact-executable Node prerequisite probe (`node:sqlite` in-memory write/read/close plus an isolated persistent reopen) runs before any file is written, installs into a staged immutable external prefix, hashes protected SOURCE only — never `node_modules` or `dist` — and activates atomically while preserving the previous receipt.
- Adds the canonical durable operation producer (`runtime/src/queue/`): admission commits transition, job and event/outbox in one owning-store transaction, a QUEUED row without its job is rejected, `attemptOrdinal` survives restart and `leaseGeneration` is rechecked on every mutable commit. No second scheduler was introduced.

## v1.0.4: Russell retained-source intake

- Registers DotCom Secrets and Expert Secrets via Skill22 and binds ten original paraphrases to retained-source hashes and edition-specific locators.
- Records primary-teaching coverage for both Russell anchors without upgrading other seats, semantic evaluation, full-book certification or installed readiness.
- Preserves private-source exclusions and publishes the approved two-persona incremental index as prebuilt-index-v2.4.3 (101 personas / 1,441 rows), with every prior row unchanged.

## Unreleased: final packaging (CWE-039)

No version change: versions are taken at merge time only. This entry
records the final packaging of the complete package whose runtime and
nine advisor packs landed in their own units after the v1.0.0
scaffold.

- Runtime and packs: the deliberation runtime, the standalone CLI,
  and all nine advisor packs ship in this package. Every pack's
  qualification is bibliographic_only (CWE-042); config/advisors.json
  pack_status now reads built_bibliographic_only for all nine seats.
- Distributable archive: scripts/build-bundles.mjs now generates
  council-of-wise-elders.skill at packaging. The archived Brunson
  pack copy has the private_scope items removed and prose references
  to them scrubbed (CWE-012 acceptance condition 3); the source tree
  retains the private-scope record.
- Install path: scripts/install-runtime.mjs performs the real
  isolated pinned install plus build (INSTALL.md Step 4), and
  INSTALL.md Step 9 states the live-acceptance terms for the built
  package, including the INSTALLED_NOT_LIVE_VERIFIED record when no
  live run is authorized.
- Housekeeping: the Wave 6 roster comment in lib-onboarding-state.sh
  and the structural test banner no longer describe the package as a
  scaffold with an unbuilt runtime.

## v1.0.0: Initial canonical scaffold

- Adds the agentskills.io-conformant SKILL.md with the fixed nine-seat
  roster, the exact Section 7 profile label discipline, and the Section
  20.1 front-door phrases with existing-session control resolution.
- Ships the portable package structure: install guide in the literal
  installer-contract order, instructions, examples, core updates,
  prereqs, configuration defaults, references (protocol, scoring,
  source policy, model routing, report template, install matrix,
  troubleshooting), and QC rubric plus bundled QC scripts.
- Registers the skill with the onboarding installer: glob discovery
  counts the folder, the Wave 6 roster in lib-onboarding-state.sh gains
  an explicit entry, the skill-department-map gains the skill 77 entry,
  and the Council deliberation SOP registers in universal-sops.
- Update-flow safety: no council state is stored inside the skill
  folder, so wholesale folder replacement by the update sync cannot
  destroy sessions, briefs, verdicts, or client knowledge.
- Honest scope: the deliberation runtime (runtime/), the standalone
  CLI, the Skill 22 exporter, and the nine advisor knowledge packs are
  scaffolded and marked not-yet-built. They are owned by their own
  build units and are not simulated here. The front door reports the
  council as not ready until they land.
