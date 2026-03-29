# Terminology — Required Reading for All Agents

This file defines terms that are used across the entire onboarding system. Read this before installing or QC'ing any skill.

---

## GHL / Convert and Flow / GoHighLevel

These three names refer to the SAME platform:
- **GHL** = GoHighLevel (abbreviation)
- **Convert and Flow** = Trevor's white-labeled version of GoHighLevel (client-facing name)
- **GoHighLevel** = the underlying platform

**CRITICAL: GHL does NOT use API keys. It uses Private Integration Tokens (PITs).**

When you see any of these in config files, env vars, or instructions, they ALL mean the same thing — a Private Integration Token:
- `GHL_API_KEY`
- `GOHIGHLEVEL_API_KEY`
- `GHL_TOKEN`
- `GHL_PIT`
- `PRIVATE_INTEGRATION_TOKEN`
- `PIT_TOKEN`
- `GOHIGHLEVEL_AGENCY_PIT`

There are TWO types of PIT:
1. **Location PIT** (`GOHIGHLEVEL_API_KEY` / `GHL_API_KEY`) — used for day-to-day work within a specific location (contacts, media uploads, etc.)
2. **Agency PIT** (`GOHIGHLEVEL_AGENCY_PIT`) — used for agency-wide operations across all sub-accounts

**Rules:**
- When talking to clients, ALWAYS say "Convert and Flow." Never say "GoHighLevel."
- When talking to agents or in technical docs, "GHL" is acceptable shorthand.
- Never tell a client they need an "API key" for GHL. The correct term is "Private Integration Token" or "PIT."
- Media uploads require the Location PIT, not the Agency PIT.
