# Changelog — 32-command-center-setup

## v12.9.36 — 2026-07-11 — fix(cc): provision a sovereignty-clean QC judge model (QC-08) + loud stale-mirror post-condition

**The Command Center quality-review judge had no model name assigned on ANY box, so no task could pass review — every client's board silently completed nothing.**

This was never a bug in the scorer. `qc-scorer.ts`'s `resolveClientJudgeModel()` reads exactly two sources — (a) the department QC agent's `model` column and (b) `QC_JUDGE_MODEL` — and both are empty on every box, so it fails **CLOSED by design** (QC-08: the judge must run on the CLIENT'S OWN model and must NEVER borrow a shared/operator key). Every review therefore fell through to the heuristic `'no-key'` path, which never auto-passes: tasks sat in `review`, escalated once to a terminal `[QC-HEURISTIC-FINAL]` marker, and were then **permanently excluded from the re-score sweep**. The board looked alive and completed nothing. It was an **unprovisioned setting**, and this release provisions it.

- **`cc_resolve_judge_model()`** — selects a judge from **THIS client's OWN Ollama Cloud text models**, read from the box's own `openclaw.json` (the same sovereign store `cc_resolve_sovereign_model` already reads: the `ollama`/`ollama-cloud` provider model lists plus the agent model defaults/fallbacks). Family precedence is the operator's decision — **deepseek > glm > qwen3 > gpt-oss > mistral**. A `*-code` / `*-coder` (or embedding) model is **never eligible**: the judge must be a strong *general reasoner*, not a code model.
- **⛔ Sovereignty, enforced.** The judge is always one of the client's OWN models. There is **no hardcoded fleet default** that could point at another client's key. If the client has **no eligible own-model**, `QC_JUDGE_MODEL` is left **UNSET** (fail-closed is the correct behaviour — the scorer holds the task for human review) and the installer logs a clear `judge not provisioned — needs a client model` line. We never guess and never borrow.
- **Idempotent.** An operator-set `QC_JUDGE_MODEL` is **preserved**, never overwritten. A per-client override is available via `CC_QC_JUDGE_MODEL` (which must itself still be a client-owned, non-code reasoning cloud model).
- **Model FORM — derived from real capability, not assumption.** We write the client's own id **verbatim** (`<m>:cloud`), stripping only a leading `ollama/` or `ollama-cloud/` provider prefix. We deliberately do **NOT** rewrite `<m>:cloud` → `ollama-cloud/<m>`: that strips the `:cloud` tag the box's endpoint may require. Proven on the operator canary — the box's Ollama endpoint **404s on the bare id** and **200s on `<m>:cloud>`**. The CC scorer's `isOllamaCloudModel()` accepts the bare `<m>:cloud` form and sends it to the endpoint unchanged.
- **JUDGE != WRITER — design note.** The scorer only enforces judge≠writer when the **writer** model is known (`input.writerModel`). Today **every** `agents.model` column is blank fleet-wide (verified on the canary: **0 of 290** agents carry a model), so `writerModel` is null and the equality guard is **skipped**. Therefore *any* eligible client-owned reasoning model is a safe judge today. When agent models are later populated, the deepseek/glm/qwen3 precedence still yields a judge that differs from a kimi/other writer in practice.
- **Endpoint dependency — explicitly OUT OF SCOPE here, and flagged.** Scoring also requires the box's Ollama Cloud connector to reach a working endpoint with the client's key. This block sets only the judge **NAME**, from the client's own models. Provisioning the connector's base URL is per-box and is deliberately **not** guessed here (never assume another box's endpoint). See the repo CHANGELOG for the canary finding.

**Loud stale-mirror post-condition.** After `cc_mirror_api_auth_to_agent_secrets`, the installer now asserts the mirror actually landed: if `MC_API_TOKEN` is present in the CC `.env.local` but **absent** from `$OC_ROOT/secrets/.env`, it logs an `ERROR` naming the cause (a **stale on-box Skill-32 checkout** predating the mirror, v12.9.31) and the remedy. A half-provisioned box — server fine, dispatch dead — must never fail silently.

## v12.9.35 — 2026-07-11 — fix(cc): tunnel daemon survives a power outage — root LaunchDaemon + resolved cloudflared + token-file

`scripts/setup-tunnel-daemon.sh` shipped three power-outage defects found in a
fleet audit (0 of 11 client Macs survived a power cut):

1. It installed the Command Center tunnel as a **user LaunchAgent**
   (`~/Library/LaunchAgents`). A LaunchAgent lives in the `gui/<uid>` launchd
   domain, which does not exist until a console login creates it —
   `RunAtLoad`/`KeepAlive` are a red herring. A tunnel has no GUI dependency, so
   it is now a **root LaunchDaemon** (system domain, starts at boot, no login).
2. It **hardcoded `/opt/homebrew/bin/cloudflared`**, which does not exist on an
   Intel Mac (Homebrew lives at `/usr/local` there). One fleet box exits 78
   (`EX_CONFIG`) on every launch and has never once run. The binary is now
   resolved with `command -v cloudflared`, with both Homebrew prefixes as
   fallbacks.
3. It referenced `~/.cloudflared/config-command-center.yml`, which is **missing
   on at least 3 fleet boxes**. It now runs from the connector **token** (what
   the registration webhook actually returns) — no config file to go missing.

Plus a fleet-wide security fix: the tunnel token was in **cleartext** in a
world-readable root plist and visible in `ps` to any local user. It now uses
`--token-file` with mode 600 (the `com.cloudflare.ghl-inbound` pattern).

Honest limit: a LaunchDaemon still does not run on a FileVault-ON Apple Silicon
box (pre-boot unlock halt). The FileVault gate in
`platform/mac/power-resilience/` is what makes this daemon meaningful. See that
directory's README for the full analysis.

## v12.9.31 — 2026-07-07 — fix(cc): durable converge guards so a Command Center rebuild can never re-break the Kanban

Root cause (proven on a client box): Phase 6 of `scripts/run-full-install.sh` pulled fresh
Command Center source and ran `npm install` (whose `postinstall` only `npm rebuild`s the
better-sqlite3 native addon) then restarted pm2 — but **never ran `next build`**. `npm start`
→ `scripts/cc-start.sh` → `next start` therefore kept serving the pre-existing `.next` bundle,
which predates the pulled source. The Next.js instrumentation hook
(`src/instrumentation.ts` → `registerCronJobs`) that registers the **intake-advance** +
**backlog-redispatch** sweeps is compiled INTO `.next`; a stale bundle omits them, so nothing
polls the backlog and cards stick in Backlog (`dispatch_attempts` stays 0). Three runtime env
vars were also never provisioned, so even a fresh build could fail closed: an empty
`OPENCLAW_GATEWAY_TOKEN` (Bridge unauthenticated to the local gateway), an unset
`SOVEREIGN_DEFAULT_MODEL` (AF-MODEL-SOVEREIGNTY blocks every text dispatch when nothing else
resolves a model), and unset `MC_API_TOKEN`/`WEBHOOK_SECRET` (newer CC middleware rejects the
ingest + agent-completion webhooks).

Four durable, idempotent, additive guards were added to `scripts/run-full-install.sh` and run
in BOTH the full-install and `--update-only` Phase-6 branches, after `npm install` and before
the pm2 (re)start:

- **(1) `cc_ensure_fresh_build`** — rebuilds `.next` **only when it is stale** (`.next/BUILD_ID`
  missing or older than any build input: `src/`, `public/`, `config/`, `next.config.*`,
  `package*.json`, ts/tailwind/postcss configs, `middleware.ts`). A no-change re-run does not
  rebuild. Verifies a fresh `BUILD_ID` (mtime ≥ build start) so a build that exits 0 yet
  produces no output is caught. A full install with no usable `.next` hard-fails; an update
  with a prior bundle degrades (resume cron retries). Freshness is folded into the FINAL
  "no false done" degraded-phase gate (`commandCenterBuildFresh`).
- **(2) `OPENCLAW_GATEWAY_TOKEN`** — copied into CC `.env.local` from **this box's own**
  `gateway.auth.token` when `gateway.auth.mode == "token"`. The token value is never logged.
- **(3) `SOVEREIGN_DEFAULT_MODEL`** — set to **this box's own** primary TEXT model, discovered
  per-box from `agents.defaults.model.primary` (→ main-agent primary → sovereign fallback →
  string form), gated to reject any free/Anthropic id (mirrors the CC model-selector) so the
  value is actually honoured. Operator override: `CC_SOVEREIGN_DEFAULT_MODEL`. Never a shared
  or hardcoded model.
- **(4) API-auth posture** — provisions `MC_API_TOKEN` + `WEBHOOK_SECRET` (generated once,
  reused, never rotated) by default so a rebuild cannot silently flip fail-closed; a
  Cloudflare-Access box may opt into `ALLOW_INSECURE_OPEN_API=true` via
  `CC_ALLOW_INSECURE_OPEN_API=true` (or `CC_API_AUTH_MODE=insecure`).

`.env.local` is written 0600 as the box user; existing operator values are always preserved
(never overwritten, secrets never rotated), so the guards are safe to re-run on every
install/update/resume.

## v12.9.30 — 2026-07-05 — feat(sop): add-sop.sh emits per-step persona SLOTS for multi-craft SOPs (F3.9, DEP-4)

- **`scripts/add-sop.sh` — new `--persona-slots` flag.** A multi-craft SOP (e.g. "build a
  landing page" = CONTENT + CODE + IMAGE) can now declare a per-step persona-slot contract:
  a JSON array of `{slot, task_category, domains?, audience_from?, required?}` objects. The
  value is validated as a non-empty JSON array (each slot needs at least `{slot, task_category}`)
  and FAILS LOUD on a malformed contract — a bad slot list must never silently drop, or the
  matcher would fall back to text-inference and hide the multi-persona wiring. On success the
  slots are emitted into the SOP header (`persona-slots: <compact-json>`, alongside the
  existing `persona-hints`) and surfaced in the `---SUMMARY---` line. The CC ingest (DEP-5)
  reads this back and drives `decompose-task.py --slots`, which fills each slot with a DISTINCT
  best-fit persona (F3.9). No behavior change when `--persona-slots` is omitted.

## v12.9.29 — 2026-07-05 — F4.5: align CORE_UPDATES persona wording with the matching protocol (doctrine only)

- **F4.5 (DEP-9) — Department-Head Pattern wording corrected.** `CORE_UPDATES.md` previously said
  departments get "Personas assigned from coaching-personas library", conflating a department's
  `dept_label` (its department-head display name) with a coaching persona. Corrected to state that
  coaching personas are matched **per task, at runtime** and are NOT assigned to departments, per
  `23-ai-workforce-blueprint/persona-matching-protocol.md`. Added a terminology callout pointing to
  `TERMINOLOGY.md` → "Persona — three distinct meanings". No provisioning/behavior change.

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
