# OpenClaw System Diagnostic Checklist

**Last verified against:** onboarding `/version` v25.1.101, paired Command Center v7.6.72 (2026-09-28).
**Purpose:** Single source of truth for verifying the AI workforce + Book-to-Persona + Command Center + Gemini Engine stack works as one fluid system.

Run this checklist:
- After every onboarding install
- Before every Sunday weekly update
- Any time something feels broken
- Before any major release

The automated runner is at **`scripts/qc-system-integrity.sh`** (invoked by `install.sh` as its final step and runnable standalone as `~/.openclaw/scripts/qc-system-integrity.sh` on Mac or `/data/.openclaw/scripts/qc-system-integrity.sh` on a VPS). Rows below marked **(runner)** are asserted automatically with the exact check ID shown; rows marked **(manual)** require a quick read or one-off command because they verify prose/doctrine or a state the runner does not yet automate. The runner exits 0 only when every **required** check (`✓`/`✗`) passes — **warn-only** checks (`⚠`) are reported but do not fail the run unless noted.

---

## How the pieces fit together

```
┌──────────────────────────────────────────────────────────────────────┐
│ Skill 31: Upgraded Memory System (8-layer memory)                     │
│   - Layer 4: Gemini Embedding 2 (vector index of:                     │
│       • coaching-personas (personas + persona-categories.json)        │
│       • the box's own clawd/workspace files                           │
│       • master-files collection                                       │
│   - scripts/gemini-indexer.py builds the embeddings                   │
│   - scripts/gemini-search.py runs semantic queries                    │
│   - All 8 layers are required (markdown files, memory flush, session  │
│     indexing, Gemini Embedding 2, memory-core, Cognee, Obsidian       │
│     Vault, Wiki System) — see 31-upgraded-memory-system/SKILL.md      │
└────────────────────────────────────┬─────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Skill 22: Book-to-Persona                                              │
│   - Reads books (PDF/EPUB) → produces persona blueprints              │
│   - 14-section persona-blueprint.md per book (see CHECKLIST.md):      │
│       Identity & Voice · Core Philosophy · Signature Framework ·      │
│       Key Principles · Coaching Mode (invoke/respond) · Task Mode     │
│       (invoke/execute) · Department Routing · Trigger Phrases ·       │
│       Sample Responses · Boundaries · Cross-Persona Integration ·     │
│       Quick Reference Card                                            │
│   - persona-categories.json: domain + perspective tags per persona    │
│     (open, book-derived vocabulary — not a fixed enum; see CHECK 6)   │
│   - Output indexed by Gemini Engine (Skill 31)                        │
└────────────────────────────────────┬─────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Skill 23: AI Workforce Blueprint                                       │
│   - Interviews the owner: theme-based, Phases 1-6 + Phase 5.5         │
│     department reconciliation (INSTRUCTIONS.md is authoritative)      │
│   - Creates the ZHC folder: workspace/zero-human-company/<slug>/      │
│   - Every company gets the CANONICAL FLOOR (mandatory departments +   │
│     the universal-primary vertical packs) unless explicitly declined  │
│     — the floor is COMPUTED, never hand-typed. Run                    │
│     `scripts/list-canonical-departments.py` or                        │
│     `scripts/department-floor.py` for the current count; do not cite  │
│     a fixed number anywhere else                                      │
│   - Per dept: director + specialist roles, each in its own subfolder  │
│   - DMAIC SOPs authored by parallel sub-agents                        │
│   - Act As If Protocol + 5-layer persona alignment for task→persona   │
│   - governing-personas.md per dept (pre-qualified pool)               │
│   - AGENTS.md/TOOLS.md/USER.md are REAL-FILE copies of this box's     │
│     canonical files, byte-identical, re-copied on every install/      │
│     update run (N29, amended 2026-07-31 — NOT symlinks; the runtime's │
│     workspace-root boundary guard rejects a symlink outright)         │
│   - Per-agent config: 200K/400K bootstrap, canonical sub-agent block  │
│   - Writes departments.json + company-config.json (with brand colors) │
└────────────────────────────────────┬─────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Skill 32: BlackCEO Command Center                                      │
│   - Activates persistent department agents (each binds to a topic)    │
│   - Kanban dashboard at localhost:4000 (or a Cloudflare tunnel)       │
│   - Reads ZHC departments.json → seeds the mission-control.db         │
│     workspaces table                                                  │
│   - Reads company-config.json → renders brand colors                  │
│   - Telegram supergroup with one topic per department                 │
│   - Runtime task→persona flow:                                        │
│       1. Task lands in the dept Telegram topic                        │
│       2. Director invokes persona-selector-v2.py (canonical selector) │
│       3. Pre-scoring funnel: pool → category (keyword) → semantic     │
│       4. Selected persona logged (persona-selection-log.md / dept     │
│          memory)                                                      │
│       5. Sub-agent spawned with an "Act as if you are [persona]"      │
│          instruction                                                  │
│       6. Sub-agent executes following the DMAIC SOP                   │
│       7. Devil's Advocate validates measurable Done criteria          │
│       8. Kanban card moves to Done                                    │
└──────────────────────────────────────────────────────────────────────┘
```

The whole thing is one pipeline. A break anywhere downstream of Skill 22 cascades. A break in Gemini Engine (Skill 31) silently degrades runtime persona selection.

---

## CHECK 1 — AI Workforce Interview (Skill 23)

| # | Check | How to verify | Pass = |
|---|---|---|---|
| 1.1 **(runner 1.1)** | ZHC folder exists for the client | `ls ~/clawd/zero-human-company/*/` (Mac) or `ls /data/.openclaw/workspace/zero-human-company/*/` (VPS) | At least one company slug folder, with `departments/` inside |
| 1.2 **(runner 1.2)** | Pre-interview research file present | `cat <company_dir>/pre-interview-research.md` | File exists, even if minimal (intentionally absent if the client said "no docs") |
| 1.3 **(runner 1.3)** | workforce-interview-answers.md exists | `ls <company_dir>/workforce-interview-answers.md` | File exists |
| 1.4 **(runner 1.4)** | interview-handoff.md has a status field | `grep status <company_dir>/interview-handoff.md` | Field present (`complete` if all done, `in_progress` if mid-flight) |
| 1.5 **(runner 1.5)** | MEMORY.md has a `## AI Workforce Build` section | `grep -q '## AI Workforce Build' ~/clawd/MEMORY.md` | Section exists |
| 1.6 (manual) | Interview follows the current phase-based spec, not a fixed question count | Read `23-ai-workforce-blueprint/INSTRUCTIONS.md` (Phases 1-6 + Phase 5.5) | The interview is theme-based, not the old "2-3 mandatory questions" model; department build-intake is "up to 7 questions per department" (`ai-workforce-blueprint-full.md` § Department Build-Intake Questions) |
| 1.7 (manual) | Pre-pass / "don't re-ask" rule active | `grep -n "context-ingest.py\|Do NOT re-ask cold\|confirmed-from-context" 23-ai-workforce-blueprint/INSTRUCTIONS.md` | `scripts/context-ingest.py` pre-pass exists and INSTRUCTIONS.md instructs "Do NOT re-ask cold" — confirmed answers are logged as `confirmed-from-context: <source>` |
| 1.8 (manual) | Save-on-break message standardized | `grep -rn "Resume my AI workforce setup" 23-ai-workforce-blueprint/*.md` | Phrase present (INSTALL.md, SKILL.md, CORE_UPDATES.md) |

## CHECK 2 — AI Workforce Skill Set (Skill 23 build phase)

| # | Check | How to verify | Pass = |
|---|---|---|---|
| 2.1 **(runner 2.1)** | Department folder count matches departments.json | Compare `len(json.load(open(departments.json)))` to `ls -d <company_dir>/departments/*/ \| wc -l` | Equal. Never compare against a hand-typed number — the canonical floor is computed by `department-floor.py`, not fixed |
| 2.2 **(runner 2.2)** | Each dept has a director subfolder | `find <company_dir>/departments -maxdepth 2 -type d -name '00-*'` | At least one `00-<director-title>/` folder exists |
| 2.3 **(runner 2.3, warn-only)** | AGENTS.md / TOOLS.md / USER.md are real-file copies, not symlinks | `find <company_dir>/departments -type l \( -name AGENTS.md -o -name TOOLS.md -o -name USER.md \)` | **Empty result.** Per N29 (amended 2026-07-31), these files must be real-file copies, byte-identical to this box's canonical — a symlink is now REJECTED by the runtime's workspace-root boundary guard, not the correct state. ⚠ Known drift: the runner's own 2.3 check still prints "should be symlinked" when it finds copies — that message is stale; CHECK 2.9 (9.9 below) is the authoritative, hard-fail version of this check and should be trusted over 2.3's wording |
| 2.4 **(runner 2.4)** | Every dept director agent registered | `jq '(.agents.entries // {}) + (.agents.list // [])' ~/.openclaw/openclaw.json` — count entries/list items whose `id` starts with `dept-` | One entry per department (OpenClaw config now supports both the `agents.entries` map and the legacy `agents.list[]` array; the runner checks both) |
| 2.5 **(runner 2.5)** | Every dept director has canonical sub-agent + bootstrap config | Same registry — check each `dept-*` entry | `bootstrapMaxChars=200000`, `bootstrapTotalMaxChars=400000`, `subagents.maxChildrenPerAgent=20`, `subagents.maxConcurrent=100`, `subagents.maxSpawnDepth=5`, `subagents.thinking="high"`, `subagents.allowAgents=["*"]` |
| 2.6 **(runner 2.6, informational)** | SOPs populated (not stubs) | `grep -rl "to be personalized based on research" <company_dir>/departments` | **Empty result.** A non-empty result on a build that should be finished means the populate step never ran — not a failure on a build that is still in progress |
| 2.7 **(runner 2.7, warn-only)** | "No guessing" rule in every SOP | `grep -L "DO NOT GUESS\|Guessing is forbidden\|no guessing" <company_dir>/departments/*/*/0[1-9]-*.md` | **Empty result** (every SOP contains the rule) |
| 2.8 (manual) | DMAIC sections in every SOP | `grep -L "## DEFINE" <company_dir>/departments/*/*/0[1-9]-*.md` (repeat for MEASURE/ANALYZE/IMPROVE/CONTROL, or grep each file for all five) | Empty result — every SOP carries all 5 DMAIC sections |
| 2.9 **(runner 2.9)** | Devil's Advocate per dept | `find <company_dir>/departments -path '*/devils-advocate/SOP.md'` | At least one match |
| 2.10 **(runner 2.10)** | ORG-CHART.md at company root | `cat <company_dir>/ORG-CHART.md` | Exists, lists CEO + each dept director + specialists |
| 2.11 **(runner 2.11, warn-only)** | Role-library materialization coverage ≥ 75% | Runner compares each dept's role-folder count against `23-ai-workforce-blueprint/templates/role-library/_index.json`'s `departments.<dept>.role_count` | ≥ 75% of expected roles materialized per department; `qc-completeness.sh` gives the full per-dept breakdown |
| 2.12 **(runner 2.12, warn-only)** | `how-to.md` library-fill provenance ≥ 75% | Runner counts `<!-- Filled from role-library v... -->` markers across role folders | ≥ 75% of role folders carry the provenance marker |
| 2.13 **(runner 2.13, warn-only)** | IDENTITY.md per role folder ≥ 95% | Runner counts `IDENTITY.md` files against role-folder count | ≥ 95% coverage |
| 2.14 **(runner 2.14)** | No stranded legacy `departments/` tree | Runner compares `/data/clawd/departments` or `~/clawd/departments` against the canonical `<company_dir>/departments` (realpath) | No legacy tree present, or it resolves to the same canonical path. A distinct stranded tree is a hard fail — run `reconcile-legacy-tree.py` |
| 2.15 **(runner 2.15, warn-only)** | Exposed-file census clean | Runner hashes every `AGENTS.md` under `departments/` against a known-exposed hash list | 0 exposed of N — a non-zero count means an operator-scoped copy leaked into a client department tree (U053/U054 remediation) |

## CHECK 3 — Book-to-Persona (Skill 22)

| # | Check | How to verify | Pass = |
|---|---|---|---|
| 3.0 **(runner 3.0)** | Canonical coaching-personas directory resolves | `ls ~/.openclaw/workspace/data/coaching-personas/` (Mac) or `/data/.openclaw/workspace/data/coaching-personas/` (VPS) | Directory exists (created on first Skill 22 run if missing) |
| 3.1 **(runner 3.1)** | persona-blueprint.md present per processed book | `find <coaching-personas-dir>/personas -name 'persona-blueprint.md' \| wc -l` | ≥ 1 |
| 3.2 (manual) | Each blueprint has all 14 sections | `grep -c '^## Section' <persona-dir>/persona-blueprint.md` | 14 (Section 1 through Section 14 — see CHECKLIST.md for the canonical list; names changed from earlier releases, see the pipeline diagram above) |
| 3.3 (manual) | Coaching Mode + Task Mode both present | `grep -c '^## Section [5-8]' <persona-dir>/persona-blueprint.md` | 4 — Sections 5-6 (Coaching Mode: When to Invoke / How to Respond) and 7-8 (Task Mode: When to Invoke / How to Execute) all present |
| 3.4 (manual) | Department Routing + Quick Reference present | `grep -E '^## Section (9|14)' <persona-dir>/persona-blueprint.md` | Section 9 (Department Routing) and Section 14 (Quick Reference Card) both present |
| 3.5 **(runner 3.5)** | persona-categories.json present + valid JSON | `python3 -c 'import json; json.load(open("<coaching-personas-dir>/persona-categories.json"))'` | Valid JSON (canonical path is `workspace/data/coaching-personas/persona-categories.json`; the skill-folder copy under `22-book-to-persona-coaching-leadership-system/` is the shipped read-only seed) |
| 3.6 **(runner 3.6, warn-only)** | Model selection is dynamic (not hardcoded) | `grep "moonshot/kimi-k2.6\|deepseek/deepseek-v3.2\|gpt-5.3-codex" ~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/_meta.json` | **Empty result** — selector-driven, no pinned model literal |
| 3.7 **(runner 3.7, warn-only)** | No Anthropic refs in Skill 22 active code | `grep -rn "anthropic/\|claude-opus\|claude-sonnet" ~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/pipeline/*.py` | **Empty result** — N1 (AGENTS.md): the pipeline runs on DeepSeek V4 Pro / Gemini Flash, never Anthropic |

## CHECK 4 — Gemini Embeddings 2 (Skill 31)

| # | Check | How to verify | Pass = |
|---|---|---|---|
| 4.1 **(runner 4.1)** | gemini-indexer.py present | `ls ~/clawd/scripts/gemini-indexer.py` (Mac) or `ls ~/.openclaw/workspace/scripts/gemini-indexer.py` / `/data/.openclaw/workspace/scripts/gemini-indexer.py` (VPS) | File exists at one of those workspace-scripts paths — **not** `~/.openclaw/scripts/` (a stale path from an earlier release) |
| 4.2 **(runner 4.2)** | gemini-search.py present | Same directory as 4.1 | File exists |
| 4.3 **(runner 4.3, warn-only)** | `--status` reports the coaching-personas collection | `python3 <gemini-indexer.py> --status \| grep -qi coaching-personas` | Match found |
| 4.4 **(runner 4.4, warn-only)** | `--status` reports the clawd workspace collection | `python3 <gemini-indexer.py> --status \| grep -qi clawd` | Match found |

**Note:** earlier releases of this doc listed separate `master-files` and `zhc-<slug>` collection checks and a `--status` re-index milestone table. The runner does not assert those today; the coaching-personas index is instead verified directly against the on-disk persona count and a live sqlite index — see CHECK X.3-X.6 below, which supersedes the old 4.5-4.8.

## CHECK 5 — Semantic Search (runtime persona selector)

| # | Check | How to verify | Pass = |
|---|---|---|---|
| 5.1 **(runner 5.1)** | persona-selector-v2.py present + executable (canonical selector) | `[ -x ~/.openclaw/skills/23-ai-workforce-blueprint/scripts/persona-selector-v2.py ]` | Executable bit set |
| 5.1a **(runner 5.1a)** | select-persona-for-task.py is a shim, not a standalone implementation | `grep -q 'DEPRECATED SHIM' <path>/select-persona-for-task.py` | Match found — it delegates every call to `persona-selector-v2.py` |
| 5.2 **(runner 5.2, warn-only)** | Test invocation returns a persona id | `python3 persona-selector-v2.py --department marketing --task "Write a launch email" --format json` | JSON output includes a non-empty `persona_id` |
| 5.3 (manual) | Output includes funnel counts | Same call, inspect the `funnel` key | `"funnel": {"pool": N, "category": N, "semantic": N}` — **note:** these are the current key names (PRD item 1.2); earlier releases of this doc named them `after_keyword`/`after_semantic`, which no longer appear in the output |
| 5.4 (manual) | Falls back gracefully if the semantic engine is unavailable | Make the configured embedding provider unreachable, re-run the selector | Selector still returns a winner via the keyword/category stage rather than erroring out |

## CHECK 6 — Keyword / Domain Tagging

| # | Check | How to verify | Pass = |
|---|---|---|---|
| 6.1 **(runner 6.1, warn-only)** | persona-categories.json entries carry domain tags | `python3 -c '...'` (runner accepts any of `domain_tags`, `domain`, or `tags` per persona) | Every persona has at least one non-empty domain/tag field |
| 6.2 (manual) | Domain vocabulary is open, not a fixed list — don't gate on an exact tag set | Inspect a few entries in `persona-categories.json` (`domain` array) | Tags are book-derived and department-specific (e.g. `strategy-innovation`, `software-craft`, `productivity-systems`) — **there is no fixed 12-tag closed list anymore**; earlier releases of this doc asserted one and it no longer matches the data |
| 6.3 (manual) | Department → domain-tag mapping exists in the canonical selector | `grep -n "^DEPT_DOMAIN_TAGS" -A 5 23-ai-workforce-blueprint/scripts/persona-selector-v2.py` | `DEPT_DOMAIN_TAGS` dict exists and has an entry for each live department slug — the mapping must be kept in lockstep with `build-workforce.py`'s `generate_persona_matrix` dept-to-domain map (see the in-file comment on the `engineering` entry for why) |
| 6.4 (manual) | `keyword_filter()` / the pre-scoring funnel narrows candidates | Add a non-matching candidate persona, re-run the selector | Candidate is filtered out before the semantic scoring stage |

## CHECK 7 — Task Assignments (Kanban / Command Center)

| # | Check | How to verify | Pass = |
|---|---|---|---|
| 7.0 **(runner 7.0)** | mission-control.db resolves | `python3 shared-utils/resolve_db.py --path` | Prints a path to an existing, non-empty `mission-control.db` (falls back to `~/projects/command-center/mission-control.db`, `~/projects/mission-control/mission-control.db`, or `/opt/mission-control/mission-control.db` if the resolver script isn't available) |
| 7.1 **(runner 7.1)** | Kanban dept count matches departments.json | `sqlite3 <db> "SELECT COUNT(*) FROM workspaces WHERE company_id='<slug>'"` vs `len(departments.json)` | Equal — never compare against a hand-typed department count |
| 7.2 **(runner 7.2, informational)** | Company row has brand colors | `sqlite3 <db> "SELECT config FROM companies WHERE slug='<slug>'"` | JSON contains a `"primary"` key. Missing brand colors is cosmetic (falls back to neutral defaults), not a failure |
| 7.3 (manual) | Telegram topics exist per dept | Open the client's Telegram supergroup, count topics (per `32-command-center-setup/SKILL.md` § Telegram Command Center) | One topic per department, organized as documented in Skill 32's own setup checklist |
| 7.4 (manual) | Each topic is bound to the correct dept agent | Follow Skill 32's own QC checklist item "Telegram bindings configured for each topic" | Messages in a dept's topic are answered by that dept's agent, not another one |
| 7.5 **(runner 7.5, warn-only)** | Kanban dashboard reachable | `curl -s -o /dev/null -w "%{http_code}" http://localhost:4000` | 200 |
| 7.6 (manual) | Dashboard renders brand colors | Open in a browser | Primary/accent visually match `company-config.json` |

## CHECK 8 — Persona Assignments

| # | Check | How to verify | Pass = |
|---|---|---|---|
| 8.1 **(runner 8.1)** | governing-personas.md exists per dept | `find <company_dir>/departments -name governing-personas.md` | One per dept |
| 8.2 **(runner 8.2)** | persona-matrix.md at company root | `ls <company_dir>/persona-matrix.md` | Exists, lists the pre-qualified pool |
| 8.3 (manual) | Pre-qualification is applied, not the full persona pool | Read `persona-matrix.md` | Personas are filtered by company mission + owner values, not every persona in the library |
| 8.4 (manual) | Selector runs fresh per task (not caching a winner) | Two invocations with different task context | Different winners — confirms the selector isn't caching |
| 8.5 (manual) | Persona reason log written | `cat <company_dir>/departments/<dept>/memory/$(date +%Y-%m-%d).md` (or the dept's own memory path) | An entry per task with the persona selection breakdown |
| 8.6 (manual) | "Act As If" protocol documented | `grep -n "Act [Aa]s [Ii]f" 23-ai-workforce-blueprint/SKILL.md` | Phrase present — still the current runtime-execution doctrine (`23-ai-workforce-blueprint/SKILL.md` § The Act As If Protocol) |

## CHECK 9 — Agent Linking

| # | Check | How to verify | Pass = |
|---|---|---|---|
| 9.2 **(runner 9.2)** | Every `dept-*` agent's workspace path exists on disk | Runner reads `agents.entries`/`agents.list[]`, checks `os.path.isdir(workspace)` for each `dept-*` id | 0 agents with a stale/missing workspace path |
| 9.5-9.7 (covered by 2.5) | allowAgents, bootstrap propagation, `thinking="high"` | See CHECK 2.5 above | 2.5 already asserts all of these fields together per dept agent — do not check them separately, that duplicates 2.5 and can disagree with it |
| 9.8 **(runner 9.8)** | Master AGENTS.md / TOOLS.md / USER.md exist at workspace root | `ls ~/clawd/{AGENTS,TOOLS,USER}.md` | Three regular files present |
| 9.9 **(runner 9.9)** | Shared core files unified (real file, byte-identical to canonical) | Runner hashes `AGENTS.md`/`TOOLS.md`/`USER.md` in every non-workflow-agent workspace against this box's own canonical (from `openclaw.json`) | Every file is a real file (not a symlink) with a matching sha256 hash. **A symlink is itself a FAIL** — N29 amended 2026-07-31: the runtime's workspace-root boundary guard rejects any symlink resolving outside the reading agent's own workspace, regardless of target, and injects a stub with no visible error. Nested workflow agents (`*/workflows/*/agents/*`) are exempt |
| 9.10 (covered by 2.14) | No legacy `~/clawd/departments/` content drift | See CHECK 2.14 above | 2.14 is the runner's hard-fail version of this check |

---

## CROSS-CUTTING — System integrity

These run inside `qc-system-integrity.sh` after CHECK 9, in this order. Most delegate to a dedicated `scripts/qc-assert-*.sh` script — each one is independently runnable for a fuller trace than the summary line.

| # | Check | Delegate script | Pass = |
|---|---|---|---|
| X.2 **(runner)** | Bootstrap limits canonical | (inline) | `agents.defaults.bootstrapMaxChars` / `bootstrapTotalMaxChars` = `200000` / `400000` |
| X.3 **(runner)** | ≥ 40 persona blueprints on disk | (inline, "Coaching-Personas Pipeline" section) | `find <coaching-personas-dir>/personas -maxdepth 2 -name '*.md'` returns ≥ 40 (current on-disk count is 99; 40 is the floor, not the target) |
| X.4 **(runner)** | persona-categories.json catalog count ≤ on-disk persona count | (inline) | Catalog never claims more personas than actually exist on disk |
| X.5 **(runner)** | gemini-index.sqlite has ≥ 40 embedded persona rows | (inline) | `SELECT COUNT(DISTINCT file_path) FROM embeddings WHERE file_path LIKE '%coaching-personas/personas/%'` ≥ 40 |
| X.6 **(runner)** | gemini-search.py returns a result for a known query | (inline) | `python3 scripts/gemini-search.py 'leadership coaching' --limit 1` returns a `PERSONA:`/`SCORE:`/`KEYWORD-HITS:` line |
| X.7 **(runner, warn-only)** | No un-migrated legacy ZHC company roots | (inline) | 0 legacy roots with company folders, or all already recorded in `.migration-log.json` |
| X.8 **(runner)** | Provider capability invariants | `qc-assert-provider-capability-invariants.sh` | No `memorySearch.fallback="none"` (I1) and no `multimodal.enabled=true` against a text-only embedding provider (I2) |
| X.9 **(runner)** | Ollama provider matches platform standard | `qc-assert-ollama-provider-platform.sh` | Mac = signed-in local daemon (`127.0.0.1:11434`, `ollama-local`); VPS = cloud-direct (`ollama.com` + client `OLLAMA_API_KEY`); no `:cloud` model configured with `maxTokens > 64000` anywhere |
| X.10 **(runner)** | No real client names in tracked repo files | `qc-assert-no-client-names.sh` | 0 hits — this repo is a fleet-wide generic template; a client name in a committed file is a co-mingling/privacy violation |
| X.11 **(runner)** | Workspace departments are materialized, not shells | `qc-assert-workspace-departments-built.sh` | rc=0: every required dept has a built-out workspace (not just a role-library template copy), no phantom duplicate dept trees, and the chosen/provisioned/displayed department sets agree |
| X.12 **(runner)** | Repo consistency + downstream artifact coverage | `qc-assert-repo-consistency.py` (skill-dir mode) | Floor/roster/role-library/SOP-source/persona-domain dimensions agree, AND every downstream artifact (org chart, routing map, Command Center, dreaming exclusions, bootstrap templates, skill count, version markers) reflects the same floor departments |
| X.13 / X.13b / X.13c **(runner)** | GHL MCP (Skill 36, Tier 2) supervision, runtime conformance, pin-file delivery | `qc-assert-ghl-mcp-supervised.sh`, `ghl-mcp-assert-runtime.sh`, `qc-assert-pin-delivery-paths.sh` | Supervised (launchd/pm2/systemd, reboot-surviving, port-pinned) both as shipped AND as actually installed; every pin-file resolver path is a path an installer actually populates |
| X.14 **(runner)** | Platform-facts stamp in AGENTS.md | `qc-assert-platform-facts-stamped.sh` | The active `AGENTS.md` carries the `<!-- PLATFORM_FACTS_V1 -->` marker (platform label, env/secrets location) and it matches the box's real platform |

**Manual cross-cutting checks not automated by the runner:**

| # | Check | How to verify | Pass = |
|---|---|---|---|
| M.1 (manual) | Anthropic models forbidden fleet-wide | `grep -rnE "anthropic/\|claude-opus\|claude-sonnet\|claude-haiku" --include="*.py" --include="*.json" .` | Zero hits outside a documented FORBIDDEN-list / changelog explanation — see AGENTS.md N1 and N35 (AF-MODEL-SOVEREIGNTY) |
| M.2 (manual) | Repo version markers consistent | `bash scripts/bump-version.sh --check` (or read `scripts/version-markers.json`) | All 10 registered markers equal `/version`. Do not hand-check individual files — the marker list itself is the source of truth and changes over time |
| M.3 (manual) | Doc-currency guards pass | `bash scripts/check-doc-currency-guards.sh` | All OK — this is the dedicated guard for exactly the kind of drift this checklist itself needed fixing for (paired-release prose, persona counts) |
| M.4 (manual) | GHL daily quota not exhausted (won't block install if so) | `bash ~/.openclaw/skills/36-ghl-mcp-setup/qc-ghl-mcp-setup.sh 2>&1 \| grep "Daily quota remaining"` | Remaining count > 100 (hard floor) / > 5000 (safe for bulk ops) — **note:** the script's own thresholds, not the `X-RateLimit-Daily-Remaining` HTTP header name; that header is consumed internally and never echoed verbatim |

---

## What to do when a check fails

Each runner check has a remediation recipe baked into `qc-system-integrity.sh`'s own output (the `FAILURES`/`WARNINGS` arrays print the exact next command). Most fixes are one-liners. If a fix requires re-running a skill install, use `update-skills.sh --only "23,32"` (comma-separated skill-number prefixes).

**Common patterns:**

| Symptom | Likely failed check | Fix |
|---|---|---|
| Dashboard department count doesn't match what the client picked | 7.1 | Rerun `python3 32-command-center-setup/scripts/seed-workspaces.py` after confirming `departments.json` is fresh — never compare against a hand-typed count |
| Marketing Director keeps using the same persona for every task | 8.4 | Confirm there is no caching layer sitting in front of `persona-selector-v2.py`; it must score fresh per invocation |
| Tasks pile up in "In Progress," never reaching Done | X.11 / 2.9 | Verify `devils-advocate/SOP.md` exists for that dept; check the Command Center done-gate (a task-PATCH must carry a valid `process_certificate_sha`) |
| One dept's AGENTS.md/TOOLS.md/USER.md is stale after a master edit | 9.9 | Real-file copies propagate on the NEXT `update-skills.sh` / `install.sh` (Step 10a) run, not instantly. Re-run it. If content still diverges afterward, `build-workforce.py` may not have written the canonical file at all |
| Persona selection always returns the same winner | X.5 + X.6 + 8.4 | Gemini index stale, or no semantic scores, or the funnel is broken. Run `gemini-indexer.py`, then re-test with `gemini-search.py` |
| SOPs still contain `to be personalized based on research` | 2.6 | Run `python3 23-ai-workforce-blueprint/scripts/populate-sops-from-manifest.py --manifest <path>` |
| Brand colors are neutral/generic in the dashboard | 7.2 + 7.6 | Either `company-config.json` is missing brand fields, or the frontend isn't reading `companies.config` |
| A required department is a shell (DREAMS.md + memory/ only, no roles) | X.11 (rc=3) | Run `build-workforce.py` / `post-build-role-workspaces.py` to instantiate the workspace, not just the role-library template |
| Same department materialized twice under sibling folder names | X.11 (rc=5) | `python3 23-ai-workforce-blueprint/scripts/reconcile-legacy-tree.py --merge-duplicates` (dry-run first, then `--apply`) |
| A paid-for department has no Command Center column | X.11 (rc=6) | `python3 23-ai-workforce-blueprint/scripts/prove-board-join.py --json`, then re-seed with `seed-workspaces.py` |

---

## Schedule

- **Every install:** runs automatically as `install.sh`'s final step
- **Every Sunday:** `weekly-full-update.sh` runs `fleet-refresh.sh --local --apply`, which snapshots first, then runs the same health gate (gateway process + `/health`, Telegram `getMe`, Command Center `/api/health`, a `sessions.reset` probe) plus a content-integrity gate (persona index, SOP library, role-library digest) after the update — a failing check gets up to 3 automatic fix attempts before the box is rolled back to its snapshot
- **Ad-hoc:** any time a client reports "it's acting weird"

`qc-system-integrity.sh` exits 0 = all required checks passed, 1 = one or more required checks failed (see the printed `FAILURE DETAILS`/`WARNING DETAILS` blocks). Warnings never change the exit code unless a future gate is explicitly promoted (see `lib-qc-shared.sh`'s `QC_FAIL_ON_WARN` mechanism).

### The fleet-wide health gate, in full

`shared-utils/fleet_refresh_runner.py` is what `fleet-refresh.sh` and `weekly-full-update.sh` both call per box. Its health checks:

- **gateway-process** — an `openclaw ... gateway` process is actually running
- **gateway-health** — `http://127.0.0.1:<gateway.port, default 18789>/health` returns 200
- **telegram-getme** — every configured bot token answers Telegram's `getMe` (read-only; never sends a message)
- **cc-health** — `http://127.0.0.1:<CC_PORT, default 4000>/api/health` returns 200 (n/a if no Command Center on the box)
- **session-reset** — a `sessions.reset` gateway *call* (never a gateway *restart*) against the main/CEO agent

The gateway is restarted only as a fix attempt after a failed health check — never as a routine step.

---

## Telegram outbound routing (2026-05-26 lesson)

The bot ALWAYS replies to the originating chat. Neither ownerChat
(workforce-build-state) nor commands.ownerAllowFrom (operator permission
list) rewrites outbound destinations. If a client reports "bot not
responding," run `scripts/telegram-offset-healthcheck.sh` FIRST. The
2026-05-26 incident wasted hours chasing a routing rewrite that did not
exist; the real cause was polling offset corruption (stored lastUpdateId
advanced past pending updates, so the bot polled above the queue while
real messages piled below).
