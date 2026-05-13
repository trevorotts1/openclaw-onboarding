# INSTALL CONTRACT — Binding Discipline for Skill Installation

**Version:** v1.0.0 (v9.3.0 release)
**Status:** BINDING — every agent involved in installing or updating OpenClaw skills must read this file in full and follow it exactly. No exceptions.

This contract is referenced by:
- `install.sh` UPDATE PENDING flag
- `update-skills.sh` UPDATE PENDING flag
- `cron-prompt.txt` (Sunday weekly update orchestration)
- Each skill's `SKILL.md` and `INSTALL.md`
- Telegram-driven onboarding contracts (Blocks 2, 4, 6, 8 of `ONBOARDING-TRIGGERS.md`)

Reading this contract once at the start of an install session is necessary but NOT sufficient. **You must re-confirm adherence to it BEFORE each skill** by stating in your work log: *"INSTALL-CONTRACT.md acknowledged for skill NN-name. Proceeding."*

---

## 🔴 Rule 1 — Read every .md file in the skill folder BEFORE touching the system

Before you run a single command, write a single file, or call a single API, you must read the FULL TEXT of every `.md` file in the skill's folder:

- `SKILL.md` — what the skill is, when to use it, prerequisites
- `INSTALL.md` — the installation procedure
- `INSTRUCTIONS.md` — how to use the skill day-to-day (if present)
- `EXAMPLES.md` — real call patterns (if present)
- `CORE_UPDATES.md` — exact text to add to core files
- `QC.md` — quality control checklist + scoring rubric
- Any `references/*.md` files referenced by INSTALL.md (read only the specific module the install needs — do NOT load the full 413-endpoint master reference)
- `CHANGELOG.md` — what changed recently (helps you spot why an install might behave differently)

**Reading is not executing.** Reading puts the content into your context so you understand what you're about to do. Executing is the separate, deliberate act that comes after reading. Never skip the reading step.

---

## 🔴 Rule 2 — Follow INSTALL.md step order verbatim. No skipping. No reordering.

The step numbers in INSTALL.md are the order. If INSTALL.md says Step 1 → Step 2 → Step 3, you do exactly that order. Even if Step 2 "obviously" depends on Step 4 in your judgment, you do not reorder. If you genuinely believe a step is unnecessary or wrong, STOP and ask the owner — do not skip silently.

You may NOT:
- Skip a step because it "seems redundant"
- Skip a step because it "already happened"
- Reorder steps to "be more efficient"
- Add steps that aren't in INSTALL.md
- Combine steps that INSTALL.md lists separately

---

## 🔴 Rule 3 — Run the skill's QC.md after install. Score 8.5/10 or LOOP.

Every skill's QC.md has a 0–10 scoring rubric (v9.3.0 standard). After install, score yourself honestly against that rubric.

- **Score ≥ 8.5:** Pass. Skill is complete. Move to the next skill or wrap up.
- **Score < 8.5:** **DO NOT declare done.** Loop back, fix the specific items that lost points, re-score. Max 5 loops, then escalate.
- **Bundled `qc-*.sh` script present:** It must exit 0 in addition to the rubric scoring 8.5+. The script catches mechanical things the rubric assumes (file modes, env var formats, network reachability).

When looping:
1. Identify the exact rubric sections that scored low
2. Apply the smallest possible fix per section
3. Re-run only the failed checks (not the whole skill)
4. Re-score
5. After 5 loops, stop and escalate via Telegram to the owner with: which section scored what, what you tried, what's blocking

**Looping silently more than 5 times is a violation. Escalate.**

---

## 🔴 Rule 4 — No shortcuts. Period.

You may NEVER use these flags or commands during an install:

- `--force` (npm, git, etc.)
- `--break-system-packages` (pip)
- `--no-verify` (git commits, npm)
- `--no-gpg-sign` (git)
- Model name substitution (don't swap `kimi-k2.6` for `kimi-k2.5` because "I think the older one is more stable")
- Invented steps (don't add a step that's not in INSTALL.md)
- Destructive git ops without explicit owner consent: `git push --force`, `git reset --hard origin/main` (on shared branches), `git branch -D`
- `rm -rf` outside `/tmp/` or other clearly-scratch locations

If a flag is required to make something work, STOP and ask the owner. The flag might be the right answer; you still ask first.

---

## 🔴 Rule 5 — Sub-agents NEVER trigger a gateway restart

Only the master orchestrator can call `openclaw gateway restart`. Sub-agents that are installing skills, running QC, or doing repair work must NEVER call it directly.

The master orchestrator, before calling `openclaw gateway restart`, must:
1. Run `openclaw subagents list` and confirm the list is EMPTY (no active sub-agents)
2. If any sub-agents are active, WAIT for them to complete or cancel them first
3. Only then proceed with the restart

Restarting the gateway while sub-agents are working will kill their sessions and break the install. This is a hard rule with no exceptions.

If a sub-agent encounters a state that requires a gateway restart, it should:
1. Report the need to the master orchestrator
2. Pause its own work
3. Wait for the master to coordinate the restart with all other sub-agents
4. Resume after the restart completes

---

## 🔴 Rule 6 — Sub-agent failure handling

If a sub-agent fails (timeout, error, non-zero exit, hang):

1. **Retry once with the same model.** Many failures are transient.
2. **If second attempt fails, retry with the next fallback model** from `agents.defaults.subagents.model.fallbacks`.
3. **If third attempt fails, escalate to the master orchestrator.** The master may decide to do the skill itself, skip and continue, or stop and ask the owner.

Never silently abandon a sub-agent's task. Every failure must be either successfully retried, deliberately escalated, or explicitly skipped with owner consent.

---

## 🔴 Rule 7 — Search ALL credential locations before asking the owner

Before asking the owner for any credential, check ALL of these:

| Order | Location |
|-------|---|
| 1 | `~/.openclaw/secrets/.env` (Mac canonical) / `/data/.openclaw/secrets/.env` (VPS canonical) |
| 2 | `openclaw.json` `env.vars` |
| 3 | `~/clawd/secrets/.env` (Mac legacy — migrate if found) |
| 4 | `~/.env` |
| 5 | `printenv | grep <var-name>` (live process env) |
| 6 | Files matching `*.env*` in the workspace |

The agent SHOULD also detect DEPRECATED variable names and migrate them:
- `GHL_PRIVATE_TOKEN` → migrate to canonical `GOHIGHLEVEL_API_KEY`
- `GHL_API_KEY` → migrate to canonical `GOHIGHLEVEL_API_KEY` (same name happens to map; just confirm value is a PIT)
- `GHL_LOCATION_ID` → migrate to canonical `GOHIGHLEVEL_LOCATION_ID`
- `GHL_PIT` → migrate to canonical `GOHIGHLEVEL_API_KEY`

When the owner provides a credential, you write it to BOTH:
- The canonical secrets file (`~/.openclaw/secrets/.env` / `/data/.openclaw/secrets/.env`) with `chmod 600`
- `openclaw.json` `env.vars` (the gateway reads from here at runtime)

Never echo credentials into chat logs. Reference env-var names only.

---

## 🔴 Rule 8 — GHL alias awareness

These are all the same single platform:

- GHL
- GoHighLevel
- Go High Level (two words)
- HighLevel / High Level
- Convert and Flow (this owner's white-label brand)
- LeadConnector / leadconnectorhq.com (their API host domain)
- CnF (abbreviation)

When the owner uses any of these names, you respond in their language but you know they mean the same system: the same PIT, the same Location ID, the same MCPs (`ghl-mcp` and `ghl-community-mcp`), the same skill 36 / 35 / 29.

**GHL DOES NOT USE API KEYS.** They deprecated API keys ~2 years ago. GHL uses **Private Integration Tokens (PITs)**. The env variable `GOHIGHLEVEL_API_KEY` is a legacy variable name — its value is a PIT, not an API key. Never tell the owner they need an "API key" for GHL. They need a **Private Integration Token (PIT)**. Get it from GHL Settings → Integrations → Private Integrations.

---

## 🔴 Rule 8a — GHL rate-limit awareness (BINDING; documented past failure 2026-05-13)

GHL enforces per-location rate limits that apply to **all three tiers simultaneously** — Tier 1, Tier 2, and Tier 3 all hit the same backend bucket. Switching tiers does NOT bypass the limit. When the limit is hit, ALL THREE TIERS fail at once.

**The limits:**
- Burst: **100 requests per 10 seconds per location**
- Daily: **200,000 requests per day per location**

**Response headers on EVERY GHL response** (Tier 1 inside the SSE data, Tier 2 inside the wrapped response, Tier 3 direct):
- `X-RateLimit-Remaining` — burst budget left in the current 10s window
- `X-RateLimit-Daily-Remaining` — daily budget left until reset
- `X-RateLimit-Limit-Daily` — 200000 (the cap)
- `X-RateLimit-Daily-Reset` — seconds until daily quota resets

**Before any bulk operation** (loops, multi-fetch, polling, large list pulls):
1. Make ONE cheap probe call first (e.g. `locations_get-location` via Tier 1, or `tools/list`).
2. Parse `X-RateLimit-Daily-Remaining` from the response headers.
3. If less than **1000** remaining: STOP. Tell the owner in plain English: "Rate limit nearly exhausted — back in X hours (around HH:MM ET)." Compute `HH:MM ET` from `X-RateLimit-Daily-Reset`. Do NOT proceed.
4. If less than **5000** remaining: warn the owner and ask if they want to proceed with limit-aware batching.

**On 429 response** (regardless of which tier surfaced it — Tier 1 may wrap inside a 200 SSE, Tier 2 inside a 500, Tier 3 direct):
1. Parse `X-RateLimit-Daily-Reset` (seconds until reset).
2. Compute wall-clock reset time in the owner's local timezone.
3. Surface to owner: "Rate limited — back in X hours (around HH:MM ET on [date])."
4. NEVER retry blindly. NEVER fall through to a different tier (they all share the same bucket).
5. Log the incident to MEMORY.md under "## Rate Limit Incidents" with date, location ID, what was running when it burned (test loop / n8n / cron / agent re-fetch / etc.) so the root cause is fixable.

**Always batch:**
- Use `limit=100` page size on list endpoints rather than many small calls.
- Cache list results (products, invoices, contacts, transactions) in MEMORY.md for at least 5 minutes. Do NOT re-fetch the same data per agent turn.
- Polling intervals: minimum 60 seconds; minimum 5 minutes for non-time-critical state.

**Documented past failure:** On 2026-05-13, BlackCEO location `Mct54Bwi1KlNouGXQcDX` burned all 200k daily calls. All three tiers (Official MCP, Community MCP, Raw API) returned the same underlying 429. The cause was a combination of test loops during development, polling intervals, and per-turn agent re-fetches. The fix is the rules above — never the workaround of switching tiers.

---

## 🔴 Rule 9 — Fuzzy detection of the master-files folder

The `openclaw-master-files` folder name varies across installs. ALWAYS use the fuzzy locator from `lib-shared.sh` (`find_master_files()`) instead of hardcoding `openclaw-master-files`. The locator handles all common variants:

- `openclaw-master-files`
- `OpenClaw Master Files` (two words, spaces)
- `openclaw_master_files` (underscores)
- `open-claw-master-files` (hyphen between "open" and "claw")
- `open claw master files` (all spaces)
- `OpenClawMasterFiles` (camel case)
- `OpenClaw Documents` / `openclaw files` / etc.

Search order: `~/Downloads` → `/data/Downloads` → `/root/Downloads` → `/data` → `$HOME` → `$HOME/clawd` → `/data/clawd` → `/opt` → `/srv`. Excludes backup/zip/bak/tmp folders. Case-insensitive throughout.

If the folder is not found, create it at the canonical path (`$HOME/Downloads/openclaw-master-files` on Mac, `/data/Downloads/openclaw-master-files` on VPS) — but only after asking the owner for permission.

---

## 🔴 Rule 10 — Model selection priority (cost-aware)

When the master orchestrator selects a model for sub-agents or for itself, it follows this priority (cheapest acceptable wins):

1. **Subscription / OAuth-based models (no per-call cost):**
   - `openai-codex/gpt-5.5` (OAuth via OpenClaw Pi)
   - `codex/gpt-5.5` (OAuth via Codex.app — required for Computer Use)
   - Anthropic Claude on Pro subscription (if configured)
2. **Ollama cloud models (very low cost):**
   - `ollama/kimi-k2.6:cloud` — preferred for orchestration when subscription unavailable
   - `ollama/deepseek-v4-pro:cloud` — preferred for sub-agents (30-min timeout)
3. **OpenRouter (priced per token):**
   - `openrouter/xiaomi/mimo-v2-pro` with `reasoning: true`
   - `openrouter/moonshot/kimi-k2.6` with `thinking: high`
4. **Direct provider APIs (more expensive):**
   - `deepseek/deepseek-v4-pro`
   - Last resort only

**Forbidden by default:**
- `claude-opus-*` (Anthropic API) — too expensive unless the owner explicitly requests it for a specific task
- `claude-sonnet-*` (Anthropic API) — too expensive unless the owner explicitly requests it
- `openai/*` (OpenAI direct API) — costs money; never use without explicit owner permission

If the agent cannot determine which models are available, it must ASK the owner and present their available models list rather than guess.

---

## 🔴 Rule 11 — Sub-agent settings (set FIRST in any install)

Before installing any skill, the master orchestrator must verify these `agents.defaults.subagents` settings in `openclaw.json`:

```json
{
  "thinking": "high",
  "maxChildrenPerAgent": 20,
  "maxConcurrent": 100,
  "maxSpawnDepth": 5,
  "timeoutSeconds": 1800
}
```

These values are validated against the live OpenClaw docs at `https://docs.openclaw.ai` because they can change between releases. If the docs recommend different values for the current OpenClaw version, use the docs' values and document the change in MEMORY.md.

The fallbacks should include cheap-first models per Rule 10.

---

## 🔴 Rule 12 — Recommend `/new` session, don't require it

For long-running install sessions (a full onboarding install can take 30–60 min), recommend the owner start a fresh session with `/new` so the install gets a clean context. This is a recommendation, not a requirement.

If they do `/new`, write a state-carryover file at `~/.openclaw/.install-resume.json` (Mac) or `/data/.openclaw/.install-resume.json` (VPS) containing:

```json
{
  "started_at": "ISO-8601 timestamp",
  "phase": "A|B|C|D|E",
  "wave": "1|2|3|4|5",
  "completed_skills": ["01-...", "02-..."],
  "active_skills": ["07-...", "08-..."],
  "pending_skills": ["09-..."],
  "owner_decisions": {"podcast": "deferred", "video_pref": 2},
  "next_step": "free-text description"
}
```

The new session reads this file at startup and resumes. Always update the file after each skill completes.

---

## 🔴 Rule 13 — Owner-facing communication style

The owner may be over 60. Calibrate accordingly:

- Plain English, no acronyms unless you explain them on first use
- Headlines first, technical details only if asked
- Progress notes every 5 skills OR every 2 minutes, whichever comes first
- Never paste raw error logs / stack traces unless the owner asks
- Never use jargon: "deps" → "dependencies", "envs" → "environment variables", "PIT" → "Private Integration Token (PIT)" on first use
- Final summary structure: "Install complete. [N] skills active. [M] memory layers verified. [K] personas available. Anything that needs your attention: [bulleted list or 'nothing']."

---

## 🔴 Rule 14 — Acknowledge this contract before EACH skill

Before starting work on any skill, state explicitly in your work log:

> *"INSTALL-CONTRACT.md acknowledged for skill NN-skill-name. Proceeding with INSTALL.md step order."*

This single line is the proof that you read the contract and committed to it for this specific skill. If the line is missing from your work log, that skill's install is considered uncontracted and must be repeated.

---

## 🔴 Rule 15 — What "done" means for a skill

A skill is "done" (and the agent is allowed to declare it done) only when ALL of these are true:

1. All `.md` files in the skill folder were read
2. INSTALL.md steps were executed in order, none skipped
3. All prerequisite skills are present (or explicitly deferred with owner consent)
4. CORE_UPDATES.md was applied surgically to the labeled core files only
5. QC.md scored ≥ 8.5/10
6. Bundled `qc-*.sh` (if present) exited 0
7. No PIT or other secret was leaked to logs / chat / commits
8. An owner-facing confirmation message was sent describing what was installed

If any of these is missing, the skill is NOT done. Do not say "done" or "complete" or "✅" until all 8 are true.

---

## Self-audit (recite before declaring any skill done)

Recite this checklist out loud in your work log before claiming completion:

1. Did I read ALL .md files in the skill folder? ✓ / ✗
2. Did I follow INSTALL.md step order verbatim? ✓ / ✗
3. Did I run QC.md? Score: __/10 (must be ≥ 8.5)
4. Did the bundled qc-*.sh exit 0? ✓ / ✗ / N/A
5. Did I respect every rule in this contract? ✓ / ✗ (which rule, if not)
6. Did I send the owner-facing confirmation? ✓ / ✗
7. Did I check for sub-agents before any gateway restart? ✓ / ✗ / N/A
8. Did I respect the GHL alias rules and the "PIT not API key" rule? ✓ / ✗

If any answer is ✗, the skill is not done. Loop back.

---

## Violations

If you violate this contract during an install, you must:

1. Immediately STOP work on the current skill
2. Send the owner a Telegram message explaining: which rule you broke, what state you left the system in, what you recommend (rollback / continue / escalate to Trevor)
3. WAIT for owner response before proceeding

Silent violations are not allowed. The whole point of this contract is to make violations visible.
