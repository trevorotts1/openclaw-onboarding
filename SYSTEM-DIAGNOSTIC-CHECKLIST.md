# OpenClaw System Diagnostic Checklist

**Version:** 1.0 (v9.6.2)
**Purpose:** Single source of truth for verifying the AI workforce + Book-to-Persona + Command Center + Gemini Engine stack works as one fluid system.

Run this checklist:
- After every onboarding install
- Before every Sunday weekly update
- Any time something feels broken
- Before any major release

The automated runner is at **`scripts/qc-system-integrity.sh`**. It executes every check below and exits 0 only when all green.

---

## How the pieces fit together

```
┌──────────────────────────────────────────────────────────────────────┐
│ Skill 31: Upgraded Memory System (8-layer memory)                     │
│   - Layer 4: Gemini Embeddings 2 (vector index of:                    │
│       • coaching-personas collection                                  │
│       • clawd workspace files                                         │
│       • master-files collection                                       │
│   - gemini-indexer.py builds embeddings                               │
│   - gemini-search.py runs semantic queries                            │
└────────────────────────────────────┬─────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Skill 22: Book-to-Persona                                             │
│   - Reads books (PDF/EPUB) → produces persona blueprints              │
│   - 14-section dual-purpose document:                                 │
│       • Coaching half (Sections 1-3, 8-11) — for HUMANS               │
│       • Governance half (Section 4, 5-7, 12-14) — for AI AGENTS       │
│   - persona-categories.json: domain + perspective tags                │
│   - Output indexed by Gemini Engine (Skill 31)                        │
└────────────────────────────────────┬─────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Skill 23: AI Workforce Blueprint                                      │
│   - Interviews owner (2-3 questions per dept, 17 default depts)       │
│   - Creates ZHC folder: ~/clawd/zero-human-company/<slug>/            │
│   - Per dept: director + specialist roles, each in own subfolder      │
│   - DMAIC SOPs written by parallel sub-agents (heavy tier, 1800s)     │
│   - persona-matching-protocol: 5-layer alignment for task→persona     │
│   - governing-personas.md per dept (pre-qualified from layers 1+2)    │
│   - SHARED files: AGENTS.md/TOOLS.md/USER.md symlinked, not copied    │
│   - Per-agent config: 200K/400K bootstrap, canonical sub-agent block  │
│   - Writes departments.json + company-config.json (with brand colors) │
└────────────────────────────────────┬─────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Skill 32: BlackCEO Command Center                                     │
│   - Activates persistent department agents (each binds to a topic)    │
│   - Kanban dashboard at localhost:4000 (or Cloudflare tunnel)         │
│   - Reads ZHC departments.json → seeds the workspaces table           │
│   - Reads company-config.json → renders brand colors                  │
│   - Telegram group with one topic per department                      │
│   - 3-check rhythm: 9 AM standup / midday / EOD                       │
│   - Runtime task→persona flow:                                        │
│       1. Task lands in dept Telegram topic                            │
│       2. Director invokes select-persona-for-task.py                  │
│       3. Hybrid search: Gemini semantic + keyword + 5-layer scoring   │
│       4. Selected persona logged to dept/memory/[date].md             │
│       5. Sub-agent spawned with "Act As If" prompt                    │
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
| 1.1 | ZHC folder exists for the client | `ls ~/clawd/zero-human-company/*/` | At least one company slug folder, with `departments/` inside |
| 1.2 | Pre-interview research file present | `cat ~/clawd/zero-human-company/*/pre-interview-research.md` | File exists, even if minimal |
| 1.3 | workforce-interview-answers.md is the SOLE source of truth | Same file, multiple Q+A entries | Last entry has timestamp; no duplicate questions |
| 1.4 | interview-handoff.md status reflects reality | `cat .../interview-handoff.md \| grep status` | `complete` if all done, `in_progress` if mid-flight |
| 1.5 | MEMORY.md `## AI Workforce Build` section present | `grep -A 20 "## AI Workforce Build" ~/clawd/MEMORY.md` | Section exists with all 5+ file paths listed |
| 1.6 | Slim interview enforced (2-3 mandatory + up to 7 conditional) | Read INSTRUCTIONS.md Step 9 | Phrase "2-3 mandatory, AI may extend up to 7" present |
| 1.7 | Pull-forward rule active | Same INSTRUCTIONS.md | "If the answer exists in pre-interview research / MEMORY / USER / AGENTS, confirm rather than re-ask" present |
| 1.8 | Save-on-break message standardized | Same | "Resume my AI workforce setup" phrase present |

## CHECK 2 — AI Workforce Skill Set (Skill 23 build phase)

| # | Check | How to verify | Pass = |
|---|---|---|---|
| 2.1 | Department count matches interview | Compare `len(departments.json) == client's chosen count` | Equal. NOT 17 unless client chose 17. |
| 2.2 | Each dept has director + specialist subfolders | `ls ~/clawd/zero-human-company/*/departments/*/00-*` | Each dept has `00-<director-title>/` |
| 2.3 | AGENTS.md / TOOLS.md / USER.md SYMLINKED, not copied | `ls -la ~/clawd/zero-human-company/*/departments/*/AGENTS.md` | Each line shows `->` (symlink arrow) pointing back to `~/clawd/<file>.md` |
| 2.4 | Every dept director in agents.list[] | `cat ~/.openclaw/openclaw.json \| jq '.agents.list[] \| select(.id \| startswith("dept-"))'` | One entry per chosen dept |
| 2.5 | Each dept director has canonical sub-agent config | Same query, check fields | `bootstrapMaxChars=200000`, `bootstrapTotalMaxChars=400000`, `subagents.maxChildrenPerAgent=20`, `maxConcurrent=100`, `maxSpawnDepth=5`, `thinking=high`, `allowAgents=["*"]` |
| 2.6 | SOPs populated (not stubs) | `grep -l "to be personalized" ~/clawd/zero-human-company/*/departments/*/*/0*.md` | **Empty result** (no SOPs with stub placeholders remaining) |
| 2.7 | "No guessing" rule in every SOP | `grep -L "DO NOT GUESS\|Guessing is forbidden" ~/clawd/zero-human-company/*/departments/*/*/0*.md` | **Empty result** (every SOP contains the rule) |
| 2.8 | DMAIC sections in every SOP | `grep -l "## DEFINE.*## MEASURE.*## ANALYZE.*## IMPROVE.*## CONTROL" ~/clawd/zero-human-company/*/departments/*/*/0*.md` | Every SOP file appears |
| 2.9 | Devil's Advocate per dept | `ls ~/clawd/zero-human-company/*/departments/*/devils-advocate/SOP.md` | One per dept |
| 2.10 | ORG-CHART.md at company root | `cat ~/clawd/zero-human-company/*/ORG-CHART.md` | Lists CEO + each dept director + specialists with type label |

## CHECK 3 — Book-to-Persona (Skill 22)

| # | Check | How to verify | Pass = |
|---|---|---|---|
| 3.1 | persona-blueprint.md present per book | `ls ~/Downloads/openclaw-master-files/coaching-personas/personas/*/persona-blueprint.md` | One per processed book |
| 3.2 | Each blueprint has all 14 sections | `grep -c "^## " <blueprint>` | ≥ 14 |
| 3.3 | Coaching half present (sections 1-3, 8-11) | Same blueprint | Author Intelligence, Core Methodology, Coaching Framework, Voice, Quote Library, Question Library, Tools/Exercises present |
| 3.4 | Governance half present (sections 4-7, 12-14) | Same | Agent Governance Framework, Foundational Principles, Problem-Solution Map, Trigger Detection, Objections, Session/Task Structure, Routing Rules present |
| 3.5 | persona-categories.json maintained | `cat ~/Downloads/openclaw-master-files/coaching-personas/persona-categories.json` | Valid JSON, every blueprint tagged with domain + perspective tags |
| 3.6 | Model selection is dynamic (not hardcoded) | `grep "moonshot/kimi-k2.5\|gpt-5.3-codex\|deepseek-v3.2" 22-*/_meta.json 22-*/PIPELINE.md` | **Empty result** (v9.5.0+ — selector-driven) |
| 3.7 | No Anthropic refs in active code paths | `grep -rn "anthropic/\|claude-opus\|claude-sonnet" 22-*/pipeline/*.py` | **Empty result** |
| 3.8 | Per-book context-aware model resolution | Read `orchestrator.py:resolve_phase_model` | Function exists, takes `input_chars` arg, returns DeepSeek-pro for `>800K` chars |

## CHECK 4 — Gemini Embeddings 2 (Skill 31)

| # | Check | How to verify | Pass = |
|---|---|---|---|
| 4.1 | gemini-indexer.py executable | `ls -la ~/clawd/scripts/gemini-indexer.py` | File exists, executable bit set |
| 4.2 | gemini-search.py executable | `ls -la ~/clawd/scripts/gemini-search.py` | Same |
| 4.3 | coaching-personas collection indexed | `python3 ~/clawd/scripts/gemini-indexer.py --status` | Collection `coaching-personas` shows ≥ 1 file indexed |
| 4.4 | clawd workspace collection indexed | Same `--status` command | Collection `clawd` shows ≥ 10 files (SOUL, MEMORY, AGENTS, etc.) |
| 4.5 | master-files collection indexed | Same | Collection `master-files` shows skill folders indexed |
| 4.6 | **New v9.6.2: ZHC company folder indexed** | Same | Collection `zhc-<company-slug>` shows departments + SOPs indexed |
| 4.7 | Test semantic query returns relevant results | `python3 ~/clawd/scripts/gemini-search.py --collection coaching-personas --query "leadership and influence"` | At least one persona returned with score > 0.5 |
| 4.8 | Re-index runs at correct milestones | Check AGENTS.md "Indexing Milestones" section | Initial, Personas (after Skill 22), AI Workforce (after Skill 23), Ongoing (any new skill) |

## CHECK 5 — Semantic Search

| # | Check | How to verify | Pass = |
|---|---|---|---|
| 5.1 | select-persona-for-task.py callable | `python3 ~/.openclaw/skills/23-ai-workforce-blueprint/scripts/select-persona-for-task.py --help` | Help text returned, exit 0 |
| 5.2 | Test invocation returns a winner | `--dept marketing --task "Write a launch email" --format id` | Returns a persona-id string, exit 0 |
| 5.3 | Top-3 candidates have varied semantic scores | Same with `--format json` | Top-3 list, scores not all identical (signal that semantic search is working) |
| 5.4 | Falls back gracefully if Gemini unavailable | Move gemini-search.py temporarily, re-run | Exits 2 with `"gemini_available": false`, still picks a persona |
| 5.5 | Selection logged to dept's daily memory | `cat ~/clawd/zero-human-company/*/departments/<dept>/memory/$(date +%Y-%m-%d).md` | Contains `## HH:MM:SS — Persona Selection` entry |

## CHECK 6 — Keyword Search

| # | Check | How to verify | Pass = |
|---|---|---|---|
| 6.1 | persona-categories.json has domain + perspective tags | `jq '.personas \| to_entries[] \| select(.value.domain_tags)' persona-categories.json` | Every persona has at least one domain tag |
| 6.2 | Domain tags match documented 12-tag list | Check tags vs SKILL.md | Marketing, Sales, Leadership, Finance, Operations, Communication, Copywriting, Mindset, Productivity/Systems, Coaching, Strategy/Innovation, Personal Development |
| 6.3 | Perspective tags match documented 6-tag list | Same | African American experience, Women's challenges, Men's challenges, Family/relationships, Faith/spirituality, Love/romantic relationships |
| 6.4 | Dept-to-domain mapping present in selector | `grep -A 20 "DEPT_DOMAIN_TAGS" select-persona-for-task.py` | Mapping exists for all 17 default depts |
| 6.5 | keyword_filter() narrows candidates correctly | Add a non-matching candidate, run selector | Candidate filtered out before scoring |

## CHECK 7 — Task Assignments (Kanban / Command Center)

| # | Check | How to verify | Pass = |
|---|---|---|---|
| 7.1 | Mission Control DB seeded with correct dept count | `sqlite3 ~/projects/command-center/mission-control.db "SELECT count(*) FROM workspaces WHERE company_id='<slug>'"` | Equal to client's chosen dept count, NOT 17 |
| 7.2 | Company row has brand colors | `sqlite3 ... "SELECT config FROM companies WHERE slug='<slug>'"` | JSON contains `brand.primary`, `brand.accent`, `brand.text` |
| 7.3 | Telegram topics exist per dept | Open Telegram, count topics in Command Center group | Equal to dept count + 1 (Cross-Department) |
| 7.4 | Each topic binds to the correct agent | `cat ~/.openclaw/openclaw.json \| jq '.channels.telegram.topicBindings'` | One binding per dept topic to `dept-<dept_id>` agent |
| 7.5 | Kanban dashboard reachable | `curl -s -o /dev/null -w "%{http_code}" http://localhost:4000` | 200 |
| 7.6 | Dashboard renders brand colors | Open in browser | Primary/accent match company config (visual check) |

## CHECK 8 — Persona Assignments

| # | Check | How to verify | Pass = |
|---|---|---|---|
| 8.1 | governing-personas.md exists per dept | `ls ~/clawd/zero-human-company/*/departments/*/governing-personas.md` | One per dept |
| 8.2 | persona-matrix.md at company root | `ls ~/clawd/zero-human-company/*/persona-matrix.md` | Exists, lists pre-qualified pool |
| 8.3 | Layer 1+2 pre-qualification applied | Read persona-matrix.md | Personas filtered by company mission + owner values (not all 40 listed) |
| 8.4 | Selector runs Layers 3-5 fresh per task | Two task invocations with different KPI contexts | Different winners (selector isn't caching) |
| 8.5 | Persona reason log written | `cat ~/clawd/workspace/memory/$(date +%Y-%m-%d).md \| grep "Persona Selection"` OR per-dept memory | Entry per task with breakdown |
| 8.6 | "Act As If" protocol in dept AGENTS.md | `grep -A 3 "Act as if\|Act As If" ~/clawd/AGENTS.md` | Phrase present |

## CHECK 9 — Agent Linking

| # | Check | How to verify | Pass = |
|---|---|---|---|
| 9.1 | Every dept director in agents.list[] | `jq '.agents.list[] \| .id' ~/.openclaw/openclaw.json \| grep "^dept-"` | One per dept |
| 9.2 | agents.list[].workspace points to ZHC path | Same | Each `workspace` field = `~/clawd/zero-human-company/<slug>/departments/<dept_id>` |
| 9.3 | allowAgents=["*"] on every agent entry | `jq '.agents.list[] \| .subagents.allowAgents' ~/.openclaw/openclaw.json` | Every line = `["*"]` |
| 9.4 | Telegram binding per dept | Same openclaw.json | `channels.telegram.allowFrom` includes the dept agent IDs |
| 9.5 | Cross-Department topic agent exists | Same | Entry with `id="dept-cross"` or similar |
| 9.6 | Bootstrap config propagated to every agent | `jq '.agents.list[] \| {id, bootstrapMaxChars, bootstrapTotalMaxChars}' ~/.openclaw/openclaw.json` | Every entry: `200000` / `400000` |
| 9.7 | Sub-agent thinking="high" on every agent | `jq '.agents.list[] \| .subagents.thinking' ~/.openclaw/openclaw.json` | Every line = `"high"` |
| 9.8 | Master AGENTS.md/TOOLS.md/USER.md exists at workspace root | `ls -la ~/clawd/{AGENTS,TOOLS,USER}.md` | Three regular files (not symlinks) |
| 9.9 | Dept AGENTS.md/TOOLS.md/USER.md SYMLINKED to master | `ls -la ~/clawd/zero-human-company/*/departments/*/{AGENTS,TOOLS,USER}.md \| grep "^l"` | All entries are symlinks pointing to `../../../../<file>.md` |
| 9.10 | No legacy `~/clawd/departments/` content drift | `diff ~/clawd/departments/ ~/clawd/zero-human-company/<slug>/departments/ 2>/dev/null` | Either legacy folder doesn't exist OR is mirror of canonical |

---

## CROSS-CUTTING — System integrity

| # | Check | Pass = |
|---|---|---|
| X.1 | Anthropic models forbidden everywhere | `grep -rn "anthropic/\|claude-opus\|claude-sonnet\|claude-haiku" /tmp/openclaw-onboarding --include="*.py" --include="*.json"` returns ONLY references inside FORBIDDEN filter / changelog explanation |
| X.2 | Bootstrap limits canonical | `jq '.agents.defaults.bootstrapMaxChars, .agents.defaults.bootstrapTotalMaxChars' ~/.openclaw/openclaw.json` returns `200000`, `400000` |
| X.3 | Sub-agent timeouts ≥ 1800s for heavy | Search all skill scripts for `aiohttp.ClientTimeout\|timeout=` — heavy-reasoning paths show 1800+ |
| X.4 | All skills point to v9.6.2 docs/templates | `grep -rn "v9.5\|v9.4\|v9.3" /tmp/openclaw-onboarding/install.sh /tmp/openclaw-onboarding/update-skills.sh` returns only historical CHANGELOG entries |
| X.5 | Both Mac + VPS repos at same commit | `cd Mac; git log -1 --oneline` AND `cd VPS; git log -1 --oneline` show same version label |
| X.6 | Memory.md links to all 5 build artifacts | `grep -c "pre-interview-research\|workforce-interview-answers\|interview-handoff\|ORG-CHART\|departments.json\|sop-research-manifest" ~/clawd/MEMORY.md` ≥ 5 |
| X.7 | GHL daily quota not exhausted (won't block install if so) | `bash ~/clawd/scripts/qc-ghl-mcp-setup.sh \| grep "X-RateLimit-Daily-Remaining"` returns > 1000 |

---

## What to do when a check fails

Each row above has a remediation recipe in `qc-system-integrity.sh`. The runner prints the row number and the exact command to fix it. Most fixes are one-liners. If a fix requires re-running a skill install, the runner suggests the exact `update-skills.sh --only "23,32"` command.

**Common patterns:**

| Symptom | Likely failed check | Fix |
|---|---|---|
| Dashboard shows 17 departments but I picked 15 | 7.1 | Rerun `python3 32/scripts/seed-workspaces.py` after confirming `departments.json` count |
| Marketing Director keeps using Seth Godin for every task | 8.4 | Check `selector-cache.json` doesn't exist; if it does, delete it. Selector must run fresh per task. |
| Tasks pile up in "In Progress" never reaching Done | 9.x (DA wiring) | Verify Devil's Advocate SOP.md exists for that dept; check Skill 32 DA-gate config (v9.7.0+) |
| Marketing Director updates TOOLS.md but Sales Director doesn't see it | 9.9 (symlinks) | Re-run `build-workforce.py` for that company — the symlinks were broken/missing |
| Persona selection always returns the same winner | 4.7 + 5.3 + 8.4 | Gemini index stale OR no semantic scores OR 5-layer scoring broken. Run `gemini-indexer.py` then re-test selector. |
| SOPs still have `[Step 1 - to be personalized]` | 2.6 | Run `populate-sops-from-manifest.py --manifest <path>` |
| Brand colors are neutral/generic in dashboard | 7.2 + 7.6 | Either `company-config.json` missing brand fields OR frontend not reading `companies.config` |

---

## Schedule

- **Every install:** run automatically as part of Skill 23 + Skill 32 install QC
- **Every Sunday (cron):** run as part of weekly health check before update prompt
- **Ad-hoc:** any time a client reports "it's acting weird"

The runner exits 0 = all green, 1 = one or more checks failed (details in log).
