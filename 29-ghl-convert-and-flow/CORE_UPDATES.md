# CORE_UPDATES.md - Paste These Into Your Core Files

> These are the only updates this skill makes to core files. They are reference pointers only.
> NEVER copy the master reference content into any core file. It is ~430K characters and will
> destroy your context window. Only TOOLS.md and MEMORY.md receive updates from this skill.

---

## TOOLS.md Update

Add this block to `~/clawd/TOOLS.md`:

```markdown
## Convert and Flow (GoHighLevel) API v2

- **Skill:** `~/.openclaw/skills/29-ghl-convert-and-flow/` (Tier 3 — direct REST)
- **Base URL:** `https://services.leadconnectorhq.com`
- **Auth:** LOCATION-scoped Private Integration Token (Bearer) — legacy API keys are DEPRECATED
- **Credentials (canonical):** `~/.openclaw/secrets/.env` → `GOHIGHLEVEL_API_KEY` + `GOHIGHLEVEL_LOCATION_ID`
- **Version header:** `2021-07-28` default (33 of 41 app specs). `2021-04-15` ONLY for conversations, calendars, saas-api, voice-ai, agent-studio, conversation-ai, knowledge-base. `v3` for the v3 generation. Confirm per-app — never blanket.

### Routing rule (Tier-0-first — per skill 36)
For every GHL operation, escalate in order — do NOT start at the REST layer:
1. Tier 0 — Convert and Flow CLI (skill 44) when it covers the operation
2. Tier 1 — Official MCP (`ghl-mcp`, 36 tools)
3. Tier 2 — Community MCP (`ghl-community-mcp`, 588 tools)
4. Tier 3 — this skill's `references/<domain>.md` (and ALWAYS for media uploads)

Read only the matching `references/<domain>.md` at query time. NEVER load the 430K master
reference into context or any core file. Do not memorize endpoints — read them fresh.

### Module quick-index (op counts read from the published specs, 2026-08-03)
- contacts (32): create/read/update/delete, tags, tasks, notes
- conversations (29): search, send SMS/email, message history — `Version: 2021-04-15`
- calendars (41): calendars, free slots, appointments — `Version: 2021-04-15`
- opportunities (12): pipelines (read-only), create/update/search deals
- locations (29): sub-account config, custom fields, tags
- medias (Tier 3 only): `POST /medias/upload-file` — LOCATION PIT, Version 2021-07-28
- AI surfaces: agent-studio (11), conversation-ai (12), knowledge-base (14), voice-ai (11) — all `Version: 2021-04-15`
- Full module list: `~/.openclaw/skills/29-ghl-convert-and-flow/references/modules.md`
```

---

## MEMORY.md Update

Add this block to `~/clawd/MEMORY.md`:

```markdown
## Convert and Flow API - Active Integration

- **Skill folder:** `~/.openclaw/skills/29-ghl-convert-and-flow/` (Tier 3 REST library)
- **Credentials:** `~/.openclaw/secrets/.env` → `GOHIGHLEVEL_API_KEY` (LOCATION PIT) + `GOHIGHLEVEL_LOCATION_ID`
- **Auth method:** Private Integration Token (Bearer); legacy API keys deprecated
- **Version header:** `2021-07-28` default. `2021-04-15` ONLY for conversations, calendars, saas-api, voice-ai, agent-studio, conversation-ai, knowledge-base. `v3` for v3-only surfaces.
- **Routing:** Tier 0 CLI (skill 44) → Tier 1/2 MCP → Tier 3 references/*.md. Media is always Tier 3.
- **Never** load the 430K master reference into context. Read one `references/<domain>.md` per task.
- After a write, point the client to the verify table in SKILL.md "Caller Contract".
- This skill owns NO Command Center board — caller skills update the Skill 32 Kanban.

Load credentials before every call (resolver maps legacy aliases, fails loud if unset):
`[ -f ~/.openclaw/secrets/.env ] && { set -a; . ~/.openclaw/secrets/.env; set +a; }`
```
