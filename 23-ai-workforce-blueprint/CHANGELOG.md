## [v10.15.35] — 2026-06-09 — CEO = orchestrator-only: production tool lock + canonical SOP-00 Owner Task Routing

### Why
Two gaps remained after v10.15.34's behavioral SOP addition: (1) the CEO/Master Orchestrator
agent entry in `openclaw.json` had no runtime enforcement — an agent could still invoke
production skills. (2) The canonical fleet-wide SOP-00 routing procedure (classify → POST
/api/tasks/ingest → notify owner → NEVER execute) had no permanent home in the
`master-orchestrator-dept/` folder that every install loads.

### Changed
- **`23-ai-workforce-blueprint/scripts/build-workforce.py` — `add_agent_to_config()`**
  - CEO/master-orchestrator agents now get `"skills": []` in their `agents.list[]` entry
  - OpenClaw `skills` at agent level REPLACES defaults (per docs.openclaw.ai/tools/skills-config)
  - Result: `dept-ceo` / `dept-master-orchestrator` cannot invoke image_generate, tts,
    video_generate, coding-agent, browser-automation, or any other installed skill
  - Other department agents (graphics, video, audio, etc.) are unaffected — no `skills` key
    = unrestricted (inherits platform default)
  - Applies to both Mac (`openclaw-onboarding`) and VPS (`openclaw-onboarding-vps`) repos

- **`23-ai-workforce-blueprint/master-orchestrator-dept/SOP-00-Owner-Task-Routing.md` — NEW**
  - Canonical fleet-wide Owner Task Routing SOP (6-step protocol)
  - Covers: classify task, POST to `/api/tasks/ingest` with idempotency_key, acknowledge owner,
    escalation path when CC is unreachable, tool-lock enforcement explanation
  - Binding rules table: what the orchestrator can and cannot do
  - Verified canonical graphics dept head name: Chief Design Officer (role #0 in
    suggested-roles/graphics-suggested-roles.md — "Imani"/"Amani" do not exist in the library)
  - Cross-platform: identical file in both Mac and VPS repos

- **Skill 23 version: 11.0.1 → 11.0.2** (skill-version.txt)

### Files touched (merge coordination)
- `23-ai-workforce-blueprint/scripts/build-workforce.py` — ONLY `add_agent_to_config()` function
  (the `agent_entry` dict + the `is_ceo_agent` guard that follows it). Skill-22 branch touches
  `create_role_workspaces.py` and `install.sh` — zero overlap.
- `23-ai-workforce-blueprint/master-orchestrator-dept/SOP-00-Owner-Task-Routing.md` — NEW FILE
- `23-ai-workforce-blueprint/CHANGELOG.md`
- `23-ai-workforce-blueprint/skill-version.txt`

## [v10.15.34] — 2026-06-09 — master-orchestrator: hard owner-task routing protocol (SOP-00)

### Why
The master-orchestrator (CEO) template lacked an explicit, binding rule preventing it from
executing owner tasks directly. Without SOP-00 the CEO would perform department-level work
itself when an owner sent a task via Telegram — bypassing the routing system, bypassing SOP
coverage, and breaking the AI-workforce model entirely.

### Changed
- **`23-ai-workforce-blueprint/templates/role-library/master-orchestrator/master-orchestrator.md`**
  - Added hard "You are NOT an executor" binding at the top of the "What This Role Is NOT" section
  - Added **SOP-00: Owner Task Routing (HARD PROTOCOL — NO EXCEPTIONS)** immediately before SOP-01
    - 7-step dispatch protocol: receive → classify to THIS client's dept roster → identify specialist → pull SOP → dispatch with full context → confirm to Owner → log
    - Explicit semantic matching: dept names matched by MEANING (e.g. "Brand Storytelling Lab" = brand narrative work), not by canonical keyword
    - Hard "NEVER" list: never draft deliverables, never route to a dept not in THIS client's roster, never dump to CEO/COM as a catch-all
    - Failure-mode handling: one clarifying question OR sub-route to dept director for sub-classification (never self-execute)
  - This is a behavioral document update — **umbrella version NOT bumped** (cut separately per standing policy)

## [v10.15.33] — 2026-06-09 — command-center pipeline fixes: 9 RC repairs to persona selection, governing-personas gate, slug hygiene, build-state backfill, and role-library path

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
- **`shared-utils/llm_score.py` — persona-selector null-content crash (CRITICAL, Fix 1)**
  - `_extract_message()`: null-guard + three-level fallback chain
    (`content` → `reasoning_details` list → `reasoning` string). DeepSeek V4 Pro as a
    THINKING model returns `content: null`; old code did `.strip()` on `None` → AttributeError.
  - `_attempt_openrouter()`: added `"reasoning": {"exclude": True}` to request body to ask
    OpenRouter to suppress thinking tokens upfront; widened except clause to also catch
    `AttributeError`, `KeyError`, `TypeError`.
- **`scripts/generate-governing-personas.sh` — NEW (Fix 2 / build RC-1)**
  New script that writes stub `governing-personas.md` files for any department missing one,
  then exits 0 only when every department has a valid file. Exit 1 = hard fail; exit 2 =
  departments dir unresolvable. Auto-detects ZHC tree (canonical → Mac fallback → VPS
  fallback). Supports `--dry-run`.
- **`INSTALL.md` — Phase 0a HARD STOP + Phase 5-PERSONA HARD gate (Fix 8 / RC-2, Fix 2)**
  - Phase 0a: changed from soft warning to HARD exit 1 when `coaching-personas` Gemini
    collection / `coaching-personas/personas` dir is absent. Operator action item printed.
  - Phase 5-PERSONA gate: replaced soft grep count with call to `generate-governing-personas.sh`
    as a HARD gate; non-zero exit blocks progress to Phase 5-ORG.
- **`INSTALL.md` — Phase 5-BUILD-A2 upgrade-company-config step (Fix 3 / Runtime D)**
  New Phase 5-BUILD-A2 documents and wires `upgrade-company-config.py` into the build
  immediately after config safety and before department workspace creation.
- **`INSTALL.md` — ROLE_LIBRARY_PATH env var documentation (Fix 9 / SOP-pull RC-3)**
  Step 4 of ACTIVATION now documents `$ROLE_LIBRARY_PATH` and `$OPENCLAW_WORKSPACE_PATH`
  overrides for operators whose default skill install templates tree is empty.
- **`scripts/upgrade-company-config.py` — NEW (Fix 3 / Runtime D)**
  Generates or upgrades `company-config.json` to schema v2.0 (adds `mission`,
  `owner_values`, `company_kpis`, `dept_kpis`). Idempotent. CLI: `--upgrade`, `--output`,
  `--dry-run`. Exit 0/1/2.
- **`scripts/sync-md-content-to-db.py` — NEW (Fix 4 / build E)**
  Reads per-dept `SOUL.md` files and writes to `agents.soul_md` in `mission-control.db`.
  Idempotent (skips non-empty rows unless `--force`). Exit 0/1/2.
- **`scripts/build-workforce.py` — explicit `slug` field in departments.json (Fix 5 / RC-3)**
  `generate_departments_json()` now emits `"slug": dept_id` (bare slug) alongside the
  existing `"id": "dept-{dept_id}"` entry. Eliminates runtime string-stripping in CC
  slug-based lookups.
- **`scripts/backfill-build-state.py` — NEW (Fix 6 / build RC-6)**
  Stamps missing gate fields (`sopLibraryStatus`, `roleLibraryStatus`,
  `commsAutomationStatus`, `canonicalReconciliation`, per-dept `roleLibraryFilled` /
  `sopLibraryFilled`) into `.workforce-build-state.json` for pre-v10.16.8 clients.
  Idempotent; heuristic detection. `--force` overwrites existing values. Exit 0/1.
- **`scripts/select-persona-for-task.py` — stale marker consumer (Fix 7 / build RC-5)**
  `_consume_persona_stale_marker()` called at start of `main()`: if `.persona-index-stale`
  exists AND coaching-personas collection is present, re-runs `gemini-indexer.py` then
  deletes the marker. Closes the add-department → stale-persona-index → re-index loop.
- **`scripts/create_role_workspaces.py` — ROLE_LIBRARY_PATH env var (Fix 9 / SOP-pull RC-3)**
  `_resolve_skill_dir()` now checks `$ROLE_LIBRARY_PATH` (validates index exists; warns +
  falls back if not) then `$OPENCLAW_WORKSPACE_PATH/skills/23-ai-workforce-blueprint`
  before the standard detect_platform path. Operators can point the library importer at
  a live ZHC departments tree.

### Also fixed (Skill 32 — seed-workspaces.py)
- **`32-command-center-setup/scripts/seed-workspaces.py` — `dept-` prefix strip (Fix 5 / RC-3)**
  `scan_skill23_workspaces()`: added `dept_id = re.sub(r'^dept-', '', dept_id)` after the
  existing `-dept` suffix stripping so both `dept-marketing` (prefix) and `marketing-dept`
  (suffix) normalize to the bare canonical slug.

### Risk
Low. All new scripts are additive and idempotent. No existing scripts deleted. INSTALL.md
changes only add Phase 5-BUILD-A2 and ROLE_LIBRARY_PATH documentation. Gate changes
(Phase 0a + Phase 5-PERSONA) enforce constraints that were already operator-documented
best-practice — hard-failing only helps operators catch gaps earlier.

---

## [v10.15.32] — 2026-06-02 — 23-department standard (N23): universal vertical-pack primaries

### Why
Clients were shipping with 17 departments (Sheila: 16 mandatory + CEO counted as custom = 17) instead
of the intended 23-25. Root cause: `apply_vertical_packs()` only fired for clients whose industry
keywords matched a pack — a client with no matching keyword got 0 vertical departments added,
landing at 16. Trevor's stated standard is 23-25 = 16 mandatory + 7 vertical packs. The fix makes
one primary department per pack (the `universal_primary` dept) fire for EVERY client regardless of
industry, giving a guaranteed 23-dept floor. Industry keyword matching is preserved for ADDITIONAL
flavor departments on top of the 23 — it no longer acts as a gate reducer.

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
  updated from "16 mandatory" to "23 departments minimum — run `department-floor.py --json`".
- `INSTRUCTIONS.md`: "I Don't Have a Business" pivot and "What Gets Built" section updated to 23-dept.

### Repo
- Repo version bumped to `v10.15.32`.

---

## [v10.15.9] — 2026-05-29 — Cross-skill chain to Skill 38 (ENFORCED) + library-gate status surfacing

Part of repo `v10.15.9` (the 8 rated improvements, port of VPS #47). Two improvements land here:

### Added
- **commsAutomationStatus** state field (+ `commsAutomationDepartments`, `commsAutomationVerifiedAt`,
  `librariesNearCapNotified`) in `build-state-schema.json`. Enforces the Skill 23 → Skill 38 cross-skill
  chain: when the workforce builds a Communications / Sales / Customer-Support department, the build is
  not fully delivered until Skill 38 has scaffolded the matching comms automations.
- New binding **Moment 3.8 — Comms-automation handoff to Skill 38** in `INSTRUCTIONS.md`, plus a
  reciprocal cross-reference in `SKILL.md` (the two siblings previously had zero cross-references).

### Changed
- `scripts/resume-workforce-build.sh`:
  - Treats the build as dirty (and dispatches a `[COMMS-AUTOMATION-RESUME]` self-ping) when all
    departments + libraries are done but `commsAutomationStatus NOT IN {done, not-applicable}`. The
    self-ping points at Skill 38 + `qc-trinity-registry.sh`. Fires after `[LIBRARY-RESUME]`.
  - **Library-gate status surfacing:** emits a one-line OPERATOR-FACING status when libraries stay dirty
    into the last 2 resume attempts (throttled via `librariesNearCapNotified`), and names the library
    status in the hard-cap escalation — a persistently-failing library pull is now visible instead of
    silently retrying to the cap.
- Repo version bumped to `v10.15.9` via `bump-version.sh` (skill-version.txt + the other 7 locations).

---

## [v10.15.8] — 2026-05-29 — ENFORCED Role Library + SOP Library auto-pull gate

### Why
Last night several clients (Kofi / Teresa / Evelyn / Maria / Lyric) had workforces *scaffolded* —
department + role folders existed, depts even flipped to `status: "done"` — but the **role library was
never pulled into the `how-to.md` files** AND the **SOP placeholders were never authored**. Nothing GATED
on those two libraries being populated, so the build "looked done." Prose like "AUTOMATIC NEXT STEP: also
pull the role library" is NOT enforcement (same lesson as the v10.14.16 build-resume fix). Enforcement =
a STATE FIELD + a VERIFY/RESUME GATE. This release adds both. A workforce is now NOT complete (no
`buildCompletedAt`, no closeout) until both libraries are populated.

### Added
- `scripts/verify-library-gate.sh` — the verify gate. Runs `qc-completeness.sh` (read-only), then writes
  `roleLibraryStatus` / `sopLibraryStatus` + per-dept `roleLibraryFilled` / `sopLibraryFilled` +
  `libraryFailureReason` into `.workforce-build-state.json` and exits non-zero unless every dept has the
  role library pulled into every `how-to.md` (library_pct == 100) AND SOPs authored (sop_stubs_remaining
  == 0, avg_sop_per_role > 0). Exit codes: 0 = both done, 2 = role library not done, 3 = SOP library not
  done, 4 = both not done, 5 = no workforce / qc could not run.

### Changed
- `build-state-schema.json` — new enforced gate fields: top-level `roleLibraryStatus`
  (`pending`→`pulling`→`done`/`failed`), `sopLibraryStatus` (`pending`→`authoring`→`done`/`failed`),
  `libraryFailureReason`; per-department `roleLibraryFilled` / `sopLibraryFilled` booleans. `closeoutStatus`
  description updated: the library gate runs BEFORE the closeout gate.
- `scripts/build-workforce.py` — after `qc-completeness.sh`, the build now invokes `verify-library-gate.sh`
  and logs LIBRARY GATE PASS/FAIL; on FAIL it instructs to re-pull and re-run before writing
  `buildCompletedAt` / `closeoutStatus=pending`.
- `scripts/resume-workforce-build.sh` — the 15-min resume cron now computes `library_dirty` (all depts done
  but `roleLibraryStatus != done` OR `sopLibraryStatus != done`) and fires a `[LIBRARY-RESUME]` self-ping
  (BEFORE the closeout gate) instructing the agent to re-run `post-build-role-workspaces.py` /
  `populate-sops-from-manifest.py` then re-run the gate until it passes.
- `resume-prompt.txt` — added a LIBRARY FLOW + decision-tree branch A2 + a gate step in BUILD FLOW step 5.
- `INSTRUCTIONS.md` — new "Moment 3.6 — ROLE LIBRARY + SOP LIBRARY auto-pull gate (BINDING)"; Moment 1 now
  seeds `roleLibraryStatus`/`sopLibraryStatus = pending`; resume-layer section lists the library-dirty
  trigger; "When ALL departments are done" renamed to require the gate first.
- `SKILL.md` — item 10 documents the enforced role/SOP library gate.

### Version
- Repo-wide bump v10.15.7 → v10.15.8 via `scripts/bump-version.sh` (all 8 version locations agree).

---

## [v10.6.2] — 2026-05-19 — Role Library Version Realigned + verify-role-library.sh

### Added
- `scripts/verify-role-library.sh` — 7-check sanity script for the role library on disk. Was referenced from the QC summary "next step" line but never existed until now. Use:
  ```bash
  bash 23-ai-workforce-blueprint/scripts/verify-role-library.sh
  # or
  bash 23-ai-workforce-blueprint/scripts/verify-role-library.sh --skill-dir /path/to/skill
  bash 23-ai-workforce-blueprint/scripts/verify-role-library.sh --json
  ```

### Updated
- `skill-version.txt` → `10.6.2` (was `10.6.1`)
- `templates/role-library/_index.json` `"version"` → `"10.6.2"` (was `"10.6.0"` — stale since the role library merge)
- `templates/role-library/_index.json` `generated_at` refreshed
- `templates/role-library/_qc-summary.md` heading → `Role Library v10.6.2` (was `v10.6.0`)

### Why these were stale
The Wave 5b commit (v10.6.1) only touched `/version` and `/skill-version.txt`. The library files were left at their original v10.6.0 generation values. Repo-wide drift-prevention (`scripts/bump-version.sh` + `.github/workflows/version-consistency.yml`) was added in this same release to prevent recurrence — see root `CHANGELOG.md`.

---

## [v10.6.1] — 2026-05-19 — Wave 5b: Library Template-Fill

### Added
- `scripts/create_role_workspaces.py` — replaces `create-role-workspaces.py` (deleted)
  - New: `library_lookup(role_slug, dept_slug)` — reads `templates/role-library/_index.json` for matching role
  - New: `try_library_fill(role_name, dept_path, is_ceo)` — orchestrates lookup + token-fill, returns filled content or None
  - New: `fill_tokens(content, role_name, dept_name, is_ceo)` — substitutes `{{COMPANY_NAME}}`, revenue cascade tokens (`{{YEARLY_GOAL}}` → cascade ÷4 ÷12 ÷52 ÷250), `{{INDUSTRY_VERTICAL}}`, `{{ROLE_TITLE}}`, `{{DEPARTMENT_NAME}}`, `{{DIRECTOR_OR_MASTER_ORCHESTRATOR}}`, `{{ISO_DATE}}`, `{{ASSIGNED_PERSONA}}`
  - New: `augment_role_folder(role_path, workspace_root)` — idempotent v2.1 file augmentation (previously referenced by post-build, never defined — Wave 4 bug)
  - New: `augment_all_existing_role_folders(dept_path, workspace_root, dry_run)` — walks a dept and augments each role folder (Wave 4 bug fix)
- `create_role_workspace()` now uses library template-fill for `how-to.md` when a match exists; falls back to `stub_how_to()` when no match

### Behavior change for `build-workforce.py`
When `build-workforce.py` finishes a dept build, the post-build hook (in place since Wave 4) now actually works — and where the v10.6.0 library has a matching role doc, the role's `how-to.md` is template-filled from the library instead of left as a stub awaiting a fresh sub-agent generation.

Estimated time-per-role on a typical build: ~3 min (template-fill) vs ~15 min (sub-agent fresh write). With ~210 of 216 library matches across the 16 mandatory depts, a typical build drops from ~3 hours to ~30-45 minutes of role-doc work.

### Removed
- `scripts/create-role-workspaces.py` (hyphen-named — Python could not import it as `create_role_workspaces`)

### Library header stamp
Every doc filled from the library carries a header comment so QC/owner can identify provenance:
```
<!-- Filled from role-library v10.6.0 on YYYY-MM-DD -->
```

---

## [v10.6.0] — 2026-05-19 — Role Library Production (216 PASS docs)

Backfilled. The 216-doc role library was merged to main via `role-library-v10.6.0` branch. The library lives at `templates/role-library/[dept]/[role-slug].md` with an `_index.json` registry.

Library is dormant at v10.6.0 — nothing reads from it. v10.6.1 (Wave 5b) wires it into role workspace creation.

---

## [v10.5.2] — 2026-05-17 — Wave 4.5: Specialist Coverage Expansion

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

## [v10.5.1] — 2026-05-17 — Wave 4: Hand-Touch Integration

### Changed

- **`scripts/build-workforce.py`** — Inline v10.5.1 hook at the end of `build_from_config()`. After all departments and persona matrix are created, spawns `post-build-role-workspaces.py` via subprocess (30s timeout) to augment every role folder with v2.1 files. Wrapped in try/except so failure doesn't break the main build.
- **`scripts/post-build-role-workspaces.py`** — Reworked to AUGMENT existing role folders rather than create duplicates. Detects pre-v2.1 role folders (any naming pattern, with or without numeric prefix) and adds IDENTITY.md, SOUL.md, MEMORY.md, HEARTBEAT.md, how-to.md stub, and AGENTS/TOOLS/USER symlinks in place. Master Orchestrator (CEO) created at company root with CEO deferral clause if missing. Pre-v2.1 files like `00-START-HERE.md` are preserved.

### Version

`skill-version.txt` bumped to `10.5.1`.

### What's no longer a hand-touch (RUNBOOK Section 5)

- ✅ `build-workforce.py` post-build call — now automatic
- ✅ `install.sh` shared-utils copy — fixed in install.sh
- ✅ Command Center `src/lib/persona-selector.ts` — created and points at `persona-selector-v2.py`

---

## [v10.5.0] — 2026-05-17 — Wave 3: v2.1 Integration Layer

### Added — scripts/

- **`post-build-role-workspaces.py`** — Post-hoc role-level workspace creator. Walks `[ZHC]/[company]/departments/` and creates role folders for every department missing them. Reads from `suggested-roles/[dept]-suggested-roles.md` to determine role list. Includes Master Orchestrator (CEO) creation at company root with CEO deferral clause variant. Idempotent.
- **`persona-selector-v2.py`** — v2.1-aware drop-in alternative to `select-persona-for-task.py`. Adds stickiness check, adaptive weights, behavioral profile reading, hybrid mode, weight override application.
- **`gemini-section-indexer.py`** — Section-level indexer. 14 vectors per persona (one per `##` section) instead of 80+ character chunks. Real Gemini embeddings when `GOOGLE_API_KEY` set; deterministic fallback otherwise.
- **`run-v2.1-migrations.sh`** — Orchestrates: platform detect → migrate deferral clauses → re-index Gemini at section level → create role workspaces. One command.
- **`verify-v2.1-installation.sh`** — End-to-end smoke test. 36 checks across file existence, Python syntax, bash syntax, and runtime execution.

### Added — root

- **`RUNBOOK-v2.1.md`** (in skill root) — Operator runbook covering upgrade flow, day-to-day scripts, persona stickiness walkthrough, hand-touch integration list, cron recommendations, troubleshooting, rollback.

### Version

`skill-version.txt` bumped to `10.5.0`.

---

## [v10.4.1] — 2026-05-17 — Wave 2 Execution

### Added

- `scripts/infer-task-category.py` — Classifies a task description into one of 14 task categories. Used by persona stickiness (v2.0 Ch 13) and adaptive weights (v2.0 Ch 17).
- `scripts/create-role-workspaces.py` — Creates role-level workspaces inside a department. Each role gets its own folder with unique IDENTITY/SOUL/MEMORY/HEARTBEAT/how-to.md files plus symlinks to the company-root AGENTS/TOOLS/USER.md. Master Orchestrator role uses the CEO variant of the Persona Governance Override clause.

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

## [v10.4.0] — 2026-05-17 — Zero-Human Company Spec (PRD v2.1)

### Added
- `INSTRUCTIONS.md` rewritten for v2.1 — 30-question interview, 16 mandatory departments, 3 vertical packs
- `department-naming-map.json` reorganized into mandatory / vertical_packs / deprecated tiers
- `templates/universal-how-to-template.md` — 18-section template every role document follows
- `prompts/role-doc-generation-prompt.md` — sub-agent generation prompt with research protocol
- `suggested-roles/crm-suggested-roles.md` — CRM department roles including Email Deliverability flagship
- `suggested-roles/openclaw-maintenance-suggested-roles.md` — OpenClaw Maintenance department with recursive-modification guard
- `suggested-roles/social-media-suggested-roles.md` — Social Media organic department with 10 platform specialists
- `suggested-roles/paid-advertisement-suggested-roles.md` — Paid Advertisement department with 12 platform-specific ad specialists
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
