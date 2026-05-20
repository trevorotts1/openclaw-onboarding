# ARCHIVED

This skill is no longer part of the active OpenClaw onboarding (33 active skills as of v10.13.0). It is kept in the repo for historical reference only.

## Why this was archived

Google Workspace setup (Gmail, Calendar, Drive, Docs, Sheets) was a v3/v4-era onboarding step when OpenClaw assumed every operator was on Google Workspace. Three things changed:

1. **MCP layer matured.** Google Workspace integrations now flow through MCP servers (`claude_ai_Gmail`, `claude_ai_Google_Calendar`, `claude_ai_Google_Drive`) that authenticate per-session, not per-install. The install-time OAuth dance Skill 13 ran is no longer needed.

2. **GHL became the canonical CRM.** Skill 29 (`gohighlevel-management`) + Skill 36 (`ghl-mcp-setup`) replaced the Google-Workspace-centric flows (calendar bookings via Google Calendar API → now via GHL appointments; email outreach via Gmail API → now via GHL conversations + email).

3. **Operator heterogeneity.** Newer onboardings target operators who don't use Google Workspace at all (Outlook 365, ProtonMail, Apple iCloud). Forcing a Google-Workspace setup created an onboarding cliff for those operators.

## What replaced it

| Old Skill 13 capability | Where it lives now |
|------------------------|--------------------|
| Gmail send/read | `claude_ai_Gmail` MCP server (per-session OAuth) |
| Google Calendar events | `claude_ai_Google_Calendar` MCP + Skill 29 GHL appointments |
| Google Drive file ops | `claude_ai_Google_Drive` MCP |
| Google Docs / Sheets editing | Direct MCP tools — no install step required |
| Workspace OAuth tokens | Per-session MCP authentication |
| Skill 13 INSTALL.md flow | Removed — replaced by `mcp__authenticate` tool calls at runtime |

## Status

- **Archived:** v10.7.0 onboarding-package rewrite (mid-May 2026).
- **Skill folder retained because:** several v5-era client onboardings still reference `Skill 13: Google Workspace Setup` in their `MEMORY.md` and `.onboarding-status` files. Removing the folder entirely would break their backward-compat lookups.
- **Do NOT install this skill on a new onboarding.** It's not in the Wave plan, the QC framework, or the audit phase list.
- **Do NOT update this folder going forward.** Any Google-Workspace-related capability change goes to MCP integrations or Skill 29 (GHL).

## Cross-references

- Skill 29 (`gohighlevel-management`) — canonical CRM (replaces Google Workspace calendar + email)
- Skill 36 (`ghl-mcp-setup`) — MCP layer for GHL
- `~/.openclaw/MEMORY.md` — old "Google Workspace installed" markers from v5-era clients
- `~/.openclaw/AGENTS.md` Section "## 🔴 N1–N27" — Skill 13 is NOT referenced in any N-rule

---

*v10.13.0 — closes audit Phase 4 finding "Skill 13 lacks any archive documentation"*
