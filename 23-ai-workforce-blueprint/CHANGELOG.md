## [v14.13.0] - 2026-06-27 - fix(presentations): separate free EVENT price from paid OFFER price in the Brainstorming-Buddy-Presentations interview (Skill 23 v2.2.0)

Separated EVENT/ACCESS price from OFFER price across the Brainstorming-Buddy-Presentations interview. Added `EVENT_PRICE` / `EVENT_ACCESS_MODE` as a distinct axis from `OFFER_STACK` / `FINAL_PRICE` / `PRICE_MODE`. Split the old conflated Q4 into Q4a (EVENT ACCESS PRICE — free or paid to attend) and Q4b (THE OFFER + PRICE — what is sold at the end), asked as two separate questions. Devil's-Advocate ALWAYS-PITCH-SOMETHING doctrine: a free event defaults `pitch_included: true` + `expect_paid_offer: true` (both `assumed: true`), surfaced at the SOP 9.3 read-back; free-only close requires explicit owner sign-off. Brainstorming-Buddy role version bumped 2.1 -> 2.2.

## [v14.11.1] - 2026-06-27 - fix(leadership-wiring): persona Task-Mode governance now fires at task time

`persona-matching-protocol.md` gains "Step 5: Load and Apply the Task Mode" (the concrete at-task-time load of
Section 4 + Definition of Done). Every role-library `## 2. Persona Governance Override` now carries the concrete
load step (run the persona search → open the matched blueprint → apply Section 4 → self-verify), so a role is no
longer silently dependent on a missing AGENTS.md Reflex; content-hash manifest restamped. `full-funnel-pipeline`
R-PERSONA-GROUNDING gains a graduated `task_mode_applied` sub-check so persona grounding means governance-applied,
not just name-surfaced (committed live-run stays the single documented residual at 8.43). Guarded by
`tests/unit/persona-task-mode-wiring.test.sh` + `persona-task-mode-wiring-guard.yml`.

## [v14.8.0] - 2026-06-27 - feat(org-wiring): template-first / reuse-before-reinvent wired into the roles, SOPs, and dept guides

Pointer references + a template-first MANDATE (flexibility = guide-not-rule) added so the agent identities that DO funnel/automation work actually consult the shipped libraries instead of hand-reinventing:
- `funnel-strategist.md` SOP 9.5 — new Step 1.5 (run `funnel_matcher` against `06-ghl-install-pages/funnel-templates/`) + `funnel_template_id` / `linked_automations` on the funnel-spec.json schema + Tools rows.
- `automation-workflow-specialist.md` SOP 9.6 — new Step 0.4 (run `automation_matcher` against `44-.../automation-templates/` + the `_links` map keyed by `funnel_template_id`) + Tools rows.
- `conversion-copywriter.md` SOP 9.2 Step 0f — reuse the matched funnel template `copyFramework` as the copy scaffold.
- Pointer references added to email-campaign / follow-up-sequence / sms-whatsapp-dm / webinar-event / lead-magnet / customer-journey / funnel-builder / landing-page specialists.
- `how-to-use-this-department.md` (marketing/crm/web-development/sales) gain a "Reusable libraries" section.
- Governance standard added to CMO / CSO / Director-of-CRM / Head-of-Web-Dev.
- `master-orchestrator-dept/SOP-07` P1/P5 dispatch carry the matchers + the FAB-QC ≥ 8.5 gate, P4→P5 handoff carries `funnel_template_id` + `linked_automations`, and the hardcoded `hormozi-100m-offers` P1 persona is replaced with the top-ranked-selector rule.

The shipped funnel/automation templates and personas are unchanged — this is wiring + pointer references only.

## [v14.1.5] - 2026-06-25 - fix(resume-cron): durable PARK gate + consecutive-stuck hard cap (kills the never-stop furnace)

`scripts/resume-workforce-build.sh` no longer re-fires a stuck build forever. The old "Rule 8 / NEVER-STOP run accounting" (slow-to-2h-and-retry-forever) is replaced by: (1) a durable PARK gate — if the box-level park marker is set (an operator park, or an agent-browser breaker trip), the cron STOPS and self-removes; (2) a consecutive-no-progress hard cap (`MAX_STUCK_FIRES`, default 24, override `WORKFORCE_RESUME_MAX_STUCK_FIRES`) that PARKS + escalates once + DISABLES the cron. A progressing build never trips it (the counter resets the moment build state advances); pre-interview / pre-seed phases are never parked. `resume-prompt.txt` gains a PARK-STOP so the current agent fire stops too. Un-park is operator-only (`scripts/unpark-build.sh`). See root CHANGELOG v14.1.5.

## [v12.17.2 / skill build] - 2026-06-15 - fix(sop-gate): widen SOP_BLOCK_RE + extend fill_tokens token map (0/406 → 327/406 SOP floor)

See root CHANGELOG.md for full details. Two deterministic fixes: (1) qc-completeness.sh SOP_BLOCK_RE widened to match `### SOP-01:` / `### SOP-AUDIO-001:` / `### SOP-01 —` formats in addition to dotted `### SOP 9.x`; (2) fill_tokens in create_role_workspaces.py extended from ~8 to 400+ tokens, eliminating all TOKEN_LEAK_RE hits in built output.

---

## [v12.7.0] - 2026-06-14 - feat: Quality Control department (the fleet-wide quality function that owns and runs the system analyzer); mandatory floor raised 28 to 29

New canonical, fleet-wide MANDATORY department shipped to every Zero Human Company. Quality Control owns and operates the ZHC System Analyzer: it reads every OTHER department's roles and standard operating procedures and holds them to the standard on two independent axes, reported side by side: Axis 1 Reality (is each mechanism actually executed at runtime, with file-and-line proof, never from prose) and Axis 2 Specificity / right-sizing (can an autonomous worker who has never seen the business run each procedure end to end without guessing, with the hard allowance that a procedure may run up to roughly 7,500 words when it earns it; brevity is never a merit; artificially thin procedures are flagged). The department diagnoses; it never repairs in place. Every failure it finds is filed to the Bugs Department and routed to the Healer.

### Changes

**A. New department `templates/role-library/quality-control/` (3 roles, all live):**
- `director-of-quality-control.md` (head; Trevor may rename) - owns the standard and operates the analyzer: maintains the two-axis rubric, the four specificity classes, the six mechanical auto-flags, the up-to-7,500-word allowance, and the visual scorecard; runs the per-department audit fan-out; assembles the system-wide rollup; signs every ship-or-hold; routes every failure to the Healer.
- `role-auditor.md` - audits role documents (reality B-dimensions + the role-document specificity overlay), hunts the summarized-away anti-pattern explicitly.
- `procedure-auditor.md` - audits standard operating procedures (the six fail-closed auto-flags, the reality checks, the eight specificity dimensions with the three autonomous-execution-floor dimensions weighted double, the earned-length test above 3,000 words).
- `00-START-HERE.md` - department front door (what it does, the two axes, the role roster, the SOP mirror index, the audit fan-out, the four classes, the six auto-flags).
- `sops/` - four executable SOPs mirrored from the role files: Q-9.1 Audit a Department's Procedures, Q-9.2 Audit a Department's Roles, Q-9.3 System-Wide Quality Rollup, Q-9.4 Maintain the Standard. Each carries purpose, the hard rule, the enforcement check, generic pass-versus-fail examples (no client names), and escalation to the Healer.

**B. Mandatory canonical floor raised 28 to 29 (22 mandatory + 7 universal-primary), computed live:**
- `department-naming-map.json` (v2.5.0 to v2.6.0): added `quality-control` to `.mandatory` with `suggested_roles_file: quality-control-suggested-roles.md`; description narrative updated to the 29-department standard.
- `scripts/department-floor.py`: `HARDCODED_MANDATORY` fallback gains `quality-control` (22 ids), docstring updated.
- `scripts/build-workforce.py`: `load_canonical_floor()` fallback gains `quality-control` (22 ids), floor comments updated.
- `scripts/list-canonical-departments.py`: descriptive docstring updated to 22 + 7 = 29.
- `suggested-roles/quality-control-suggested-roles.md`: new (department purpose + 3-role roster).
- `templates/role-library/_index.json`: new `quality-control` dept entry (count 3); 3 role entries added to `roles`; `total_departments` 23 to 24; `total_roles` +3.
- `build-state-schema.json`, `INSTRUCTIONS.md` (mandatory list + 3 count strings), `scripts/test-reconciliation-engine.sh` (floor assertion 28 to 29, mandatory 21 to 22): floor count strings reconciled to 29.

The floor count is computed live everywhere (no integer floor gate is hardcoded). The CI count-drift guard (`scripts/check-floor-count-drift.py`) computes 29 (22 mandatory + 7 universal) and passes; `list-canonical-departments.py` reports floor 29 with `quality-control` in the canonical mandatory set.

## [v12.5.0] - 2026-06-14 - feat: department-reconciliation engine (PRD R2.x) - semantic combine/merge, per-dept custom roles + SOPs, symmetric opt-out for floor + verticals + customs; stale floor numbers corrected to 21+7=28

Reconciliation-engine release for Skill 23. Builds the six reconciliation capabilities into the engine per ZHC-INTERVIEW-CLOSEOUT-FIX/PRD.md coverage area 2 + diag/02-departments.md. No roles added or removed (canonical floor stays 21 mandatory + 7 universal-primary = 28, computed live from department-naming-map.json v2.5.0). CORRECTION HONORED: no "Ant Farm fold-in" was added as a fleet/repo capability - Ant Farm is Trevor-only, handled on his box separately, and must NEVER appear in the shared client interview/build flow; build-workforce.py contains zero ant-farm references and no antfarm-foldin.py was authored.

### Changes

A. **`scripts/build-workforce.py`** - engine capabilities:
   - R2.3 Capability 2 SEMANTIC COMBINE/MERGE (new): `SEMANTIC_OVERLAP_KEYWORDS` + `SEMANTIC_OVERLAP_KEYWORDS_VERTICAL` maps, `_semantic_overlap_match()`, `detect_semantic_overlaps()`, `apply_semantic_merges()`. Detects a custom dept that semantically overlaps a canonical/universal-primary dept under a NON-aliased, NON-variant name (e.g. Accounting->billing-finance, Client Success->customer-support, Brand & Identity Design->graphics, Marketing & CRM Automation->crm). On an owner `mergeDecisions[<custom_id>]=="merge"` it FOLDS the custom into the canonical survivor (records `mergedInto`, annotates `mergedFrom`) and DROPS the duplicate; `"keep"` ships both; un-decided overlaps stay standalone + recorded PENDING. Never a silent merge. Wired into `build_from_config()` after `apply_vertical_packs()`. Replaces the advisory-only "recommend merge/drop" prompt strings (which had no executor).
   - R2.4 Capability 3 per-dept CUSTOM ROLES (new): `materialize_custom_roles()` + `_next_role_number()`. Reads `dept_config.customRoles` / `canonicalReconciliation.customRoles[<dept>]`, materializes each as a real role folder with a library-fill PENDING how-to.md at build (not the post-build add-role.sh path), records `customRolesBuilt`. Also materializes absorbed-merge functions as a role inside the survivor dept. Idempotent.
   - R2.5 Capability 4 per-dept CUSTOM SOPs (new): `capture_custom_sops()`. Captures owner procedures to `<dept>/owner-procedures.md`, RESPECTING `sop_boundary_gate.py` - canonical dept = supplemental overlay over copied 233-template SOPs (LLM authoring stays refused), custom dept = LLM-authoring ground truth. Records `customSopsCaptured` with `isCanonical`.
   - R2.6 Capability 5 symmetric OPT-OUT (extended): `apply_vertical_packs()` now skips a universal-primary vertical the owner declined (`canonicalReconciliation.decisions[id]=="no"` or `declinedDepartments[]`, read via the shared `_canonical_decline_set`), records `verticalPacks.declinedVerticals`. Custom-dept opt-out uses the same decline path.
   - R2.1 stale floor numbers corrected: every "16 canonical / 16 mandatory / 16+7 / 23-dept / below 23 / canonical-16 / = 23 / = 26 / 19 mandatory" string replaced with the live-computed "21 mandatory + 7 universal-primary = 28 (v2.5.0)" language. Enforcement was already correct (runtime-derived); this is documentation truth. Also fixed the `load_canonical_floor()` hardcoded FALLBACK list from 16 ids to the full 21 so a broken install (no naming map) still enforces the full floor.

B. **`scripts/department-floor.py`** - docstring header refreshed to the 21+7=28 floor narrative and explicit symmetric-decline note (mandatory / universal-primary vertical / custom). `declined_set()` already reads `canonicalReconciliation.decisions=="no"` OR `declinedDepartments[]`, so vertical + custom declines are honored on the on-disk enforcer with no logic change (kept in lockstep with the builder).

C. **`scripts/list-canonical-departments.py`** - docstring "19 mandatory ... = 26" -> "21 mandatory + 7 universal-primary = 28", with a note the count is computed live and never a hardcoded gate.

D. **`INSTRUCTIONS.md`** - Phase 5.5: added Step 3.5 (semantic merge decision), Step 3.6 (opt-out for the 7 universal-primary verticals AND customs), Step 3.7 (per-dept custom roles), Step 3.8 (per-dept custom SOPs). Extended the `canonicalReconciliation` JSON example with `mergeDecisions` / `customRoles` / `customSops` and a vertical opt-out in `decisions`. Step 2/Step 4 stale "16 departments" prose replaced with the live-count guidance. (Built additively on top of the interview-redesign agent's build-intake framing - no sibling content removed.)

E. **`SKILL.md`** - "Creates departments" bullet extended to describe the reconciliation engine (semantic combine, symmetric opt-out, custom roles, custom SOPs) with the boundary-gate note.

F. **`build-state-schema.json`** - documented the `canonicalReconciliation` object (decisions, mergeDecisions, customKeeps, customRoles, customRolesBuilt, customSops, customSopsCaptured, semanticMerges, mergedInto) and `verticalPacks` (incl. declinedVerticals). Additive; root allows additional properties; remains draft-07 valid.

G. **NEW `scripts/test-reconciliation-engine.sh`** - 30-check regression guard for R2.1-R2.6 + the no-Ant-Farm correction, importing build-workforce.py as a module against an isolated temp build-state. Green.

---

## [v12.3.10] - 2026-06-13 - fix: interview-nudge cron self-removes at closeout + on next fire; converted to silent command mode (no operator-announce)

- `scripts/interview-nudge-cron.sh`: added `self_remove_cron()` / `find_nudge_cron_uuid()` (UUID-from-state primary, name-scan fallback). `interviewComplete=true` branch now calls `self_remove_cron("interviewComplete")` before `exit 0` - guarantees removal on the next 6h fire even for clients completed before this release. Added OPERATOR-ANNOUNCE RULE and SELF-REMOVAL docs to header.
- `build-state-schema.json`: added `interviewNudgeUuid` + `interviewNudgeRegisteredAt` (additive, non-required, mirrors `closeoutResumeUuid`/`closeoutResumeRegisteredAt`).
- `scripts/test-interview-experience.sh`: added T13 - `interviewComplete=true` + recorded UUID → shim receives `cron rm <uuid>` (self-remove behavioral test).

---

## [v12.3.4] - 2026-06-13 - feat: Skill 23 interview ingests existing client context to ask sharper, non-redundant questions (no-fabrication guardrail)

### Overview

Logic/interview-flow release. No roles added or removed (total_roles stays 335). Implements a structured context-ingestion pre-pass that reads all 6 core workspace files + prior answers + Phase 0 research BEFORE asking any question, classifies each interview theme as KNOWN/PARTIAL/UNKNOWN, and routes accordingly - skipping redundant cold questions, deepening partial ones, and asking fresh only for unknowns. Ships the KNOWN-CONTEXT vs RECORDED-ANSWER distinction with a real enforcement layer (not just prose).

### Changes

A. **NEW: `scripts/context-ingest.py`** - Skill 23 context ingestion helper (mirrors qc-interview-completion.py conventions: `_resolve_openclaw_root`, argparse, `--json`/`--human`). Reads 10 sources (6 core workspace .md files + pre-interview-research.md + software-stack-capabilities.md + prior workforce-interview-answers.md + provided-context-manifest.md). For each of 33 interview themes (Phase 1-6 + branding question ids) emits `{theme_id, phase, label, status, source, snippet, confidence, suggested_action}`. Writes `[slug]/interview-context-map.json` atomically; hard-coded to NEVER open `workforce-interview-answers.md` for writing. On a box with no context files, all themes are UNKNOWN and the interview runs exactly as today (pure superset).

B. **`build-workforce.py`**: CONTEXT_FILES expanded from 4 files `[USER, MEMORY, AGENTS, TOOLS]` to 6 files `[USER, MEMORY, AGENTS, TOOLS, IDENTITY, SOUL]`. `read_existing_context()` (L1795) picks up IDENTITY + SOUL with no other change. `main()` docstring Step 2 note updated; new Step 2.5 'Context Ingestion Pre-Pass' instructs the agent to invoke `context-ingest.py`, load the resulting map, and apply KNOWN/PARTIAL/UNKNOWN routing before Phase 1. Building-block comment updated to list context-ingest.py first.

C. **`INSTRUCTIONS.md`**: Added Phase 0.5 'Context Ingestion (0 questions)' immediately after Phase 0. Replaced 'Pull-Forward Rule (Binding)' with 'Context Ingestion + Pull-Forward Rule (Binding)' - enumerates all 10 ingestion sources (6 core files + 4 context files), defines KNOWN-CONTEXT and RECORDED-ANSWER, specifies three-way routing (confirm/deepen/ask-fresh), de-duplication rule, and three enforcement levels (structural file separation + state field + QC check #5). INTERVIEWER-BEHAVIORAL-CONTRACT fence and all 6 required keywords remain intact.

D. **`SKILL.md`**: Replaced one-liner 'Before Asking Any Question' with full context-ingestion section (6-file list + KNOWN/PARTIAL/UNKNOWN routing + two-label definitions). Updated 'What This Skill Does' bullet #1 to make context-ingestion a first-class step. Updated question-count note to reference interview-context-map.json as the source of 'what is already known'.

E. **`scripts/qc-interview-completion.py`**: Added check #5 (`check_no_fabrication()`). If `interview-context-map.json` exists, any answer containing a verbatim context snippet >= 30 chars WITHOUT a `confirmed-from-context:` provenance note → HARD FAIL exit 3 'unconfirmed-context-as-answer'. Answers WITH the provenance note pass. Map absent → check skips (not a failure). Added `--context-map` and `--no-context-map` CLI flags. Updated docstring from 4 checks to 5. PRD version bumped to PRD-2.15 + PRD-2.16.

F. **`build-state-schema.json`**: Added `interviewProgress.contextIngest` object (ranAt, sources[], themesKnown, themesPartial, themesUnknown, mapPath). Schema remains draft-07 valid; all existing fields untouched.

G. **`ai-workforce-blueprint-full.md`**: New subsection 'Context Ingestion (Before Any Question)' in the Context-Aware Question Flow section. Plain-English explanation of the KNOWN/PARTIAL/UNKNOWN routing, the confirm-not-fabricate pattern, and the NO-FABRICATION rule. Updated context flow step 1 to reference Phase 0.5.

### Version

Version: v12.3.3 → v12.3.4. Markers updated: version, install.sh, update-skills.sh, skill-version.txt, _index.json, _qc-summary.md, README.md (x2), DIRECT-TO-AGENT-UPDATE-MESSAGE.md. total_roles unchanged at 335.

---

## [v11.11.0] - 2026-06-10 - PRD 2.15: Interview experience - persona block, industry-pack assertion, completion QC gate, nudges verified - QC score 9.1/10 (PASS)

### Overview

Four converging deliverables - all wire-it-up + gate-it, not greenfield:

1. **Interviewer behavioral contract (persona block)** - Wrapped the existing "Oprah / Couric Standard" doctrine (INSTRUCTIONS.md lines 103–151) in `<!-- INTERVIEWER-BEHAVIORAL-CONTRACT v1 (PRD-2.15) -->` … `<!-- /INTERVIEWER-BEHAVIORAL-CONTRACT -->` sentinels. Added explicit six-behavior checklist (ONE question, leads with knowledge, suggests answers, earlier answers, celebrates milestones, NEVER uses forbidden term) so the QC gate can grep each. Added "Jennifer Hudson" to the world-class interviewer trio.

2. **Industry-pack assertion (industryPack provenance)** - New `record-industry-pack.sh` wrapper calls `shared-utils/industry-detector.py` and writes `industryPack` provenance object (slug, confidence, source, matchedSignals, detectedAt) into build state atomically. `build-workforce.py` now requires `industryPack.slug` in state before building; absent = hard fail with remediation message; slug="unknown" = loud warning (not a hard block - unclassifiable business is still buildable). `update-interview-state.sh` accepts `--industry-pack <blob>` passthrough.

3. **Interview QC gate** - New `scripts/qc-interview-completion.py`. Four checks: (a) question count 25–35; (b) zero forbidden-jargon hits in AI-authored transcript text (loads from `interview/forbidden-jargon.json` - single canonical source); (c) every branding `required:true` field + structural fields present (branding fields derived at runtime from `branding-questions.json`, not hardcoded); (d) nudge cadence statically verified wired. Exit 0/2/3 contract mirrors `qc-completeness.sh`. Added Phase 6.5 subsection to INSTRUCTIONS.md invoking the gate. `update-interview-state.sh --complete` now sets `interviewQc.status="pending"`.

4. **Nudges live, gateway-routed, state-driven** - New `interview-nudge-cron.sh` (cheap-check-first, lockfile, kill-condition, mirrors `resume-closeout-cron.sh`). Registered every 6h in `install.sh` (Step 13.5). `nudge-incomplete-interviews.py` converted from direct `api.telegram.org` urllib path to `openclaw message send` (binding memory rule). Worker now reads `interviewProgress.lastQuestionAt` and `interviewComplete` from `.workforce-build-state.json` as PRIMARY; falls back to `interview-handoff.md` frontmatter only if state is absent. Idempotency: nudge keys recorded in state (canonical) and handoff (legacy compat).

### New files
- `interview/forbidden-jargon.json` - single machine-readable source of truth for 7 forbidden terms + approved replacements. INSTRUCTIONS.md and build-workforce.py are pointers.
- `scripts/qc-interview-completion.py` - completion QC gate (exit 0/2/3).
- `scripts/record-industry-pack.sh` - industryPack provenance recorder.
- `scripts/interview-nudge-cron.sh` - state-driven gateway-routed nudge cron.
- `scripts/test-interview-experience.sh` - 12 offline fixture tests (T1–T12).

### Schema additions (build-state-schema.json)
- `industryPack` object: slug, confidence, source (enum), matchedSignals, detectedAt.
- `interviewQc` object: status (enum), questionCount, jargonHits, missingFields, nudgesWired, ranAt, rubricVerdict.

### Cross-skill seam (Skill 37 follow-up)
`run-closeout.sh` (Skill 37) should gate on `interviewQc.status != "pass"` before advancing past `pending`. The state field and gate that populate it are in this PR; the one-line Skill 37 wiring is flagged as the next Skill 37 touch.

---

## [v11.8.7] - 2026-06-10 - PRD 2.5: branding-questions.json single source of truth

**New:** `interview/branding-questions.json` - canonical structured definition of all 8 branding questions. INSTRUCTIONS.md Phase 3 + header annotated with question ids and JSON reference. SKILL.md required-read-order note added. Command Center vendoring + sync test defined in syncTest block (implemented in CC sub-agent 2.5-cc).

---

## [v11.8.2] - 2026-06-10 - PRD 2.3: list-canonical-departments.py + stale count sweep

**New:** `scripts/list-canonical-departments.py` - single-source-of-truth script that reads `department-naming-map.json` and prints the 19 mandatory departments, 7 universal-primary vertical-pack departments, and computed floor (26). All live docs now reference this script instead of hardcoded counts (16, 17, 23, 24 swept from SKILL.md, INSTRUCTIONS.md, ZHC-BUILDOUT-EXPERIENCE.md, SYSTEM-DIAGNOSTIC-CHECKLIST.md, 34-ARCHIVED.md).

---

## [v11.1.0] - 2026-06-09 - General Task + PAO departments, auto-wire detection, Ollama HARD RULE, model-object enforcement

### Overview

This is a **minor release** - new functionality (2 new mandatory departments, post-build extension detection, N30/N31 hard rules) built on top of v11.0.1 with zero breaking changes to existing client installs.

### Highlights

#### Step 1 (merged pre-bump)
- **Skill 22 (Book-to-Persona):** argparse `--single-book`, path unification, inbox watcher, headless Calibre, schema fix
- **Skill 23 (CEO = orchestrator-only):** `build-workforce.py` production tool lock (CEO agents get `"skills": []`) + SOP-00 canonical Owner Task Routing document

#### Step 2 - Two new mandatory departments (floor 23→26)
- **General Task** (`general-task`): 5 roles - head-of-general-task, generalist-operator, triage-classifier, qc-specialist-general-task, sop-writer. Routing priority 1 (lowest, fallback-only). Zero-drop catch-all for tasks that fail all routing.
- **Project Architecture Office** (`project-architecture-office`): 6 roles - chief-project-architect, research-agent, code-monitor, code-editor, qc-agent, sop-writer. Loop engineering harness: max 12 loops, 72h deadline, ≥8.5 gate, pao-reaper cron.
- **PRD folder templates**: PRD.md, checklist.md, CHANGELOG.md, todo.md, QC.md, loop-state.json
- `department-naming-map.json` v2.3.0→v2.4.0 (mandatory block updated, 26-dept floor)
- `department-floor.py` HARDCODED_MANDATORY + evaluate_floor() updated (23→26)
- `_index.json`: total_roles 233→244, total_departments 17→19
- 2x `suggested-roles/` files added

#### Step 3 - Auto-wire detection + Ollama hard rules
- `32-command-center-setup/scripts/sync-extensions.sh`: master idempotent post-build orchestrator
- `32-command-center-setup/scripts/detect-extensions.py`: manifest-diff detector (last-sync.json)
- `32-command-center-setup/scripts/register-routing-dept.py`: routing registration (N31-compliant)
- `32-command-center-setup/EXTENSIBILITY.md`: operator runbook
- `universal-sops/adding-capability-after-build.md`: DMAIC SOP for agents
- **N30 HARD RULE**: `OLLAMA_BASE_URL` MUST be `https://ollama.com` for `:cloud` models - NEVER `127.0.0.1`
- **N31 HARD RULE**: agent model field MUST be object `{primary, fallbacks:[...]}` - never bare string
- `build-workforce.py` N31 FIX: `add_agent_to_config()` now writes model as object

#### Step 4 - Version bump (this commit)
- `bump-version.sh v11.1.0` run atomically - all 9 markers agree at v11.1.0

### Files touched (complete list)
See individual step CHANGELOG entries below (v11.1.0-step2, v11.1.0-step3) for per-file details.

---

## [v11.1.0-step3] - 2026-06-09 - Auto-wire detection + Ollama HARD RULE + model-object enforcement (v11.1.0 pre-bump)

### Why
Three gaps in the system needed closing before the v11.1.0 release:
(1) No mechanism to detect and register new skills/departments added post-build - client boxes
would stay frozen even after the role library grew. (2) No hard rule preventing agents from
routing `:cloud` model calls to `127.0.0.1` (local daemon) - every client box → ECONNREFUSED.
(3) `build-workforce.py` wrote bare-string `"model"` fields with no fallbacks - a single Ollama
Cloud outage silences ALL department agents.

### Changed

#### Auto-wire / extension detection (Skill 32)
- `32-command-center-setup/scripts/sync-extensions.sh` - NEW master idempotent orchestrator:
  detects delta via `detect-extensions.py`, registers new depts, materializes workspaces,
  updates `last-sync.json`, sends Telegram summary
- `32-command-center-setup/scripts/detect-extensions.py` - NEW manifest-diff detector:
  diffs current `_index.json` against `last-sync.json`; emits `NEW: <slug>` / `SKIP: <slug>`
- `32-command-center-setup/scripts/register-routing-dept.py` - NEW routing registration:
  writes dept into `extension_registry.departments[]` in `openclaw.json`; idempotent;
  N31-compliant model objects; atomic backup+write
- `32-command-center-setup/EXTENSIBILITY.md` - NEW operator doc: manual + auto paths,
  script reference, rollback, model rules cross-reference
- `universal-sops/adding-capability-after-build.md` - NEW SOP for PAO/General Task agents

#### Ollama HARD RULE (N30 + N31)
- `AGENTS.md` - added N30 (Ollama Cloud URL must be `https://ollama.com`; NEVER 127.0.0.1) and
  N31 (model field must be object `{primary, fallbacks:[...]}`) to the canonical N-rule index
  AND as full expanded sections with violation examples and correct forms
- `23-ai-workforce-blueprint/scripts/build-workforce.py` - N31 FIX: `add_agent_to_config()`
  now writes model as object `{"primary": ..., "fallbacks": [...]}` instead of bare string;
  fallback chain: kimi-k2.6:cloud → openrouter/moonshotai/kimi-k2.6 →
  deepseek-v4-pro:cloud → openrouter/deepseek/deepseek-v4-pro

### Files touched
- `32-command-center-setup/scripts/sync-extensions.sh` - NEW
- `32-command-center-setup/scripts/detect-extensions.py` - NEW
- `32-command-center-setup/scripts/register-routing-dept.py` - NEW
- `32-command-center-setup/EXTENSIBILITY.md` - NEW
- `universal-sops/adding-capability-after-build.md` - NEW
- `AGENTS.md` - N30 + N31 added (index rows + full expanded sections)
- `23-ai-workforce-blueprint/scripts/build-workforce.py` - N31 model-object fix
- `23-ai-workforce-blueprint/CHANGELOG.md`

Note: umbrella version bump deferred to Step 4 (bump-version.sh --tag with all 9 markers).

## [v11.1.0-step2] - 2026-06-09 - General Task + Project Architecture Office departments (v11.1.0 pre-bump)

### Why
Two mandatory departments were missing from the 26-department floor: (1) General Task - a
zero-drop catch-all for tasks that fail keyword + semantic routing; (2) Project Architecture
Office (PAO) - a bounded execution department that governs any project from PRD to verifiable
completion. Without General Task, low-confidence fallback tasks vanish silently. Without PAO,
there is no canonical loop-engineering harness (max 12 loops, 72h deadline, ≥8.5 gate) for
cross-department projects.

### Changed

#### New department: General Task (`general-task`)
- **5 roles** added to `templates/role-library/general-task/`:
  - `head-of-general-task.md` - leadership/triage; SOP-03 recurrence detection with ≥4/month dept recommendation trigger
  - `generalist-operator.md` - on-call execution with QC gate
  - `triage-classifier.md` - on-call re-classifier returning `{task_id, dept_slug, confidence, reason}`
  - `qc-specialist-general-task.md` - dedicated QC (Rule 6: different model from writer)
  - `sop-writer.md` - SOP codification for recurring novel task types
- **Routing priority: 1** (lowest); intentionally no keywords - reached only via explicit fallback path
- `suggested-roles/general-task-suggested-roles.md` - NEW

#### New department: Project Architecture Office (`project-architecture-office`)
- **6 roles** added to `templates/role-library/project-architecture-office/`:
  - `chief-project-architect.md` - leadership/orchestrator with 8 SOPs; owns PRD folder lifecycle, loop-state.json, pao-reaper cron
  - `research-agent.md` - deep-research; Context7 primary; mandatory source citations
  - `code-monitor.md` - CI/build watcher; NEVER edits code; short-lived
  - `code-editor.md` - implementation agent; elevated reasoning; no self-approval
  - `qc-agent.md` - QC gatekeeper; `{task_id, round, score, dimension_scores, pass, fix_directives, model_used, writer_model}`; max 3 rounds
  - `sop-writer.md` - SOP authoring for reusable project patterns
- **PRD folder template** added at `templates/prd-folder/`:
  - `PRD.md`, `checklist.md`, `CHANGELOG.md`, `todo.md`, `QC.md`, `loop-state.json`
  - `loop-state.json` schema: `{project, goal_ref, loop, max_loops:12, deadline_iso, last_qc_score, gate:8.5, cron_id, status, started_iso, active_agents[]}`
- **Routing priority: 7**; keywords: `prd`, `project requirements`, `spec`, `scope`, `milestone`, `project plan`, `architecture`, `build plan`, `requirements doc`, `project architecture`
- `suggested-roles/project-architecture-office-suggested-roles.md` - NEW

#### Config updates
- `department-naming-map.json` - version 2.3.0 → 2.4.0; both departments added to `mandatory` block; description updated to "26-department standard" (floor 17+7+2=26)
- `scripts/department-floor.py` - `HARDCODED_MANDATORY` + `evaluate_floor()` updated to include `general-task` and `project-architecture-office`; all "23-department standard" refs updated to "26-department standard"; floor math 23→26
- `templates/role-library/_index.json` - total_roles 233→244, total_departments 17→19; 11 new role entries + 2 new department blocks
- `templates/role-library/_qc-summary.md` - heading updated to v11.1.0, total 233/233→244/244, rows added for both new departments

### Files touched
- `23-ai-workforce-blueprint/templates/role-library/general-task/` - 5 NEW files
- `23-ai-workforce-blueprint/templates/role-library/project-architecture-office/` - 6 NEW files
- `23-ai-workforce-blueprint/templates/prd-folder/` - 6 NEW files
- `23-ai-workforce-blueprint/suggested-roles/general-task-suggested-roles.md` - NEW
- `23-ai-workforce-blueprint/suggested-roles/project-architecture-office-suggested-roles.md` - NEW
- `23-ai-workforce-blueprint/department-naming-map.json`
- `23-ai-workforce-blueprint/scripts/department-floor.py`
- `23-ai-workforce-blueprint/templates/role-library/_index.json`
- `23-ai-workforce-blueprint/templates/role-library/_qc-summary.md`
- `23-ai-workforce-blueprint/CHANGELOG.md`

Note: umbrella version bump deferred to Step 4 (bump-version.sh --tag with all 9 markers).

## [v10.15.35] - 2026-06-09 - CEO = orchestrator-only: production tool lock + canonical SOP-00 Owner Task Routing

### Why
Two gaps remained after v10.15.34's behavioral SOP addition: (1) the CEO/Master Orchestrator
agent entry in `openclaw.json` had no runtime enforcement - an agent could still invoke
production skills. (2) The canonical fleet-wide SOP-00 routing procedure (classify → POST
/api/tasks/ingest → notify owner → NEVER execute) had no permanent home in the
`master-orchestrator-dept/` folder that every install loads.

### Changed
- **`23-ai-workforce-blueprint/scripts/build-workforce.py` - `add_agent_to_config()`**
  - CEO/master-orchestrator agents now get `"skills": []` in their `agents.list[]` entry
  - OpenClaw `skills` at agent level REPLACES defaults (per docs.openclaw.ai/tools/skills-config)
  - Result: `dept-ceo` / `dept-master-orchestrator` cannot invoke image_generate, tts,
    video_generate, coding-agent, browser-automation, or any other installed skill
  - Other department agents (graphics, video, audio, etc.) are unaffected - no `skills` key
    = unrestricted (inherits platform default)
  - Applies to both Mac (`openclaw-onboarding`) and VPS (`openclaw-onboarding-vps`) repos

- **`23-ai-workforce-blueprint/master-orchestrator-dept/SOP-00-Owner-Task-Routing.md` - NEW**
  - Canonical fleet-wide Owner Task Routing SOP (6-step protocol)
  - Covers: classify task, POST to `/api/tasks/ingest` with idempotency_key, acknowledge owner,
    escalation path when CC is unreachable, tool-lock enforcement explanation
  - Binding rules table: what the orchestrator can and cannot do
  - Verified canonical graphics dept head name: Chief Design Officer (role #0 in
    suggested-roles/graphics-suggested-roles.md - "Imani"/"Amani" do not exist in the library)
  - Cross-platform: identical file in both Mac and VPS repos

### Files touched (merge coordination)
- `23-ai-workforce-blueprint/scripts/build-workforce.py` - ONLY `add_agent_to_config()` function
  (the `agent_entry` dict + the `is_ceo_agent` guard that follows it). Skill-22 branch touches
  `create_role_workspaces.py` and `install.sh` - zero overlap.
- `23-ai-workforce-blueprint/master-orchestrator-dept/SOP-00-Owner-Task-Routing.md` - NEW FILE
- `23-ai-workforce-blueprint/CHANGELOG.md`

Note: umbrella version bump deferred to Step 4 (bump-version.sh --tag with all 9 markers).

## [v10.15.34] - 2026-06-09 - master-orchestrator: hard owner-task routing protocol (SOP-00)

### Why
The master-orchestrator (CEO) template lacked an explicit, binding rule preventing it from
executing owner tasks directly. Without SOP-00 the CEO would perform department-level work
itself when an owner sent a task via Telegram - bypassing the routing system, bypassing SOP
coverage, and breaking the AI-workforce model entirely.

### Changed
- **`23-ai-workforce-blueprint/templates/role-library/master-orchestrator/master-orchestrator.md`**
  - Added hard "You are NOT an executor" binding at the top of the "What This Role Is NOT" section
  - Added **SOP-00: Owner Task Routing (HARD PROTOCOL - NO EXCEPTIONS)** immediately before SOP-01
    - 7-step dispatch protocol: receive → classify to THIS client's dept roster → identify specialist → pull SOP → dispatch with full context → confirm to Owner → log
    - Explicit semantic matching: dept names matched by MEANING (e.g. "Brand Storytelling Lab" = brand narrative work), not by canonical keyword
    - Hard "NEVER" list: never draft deliverables, never route to a dept not in THIS client's roster, never dump to CEO/COM as a catch-all
    - Failure-mode handling: one clarifying question OR sub-route to dept director for sub-classification (never self-execute)
  - This is a behavioral document update - **umbrella version NOT bumped** (cut separately per standing policy)

## [v10.15.33] - 2026-06-09 - command-center pipeline fixes: 9 RC repairs to persona selection, governing-personas gate, slug hygiene, build-state backfill, and role-library path

### Why
Live builds exposed 9 pipeline failures in the AI-Workforce → Command Center flow: the
persona scorer crashed on DeepSeek V4 Pro's `content: null` thinking-model response;
governing-personas.md was a soft operator self-report with no enforcement; `departments.json`
lacked a canonical `slug` field; `soul_md` DB column was always empty; `company-config.json`
had no upgrade path to the v2.0 schema the 5-layer scorer needs; legacy clients missing gate
fields in `.workforce-build-state.json`; the stale-persona-index marker was written but never
consumed; Skill 22 absence was a soft warning instead of a hard stop; and the role-library
importer had no env-var escape hatch when the default path yielded an empty templates tree.

### Changed
- **`shared-utils/llm_score.py` - persona-selector null-content crash (CRITICAL, Fix 1)**
  - `_extract_message()`: null-guard + three-level fallback chain
    (`content` → `reasoning_details` list → `reasoning` string). DeepSeek V4 Pro as a
    THINKING model returns `content: null`; old code did `.strip()` on `None` → AttributeError.
  - `_attempt_openrouter()`: added `"reasoning": {"exclude": True}` to request body to ask
    OpenRouter to suppress thinking tokens upfront; widened except clause to also catch
    `AttributeError`, `KeyError`, `TypeError`.
- **`scripts/generate-governing-personas.sh` - NEW (Fix 2 / build RC-1)**
  New script that writes stub `governing-personas.md` files for any department missing one,
  then exits 0 only when every department has a valid file. Exit 1 = hard fail; exit 2 =
  departments dir unresolvable. Auto-detects ZHC tree (canonical → Mac fallback → VPS
  fallback). Supports `--dry-run`.
- **`INSTALL.md` - Phase 0a HARD STOP + Phase 5-PERSONA HARD gate (Fix 8 / RC-2, Fix 2)**
  - Phase 0a: changed from soft warning to HARD exit 1 when `coaching-personas` Gemini
    collection / `coaching-personas/personas` dir is absent. Operator action item printed.
  - Phase 5-PERSONA gate: replaced soft grep count with call to `generate-governing-personas.sh`
    as a HARD gate; non-zero exit blocks progress to Phase 5-ORG.
- **`INSTALL.md` - Phase 5-BUILD-A2 upgrade-company-config step (Fix 3 / Runtime D)**
  New Phase 5-BUILD-A2 documents and wires `upgrade-company-config.py` into the build
  immediately after config safety and before department workspace creation.
- **`INSTALL.md` - ROLE_LIBRARY_PATH env var documentation (Fix 9 / SOP-pull RC-3)**
  Step 4 of ACTIVATION now documents `$ROLE_LIBRARY_PATH` and `$OPENCLAW_WORKSPACE_PATH`
  overrides for operators whose default skill install templates tree is empty.
- **`scripts/upgrade-company-config.py` - NEW (Fix 3 / Runtime D)**
  Generates or upgrades `company-config.json` to schema v2.0 (adds `mission`,
  `owner_values`, `company_kpis`, `dept_kpis`). Idempotent. CLI: `--upgrade`, `--output`,
  `--dry-run`. Exit 0/1/2.
- **`scripts/sync-md-content-to-db.py` - NEW (Fix 4 / build E)**
  Reads per-dept `SOUL.md` files and writes to `agents.soul_md` in `mission-control.db`.
  Idempotent (skips non-empty rows unless `--force`). Exit 0/1/2.
- **`scripts/build-workforce.py` - explicit `slug` field in departments.json (Fix 5 / RC-3)**
  `generate_departments_json()` now emits `"slug": dept_id` (bare slug) alongside the
  existing `"id": "dept-{dept_id}"` entry. Eliminates runtime string-stripping in CC
  slug-based lookups.
- **`scripts/backfill-build-state.py` - NEW (Fix 6 / build RC-6)**
  Stamps missing gate fields (`sopLibraryStatus`, `roleLibraryStatus`,
  `commsAutomationStatus`, `canonicalReconciliation`, per-dept `roleLibraryFilled` /
  `sopLibraryFilled`) into `.workforce-build-state.json` for pre-v10.16.8 clients.
  Idempotent; heuristic detection. `--force` overwrites existing values. Exit 0/1.
- **`scripts/select-persona-for-task.py` - stale marker consumer (Fix 7 / build RC-5)**
  `_consume_persona_stale_marker()` called at start of `main()`: if `.persona-index-stale`
  exists AND coaching-personas collection is present, re-runs `gemini-indexer.py` then
  deletes the marker. Closes the add-department → stale-persona-index → re-index loop.
- **`scripts/create_role_workspaces.py` - ROLE_LIBRARY_PATH env var (Fix 9 / SOP-pull RC-3)**
  `_resolve_skill_dir()` now checks `$ROLE_LIBRARY_PATH` (validates index exists; warns +
  falls back if not) then `$OPENCLAW_WORKSPACE_PATH/skills/23-ai-workforce-blueprint`
  before the standard detect_platform path. Operators can point the library importer at
  a live ZHC departments tree.

### Also fixed (Skill 32 - seed-workspaces.py)
- **`32-command-center-setup/scripts/seed-workspaces.py` - `dept-` prefix strip (Fix 5 / RC-3)**
  `scan_skill23_workspaces()`: added `dept_id = re.sub(r'^dept-', '', dept_id)` after the
  existing `-dept` suffix stripping so both `dept-marketing` (prefix) and `marketing-dept`
  (suffix) normalize to the bare canonical slug.

### Risk
Low. All new scripts are additive and idempotent. No existing scripts deleted. INSTALL.md
changes only add Phase 5-BUILD-A2 and ROLE_LIBRARY_PATH documentation. Gate changes
(Phase 0a + Phase 5-PERSONA) enforce constraints that were already operator-documented
best-practice - hard-failing only helps operators catch gaps earlier.

---

## [v10.15.32] - 2026-06-02 - 23-department standard (N23): universal vertical-pack primaries

### Why
Clients were shipping with 17 departments (one client: 16 mandatory + CEO counted as custom = 17) instead
of the intended 23-25. Root cause: `apply_vertical_packs()` only fired for clients whose industry
keywords matched a pack - a client with no matching keyword got 0 vertical departments added,
landing at 16. Trevor's stated standard is 23-25 = 16 mandatory + 7 vertical packs. The fix makes
one primary department per pack (the `universal_primary` dept) fire for EVERY client regardless of
industry, giving a guaranteed 23-dept floor. Industry keyword matching is preserved for ADDITIONAL
flavor departments on top of the 23 - it no longer acts as a gate reducer.

### Changed
- `department-naming-map.json` v2.2.0 → v2.3.0: each vertical pack's first department is marked
  `"universal_primary": true`; description updated to document the 23-dept standard. 7 packs, 7
  universal primaries: `presentations` (personal-pro-dev), `listings` (real-estate),
  `scheduling-dispatch` (service-industry), `logistics-fulfillment` (ecommerce), `engineering` (saas),
  `account-management` (agency), `podcast` (content-creator). TODO comment: PA dept pending proposal
  will bring floor to 24.
- `scripts/department-floor.py`: new `universal_primary_vertical_departments()` function returns the 7
  universal primaries from the naming map; `matched_vertical_pack_departments()` now always includes all
  7 universal primaries (Phase 1) before adding keyword-matched extras (Phase 2); `evaluate_floor()`
  gates on 16 mandatory + 7 universal primaries = 23 minimum (exit 3 when below 23); verdict dict adds
  `universal_primary_vertical` and `missing_universal_primary` fields; docstring and stderr output
  updated to say "23-department standard".
- `scripts/build-workforce.py`: `apply_vertical_packs()` runs Phase 1 (universal primaries, always) then
  Phase 2 (keyword extras, flavor); canonical floor comment updated to N23; log lines show universal
  vs extras count.
- `ZHC-BUILDOUT-EXPERIENCE.md` Stage 2 prose updated to "23-department minimum"; Stage 2 checklist item
  updated from "16 mandatory" to "23 departments minimum - run `department-floor.py --json`".
- `INSTRUCTIONS.md`: "I Don't Have a Business" pivot and "What Gets Built" section updated to 23-dept.

### Repo
- Repo version bumped to `v10.15.32`.

---

## [v10.15.9] - 2026-05-29 - Cross-skill chain to Skill 38 (ENFORCED) + library-gate status surfacing

Part of repo `v10.15.9` (the 8 rated improvements, port of VPS #47). Two improvements land here:

### Added
- **commsAutomationStatus** state field (+ `commsAutomationDepartments`, `commsAutomationVerifiedAt`,
  `librariesNearCapNotified`) in `build-state-schema.json`. Enforces the Skill 23 → Skill 38 cross-skill
  chain: when the workforce builds a Communications / Sales / Customer-Support department, the build is
  not fully delivered until Skill 38 has scaffolded the matching comms automations.
- New binding **Moment 3.8 - Comms-automation handoff to Skill 38** in `INSTRUCTIONS.md`, plus a
  reciprocal cross-reference in `SKILL.md` (the two siblings previously had zero cross-references).

### Changed
- `scripts/resume-workforce-build.sh`:
  - Treats the build as dirty (and dispatches a `[COMMS-AUTOMATION-RESUME]` self-ping) when all
    departments + libraries are done but `commsAutomationStatus NOT IN {done, not-applicable}`. The
    self-ping points at Skill 38 + `qc-trinity-registry.sh`. Fires after `[LIBRARY-RESUME]`.
  - **Library-gate status surfacing:** emits a one-line OPERATOR-FACING status when libraries stay dirty
    into the last 2 resume attempts (throttled via `librariesNearCapNotified`), and names the library
    status in the hard-cap escalation - a persistently-failing library pull is now visible instead of
    silently retrying to the cap.
- Repo version bumped to `v10.15.9` via `bump-version.sh` (skill-version.txt + the other 7 locations).

---

## [v10.15.8] - 2026-05-29 - ENFORCED Role Library + SOP Library auto-pull gate

### Why
Last night several clients had workforces *scaffolded* -
department + role folders existed, depts even flipped to `status: "done"` - but the **role library was
never pulled into the `how-to.md` files** AND the **SOP placeholders were never authored**. Nothing GATED
on those two libraries being populated, so the build "looked done." Prose like "AUTOMATIC NEXT STEP: also
pull the role library" is NOT enforcement (same lesson as the v10.14.16 build-resume fix). Enforcement =
a STATE FIELD + a VERIFY/RESUME GATE. This release adds both. A workforce is now NOT complete (no
`buildCompletedAt`, no closeout) until both libraries are populated.

### Added
- `scripts/verify-library-gate.sh` - the verify gate. Runs `qc-completeness.sh` (read-only), then writes
  `roleLibraryStatus` / `sopLibraryStatus` + per-dept `roleLibraryFilled` / `sopLibraryFilled` +
  `libraryFailureReason` into `.workforce-build-state.json` and exits non-zero unless every dept has the
  role library pulled into every `how-to.md` (library_pct == 100) AND SOPs authored (sop_stubs_remaining
  == 0, avg_sop_per_role > 0). Exit codes: 0 = both done, 2 = role library not done, 3 = SOP library not
  done, 4 = both not done, 5 = no workforce / qc could not run.

### Changed
- `build-state-schema.json` - new enforced gate fields: top-level `roleLibraryStatus`
  (`pending`→`pulling`→`done`/`failed`), `sopLibraryStatus` (`pending`→`authoring`→`done`/`failed`),
  `libraryFailureReason`; per-department `roleLibraryFilled` / `sopLibraryFilled` booleans. `closeoutStatus`
  description updated: the library gate runs BEFORE the closeout gate.
- `scripts/build-workforce.py` - after `qc-completeness.sh`, the build now invokes `verify-library-gate.sh`
  and logs LIBRARY GATE PASS/FAIL; on FAIL it instructs to re-pull and re-run before writing
  `buildCompletedAt` / `closeoutStatus=pending`.
- `scripts/resume-workforce-build.sh` - the 15-min resume cron now computes `library_dirty` (all depts done
  but `roleLibraryStatus != done` OR `sopLibraryStatus != done`) and fires a `[LIBRARY-RESUME]` self-ping
  (BEFORE the closeout gate) instructing the agent to re-run `post-build-role-workspaces.py` /
  `populate-sops-from-manifest.py` then re-run the gate until it passes.
- `resume-prompt.txt` - added a LIBRARY FLOW + decision-tree branch A2 + a gate step in BUILD FLOW step 5.
- `INSTRUCTIONS.md` - new "Moment 3.6 - ROLE LIBRARY + SOP LIBRARY auto-pull gate (BINDING)"; Moment 1 now
  seeds `roleLibraryStatus`/`sopLibraryStatus = pending`; resume-layer section lists the library-dirty
  trigger; "When ALL departments are done" renamed to require the gate first.
- `SKILL.md` - item 10 documents the enforced role/SOP library gate.

### Version
- Repo-wide bump v10.15.7 → v10.15.8 via `scripts/bump-version.sh` (all 8 version locations agree).

---

## [v10.6.2] - 2026-05-19 - Role Library Version Realigned + verify-role-library.sh

### Added
- `scripts/verify-role-library.sh` - 7-check sanity script for the role library on disk. Was referenced from the QC summary "next step" line but never existed until now. Use:
  ```bash
  bash 23-ai-workforce-blueprint/scripts/verify-role-library.sh
  # or
  bash 23-ai-workforce-blueprint/scripts/verify-role-library.sh --skill-dir /path/to/skill
  bash 23-ai-workforce-blueprint/scripts/verify-role-library.sh --json
  ```

### Updated
- `skill-version.txt` → `10.6.2` (was `10.6.1`)
- `templates/role-library/_index.json` `"version"` → `"10.6.2"` (was `"10.6.0"` - stale since the role library merge)
- `templates/role-library/_index.json` `generated_at` refreshed
- `templates/role-library/_qc-summary.md` heading → `Role Library v10.6.2` (was `v10.6.0`)

### Why these were stale
The Wave 5b commit (v10.6.1) only touched `/version` and `/skill-version.txt`. The library files were left at their original v10.6.0 generation values. Repo-wide drift-prevention (`scripts/bump-version.sh` + `.github/workflows/version-consistency.yml`) was added in this same release to prevent recurrence - see root `CHANGELOG.md`.

---

## [v10.6.1] - 2026-05-19 - Wave 5b: Library Template-Fill

### Added
- `scripts/create_role_workspaces.py` - replaces `create-role-workspaces.py` (deleted)
  - New: `library_lookup(role_slug, dept_slug)` - reads `templates/role-library/_index.json` for matching role
  - New: `try_library_fill(role_name, dept_path, is_ceo)` - orchestrates lookup + token-fill, returns filled content or None
  - New: `fill_tokens(content, role_name, dept_name, is_ceo)` - substitutes `{{COMPANY_NAME}}`, revenue cascade tokens (`{{YEARLY_GOAL}}` → cascade ÷4 ÷12 ÷52 ÷250), `{{INDUSTRY_VERTICAL}}`, `{{ROLE_TITLE}}`, `{{DEPARTMENT_NAME}}`, `{{DIRECTOR_OR_MASTER_ORCHESTRATOR}}`, `{{ISO_DATE}}`, `{{ASSIGNED_PERSONA}}`
  - New: `augment_role_folder(role_path, workspace_root)` - idempotent v2.1 file augmentation (previously referenced by post-build, never defined - Wave 4 bug)
  - New: `augment_all_existing_role_folders(dept_path, workspace_root, dry_run)` - walks a dept and augments each role folder (Wave 4 bug fix)
- `create_role_workspace()` now uses library template-fill for `how-to.md` when a match exists; falls back to `stub_how_to()` when no match

### Behavior change for `build-workforce.py`
When `build-workforce.py` finishes a dept build, the post-build hook (in place since Wave 4) now actually works - and where the v10.6.0 library has a matching role doc, the role's `how-to.md` is template-filled from the library instead of left as a stub awaiting a fresh sub-agent generation.

Estimated time-per-role on a typical build: ~3 min (template-fill) vs ~15 min (sub-agent fresh write). With ~210 of 216 library matches across the 16 mandatory depts, a typical build drops from ~3 hours to ~30-45 minutes of role-doc work.

### Removed
- `scripts/create-role-workspaces.py` (hyphen-named - Python could not import it as `create_role_workspaces`)

### Library header stamp
Every doc filled from the library carries a header comment so QC/owner can identify provenance:
```
<!-- Filled from role-library v10.6.0 on YYYY-MM-DD -->
```

---

## [v10.6.0] - 2026-05-19 - Role Library Production (216 PASS docs)

Backfilled. The 216-doc role library was merged to main via `role-library-v10.6.0` branch. The library lives at `templates/role-library/[dept]/[role-slug].md` with an `_index.json` registry.

Library is dormant at v10.6.0 - nothing reads from it. v10.6.1 (Wave 5b) wires it into role workspace creation.

---

## [v10.5.2] - 2026-05-17 - Wave 4.5: Specialist Coverage Expansion

Every mandatory department now has the role roster needed to operate at Fortune-500 scale. Brings 12 pre-v2.1 department files up to the v2.1 baseline (added missing QC + Deep Research roles to depts that had them only conceptually) AND adds 70 new specialist roles across 16 departments.

### What changed per department

| Department | Pre-Wave-4.5 specialists | Post-Wave-4.5 specialists | Net change |
|---|---:|---:|---:|
| Marketing | 4 → | 11 (Brand Positioning, Content Strategist, Content Marketing, Funnel, Customer Journey, Influencer, Marketing Analytics, Lead Magnet, Webinar/Event, Email Campaign, Affiliate) | +7 |
| Sales | 4 → | 11 (SDR, Appointment Setter, Discovery, Closer, AE Full-Cycle, Account Manager, Proposal, Follow-up, Sales Ops, CRM-Sales, +1 deep research) | +7 |
| Billing & Finance | 3 → | 9 (Invoicing/AR, Subscription, Bookkeeping, Cash Flow, FP&A, Collections, Financial Reporting, Tax Liaison, CRM-Billing) | +6 |
| Customer Support | 3 → | 11 (Tier 1/2, Refunds, Onboarding, Retention, KB, Live Chat, Voice, Account Health, Churn Prevention) | +8 |
| Web Development | 3 → | 12 (Funnel, Landing Page, SEO, Tech SEO, Web Designer, Frontend/JS/React, CRO, WordPress, Member Area, A11y, Web Security) | +9 |
| App Development | 3 → | 11 (Desktop, iOS, Android, PWA, API/Backend, UX/UI, Cloud Infra, ASO, App Analytics, QA Tester) | +8 |
| Graphics | 5 → | 12 (AI Image Gen, Brand Identity, Social Media Graphics, Ad Creative, Presentation Designer, Course Slides, Book Cover, Infographic, Email Designer, Print, Thumbnail) | +7 |
| Video | 5 → | 13 (Storyboard, Long-form, Short-form, AI Video Gen, Editor, Video SEO, VSL, Motion Graphics, Animation, Color Grading, Captioning, Live Streaming, CRM-Video) | +8 |
| Audio | 6 → | 11 (Producer, Editor, AI Voice, Sound Design, Speech Writing, Music, Transcription, Audio Mastering, Audiobook, Voice Agent Builder, CRM-Audio) | +5 |
| Research | 3 → | 7 (Industry Analysis, Competitive Intel, Market Trends, Customer Research, Persona Research, Data Analysis, Survey & Polling) | +4 |
| Communications | 3 → | 10 (PR, Internal Comms, Brand Messaging, Press Release, Crisis Comms, Speech/Talking Points, Media Pitching, Op-Ed Ghostwriter, Investor/Stakeholder, Deep Research) | +7 |
| CRM | 7 → | 7 (already complete in v2.1, no expansion needed) | 0 |
| OpenClaw Maintenance | 6 → | 9 (System Health, Skill Update, Memory Hygiene, Integration/MCP, Backup & Recovery, Security & Secrets, Monitoring/Observability, Performance Tuning, Disaster Recovery) | +3 |
| Legal | 2 → | 10 (Contract Drafter, Customer Agreement, Affiliate Agreement, Employment Contract, Compliance Monitor, Industry-Specific Regulatory, Terms/Privacy, IP/Trademark, Vendor Contract, Dispute Resolution) | +8 |
| Social Media | 10 → | 13 (Facebook, Instagram, TikTok, LinkedIn, Twitter/X, Pinterest, YouTube Channel, Threads, Bluesky, Community Manager, Reddit, Quora, Discord) | +3 |
| Paid Advertisement | 12 → | 17 (Google, Bing, Facebook, Instagram, TikTok, LinkedIn, Twitter/X, Pinterest, YouTube, Spotify, Snapchat, Native, Cross-Platform Attribution, Retargeting, Creative Testing, Audience Research, Conversion Tracking) | +5 |
| **TOTAL specialists** | **79** | **174** | **+95** |

Plus universal roles (Director + QC + Deep Research per dept = 47 universal) + Master Orchestrator = **~222 total roles in the canonical roster**.

### v2.1 Baseline Brought Forward

Every department now has all 4 universal roles confirmed:
- Director (role #0)
- QC Specialist
- Deep Research Specialist (except Research dept which IS deep research)
- Devil's Advocate (sub-folder, created by `build-workforce.py:create_department_workspace`)

### Calendar Specialist NOT added
Confirmed via owner feedback: clients use GoHighLevel calendar or Google Calendar directly. No Calendly/booking-system specialist needed in Web Development.

### Why this matters for the role library generation (PRD v2.3)
PRD v2.3 estimated 146 docs. With this expansion, the library generation produces **~205 docs** (Master Orchestrator + ~204 mandatory specialists across 16 depts). Adjusts:
- 20 writer sub-agents → still 20 (each writer handles ~10 docs instead of ~7)
- Wall-clock: ~130-150 min instead of ~100-115
- Cost: ~$22-35 (Ollama primary) or ~$110-150 (all OpenRouter)
- Still well within owner's time and budget tolerance

### Versions
- `skill-version.txt`: 10.5.1 → **10.5.2**
- Onboarding root `version`: v10.5.1 → **v10.5.2**

---

## [v10.5.1] - 2026-05-17 - Wave 4: Hand-Touch Integration

### Changed

- **`scripts/build-workforce.py`** - Inline v10.5.1 hook at the end of `build_from_config()`. After all departments and persona matrix are created, spawns `post-build-role-workspaces.py` via subprocess (30s timeout) to augment every role folder with v2.1 files. Wrapped in try/except so failure doesn't break the main build.
- **`scripts/post-build-role-workspaces.py`** - Reworked to AUGMENT existing role folders rather than create duplicates. Detects pre-v2.1 role folders (any naming pattern, with or without numeric prefix) and adds IDENTITY.md, SOUL.md, MEMORY.md, HEARTBEAT.md, how-to.md stub, and AGENTS/TOOLS/USER symlinks in place. Master Orchestrator (CEO) created at company root with CEO deferral clause if missing. Pre-v2.1 files like `00-START-HERE.md` are preserved.

### Version

`skill-version.txt` bumped to `10.5.1`.

### What's no longer a hand-touch (RUNBOOK Section 5)

- ✅ `build-workforce.py` post-build call - now automatic
- ✅ `install.sh` shared-utils copy - fixed in install.sh
- ✅ Command Center `src/lib/persona-selector.ts` - created and points at `persona-selector-v2.py`

---

## [v10.5.0] - 2026-05-17 - Wave 3: v2.1 Integration Layer

### Added - scripts/

- **`post-build-role-workspaces.py`** - Post-hoc role-level workspace creator. Walks `[ZHC]/[company]/departments/` and creates role folders for every department missing them. Reads from `suggested-roles/[dept]-suggested-roles.md` to determine role list. Includes Master Orchestrator (CEO) creation at company root with CEO deferral clause variant. Idempotent.
- **`persona-selector-v2.py`** - v2.1-aware drop-in alternative to `select-persona-for-task.py`. Adds stickiness check, adaptive weights, behavioral profile reading, hybrid mode, weight override application.
- **`gemini-section-indexer.py`** - Section-level indexer. 14 vectors per persona (one per `##` section) instead of 80+ character chunks. Real Gemini embeddings when `GOOGLE_API_KEY` set; deterministic fallback otherwise.
- **`run-v2.1-migrations.sh`** - Orchestrates: platform detect → migrate deferral clauses → re-index Gemini at section level → create role workspaces. One command.
- **`verify-v2.1-installation.sh`** - End-to-end smoke test. 36 checks across file existence, Python syntax, bash syntax, and runtime execution.

### Added - root

- **`RUNBOOK-v2.1.md`** (in skill root) - Operator runbook covering upgrade flow, day-to-day scripts, persona stickiness walkthrough, hand-touch integration list, cron recommendations, troubleshooting, rollback.

### Version

`skill-version.txt` bumped to `10.5.0`.

---

## [v10.4.1] - 2026-05-17 - Wave 2 Execution

### Added

- `scripts/infer-task-category.py` - Classifies a task description into one of 14 task categories. Used by persona stickiness (v2.0 Ch 13) and adaptive weights (v2.0 Ch 17).
- `scripts/create-role-workspaces.py` - Creates role-level workspaces inside a department. Each role gets its own folder with unique IDENTITY/SOUL/MEMORY/HEARTBEAT/how-to.md files plus symlinks to the company-root AGENTS/TOOLS/USER.md. Master Orchestrator role uses the CEO variant of the Persona Governance Override clause.

### Moved

These previously-mandatory suggested-roles files moved to `suggested-roles/_deprecated/`:
- `creative-suggested-roles.md` (folded into Graphics + Video + Audio)
- `hr-people-suggested-roles.md` (no longer mandatory)
- `it-tech-suggested-roles.md` (replaced by OpenClaw Maintenance)
- `operations-suggested-roles.md` (distributed across departments)

Preserved for Audit/Resume mode (Option C) backward compatibility.

### Version

`skill-version.txt` bumped to `10.4.1`.

---

## [v10.4.0] - 2026-05-17 - Zero-Human Company Spec (PRD v2.1)

### Added
- `INSTRUCTIONS.md` rewritten for v2.1 - 30-question interview, 16 mandatory departments, 3 vertical packs
- `department-naming-map.json` reorganized into mandatory / vertical_packs / deprecated tiers
- `templates/universal-how-to-template.md` - 18-section template every role document follows
- `prompts/role-doc-generation-prompt.md` - sub-agent generation prompt with research protocol
- `suggested-roles/crm-suggested-roles.md` - CRM department roles including Email Deliverability flagship
- `suggested-roles/openclaw-maintenance-suggested-roles.md` - OpenClaw Maintenance department with recursive-modification guard
- `suggested-roles/social-media-suggested-roles.md` - Social Media organic department with 10 platform specialists
- `suggested-roles/paid-advertisement-suggested-roles.md` - Paid Advertisement department with 12 platform-specific ad specialists
- Persona Governance Override clause baked into INSTRUCTIONS.md (standard + CEO variant)

### Changed
- Interview density: ~50-65 questions → ~28-30 questions
- All assisting language preserved from v9.6.0: "I Don't Know" 6-step flow, hesitation detection, plain-English progress, pause/resume, specialist auto-staffing

### skill-version.txt
Bumped to `10.4.0`

---

## [v1.5.0] - March 7, 2026

### Changed
- Converted INSTALL.md to agent-executable, autonomous execution format.
- Ensured TYP guardrails are present: MANDATORY TYP CHECK, CONFLICT RULE, and TYP file storage instructions.
- Replaced "say to your AI" instructions with a real multi-phase autonomous execution flow.
