# OpenClaw Onboarding — Mac mini

> **Version:** see `/version` — this repo at v10.13.20.
> Every release MUST agree across the version-tracked files; run `./scripts/bump-version.sh vX.Y.Z` to update them atomically. Drift is caught in CI (`.github/workflows/version-consistency.yml`).
>
> **NOTE (v10.13.17):** Bump-script coverage extended to track README.md and DIRECT-TO-AGENT-UPDATE-MESSAGE.md — both used to drift independently of the 5 originally-tracked files. If you find a NEW version-bearing file in the future, ADD it to `scripts/bump-version.sh` before fixing the drift.
>
> **After every release:** `git tag vX.Y.Z && git push --tags && gh release create vX.Y.Z --notes-from-tag` so the GitHub Releases page mirrors the CHANGELOG.


<!-- BEGIN v2.1 SECTION -->
## v2.1 — Zero-Human Company Spec (PRD v2.1)

> **What this version delivers:** A solo founder can complete the AI Workforce setup in under 45 minutes and end up with the operational machinery of a Fortune 500 company. 16 mandatory departments. 130-200 specialized AI roles. Persona-governed execution.

### The 16 Mandatory Departments
Auto-built for every zero-human company:

1. **Marketing** — Demand generation, brand positioning
2. **Sales** — Outreach, conversion, deals
3. **Billing & Finance** — Invoices, cash flow, forecasting
4. **Customer Support** — Onboarding, retention, service
5. **Web Development** — Website, funnels, SEO, technical SEO
6. **App Development** — Desktop, mobile, PWA
7. **Graphics** — Visual content across all formats
8. **Video** — Production, editing, Video SEO
9. **Audio** — Podcast, AI voice (11 Labs), sound design
10. **Research** — McKinsey-style industry + competitor intel
11. **Communications** — PR, internal/external messaging
12. **CRM** — Platform admin, **Email Deliverability & Optimization (flagship)**
13. **OpenClaw Maintenance** — System health, backups, security
14. **Legal** — Contracts, compliance, IP
15. **Social Media** — Organic posting across 10 platforms (separate from Paid Ads)
16. **Paid Advertisement** — Paid media across 13 ad platforms

**Plus: Master Orchestrator (CEO agent)** above all departments. Special persona deferral clause — uses personas as input but mission and owner values override on conflict.

### Industry Vertical Packs (Auto-Added)
- **Personal/Professional Development** (~60% of clients): Presentations, Client Coaches, Course Creator, Podcast, Community Management
- **Real Estate**: Listings, MLS Ops, Lead Gen, Showings, Open House, Closing, Local Market Intelligence
- **Service Industry**: Scheduling/Dispatch, Field Operations, Reviews Management, Recurring Service

### The 30-Question Interview
6 phases, ~35 minutes total. Pre-interview asset drop pre-fills 40%+ of answers. Behavioral interview (5 scenario-based questions) replaces value-based platitudes. Department customization bundled across 13 questions (not 1-per-dept).

### Universal How-To Template
Every role's `how-to.md` follows the same 18-section structure: identity, persona governance, daily/weekly/monthly/quarterly ops, KPIs tied to revenue cascade, tools, SOPs, quality gates, handoffs, escalation paths, good/bad examples, common mistakes, research sources, edge cases, update triggers.

QC sub-agent verifies every generated document against a 9-item quality checklist. 2 revision cycles max before flagging for owner review.

### Generation Orchestration
After the interview completes, the AI spawns sub-agents:
- 1 industry research sub-agent (McKinsey + Perplexity + competitor intel)
- Up to 10 department sub-agents in parallel
- Up to 50 role sub-agents in parallel (each generating one how-to.md)
- 1 QC sub-agent

**Full build: 25-45 minutes for 130-200 role documents.**

### Platform Abstraction
`shared-utils/detect_platform.py` resolves paths automatically:
- Mac legacy: `~/clawd/`
- Mac new install: `~/.openclaw/workspace/`
- VPS (Hostinger Docker): `/data/.openclaw/workspace/`

No hardcoded paths. Same code runs on every platform.

### Persona Governance Override
Persona is the strongest control over agent behavior. Every generated SOUL.md and IDENTITY.md contains a deferral clause:

> *When a persona is assigned, that persona governs HOW you perform the work. Your beliefs, voice, decision logic come from the persona — not from this file.*

Master Orchestrator (CEO) gets the special variant: persona is INPUT, but company mission and owner values WIN on conflict.

### Documentation
See PRD v2.1 (`onboarding ant farm PRD v2.1.md` in user's local Downloads) for the complete specification. Executes in order: v1.1 (foundation) → v2.0 (intelligence) → v2.1 (zero-human-company spec).
<!-- END v2.1 SECTION -->



**A complete onboarding package for setting up a fully operational OpenClaw agent on macOS.**

**Current Version: v10.3.0** — See [CHANGELOG.md](CHANGELOG.md) for what's new.

This repo is **Mac-only**. The Hostinger Docker VPS installer lives at https://github.com/trevorotts1/openclaw-onboarding-vps.

This repo contains **36 skill folders** (01 through 36, with 13, 33, and 34 archived) plus an install script and update script.

> **First time installing or updating?** Read **[ONBOARDING-TRIGGERS.md](ONBOARDING-TRIGGERS.md)** — it shows exactly how to start a fresh install or run an update via Terminal or Telegram.

### What's New in v10.3.0 (May 14, 2026) — Auto-install Calibre + remove MOONSHOT_API_KEY hardcoding

**Fix 1:** install.sh now auto-installs Calibre (ebook-convert) for Skill 22 ebook extraction. Mac uses `brew install --cask calibre`; VPS uses Linuxbrew or the official Calibre Linux installer. Silent if already present, non-fatal if it fails.

**Fix 2:** Skill 22 `pipeline/orchestrator.py` no longer crashes on missing `MOONSHOT_API_KEY`. Added real `call_ollama_cloud()` function that hits `https://ollama.com/api/chat` directly. All three phases (Phase 1 extraction, Phase 2 analysis, Phase 3 synthesis) now route through Ollama Cloud when the selector picks `ollama/*` models — previously a TODO that silently fell back to OpenRouter. Same-model OpenRouter fallback fires on Ollama Cloud failure. Deprecated `call_moonshot()` kept for back-compat but no longer in the routing chain. Future-proofed via version-pattern regex.

### What's New in v10.2.0 (May 14, 2026) — No-shortcut rule for sub-agents + explicit DeepSeek/Kimi priority

**Change 1 — Sub-agent no-shortcut rule.** Sub-agents installing skills were skipping CORE_UPDATES.md, INSTRUCTIONS.md, references/*.md and other skill docs, leading to wrong AGENTS.md/MEMORY.md updates and silent install failures. v10.2.0 adds a hard reinforcement block in the UPDATE PENDING flag that requires every sub-agent to read ALL files in the skill folder BEFORE any install command, report a structured read-log with 100% coverage, and the master orchestrator independently verifies the file count.

**Change 2 — Book extraction model priority.** Per owner directive: for Skill 22 (book-to-persona) Phase 1 + 2, favor Ollama DeepSeek V4-pro OR Ollama Kimi 2.6 (or latest version of each). If the client doesn't have Ollama Cloud, fall back to the OpenRouter version of the SAME model. Updated `select_model.py` chain order, Skill 22 SKILL.md Model Routing section, and Skill 22 PIPELINE.md Phase 1 + 2 priority lists.

### What's New in v10.1.0 (May 14, 2026) — Ollama Cloud first, OpenRouter as fallback

Skills (especially the Skill 22 book-to-persona pipeline and Skill 35 social-media-planner) had legacy documentation that defaulted heavy-reasoning calls to OpenRouter even when Ollama Cloud Kimi / DeepSeek-pro was available. Ollama Cloud is subscription-billed (cheap) while OpenRouter is per-token (expensive), so the wrong default was costing real money on every install.

The `shared-utils/select_model.py` selector was already correctly ordered Ollama-first. v10.1.0 fixes the stale skill docs (SKILL.md tables, INSTALL.md verify steps, QC.md checklists, agent prompts) to match. Clients with Ollama Cloud configured will now correctly route through it for heavy reasoning; OpenRouter only fires as fallback when Ollama Cloud is unavailable.

### What's New in v10.0.3 (May 14, 2026) — CLI scope auto-repair

Real root cause finally identified (with Floyd's help): fresh OpenClaw pairings can leave the CLI device with `[operator.read, operator.pairing]` only — missing `operator.write` and `operator.admin`. Without those, every `openclaw message send` and `openclaw cron create` call from the CLI is rejected by the gateway with `scope upgrade pending approval`. The gateway reports `Capability: read-only` in `openclaw gateway status --verbose`.

v10.0.3 adds `auto_repair_cli_scopes()` that detects this state at install start and repairs it automatically via two strategies: (Plan A) `openclaw devices rotate` + `approve` using the master gateway token from openclaw.json, or (Plan B) direct edit of `~/.openclaw/devices/paired.json` per Floyd's proven repair sequence. Both back up state, restart the gateway, and verify capability afterwards.

The UPDATE PENDING flag in AGENTS.md now includes a self-healing guide so the agent knows how to recover if anything goes wrong.

### What's New in v10.0.2 (May 14, 2026) — Durable logs + terminal error summary

Install logs now live at `~/Downloads/openclaw-backups/install-logs/` instead of `/tmp/` — durable, survives reboot, sits alongside config backups for easy reference when reporting issues.

At the very end of every install, a summary block prints to the terminal. If everything went clean, you see "✅ INSTALL COMPLETED CLEANLY" + the log path. If anything went wrong, you see the count of errors/warnings, the first 10 issues with line numbers, the log path, a `pbcopy` command to grab the full log, and the GitHub issues URL — all in one terminal block, no scrolling.

### What's New in v10.0.1 (May 14, 2026) — Stop breaking Telegram with rotation

v9.7.7 added a `rotate_all_devices_to_full_scopes()` helper that, per the OpenClaw docs, was actually creating new pending scope upgrade requests. Those pending requests blocked the gateway from sending Telegram messages during install — exactly the failure mode the rotation was meant to prevent. Self-inflicted deadlock.

v10.0.1 removes the rotation entirely, plus the two scope-approval helpers that were trying to clean up after it. Existing clients all have `operator.write` on their paired device (that's what their daily Telegram requires), so `openclaw message send` just works directly. No rotation, no approval, no retries, no user action.

See CHANGELOG.md for the full root-cause analysis and removed-code list.

### What's New in v10.0.0 (May 14, 2026) — The split: Mac-only repo, bulletproof discovery

This is a deliberate major version break that splits the previous unified codebase into two dedicated repos. The VPS installer is its own thing now (https://github.com/trevorotts1/openclaw-onboarding-vps). This repo is Mac-only — no `/data/...` paths, no Hostinger Docker branches, no platform detect.

**Bulletproof Telegram chat ID resolver — 23 sources.** Mac canonical pairing always succeeds before onboarding runs. If we don't find a chat ID, it's because we didn't look hard enough. The resolver now walks all 23 plausible Mac locations (CLI queries, credentials/ files, openclaw.json branches, per-agent bindings, alternate Mac config paths, runtime CLI introspection, .env files, env.vars block, shell env vars, recursive filesystem walks, audit logs). Verified live on the Mac dev box — resolved chat ID via Strategy 1.

**Bulletproof credential discovery — 10 sources.** Shell env → ~/.openclaw/secrets/.env → ~/clawd/secrets/.env → env.vars block in openclaw.json → models.providers.*.apiKey → plugins.entries.*.config → auth-profiles.json → ~/.openclaw/secrets.json → deep scan. Alias map covers naming variants per credential.

**Bulletproof workspace resolver.** Per-agent override → defaults.workspace → ~/clawd → ~/.openclaw/workspace. Handles both your existing setup (~/clawd) and OpenClaw's fresh-install default.

**All 36 skills cleaned to Mac-only paths.** 263 path replacements across 81 files. No more cross-platform branches in skill code.

See CHANGELOG.md for the full list of changes.

End-of-discovery report now lists any missing canonical credentials so the operator can fix gaps before skill installs hit them.

### What's New in v9.7.10 (May 14, 2026) — Strategy 5: scan credentials/ for chat IDs

Hostinger Docker installs store the Telegram chat allowlist in a SEPARATE file (`credentials/telegram-<account>-allowFrom.json`) — NOT inside openclaw.json like Mac/desktop. v9.7.9's 4-strategy universal lookup missed this. v9.7.10 adds Strategy 5: glob the `credentials/` directory for `telegram-*-allowFrom.json` files, read the `allowFrom` array, also derive the account name from the filename. Zero regression on Mac (Strategy 5 finds no files there and the lookup falls through to the older strategies).

See CHANGELOG.md for live verification on Evelyn's Hostinger container.

### What's New in v9.7.9 (May 14, 2026) — Platform-aware paths for Hostinger Docker VPS

VPS installs now correctly use `/data/...` instead of `/root/Downloads/...`. The Hostinger Docker container persists `/data` across rebuilds; the previous version's hardcoded `$HOME/Downloads/...` paths landed install artifacts inside the container, where they'd be lost on rebuild.

Top-level platform detector added (`[ -d "/data/.openclaw" ]` → VPS); 34 hardcoded `$HOME` paths replaced; 3 Python heredocs updated to read `$OPENCLAW_JSON` from env instead of hardcoded `expanduser`. Telegram-ID detection on Docker VPS already worked via the 4-strategy universal resolver from v9.6.9 — `openclaw config get` runs inside the container and finds the chat ID regardless of where openclaw.json lives.

See CHANGELOG.md for the complete diff inventory.

### What's New in v9.7.8 (May 13, 2026) — Multi-account Telegram cron support

**v9.6.9 successfully resolved the Telegram chat ID via universal scan — confirmed on a client with the newer multi-account schema** (`channels.telegram.accounts.default` + `channels.telegram.accounts.wifey`). Lookup returned `8666242544`. But the next step (`openclaw cron create`) then failed for that client because the cron delivery couldn't route to a specific Telegram account.

**Fix:** install.sh now auto-detects multi-account setups and passes `--account <id>` to `openclaw cron create`. Logic:

- If `channels.telegram.accounts` exists with named accounts → pass `--account default` (or first key if `default` missing)
- Otherwise → omit `--account` (single-account / legacy schema)

Also added:
- Explicit `--agent main` flag (some newer OpenClaw builds require it for cron jobs)
- Removed `--exact` flag (was redundant with `--session isolated`)
- Retry-without-account fallback if the first attempt fails
- Improved error messaging that lists likely causes: gateway not running, agent 'main' not defined, channel 'telegram' disabled

Verified on this machine: `openclaw cron create` with all the new args returns exit 0 and creates a valid cron job.

### What's New in v9.6.9 (May 13, 2026) — UNIVERSAL Telegram lookup (no client action ever)

Replaced rigid 5-path lookup with 4-strategy universal resolver:

- **Strategy 1:** `openclaw config get` direct query (CLI knows where its own config lives)
- **Strategy 2:** Scan every plausible `openclaw.json` location (Mac, Linux, VPS, XDG paths, globbed)
- **Strategy 3:** Recursive JSON tree walk — finds any 6-20 digit numeric value under any key containing `telegram`, `chat`, `allowfrom`, `allowedchat`, `chatid`, or `targetchat`
- **Strategy 4:** `$TELEGRAM_CHAT_ID` env var

Works regardless of OpenClaw schema version. Tested against multi-account schema (`channels.telegram.accounts.default`) and legacy single-account (`channels.telegram.allowFrom`).

### What's New in v9.6.5 (May 13, 2026) — Closing the Last 4 Gaps

- **Brand colors render in the Kanban frontend** via `generate-brand-css.py` (auto-invoked by `seed-workspaces.py`).
- **Devil's Advocate gate on Kanban "Done" column** — Kanban Done-Gate Protocol added to AGENTS.md.
- **Company KPI roll-up widget** via `generate-kpi-rollup.py`.
- **Live selector quality test harness** at `test-persona-selector.sh`.

### What's New in v9.6.4 (May 13, 2026) — Add Personas from Books, YouTube, or Video

- **New `add-persona-from-source.sh`** — book PDFs, YouTube URLs, local video, or transcript text → persona pipeline. Auto-re-indexes Gemini Engine.

### What's New in v9.6.3 (May 13, 2026) — Department Directors Now Call Unified Persona Selector

- **Persona Operating Protocol rewritten** in Skill 23 INSTALL.md. Every department's AGENTS.md now tells the director to call `select-persona-for-task.py --dept X --task "..." --format json` as Step 1. Unified script does semantic + keyword + 5-layer in one call.
- **Reason logging auto-logged** by the selector to the dept's daily memory file.
- **Skill 32 INSTALL.md §7.5** updated: FAIL if agent only ran `gemini-search.py` standalone.

### What's New in v9.6.2 (May 13, 2026) — Bulletproof Pass: SOP Auto-Spawn + Runtime Persona Selector + Diagnostic Runner

- **SOP auto-population.** New `23-ai-workforce-blueprint/scripts/populate-sops-from-manifest.py` reads `sop-research-manifest.json` and spawns up to 10 parallel sub-agents (heavy tier, 1800s each), one per dept, to write real DMAIC SOPs replacing placeholders. Auto-invoked from `build-workforce.py:build_from_config`.
- **Runtime persona selector.** New `select-persona-for-task.py` — hybrid search (Gemini semantic + keyword filter + 5-layer alignment). Logs per-task selection to the dept's daily memory file. Falls back gracefully if Gemini Engine unavailable.
- **Skill 22 Phase 2/3 routing fixed.** No more hardwired models; per-book size-aware resolution.
- **`SYSTEM-DIAGNOSTIC-CHECKLIST.md`** at repo root + **`scripts/qc-system-integrity.sh`** executable runner. 9-area checklist + cross-cutting integrity. Color-coded, exits 0 only when all green.

### What's New in v9.6.0 (May 13, 2026) — Zero Human Company folder + Slim Interview + Lean Six Sigma SOPs

- **New Zero Human Company (ZHC) folder structure.** Departments now live under `~/clawd/zero-human-company/<company-slug>/departments/` so an owner with multiple companies can host each one's workforce in its own folder.
- **Pre-interview asset gathering (Step 6a).** Before any questions, the agent offers to ingest brand docs, LinkedIn, YouTube, website, deck.
- **Per-department questions slimmed** from 3-7 → 2-3 mandatory + up to 7 conditional on criticality.
- **Pull-forward rule (binding).** Before asking any question, check pre-interview research → MEMORY.md → USER.md → AGENTS.md.
- **Lean Six Sigma SOP generation phase.** `sop-research-manifest.json` written for parallel sub-agent fan-out (up to 10, heavy tier, 1800s each).
- **MEMORY.md `## AI Workforce Build` section** lists all per-company file paths.

### What's New in v9.5.2 (May 13, 2026) — Sub-Agent Timeout Floors (30-60 min for Heavy Reasoning)

- **New INSTALL-CONTRACT.md Rule 11a** — binding timeout floors by work class:
  - Heavy reasoning sub-agents (Skill 22 phases, Skill 23 workforce synthesis, persona generation, complex refactor): **min 1800s (30 min), preferred 3600s (60 min)**
  - Mid-tier (creative copy, routine analysis): min 600s, preferred 1200s
  - Fast/bulk (single API call, lint, format conversion): min 300s, preferred 600s
- **install.sh UPDATE PENDING flag — phase timeouts raised:**
  - Phase A (parallel install per wave): 600s → **1800s (30 min)**
  - Phase B (foundation): 900s → **2700s (45 min)**
  - Phase C (interactive Book/Workforce): 1200s → **3600s (60 min)**
  - Phase D (validation + QC): 1800s → **3600s (60 min)**
  - Phase E: still no timeout
- **Skill 22 orchestrator.py — HTTP timeouts raised:**
  - Moonshot (Phase 1): 600s → 1800s
  - OpenRouter (Phase 1/2 fallback): 600s → 1800s
  - Codex / OAuth GPT (Phase 3): 900s → 3600s
- **Skill 22 PIPELINE.md, INSTALL.md, QC.md** — updated "Timeout after 15 minutes" references to reflect the new floors (30 min Phases 1/2, 60 min Phase 3).
- ONBOARDING_VERSION bumped to v9.5.2.

### What's New in v9.5.1 (May 13, 2026) — Context-Aware Model Selection + GLM/Mimo Added

- `select_model.py` now accepts `--context-need {normal,large,huge}` or `--input-chars N`. Heavy chain reorders: normal favors Kimi (smartest, 262K ctx); large flips to DeepSeek V4-pro (1M ctx); huge is DeepSeek-pro only.
- OpenRouter Mimo Pro + OpenRouter GLM added to the heavy chain at the `normal` slot.
- Skill 22 orchestrator computes book char count per book and passes it to the selector. Small books → Kimi (smarter), large books → DeepSeek-pro (1M ctx).

### What's New in v9.5.0 (May 13, 2026) — Smart Model Selector + Anthropic Stripped from Skills 15, 22, 23

- **New `shared-utils/select_model.py`** — single source of truth for model selection across all skills. Three purpose-tier chains, auto-picks highest version in each:
  - **`--purpose-tier heavy`** (reasoning, planning, synthesis): Ollama Cloud Kimi → OpenRouter Kimi → Ollama DeepSeek V*-pro → OpenRouter DeepSeek V*-pro → OAuth GPT (latest)
  - **`--purpose-tier mid`** (creative, routine): Ollama Cloud Minimax → OpenRouter Mimo Pro (thinking=high)
  - **`--purpose-tier fast`** (bulk, cheap): Ollama Cloud DeepSeek V*-flash → OpenRouter DeepSeek V*-flash → OpenRouter Gemini Flash Lite
- **ABSOLUTE RULE — Anthropic models FORBIDDEN.** Filter applied at every tier of every chain. `anthropic/claude-*` is rejected before selection.
- **Auto-adapts to new versions.** When Kimi 2.7 / 3.0 / GPT-5.10 ships and the client adds it, the selector picks the higher number automatically. Zero skill edits needed.
- **Tier 5 fallback — owner input prompt.** If the client's `openclaw.json` has nothing matching the chain, the selector returns a plain-English prompt the install agent shows the owner. Install does NOT block; only the model binding waits on the reply.
- **Patched skills:**
  - **Skill 22 (Book-to-Persona)** — `_meta.json` rewritten to declare selection INTENT, not hardcoded IDs. `pipeline/orchestrator.py` now calls the selector at runtime. PIPELINE.md, CORE_UPDATES.md, QC.md, CHECKLIST.md all updated. Phase 1, 2, 3 all use `--purpose-tier heavy`.
  - **Skill 15 (BlackCEO Team Management)** — `full.md` and `EXAMPLES.md` rewritten. Removed `anthropic/claude-opus-4-6` "complex reasoning" line, `openai-codex/gpt-5.3-codex` primary, MiniMax M2.5 fallback, the Opus/Sonnet decision tree. All replaced with selector references.
  - **Skill 23 (AI Workforce Blueprint)** — `SKILL.md` Model Requirements section, `INSTALL.md` 5-PRE model check, and `QC-ROLES-MASTER.md` 17-row department-to-model table all replaced with selector tier references.
- **Skill 22 version** bumped 1.0.0 → 2.0.0 (`_meta.json`) to reflect breaking change in model resolution.
- ONBOARDING_VERSION bumped to v9.5.2.

### What's New in v9.4.0 (May 13, 2026) — Canonical Bootstrap + Sub-Agent Config in Step 0

- **Step 0 rewritten** to apply the canonical sub-agent + bootstrap config block before any other install work runs. Replaces the broken legacy `configure_concurrency()` function that used wrong field names (`maxQueue`/`maxDepth`) and lower values.
- **Hard-overwrite of numeric limits** (protocol gates):
  - `agents.defaults.bootstrapMaxChars = 200000`, `bootstrapTotalMaxChars = 400000`
  - `agents.defaults.subagents.maxChildrenPerAgent = 20`, `maxConcurrent = 100` (min-clamp 50), `maxSpawnDepth = 5`, `thinking = "high"`
- **`allowAgents = ["*"]` wildcard** written to every `agents.list[N].subagents` entry (75 entries on live config).
- **Sub-agent model fallback chain preserved** if a client has customized it; only seeded if missing.
- **5 dependency-aware install waves** documented with correct cap: Wave 1 = 01+02 sequential. Wave 2 = 11 parallel. Wave 3 = 14 parallel. Wave 4 = 31→36 sequential. Wave 5 = 22→23→32→35 sequential main-orchestrator-only.

### What's New in v9.3.9 (May 13, 2026) — Trigger Doc Renamed "Fresh Install" → "Full Onboarding"

- **`ONBOARDING-TRIGGERS.md`** — Blocks 1–4 renamed from "Fresh Install" to "Full Onboarding" to accurately describe what they do. In Trevor's workflow, every client arrives with a baseline OpenClaw + Telegram agent already configured; Blocks 1–4 lift that baseline to the full 36-skill package.
- **Blocks 2 (Mac, Telegram) and 4 (VPS, Telegram) marked as ⭐ standard path** — these are the default onboarding routes; Terminal blocks (1, 3) are for self-service or bootstrap scenarios.
- **Alarmist "Before you start" notes removed** from Blocks 2 and 4.

### What's New in v9.3.8 (May 13, 2026) — Core.md Terminology Seeded into MEMORY.md

- **New install + update step (10b)** — `install.sh` and `update-skills.sh` now seed every workspace `MEMORY.md` with a `## Terminology — Core.md Files` section. The owner's term "Core.md files" refers to the 6 OpenClaw bootstrap files loaded each session (IDENTITY, SOUL, AGENTS, USER, TOOLS, MEMORY) — not a literal `core.md` file. Idempotent: re-runs detect the existing section and skip.
- **Corrected definitions per the owner's authoritative usage:**
  - **IDENTITY.md** holds the role the agent is playing, including the **experiences and the skills they need to embody** that role — not just surface metadata.
  - **SOUL.md** holds the **personality**, **true mission**, **beliefs**, **rules**, **goals**, **belief systems**, and **principles** — who the agent IS, not who they are playing. First file injected each session.

### What's New in v9.3.7 (May 13, 2026) — Redact production GHL Location ID

- Redacted real BlackCEO Location ID from 7 documentation references across both repos (replaced with `[REDACTED]` in incident citations, fake `AbCdEfGhIjKlMnOpQrStUv` in format examples). Pure documentation change — runtime Location ID still read from `~/.openclaw/secrets/.env` as `GOHIGHLEVEL_LOCATION_ID`.

### What's New in v9.3.6 (May 13, 2026) — Sunday Cron Quota Gate + Onboarding Triggers Skill 36 Surfacing

- `cron-prompt.txt` RULE 18: Sunday cron now probes GHL daily quota via Tier 3 direct REST before any GHL-touching task; skips the cycle if `< 5000` remain, surfaces reset clock time to client in plain English. Binding even on "install all."
- `ONBOARDING-TRIGGERS.md`: new "What actually gets installed" inventory naming Skill 36 (5-tier chain, port 8765, launchd/systemd, disclosure protocol, standalone `qc-ghl-mcp-setup.sh` validator). Pre-install rate-limit warning callout citing 2026-05-13 incident.
- Filename drift fix — 18 references corrected from `qc-ghl-setup.sh` → `qc-ghl-mcp-setup.sh`. Eliminated embedded duplicate copies of the QC script in `QC.md` and `ghl-mcp-setup-full.md`; standalone file is now the single source of truth.

### What's New in v9.3.5 (May 13, 2026) — GHL Rate-Limit Protocol (2026-05-13 incident response)

- **Documented incident:** location [REDACTED] burned all 200,000 daily GHL API calls. All three tiers (Official MCP, Community MCP, Raw API) returned 429s simultaneously because they share the same per-location backend bucket. Switching tiers does NOT bypass.
- **New INSTALL-CONTRACT.md Rule 8a** — full rate-limit awareness protocol. Pre-flight  probe before bulk ops. On 429: parse , surface wall-clock reset time to owner, NEVER retry blindly, NEVER fall through tiers, log to MEMORY.md.
- **Skill 36 SKILL.md** — added rate-limit as Critical Thing #7.
- **Skill 36 INSTRUCTIONS.md** — full Rate-Limit Protocol section with pre-flight curl example, batching rules, common quota-burners list.
- **Skill 36 qc-ghl-mcp-setup.sh** — new Section B2 actually probes the rate-limit headers (via Tier 3 direct API where the headers live), reports remaining quota + reset time in plain English, fails if under 100 remaining.
- **GHL response headers documented:**  (burst budget),  (daily budget left),  (200000),  (ms until reset),  (100),  (10000).
- ONBOARDING_VERSION bumped to v9.3.5.

### What's New in v9.3.4 (May 13, 2026) - Skill 36 standalone qc-ghl-mcp-setup.sh
- Extracted Skill 36's QC script from the QC.md heredoc into a standalone file at the folder root, matching the convention of the other 32 skills. All 33 active skills now have a standalone qc-*.sh file at their folder root.
- Skill 36 file count: was 10 files (with QC script embedded in QC.md), now 11 files (QC script as standalone qc-ghl-mcp-setup.sh).
- The QC.md heredoc is retained as documentation reference but the canonical executable lives at the standalone file path.
- ONBOARDING_VERSION bumped to v9.3.4.

### What's New in v9.3.3 (May 13, 2026) — Mac/VPS Sync Audit + Skill 35 v2.0.0 mirrored to VPS
- **Audited cross-contamination between Mac and VPS repos.** Most folder diffs are legitimate platform-specific paths (Mac uses ~/clawd, VPS uses /data/clawd) — those are correct.
- **Real bugs found and fixed:**
  - VPS install.sh header comment referenced Mac repo URL. Fixed to openclaw-onboarding-vps/main.
  - Skill 35 v2.0.0 (canonical GOHIGHLEVEL_API_KEY env var, MCP-first routing, qc-skill35.sh) had only landed on Mac. Mirrored to VPS. Both repos now ship Skill 35 v2.0.0 identically.
- **Confirmed correct (not bugs):**
  - Mac/VPS install.sh and update-skills.sh contain reciprocal defensive branches (`[ -d "/data/.openclaw" ] && REPO_URL=...-vps/main`) that auto-switch repo URL based on detected platform. This is by design — protects against the wrong script being run on the wrong machine.
  - 21 skill folders have legitimate path differences between Mac and VPS (`~/clawd/...` vs `/data/clawd/...`). This is correct; not cross-contamination.
- ONBOARDING_VERSION bumped to v9.3.3.

### What's New in v9.3.2 (May 13, 2026) — Bespoke Per-Skill QC Scripts
- **Replaced all 31 generic qc-*.sh scripts with bespoke, skill-specific validation scripts.** Each script now tests assertions specific to that skill's actual goal — credentials, software dependencies, live API reachability, prerequisite skills installed, agent core file wiring, security checks. No more copy-paste boilerplate.
- Examples of the bespoke checks:
  - Skill 05 (GHL Setup): hits live `services.leadconnectorhq.com/locations/<id>` endpoint to verify PIT works
  - Skill 08 (Vercel): validates VERCEL_TOKEN against `api.vercel.com/v2/user`
  - Skill 12 (OpenRouter): validates token against `openrouter.ai/api/v1/auth/key`
  - Skill 21 (Tavily): hits `api.tavily.com/search` with a test query
  - Skill 30 (Fish Audio): hits `api.fish.audio/wallet/self/api-credit`
  - Skill 22 (Persona): verifies Skill 31 (Memory) installed FIRST + coaching-personas folder + persona-categories.json
  - Skill 23 (Workforce): verifies Skill 22 installed + departments/ OR ORG-CHART.md (STATE C interview-complete)
  - Skill 31 (Memory): all 8 memory layers checked (core .md → flush → session → Gemini → memory-core → Cognee → Obsidian → Active Memory)
  - Skill 32 (Command Center): port 3000 (Mac) or 4000 (VPS) reachable, PM2 installed, Cloudflare tunnel token
  - Skill 25/26/27/28 (video skills): FFmpeg-specific codec + filter checks (drawtext, libx264, AAC, concat demuxer)
- Each script returns proper exit codes (0 = pass, 1 = fail) so the cron / install orchestrator can gate on it.
- ONBOARDING_VERSION bumped to v9.3.2.

### What's New in v9.3.1 (May 13, 2026) — Universal QC + Dependency Waves + Step 0 Bootstrap
- All 31 remaining active skills got the v9.3.0 install-time QC rubric appended to their `QC.md` (8.5+ gate, loop-until-passing). Plus each got a bundled `qc-*.sh` baseline validation script. Total: 33 active skills, 33 rubrics, 33 validation scripts.
- Install waves rewritten by actual dependency graph (Wave 1 = TYP + BYUP; Wave 2 + 3 = parallel up to 10 sub-agents; Wave 4 = Memory → MCP; Wave 5 = main-orchestrator-only Persona → Workforce → CC → Social).
- New Step 0 "Bootstrap" in install.sh — recommends `/new`, writes state-carryover JSON, sets `agents.defaults.subagents` to 20/100/5/high, prints cost-aware model priority.
- cron-prompt.txt: added Rule 15 (sub-agent failure retry), Rule 16 (gateway-restart guard — master only, only when subagents list empty), Rule 17 (INSTALL-CONTRACT acknowledgment per skill).
- ONBOARDING_VERSION bumped to v9.3.1.

### What's New in v9.3.0 (May 13, 2026) — Install Discipline Contract + Skill 35 Overhaul
- **New `INSTALL-CONTRACT.md` at repo root** — 15 binding rules every agent MUST follow when installing or updating any skill. Covers: read all .md files first, follow INSTALL.md order verbatim, QC 8.5+ or loop, no shortcuts, sub-agent gateway-restart guard, credential search order, GHL alias awareness, PIT-not-API-key rule, fuzzy master-files detection, model selection priority (cost-aware), sub-agent settings, /new recommendation, owner-facing communication style. Agents acknowledge the contract BEFORE EACH SKILL.
- **New `lib-shared.sh`** — shared library sourced by install.sh, update-skills.sh, check-updates.sh, and skill scripts. Provides: platform detection, canonical path resolution, fuzzy master-files locator (handles all variants: openclaw-master-files, OpenClaw Master Files, open claw master files, OpenClawMasterFiles, openclaw documents, etc.), GHL alias detection, canonical GHL credential read functions.
- **Skill 35 (Social Media Planner) bumped to v2.0.0 with major fixes:**
  - Replaced `GHL_PRIVATE_TOKEN` with canonical `GOHIGHLEVEL_API_KEY` everywhere (eliminates the "auto-fix during install" bug)
  - Migrated credential paths from deprecated `~/clawd/secrets/.env` to canonical `~/.openclaw/secrets/.env` (Mac) / `/data/.openclaw/secrets/.env` (VPS)
  - Updated required PIT scopes to match Skill 36's full set + Skill 35-specific scopes (medias.write, social-media-posting.readonly + write)
  - Injected MCP-first routing logic INTO INSTALL.md (Step 4 — detects Skill 36 and configures routing mode), not just into CORE_UPDATES.md
  - Resolved the 9-month-old `PPSA: PENDING` placeholder (removed)
  - Added 0-10 install-time QC rubric to QC.md with 8.5+ pass gate and loop-until-passing rule (max 5 loops)
  - New bundled `qc-skill35.sh` validation script (mirrors Skill 36's qc-ghl-mcp-setup.sh pattern)
- **install.sh + UPDATE PENDING flag now teach the agent:** all GHL aliases (GHL, GoHighLevel, Convert and Flow, LeadConnector, etc.) refer to the same platform. **GHL DOES NOT USE API KEYS — it uses Private Integration Tokens (PITs).** The env var `GOHIGHLEVEL_API_KEY` is a legacy name; its value is a PIT.
- **install.sh credential discovery list updated** to use canonical `GOHIGHLEVEL_API_KEY` / `GOHIGHLEVEL_LOCATION_ID` names. Deprecated names (`GHL_PRIVATE_TOKEN`, `GHL_API_KEY`, `GHL_LOCATION_ID`) are still auto-detected for migration but no longer the source of truth.
- ONBOARDING_VERSION bumped to v9.3.0.

### What's New in v9.2.0 (May 13, 2026) — Weekly Auto-Check System
- **New `check-updates.sh`** at repo root — READ-ONLY script that fetches the latest version + changelog excerpt from GitHub and compares to the local install. Per-skill aware (lists every skill folder's version diff). Emits structured JSON. Never installs anything.
- **`update-skills.sh` now accepts `--only "05,06,36"` flag** for partial installs. Lets clients install only specific skill folders instead of all-or-nothing. Existing call with no flag still installs everything.
- **New cron-installer block in `install.sh` and `update-skills.sh`** — idempotently creates the Sunday 2am ET weekly update-check cron via `openclaw cron create`. Fresh installs get the cron automatically. Existing clients get it the first time they run the updater.
- **New `cron-prompt.txt`** — the orchestration prompt the Sunday cron fires. Checks all relevant repos (onboarding + command-center), classifies risk per change (Q1 Option C: changelog `### Risk:` tag if present, agent inference if not), composes a plain-English Telegram summary, asks client permission BEFORE applying anything, supports per-skill selection ("install skills 5, 6, 36"), supports high-risk escalation to Trevor.
- **Catchup logic in `update-skills.sh`** — if the weekly check hasn't fired in >7 days (machine was asleep), the manual updater run surfaces a note so the client knows.
- **🐛 BUG FIX:** The old `weekly-onboarding-update` cron silently auto-installed updates every Sunday WITHOUT permission. Now it asks first. (Was 'Execute `update-skills.sh`' then 'ask if you want to proceed' — proceed with what, it already happened.)
- Script version bumped to v9.2.0 in install.sh and update-skills.sh.

### What's New in v9.1.1 (May 13, 2026) — Block-Based Trigger Document
- **ONBOARDING-TRIGGERS.md restructured into 8 standalone blocks**: previously 5 sections (with the update path bundled into one "either-platform" section); now 8 separate blocks — 4 fresh-install (Mac Terminal, Mac Telegram, VPS Terminal, VPS Telegram) plus 4 update (same 4 paths). Each block is self-contained; staff and clients can grab one without reading the others.
- **Telegram contracts expanded to 18–22 numbered rules each**: explicit phase timing, sub-agent concurrency limits, QC thresholds, forbidden shortcuts, watchdog rules, communication style calibration. Each rule is hard-coded so frontier models can't soften them.
- **Deep-link anchors** on each block for direct linking (e.g. `#block-1-mac-fresh-install-via-terminal`) so staff can send a client to the exact section they need.
- **Quick block selector table** at top of doc for fast self-routing.
- Script version bumped to v9.1.1 (content-only patch release; install.sh and update-skills.sh otherwise unchanged from v9.1.0).

### What's New in v9.1.0 (May 13, 2026) — Telegram Handoff Fix + Onboarding Triggers
- **Fixed silent Telegram failure on install completion**: previous versions wrapped `openclaw message send` with `2>/dev/null || true`, swallowing all errors. v9.1.0 logs failures and surfaces a status line so you can see whether the note actually went through.
- **Fixed race condition during gateway restart**: completion message used to be backgrounded with a 10-second sleep, then sent AFTER the gateway restart had begun — by which time the gateway was down and the send silently failed. Now the message is sent BEFORE the restart, so the gateway is still up to deliver it.
- **Paste-ready Telegram body**: the completion notification now contains an exact instruction block the client can copy and paste to their agent. No more vague "check AGENTS.md" wording.
- **Backup terminal block**: install.sh now always prints a fully-formatted backup instruction box at the end of the install, regardless of whether the Telegram note made it through. Nobody gets stranded.
- **update-skills.sh now writes its own UPDATE PENDING flag**: previously only fresh installs wrote the flag, so existing-client updates left the agent with no idea anything happened. Now the updater writes a flag, lists which skills were newly installed, and tells the agent the activation steps.
- **update-skills.sh now sends its own Telegram + backup block**: mirrors the install.sh fix.
- **New ONBOARDING-TRIGGERS.md at repo root**: client-facing document with 5 trigger sections (Mac terminal, Mac Telegram, VPS terminal, VPS Telegram, existing-client update). No version numbers pinned — always pulls latest. Hand-holding tone for over-60 audience.
- **ONBOARDING_VERSION bumped to v9.1.0** in install.sh and update-skills.sh.

### What's New in v9.0.0 (May 13, 2026) — GHL MCP Multi-Tier Access
- **New skill 36 (`36-ghl-mcp-setup`)**: Installs a 5-tier GHL access chain — Official MCP (36 tools), Community MCP (588 tools, BusyBee3333 2026 fork), direct REST API (skill 29), Playwright browser, Codex Computer Use. The agent tries each tier in order before falling through.
- **`$GHL_COMMUNITY_MCP_URL` env var**: Removes the agent's ability to hardcode wrong port numbers — documented past failures (port 8000 / 8765 confusion) eliminated by design.
- **Cardinal Tier Escalation Protocol added to SOUL.md template**: Tier order is binding; "session memory is not authoritative — the canonical state block is"; mandatory `[GHL tier used: N — tool_name]` disclosure header on every GHL response.
- **launchd plist (macOS) / systemd unit (Linux/VPS) lifecycle**: No Docker dependency. Server auto-starts at login, restarts on crash.
- **20-assertion QC script (`qc-ghl-mcp-setup.sh`)**: Exit 0 gate before declaring setup complete. Covers credentials, both MCPs, core file wiring, security.
- **Credential canonical path migrated in skill 05**: From `~/clawd/secrets/.env` to `~/.openclaw/secrets/.env` (Mac) / `/data/.openclaw/secrets/.env` (VPS) to align with AGENTS.md operating rules.
- **Skill 35 routes GHL operations through MCPs first**: Social posting, blog publish, media upload, campaign scheduling all check `social-media-posting_create-post` (Tier 1) and `create_social_post` (Tier 2) before falling to raw API.
- **Skill 29 SKILL.md updated**: Now explicitly identifies itself as Tier 3 of the 5-tier chain, points readers to skill 36 for the MCP layer.
- **README skill inventory fully resynced**: Previous inventory had stale entries (`32-blackceo-voice-call-plugin`, missing `34-intelligent-staffing-ARCHIVED`). Real on-disk folders now reflected.

### What's New in v8.0.0 (April 13, 2026) — BlackCEO System Overhaul v3.3
- **Persona runtime loader**: Replaces hardcoded PERSONA_DETAILS with dynamic runtime loading from company-config.json
- **Grade formula updated**: New 40/30/15/15 weighting (Revenue 40%, Mission 30%, Efficiency 15%, Team 15%)
- **company-config.json wired to CEO Board**: CEO Performance Board now reads directly from company configuration
- **Department Browser + Focus view**: New Kanban-style department browser with focused task views at `/ceo-board/[dept]/focus`
- **Task API department filtering**: All task endpoints support department-based filtering
- **SOP creation + Devil's Advocate**: Each department now has SOP templates with built-in Devil's Advocate review
- **303 hardcoded ~/clawd/ paths cleaned**: All paths now use configurable workspace variables
- **All ports standardized to 4000**: Consistent port configuration across all services
- **department-naming-map.json created**: Standardized department naming conventions
- **persona-selection-log template created**: Structured logging for persona selection decisions
- **Anti-staleness guards added**: Automatic detection and refresh of stale configuration data
- **Post-task persona verification**: Validation step confirms persona performance after task completion
- **Memory Wiki integration**: Full integration with OpenClaw Memory Wiki for persistent knowledge

### What's New in v6.0.7 (March 27, 2026)
- **Persona Matching Protocol**: Personas are now matched per-task at runtime, not assigned per-department at build time. New `persona-matching-protocol.md` documents the 5-layer alignment check (Mission, Values, Company Goals, Department Goals, Task Fit). Layers 1-2 run once at setup; Layers 3-5 run fresh every task.
- **persona-categories.json added to Skill 22**: 40 personas with 12 domain tags and 6 perspective tags for category-filtered matching.
- **Skill 23 governing-personas.md corrected**: Now a reference guide per role folder, not a static department assignment.
- **Skill 32 token-in-webhook-response architecture**: The tunnel token now comes directly in the webhook HTTP response. No more waiting for Trevor to forward a Telegram notification. Trevor still receives a backup Telegram notification.
- **Skill 32 cloudflared install built into process**: `create-tunnel.sh` auto-installs cloudflared (brew on Mac, curl on Linux) if not present.
- **Skill 32 simplified script**: `create-tunnel.sh` rewritten from 147 lines to 59. Calls webhook, captures token, saves to .env, starts PM2, verifies URL.
- **Skill 14 rewritten:** Google Workspace CLI (gws) replaces google-api.js and gog - single tool for Gmail and Workspace
- **Skill 23 fixed:** AI Workforce Blueprint now properly presents options A, B, C before asking questions
- **Skill 15 fixed:** BlackCEO Team Management now requires real Telegram IDs, not placeholders
- **Legacy retrieval fully replaced** with Google Gemini Embedding 2 across all skills and scripts
- **Onboarding watchdog** added: 10-minute stall detection, never-stop-early, progress reporting every 5 skills
- **Mandatory file reading protocol:** agent must read ALL .md files before installing any skill
- **CONTRIBUTING.md** added: complete checklist for adding/modifying skills
- **MIGRATION.md** added: step-by-step guide for existing Google Embedding 2 users to migrate to Gemini Embedding 2

---

## Quick Install (Recommended)

Run this one command on the target machine:

```bash
curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash
```

What it does:
1. Downloads the latest onboarding package
2. Copies skills into `~/.openclaw/skills/`
3. Installs Gemini Engine early (required by skill 22 and skill 23)
4. Asks for missing API keys with a skip option (does not block optional skills)
5. Prints the next step

---

## Next Step After Install

Open:

- `~/.openclaw/skills/Start Here.md`

That file is the master instruction file. It contains:
- prerequisites
- exact skill install order
- the required file read order per skill
- verification rules
- what to do on failures

---

## Skill Inventory (Folder Names)

| Folder | Skill |
|--------|-------|
| 01-teach-yourself-protocol | Teach Yourself Protocol |
| 02-back-yourself-up-protocol | Back Yourself Up Protocol |
| 03-agent-browser | Agent Browser |
| 04-superpowers | Superpowers |
| 05-ghl-setup | GHL Setup |
| 06-ghl-install-pages | GHL Install Pages |
| 07-kie-setup | KIE Setup |
| 08-vercel-setup | Vercel Setup |
| 09-context7 | Context7 Setup |
| 10-github-setup | GitHub Setup |
| 11-superdesign | Superdesign |
| 12-openrouter-setup | OpenRouter Setup |
| 13-google-workspace-setup-ARCHIVED | Google Workspace Setup (ARCHIVED — replaced by skill 14) |
| 14-google-workspace-integration | Google Workspace Integration |
| 15-blackceo-team-management | BlackCEO Team Management |
| 16-summarize-youtube | Summarize YouTube |
| 17-self-improving-agent | Self-Improving Agent |
| 18-proactive-agent | Proactive Agent |
| 19-humanizer | Humanizer |
| 20-youtube-watcher | YouTube Watcher |
| 21-tavily-search | Tavily Search |
| 22-book-to-persona-coaching-leadership-system | Book-to-Persona Coaching Leadership System |
| 23-ai-workforce-blueprint | AI Workforce Blueprint |
| 24-storyboard-writer | Storyboard Writer |
| 25-video-creator | Video Creator |
| 26-caption-creator | Caption Creator |
| 27-video-editor | Video Editor |
| 28-cinematic-forge | Cinematic Forge |
| 29-ghl-convert-and-flow | GHL Convert and Flow (Tier 3 API reference for skill 36) |
| 30-fish-audio-api-reference | Fish Audio API Reference |
| 31-upgraded-memory-system | Upgraded Memory System |
| 32-command-center-setup | Command Center Setup |
| 33-department-heads-ARCHIVED | Department Heads (ARCHIVED) |
| 34-intelligent-staffing-ARCHIVED | Intelligent Staffing (ARCHIVED) |
| 35-social-media-planner | Social Media Planner — FFmpeg ≥4.0 + kie.ai key required. Routes GHL operations through skill 36 MCPs when installed. |
| 36-ghl-mcp-setup | **GHL MCP Setup (v9.0.0)** — 5-tier GHL access chain: Official MCP (36 tools) → Community MCP (588 tools) → REST API (skill 29) → Playwright → Codex Computer Use. Sets `$GHL_COMMUNITY_MCP_URL`, installs launchd plist (macOS), wires cardinal rules into SOUL.md/AGENTS.md/TOOLS.md/MEMORY.md, includes 20-assertion QC script. |

**Total: 36 numbered skill folders** (33 active + 3 archived: 13, 33, 34).

> **Note:** The Voice Call Plugin (`@openclaw/voice-call`) is installed separately via `openclaw plugins install @openclaw/voice-call`. It is NOT part of the onboarding skill sequence — installing it as a skill caused double-install conflicts.

---

## What Is Inside a Skill Folder

Each skill folder contains a subset of these files:
- `SKILL.md`
- `INSTALL.md`
- `INSTRUCTIONS.md`
- `EXAMPLES.md`
- `CORE_UPDATES.md`
- `*.skill` (the OpenClaw install descriptor)

Some skills also include:
- `*-full.md` (a full reference guide)
- `upstream-original/` (for imported skills)
- `scripts/`, `templates/`, `references/`

---

## Notes

- Gemini Engine is installed by `install.sh` before platform skills. There is no separate Gemini Engine skill folder.
- If you fork this repo for client delivery, update `install.sh` to point at your fork.
