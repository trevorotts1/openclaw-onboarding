# Changelog — 32-command-center-setup

## v12.9.28 — 2026-07-05 — F4.4/F4.7: Kanban Persona-Gate + persona observability probe (DEP-10)

- **F4.4 — `scripts/move-task.py` now enforces a persona precondition on the Kanban
  lifecycle** (persona-aware boards only; migration 016+ `tasks.persona_id`). The
  sole sanctioned status mover previously had zero persona awareness — a card could
  travel backlog→done persona-"naked". New Persona-Gate:
  - **INTO `in_progress` → warn-and-heal.** If the card has neither an assigned
    persona nor a recorded `no_persona_required` decision, best-effort invoke the
    canonical selector (`persona-selector-v2.py`, **bounded `--no-llm --no-record`**)
    to heal it, then PROCEED regardless. Never parks work (availability > purity).
  - **INTO `review` → HARD gate.** A card may not enter Review naked: heal once, and
    if still naked BLOCK (exit 2) — by this stage a missing persona is a bug signal,
    not a workflow state. Explicit operator override `--allow-no-persona` records the
    `no_persona_required` decision (audited) for genuinely mechanical work.
  - Fully schema-tolerant: boards without persona columns (Skill 23 not installed)
    are unaffected — the gate is a silent no-op. `MOVE_TASK_SELECTOR` env override
    for CI/probe determinism. All transitions/heals/blocks written to
    `task_status_audit`.
- **F4.4/F4.7 — new `shared-utils/fleet-heartbeat-persona-probe.sh`** (operator-side
  only). Two signals for the fleet heartbeat / operator living-status doc: (1) SQL
  count of **naked in-flight tasks** per box (in_progress+review with no persona and
  no `no_persona_required`), and (2) a **synthetic selector `--no-record` dry-run
  self-test** asserting selection actually runs on THIS box (catches fleet CC version
  skew). Degrades LOUDLY when Skill 23 is absent. Per the operator-box-separate +
  silent-updates doctrine the probe performs **no messaging of any kind** — report to
  stdout + exit code only; never wired to a client channel.
- **CI — `.github/workflows/persona-task-mode-wiring-guard.yml`** now compiles
  `move-task.py`, syntax-checks the probe, runs the new `move-task-persona-lifecycle`
  contract test, and **wires FDN-2's `no-naked-dispatch` contract test as the runtime
  enforcement gate** (hard once FDN-2 lands the file; visible pending notice until
  then — dependency-ordered self-activation).
- Tests: `tests/unit/move-task-persona-lifecycle.test.sh` (18 assertions, hermetic,
  stubbed selector) covering warn-and-heal, the hard Review gate, the override, the
  no-op on non-persona boards, and "never park" on In Progress.

## v12.9.26 — 2026-07-03 — OQ-1: locked interview-mode CC is BY DESIGN (docs + gating comments)

- **OQ-1 (ratified 2026-07-03) — Locked interview-mode Command Center.** The CC now ships
  FIRST but LOCKED to the `/interview` surface: the client sees only the interview (and its
  `/onboarding` progress screen) until closeout, when the full dashboard is revealed. The CC
  middleware (P0-5) 302-redirects every non-`/interview`, non-`/onboarding` page to `/interview`
  while build-state `interviewComplete` is `false`, and unlocks the full dashboard once
  `buildCompletedAt` is set. This is documentation + gating clarity ONLY — no provisioning
  behavior changed in this skill.
- **Clarified what the interview-complete gate protects.** `SKILL.md`, `INSTALL.md`,
  `PREREQS.json`, and the `run-full-install.sh` interview-gate comments now state explicitly that
  the `interviewComplete` gate protects the seeding/materialization of the client's REAL
  zero-human workforce (departments, roles, agents) — NOT the shipping of the locked CC shell.
  The interview-only view in front of an empty board before closeout is the intended experience,
  BY DESIGN, and must not be "unlocked" or treated as a rogue/stale board.
- **No invented env names.** The lock is STATE-DRIVEN off the canonical build-state fields
  `interviewComplete` / `buildCompletedAt` that this installer already reads/writes; there is no
  separate CC "unlock" env var and provisioning must not introduce one. Enforcement of the lock
  itself lives in the CC middleware (P0-5), a separate deliverable in the blackceo-command-center
  repo.

## v12.9.23 — 2026-07-01 — Dept-scan dedup-priority fix, interview multi-signal corroboration gate, jq-injection-safe state writes, tunnel phase-letter dedup

- **P2-4 — Dept-scan dedup-priority fix.** `materialize-dept-agents.sh` `DEPT_SCAN_ROOTS` was
  scanned legacy-first / canonical-last while the Python discovery loop uses first-wins
  `setdefault()` — so a stale leftover folder under the legacy `workspace/departments/` path
  could silently shadow the current, correct `build-workforce.py` output for the same slug.
  Reordered to most-authoritative-first: canonical master-files ZHC tree, then the Skill 32
  `workspaces/command-center` alt path, then the legacy `workspace/departments` path last, so
  first-wins `setdefault()` actually picks the canonical copy.
- **P2-7 — Interview multi-signal corroboration gate (binding, SKILL.md).** `run-full-install.sh`
  no longer scaffolds a Command Center off the bare `interviewComplete` flag alone. After the
  fast pre-check passes, it now shells out to `23-ai-workforce-blueprint/scripts/qc-interview-completion.py`
  (question count, forbidden jargon, mandatory fields, nudge wiring, no-fabrication) and only
  proceeds on a PASS (rc=0). A missing qc script fails **closed** (exit 1, `commandCenterStatus =
  "interview-qc-unverified"`) rather than silently passing; a non-PASS QC result gates the CC and
  exits clean (`commandCenterStatus = "interview-pending"`) so the interview resume/nudge loop can
  drive it to PASS.
- **P3-2 — jq-injection-safe state writes.** New `state_set_arg` helper writes any free-form or
  user-derived string (failure reasons, GHL missing-cred lists, tunnel URLs) via `jq --arg`
  instead of interpolating it into the jq program text, so a reason containing a quote or newline
  can no longer corrupt `openclaw-state.json` or inject jq. Applied to `fail_install`, the GHL
  credential-preflight missing-cred record, and the tunnel-success URL write.
- **P3-2 — Tunnel phase-letter collision fixed.** The tunnel phase in `run-full-install.sh` was
  mislabeled "PHASE 6b", colliding with the workspace-seed phase (also 6b). Renamed to the next
  free letter, 6h (6b–6g are seed/sync/md-sync/dashboard-content/kpi/ghl-preflight). The state key
  renamed `commandCenterPhase6bStatus` → `commandCenterPhase6hStatus`, with a backward-compat read
  fallback to the old key so the duplicate-CC re-POST guard keeps working on boxes whose state
  predates the rename.
- **P1-3 — `--update-only` client-slug resolution.** Now reads `companySlug` (canonical, written
  by `build-workforce.py`) via `state_get`, falling back to the legacy `clientSlug` alias, instead
  of a raw one-off `python3 -c` read that only checked `clientSlug`.

## v12.9.21 — 2026-06-30 — DB-path reconciliation, GHL preflight, orphan wiring, Done-Gate enforcement

- **P0 — One DB resolver everywhere.** Reconciled every `mission-control.db` lookup to
  `shared-utils/resolve_db.py` (Mac `~/projects/command-center` first, then VPS
  `/data/projects/command-center`), killing the VPS-only `/data/...` hardcodes that broke Mac:
  - `scripts/ingest-sop-library.py` — imports the shared resolver for its default DB.
  - `scripts/ingest-sop-library.sh` — Mac-first candidate list (the "Mac mini variant" now
    resolves on a Mac instead of `exit 2`); `$MISSION_CONTROL_DB` override.
  - `scripts/ingest-template-libraries.py` — `_DEFAULT_DB` now resolver-backed.
  - `scripts/materialize-dept-agents.sh` Phase 3 — replaced the wrong
    `$OC_ROOT/workspaces/command-center` candidate list (which silently skipped install-time
    QC/Devil's-Advocate/Healer rows) with the shared resolver + add-department.sh fallback, so
    the trio/quad rows land in the SAME db `add-department.sh` writes to.
  - `INSTALL.md` — canonical-DB note + clone target corrected to `~/projects/command-center`;
    removed the false "`~/projects` is stale" claim and the misdirecting symlink instruction.
- **P0 — QC port.** `qc-command-center-setup.sh` fallback `CC_PORT` 3000 → 4000 (the dashboard
  is `:4000` everywhere else), so the CC-running check targets the right port.
- **P1 — GHL credential preflight.** New `run-full-install.sh` Phase 6g: presence-only check of
  `GOHIGHLEVEL_API_KEY` (PIT) + `GOHIGHLEVEL_LOCATION_ID` in `secrets/.env`. Operator-facing,
  non-blocking, never silent, never messages the client; records the verdict to state.
- **P1 — Wired the orphans into `run-full-install.sh`** (both full and `--update-only`,
  WARN-only + state-recorded): Phase 6e `seed-dashboard-content.py` (Kanban renders cards),
  Phase 6f `generate-kpi-rollup.py` (CEO Performance Board `kpi-rollup.json`).
- **P1 — Done-Gate is now enforced in code.** New `scripts/move-task.py` state machine: the only
  sanctioned way to change `tasks.status`; refuses Review→Complete unless a Devil's Advocate
  sign-off (verdict=pass) exists; writes a `task_status_audit` row per transition. CORE_UPDATES.md
  updated to point the Done-Gate prose at the tool.
- **P1 — Canary heartbeat.** Shipped `HEARTBEAT.md` (the block `heartbeat-canary-probe.py`'s
  docstring references) with the grounded `openclaw cron create` command. (Cron registration is
  documented, not auto-executed from the orchestrator — deliberate, to avoid fleet-wide cron/token
  risk; canary alerts are already gated on `RESCUE_RANGERS_HELP_CHAT_ID`.)
- **P2 — crm_platform from interview + verify PIT before stamping.** `ingest-sop-library.py` now
  derives `crm_platform` from the company-config `connectedSystems` (mirrors
  `create_role_workspaces.py`: GoHighLevel default, HubSpot/Salesforce override; `$CRM_PLATFORM`
  wins), keeping INSERT OR IGNORE. When stamping GoHighLevel without the PIT present it emits a
  non-blocking operator NOTE.
- **P2 — Tunnel hardening.** `create-tunnel.sh`: transport-only webhook retry/backoff (never
  re-POSTs a received response — the webhook is non-idempotent) and writes the tunnel token to the
  canonical `~/.openclaw/secrets/.env` (chmod 600) in addition to the legacy `~/.openclaw/.env`.
- **P2 — Hygiene.** `generate-kpi-rollup.py` `datetime.utcnow()` → `datetime.now(timezone.utc)`;
  reconciled version markers (`.skill` 1.0.0 → 12.9.21 to match `skill-version.txt`).

Functionality preserved: every existing phase, the interview gate, memory-bloat `extraPaths=[]`,
strict dept count (no 17-default), atomic writes + timestamped backups are untouched. No client
chatter introduced. No first-party-LLM model recommendation exists in this skill (model scrub:
0 found, 0 introduced); GoHighLevel credential var names already canonical (`GOHIGHLEVEL_API_KEY` /
`GOHIGHLEVEL_LOCATION_ID`).
