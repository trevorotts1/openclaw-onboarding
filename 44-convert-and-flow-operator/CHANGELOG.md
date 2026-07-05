# Changelog — convert-and-flow-operator (Skill 44)

## [1.3.5] - 2026-07-05 — fix: close FAB-QC/TRINITY fail-open gaps + persona-log + Firebase/Tier-4 doc truth (merge-train T-44-convert-and-flow)

Skills-analysis campaign fixes. All changes are scoped to this skill directory.

### Fixed
- **FIX-XC-03g — FAB-QC now fails CLOSED.** `qc-built-workflow.sh` previously printed
  "(FAB-QC skipped)" with `FAB_RC=0` (ledger PASS, exit 0) whenever the scorer or evidence
  root was missing, and `FAB_EVIDENCE` defaulted to a dir nothing created — so the claimed
  ≥8.5 gate was a silent no-op. When `--fab`/`--evidence` is passed and the score is
  UNAVAILABLE for any reason (scorer absent, evidence_root missing, scorer emits nothing),
  the run is now `REQUIRES_OPERATOR`: `FAB_RC=1` and a non-zero exit. The canonical
  `evidence_root` is defined in INSTRUCTIONS Step 0.4 and the SAME root is passed at Step 9.3c.
- **FIX-S36-25 — persona-selection-log producer + `copy_persona` on 7 templates.** FAB-QC D4
  is fail-closed on `<evidence_root>/persona-selection-log.md`, a Skill-6 artifact that
  nothing in Skill 44 produced — so every standalone templated automation build hard-missed
  D4. `automation_matcher.step0_match` now PRODUCES that log in Step 0.4 (names the matched
  template's `copy_persona`, or a `selected_persona: net-new` marker for CREATE_NEW). Added
  snake_case `copy_persona` + `source_books` (mirroring the existing `copyPersona`/`source`)
  to the 7 engagement-broadcast templates that lacked the key FAB-QC D4 reads.
- **FIX-S36-26 — corrected workflow read-path docs + explicit Tier-4 QC branch.** `caf
  workflows list` is Tier-0 (LOCATION PIT); `caf workflows get`/`export` route through the
  INTERNAL Firebase client and REQUIRE the Firebase refresh token — the docs wrongly called
  export "Tier 0 / read-only". INSTRUCTIONS.md (routing table, per-op rule, Step 9.3) fixed.
  Added a fail-closed Tier-4 branch: with no Firebase token, export (and therefore mechanical
  QC) cannot run — `qc-built-workflow.sh` exits 2 `REQUIRES_OPERATOR` and the build is NOT
  DONE until the token is restored or an agent-browser read-back confirms it.
- **FIX-S36-27 — `--conversational` makes WF-19 a real hard gate.** `qc-trinity-registry.sh`
  was claimed as a hard pre-registration gate but nothing executed it (existence-assert only;
  WF-19 was REQUIRES_HUMAN_REVIEW). `qc-built-workflow.sh --conversational` now EXECUTES Skill
  38's `qc-trinity-registry.sh` and FAILs WF-19 mechanically on any non-zero exit (incomplete
  TRINITY, or no `conversation-workflows/` folder); a missing registry script fails closed.
  `qc-convert-and-flow.sh` now proves the wiring, not just the script's existence.
- **FIX-S36-28 (P3 bundle).**
  (i) Documented fail-soft kanban touchpoints on the deploy rail Skill 50 hands to
      (`in_progress` at PLAN MODE / Step 0.5, `done` only after all-PASS / Step 9.6) — never
      a blocker.
  (ii) `qc-built-workflow.sh` no longer aborts on a whole-export grep for `error|404` (which
      false-aborted on innocent email copy). It aborts only on a non-zero `caf` exit or a
      TOP-LEVEL JSON error key.
  (iii) Deleted the stray nested `tools/engine/tools/engine/...test_safety_gate.py` duplicate
      (a strict subset of the real test — no unique assertions lost) and reworded the stale
      "working copies in this scratchpad" note in `automation-templates/_matcher/WIRING.md`.

## [1.3.4] - 2026-07-01 — fix: unified 11-alias LOCATION-PIT scan closes credential crash-loop

### Fixed
- `tools/engine/cli_anything/gohighlevel/utils/ghl_client.py::_get_token()` previously read ONLY
  `GHL_API_KEY` from the live process environment. On a box whose token was stored under
  `GOHIGHLEVEL_API_KEY` (or any other canonical alias) with no `GHL_API_KEY` re-export, the engine
  raised a hard credential error and the calling agent looped retrying the same failing call.
  `_get_token()` now scans the full canonical `_LOCATION_PIT_ENV_NAMES` (11 names — see
  `TERMINOLOGY.md`) in order and returns the first non-empty hit; the error message names every
  var it checked. Root cause: a client-box GHL-MCP credential crash-loop, 2026-06.
- `tools/engine/wire-ghl-env.sh` now wires all 11 aliases into `env.vars` (previously wrote only
  `GOHIGHLEVEL_API_KEY` + `GHL_API_KEY`), closing the wiring-vs-engine mismatch that caused the
  crash-loop above (the wrapper wrote one set of names; the engine read a different single name).

### Added
- `SKILL.md` gains the GHL PIT-aliases banner and a "Unified 11-alias scan" callout documenting
  the `_get_token()` fix and which two credentials (the Agency PIT and the Firebase refresh token)
  remain on separate paths and are NOT part of this scan.

### Housekeeping — reconciles the v1.3.3 no-CHANGELOG gap
- v1.3.3 (bumped in the fleet-wide `v16.2.10` release, 2026-06-30) corrected six fabricated `caf`
  command-table rows in `INSTRUCTIONS.md` and fixed `--json` flag ordering, but shipped with no
  CHANGELOG entry. Recorded here for the version trail: `INSTRUCTIONS.md` command-table rows now
  match the real CLI surface.

---

## [1.3.2] - 2026-06-30 — fix: add `caf doctor` (probe entrypoint) + correct products/prices endpoints + remove-tag body + token-liveness idempotency + client-model scrub

### Fixed (correctness — proven bug)
- **`caf doctor` now EXISTS.** It was documented (INSTALL.md Action 6), asserted by the live
  install-QC (`qc-convert-and-flow.sh:277 "caf doctor exits green"`), and named as the probe
  entrypoint in `internal/probe.py`, but the command did not exist — so the `--live` QC failed on
  every provisioned box AND the contract-probe → auto-degrade subsystem had no runtime trigger.
  Added a read-only `@cli.command("doctor")` that runs `run_contract_probe(adapter)` (no
  `allow_write_probe`): PASS → exit 0; token absent/dead → WARN exit 0 (INSTALL.md "WARN not
  FAIL"); contract drift → exit 1. Missing-credential SystemExit/AdapterError are caught → WARN
  exit 0 (never a traceback). Issues NO writes.
- **`payments create-product` / `create-price` used an unverified path.** Corrected to the GHL
  Products API (confirmed against marketplace.gohighlevel.com/docs + the GHL "create a product with
  price" help article): create-product now POSTs `/products/` (not `/payments/products`) and
  create-price POSTs `/products/{id}/price` (SINGULAR, not `/payments/products/{id}/prices`).
  Dropped the payments-API `altId`/`altType` keys from both bodies; the products API takes
  `locationId` (+ `product` on the price). Test assertions updated in lockstep
  (`tests/test_ecosystem_cli.py`).
- **`contacts remove-tag` never sent the tags.** `ghl_client.delete()` had no body parameter, so
  the computed tag list was discarded and GHL's `DELETE /contacts/{id}/tags` (which reads the tags
  from the request body) could not remove them. `delete()` now takes an optional `body`; remove-tag
  passes `{"tags": [...]}` (symmetric with add-tag). Omitted body preserves every other DELETE
  caller's behaviour.
- **Token-liveness notification idempotency was one-sided (client-spam risk).**
  `check-ghl-token-liveness.sh` short-circuited on the `.ok` (VALID) stamp but never read the
  `.notified` (INVALID) stamp, so a second run on a dead-token day (double-fire cron / manual run /
  auto-redispatch) re-sent the client notification. Added a top-of-script `.notified` guard that
  short-circuits (exit 1, NO re-send) — honouring "at most once per calendar day" on the INVALID
  branch too (collided with the silent-updates / no-client-spam directive).

### Changed
- Build parallelism now honours `CAF_INTERNAL_MAX_WORKERS` (default 3, matching the internal
  adapter's burst-reduced cap) instead of a hard-coded 10 — bounds a single multi-workflow build's
  concurrent pipelines at the shared GHL rate bucket (`workflow_builder.py`).
- `caf`/`ghl`/`convertandflow` wrappers now `exec "$VENV_PYTHON"` (the absolute venv interpreter)
  rather than relying on `python3` resolving via PATH after `source activate` — strictly more
  robust; identical behaviour when the venv exists.
- **CAF_APPROVAL_TOKEN provisioning:** the wrappers now map canonical
  `GOHIGHLEVEL_APPROVAL_TOKEN → CAF_APPROVAL_TOKEN` (fallback to a direct `CAF_APPROVAL_TOKEN`),
  the same GOHIGHLEVEL_* → CAF_* pattern already used for allowed-locations/draft-only/dry-run.
  Previously the write-approval token had no canonical alias, so an operator who set the canonical
  `GOHIGHLEVEL_APPROVAL_TOKEN` still had surgical update/patch writes refused. Kept in secrets/.env
  (never wired into openclaw.json env.vars); empty when unset = the gate stays fail-closed (safe).
- `ghl_client._get_token()` now points the operator at the canonical `GOHIGHLEVEL_API_KEY` (the
  wrapper maps it to the engine-internal `GHL_API_KEY`), matching `_get_location_id()`'s guidance.
  Added an explicit `/products/` → `2021-07-28` VERSION_MAP entry.

### Client-model policy (client boxes run their OWN providers — NEVER Anthropic)
- Scrubbed genuine client-runtime model recommendations of Anthropic model names: INSTRUCTIONS.md
  Step 0 and the Step 9 hallucination-escalation now recommend DeepSeek v4 pro or GLM 5.2 (Ollama
  Cloud preferred, OpenRouter backup; thinking=HIGH) in place of "Opus-tier"; removed `haiku` from
  the "lighter model" examples; QC.md Section H header de-branded; the generated email-sequences
  doc now says "tell your assistant" (clients do not run Claude). Left untouched (framework/agent
  names, not model choices): upstream-engine "Claude Code" product-name mentions, the
  architecture-diagram label, and the historical CHANGELOG attribution.

## [1.3.1] - 2026-06-30 — fix: rebuild `caf` on every update (skill-root wire.sh) + drift stamp

### Fixed (root cause — proven drift)
- The routine update path never rebuilt `caf`: `update-skills.sh`'s wiring loop runs a skill
  installer only when found at the skill ROOT (`wire.sh > install.sh > scripts/install.sh >
  setup-*.sh`), and skill 44's only installer was at `tools/engine/install.sh`, which the loop
  never invokes. So the installed CLI silently drifted behind the synced source fleet-wide.

### Added
- `wire.sh` at the skill root: idempotent, fail-soft (re)builder for `caf` that the wiring loop
  DOES pick up. Copies the engine into `~/.openclaw/tools/convert-and-flow-cli/engine`, runs
  `pip install -e` in the venv, installs the caf/convertandflow/ghl wrappers, and writes the
  `.installed-from` drift stamp. Fast no-op when already current; always exits 0; no bare `gws`.
- `tools/engine/install.sh` now writes the `.installed-from` stamp (TOOL/SKILL_VERSION/
  ONBOARDING_VERSION/INSTALLED_AT/SOURCE_PATH) right after `pip install -e` succeeds, so an
  agent/guard rebuild also records the source version for `scripts/tool-drift-check.sh`.



### Fixed (correctness — proven bug)
- `Catalog.by_id` was keyed by BARE id, so `soap-opera-sequence` (present in BOTH
  `welcome-indoctrination/` and `sales-close-sequences/`) collapsed 28 templates to 27 and the
  welcome variant shadowed the sales-close one — expanding `follow-up-funnel` built the WRONG
  workflow_plan. Catalog now keys a qualified `by_key` (`group/id`) + `get(tid, group=…)` that
  refuses to guess an ambiguous bare id; `match_automation` and `expand_funnel_to_automations`
  resolve by the qualified `category/automation_id` the link map already supplies. Regression-locked
  by `tests/test_automation_matcher.py` (per-variant + all-38-funnels assertions).

### Added
- `automation-templates/_matcher/catalog-index.json` rebuilt PORTABLE — relative `root`/`sourcePath`,
  re-absolutised on load; the leaked operator-local scratchpad path is GONE.
- `automation_matcher.step0_match` emits `matched_template_key` + a `routing/match-decision.json`
  receipt for the QC gate.
- FAB-QC overlay in `qc-built-workflow.sh --fab` (shared scorer `shared-utils/fab_qc.py`, rubric
  `universal-sops/funnel-automation-build-quality-rubric.md`); "done" now requires WF-1..21 PASS AND
  FAB-QC ≥ 8.5 (INSTRUCTIONS Step 9.3c / 9.4).
- `tools/engine/wire-ghl-env.sh` exports the six matcher env vars so STEP 0 / Step 0.4 activate on a box.
- `automation-templates/README.md` (library orientation); SKILL.md read-order entry for the library.
- Deprecated v1 link map (`funnel-to-automation-link-map.json`) marked `deprecated` + parity-tested.
- Tests: `tests/test_automation_matcher.py` (flex, decisions, collision-safe variant, expansion,
  portable index, v1/v2 parity, step0 receipt).

## [1.2.0] - 2026-06-27 — feat: flex.py shared core + standardised decisions + Step 0.4 + link map v2 + Skill-6 matcher retrofit

### Added
- `automation-templates/_matcher/flex.py` — shared intent-mode detection + flexibility
  decision core (stdlib-only). Three modes: EXPLICIT_USER_SPEC / UNSURE_WANTS_SUGGESTION /
  HANDS_OFF_DO_IT_ALL. Four decisions: HONOR_USER / SUGGEST_TEMPLATE / USE_TEMPLATE /
  CREATE_NEW. The module is shared by automation_matcher.py and mirrors the Skill-6
  funnel_matcher retrofit inline copy.
- `automation-templates/_matcher/cli.py` — command-line interface for the matcher
  (--list / --match / --selftest).
- `automation-templates/_matcher/catalog-index.json` — pre-built catalog index
  (avoids filesystem scan on every invocation).
- `automation-templates/_matcher/README.md` — usage guide for the automation library.
- `automation-templates/_matcher/WIRING.md` — how automation_matcher wires into
  the Skill-44 build loop (Step 0.4) and the Skill-6 handoff.
- `automation-templates/_links/_build_link_map.py` — script to regenerate
  `funnel-to-automation.json` from the funnel catalog.
- `automation-templates/_links/funnel-to-automation.json` — canonical link map v2
  (replaces `funnel-to-automation-link-map.json`; both ship for backward compat).
  Maps all 38 Skill-6 funnel templates to Skill-44 follow-up automations with
  primary, secondary, and graduation links. Each link carries a `flexibility` block
  enforcing RECOMMENDED-not-mandatory at the data level.
- `automation-templates/_patches/` — three patch artifacts:
  `_skill44_step0_section.md` (the INSTRUCTIONS.md Step 0.4 prose),
  `skill44-instructions-step0-flexible-match.patch` (diff form of Step 0.4),
  `skill6-funnel-matcher-flexibility.patch` (the Skill-6 retrofit patch).

### Changed
- `automation-templates/_matcher/automation_matcher.py` — upgraded to use `flex.py`
  shared core; standardised decision names (HONOR_USER / SUGGEST_TEMPLATE /
  USE_TEMPLATE / CREATE_NEW); adds `expand_funnel_to_automations()` and the full
  `step0_match()` wiring with funnel link map expansion.
- `INSTRUCTIONS.md` — adds **Step 0.4** (Flexible Template Match) between the
  existing Step 0 (Model Check) and Step 0.5 (PLAN MODE). Step 0.4 defines the
  complete-funnel handoff from Skill 6 to Skill 44 via `funnel-to-automation.json`.

### Flexibility model (standardised)
HONOR_USER (EXPLICIT) — build exactly what the user wants; template = optional ref only.
SUGGEST_TEMPLATE (UNSURE + confident) — recommend + why, await confirm; never build yet.
USE_TEMPLATE (HANDS_OFF + confident) — build the whole automation from the template.
CREATE_NEW (nothing fits or unsure + no match) — generate net-new + save back.
imposes_on_user is ALWAYS false. override_allowed is ALWAYS true. Never blocks.

## [1.1.0] - 2026-06-27 — feat: automation template library + funnel link map + flexible matcher

### Added
- `automation-templates/` — 28 real email/automation templates (not stubs) in 5 categories: welcome-indoctrination (3), sales-close-sequences (7), engagement-broadcast (7), funnel-specific-followups (6), multichannel-automation (5). Each template has a JSON schema + Markdown companion.
- `automation-templates/_links/funnel-to-automation-link-map.json` — maps all 38 Skill-6 funnel templates to their primary and supporting Skill-44 automation templates with rationale and entry event.
- `automation-templates/_matcher/automation_matcher.py` — flexible automation matcher (stdlib-only, deterministic): three-mode GUIDE-NOT-RULE flexibility model, HONORED_EXPLICIT fast path for explicit user desire, funnel-link hint boost, step0_match() wiring, save_new_automation() grow-the-library, CLI with --list / --match / --selftest. 12/12 selftest cases pass.

### Flexibility Model (prime directive)
Mode 1 (Explicit): HONORED_EXPLICIT, no scoring, build exactly what was named.
Mode 2 (Unsure): suggestion with rationale, user decides.
Mode 3 (Just do it): top match built directly.
Neither matcher ever blocks a build. Every element is overridable.

## [1.0.17] - 2026-06-21 — feat: weighted workflow-quality rubric (SUPERSET overlay on WF-1..21) + SMS fromNumber WF-12 hardening

### Added (Workflow-Quality Rubric — non-breaking SUPERSET overlay)
- **references/workflow-quality-rubric.md** — an 8-dimension weighted 1–10 quality grade that
  sits ON TOP of the binary WF-1..21 checklist. Dimensions + weights: D1 Goal-fit (20%),
  D2 Trigger (15%), D3 Steps/ordering (15%), D4 Branching (12%), D5 Edge-cases (12%),
  D6 Deliverability (10%), D7 Idempotency (8%), D8 Naming/testability (8%). Each dimension
  defines its 1/5/10 anchors and CITES its existing WF-1..21 (or `link_steps()`) evidence
  source, so the rubric cannot contradict the current QC and needs no new infrastructure.
- **Ship threshold ≥ 8.5** (aligns with the binding OpenClaw QC Protocol). Below 8.5 → loop,
  naming the specific low dimension. The rubric is computed AT STEP 9 AFTER WF-1..21, never
  instead of it; a high rubric score can never buy back a hard WF FAIL.

### Changed (Step 9 QC GATE wiring — SKILL.md + INSTRUCTIONS.md)
- SKILL.md Step 9 summary + Teach-Yourself read-order + file manifest now reference the rubric.
- INSTRUCTIONS.md adds Step 9.3b (rubric computed after WF-1..21) and updates Step 9.4 verdict
  routing (WF FAIL → fix; rubric < 8.5 → loop naming the low dimension) and Step 9.6 hand-over
  (filled checklist + weighted rubric score).
- **qc-built-workflow.sh** now emits BOTH the WF-1..21 result AND the weighted rubric score
  (a machine-knowable FLOOR per dimension + the human-grade-required flags + lowest dimension),
  in both human-readable and `--json` modes, and logs the rubric floor to the build-events
  ledger. D2 (Trigger) and D3 (Steps/ordering) are fully mechanical; D1/D4/D5/D6/D7/D8 emit a
  conservative floor flagged for the QC sub-agent to grade 1/5/10 and recompute the final score.

### Fixed (WF-12 SMS From-number gap)
- **workflow_builder.py `sms_step`** now ALWAYS emits a `fromNumber` field in the SMS node
  attributes (previously absent entirely → silent send-failure with nothing for WF-12 to read).
  Resolution order: explicit `from_number=` kwarg → `CAF_SMS_FROM_NUMBER` →
  `GOHIGHLEVEL_SMS_FROM_NUMBER` → "" (empty, left for GHL's location-default send-time
  resolution — which is UNPROVEN and surfaced by QC for confirmation before going LIVE).
- **qc-built-workflow.sh WF-12** hardened to mechanically assert every SMS node carries a
  `fromNumber` KEY; on a LIVE/published workflow the value must additionally be NON-EMPTY (FAIL
  otherwise); on a DRAFT an empty From is a surfaced WARNING (pass).

### Non-breaking guarantee
- NO change to `safety_gate.py`, `VERIFIED_ACTIONS` (still 56 types incl. `sms`), or
  `link_steps()`. The rubric reads outputs only. Full existing pytest suite (119 tests) passes.

## [1.0.15] - 2026-06-13 — feat: PLAN→BUILD→QC protocol (plan mode + WF-21 checklist + independent MiniMax QC gate + hallucination escalation)

### Added (PLAN MODE — INSTRUCTIONS.md Step 0.5)
- **Step 0.5 — PLAN MODE** binding gate inserted between Step 0 (model check) and the
  Natural-language intents table in INSTRUCTIONS.md. Fires on any new workflow CREATE/BUILD;
  not triggered by reads, REVIEW/export, or single-step patch-email/patch-trigger on an
  existing workflow.
- Six mandatory steps before any `caf workflows build` call:
  - **Step A — THINK:** reason through A1 (desired result in client's own framing), A2
    (client expectations, honored verbatim when hyper-specific), A3 (best trigger/node/action
    approach for THIS client's goal).
  - **Step B — DEPENDENCY PRE-CHECK:** GET-verify every tag/custom-field/custom-value before
    the build; missing items listed as "must create first"; ZHC-/ZHC_ standing approval noted.
  - **Step C — OUTLINE:** ordered trigger→nodes→exit blueprint with config for each step.
  - **Step D — CHECKLIST:** instantiate references/workflow-build-checklist-template.md for
    this build with all 21 WF items filled.
  - **Step E — IMPROVEMENTS:** optional labeled suggestions alongside (never instead of) the
    client's exact spec.
  - **Step F — PRESENT + GATING QUESTIONS:** present plan to client and ask two mandatory
    gating questions: Q1 publish/draft, Q2 re-entry once/allow-multiple.
- Binding rule: "Rushing to a default build is NOT the best outcome and is a violation."
- `"Build a follow-up workflow"` intent row re-pointed to "PLAN MODE (Step 0.5) first, then
  TRINITY."
- Per-operation decision rule: new sub-rule 2.0 "New workflow build → run PLAN MODE (Step 0.5)
  and get gating answers BEFORE choosing the token/tier path."

### Added (WF-1..WF-21 Checklist Template)
- **references/workflow-build-checklist-template.md** — new canonical 21-item reusable
  checklist serving BOTH the agent self-check (PLAN MODE Step D) AND the client hand-over
  (after QC passes). Covers: name, tags, trigger type+filters, trigger active flag (WF-4
  WF-ACTIVE gate), publish state, re-entry/allow-multiple, action sequence, If/Else conditions,
  wait durations, custom fields, custom values, SMS From-number (WF-12 trigger-active trap), email
  sender, webhooks, delivery chain linkage, advanced settings, edge cases, dependencies,
  TRINITY completeness, hallucination detection (WF-20), and snapshot verification (WF-21).
  Cross-referenced as superset of skill 41's 12-point checklist.

### Added (Step 9 — QC GATE, INSTRUCTIONS.md)
- **Step 9 — QC GATE** binding gate: after build completion, before declaring done.
  Sequence:
  1. Verbatim client announce via `openclaw message send --channel telegram` (mandatory).
  2. Spawn independent MiniMax QC sub-agent via `sessions_send` in a fresh session; prefer
     `minimax/minimax-m3` via OpenRouter or `minimax-m3:cloud`; verify model configured +
     reachable before spawn; fall back to next independent high-reasoning model and log.
  3. QC sub-agent inspects via `caf workflows export <id>` + `qc-built-workflow.sh <id>`;
     returns explicit PASS/FAIL + observed vs expected for each WF-1..WF-21 item.
  4. All-PASS → Step 6. Any FAIL → fix + re-run QC.
  5. ONLY after all-PASS: declare done + hand client the filled checklist.
  6. Log QC run to build-events ledger (model used, per-item verdicts, pass/fail, escalation).
- **Hallucination escalation sub-section:** when QC class=HALLUCINATION (build-agent-claimed
  TRUE, QC-observed FALSE): hard stop; v12.3.5 Step 0 recommendation FLIPPED TO REQUIREMENT
  (redo must use high-reasoning model + thinking=HIGH); full re-QC from scratch; honest client
  disclosure; ledger log.

### Added (qc-built-workflow.sh — per-build QC script)
- **qc-built-workflow.sh** — new per-build QC script (DISTINCT from install-level
  qc-convert-and-flow.sh). Takes `<workflow-id> [--publish-intent DRAFT|LIVE]
  [--re-entry ONCE|ALLOW-MULTIPLE] [--json]`. Machine-asserts WF-3 (trigger present),
  WF-4 (trigger active vs publish-intent — WF-ACTIVE gate), WF-5 (publish status), WF-6
  (re-entry setting), WF-7 (action nodes present), WF-12 (SMS From-number non-empty),
  WF-15 (delivery chain linkage), WF-18+WF-21 (snapshot exists). Emits per-item PASS/FAIL
  JSON. Appends to build-events ledger. Exit 0=all-pass, 1=fail, 2=prereq-error.

### Added (qc-convert-and-flow.sh Section S static assertions)
- 35 new static assertions in Section S covering: Step 0.5 PLAN MODE present + all binding
  rules, Step 9 QC GATE + announce template + MiniMax dispatch + checklist handover, checklist
  template exists with all 21 WF items + WF-ACTIVE/SMS gates + hallucination detector + skill 41
  cross-ref, qc-built-workflow.sh present + executable + per-item assertions, CORE_UPDATES
  AGENTS.md block has all 3 new rules (plan-mode, QC-gate, hallucination→reasoning-HIGH).

### Changed (SKILL.md)
- READ-BEFORE-ACT block extended with Step 0.5 PLAN MODE + Step 9 QC GATE summaries.
- Teach Yourself read-order updated (references/workflow-build-checklist-template.md item 4,
  qc-built-workflow.sh item 5; existing items renumbered).
- Files in this folder list updated (items 9, 16 added).

### Changed (CORE_UPDATES.md AGENTS.md block)
- Three new binding rules prepended to the Convert and Flow Operator AGENTS.md section so
  every client agent inherits them on session start:
  1. PLAN MODE before build (think→outline→checklist→recommendations→gating questions).
  2. Independent MiniMax QC + checklist hand-over before declaring done.
  3. Hallucination → reasoning-model-thinking-HIGH (hard requirement, not recommendation).

### Scope
- Engine builder code under tools/engine/ is UNTOUCHED (docs/protocol + QC-script release).
- Engine CLI version unchanged (2.1.1).
- total_roles UNCHANGED (335).

---

## [1.0.13] - 2026-06-13 — docs: model-recommendation pre-flight warning for workflow builds

### Added (Step 0 model check — recommendation gate, not a hard block)
- **INSTRUCTIONS.md Step 0** — new "Model Check Pre-flight" section at the top of
  INSTRUCTIONS.md, triggered before any workflow BUILD or MODIFY action. Checks the
  active session model/thinking level; if lighter/non-high-reasoning or thinking not HIGH,
  surfaces a clear recommendation to the owner before proceeding. Proceeds on owner
  acknowledgement ("proceed anyway") — never blocks. Read-only ops exempt.
- **SKILL.md READ-BEFORE-ACT block** — a short "READ-BEFORE-ACT" callout added above
  the Teach Yourself Protocol, pointing to INSTRUCTIONS.md Step 0 for the model check.
- **CORE_UPDATES.md AGENTS.md block** — a concise pre-flight note prepended to the
  Convert and Flow Operator AGENTS.md section so every client agent sees the check rule
  every session.

### Motivation
A lighter model previously hallucinated a workflow's failure cause, a fake link, and a
wrong number — turning a 2-minute fix into a 12-hour debugging loop. This warning
surfaces the risk before the build starts and routes the operator to a better model when
needed, without blocking work when the owner chooses to proceed.

---

## [1.0.11] - 2026-06-11 — fix: wire GHL creds into gateway-inherited env + fail-loud live verify (VPS env-inheritance bug reproduction)

### Fixed (install env-wiring gap — root cause of caf dying on a "successful" install)
- **Creds landed only where the gateway process never reads them.** The installer
  left `GOHIGHLEVEL_*` in `~/.openclaw/secrets/.env` — a file the OpenClaw
  gateway/agent **process never loads.** When the agent invoked `caf`, the
  gateway's process env had no `GOHIGHLEVEL_LOCATION_ID`, so the engine died at
  `Error: GHL_LOCATION_ID environment variable is not set.` while the install had
  already reported success. **Reproduced live on a client VPS, 2026-06-11.**
- **Empty docker `env_file` placeholders masked everything (VPS).** The Hostinger
  compose `env_file` (`/docker/<project>/.env`) carried empty placeholder lines
  (`GOHIGHLEVEL_API_KEY=` with no value, no FIREBASE line). docker-compose injects
  an empty `env_file` value as an **empty string** into the container process env,
  and an empty string still wins against the secrets file for any consumer that
  reads `os.environ` — so it masked the real value even after it was added
  elsewhere. Empty placeholders are now **replaced in place**, never appended-after.

### Added (`tools/engine/wire-ghl-env.sh` — single-source env wiring)
- Wires all **5** canonical vars (`GOHIGHLEVEL_API_KEY`, `GOHIGHLEVEL_LOCATION_ID`,
  `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN`, `GOHIGHLEVEL_ALLOWED_LOCATION_IDS`,
  `GOHIGHLEVEL_DRAFT_ONLY`) into `openclaw.json` `env.vars` — the block the gateway
  inherits at process start. Tries `openclaw config set` first; **falls back to a
  direct JSON deep-merge** into `openclaw.json` when `config set` rejects the
  nested key (the supported pattern on OpenClaw 2026.5.20+, same as
  `31-upgraded-memory-system/scripts/activate-memory-stack.sh`).
- **VPS:** ALSO populates the host `/docker/<project>/.env`, REPLACING empty
  `GOHIGHLEVEL_*=` placeholder lines in place (with a logged note on why empty
  placeholders mask). Auto-finds the OpenClaw project under `/docker`; skipped
  cleanly when `/docker` is not visible (inside the container).
- **Mac:** wires `env.vars` but does NOT restart the gateway (rescue-Mac rule);
  documents that a `launchctl kickstart` may be needed for full inheritance.
- Exit 2 (required var absent everywhere) lets the caller mark the skill
  installed-with-missing-prereqs and list exactly which vars — never a fabricated
  success.

### Added (`tools/engine/verify-ghl-live.sh` — fail-loud post-install verify gate)
- Runs a **real read** against GHL using **ONLY the inherited process env** (no
  manual secrets sourcing — reproduces exactly what the gateway/agent process
  sees): `caf workflows list`, falling back to `caf contacts list --limit 1`
  (PIT-only, since workflow reads can legitimately fail without the Firebase
  token). **FAILS LOUDLY (exit 1)** if creds are present but caf can't reach GHL
  (the VPS env-inheritance failure mode). Exit 2 = installed-with-missing-prereqs (lists the
  vars). Exit 0 = live-verified. The install path NEVER reports skill-44 success
  on exit 1.

### Wired into both install paths
- **`INSTALL.md` Action 5** rewritten to call `wire-ghl-env.sh` (single source, no
  inline `config set` drift); **new Action 6b** runs the fail-loud verify gate;
  Action 2 chmods the two new scripts; "Done When" updated.
- **Root `install.sh` Step 14e** (`install_skill_44_convert_and_flow_operator_env`)
  runs both scripts as part of the orchestrated install, with the same
  fail-loud / missing-prereqs semantics.

### Added (CI + QC)
- `.github/workflows/skill44-install-path.yml` — new job `install-path-env-wiring`
  asserting both scripts exist, the deep-merge fallback + docker placeholder-replace
  logic is present, INSTALL.md Action 5 calls `wire-ghl-env.sh`, and Action 6b runs
  `verify-ghl-live.sh`.
- `qc-convert-and-flow.sh` — Section S assertions for the two scripts, the
  env-wiring call, and the verify gate.

### Scope note
- Installer / env-wiring only. Engine builder code is untouched (a separate branch
  `caf-engine-folder-hardening` owns engine fixes).

## [1.0.10] - 2026-06-11 — docs: world-first "just by talking" hype in owner-facing copy

Docs-only release. No engine, wrapper, or CLI behaviour changed (CLI stays `2.1.1`). Per the
repo G3 guard (any change inside a skill folder requires a `skill-version.txt` bump), the
skill version moves `1.0.9` -> `1.0.10` to carry the copy update with the skill payload.

### Changed
- **`references/fleet-announcement-template.md`** — MESSAGE 1 of the canonical 3-message
  template: same structure (🎉 congrats → what it unlocks → one final 5-min token setup →
  next two messages → reach Trevor), but the "what it unlocks" middle now leads with the
  fact the owner builds workflows **just by talking** to [AGENT_NAME] (plain chat message →
  draft to review; no clicking, no tech setup, no tutorials) and states plainly that this is
  the **only system in the world** that can do this right now, installed on the owner's own
  setup. Placeholders `[OWNER_NAME]` / `[AGENT_NAME]` unchanged.
- **`references/owner-token-grabber-guide.md`** — the "What this unlocks for you" intro now
  weaves in the same two beats (build automations **just by talking** + **only system in the
  world** that does this right now). The 8 setup steps and the FOR THE AGENT wiring section
  are untouched.

### Not changed
- Engine (`2.1.1`), wrapper, CLI surface, write-safety posture, the token-setup steps, and
  all tests are untouched. This release ships owner-facing copy only.

## [1.0.9] - 2026-06-11 — docs: standardized fleet announcement template + send runbook

Docs-only release. No engine or wrapper behaviour changed; the CLI version stays `2.1.1`.
Per the repo G3 guard (any change inside a skill folder requires a `skill-version.txt`
bump), the skill version moves `1.0.8` -> `1.0.9` to carry the new doc with the skill payload.

### Added
- **`references/fleet-announcement-template.md`** — the ONE canonical owner-facing Skill 44
  announcement, sent fleet-wide once a box has been given Skill 44. Two parts:
  - **The canonical 3-message template** (placeholders `[OWNER_NAME]` / `[AGENT_NAME]`,
    verbatim from what was sent to the first fleet clients): Message 1 = 🎉 congratulations +
    plain-English "what it unlocks" (the agent BUILDS Convert & Flow automation workflows as
    drafts to review — appointment follow-ups, lead-nurture, tag-and-text) + the "one final
    5-minute one-time token setup" framing + the "reach out to Trevor" offer; Message 2 =
    🔑 FINAL SETUP Part 1 of 2 (token explainer + Chrome Token Grabber, steps 1️⃣–5️⃣: download
    from the public Drive link, unzip, `chrome://extensions`, Developer mode ON, Load unpacked,
    pin the 🧩); Message 3 = 🔑 FINAL SETUP Part 2 of 2 (steps 6️⃣–8️⃣: log out/in, grab + copy,
    paste the canonical "Here is the Convert and Flow GHL Firebase token: …" message, then
    "Use Skill 44 and create me a test workflow").
  - **The operator-facing fleet-send runbook**: the GATE (only announce when the box's ledger
    shows skill44 remediation complete — caf engine ≥ 2.1.1 with a live `caf` read, or
    explicitly token-pending where the announcement IS the token ask; never announce a
    capability that is not live on the box), SEND MECHANICS (always the client's OWN OpenClaw
    gateway via `openclaw message send --channel telegram` — never the direct Telegram API;
    one client at a time; substitute the roster names; verify exit code + message id before
    the next; 3 messages in order), RECEIPTS (per-client JSON line appended to the operator
    ledger), and the already-announced list (fleet client msg ids / prior announce, both
    2026-06-11) to prevent duplicate sends.

### Changed
- `SKILL.md` — the Token Grabber section now points to the new fleet-announcement template
  (a "Fleet announcement" subsection beside the owner-facing setup guide), and the "Files in
  this folder" list includes `references/fleet-announcement-template.md` (item 14).

### Not changed
- Engine (`2.1.1`), wrapper, CLI surface, write-safety posture, and all 119 tests are
  untouched. This release ships documentation only.

## [1.0.8] - 2026-06-11 — docs: owner-facing Token Grabber setup guide + agent wiring notes

Docs-only release. No engine or wrapper behaviour changed; the CLI version stays `2.1.1`.
Per the repo G3 guard (any change inside a skill folder requires a `skill-version.txt`
bump), the skill version moves `1.0.7` -> `1.0.8` to carry the new doc with the skill payload.

### Added
- **`references/owner-token-grabber-guide.md`** — a NEW owner-facing explainer a client
  agent can send or walk a non-technical business owner through. Plain-English description
  of what Skill 44 unlocks (the agent builds Convert & Flow / GHL automation workflows as
  DRAFTS the owner reviews: appointment follow-ups, lead nurture, tag-and-text), the
  prominent public download link for the Convert & Flow Token Grabber Chrome extension, and
  the polished 8-step one-time setup (download/unpack → `chrome://extensions` → Developer
  mode → Load unpacked → pin the 🧩 → log out/in → grab + copy → paste to agent).
- A clearly-separated **FOR THE AGENT** section inside the same doc: wire the pasted token
  as `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN` into the gateway-inherited env (`openclaw config
  set env.vars.*`; on Hostinger VPS also replace the empty `/docker/<project>/.env`
  placeholder + `--force-recreate`), verify with a real `caf` read on the inherited env,
  then build the test workflow DRAFT-only with a `ZHC-` prefixed name, retrying once on a
  transient "token refresh failed" before reporting any problem.

### Changed
- `SKILL.md` — the "Chrome Extension: Token Grabber" section now points to the new
  owner-facing guide, and the "Files in this folder" list includes
  `references/owner-token-grabber-guide.md` (item 13).

### Not changed
- Engine (`2.1.1`), wrapper, CLI surface, write-safety posture, and all 119 tests are
  untouched. This release ships documentation only.

## [1.0.7] - 2026-06-11 — fix: ZHC- folder standing approval + top-level `folder` plan-key hardening (both reproduced live on a client box)

Two surgical engine fixes, both confirmed live on a managed client VPS box
by an Opus diagnostic 2026-06-11. These are NEW bugs — disjoint from the 1.0.3
400 `corrupted order` fix (already shipped).

### Fixed (CRITICAL — engine `workflow_builder.py`)
- **Bug 2a — folder-creation POST bypassed ZHC- standing approval.**
  `CampaignBuilder._build_locked` created the campaign folder with
  `self.client.request("POST", f"/workflow/{loc}", {"name": folder_name, ...})`
  WITHOUT passing `workflow_name`. The safety gate (`safety_gate._is_approved`)
  only inspects `workflow_name` for the ZHC-/ZHC_ standing-approval prefix, so it
  saw an empty string and **demanded `CAF_APPROVAL_TOKEN` even when the FOLDER
  name was ZHC-prefixed** — the build refused at the folder step despite a
  ZHC- folder name that should be standing-approved exactly like a ZHC- workflow
  name. Fix: pass `workflow_name=folder_name` on the folder POST. Non-ZHC folder
  names still require a token (gate behaviour unchanged).

### Fixed (CRITICAL — engine CLI `gohighlevel_cli.py` `workflows build`)
- **Bug 2b — a top-level `"folder": "<name>"` plan key crashed the builder with
  `TypeError: string indices must be integers`.** The `workflows build` handler
  read `campaign.get("folder")` for the folder name but passed the WHOLE plan
  dict (including the bare-string `folder` value) into `CampaignBuilder.build()`,
  which iterates every value as a workflow dict (`wf_def["name"]`) — indexing a
  string with `"name"` raised the TypeError. Fix: `pop` `folder` out of the plan
  dict before iterating; use the popped value as the folder name when `--folder`
  was not supplied; `--folder` wins when both are present. After the pop, every
  remaining entry must be a workflow object — the handler now **fails loud** with
  a clear message listing the offending non-dict entries (and exits non-zero)
  instead of surfacing a raw TypeError.

### Changed
- Engine CLI version bumped `2.1.0` -> `2.1.1` (behaviour: folder POST carries
  the folder name for ZHC- standing approval; build pops/validates the `folder`
  plan key).

### Added
- Regression tests `TestZHCFolderStandingApprovalAndFolderKeyPlan` in
  `tools/engine/tests/test_e2e_unit11.py`:
  - **TEST A** — a ZHC- folder name + ZHC- workflow name, NO `CAF_APPROVAL_TOKEN`:
    build exits 0 and the folder-creation POST carries `workflow_name=<ZHC folder>`
    (FAILS on pre-fix main, where the missing name triggers a SAFETY GATE refusal /
    non-zero exit).
  - **TEST B** — a plan with a top-level `"folder": "<name>"` string key builds
    successfully (no TypeError), the folder key is consumed as the folder name,
    and is NOT iterated as a workflow.
  - **TEST C** — `--folder` wins over the plan `folder` key when both are present.
  - **TEST D** — a non-dict, non-`folder` top-level entry fails loud (non-zero
    exit, clear message) rather than raising a raw TypeError.
- `TestZHCFolderApprovalGate` in `tools/engine/tests/test_safety_gate.py`:
  unit-level proof that `check_write` with `workflow_name="ZHC-Folder"` and NO
  token passes (the gate-side contract Bug 2a relies on).

### Not changed (safety gate preserved exactly)
- Fail-closed location whitelist, the approval gate semantics for non-ZHC names,
  dry-run refusals, draft-only default, the 1.0.3 build fail-loud / `link_steps`
  ordering, and the 1.0.4 token retry-once are all untouched.

## [1.0.6] - 2026-06-11 — fix: install auto-applies CORE_UPDATES + de-dup wrapper (single source) + CI install-path test

### Fixed (install integrity — root cause of boxes not knowing skill 44 is installed)
- **CORE_UPDATES were never auto-applied by INSTALL.md.** The "Done When" checklist listed
  the sentinel as a requirement, but no Action step actually wrote it. Agents on boxes where
  skill 44 was installed pre-this-fix had no `<!-- skill:44-convert-and-flow-operator:core-update-applied -->`
  in AGENTS.md / TOOLS.md / MEMORY.md, so the agent had no knowledge of Tier 0 and
  fell through to MCP on every GHL op. Added **Action 7** to INSTALL.md: idempotent script
  (guard checks for sentinel first) that appends the exact CORE_UPDATES.md blocks to
  AGENTS.md, TOOLS.md, and MEMORY.md automatically at install time.

### Fixed (wrapper single source — eliminates heredoc drift)
- **INSTALL.md Action 3 re-declared the wrapper as an inline heredoc**, creating a second
  copy of the wrapper logic that could silently diverge from `tools/engine/caf` (exactly how
  the `gohighlevel.main` bug in PR #167 happened: the engine wrapper was correct but the
  heredoc was stale). Action 3 now `cp`s the committed `tools/engine/caf`,
  `tools/engine/convertandflow`, and `tools/engine/ghl` wrappers to `$CAF_DIR/` instead of
  re-writing them inline. Single source — one place to edit wrapper logic, zero drift.

### Added (CI install-path test)
- **`.github/workflows/skill44-install-path.yml`** — new CI job `skill44-install-path` with
  two checks that run on every PR touching `44-convert-and-flow-operator/**`:
  1. `install-path-wrapper-exec` — asserts `tools/engine/caf` exec line is
     `python -m cli_anything.gohighlevel` (not `.main`), and that the `convertandflow`/`ghl`
     wrappers match. Fails on pre-#167 exec line. Guards against entrypoint drift.
  2. `install-path-core-updates-action` — asserts INSTALL.md contains the CORE_UPDATES
     auto-apply action (sentinel grep + `skill:44-convert-and-flow-operator:core-update-applied`
     present in Action 7 block). Fails without this fix.
  The workflow is additive — does not replace `skill44-e2e.yml`.

### QC (qc-convert-and-flow.sh)
- Two new static assertions in Section S:
  - `INSTALL.md contains CORE_UPDATES auto-apply action (Action 7)`
  - `INSTALL.md Action 3 uses cp (single-source wrapper, no inline heredoc)`

## [1.0.5] - 2026-06-11 — fix: INSTALL.md Action-3 heredoc used stale `cli_anything.gohighlevel.main` entrypoint (no `main.py` in engine 2.1.0)

### Fixed (install path)
- **INSTALL.md Action-3 heredoc** exec line corrected from
  `exec "$VENV/bin/python" -m cli_anything.gohighlevel.main "$@"` to
  `exec "$VENV/bin/python" -m cli_anything.gohighlevel "$@"`.
  Engine 2.1.0 (shipped in PR #163) removed `main.py` — the package entry point
  is now `__main__.py` which routes to `gohighlevel_cli:main`. The stale
  `.main` suffix caused `ModuleNotFoundError` on every `caf` invocation on any
  box installed with the 2.1.0 engine via INSTALL.md. The three committed wrapper
  scripts (tools/engine/caf, convertandflow, ghl) were already correct and are
  unchanged.

### Root cause
  Engine CLI was bumped 2.0.0 → 2.1.0 in PR #163; `main.py` was removed but the
  INSTALL.md heredoc was not updated to match. Boxes receiving the 2.1.0 engine
  via the heredoc install path broke silently; boxes that copied the committed
  wrapper scripts (e.g. hand-patched) were unaffected.

## [1.0.4] - 2026-06-11 — fix: retry-once on the transient Firebase token-refresh error for workflow writes

### Fixed (engine `internal/transport.py`)
- **Transient Firebase token-refresh failure now auto-retries ONCE before
  surfacing.** The securetoken refresh exchange can return `None` as a ONE-TIME
  transient (observed live on a managed box) and succeed on the very next call;
  the old code raised `TOKEN_REFRESH_FAILED` on the first `None`, falsely nudging
  the owner to re-grab a token that was still valid. `InternalTransport.get_token()`
  now retries the exchange **exactly once** on a `None` result, and only raises
  `TOKEN_REFRESH_FAILED` if the second attempt also fails. This is one retry, not
  a loop, and is disjoint from the existing request()-level 401/403 retry.

### Preserved (NOT weakened)
- The PR #163 build-path **fail-loud** behaviour is untouched: a downstream HTTP
  error dict (e.g. the 400 `corrupted order` save rejection) is returned UNCHANGED
  by `transport.request()` and never triggers a token-refresh exchange. Only a
  `None` from the securetoken exchange (transient) is retried; only a `None` from
  `_do_request` (401/403 auth signal) drives the separate one-shot `force_refresh`.

### Added
- `tools/engine/tests/test_token_retry.py` (`TestTokenRefreshRetryOnce`):
  - transient failure -> ONE retry -> success (exactly 2 exchange attempts);
  - persistent failure -> `TOKEN_REFRESH_FAILED` surfaced after one retry (exactly
    2 attempts — proves no loop);
  - happy path -> single attempt (never retried);
  - HTTP `_error` dict (400 corrupted-order) -> surfaced unchanged, no refresh
    triggered (guards the PR #163 fail-loud).
  The two retry tests FAIL on pre-1.0.4 transport and PASS after the fix.

## [1.0.3] - 2026-06-11 — fix: `workflows build` now ADDS action ordering and FAILS LOUD on rejected save; opportunities list snake_case params; payments list alias

### Fixed (CRITICAL — engine `workflow_builder.py`)
- **Bug 1a — `workflows build` omitted action ORDERING on the save PUT** (GHL rejected with
  400 `corrupted order`). `CampaignBuilder._create_workflow` now runs `link_steps()` on the
  plan templates ONCE up front and uses that linked copy (carrying `order`/`next`/`parentKey`)
  for the Step-2 first-step link, the Step-3 step-save PUT body, AND the Step-4 sync PUT.
  Previously `link_steps` was defined but never called on the build path, so the very first
  save PUT had zero execution chain and GHL rejected it.
- **Bug 1b — `workflows build` SWALLOWED a non-2xx save and printed `Steps: 0, Errors: 0`
  (false success, exit 0).** A rejected step-save PUT (transport returns
  `{"_error": True, "http_code": 400, ...}`) is now captured as a real error string
  (including HTTP code + message), returned from `_create_workflow`, and appended to
  `stats['errors']` UNCONDITIONALLY (not gated on the workflow-shell id). The CLI
  (`workflows build` / `workflows create` / `workflows create-n8n`) now prints the error
  summary to stderr and exits non-zero whenever `stats['errors']` is non-empty.

### Fixed (engine CLI `gohighlevel_cli.py`)
- **Bug 3 — `opportunities list` 422 from camelCase params.** `GET /opportunities/search`
  now sends snake_case `location_id`/`pipeline_id` (the one search endpoint that diverges
  from the camelCase convention). The create/update BODIES (camelCase) are unchanged.
- **Bug 4 — `payments` had no `list` verb.** Added a thin `payments list` alias that
  forwards to `payments transactions`, so the uniform `<group> list` pattern works.
  Explicit `transactions`/`orders`/`invoices` verbs are unchanged.

### Changed
- Engine CLI version bumped `2.0.0` -> `2.1.0` (behavior change: build applies ordering and
  fails loud on a rejected save).

### Added
- Regression tests `TestBuildFailsLoudAndEmitsOrdering` in
  `tools/engine/tests/test_e2e_unit11.py`:
  - TEST A asserts a rejected step-save exits non-zero with the 400/`corrupted order`
    cause surfaced (guards the exact pre-fix Steps:0/Errors:0/exit-0 false-success shape).
  - TEST B asserts the FIRST (step-save) PUT body carries `order` `[0,1,2]` plus
    `next`/`parentKey` links — proving `link_steps` ran BEFORE the save PUT.
  Both tests FAIL on pre-fix main and PASS after the fix.
- `qc-convert-and-flow.sh` static asserts for the build-path `link_steps`, CLI fail-loud,
  snake_case opportunities params, payments list alias, the regression test, and the
  `convertandflow`/`ghl` wrapper auto-seed parity.

### Hardening (consistency, not a blocker)
- `tools/engine/convertandflow` and `tools/engine/ghl` wrappers now apply the same
  `CAF_ALLOWED_LOCATION_IDS` auto-seed-from-`GHL_LOCATION_ID` logic that `caf` got in 1.0.2,
  so a blank whitelist never silently blocks all writes on any of the three runtime wrappers.
- `INSTALL.md` Action 3 installed wrapper now exports `CAF_ALLOWED_LOCATION_IDS` /
  `CAF_DRAFT_ONLY` / `CAF_DRY_RUN` (the exact names `safety_gate.py` reads) instead of the
  `GHL_`-prefixed names the gate ignores — matching the shipped engine wrappers.

### Not changed (safety gate preserved exactly)
- Fail-closed location whitelist, approval gate, and dry-run refusals (all `sys.exit(1)` on
  `SafetyRefused`). Draft-only default. `STRIP_KEYS`. Transport 401 retry-once / 429 no-retry.

## [1.0.2] - 2026-06-11 — fix: CAF_ALLOWED_LOCATION_IDS auto-seeds from GOHIGHLEVEL_LOCATION_ID at install

### Fixed
- `tools/engine/caf` (engine wrapper): `CAF_ALLOWED_LOCATION_IDS` no longer defaults to
  blank, which silently blocked every write on a fresh single-location install. When neither
  `GOHIGHLEVEL_ALLOWED_LOCATION_IDS` nor `CAF_ALLOWED_LOCATION_IDS` is set, the wrapper now
  seeds the whitelist from `GHL_LOCATION_ID` (i.e. the client's own location) and emits:
  `[caf] Allowed write locations set to <id>; add more in CAF_ALLOWED_LOCATION_IDS`
- `INSTALL.md` Action 3 (installed wrapper written to disk): same auto-seed logic applied
  so the problem cannot re-emerge after a fresh install.
- `INSTALL.md` Action 5 (credential wiring step): now explicitly wires
  `GOHIGHLEVEL_ALLOWED_LOCATION_IDS` via `openclaw config set` to `$GOHIGHLEVEL_LOCATION_ID`
  as the initial value, matching the auto-seed logic.

### Added
- `INSTALL.md` "Note: Write-location whitelist auto-seed" section explaining the behaviour,
  the log line, and how to add additional sub-account IDs for multi-location setups.

### Not changed
- Draft-only default (`GOHIGHLEVEL_DRAFT_ONLY=true`) untouched.
- Approval gate untouched.
- Engine internals untouched.

## [1.0.1] - 2026-06-11 — Chrome extension: switch to load-unpacked (no Chrome Web Store)

### Changed
- Chrome extension delivery method: NOT publishing to the Chrome Web Store.
  Clients load the extension unpacked via chrome://extensions → Developer mode ON →
  "Load unpacked" → select tools/chrome-extension/.
- INSTALL.md: added Action 5b with full load-unpacked steps (get folder, install,
  grab token, store as GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN, reload after edits).
- SKILL.md: added "Chrome Extension: Token Grabber" section documenting the no-web-store
  decision, what the extension does (zero network calls, IndexedDB reader), and the
  tools/chrome-extension/ file manifest.
- tools/chrome-extension/: added as top-level client-facing copy of the extension
  (manifest.json, popup.html, popup.js, icon48.png — identical to the zip the operator
  ships). Skill is now self-contained.

## [1.0.0] - 2026-06-10 — Initial release

### Added
- Full Tier 0 GHL operator: caf/convertandflow/ghl CLI wrapper over the de-branded
  Convert and Flow engine (Jay's zip, stripped of Nextcloud/Blotato, de-branded builders,
  Chrome extension rebranded, UNIVERSAL templates).
- Token-aware routing: PIT for standard ops; Firebase refresh token for workflow writes;
  graceful fall-through to Tier 4 when Firebase token absent.
- Write-safety posture: dry-run, draft-only default (GOHIGHLEVEL_DRAFT_ONLY=true),
  location whitelist, approval gate, ZHC- standing approval.
- Workflow-write data rollback: pre-write snapshot before every mutation; `workflows restore`.
- TRINITY gate: any conversational workflow build auto-invokes skill 38; qc-convert-and-flow.sh
  calls qc-trinity-registry.sh as a hard gate.
- Dependency-first contract from skill 41: refuses to build if dependencies don't exist.
- Engine vendored at tools/engine/ (from skill44-build/engine).
- Platform overlays: platform/mac/ (venv at ~/.openclaw/tools/..., auto-re-grab recipe) +
  platform/vps/ (venv at /data/.openclaw/tools/..., owner-nudge on expired token).
- Client-facing plain-language auto-re-grab disclosure in INSTALL.md (binding transparency).
- qc-convert-and-flow.sh with assertions for all acceptance criteria.
