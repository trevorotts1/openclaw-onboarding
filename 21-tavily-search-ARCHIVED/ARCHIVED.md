# ARCHIVED — Skill 21: Tavily Search

This skill is no longer part of the active OpenClaw onboarding (41 active skills as of v12.26.0). It is kept in the repo for historical reference only.

## Why this was archived

Skill 21 — "Tavily Search" — wired the Tavily real-time web-search API into the agent as a tool. Tavily is no longer used in the OpenClaw fleet.

1. **Tavily dependency dropped.** The operator fleet migrated away from Tavily as a paid search dependency. Web-search capability is now covered through native MCP tools and Context7 (Skill 09) for documentation lookups, plus the agent's built-in browsing capability via Agent Browser (Skill 03).

2. **Tavily API key requirement.** Every client box would need a funded Tavily API key. With the migration to other search approaches, requiring a Tavily key at onboarding creates an unnecessary dependency and cost for clients who do not need real-time web search as a standalone tool.

## What replaced it

| Old Skill 21 capability | Where it lives now |
|------------------------|--------------------|
| Real-time web search | Agent Browser (Skill 03) — Playwright-backed browser automation for live web research |
| Current news / facts not in training data | MCP `context7` server (Skill 09) for library/framework docs; Agent Browser for general research |
| API-driven search results | Replaced by native browsing; no Tavily API key required |

## Status

- **Archived:** v12.26.0 (June 2026). Tavily is no longer used in the OpenClaw fleet.
- **Skill folder retained because:** some client onboardings may reference `Skill 21: Tavily Search` in their `MEMORY.md` or `.onboarding-status` files. Removing the folder would break backward-compat lookups during update checks.
- **Do NOT install this skill on a new onboarding.** It is not in the Wave plan, the QC framework, or the audit phase list.
- **Do NOT update this folder going forward.** Any web-search capability change goes to Agent Browser (Skill 03) or Context7 (Skill 09).

## Cross-references

- **Skill 03** (`03-agent-browser/`) — canonical live web-browsing + research capability
- **Skill 09** (`09-context7/`) — library and framework documentation lookups via MCP

---

*v12.26.0 — archived: Tavily is no longer used in the OpenClaw fleet*
