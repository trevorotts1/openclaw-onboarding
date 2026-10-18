# Council of Wise Elders (77): Changelog

## v1.0.9: waves 5-6 cohort (route discovery, durable budgets, capability probe, supervisor HYB-03/04)

- Discovers Council routes from the actual OpenClaw host layout (`runtime/src/cli/route-discovery.ts`): non-default config and state roots without any `~/.openclaw` assumption, JSON5 host configuration, named secret **references** that resolve only at flight time with the value asserted absent from errors, logs and receipts, explicit failure for unsupported API families and ambiguous model selection with no silent substitution, and freezing through the WER-006 snapshot contract so downstream transport consumes one shape.
- Adds durable budgets (`runtime/src/budgets/`) and wires them into the CLI host (`runtime/src/cli/local-host.ts`, `budget.ts`, `leases.ts`): the tightest applicable ceiling wins over runtime defaults, per-operation reservations commit before dispatch, lease fencing generation flows from the durable store rather than a process-local counter, unknown outcomes stay reserved while known-rejected ones release, and renewal adds capacity without erasing history. Two concurrent admissions against one bound produce exactly one winner across separate store instances.
- Adds the historically-unready bounded capability probe (`runtime/src/cli/model-probe.ts`): purpose-bound grant, route snapshot verified before any spawn, operation/attempt identity recorded before launch, and three distinct outcomes — attempted, answered, schema-qualified — so a refused, failed, malformed or timed-out probe can never set a callable success state. One token never qualifies a complete Council.
- Extends the engineering supervisor with HYB-03 and HYB-04 (`scripts/supervisor/`): deterministic health collection, staffing comparison with expiring underfill exceptions, an incident/action journal with counters that survive restart, a QC-backlog trigger, launchd plist and validated start/status/stop/restart command arrays as artifacts (nothing registered or loaded), an independent due+30s overdue detector that fires even with a live PID, and restart reconciliation over durable pending actions. Supervisor suite: 99/99 (47 original preserved).

## v1.0.8: wave-3 cohort (subprocess transport, approval front door)

- Adds the platform-safe bounded subprocess transport (`runtime/src/cli/`): a structured executable resolver handling native binaries, Windows `.cmd` shims and supported PowerShell invocation without assuming WSL, bash shebangs or symlinks; per-request model/effort and profile config pinned rather than read from a mutable global; prompt content delivered **only** on stdin and never interpolated into a shell string; bounded output, enforced deadlines, abort propagation and whole child-process-tree cleanup on cancellation. A Windows path containing spaces and non-ASCII characters resolves byte-intact in the simulated-resolver tests.
- Records `operationId` and `attemptId` **before** launching, so a timeout is recorded as potentially-dispatched rather than safe-to-retry. A route snapshot failing `verifyRouteSnapshotHash` is refused before any spawn.
- Adds the approval front door (`runtime/src/authorization/`): fingerprinting over the entire normalised approval command — ceilings, expiry, parent/renewal linkage and route options — so an exact retry returns the original committed receipt while a changed option under the same idempotency key conflicts **before** any write. Preview-to-session association is validated, so submitting one session's preview to another's approval URL performs zero grant, state or event writes even under the same owner. Revoked and expired authority both refuse without mutating. Reuses the existing grant service; Council spending authority stays distinct from development merge permission and from action-plan execution authority.

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
