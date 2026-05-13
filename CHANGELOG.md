## v9.5.0 - May 13, 2026 - Smart Model Selector + Anthropic Stripped from Skills 15, 22, 23

### Added
- **`shared-utils/select_model.py`** — new single source of truth for model selection across all skills. Three purpose-tier chains:
  - **`heavy`**: ollama/kimi-k*:cloud → openrouter/moonshot/kimi-k* → ollama/deepseek-v*-pro:cloud → openrouter/deepseek/deepseek-v*-pro → (openai-)codex/gpt-* (latest version per slot)
  - **`mid`**: ollama/minimax-m*:cloud → openrouter/xiaomi/mimo-v*-pro
  - **`fast`**: ollama/deepseek-v*-flash:cloud → openrouter/deepseek/deepseek-v*-flash → openrouter/google/gemini-*-flash-lite
- **Auto-version pickup** — selector picks the highest version number it finds in each chain slot. When Kimi 2.7 or 3.0 or GPT 5.10 ships and the client adds it, the selector picks it automatically with no skill edit needed.
- **Tier 5 owner-input fallback** — if a chain finds nothing in the client's config, the selector returns a plain-English prompt for the install agent to show the owner. The install does NOT block; only the model binding waits on the reply.
- CLI: `python3 select_model.py --skill X --purpose-tier {heavy,mid,fast} --format {json,id,prompt}`. Exit 0 = model returned. Exit 2 = owner input required.

### Security / Policy
- **Anthropic models FORBIDDEN at every tier.** `anthropic/claude-*` is hardcoded into the FORBIDDEN_PREFIXES filter and rejected before selection. Cost-prohibitive per Trevor's policy. The selector enforces this even if a client has Anthropic models in their config.

### Changed (Skill 22 — Book-to-Persona)
- **`_meta.json` rewritten and version bumped 1.0.0 → 2.0.0.** Model fields now declare SELECTION INTENT (`"kimi-latest-preferred"`, `"oauth-gpt-preferred-with-kimi-fallback"`), not hardcoded IDs. `selector` field points at `shared-utils/select_model.py`. `forbidden_prefixes` lists `anthropic/` and `claude-`.
- **`pipeline/orchestrator.py`** — replaced hardcoded `MODEL_EXTRACTION = "moonshotai/kimi-k2.5"`, `MODEL_ANALYSIS = "deepseek/deepseek-v3.2"`, `MODEL_SYNTHESIS = "gpt-5.3-codex"` with `_resolve_model()` that calls the selector at runtime with `--purpose-tier heavy`. Falls back to documented defaults if the selector is unreachable (defense in depth).
- **`PIPELINE.md`** — Phases 1, 2, 3 documentation rewritten to describe dynamic selection with all 5 heavy-tier chain positions. Removed every hardcoded "kimi-k2.5", "deepseek-v3.2", "gpt-5.4" reference.
- **`CORE_UPDATES.md`** — splice text for AGENTS.md / TOOLS.md updated. No more hardcoded model IDs in the splice; agents are told to call the selector.
- **`QC.md`** — Phase 1/2/3 routing assertions changed from "Phase 1 routing entry: moonshot/kimi-k2.5" to "Phase 1 routing references DYNAMIC selection via shared-utils/select_model.py".
- **`CHECKLIST.md`** — Phase 1 and Phase 2 sub-agent-spawn checklists updated to instruct the install agent to use the selector output.

### Changed (Skill 15 — BlackCEO Team Management)
- **`blackceo-team-management-full.md`** — Removed:
  - JSON config block hardwiring `openai-codex/gpt-5.3-codex` as primary with `openrouter/minimax/MiniMax-M2.5` and `openrouter/google/gemini-3-flash-preview` fallbacks
  - "Complex reasoning → spawn with model: anthropic/claude-opus-4-6" line
  - "Creative task → spawn with model: mistral/latest-creative" line
  - Decision tree referencing Opus 4.6, Sonnet 4.6, Mistral Creative, MiniMax M2.5, Gemini Flash
  - Worker-config note referencing MiniMax/Sonnet/Codex as the only tool-call-capable list
- **Replaced with selector references and tier descriptions** (heavy/mid/fast).
- **`EXAMPLES.md`** — Worker config block now points at the selector instead of hardcoding `openai-codex/gpt-5.3-codex`.

### Changed (Skill 23 — AI Workforce Blueprint)
- **`SKILL.md` Model Requirements section** — entire "Approved models" list (which included `anthropic/claude-opus-4-6` and `anthropic/claude-sonnet-4-6` as the top two entries) replaced with selector tier reference + chain explanation. `kimi-k2.5` removed from the "Forbidden for this skill" list (the skill is now version-agnostic).
- **`INSTALL.md` Section 5-PRE Model Check** — rewritten to call the selector and react to its Tier 5 owner-input case. Removed the hardcoded "approved models" list that previously included two Anthropic entries.
- **`QC-ROLES-MASTER.md` 17-row department-to-model table** — every row's "Recommended Models" column was a list of Anthropic + GPT IDs (16 of 17 rows referenced `anthropic/claude-opus-4-6` or `anthropic/claude-sonnet-4-6`). Column renamed to "Selector Tier" and now contains `--purpose-tier heavy` or `--purpose-tier mid` references. Added an "How to invoke" code block at the bottom.

### Changed
- **ONBOARDING_VERSION** bumped to v9.5.0 in install.sh, update-skills.sh, VERSION, README.md, both repos.

---

## v9.4.0 - May 13, 2026 - Canonical Bootstrap + Sub-Agent Config in Step 0

### Added
- **Canonical Step 0 bootstrap block** in `install.sh`. Runs before any other install work and writes the protocol-gate numeric limits + sub-agent permissions block to `openclaw.json`:
  - `agents.defaults.bootstrapMaxChars` → `200000` (hard overwrite)
  - `agents.defaults.bootstrapTotalMaxChars` → `400000` (hard overwrite)
  - `agents.defaults.subagents.maxChildrenPerAgent` → `20` (hard overwrite)
  - `agents.defaults.subagents.maxConcurrent` → `100` with min-clamp of 50 (hard overwrite if existing < 100, never lower than 50)
  - `agents.defaults.subagents.maxSpawnDepth` → `5` (hard overwrite)
  - `agents.defaults.subagents.thinking` → `"high"` (hard overwrite)
  - `agents.defaults.subagents.model.fallbacks` — **preserved** if a client has customized it; only seeded with default chain (Ollama Kimi cloud → OpenRouter Xiaomi Mimo → DeepSeek v4 pro) if missing entirely
  - `agents.list[N].subagents.allowAgents = ["*"]` wildcard applied to every entry in the agent list (75 entries on Trevor's live config). Previously most entries had `allowAgents: []` and could not spawn sub-agents at all.

### Fixed
- **Removed conflict with legacy `configure_concurrency()` function** which used the wrong field names (`maxQueue`/`maxDepth`) and lower values (`50/10/4`). Renamed to `configure_concurrency_LEGACY_UNUSED()`. Step 7 invocation replaced with a no-op note that points back at Step 0.
- **Wave-count documentation** in the UPDATE PENDING flag aligned with `maxChildrenPerAgent=20`: Wave 2 ~11 skills parallel, Wave 3 ~14 skills parallel — both within the cap. Previous comments said "~10 sub-agents" which was stale from older `maxChildren=10`.

### Changed
- **5-wave dependency-aware install pipeline** documented explicitly:
  - **Wave 1 — Foundation** (sequential): `01-teach-yourself-protocol`, `02-back-yourself-up-protocol`
  - **Wave 2 — Independent integrations** (parallel, up to 20 children): 11 skills — 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 14
  - **Wave 3 — Content + service tools** (parallel, up to 20 children): 14 skills — 15, 16, 17, 18, 19, 20, 21, 24, 25, 26, 27, 28, 29, 30
  - **Wave 4 — Infrastructure** (sequential): `31-upgraded-memory-system` → `36-ghl-mcp-setup`
  - **Wave 5 — Main-orchestrator-only** (sequential, NEVER delegate): `22-book-to-persona` → `23-ai-workforce-blueprint` → `32-command-center-setup` → `35-social-media-planner`
- **ONBOARDING_VERSION** bumped to v9.4.0 in install.sh, update-skills.sh, VERSION, README.md, both repos.

---

## v9.3.9 - May 13, 2026 - Trigger Doc Renamed "Fresh Install" → "Full Onboarding"

### Changed
- **`ONBOARDING-TRIGGERS.md` Blocks 1-4 renamed** from "Fresh Install" to "Full Onboarding" to accurately reflect the actual onboarding workflow. In Trevor's process, every client arrives with a baseline OpenClaw + Telegram agent already configured. Blocks 1-4 lift that baseline to the full 36-skill onboarding package. The old "Fresh Install" name implied an empty machine, which never occurs in the real workflow and was misleading to anyone reading the trigger document.
- **Blocks 2 (Mac, Telegram) and 4 (VPS, Telegram) marked with ⭐ as the standard path.** Terminal blocks (1 and 3) remain for self-service or bootstrap scenarios.
- **Removed alarmist "Before you start" warnings** from Blocks 2 and 4 that previously redirected clients to Terminal-based blocks if they didn't have OpenClaw running — that condition doesn't apply to this workflow.
- **Block selector table heading** updated: "Fresh install or update?" → "Full onboarding or update?"
- **ONBOARDING_VERSION** bumped to v9.3.9 in install.sh, update-skills.sh, VERSION file, README.md. Both repos.

---

## v9.3.8 - May 13, 2026 - Core.md Terminology Seeded into MEMORY.md

### Added
- **`install.sh` Step 10b and `update-skills.sh` post-flag hook**: every install and every update now seeds the workspace `MEMORY.md` with a `## Terminology — Core.md Files` section, idempotently. The section defines the owner's term "Core.md files" as the 6 OpenClaw bootstrap files loaded each session (IDENTITY, SOUL, AGENTS, USER, TOOLS, MEMORY) — explicitly NOT a literal `core.md` file. Includes a routing table mapping intent (personality / procedure / tool note / durable fact / user info / identity metadata) to the correct target file. Re-runs detect the existing section header and skip.

### Fixed
- **Corrected SOUL.md and IDENTITY.md definitions** in install/update seeds and in the README, replacing earlier compressed versions that had stripped specifics the owner explicitly defined:
  - **IDENTITY.md** now states: *the role the agent is playing — contains the experiences and the skills they need to embody that role.* Earlier seed listed only "name / vibe / emoji / routing metadata," which omitted the embodied capability set.
  - **SOUL.md** now states: *the personality, true mission, beliefs, rules, goals, belief systems, and principles — who the agent IS, not who they are playing.* Earlier seed compressed this to "personality, beliefs, mission, principles, boundaries," dropping rules / goals / belief systems and inserting "boundaries" from generic OpenClaw docs.
- **README.md staleness** — both repos: "Current Version" was stuck at v9.3.5 through the v9.3.6 and v9.3.7 releases. Now bumped to v9.3.8 with What's New entries for v9.3.6, v9.3.7, and v9.3.8 added.

### Changed
- **ONBOARDING_VERSION** bumped to v9.3.8 in install.sh, update-skills.sh, VERSION file, README.md. Both repos.

---

## v9.3.7 - May 13, 2026 - Redact production GHL Location ID from documentation

### Security
- **Redacted the real BlackCEO GHL Location ID** from 7 documentation references across both repos. Replaced with `[REDACTED]` in prose citations (incident postmortems in SKILL.md, INSTRUCTIONS.md, INSTALL-CONTRACT.md, CHANGELOG.md, README.md) and with the fake string `AbCdEfGhIjKlMnOpQrStUv` in format examples (ghl-mcp-setup-full.md ×2). Pure documentation change — zero runtime impact: no script, install path, QC, or agent behavior reads these files for the Location ID value (the real ID lives in `~/.openclaw/secrets/.env` as `GOHIGHLEVEL_LOCATION_ID` and is read from there at runtime). Removes a public production-identifier leak from HEAD. Note: the real ID remains in git history of prior commits — rotation is not possible for Location IDs (they're permanent tenant identifiers), so history rewrite would be the only complete scrub if needed.

### Changed
- **ONBOARDING_VERSION** bumped to v9.3.7 in install.sh, update-skills.sh, VERSION file. Both repos.

---

## v9.3.6 - May 13, 2026 - Sunday Cron Quota Gate + Triggers Skill 36 Surfacing

### Added
- **`cron-prompt.txt` RULE 18 — GHL rate-limit pre-check.** Before the Sunday agent runs anything that calls GHL (Skill 36's `qc-ghl-mcp-setup.sh`, post-install QC for any GHL-connected skill, or self-invented "verify everything" steps), it must probe quota via Tier 3 direct REST (the only path whose headers are not stripped), read `X-RateLimit-Daily-Remaining`, and skip GHL verification for the cycle if < 5000 remain. Logs the skip to MEMORY.md and surfaces the reset clock time to the client in plain English. Binding even when the client says "install all" — protection is non-negotiable.
- **`ONBOARDING-TRIGGERS.md` — "What actually gets installed" inventory section.** Headlines what the 8 install blocks deploy, naming Skill 36 (GHL MCP, 5-tier chain, port 8765, launchd/systemd, disclosure-header protocol, standalone `qc-ghl-mcp-setup.sh` validator) and the other foundation skills (01, 02, 05, 22, 23, 29, 31, 32, 35) so anyone reading the triggers knows what the install delivers without digging into the install script.
- **`ONBOARDING-TRIGGERS.md` — pre-install rate-limit warning callout.** Documents the 100/10s burst + 200,000/day cap, the shared-bucket constraint across all three MCP tiers, the 2026-05-13 incident, and explains that if Skill 36's QC refuses to proceed because quota is low, that is the protection working — wait for the reset clock and re-run.

### Fixed
- **Filename drift across 18 live references to the Skill 36 QC script** — `qc-ghl-setup.sh` (obsolete) renamed to `qc-ghl-mcp-setup.sh` (the file that actually ships) in: `ONBOARDING-TRIGGERS.md` (6 refs), `36-ghl-mcp-setup/INSTALL.md` (5 refs), `36-ghl-mcp-setup/QC.md` (2 refs), `36-ghl-mcp-setup/CORE_UPDATES.md` (1), `36-ghl-mcp-setup/SKILL.md` (1), `36-ghl-mcp-setup/ghl-mcp-setup-full.md` (2), `README.md` (2). Historical CHANGELOG entries preserved as-written.
- **Eliminated embedded duplicate copies of the QC script.** `36-ghl-mcp-setup/QC.md` Section 6 and `36-ghl-mcp-setup/ghl-mcp-setup-full.md` Sections 11.B/11.C previously embedded the full QC script body as a heredoc. The standalone `qc-ghl-mcp-setup.sh` is now declared the single source of truth; the embedded copies are replaced with pointers and a short summary of what the script does. Closes the drift hazard where v9.3.5's rate-limit probe was added to the standalone but the embedded copies silently fell out of sync.
- **Updated `INSTALL.md` Action 9** — removed the instruction to extract the script from `QC.md` and save it. Now points directly at the shipped standalone file.

### Changed
- **ONBOARDING_VERSION** bumped to v9.3.6 in install.sh, update-skills.sh, VERSION file. Both repos.

---

## v9.3.5 - May 13, 2026 - GHL Rate-Limit Protocol (incident response)

### Added
- **Rate-limit awareness protocol** baked into the install discipline contract and Skill 36 documentation. Triggered by the 2026-05-13 incident where BlackCEO location [REDACTED] burned all 200,000 daily GHL API calls during development testing. All three tiers (Official MCP, Community MCP, Raw API) returned 429s simultaneously because they share the same per-location backend bucket — switching tiers does NOT bypass.
- **INSTALL-CONTRACT.md — new Rule 8a "GHL rate-limit awareness"**. Binding rules:
  - Before bulk operations: probe `X-RateLimit-Daily-Remaining`. If under 1000, STOP. If under 5000, warn the owner. Compute reset time from `X-RateLimit-Daily-Reset` and surface in plain English ("back at HH:MM ET").
  - On 429: NEVER retry blindly. NEVER fall through tiers. Parse reset header, surface wall-clock time, log to MEMORY.md under "## Rate Limit Incidents".
  - Always batch: limit=100 page size, cache list results in MEMORY.md for 5+ min, polling intervals >=60 sec.
  - Documented past failure block with date + location ID + root causes (test loops + n8n polling + community MCP polling + agent per-turn re-fetches).
- **Skill 36 SKILL.md "Critical Things Your Agent Must Know" entry #7** — full rate-limit summary visible to every agent reading the skill.
- **Skill 36 INSTRUCTIONS.md "Rate-Limit Protocol — 429 is NOT a fallthrough trigger"** — operational reference with pre-flight curl example showing how to read the headers, on-429 response steps, batching rules, common quota-burners list.
- **Skill 36 qc-ghl-mcp-setup.sh — new Section B2** — actually probes the rate-limit headers on a Tier 3 direct API call (which is where the headers live; the Official MCP SSE wrapper does not expose them). Reports remaining daily quota, burst quota, and reset time in plain English. Fails the QC if under 100 daily remaining. Tested live during this release — correctly detected the 0-remaining state on the burned location and computed reset time as "around 7:00 PM EDT".

### Headers reference

- `X-RateLimit-Remaining` — burst budget left in current 10s window
- `X-RateLimit-Max` — 100 (burst cap per 10s)
- `X-RateLimit-Daily-Remaining` — daily budget left
- `X-RateLimit-Limit-Daily` — 200000 (daily cap)
- `X-RateLimit-Daily-Reset` — milliseconds until daily quota resets
- `X-RateLimit-Interval-Milliseconds` — 10000 (10-second burst window)

These headers ONLY appear on direct API responses (Tier 3 endpoints under services.leadconnectorhq.com/contacts, /locations, /products, etc.). The Official MCP SSE wrapper does NOT expose them — its responses contain only `data: {...}` JSON-RPC payloads. Pre-flight probes must hit a direct API endpoint.

### Changed
- **ONBOARDING_VERSION** bumped to v9.3.5 in install.sh and update-skills.sh.
- **version file** bumped to v9.3.5 in both repos.

### Risk: medium
This release adds new agent behavior (rate-limit pre-flight + 429 handling). Behavior is additive — clients on v9.3.4 still work, but the new rules prevent future quota exhaustion. Most impactful for clients who run heavy GHL workflows or test scripts.

### Notes
- Trevor's local workspace AGENTS.md and MEMORY.md updated separately during this release (not part of the repo push). MEMORY.md got a "## Rate Limit Incidents" section logging the 2026-05-13 event with full headers, root causes, and the fix.
- VPS install.sh has the same rules but uses systemd paths where the Mac uses launchd.

---

## v9.3.4 - May 13, 2026 - Skill 36 standalone qc-ghl-mcp-setup.sh

### Added
- **Standalone `qc-ghl-mcp-setup.sh`** at the root of `36-ghl-mcp-setup/` folder in both repos. Matches the convention of the other 32 skills (each skill has a `qc-<short-name>.sh` at its folder root). Previously the Skill 36 QC script lived embedded inside QC.md as a heredoc the agent was supposed to write to disk during install — a special case that broke folder-listing consistency.
- The new standalone script ports the full v1.0.0 Skill 36 QC logic: master-files fuzzy lookup, GHL canonical credentials check (PIT — not API key), Tier 1 Official MCP tool count (36), Tier 2 Community MCP service running + /health + 500+ tools + real data call, core .md wiring, master-files reference doc archived, PIT security check.
- All 33 active skills now have a standalone qc-*.sh script at their folder root. Uniform structure. The QC.md heredoc in Skill 36 is retained for documentation reference.

### Changed
- **ONBOARDING_VERSION** bumped to v9.3.4 in install.sh and update-skills.sh.
- **version file** bumped to v9.3.4 in both repos.

### Risk: low
Pure additive change. No behavior changes. The standalone script duplicates the heredoc logic verbatim — anything that previously worked off the heredoc still works; the standalone file now also works for tools that expect a file at the folder root.

---

## v9.3.3 - May 13, 2026 - Mac/VPS Sync Audit + Skill 35 v2.0.0 mirrored to VPS

### Fixed
- **VPS install.sh header URL** referenced Mac repo (`openclaw-onboarding/main/install.sh` instead of `openclaw-onboarding-vps/main/install.sh`). Stale since the original VPS fork. Fixed.
- **Skill 35 v2.0.0 only existed on Mac.** The v9.3.0 INSTALL.md rewrite, QC.md rubric upgrade, and qc-skill35.sh bespoke validator only landed on the Mac repo. VPS was still shipping the v1.4.0 INSTALL.md with deprecated `GHL_PRIVATE_TOKEN` env var, deprecated `~/clawd/secrets/.env` paths, and old PIT scope list. Mirrored to VPS. Both repos now ship Skill 35 v2.0.0 identically.

### Audited (confirmed correct)
- **Cross-platform defensive branches** in both install.sh and update-skills.sh that read `[ -d "/data/.openclaw" ] && REPO_URL=...-vps/main` — these are intentional, protect against the wrong script being run on the wrong machine. Each script auto-detects platform and switches repo URL.
- **21 skill folders have legitimate Mac-vs-VPS path differences** (Mac uses `~/clawd/...`, VPS uses `/data/clawd/...`). This is correct — not cross-contamination. The platform paths are platform-specific.
- **All 36 skill folders present in both repos** (33 active + 3 archived: 13/33/34). No skills missing on either side.

### Changed
- **ONBOARDING_VERSION** bumped to v9.3.3 in install.sh and update-skills.sh.
- **version file** bumped to v9.3.3 in both repos.

### Risk: low
Bug-fix release. No new infrastructure. Existing clients on v9.3.2 should run `update-skills.sh` to pull the Skill 35 v2.0.0 fix on VPS clients specifically.

---

## v9.3.2 - May 13, 2026 - Bespoke Per-Skill QC Scripts

### Changed
- **Replaced the 31 generic qc-*.sh scripts with bespoke skill-specific validation scripts.** v9.3.1 generated a single 100-line generic template and copied it to every skill. v9.3.2 ships custom scripts where each script tests the actual goal of that specific skill.
- Bespoke per-skill assertions include:
  - **Skill 01 (TYP):** 3-layer storage model + AGENTS.md lean-file check (<50KB)
  - **Skill 02 (BYUP):** backup directory writable + live cp test
  - **Skill 03 (Agent Browser):** agent-browser CLI on PATH + --help responds
  - **Skill 04 (Superpowers):** companion files preserved (git-clone install, not curl-only)
  - **Skill 05 (GHL Setup):** PIT format validation + live `services.leadconnectorhq.com/locations/` endpoint hit + alias awareness in core files
  - **Skill 06 (GHL Install Pages):** GHL_AGENCY_EMAIL/PASSWORD present + Playwright + Chrome detection
  - **Skill 07 (KIE Setup):** live `api.kie.ai/api/v1/chat/credit` endpoint check
  - **Skill 08 (Vercel):** vercel CLI + jq + live token validation via `api.vercel.com/v2/user`
  - **Skill 09 (Context7):** MCP registered in openclaw mcp list
  - **Skill 10 (GitHub):** gh authenticated + git user.email + git user.name configured
  - **Skill 11 (Superdesign):** at least one LLM key + Chrome + Node v16+
  - **Skill 12 (OpenRouter):** sk-or- prefix + live `openrouter.ai/api/v1/auth/key` validation
  - **Skill 14 (Google Workspace):** gws CLI + auth status + legacy 'google-api.js' confirmed absent
  - **Skill 15 (Team Management):** CLIENT_ID present + non-placeholder TEAM_MEMBER_*_ID values
  - **Skill 16 (YouTube Summary):** at least one summarization LLM + yt-dlp
  - **Skill 21 (Tavily):** live `api.tavily.com/search` hit
  - **Skill 22 (Book-to-Persona):** Skill 31 dep + coaching-personas folder + persona-categories.json + PERSONA-ROUTER.md
  - **Skill 23 (Workforce):** Skill 22 dep + STATE C evidence (departments/ OR ORG-CHART.md) + company-config.json
  - **Skill 25/26/27 (Video skills):** FFmpeg-specific codec checks (libx264, drawtext filter, concat demuxer)
  - **Skill 28 (Cinematic Forge):** FFmpeg supports x264 + AAC
  - **Skill 29 (GHL API):** PIT + references/ subfolder + master reference doc in master-files
  - **Skill 30 (Fish Audio):** live `api.fish.audio/wallet/self/api-credit` hit
  - **Skill 31 (Memory):** all 8 memory layers (core .md → flush → session → Gemini → memory-core → Cognee → Obsidian → Active Memory) + DREAMS.md
  - **Skill 32 (Command Center):** port 3000 (Mac)/4000 (VPS) reachable + PM2 + cloudflared (Mac) + tunnel token
- All bespoke scripts share the same shell scaffolding: source lib-shared.sh, fallback resolve_platform_paths, color-coded PASS/FAIL/WARN output, proper exit codes for cron gating.

### Risk: low
Pure replacement of QC scripts. No install.sh / update-skills.sh behavior changes. Existing v9.3.1 installs work unchanged; running update-skills.sh pulls the bespoke scripts in.

---

## v9.3.1 - May 13, 2026 - Universal QC + Dependency Waves + Step 0 Bootstrap

### Added
- **Install-time QC rubric appended to all 31 remaining active skills** — every skill (01–32, plus 36) now has the standard 0-10 install-time rubric with 8.5+ pass gate, loop-until-passing rule (max 5 loops), and 7-item self-audit. Skill 35 has its own bespoke v2.0.0 rubric. Skill 36 has its own bespoke 20-assertion rubric. Total: 33 active skills, 33 QC rubrics with the 8.5+ gate.
- **Bundled `qc-*.sh` validation script for each of the 31 skills** that didn't have one — generic baseline checks (SKILL.md/INSTALL.md/QC.md/CORE_UPDATES.md present, INSTALL-CONTRACT acknowledged, skill installed at canonical path, secrets file chmod 600). Skills 35 and 36 retain their bespoke scripts (`qc-skill35.sh` and `qc-ghl-setup.sh`).
- **Dependency-aware install waves** replacing the old number-based waves:
  - Wave 1 (sequential): 01-teach-yourself-protocol, 02-back-yourself-up-protocol
  - Wave 2 (parallel ~10 sub-agents): 03–12, 14
  - Wave 3 (parallel ~10 sub-agents): 15–21, 24–30
  - Wave 4 (sequential): 31 (memory) → 36 (MCP)
  - Wave 5 (sequential, main-orchestrator-only): 22 (persona) → 23 (workforce) → 32 (command center) → 35 (social planner)
- **Step 0 "Bootstrap" in install.sh** — runs BEFORE Step 1. Recommends `/new` session, writes state-carryover file (`.install-resume.json`), sets `agents.defaults.subagents` to 20/100/5/high, prints model selection priority (subscription → Ollama cloud → OpenRouter; Opus/Sonnet forbidden by default). Cost-aware per INSTALL-CONTRACT.md Rule 10.
- **Sub-agent failure retry rule** added to cron-prompt.txt (Rule 15): same-model retry → next-fallback retry → escalate to master. Never silently abandon a task.
- **Gateway-restart guard** added to cron-prompt.txt (Rule 16): only master orchestrator can call `openclaw gateway restart`, only when `openclaw subagents list` returns empty.
- **INSTALL-CONTRACT.md re-acknowledgment rule** in cron-prompt.txt (Rule 17): before each skill, agent must log "INSTALL-CONTRACT.md acknowledged for skill NN-name. Proceeding."

### Changed
- **install.sh UPDATE PENDING flag** — 5-phase processing order rewritten with dependency-aware waves (was number-based). Plus explicit sub-agent retry policy and gateway-restart guard inline.
- **ONBOARDING_VERSION** bumped to v9.3.1 in install.sh and update-skills.sh.
- **version file** bumped to v9.3.1.

### Risk: low
This release is additive and tightens existing discipline. No breaking changes. All clients on v9.3.0 benefit from running `update-skills.sh` to get the new QC rubrics and qc-*.sh scripts.

### Notes
- The wave order in the UPDATE PENDING flag now matches the actual dependency graph (memory before persona, persona before workforce, workforce before command center, etc.).
- Parallel waves (2 and 3) can run up to maxConcurrent sub-agents (default 100 per agents.defaults.subagents) — realistic install with 10–20 parallel sub-agents per wave.
- Step 0 also writes `.install-resume.json` so if the client starts `/new` mid-install, the new session can resume.

---

## v9.3.0 - May 13, 2026 - Install Discipline Contract + Skill 35 v2.0.0

### Added
- **`INSTALL-CONTRACT.md`** (312 lines, repo root) — binding discipline contract every agent must read before installing/updating any skill. 15 rules covering: read all .md files first, follow INSTALL.md order verbatim, QC 8.5+ or loop (max 5), no shortcuts (`--force`, `--break-system-packages`, `--no-verify`, model substitution forbidden), sub-agent gateway-restart guard (master orchestrator only, only when subagents list is empty), credential search order (canonical → JSON → deprecated), GHL alias awareness, "PIT not API key" rule, fuzzy master-files detection, cost-aware model selection priority (subscription → Ollama cloud → OpenRouter; Opus/Sonnet forbidden by default), sub-agent settings (20/100/5/high), `/new` session recommendation with state carryover via `.install-resume.json`, owner-facing communication style (over-60 calibrated), 8-point self-audit before declaring done, contract re-acknowledgment BEFORE EACH SKILL.
- **`lib-shared.sh`** (240 lines, repo root) — shared bash library sourced by install.sh, update-skills.sh, check-updates.sh, and skill scripts:
  - `detect_platform()` / `resolve_platform_paths()` — single source of truth for Mac vs VPS paths
  - `find_master_files()` — fuzzy locator handling all name variants (one-word/two-word, hyphenated/underscored/spaced, mixed case, "documents" vs "files")
  - `get_or_create_master_files()`
  - `is_ghl_alias()` — recognizes ghl, gohighlevel, highlevel, convertandflow, leadconnector, leadconnectorhq, cnf
  - `canonical_ghl_pit_name()` / `canonical_ghl_location_id_name()` — single source of truth for env-var names
  - `read_ghl_pit()` / `read_ghl_location_id()` — read canonical → openclaw.json → deprecated names (with migration)
- **GHL alias awareness block** in install.sh UPDATE PENDING flag — teaches every installed agent that GHL, GoHighLevel, Convert and Flow, LeadConnector, CnF are all the same platform, and that **GHL does NOT use API keys** (deprecated ~2 years ago) — uses Private Integration Tokens (PITs).
- **Skill 35 (Social Media Planner) v2.0.0**:
  - Replaced `GHL_PRIVATE_TOKEN` with canonical `GOHIGHLEVEL_API_KEY` throughout INSTALL.md, CORE_UPDATES.md, SKILL.md
  - Migrated credential paths from `~/clawd/secrets/.env` (deprecated) to canonical `~/.openclaw/secrets/.env` (Mac) / `/data/.openclaw/secrets/.env` (VPS)
  - Updated required PIT scope list (full Skill 36 set + `medias.write` + `social-media-posting.readonly` + `social-media-posting.write`)
  - Added Step 4: detect Skill 36 → set `ROUTING_MODE=mcp-first` or `direct-api`. MCP-first now baked into the install sequence, not just post-install
  - Added 0-10 install-time QC rubric in QC.md with 8.5+ gate and loop-until-passing rule
  - New bundled `qc-skill35.sh` validation script (8 sections, ~70 assertions; mirrors Skill 36's qc-ghl-setup.sh pattern)
  - Removed 9-month-old `PPSA: PENDING` placeholder

### Changed
- **install.sh credential discovery list** — replaced `GHL_PRIVATE_TOKEN:GHL` and `GHL_LOCATION_ID:GHL` with canonical `GOHIGHLEVEL_API_KEY` and `GOHIGHLEVEL_LOCATION_ID` (with inline note that this is a legacy var name whose value is a PIT). Deprecated names still auto-detected for migration via Rule 7 of INSTALL-CONTRACT.md.
- **install.sh UPDATE PENDING flag** — inserted "🔴 GHL ALIAS AWARENESS" section right after "SOURCE OF TRUTH RULE", teaching every agent the full alias set and the PIT-not-API-key rule.
- **ONBOARDING_VERSION**: bumped to v9.3.0 in install.sh and update-skills.sh.
- **version file**: bumped to v9.3.0.
- **README "Current Version"**: bumped, plus full v9.3.0 "What's New" entry.

### Risk: low
This release tightens existing install discipline. No new infrastructure that didn't exist in v9.2.0. INSTALL-CONTRACT.md is additive — older clients on v9.2.0 still work without it; this release encourages adoption. Skill 35 v2.0.0 changes are backward-compatible — the auto-search step in INSTALL.md detects deprecated env var names and migrates them.

### Notes
- INSTALL-CONTRACT.md adoption is enforced via the cron prompt (next Sunday's run will reference it) and via every skill's INSTALL.md (Skill 35 already references it explicitly; other skills get updates in v9.4.0).
- Skill 35 v2.0.0 install scoring on a fresh install should pass 8.5+ cleanly. Existing Skill 35 installs running v1.4.0 should run `update-skills.sh --only "35"` and the agent should re-process activation per INSTALL-CONTRACT.md Rule 14.

---

## v9.2.0 - May 13, 2026 - Weekly Auto-Check System + Telegram Permission Flow

### Added
- **`check-updates.sh` at repo root** — READ-ONLY script that fetches the GitHub `version` file + `CHANGELOG.md` excerpt + per-skill `skill-version.txt` map from the live repo, compares against local state, emits structured JSON. Never installs anything. Designed to be called by the Sunday cron or manually for inspection.
- **`--only "05,06,36"` flag on `update-skills.sh`** — partial install support. Comma-separated list of skill folder prefixes; the updater only installs/updates matching folders. Existing call with no flag still does all-or-nothing.
- **Catchup detection in `update-skills.sh`** — if `.last-update-check` timestamp is older than 7 days, surfaces a note that the Sunday cron may have missed (machine asleep at 2am Sunday). Manual run still works normally; the note is informational.
- **Cron-installer in `install.sh` AND `update-skills.sh`** — idempotently creates the `weekly-onboarding-update` cron via `openclaw cron create`. Fresh installs get the cron automatically as part of Step 12. Existing clients (pre-v9.2.0) get the cron backfilled the first time they run `update-skills.sh` after upgrading.
- **`cron-prompt.txt` at repo root** — 14-rule orchestration prompt the Sunday cron fires. Detects platform, runs check-updates.sh on each relevant repo (onboarding + command-center), classifies risk per change (Q1 Option C — explicit `### Risk: low|medium|high` tag in changelog if present, agent inference if not), composes plain-English Telegram summary to client, requires explicit permission BEFORE installing, supports five response paths ("install all" / "install onboarding" / "install command center" / "install skills NN, NN" / "skip this week" / "ping Trevor"), escalates high-risk items to Trevor on `5252140759`, sends final summary after install completes.
- **Per-skill selection in cron prompt** — client can reply "install skills 5, 6, 36" and the cron uses `update-skills.sh --only "05,06,36"` instead of all-or-nothing.
- **High-risk safety check** — even if client says "install all", if any item is classified HIGH the agent stops and explicitly confirms before proceeding.
- **2-hour permission timeout** — if client doesn't reply, cron exits cleanly with a "no response, will ask next Sunday, no changes made" Telegram. No silent updates.

### Fixed
- **🐛 Silent Sunday auto-update bug**. The old `weekly-onboarding-update` cron prompt said *"Execute: bash update-skills.sh ... Report the results ... Ask the client if they want to proceed"*. Problem: `update-skills.sh` is destructive — running it = applying the update. So "report results" meant "tell client what was just applied" and "ask if they want to proceed" was nonsensical (proceed with what, it already happened). v9.2.0 replaces this with the new cron-prompt.txt that calls `check-updates.sh` (read-only) first, then asks permission, then runs the install only after explicit yes.
- Trevor's existing cron (`ad0730e5-b64c...`) was deleted and recreated with the v9.2.0 prompt as part of this release. The new cron ID is `bcbe0b1b-4d31-41a1-80d1-1d170b40f987`. Next fire: Sunday May 17, 2am ET.

### Changed
- **ONBOARDING_VERSION** bumped to v9.2.0 in `install.sh` and `update-skills.sh`.
- **version file** bumped to v9.2.0.
- **README "What's New"** entry added for v9.2.0; new feature link to cron-prompt.txt + check-updates.sh.

### Risk: medium
This release introduces new infrastructure (cron orchestration + per-skill install). The cron itself is backward-compatible (existing clients on v9.0.0+ will have it installed by running `update-skills.sh`). Per-skill install is opt-in via flag. The fix for the silent auto-update bug is the most impactful change — clients will now always be asked before any update applies.

### Notes
- Existing clients who already have a stale `weekly-onboarding-update` cron from pre-v9.2.0: the install script's `install_weekly_cron` function skips if a cron with that name exists. To force the upgrade, the client (or staff) must run `openclaw cron delete <id>` first, then re-run `update-skills.sh` to install the new prompt. This release does NOT automatically delete old crons — too destructive without explicit permission.
- The cron orchestration prompt depends on `check-updates.sh` being present in each repo (added in this release). The new cron will fail gracefully if run against a pre-v9.2.0 install (no `check-updates.sh` available yet).
- Backward-compatible with v9.1.x. Existing clients can upgrade via `update-skills.sh`.

---

## v9.1.1 - May 13, 2026 - Block-Based Trigger Document

### Changed
- **ONBOARDING-TRIGGERS.md restructured from 5 sections to 8 standalone blocks**. Previous version bundled the update path into a single "either platform" section; new version separates Mac-update-Telegram (Block 6) from VPS-update-Telegram (Block 8) and Mac-update-Terminal (Block 5) from VPS-update-Terminal (Block 7). Same for fresh installs (Blocks 1–4). Staff can now send a client a deep link to the exact block matching their situation.
- **Telegram contracts inside Blocks 2, 4, 6, 8 expanded from 12 rules to 18–22 numbered rules each**. New explicit rules cover: phase timing (Phase A 600s, B 900s, C 1200s, D 1800s, E no timeout), sub-agent concurrency caps (50/10/4), QC scoring thresholds (8/10 minimum), forbidden shortcut list (--break-system-packages, --force, --no-verify, --no-gpg-sign, model substitution, invented steps), watchdog alerts (10-min stall), communication style calibration (plain English, no jargon, headlines first, over-60 friendly), and required final-summary format. Rules are designed to survive frontier-model softening.
- **Quick block selector table** added at top of trigger doc — staff and clients can route to the right block in one glance.
- **Anchor IDs on each block** (e.g. ) for deep linking.

### Notes
- This is a content-only patch release.  and  are unchanged from v9.1.0 functionality; only the version string bumped to v9.1.1.
- Backward-compatible with v9.1.0 — clients on v9.1.0 don't need to update unless they want the new trigger doc structure (which is public/GitHub-hosted, so they'll see it regardless).
- The private staff version at  is synced to v9.1.1 with the same 8-block structure plus staff-only notes per block + escalation rules at top.

---

## v9.1.0 - May 13, 2026 - Telegram Handoff Fix + Onboarding Triggers

### Fixed
- **install.sh — silent Telegram failure on completion**: `openclaw message send ... 2>/dev/null || true` swallowed all errors. Now logs to `/tmp/openclaw-install-*.log` and surfaces a per-send status (`sent:TARGET`, `no-openclaw-cli`, `no-telegram-target`, or `failed:see-LOG`) so operators know whether the note actually delivered.
- **install.sh — race condition during gateway restart**: the post-restart Telegram send used `(sleep 10; openclaw message send ...) &` — the 10-second backgrounded delay finished AFTER the gateway restart had taken the gateway down, so the send silently failed. The completion message is now sent BEFORE the gateway restart while the gateway is still up.
- **install.sh — vague Telegram message body**: the old message said "Check AGENTS.md for UPDATE PENDING instructions" with no actionable content. Now contains a paste-ready instruction block the client copies directly to their agent.

### Added
- **install.sh — always-printed backup terminal block**: regardless of whether the Telegram note delivered, install.sh now prints a fully-formatted ASCII box at the end of the install containing the exact instructions to paste to the agent. No client gets stranded if Telegram is misconfigured.
- **update-skills.sh — UPDATE PENDING flag write**: previously only `install.sh` wrote the flag; existing-client updates via `update-skills.sh` left the agent unaware anything happened. Now `update-skills.sh` writes its own flag listing exactly which skills were newly installed and the activation steps for each.
- **update-skills.sh — Telegram notification + backup block**: mirrors the install.sh handoff. Same paste-ready body, same per-send status surfacing, same always-printed backup block.
- **update-skills.sh — `NEW_SKILLS_CSV` tracking**: the updater builds a comma-separated list of newly-installed (vs updated-in-place) skills during the install loop. The UPDATE PENDING flag and Telegram message both reference this list explicitly so the agent activates only what's new.
- **ONBOARDING-TRIGGERS.md at repo root**: new client-facing document with five trigger sections — (A) Mac terminal, (B) Mac Telegram, (C) VPS terminal, (D) VPS Telegram, (E) existing-client update for ANY prior version. No version numbers pinned. Plain-English hand-holding tone calibrated for an over-60 audience. README now links to this file as the first thing a new client should read.

### Changed
- **ONBOARDING_VERSION**: bumped to v9.1.0 in `install.sh` and `update-skills.sh`.
- **version file**: bumped to v9.1.0 in both Mac and VPS repos.
- **README "Current Version" header**: bumped to v9.1.0; added pointer to `ONBOARDING-TRIGGERS.md` for new clients.

### Notes
- The Telegram bugs were diagnosed by inspecting actual log behavior on Trevor's Mac (commit `40a57ce` install on 2026-05-13) — confirmed that the previous Telegram notification never arrived despite `openclaw message send` being a valid command. Root cause was error-swallowing + post-restart race, not command syntax.
- `update-skills.sh` is non-destructive — it backs up existing skills to `~/Downloads/openclaw-backups/` (Mac) or `~/openclaw-backups/` (VPS) before replacing them. Unchanged skills are still re-copied for hash consistency, but the backup ensures recovery.
- This release is backward-compatible with v9.0.0. Clients on any prior version can run `update-skills.sh` to land on v9.1.0 without re-running the full install.

---

## v9.0.0 - May 13, 2026 - GHL MCP Multi-Tier Access

### Added
- **Skill 36 (`36-ghl-mcp-setup`)**: New skill that installs the 5-tier GHL access chain. Folder contains 10 files (SKILL, INSTALL, INSTRUCTIONS, EXAMPLES, CORE_UPDATES, QC, CHANGELOG, skill-version.txt, ghl-mcp-setup-full.md, ghl-mcp-setup.skill bundle).
- **5-tier escalation chain**:
  - Tier 1 — Official GHL MCP (`ghl-mcp`, 36 tools, hosted by GHL, stateless protocol)
  - Tier 2 — Community GHL MCP (`ghl-community-mcp`, 588 tools, BusyBee3333 2026 fork, runs locally on `$GHL_COMMUNITY_MCP_URL`)
  - Tier 3 — Direct REST API + skill 29 reference files
  - Tier 4 — Playwright browser at app.gohighlevel.com (or client white-label URL)
  - Tier 5 — Codex Computer Use (`codex/gpt-5.5`, 45-min default timeout)
- **`$GHL_COMMUNITY_MCP_URL` env var**: Added to `openclaw.json` `env.vars`. Removes the agent's ability to hardcode wrong port numbers. Documented past failures (port 8000 vs 8765 confusion with Cognee) eliminated by design.
- **Cardinal rules in SOUL.md template** (deployed via `CORE_UPDATES.md`):
  - Tier order is binding — no skipping
  - Session memory is not authoritative — the canonical state block in AGENTS.md is
  - Mandatory `[GHL tier used: N — tool_name]` disclosure header on every GHL response
  - "It looked broken earlier" is not an excuse — recover (kickstart / systemctl restart) before falling through
- **launchd plist (macOS)** at `~/Library/LaunchAgents/com.clawd.ghl-mcp.plist` — auto-starts at login, restarts on crash, no Docker dependency
- **systemd unit (Linux/VPS)** at `/etc/systemd/system/ghl-mcp.service` — same lifecycle guarantees as launchd
- **20-assertion QC script** (`qc-ghl-setup.sh`): Bundled in skill 36's QC.md. Exits 0 only when all checks pass. Required gate before declaring setup complete.
- **Canonical state block** in AGENTS.md template: Tier 2 URL/port/health endpoint listed as authoritative; overrides stale session memory.
- **Anti-pattern enforcement block** citing two documented failures (2026-05-12): (1) skipping Tier 2 for products query, (2) hardcoding port 8000 instead of using `$GHL_COMMUNITY_MCP_URL`.
- **Tool name reference tables** for both MCPs in TOOLS.md template: contacts (Tier 1), products/invoices/subscriptions (Tier 2), Voice AI / Phone System / Agent Studio (Tier 2 new in BusyBee fork).

### Changed
- **Skill 05 (`05-ghl-setup`)**: Credential canonical path migrated from `~/clawd/secrets/.env` to `~/.openclaw/secrets/.env` (Mac) / `/data/.openclaw/secrets/.env` (VPS) to align with current AGENTS.md operating rules. Updated CORE_UPDATES.md, INSTALL.md, QC.md. Added cross-reference banner at top of SKILL.md pointing to skill 36 for MCP-based access.
- **Skill 29 (`29-ghl-convert-and-flow`)**: SKILL.md now explicitly identifies itself as **Tier 3** of the 5-tier chain. Banner at top points readers to skill 36 for the MCP layer (Tiers 1 and 2).
- **Skill 35 (`35-social-media-planner`)**: CORE_UPDATES.md adds MCP-first routing guidance — all GHL operations (social posting, blog publish, media upload, campaign scheduling) check `social-media-posting_create-post` (Tier 1) and `create_social_post` (Tier 2) before falling to the direct Social Planner API.
- **README skill inventory fully resynced**: Previous inventory was stale — listed `32-blackceo-voice-call-plugin` instead of actual `32-command-center-setup`, missed `34-intelligent-staffing-ARCHIVED`, had formatting issues on `35-social-media-planner` row. Now matches real on-disk folders (01-36, with 13/33/34 archived).
- **ONBOARDING_VERSION**: Bumped to v9.0.0 in install.sh and update-skills.sh
- **version file**: Bumped to v9.0.0 in both Mac and VPS repos

### Notes
- Both repos (Mac onboarding + VPS onboarding) ship skill 36 identically. Platform differences (`~/Downloads` vs `/data/Downloads`, launchd vs systemd) are handled by conditional logic inside the skill's INSTALL.md and QC script.
- Skill 36 has no destructive interactions with existing skills — only adds cross-reference banners to 05 and 29, and adds MCP-first guidance to 35. Original skill behavior is preserved as fallback.
- The PIT and Location ID used by skill 36 are the same as those used by skill 05 and skill 29 — no second credential exchange required.

---

## v8.8.2 - April 25, 2026 - Update System Overhaul

### Fixed
- **update-skills.sh**: Complete rewrite with dependency checks, dry-run mode, deprecated model detection
- **Error handling**: Added rollback on failure, better logging, verification after applying updates
- **deprecated-models.json**: Added for tracking model deprecation across updates
- **.onboarding-version**: Added creation during update process
- **Telegram notification**: improved with new/updated skill lists

### Changed
- **ONBOARDING_VERSION**: Bumped to v8.8.2 in install.sh and update-skills.sh

---

## v8.8.1 - April 25, 2026 - Superpowers Install Method Fix

### Fixed
- **Superpowers INSTALL.md**: Made git clone the ONLY recommended method for downloading superpowers
  - Method A (git clone) now clearly marked as the only recommended method
  - Method C (curl individual files) marked as NOT RECOMMENDED - misses 20+ companion files
  - Added list of missing files: brainstorm server scripts, test files, platform tool references
  - Updated skill-version.txt to v5.0.7 (upstream superpowers version)

### Changed
- **ONBOARDING_VERSION**: Bumped to v8.8.1 in install.sh and update-skills.sh

---

## v8.8.0 - April 14, 2026 - Active Memory (Layer 8) Configuration

### Added
- **Active Memory (Layer 8)**: Automatic configuration during install and update
  - `plugins.entries.active-memory` with enabled=true, agents=["main"], allowedChatTypes=["direct"]
  - `queryMode`: "recent", `promptStyle`: "balanced", `timeoutMs`: 15000, `maxSummaryChars`: 220
  - `plugins.slots.memory` set to "memory-core"
  - `agents.defaults.memorySearch.provider` set to "gemini"
- **install.sh**: New Step 7a "Configuring Active Memory (Layer 8)" runs after concurrency config
- **update-skills.sh**: Active Memory verification and auto-configuration if missing
- **UPDATE PENDING flag**: Added Active Memory verification to Phase B (Skill 31 activation)

### Changed
- **ONBOARDING_VERSION**: Bumped to v8.8.0 in install.sh and update-skills.sh
- **Completion checklist**: Added "Active Memory (Layer 8) configured and enabled" to both install and update flags

## v8.7.0 - April 14, 2026
- Install experience overhaul for 55+ client audience
- Sub-agent concurrency configured at install time (50 concurrent, 10 queue, 4 depth)
- Skill processing order in onboarding flag:
  Phase A: Install all skills in parallel (read + apply)
  Phase B: Activate foundation (Skill 31 memory, Skill 22 persona)
  Phase C: Activate interactive (Skill 35 social media)
  Phase D: Ready but waiting (Skill 23 interview not forced, Skill 32 Command Center waits for interview completion)
  Phase E: QC and report to client
- Workforce interview (Skill 23) is installed but NOT executed during onboarding. Client starts it when ready.
- Command Center (Skill 32) waits for interview completion
- Timeout reference: 600s simple, 900s complex, 1200s interactive, 1800s media production
- Clean progress output (6 steps, ~20 lines)
- All technical noise redirected to log file
- Silent credential discovery with alternate name matching across all .env files
- Credential scan results written into onboarding flag
- Removed all credential warnings from install output
- Clear completion message with exact next steps
- Fixed bash 3.2 compatibility (no declare -A)
- All arrays initialized before use
- Telegram notification includes follow-up trigger


## v8.6.0 - April 14, 2026 - Skill 35 v1.4.0 Video Pipeline

### Updated
- **Skill 35 Social Media Planner v1.4.0**: Full video production pipeline (kie.ai Veo + FFmpeg crossfades/post-processing), 8-platform video posting (Facebook/Instagram/LinkedIn/YouTube/TikTok/Pinterest/Threads/X), HTML email newsletters, scaled to 15 production sub-agents + 6 QC agents, Podbean podcast publishing

## v8.4.0 - April 13, 2026 - Skill Activation Instructions Fix

### Fixed
- **FIX 1: update-skills.sh NEW skill processing**: Added explicit 6-step activation protocol that prints when a new skill is detected during update
  - a. READ all files (Teach Yourself Protocol)
  - b. CHECK prerequisites, search .env files
  - c. EXECUTE setup (different from reading!)
  - d. APPLY CORE_UPDATES.md surgically
  - e. RUN QC.md checks
  - f. TELL client what was set up
  - Added explicit note: "Teach Yourself means READ. Activate means EXECUTE."
- **FIX 2: Skill 35 INSTALL.md**: Added ACTIVATION section with 8 steps
  1. CREATE Google Sheet via webhook
  2. ASK client (videos, action link)
  3. ASK about podcast (skip-but-keep-asking)
  4. SEARCH .env for GHL credentials
  5. ADD heartbeat to HEARTBEAT.md
  6. APPLY CORE_UPDATES.md
  7. RUN QC.md checks
  8. CONFIRM to client
- **FIX 3: Skill 35 SKILL.md**: Added "⚠️ ACTIVATION REQUIRED" callout right after Teach Yourself Protocol section
- **FIX 4: Other skills with setup steps**: Added ACTIVATION sections to:
  - Skill 22: Gemini scripts to workspace
  - Skill 23: Interview run/resume with build-workforce.py
  - Skill 31: DREAMS.md + active-memory config
  - Skill 32: Command Center install + tunnel
  - Each includes: Prerequisites, Teach Yourself, ACTIVATION, Verification sections
- **FIX 5: Version bump**
  - Skill 35: v1.1.0 → v1.2.0
  - Repo: v8.3.0 → v8.4.0 (both Mac and VPS)
  - Updated install.sh headers
  - Updated update-skills.sh headers

## v8.3.0 - April 13, 2026 - Skill 35: Google Sheet Webhook Integration

### Changed
- **Skill 35 (Social Media Planner)**: Updated to v1.1.0
  - Google Sheet creation now uses n8n webhook instead of Google Workspace API
  - Webhook: `POST https://main.blackceoautomations.com/webhook/social-planner-sheet-create`
  - Fields: `brandName`, `clientEmail` → Response: `sheetUrl`, `sheetId`, `sheetName`
  - No client credentials required for sheet creation
  - Updated playbook.md, SKILL.md, INSTALL.md, CORE_UPDATES.md, README.md, QC.md
  - Added Google Sheet Verification checklist to QC.md
- Bumped ONBOARDING_VERSION to v8.3.0

## v8.2.1 - April 13, 2026 - Comprehensive Repo Instruction Fixes
- Added SOURCE OF TRUTH rule to Start Here.md (both repos) - skill files are authority over generic docs
- Added SOURCE OF TRUTH header to Skill 31 (both repos) - all 8 layers required, DREAMS.md required
- Rewrote UPDATE PENDING flag with EXECUTION MODE - do not ask permission, just execute
- Added 9-step processing protocol: search data → interview detection → process skills → verify memory → verify persona → cleanup config → surgical updates → report → cleanup
- Added smart credential discovery - searches all .env files, syncs to canonical location
- Added Gemini scripts copy logic - copies gemini-indexer.py and gemini-search.py to workspace
- Fixed read -p with /dev/tty in update-skills.sh
- Verified skill-version.txt files clean (v6.5.7) in Skills 22 and 23
- Verified Skill 35 exists on GitHub
- Added discover_skills_dir function for old install migration
- Bumped version to v8.2.1

## v8.2.0 - April 13, 2026 (Update System Fix Applied)
- Fixed install.sh and update-skills.sh: dynamic skill discovery, applies updates instead of staging, surgical core .md handling, real Telegram messages, full UPDATE PENDING instructions, flag auto-removal after processing

## v8.2.0 - April 13, 2026
- Added Skill 35: Social Media Planner
  - 7-part weekly content series across 6 platforms
  - 8 parallel sub-agents for production
  - 40+ QC checks across 8 categories
  - GoHighLevel Social Planner API (Private Integration Token) for posting and commenting
  - Image generation via kie.ai Nano Banana 2
  - Video via kie.ai Veo 3.1 Lite + FFmpeg
  - Podcast via Fish Audio S2, published through n8n webhook to Podbean
  - Persona integration with 5-layer alignment and client override option
  - Memory-core integration for theme and performance tracking
  - Podcast cover images: JPEG/PNG only, under 500 KB

## v8.1.0 - April 13, 2026 - Platform Architecture Playbook v1.0

### Overview
Release adds the missing platform version-detection architecture so client Sunday update checks can reliably detect and apply a new onboarding release.

### Fixed
- **install.sh version detection**: Moved the repo version sync check to run after `ONBOARDING_DIR` is defined so `set -u` does not hit an unbound variable before the installer can compare versions
- **Release bookkeeping**: Added the missing changelog entry for the v8.1.0 platform architecture release

### Added
- **VERSION-ARCHITECTURE.md**: Documents publisher-side vs client-side version truth, `.onboarding-version`, `.skill-manifest.json`, and rollback behavior
- **scripts/generate-manifest.sh**: Standalone generator for `~/.openclaw/skills/.skill-manifest.json`
- **install.sh manifest generation**: Installer now writes `.skill-manifest.json` after install

### Changed
- **install.sh**: Keeps `ONBOARDING_VERSION` aligned with the repo `version` file and verifies the installed `.onboarding-version` at the end of install
- **scripts/update-skills.sh**: Rewritten as a full safe updater with staged download, version comparison, per-skill diffing, changelog display, risk assessment, backup, confirmation gate, apply, manifest regeneration, logging, Telegram notification, and UPDATE PENDING flag handling
- **Version**: Root `version` and `install.sh` `ONBOARDING_VERSION` bumped to `v8.1.0`

---

## v8.0.0 - April 12-13, 2026 - BlackCEO System Overhaul v3.3

### Overview
Major overhaul addressing 29 broken items across 6 workstreams (Personas, Workforce, Kanban, Performance, Deployment, Hygiene). All items verified via QC Pass 1 + Pass 2 with exact grep commands.

### Changed
- **Skill 22**: Replaced hardcoded PERSONA_DETAILS with runtime persona-categories.json loader; added category filtering, auto re-index, auto persona-categories.json update; added anti-staleness guards; added post-task persona verification; added Memory Wiki integration
- **Skill 23**: Fixed determine_specialists() to populate actual roles; added create_role_workspace() with SOP stubs; added Devil's Advocate SOUL.md + SOP.md generation; added persona-matrix.md auto-generation; added deeper interview questions; added "I don't know" 6-step flow; added 1800s timeout override; added Memory Wiki integration
- **Skill 32**: Updated tunnel documentation for token-in-response n8n webhook; all port references confirmed 4000; create-tunnel.sh created in Command Center
- **Command Center**: Replaced hardcoded PERSONA_DETAILS with runtime loader; added grade-calculator.ts (40/30/15/15 formula); wired company-config.json; created DepartmentBrowser.tsx (sidebar + Kanban); created /ceo-board/[dept]/focus/ view; fixed task API department filtering; added Breadcrumb component to all pages; unified /workspace/ and /ceo-board/ route families; added "Business KPIs" / "Agent Performance" / "Proactive Intelligence" lens labels; replaced synthetic data with real API calls
- **All skills**: Fixed 303 hardcoded ~/clawd/ paths to ~/.openclaw/workspace/ or relative paths
- **Documentation**: All port references standardized to 4000 across 11 files

### Added
- department-naming-map.json (17 canonical departments, both repos)
- persona-selection-log.md template
- resolve-department.ts (shared department resolution)
- PRD.md, CHECKLIST.md (Command Center)
- DECISION-LOG.md (overhaul decisions)
- create-tunnel.sh (Command Center)

### Removed
- Hardcoded PERSONA_DETAILS map (~40 entries) from Command Center
- Synthetic/seeded placeholder data from CEO Board components
- Hardcoded ~/clawd/ paths from all client-facing skill documentation

### QC Scores
- A (Personas): 10/10 | B (Workforce): 9.2/10 | C (Kanban): 9.8/10
- D (Performance): 9.5/10 | E (Deployment): 9.8/10 | F (Hygiene): 8.5/10

---

## v6.5.31 - April 12, 2026 - Memory Architecture Migration v2.0

### Changed
- Skill 31: Upgraded from 5-layer to 8-layer memory architecture
- Skill 31: Replaced Mem0 (openclaw-mem0) with memory-core as active memory slot
- Skill 31: Added Layer 6 (Cognee), Layer 7 (Memory Wiki), Layer 8 (Active Memory)
- Skill 22: Added Memory Wiki integration for persona blueprint governance
- Skill 23: Added wiki compilation step to Interview Persistence Protocol
- Skill 32: Updated prerequisites, added wiki query capability
- All skills: Updated for memory-core compatibility
- All skills: Fixed Universal Path Rule violations (~/clawd/ → standard paths)

### Added
- Skill 31: MIGRATION-FROM-MEM0.md for existing Mem0 users
- Skill 31: Obsidian check and wiki renderMode selection
- Memory Surgery Playbook v3.5 implementation

### Removed
- All skills: Removed all references to openclaw-mem0 / Mem0 (except migration guides)

## v6.5.26 - April 3, 2026

### Merged
- **fix/skill22-auto-reindex**: Merged branch containing Skill 22 Phase 5 auto-reindex functionality for automated persona index refresh after synthesis.
- **fix/skill23-department-write-path**: Merged branch containing Skill 23 Mac backport parity with `--non-interactive` flag and `build_from_config()`.

### Changed
- **version**: Bumped to v6.5.26
- **ONBOARDING_VERSION**: Updated install.sh header to v6.5.26

---

## v6.5.25 - April 3, 2026

### Fixed
- **Skill 23 - Mac backport parity**: Backported VPS v2.1.0 functionality to Mac. Added `--non-interactive` flag and `build_from_config()` for automated `departments.json` generation in Skill 23.

### Changed
- **version**: Bumped to v6.5.25
- **ONBOARDING_VERSION**: Updated install.sh header to v6.5.25

---

## v6.5.24 - April 3, 2026

### Added
- **Skill 22 - Phase 5 auto-reindex**: Added Phase 5 auto-reindex after persona generation in orchestrator.py so the Gemini persona index is refreshed automatically after synthesis.

### Changed
- **version**: Bumped to v6.5.24
- **ONBOARDING_VERSION**: Updated install.sh header to v6.5.24

---

## v6.5.23 - April 3, 2026

### Fixed
- **install.sh - Agent message visibility**: Fixed bug where Telegram confirmation told users to "send your agent the message shown in your terminal" but the terminal never printed the exact message. Added clearly formatted "📋 SEND THIS MESSAGE TO YOUR AGENT" block to terminal output. Updated Telegram confirmation message to include the actual text instead of referencing the terminal.

### Changed
- **version**: Bumped to v6.5.23
- **ONBOARDING_VERSION**: Updated install.sh header to v6.5.23

---

## v6.5.22 - April 1, 2026

### Added
- **QC.md - Skill-specific checklists**: Added comprehensive QC.md files for all 34 skills with skill-specific criteria. Each QC.md includes:
  - Purpose statement tailored to the skill
  - Installation checks (folder existence, SKILL.md, INSTALL.md)
  - Dependency checks (specific packages, CLIs, API keys per skill)
  - Smart key detection with name variations (e.g., OPENROUTER_API_KEY, OPENROUTER_KEY)
  - 3-5 functional tests specific to what each skill does
  - QC scoring framework with 8.5/10 minimum passing score
  - QC loop rule (max 5 retry attempts)
- **QC.md - Mac/VPS parity**: Ensured QC.md files are synchronized between Mac and VPS repositories with platform-specific path adjustments

### Changed
- **version**: Bumped to v6.5.22
- **ONBOARDING_VERSION**: Updated install.sh header to v6.5.22

---

## v6.5.21 - April 1, 2026

### Fixed
- **install.sh - Smart skill discovery**: Fixed critical bug where installer counted skills from `skills/` subdirectory (only 3 .skill packages) instead of root (34 numbered skill folders). Added `discover_skills()` function that searches multiple locations (numbered folders, SKILL.md files, installed skills) and returns the highest count. Replaced hardcoded `ls | grep | wc -l` with smart discovery. Added diagnostic output showing skills source/destination paths at start and final count at end.
- **install.sh - Telegram notification**: Removed "Reply YES when ready to proceed." from client-facing Telegram message. This was developer scaffolding that should not appear in production notifications.

### Changed
- **version**: Bumped to v6.5.21
- **ONBOARDING_VERSION**: Updated install.sh header to v6.5.21

---

## v6.5.20 - April 1, 2026

### Added
- **install.sh - Post-install skill summary**: Added terminal output showing every skill installed/updated with name, description from SKILL.md, and QC rating (PASS/FAIL)
- **install.sh - Untouched skills list**: Shows skills that were left unchanged (already at latest version)
- **install.sh - OpenRouter model check**: Automatically fetches new free models from OpenRouter API and adds them to client's models map. Never touches primary model, never removes existing models.
- **install.sh - Telegram summary**: Sends concise install summary to client's Telegram after completion

### Changed
- **version**: Bumped to v6.5.20
- **ONBOARDING_VERSION**: Updated install.sh header to v6.5.20

---

## v6.5.19 - April 1, 2026

### Fixed
- **markitdown-skill**: Added missing SKILL.md and INSTALL.md files to the empty markitdown-skill folder. This was blocking client installs with "empty source folder" error.

### Changed
- **version**: Bumped to v6.5.19
- **ONBOARDING_VERSION**: Updated install.sh header to v6.5.19

---

## v6.5.18 - April 1, 2026

### Fixed
- **install.sh - backup_config_file() protocol compliance**: Fixed backup_config_file() to save backups to ~/Downloads/openclaw-backups/ with .txt extension per AGENTS.md protocol. Previously backed up to same directory as original with .bak-timestamp extension.
- **install.sh - Skill count reporting**: Fixed misleading Telegram progress message that reported skills extracted to "OpenClaw" (ambiguous) instead of specifying the actual path `~/.openclaw/onboarding/`. Added Step 3a to copy .skill packages from the skills/ subdirectory to `~/.openclaw/skills/` so the agent finds skills in the expected location. Prevents "only 3 skills found" confusion caused by empty skills directory.

### Changed
- **version**: Bumped to v6.5.18
- **ONBOARDING_VERSION**: Updated install.sh header to v6.5.18

---

## v6.5.17 - April 1, 2026

### Added
- **install.sh - UPDATE_PENDING flag mechanism**: Added `write_update_pending_flag()` function that writes an UPDATE_PENDING section to AGENTS.md at the end of every install/update. This ensures the agent detects and processes updates on next boot.
- **install.sh - Exact agent message restored**: Terminal and Telegram messages now show the exact message: "You have just received an OpenClaw update. Read the UPDATE_PENDING section in your AGENTS.md, process it, confirm you are ready, then remove the UPDATE_PENDING section from your AGENTS.md."

### Changed
- **version**: Bumped to v6.5.17
- **ONBOARDING_VERSION**: Updated install.sh header to v6.5.17

---

## v6.5.16 - April 1, 2026

### Added
- **install.sh - Mandatory backup-before-edit protocol**: Added `backup_config_file()` function that creates timestamped backups before any openclaw.json or exec-approvals.json edit
- **install.sh - Docs verification comments**: Added schema verification comments to all config write blocks referencing docs.openclaw.ai
- **install.sh - Backup calls**: Added backup_config_file calls before all config file modifications

### Fixed
- **install.sh - Exec security unconditional application**: Added `apply_exec_security_config()` function that runs at the end of every installer execution (both fresh install AND update). Previously, exec security config was only inside Step 3c which could be skipped if openclaw.json didn't exist yet. Now exec security is applied unconditionally after all skill installs.

### Changed
- **version**: Bumped to v6.5.16
- **ONBOARDING_VERSION**: Updated install.sh header to v6.5.16

---

## v6.5.15 - April 1, 2026

### Changed
- **install.sh - Exec security comments**: Updated doc-reference comments for tools.exec and exec-approvals.json sections to cite https://docs.openclaw.ai/tools/exec-approvals as the source of truth
- **install.sh - Re-verify note**: Added explicit comment reminding to re-verify exec security config if OpenClaw version is bumped
- **version**: Bumped to v6.5.15
- **ONBOARDING_VERSION**: Updated install.sh header to v6.5.15

---

## v6.5.13 - April 1, 2026

### Fixed
- **install.sh - send_telegram_progress function**: Replaced the broken function that had no `--target` or `--channel` flags. The old version silently failed on every fresh install because there was no active Telegram session and no recipient specified. The new version reads the client's Telegram chat ID from `openclaw.json` allowFrom list via python3, passes it explicitly via `--target` and `--channel telegram`, and falls back to terminal output if the ID can't be found or the send fails.

### Changed
- **version**: Bumped to v6.5.13
- **ONBOARDING_VERSION**: Updated install.sh header to v6.5.13

---

## v6.5.12 - April 1, 2026

### Fixed
- **install.sh - Gateway restart instruction**: Replaced the Done section with a clear two-step restart flow. Terminal output now shows STEP 1 (restart the gateway) and STEP 2 (send the onboarding message after restart). Without a restart, the agent won't see the ONBOARDING PENDING flag for up to 30 minutes.
- **install.sh - Telegram timing**: Moved send_telegram_progress call to BEFORE the terminal output block so the notification fires before the script completes. Updated the Telegram message to include restart instructions (`/restart`) and the exact message to send after restart. Previously the Telegram fired silently and the client was never told to restart.

### Changed
- **version**: Bumped to v6.5.12
- **ONBOARDING_VERSION**: Updated install.sh header to v6.5.12

---

## v6.5.11 - April 1, 2026

### Fixed
- **install.sh - Primary model protection**: Sub-agent model config now checks for existing `agents.defaults.subagents.model.primary` before writing. If the client already has a primary model set, it is preserved exactly. Only sets the default (`openrouter/google/gemini-3.1-flash-lite-preview`) on fresh installs. Prevents overwriting client-customized model choices on re-runs.
- **install.sh - ONBOARDING_FLAG heredoc**: Added critical wave ordering rule: Skill 12 (openrouter-setup) MUST be installed first in Wave 1 before any other skill. Other skills spawn sub-agents that need OpenRouter configured first. Skipping or delaying Skill 12 causes cascading sub-agent failures.
- **install.sh - ONBOARDING_FLAG heredoc**: Added MiMo V2 Pro thinking level rule. Main agent uses medium (default). All sub-agents spawned via sessions_spawn() must explicitly pass `thinking: "high"`. Never rely on default thinking for sub-agents.

### Changed
- **version**: Bumped to v6.5.11
- **ONBOARDING_VERSION**: Updated install.sh header to v6.5.11 (was v6.5.6, out of sync)

---

## v6.5.10 - April 1, 2026

### Added
- Skill 31 (Upgraded Memory System): Added QC.md with quality control checks (mirrored from VPS v6.5.12)
- Skill 32 (Command Center Setup): Added QC.md with quality control checks (mirrored from VPS v6.5.12)


## v6.5.9 - April 1, 2026

### Changed
- Skill 12 (OpenRouter Setup): Removed openrouter/mistralai/mistral-small-creative (deprecated, end-of-life April 30, 2026)
- Skill 12 (OpenRouter Setup): Updated all routing guidance to use MiniMax M2.7 for writing/creative tasks
- Skill 12 (OpenRouter Setup): Removed all Mistral references from INSTALL.md, openrouter-setup-full.md, INSTRUCTIONS.md, EXAMPLES.md, QC.md

## v6.5.8 - April 1, 2026

### Changed
- Skill 12 (OpenRouter Setup): Removed openrouter/openai/gpt-5.2-codex, openrouter/openai/gpt-5-mini, openrouter/openai/gpt-5-nano from all config blocks, model lists, narrative references, and routing tables
- Skill 12 (OpenRouter Setup): Updated all routing guidance to use MiniMax M2.7 / MiMo V2 Pro / DeepSeek R1 Free as replacements
- Skill 12 (OpenRouter Setup): Fixed fallback order -- kimi-k2.5 now appears before nemotron in fallback chain

## v6.5.7 - April 1, 2026

### Changed
- Skill 12 (OpenRouter Setup): Removed all Anthropic model entries (claude-opus-4.6, claude-sonnet-4.6, claude-haiku-4.5)
- Skill 12 (OpenRouter Setup): Removed all Perplexity model entries (sonar-pro-search, sonar)
- Skill 12 (OpenRouter Setup): Added openrouter/openrouter/free model
- Skill 12 (OpenRouter Setup): Updated fallback chain order -- MiMo V2 Pro first, Gemini Flash Lite second, OpenRouter Free third, then remaining models
- Skill 12 (OpenRouter Setup): Updated primary model recommendation to openrouter/xiaomi/mimo-v2-pro for sub-agents
- Skill 12 (OpenRouter Setup): Updated all config JSON examples and bash blocks to reflect new model roster (19 models)
- Skill 12 (OpenRouter Setup): Updated INSTALL.md, openrouter-setup-full.md, EXAMPLES.md, INSTRUCTIONS.md, QC.md

# Changelog

All notable changes to the OpenClaw Onboarding package are documented here.

---

## v6.5.6 — April 1, 2026

### Added
- Per-skill version tracking: each skill folder now contains `skill-version.txt`
- update-skills.sh now compares per-skill versions before overwriting — prevents false "up to date" reports when a skill folder exists but is at an older version

### Fixed
- install.sh ONBOARDING_VERSION header updated from v6.1.9 to match actual repo version (v6.5.6)
- check-update-impact.sh and setup-weekly-update.sh version headers synced to v6.5.6

---

## v6.5.5 — April 1, 2026

### Fixed
- Skill 22 folder name references updated from `22-book-to-persona/` to `22-book-to-persona-coaching-leadership-system/` in all scripts and docs — prevents "directory not found" errors on fresh installs

---

## v6.5.4 — March 31, 2026

### Fixed
- **Version file sync**: Updated version file from v6.5.2 to v6.5.4 to match HEAD commit (0243586d). Version file was not bumped in v6.5.3 or v6.5.4 commits.

---
## v6.5.0 — March 31, 2026

### Fixed
- **Runtime persona wiring (AGENTS.md)**: Added Persona Operating Protocol to ~/clawd/AGENTS.md. Every department agent now reads governing-personas.md at task start and operates through that persona for the entire task. Applies to all 17 departments via symlinks.
- **Skill 23 INSTALL.md Phase 5-BUILD-B**: Added instruction to append Persona Operating Protocol to each department's AGENTS.md during setup.
- **Skill 32 INSTALL.md Phase 7.4**: Added Persona Runtime Test to verification phase. Agents must answer "What persona are you operating as and why?" with a reference to governing-personas.md. Fail = install incomplete.

## v6.5.1 — March 31, 2026

### Fixed (QC-driven, 8→10 round)
- **Skill 22**: Added gemini-search.py and gemini-indexer.py to pipeline/ directory within the skill folder. Fresh client installs no longer fail at Step 5b (QC: 8→10).
- **Skill 23**: Documented canonical departments.json path as ~/Downloads/openclaw-master-files/company-discovery/departments.json in both INSTALL.md and CORE_UPDATES.md. Absolute path, not relative (QC: 8→9.5).
- **Skill 23**: Graceful Skill 22 dependency -- Skill 23 no longer blocks if Skill 22 is not installed. Persona creation falls back to local files.
- **Skill 32**: Added 10 Telegram progress pings to INSTALL.md covering every long-running command (npm install, PM2, cloudflared tunnel, database seeding). Added 5-minute npm install timeout with retry fallback (QC: 8→9.5).
- **Skill 32 seed-workspaces.py**: Added canonical departments.json path as first search candidate. Handoff from Skill 23 to Skill 32 now airtight.

## v6.5.2 — March 31, 2026

### Added
- **Dynamic Persona Selection Engine**: Every agent now runs Gemini search + 5-layer alignment scoring before selecting a persona for a new task. No more static "always use Primary" behavior.
- **AGENTS.md**: Persona Operating Protocol now has 3 new steps: (1) Gemini Search finds top 3 candidates, (2) 5-Layer Alignment picks the winner, (3) Reason Log entry to daily memory/[date].md. Graceful fallback to governing-personas.md Primary if Gemini unavailable.
- **Skill 23 Phase 5-BUILD-B**: Dynamic persona selection engine with weighted scoring table (Owner Values 25%, Company Mission 25%, Business KPIs 20%, Dept KPIs 15%, Task Fit 15%).
- **Skill 32 Phase 7.5**: 3-layer runtime verification test — Search Evidence (did agent use Gemini?), 5-Layer Alignment (can agent explain reasoning?), Reason Log (did agent write to daily memory file?). FAIL conditions catch agents that always default to the same persona.
- **Phase numbering fix**: Renumbered duplicate Phase 7.4 in Skill 32 to 7.4/7.5/7.6.

## v6.5.3 — March 31, 2026

### Fixed (adversarial QC-driven fixes)
- **gemini-search.py**: Now returns parent folder names (e.g., "rackham-spin-selling") not bare filenames. Deduplicates by folder -- returns 3 DISTINCT personas not 3 chunks from same file. Clean error on empty input. Exit code 2 on missing API key (triggers AGENTS.md fallback).
- **gemini-indexer.py**: Exit code 2 (not sys.exit(1)) on missing API key for --status. Added --watch flag for auto-reindex on new book drop. Added --rotate-logs flag with 100-entry cap and archive rotation.
- **install.sh**: Scripts now copy to ~/clawd/scripts/ (correct path). Added gemini-search.py to copy (was missing). Removed hardcoded Cloudflare tunnel token (was exposed in public GitHub repo).
- **7 governing-personas.md**: Legal→Tawwab, WebDev→Clear, IT→Samit, Video→Kane, Audio→Grenny, Creative→Godin, AppDev→Clear. Daniel Miller: 5 depts → 1. Jim Collins: 3 depts → 1.
- **AGENTS.md**: Added weighted scoring rubric for 5-layer alignment (Owner Values 3x, Mission 2x, Biz KPIs 2x, Dept KPIs 1.5x, Task Fit 1x). Tie-breaking rule documented.
- **AGENTS.md + MEMORY.md**: Added permanent QC Execution Rule -- QC must run scripts not read docs. Any QC on a script requires 3 mandatory execution tests (valid input, empty input, missing API key).

---

## v6.4.0 — March 31, 2026

### Fixed
- **Skill 22 INSTALL.md**: Added Step 5b to deploy gemini-search.py and gemini-indexer.py to ~/clawd/scripts/ after indexing. Added graceful degradation when GOOGLE_API_KEY is missing (falls back to PERSONA-ROUTER.md, no sys.exit).
- **Skill 22 CORE_UPDATES.md**: Added mandatory re-indexing trigger to AGENTS.md section. When a new persona is added, agents must run gemini-indexer.py.
- **Skill 23 INSTALL.md**: Phase 5-PERSONA now requires explicit content in every governing-personas.md with gate check (grep verification). Phase 6 now has mandatory specialist folder creation (2+ role files per dept) and ORG-CHART.md creation, both with gate checks.
- **Skill 23 CORE_UPDATES.md**: Added Governing Personas Update Protocol to AGENTS.md section -- re-index, review assignments, update ORG-CHART.md when new books added.

---

## v6.3.0 — March 31, 2026

### Fixed
- **Skill 23 Phase 0a**: Replaced hard exit if Skill 22 missing with graceful degradation. Workforce build now proceeds with generic personas; client notified they can add custom personas later via Option C.
- **Skill 23 naming convention**: Removed all -dept suffix references from INSTALL.md (10 edits), CORE_UPDATES.md (1 edit). Standardized to no-suffix folder names matching build-workforce.py actual output.
- **Skill 32 INSTALL.md**: Removed -dept suffix from department folder references. Consistent with Skill 23.
- **Interview answer canonical path**: Canonicalized to ~/Downloads/openclaw-master-files/company-discovery/ across INSTALL.md and CORE_UPDATES.md (Skill 23). Removed 3 wrong path references.
- **Phase 5-PRE check path**: Fixed from ~/.openclaw/workspace/ to ~/clawd/departments/ in Skill 23 INSTALL.md.

---

## v6.2.0 — March 31, 2026

### Fixed
- **Command Center (Skill 32) integration with Skill 23**: seed-workspaces.py now scans ~/clawd/departments/ where Skill 23 writes departments. Strips -dept suffix from folder names. DB path corrected to ~/projects/command-center/.
- **Hardcoded "17 departments" removed**: INSTALL.md Phase 6.5 now uses dynamic count placeholder instead of hardcoded number.
- **Agent ID format unified**: Changed from cc/[name] to dept-[name] throughout INSTALL.md to match Skill 23 format. Updated Phase 4.2, 5.4, 7.2.
- **install.sh progress visibility**: Removed -s silent flag from curl. Added show_status() messages with time estimates before long operations. Added send_telegram_progress() notifications at 6 key steps.
- **Removed __pycache__** from version control, added .gitignore.

---

## v6.1.9 — March 31, 2026

### Fixed
- **update-skills.sh Telegram message**: No longer tells user to relay a message to the agent. Now simply says "restart your gateway, your agent will handle the rest." The agent auto-detects the UPDATE PENDING flag on boot.
- **update-skills.sh Terminal output**: Same fix. Agent auto-detects. No user message relay needed.

---

## v6.1.8 — March 31, 2026

### Fixed
- **update-skills.sh message**: Replaced vague "Review the update reports" with specific instruction pointing to /tmp/oc-update-notification.md and UPDATE-PLAYBOOK.md. Agent now knows exactly where to find update details and what to do with them.

---

## v6.1.7 — March 31, 2026

### Fixed
- **update-skills.sh Terminal output**: Always shows gateway restart command and agent message, regardless of Telegram send status. Previously only showed when Telegram failed.
- **update-skills.sh Telegram message**: Now includes "openclaw gateway restart" as Step 1 before the agent instruction. Previously did not tell users to restart.
- **update-skills.sh Telegram errors**: Now logs the actual Telegram API response and config status instead of silently hiding errors.

### Added
- **setup-weekly-update.sh**: Saturday 11:59 PM cron job — runs `npm update -g openclaw` to update OpenClaw CLI before Sunday onboarding check. Ensures config structures are validated against the latest OpenClaw version.
- **install.sh**: Sub-agent default model — sets `agents.defaults.subagents.model.primary` to `gemini-3.1-flash-lite-preview` so sub-agents use a cheaper model by default.
- **HEARTBEAT.md model check**: Step 1 now checks `openclaw --version` and validates config structures against the current OpenClaw version before making changes.

### Removed
- **Perplexity models from allow list**: OpenClaw no longer supports Perplexity as a model. Any `openrouter/perplexity/*` entries in the client's model allow list are now automatically removed during install and updates.

### Changed
- **install.sh**: Sync ALL client models to sub-agent allow list — scans entire openclaw.json for model references and adds them to agents.defaults.models. Sub-agents can use any model the client has configured, not just the 8 hardcoded core models.
- **UPDATE-PLAYBOOK.md Step 6**: Exhaustive credential search — now checks 10+ env file locations, 4 openclaw.json sections, system env, and shell variables before marking a credential as BLOCKED. Explicit warning: "Do NOT ask the client until you have searched ALL locations."
- **UPDATE-PLAYBOOK.md Step 4e**: Fixed maxChildrenPerAgent mismatch — was 10, corrected to 20 (consistent with install.sh and Step 4c).

### Added
- **HEARTBEAT.md**: Sunday 3 AM agent update check — agent reads changelog, sends Telegram summary, waits for approval, follows UPDATE-PLAYBOOK.md
- **HEARTBEAT.md**: OpenClaw model check — verifies client has latest models, researches docs.openclaw.ai and OpenClaw GitHub before any model changes
- **HEARTBEAT.md**: Post-update QC loop — QC all updated skills, spin up sub-agent to fix failures, re-QC, maximum 5 retries per skill
- **setup-weekly-update.sh**: Gateway restart after update staging — agent picks up UPDATE PENDING flag on boot instead of waiting for manual restart
- **setup-weekly-update.sh**: Smart restart — only restarts gateway if an update was actually staged (checks for flag file)

---

## [v6.1.6] - March 29, 2026

### Interview Persistence Protocol + Update Flow Fixes + Terminology
- **Skill 5 CORE_UPDATES.md**: Added GHL/PIT terminology. AGENTS.md and TOOLS.md sections now explain that GHL uses Private Integration Tokens, not API keys.
- **Skill 23 SKILL.md**: Added explicit "I Don't Know" Research Protocol. When client cannot answer, agent researches best practices tailored to their industry, goals, department, and role. Presents recommendation, waits for approval, logs with attribution.

#### Added
- **TERMINOLOGY.md**: New repo-root file defining GHL/Convert and Flow/GoHighLevel naming rules and Private Integration Token (PIT) terminology. Required reading for all agents.
- **Skill 23 SKILL.md**: Full Interview Persistence Protocol replacing one-line flush note. 4-step mandatory flush after every question (answer to disk first, handoff update, MEMORY.md progress, then next question). Boot-time resume logic with 4-tier fallback. Edge cases: skip/circle-back, answer corrections, stale handoffs (90+ days), crash recovery, resume triggers.
- **Skill 23 CORE_UPDATES.md**: Interview Resume Protocol section for AGENTS.md — boot-time check for incomplete interviews.

#### Changed
- **scripts/update-skills.sh**: v6.1.3. Now sends Telegram notification directly to paired user using botToken and allowFrom from openclaw.json. If Telegram fails, prints clear fallback box in Terminal with exact agent instruction. AGENTS.md flag still written as backup layer.
- **install.sh**: Auto-cleanup of misplaced config keys. If `subagents` or `allow` appear under top-level `models` (where they do not belong), they are deleted automatically. Prevents config validation errors on startup.
- **UPDATE-PLAYBOOK.md**: v6.1.3. Added explicit JSON paths for subagent config (`agents.defaults.subagents`) and model allow list (`agents.defaults.models`). Added TERMINOLOGY.md reference. Warns agents not to put subagents under `models`.
- **Start Here.md**: Added TERMINOLOGY.md reference.
- **All script headers**: Synced to 6.1.3.

#### Removed
- **Perplexity sonar models** from model allow list (install.sh, deprecated-models.json, UPDATE-PLAYBOOK.md). `openrouter/perplexity/sonar-pro-search` and `openrouter/perplexity/sonar` are web search tools, not models. Allow list is now 8 models.

#### Fixed
- Script version headers were out of sync with repo version file. All 3 scripts now match `version` file. New rule: every push must bump version + headers in same commit.
- UPDATE-PLAYBOOK.md told agents to add subagent config but did not specify the JSON path, causing agents to put keys in the wrong place (`models` instead of `agents.defaults`).

---

## [v6.1.0] - March 27, 2026 (Late Evening)

### Skill 23 Persistence Hardening + Version-Proof Update System + Notification Overhaul

#### Added
- **scripts/setup-weekly-update.sh**: v4.0 rewritten. Installs a Sunday 3:00 AM cron job that uses the GitHub-hosted curl command to stage updates. Version-proof: always pulls the latest updater from GitHub, never a stale local file.
- **Skill 23 templates/company-discovery/workforce-interview-answers.md**: Default interview answer template for guaranteed persistence.
- **Skill 23 templates/company-discovery/interview-handoff.md**: Resume state template for long-running interviews.

#### Changed
- **Skill 23 build-workforce.py**: Persistence hardened. `find_master_files_folder()` now guarantees a valid path and never returns None. If the normal path doesn't exist, it falls back to `~/clawd/data/company-discovery/` with explicit warning. `log_answer()` and `create_handoff()` now print success/error to stderr. No code path where an answer is silently dropped.
- **UPDATE-PLAYBOOK.md**: Overhauled to v2.0. Added STEP 16: Client Notification Protocol with 3-channel fallback (Telegram → email → SMS). Added 4 message templates (Update Found, Update Applied, Update Blocked, SMS Fallback). Added plain-English guidance on what "staged" means. Added fallback channel protocol with email subject lines and SMS templates. Method 1 updated to use GitHub-hosted curl bootstrap command.
- **scripts/update-skills.sh**: v4.0 rewritten. Now generates a client-friendly notification message at /tmp/oc-update-notification.md instead of just saying "update staged." The notification explains what was found, what it means, what will happen if they say yes, and what they need to do. AGENTS.md flag now points agent to the notification file.
- **Version file**: v6.0.7 -> v6.1.0

## [v6.0.7] - March 27, 2026

### Persona Matching Protocol + Skill 32 Token-in-Webhook Architecture

#### Added
- **persona-matching-protocol.md** (Skill 23): New reference document defining the 5-layer persona alignment check (Company Mission, Owner Values, Company Goals/KPIs, Department Goals/KPIs, Task Fit). Layers 1-2 run once at setup to create a pre-qualified pool. Layers 3-5 run fresh for every task. Personas are matched per-task at runtime, not statically assigned per department.
- **persona-categories.json** (Skill 22): 40 personas tagged with 12 domain categories (marketing, sales, leadership, finance, operations, communication, copywriting, mindset, productivity-systems, coaching, strategy-innovation, personal-development) and 6 perspective tags (african-american-experience, womens-challenges, mens-challenges, family-relationships, faith-spirituality, love-romantic-relationships). Category-filtered matching enables efficient search across large persona libraries.

#### Changed
- **Skill 23 INSTALL.md**: Persona alignment section rewritten. governing-personas.md is now a REFERENCE GUIDE in each role folder, not a static department assignment. Added 5-layer alignment description and runtime matching instructions.
- **Skill 23 SKILL.md**: Corrected persona-matching-protocol.md reference from "3-layer" to "5-layer" (matches the protocol document and all other references).
- **Skill 32 INSTALL.md Phase 6b**: Architecture rewritten. Tunnel token now returned directly in the webhook HTTP response (JSON: tunnelToken, subdomain, tunnelId). Agent captures token programmatically, saves to ~/.openclaw/.env, starts PM2, verifies URL. Trevor still receives a backup Telegram notification with the same token. No more manual token forwarding step.
- **Skill 32 INSTALL.md Phase 6b**: cloudflared installation now built into the process. Step 6b.2 installs cloudflared via brew (Mac) or curl (Linux) before the webhook call.
- **32-command-center-setup/scripts/create-tunnel.sh**: Complete rewrite. Reduced from 147 lines to 59. Removed Cloudflare API calls, credential file management, launchctl plist generation, local tunnel config. Added auto cloudflared install, webhook POST with token capture, PM2 process management, clean verification.

#### Removed
- **Skill 32**: Manual "Wait for Trevor's Token" step (6b.3). Token now comes in webhook response.
- **Skill 32**: Manual echo CLOUDFLARE_TUNNEL_TOKEN step. Replaced with automated grep/mv in script.
- **Skill 32 create-tunnel.sh**: All Cloudflare API code (account ID, bearer token, tunnel creation via API, credential file writing, config-command-center.yml generation, launchctl plist creation). Replaced by single webhook call.

## [v6.0.2] - March 25, 2026

### Update System Fix

#### Fixed
- **scripts/update-skills.sh**: Complete rewrite. Now stages updates to /tmp and creates .update-pending flag file. No longer attempts to apply changes directly — agent follows UPDATE-PLAYBOOK.md.
- **Version comparison bug**: Eliminated. Script now reads version files directly instead of parsing changelog headers.
- **scripts/deprecated-models.json**: New file. Single source of truth for required models, deprecated model replacements, and sub-agent configuration.
- **UPDATE-PLAYBOOK.md**: Step 4d now references deprecated-models.json. Step 4e added for sub-agent config check (maxSpawnDepth: 4, maxChildrenPerAgent: 10, maxConcurrent: 20).

#### Added
- MiMo V2 Pro (openrouter/xiaomi/mimo-v2-pro) to required model list
- MiMo V2 Omni (openrouter/xiaomi/mimo-v2-omni) to required model list
- Sub-agent config validation (4, 10, 20)
- .update-pending flag file mechanism (replaces AGENTS.md bloat)

#### Changed
- update-skills.sh no longer applies changes — it stages the update and the agent follows UPDATE-PLAYBOOK.md
- Deprecated minimax-m2.5 → minimax-m2.7 tracked in deprecated-models.json

## [v6.0.1] - March 22, 2026

### Bug Fixes - Install Sequence, Skill 15, Skill 22, Gemini Engine

#### Fixed
- **install.sh**: Gemini Engine script no longer runs indexer on empty directories. Step 3b now only copies script + installs python package. Indexing deferred to after Skill 22 adds books.
- **install.sh**: Step 3b API key search now checks ~/.openclaw/.env first (OpenClaw standard) instead of hardcoded ~/clawd/secrets/.env (Trevor-specific path).
- **install.sh**: Step 3c now also sets model allow list (9 models) alongside sub-agent concurrency settings.
- **install.sh**: Step 4 now creates ~/Downloads/openclaw-master-files/ folder (coaching-personas/personas + project-prds).
- **Start Here.md**: Added Step 2.5 (sub-agent concurrency + model allow list) between backup protocol and Step 3.
- **Start Here.md**: Removed stale Skill 13 dependency. Skill 14 now runs independently.
- **Start Here.md**: Removed Skill 13 from Agent C assignment and Wave 2 install loop.
- **Skill 15**: Hard-coded team Telegram IDs (Trevor: 5252140759, LeAnne: 6663821679, E.R. Spaulding: 6771245262) back into INSTALL.md and TEAM_CONFIG.md. Previous sub-agent replaced them with placeholders.
- **Skill 15**: Removed interactive Step 0 intake questions. Step 0 now loads pre-configured data from TEAM_CONFIG.md.
- **Skill 15**: Step 2 now verifies existing sub-agent settings instead of overwriting them.
- **Skill 22**: Added model fallback chain. Primary: Kimi K2.5 via OpenRouter, then MiMo V2 Pro, then Kimi via Moonshot, then GPT Codex, then Gemini/Sonnet.
- **Skill 22**: INSTALL.md Step 4 now checks which models are available instead of requiring Moonshot API key.
- **gemini-indexer.py**: Added --status, --init, --dry-run flags. Skips missing collections gracefully. Supports multiple collections.

## [v6.0.0] - March 22, 2026

### AI Workforce Blueprint v2.3 + Skills 33/34 Merge

#### Added
- **Skill 23**: Workspace creation with core file inheritance (SOUL.md unique, TOOLS.md/AGENTS.md/USER.md inherited from CEO workspace)
- **Skill 23**: Specialist determination function (permanent vs on-call classification)
- **Skill 23**: Persona alignment via 5-layer selection (Mission, Values, KPIs, Dept Goals, Task Fit)
- **Skill 23**: ORG-CHART.md generation with model assignments
- **Skill 23**: Command Center departments.json generation
- **Skill 23**: Config safety protocol (backup before openclaw.json edits)
- **Skill 23**: interview-handoff.md auto-creation and flush after every answer
- **Skill 23**: Model check (high reasoning required) at install start
- **Skill 23**: Hesitation detection with industry research fallback (Perplexity sonar-pro-search)
- **Skill 23**: Client stop/resume with interview-handoff.md save
- **Skill 23**: 10 industry examples in INSTRUCTIONS.md
- **Skill 22**: persona-categories.json (40 personas, 12 domain + 6 perspective tags)
- **Skill 22**: Category metadata per persona (domain_tags, business_stage, ideal_user)

#### Changed
- **Skill 23**: All files rewritten to v2.3 (Start Here, SKILL.md, INSTRUCTIONS.md, build-workforce.py, INSTALL.md, CORE_UPDATES.md)
- **Skill 23**: Options presented as A/B/C with plain English descriptions (no "permanent agent"/"sub-agent")
- **Skill 23**: Interview questions are dynamic (3-7 per department, not fixed 7 with jargon)
- **Skill 23**: Department count is dynamic (any number, not hardcoded 17)
- **Skill 23**: Forbidden jargon removed from all files (handoff, tech stack, SOP, KPI, etc.)

#### Archived
- **Skill 33**: Department Heads - merged into Skill 23 (create_department_workspace, generate_soul_md, add_agent_to_config)
- **Skill 34**: Intelligent Staffing - merged into Skill 23 (determine_specialists, persona alignment)

---

## [v5.5.2] - March 21, 2026

### Skill 3 Fix + Calibre Auto-Install

#### Fixed
- **Skill 3**: Case-insensitive Gemini detection for Mem0 provider
- **Skill 3**: Onboarding path detection for Intel vs Apple Silicon Macs
- **Skill 3**: Calibre auto-installation (brew install --cask calibre)
- **Skill 3**: Completion confirmation before proceeding

---

## [v5.5.1] - March 20, 2026

### QC Agent Roles + Cloudflare Manual Setup

#### Added
- **Skill 23**: QC-ROLES-MASTER.md - 34KB master reference for QC agents
- **Skill 23**: QC agent roles added to all 17 department suggested-roles files
- **Skill 32**: Phase 8 - Manual Cloudflare Tunnel Setup (9 subsections)

#### Changed
- **Skill 31**: Mem0 config switched from OpenAI to Gemini (LLM + embedder)
- **Skill 32**: Phase 6b clarified as agent-automated path

---

## [v5.5.0] - March 20, 2026

### Command Center v1.4.0 + Multi-Company

#### Added
- **Skill 34: Intelligent Workspace Staffing** - Auto-hire/fire based on workload
- Multi-company schema support in Command Center
- Per-department memory architecture
- 17 permanent department head agents (54 total agents)

#### Changed
- **Skill 32**: v1.4.0 with KPI forms, effectiveness tracking, execution queue
- **Skill 32**: Sparklines, model pills, benchmarks

---

## [v5.4.0] - March 19, 2026

### Command Center Setup

#### Added
- **Skill 32: Command Center Setup** - Activates AI workforce as live Command Center
- Persistent department agents with Telegram topics
- Visual Kanban dashboard at localhost:3000
- Cloudflare Tunnel auto-setup (Phase 6b)

#### Changed
- Unique hostname pattern: `[company-slug]-[shortid]`
- 5-layer memory verification requirement

---

## [v5.3.0] - March 19, 2026

### Department Heads

#### Added
- **Skill 33: Department Heads** - 17 department head agents with full SOPs
- Per-department workspace architecture
- AGENTS.md, MEMORY.md, TOOLS.md templates for each dept
- agents.list configuration for department orchestration

---

## [v5.2.0] - March 19, 2026

### Command Center v1.3.0

#### Added
- KPI submission forms
- Effectiveness tracking (agent task completion rates)
- Execution queue system
- Model pills and sparklines

---

## [v5.1.0] - March 19, 2026

### Command Center Setup (Initial)

#### Added
- **Skill 32: Command Center Setup** - Initial release
- Kanban board interface
- Department agent spawning
- Telegram topic integration

---

## [v5.0.0] - March 19, 2026

### Major Release: Memory System Upgrade, Google Workspace CLI, Migration Fixes

#### New Skills
- **Skill 31: Upgraded Memory System** - 5-layer memory architecture (markdown files, improved flush, session indexing, Gemini Embedding 2 search, Mem0 auto-capture)

#### Skill Rewrites
- **Skill 14: Google Workspace Integration** - Complete rewrite. Replaced google-api.js and gog with Google Workspace CLI (gws). Single tool for both Gmail and Workspace. 81 scopes preserved.

#### Bug Fixes
- **Skill 23: AI Workforce Blueprint** - Fixed: agent was skipping the 3 options (A, B, C) and going straight to questions. Added MANDATORY OPTION PRESENTATION rule.
- **Skill 15: BlackCEO Team Management** - Fixed: agent was not writing real Telegram IDs to memory files. Added enforcement block requiring real data, not placeholders.

#### Infrastructure
- **Legacy retrieval fully replaced** with Google Gemini Embedding 2 across all skills and scripts
- **Onboarding watchdog** added to Start Here.md: 10-minute stall detection, never-stop-early, progress reporting every 5 skills
- **Mandatory file reading** protocol: agent must read ALL .md files before installing any skill
- **CONTRIBUTING.md** added: checklist for adding/modifying skills and pushing updates
- **MIGRATION.md** rewritten with correct commands, env vars, and step-by-step instructions

#### Migration Notes
- Existing users on Google Embedding 2: run the migration steps in MIGRATION.md
- The weekly update script (Sundays 2AM) will detect the version change and flag it
- No automatic changes are applied without user approval

#### Total Skills: 31 (Skill 13 archived)

---

## [v4.0.1] - March 16, 2026

### Skill Restructure — Voice Call Plugin Removed, Fish Audio Renumbered

#### Changed
- **Skill 30 (Voice Call Plugin) REMOVED** — The `@openclaw/voice-call` plugin is an official OpenClaw npm package installed via `openclaw plugins install @openclaw/voice-call`. Having it as an onboarding skill caused double-install conflicts on machines where it was already installed. Clients install it manually after onboarding.
- **Skill 31 → Skill 30 (Fish Audio API Reference)** — Renumbered. Now the final skill. Standalone reference doc so the agent knows Fish Audio endpoints, parameters, and call patterns.
- **Old Skill 30 folder archived** as `30-blackceo-voice-call-plugin-ARCHIVED`
- **README and Start Here updated** to reflect new skill numbering

---

## [v4.0.0] - March 16, 2026

### Major Release — Department Restructure, Interdepartmental Communication, Persona Mapping, Surgical Updates

#### Skill Restructure
- **Removed Skill 30** (Voice Call Plugin) — voice-call plugin is installed via OpenClaw npm (`openclaw plugins install @openclaw/voice-call`), not via onboarding. Having it in onboarding caused double-install conflicts.
- **Renamed Skill 31 → Skill 30** — Fish Audio API Reference is now Skill 30 (standalone reference doc)
- **Total skills: 30** (was 31)

#### New Departments
- **graphics-dept** — NEW separate department for all static image/visual work (KIE.ai primary, Nano Banana, OpenAI images, FAL optional)
- **video-dept** — NEW separate department for all video production (KIE.ai video endpoints, ties to Skills 24-28)
- **audio-dept** — NEW separate department for the full audio lifecycle: generate, transcribe, process, deliver (KIE.ai audio/ElevenLabs/Suno endpoints, Fish Audio, Whisper local/cloud)
- **creative-dept restructured** — now ALL written content only ("If it starts as words, it starts here"). Covers copywriting, blog posts, speeches, keynotes, presentation scripts, PowerPoint content, podcast scripts, video scripts. Creative writes — other departments produce.

#### Suggested Roles Per Department
- Added `23-ai-workforce-blueprint/suggested-roles/` folder with 15 department files
- Each file includes: role names, what each role does, core SOPs to build, persona trait suggestions, interdepartmental relationships
- CRM Specialist role documented across multiple departments (sales, marketing, creative, billing, graphics, video, audio) with department-specific SOPs for each

#### Department Folder Organization
- All department folders now live inside `openclaw-master-files/my AI company departments/`
- Company discovery subfolder: `company-discovery/workforce-interview-answers.md` and `persona-alignment-notes.md`
- Daily company logs: `daily-company-logs/YYYY-MM-DD.md` with Gemini Engine integration

#### Interdepartmental Communication System
- Added `universal-sops/cross-dept-request-template.md` — standard format for all cross-dept requests
- Added `universal-sops/interdepartmental-communication-guidelines.md` — CC model (not approval model), direct dept-to-dept communication with master orchestrator awareness
- Added `03-Activity-Log-Template.md` — running daily log format for the master orchestrator
- Pre-built cross-dept workflow SOPs for common routes (Sales→Audio, Marketing→Graphics, Video→Audio, etc.)

#### Persona 4-Layer Alignment Protocol
- Added `universal-sops/persona-re-evaluation-protocol.md`
- 4 layers: Company Alignment → Owner/CEO Alignment → Role/Functional Alignment → Beliefs/Principles Alignment
- Both Layer 3 (what they DO) and Layer 4 (WHY they do it) must pass
- Re-evaluation triggers: company goals change, new dept added, owner priorities shift, role changes, persona underperforming

#### Weekly Auto-Update System (Rebuilt)
- `scripts/update-skills.sh` rebuilt with surgical logic: changelog-first, version comparison, gap analysis, impact rating
- `scripts/check-update-impact.sh` — helper for per-file risk assessment (LOW/MEDIUM/HIGH)
- `scripts/setup-weekly-update.sh` updated to v2.0
- Impact levels: LOW (auto-apply), MEDIUM (recommend + confirm), HIGH (recommend SKIP + show diff)
- NEVER overwrites: core .md files, company dept folders, custom SOPs
- NEVER triggers gateway restart — always instructs client with restart steps

#### AI Workforce Interview Improvements
- Context-first questioning: agent checks existing files before asking any question
- Cross-department learning: answers carry forward, reducing questions as interview progresses
- Running answers document: `company-discovery/workforce-interview-answers.md` (append-only)

#### Daily Company Log System
- Master orchestrator appends log entries in real time (not end of day)
- Concise single-line timestamped format: `HH:MM — Dept→Dept: action [JobID] ✅/🔄`
- Gemini Engine integration: previous day's log embedded every morning
- Annual archive: end of year move to `archive/YYYY/`, Gemini Engine embed archive

---

## [v3.0.0] - March 15, 2026

### Major Release — Voice System, Skill Quality, Model Fixes

#### Added
- **Skill 31: Fish Audio API Reference** — standalone Fish Audio skill for podcast, video narration, speeches, webinars, and all non-phone audio generation
- **Fish Audio S2 Voice Behavior SOP v3.0** — added to both Skill 30 (Voice Call) and Skill 31 (Fish Audio). Large TYP deep-reference document covering 8 parts: tag system, universal rules, phone call SOP, podcast SOP, AI decision logic, voice selection, master instruction blocks, and quick-reference cheat sheet. Do NOT load into core files — TYP required
- **CHANGELOG.md and README.md** — now present in both repos

#### Fixed
- **Skill count updated throughout**: all references to "29 skills" updated to "31 skills" (install.sh, AGENTS.md, Start Here.md, ONBOARDING PENDING flag)
- **OpenRouter model ID bugs**: `hunter-alpha` and `healer-alpha` now correctly use `openrouter/` prefix. Was causing "not a valid model ID" errors for all clients
- **NVIDIA Nemotron model ID**: fixed to include `:free` suffix — `nvidia/nemotron-3-super-120b-a12b:free`
- **ONBOARDING PENDING flag message**: corrected "29 skills" → "31 skills" in install.sh output
- **Skill quality improvements**: skills 03, 14, 21, 25, 27 all raised from below 8.5 to 8.5+ after targeted fixes

#### Changed
- **Version bump**: v2.4.0 → v3.0.0 (major release due to voice system additions)
- All 31 skills now score 8.5 or above on the 5-dimension evaluation rubric (Clarity, Completeness, Intent Preservation, Error Recovery, Size/Complexity)

---

## [v2.2.2] - March 12, 2026

### Added
- **SKILL INSTALLATION PROTOCOL** section in Start Here.md: mandatory 5-step protocol that agents must follow for every skill (01-29). Addresses agent shortcut-taking, incomplete TYP execution, and premature "done" declarations.
- **ZERO TOLERANCE SHORTCUTS** language explicitly forbids: "I'll read that later", "This looks similar", "I can skip this step", "Close enough", "The user probably wants".
- **Step-by-step verification requirements**: agents must list every .md file read, confirm step completion, and verify all success criteria before declaring a skill complete.
- **Anti-drift safeguards**: no global "done" until all 29 skills verified, no skipping "optional" skills, explicit checkpoint before ONBOARDING COMPLETE status.
- **GATEWAY RESTART PROTOCOL**: agents are forbidden from triggering gateway restarts autonomously. Must notify user and ask for explicit permission before any restart.
- **COMPLETE ALL DEPENDENCIES**: agents must complete every dependency, sub-task, and configuration step listed in skill docs. No partial installs.
- **OPENROUTER RULE**: agents are forbidden from changing user's primary model when installing OpenRouter. Install tooling only, inform user, offer help if asked.
- **MAIN ORCHESTRATOR ONLY SKILLS**: 22-book-to-persona-coaching-leadership-system and 23-ai-workforce-blueprint must be installed by main orchestrator only, never sub-agents.
- **GOOGLE WORKSPACE - SAVE FOR LAST**: Google Workspace skills (13/14) must be installed after all other skills due to complexity and user interaction requirements.
- **ONBOARDING FLOW PROTECTION**: For AI Workforce Blueprint, agent must notify user first and wait for explicit response before asking configuration questions.
- **MASTER FILES FOLDER DISCIPLINE**: Agent must check for existing master files folders first, use existing if found, create skill subfolders inside.
- **CORE.MD FILES PROTECTION**: Explicit list of core files (AGENTS.md, MEMORY.md, TOOLS.md, USER.md, IDENTITY.md, SOUL.md, HEARTBEAT.md) with TYP storage rules and conflict resolution.
- **Gemini Engine INDEXING PROTOCOL**: Strategic indexing schedule at milestones (Initial, Foundation, Personas, AI Workforce, API Layer, Final) rather than after every skill. Prevents redundant embeddings while ensuring searchability.

### Changed
- Updated install.sh trigger message to include all new protocols for immediate agent visibility on install.
- Updated AGENTS.md ONBOARDING PENDING flag to include all protocol references.

---

## [v2.2.1] - March 10, 2026

### Fixed
- Corrected onboarding install routing for API-driven skills so Vercel, Context7, and GitHub use browser + token/API flows during onboarding instead of service CLI setup.
- Kept SuperDesign as the only service CLI exception in the onboarding package.
- Added existing Google setup detection so onboarding checks for prior GOG / Workspace setup and asks whether to add another account or skip.
- Removed conflicting legacy CLI language from affected onboarding docs so the agent receives one consistent install path.

---

## [v2.2.0] - March 8, 2026

### Added
- **CLOUD / LINUX INSTALL NOTES section** in Start Here.md: fires automatically when Linux detected. Covers brew→apt-get, Playwright headless mode + --no-sandbox, master files folder path (~/openclaw-master-files/ instead of ~/Downloads/), xdg-open vs open, date command compatibility, shell defaults.
- **Universal browser session persistence rule** in Start Here.md: all three browser tools now enforce login-once persistent sessions. agent-browser uses `--session-name <skill-name>`, Playwright uses `launchPersistentContext`, OpenClaw browser uses `--browser-profile openclaw` (named Chrome profile, persistent by default).

### Fixed
- **OS check** now handles three scenarios: macOS (Darwin) full support, Linux proceeds with brew→apt substitution note, Windows/anything else stops with clear message.
- **Skill 13 (Google Workspace Setup)**:
  - Added CREDENTIAL CHECK block to both Path A and Path B: scans all ENV files first (workspace secrets/.env, ~/.openclaw/secrets/, openclaw.json, shell env), then offers Option A (agent logs in automatically) or Option B (user logs in manually in open browser). Both use persistent sessions.
  - Browser priority fixed: agent-browser first, Playwright fallback, OpenClaw browser last resort. Playwright was previously hardcoded throughout.
  - All 132 agent-browser commands updated with `--session-name google-setup` for persistent sessions.
  - All `~/clawd/` hardcoded paths replaced with `[WORKSPACE_ROOT]/` (24 occurrences).
  - Session detection added before first browser step in both paths.
- **Skill 06 (GHL Install Pages)**: Playwright `launch()` replaced with `launch_persistent_context` pointing to `~/.openclaw/playwright-data/ghl-install-pages/`.
- **Start Here.md gap analysis fixes** (12 categories):
  - Resume mechanism: .onboarding-status.json tracks per-skill status, agent resumes from last incomplete skill
  - Prerequisites: write permission check, 2 GB disk space check, workspace root auto-detection, messaging channel auto-detection, existing skills scan
  - Master files folder: search first, only ask if multiple candidates
  - Step 1 TYP: agent reads silently, no announcement
  - Step 9: report done + continue immediately, no waiting
  - Sub-agent dependency chain: 05→06, 13→14, 22→23 must stay sequential
  - API key: expanded scan + storage location + pending keys file
  - Network retry: up to 3x with 10-second delays
  - Progress updates every 5 skills
  - "28 skills" → "29 skills" throughout
  - Weekly update "Notify Trevor" → generic messaging channel
  - ONBOARDING PENDING flag removed from AGENTS.md on completion

---

## [v2.1.0] - March 8, 2026

### Added
- **install.sh**: One-command autonomous onboarding trigger. Run `curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash`. Downloads package, sets up backup folder, writes onboarding flag to AGENTS.md, fires agent trigger via `openclaw agent --message --deliver`. Zero human action after the curl command.
- **Skill 29 - GHL / Convert and Flow API v2**: Full API reference skill. 12 domain reference files covering 413 endpoints, 35 modules, 106 scopes. Contacts, conversations, calendars, payments, opportunities, locations, users, auth, campaigns, webhooks, phone-numbers. Proper `ghl-convert-and-flow/` archive root. Phone-numbers module includes TREVOR-ONLY safety warning (no autonomous release).
- **Weekly GitHub update check**: Added to Start Here.md. Every Sunday, agent pulls from `trevorotts1/openclaw-onboarding`, re-runs TYP on any changed skill, notifies via configured messaging channel.
- **Missing .skill archives built**: 03-agent-browser, 22-book-to-persona-coaching-leadership-system, 23-ai-workforce-blueprint were missing archives - all three rebuilt and verified.

### Fixed
- **Skill 02 (Back Yourself Up Protocol)**: All 5 files now consistently use `.txt` extension for backup files (was `.json` in EXAMPLES.md, INSTRUCTIONS.md, INSTALL.md, CORE_UPDATES.md - only back-yourself-up-protocol-full.md had it right). Default folder name standardized to `OpenClaw Backups`. Smart detection: if folder already exists, use it - never create a duplicate.
- **Skill 24 (Storyboard Writer)**: Fixed fatal `ModuleNotFoundError` crash - `create_storyboard.py` crashed when run from skill root due to missing `sys.path.insert(0, str(Path(__file__).resolve().parent))`. Added agent intake flow to SKILL.md.
- **Skill 25 (Video Creator)**: Fixed all `25-video-creator` path references to `video-creator/`. Removed `/tmp/openclaw-onboarding` hardcoded paths. Removed `BlackCEO Presents` branding from sample_script.txt. Removed `weekly_roundup` template reference (not shipped). Rebuilt archive with proper `video-creator/` root.
- **Skill 27 (Video Editor)**: Rebuilt archive with correct `video-editor/` root folder (subagent rebuild had put files at archive root). Fixed all `27-video-editor` path references. Cleaned BROLL-WORKFLOW.md (removed video2x, Telegram delivery section). Fixed ffmpeg-vs-moviepy.md command paths to include `scripts/` prefix.
- **Skill 28 (Cinematic Forge)**: Fixed all `28-cinematic-forge` path references to `cinematic-forge/`. Generalized `~/clawd/secrets/.env` reference. Removed "Tell your agent" / "master files directory" language from README.md.
- **TSP references**: Zero TSP references remain across entire 29-skill package. AGENTS.md and MEMORY.md updated to clarify TSP = TYP (identical, never correct user on this).
- **Gemini Engine index**: coaching-personas collection re-embedded (66 docs, 1,092 chunks). Broken symlink in clawd collection removed and resolved.

---

## [v1.7.0] - March 8, 2026

### Fixed (final polish pass - all skills to 10/10)
- Skill 22 SKILL.md: "skill 22" → "skill 23" in AI Workforce Blueprint connection section (lines 151 and 157)
- Skill 22 CORE_UPDATES.md: "Trevor" → "the user" in 2 places (portability for client delivery)
- Skill 22 INSTALL.md + CORE_UPDATES.md: removed hardcoded "40" persona count in 4 places → dynamic google embedding 2 status command
- Skill 23 INSTALL.md: added ai-workforce-blueprint-full.md file size verification after copy (truncation check)

---

## [v1.6.0] - March 8, 2026

### Changed
- **Skill 22 renamed**: "book-to-persona" → "Book To Persona & Coaching & Leadership System" per Trevor
- **Skill 23 confirmed**: "AI Workforce Blueprint" name confirmed

---

## [v1.5.0] - March 7, 2026

### Added
- **Skill 03 - Agent Browser (Vercel)**: Wrapper skill to ensure `agent-browser` is installed and available as the preferred browser automation tool.

### Changed
- **Renumbered skills 03 and up** to insert Agent Browser as Skill 03.
  - Example mapping: 03-superpowers -> 04-superpowers, 12-google-workspace-setup -> 13-google-workspace-setup, 21-book-to-persona -> 22-book-to-persona-coaching-leadership-system, 22-ai-workforce-blueprint -> 23-ai-workforce-blueprint.
- **All INSTALL.md files rewritten to be agent-executable** (autonomous execution). Removed "say to your AI" style instructions.
- **Google Workspace Setup**: major expansion and hardening
  - Added Gmail-only OAuth path (separate from Workspace service account path)
  - Browser automation hierarchy: agent-browser first, Playwright persistent context fallback, OpenClaw browser last resort
  - Added proactive recovery for org policy blocks on service account JSON key creation
  - Added automatic post-setup test and GOG setup after success
- **BlackCEO Team Management**: clarified isolation rules
  - Isolation means context and data isolation only
  - Communication is allowed when explicitly directed
- **Book To Persona & Coaching & Leadership System**: fixed step numbering and added pipeline execution test step
- **AI Workforce Blueprint**: rewrote INSTALL.md into a real multi-phase autonomous execution flow

---

## [v1.4.0] - March 7, 2026

### Added
- **Skill 22 - AI Workforce Blueprint**: Build the folder and file system that turns your AI into a trained workforce. Creates department folders, role folders, Start Here files, routing logic, and SOPs. Includes automated scaffold script (Option A), manual build guide (Option B), and resume/audit mode (Option C). Full 66,819-character blueprint document included.
- **Skill 21 - Book To Persona & Coaching & Leadership System**: Convert any book (PDF, EPUB, MOBI, AZW3) into a dual-purpose persona blueprint. 40 pre-built personas from bestselling books already included - no pipeline required for existing books. 3-phase pipeline: Kimi extract → DeepSeek analyze → Codex synthesize. PERSONA-ROUTER.md maps task types to personas and department folders. Gemini Engine integration for instant semantic search across all 447 persona documents (7,465 vectors).
- **Skill 20 - Tavily Search**: AI-optimized web search via Tavily API for deep research tasks.

---

## [v1.3.0] - March 3, 2026

### Added
- **Skill 19 - YouTube Watcher**: Fetch and read transcripts from YouTube videos.
- **Skill 18 - Humanizer**: Remove AI writing markers and make output sound natural.
- **Skill 17 - Proactive Agent**: WAL Protocol, Working Buffer, and autonomous cron support.
- **Skill 16 - Self-Improving Agent**: Capture learnings, errors, and corrections for continuous improvement.

---

## [v1.2.0] - March 1, 2026

### Added
- **Skill 15 - Summarize YouTube**: YouTube transcript extraction and summaries with OpenAI-first, Gemini-fallback key handling.
- **Skill 14 - BlackCEO Team Management**: Multi-person team management through Telegram with message routing and worker agents.

---

## [v1.1.0] - February 23, 2026

### Added
- **Skill 13 - Google Workspace Integration**: Deep technical guide - 70+ permission scopes, 26 APIs, Playwright persistent context, troubleshooting.
- **Skill 12 - Google Workspace Setup**: Google Cloud project, service account, and API connections for Gmail, Calendar, Drive.
- **Skill 11 - OpenRouter Setup**: Configure multiple AI models with intelligent routing and cost management.
- **Skill 10 - SuperDesign**: Design professional interfaces before building them.
- **Skill 09 - GitHub Setup**: Code backup, version control, and repository management.
- **Skill 08 - Context7**: Up-to-date documentation lookup for any software library.
- **Skill 07 - Vercel Setup**: Website and app deployment.
- **Skill 06 - KIE Setup**: AI image, video, and audio generation via KIE.ai.
- **Skill 05 - GHL Install Pages**: Deploy websites and landing pages into GoHighLevel.
- **Skill 04 - GHL Setup**: Connect to GoHighLevel for CRM, contacts, messaging, calendars.

---

## [v1.0.0] - January 28, 2026

### Initial Release
- **Skill 01 - Teach Yourself Protocol**: Foundation skill. Teaches the AI how to learn new skills without cluttering core files.
- **Skill 02 - Back Yourself Up Protocol**: Automatic config backups before every change.
- **Skill 03 - Superpowers**: 4 Iron Laws + 14 sub-skills for systematic problem-solving.
- README.md and Start Here.md included.

## v6.5.17 - 2026-04-01
### Fixed
- **install.sh - Auto-restart and Telegram confirmation**: Added automatic gateway restart at end of install. Previously, clients had to manually run `openclaw gateway restart`. Now the installer triggers the restart automatically and queues a Telegram confirmation message to be sent after the gateway comes back up. The notification uses a background process with an 8-second delay to ensure delivery after reconnect.

### Changed
- **version**: Bumped to v6.5.17
- **ONBOARDING_VERSION**: Updated install.sh header to v6.5.17

## v6.5.14 - 2026-04-01
- Set tools.exec security=full and ask=off in openclaw.json during install
- Write exec-approvals.json with askFallback=full — eliminates approval wall for autonomous agent operation
