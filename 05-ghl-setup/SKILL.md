---
name: ghl-setup
description: Foundational GoHighLevel (GHL / Convert and Flow) setup — obtains API credentials, configures direct REST API access, and teaches the agent how to search contacts, send messages, and handle errors. Install before or alongside skill 36 (GHL MCP) for full multi-tier access.
---

# GHL / Convert and Flow Setup

> **For official-MCP access:** This skill covers the foundational direct-API setup. For the **official GHL MCP** — documented catalog: four tools, `list_locations`, `search_operations`, `describe_operation`, `execute_operation` — install **skill 36 (`36-ghl-mcp-setup`)** after completing this one. The agent prefers the official MCP where its catalog covers the call and falls back to this skill's direct public REST API otherwise.
>
> **The community GHL MCP is retired.** It is not part of the update or install path: fresh installs omit it, and an updated box must verify it is **off** — service unloaded and de-registered. A stopped process is not a retirement; a lingering launchd job with `RunAtLoad=true` resurfaces it at login. Never repair or reinstall it because a tool count looks low. Official MCP plus public REST are the supported routes.

## What This Is

This skill teaches your AI agent how to connect to GoHighLevel (GHL), which is a customer relationship management (CRM) platform. Think of a CRM as a digital address book that also lets you send text messages, emails, and track business conversations - all in one place.

"Convert and Flow" is the client-facing name for GHL. They are the same thing on the backend. Same login, same system, same connection method. When someone says "Convert and Flow" they mean GHL.

## When to Use This Skill

Use this skill when:
- You are setting up GHL or Convert and Flow for the first time
- Your agent needs to search for contacts, send text messages, or send emails through GHL
- You need to get your API credentials (the keys that let your agent talk to GHL)
- Your agent is getting errors when trying to use GHL
- Someone says "set up GHL," "connect to Convert and Flow," or "send a message through GHL"

## Prerequisites

You MUST have these installed first:
1. Teach Yourself Protocol (TYP) - Skill 01
2. Back Yourself Up Protocol - Skill 02
3. An active GoHighLevel or Convert and Flow account (you need to be able to log in)

## Critical Things Your Agent Must Know

These are the most common mistakes AI agents make with GHL. Read these carefully:

1. **GHL does NOT use API keys anymore.** That method is old and no longer recommended. GHL uses a Private Integration Token (PIT). If your agent says "I need the API key" for GHL, it is using outdated information. The correct term is Private Integration Token. You find it in Settings > Integrations > Private Integration Token. This PIT is the **public REST API** credential. The **official GHL MCP is a separate path and uses OAuth, not a PIT** — do not hand it a PIT and call that the documented connection.

2. **The Version header is selected PER OPERATION.** There is no global default you may assume: many current operations are documented at `v3`, while dated versions remain supported for other operations. Read the version from that operation's own documentation before each call. Omitting the header on an operation that declares one fails with a 401 (`version header was not found`). See skill 29 (`29-ghl-convert-and-flow`) and its `references/api-generations.md` for the per-operation table, and never sweep one version string across calls.

3. **The base URL for all GHL API calls is:** https://services.leadconnectorhq.com

4. **Your agent should check two places for credentials:**
   - ~/.openclaw/secrets/.env (look for GOHIGHLEVEL_API_KEY; full alias set — see TERMINOLOGY.md)
   - ~/.openclaw/openclaw.json under env.vars

> **GHL LOCATION-PIT unified resolver (11 aliases):** `GOHIGHLEVEL_API_KEY` is
> the canonical name; 10 additional aliases (`GHL_API_KEY`, `GHL_PIT`,
> `GHL_TOKEN`, `GHL_PRIVATE_INTEGRATION_TOKEN`, `PRIVATE_INTEGRATION_TOKEN`,
> `GHL_PRIVATE_TOKEN`, `PIT_TOKEN`, `GHL_PIT_TOKEN`, `GOHIGHLEVEL_LOCATION_PIT`,
> `GHL_LOCATION_PIT`) all resolve to the same LOCATION Private
> Integration Token. All 11 are checked in order across every env store before
> any "not found" is raised. **Agency PITs are kept separate** —
> `GOHIGHLEVEL_AGENCY_PIT`, `GOHIGHLEVEL_AGENCY_API_KEY`,
> `GOHIGHLEVEL_CONVERTANDFLOW_AGENCY_PIT`, and `GHL_AGENCY_PIT` are NOT in this
> set and must not be substituted for a LOCATION PIT (they 401 on media and
> location-scoped endpoints). See **`TERMINOLOGY.md`** (repo root) for the full
> canonical alias set and backend-equivalence notes (Convert & Flow /
> leadconnectorhq.com / app.gohighlevel.com = one platform).

## What This Skill Covers

- How to get your Private Integration Token and Location ID from GHL
- How to add those credentials to your OpenClaw configuration
- The required headers (Authorization plus the operation's own Version)
- Common operations: searching contacts, creating contacts, sending SMS, sending email, calendar booking, managing opportunities
- Example curl commands you can copy and use right away
- A 5-step, entirely read-only self-test to verify everything is working before claiming setup is done. It does not send anything — proving send capability is a separate, operator-approved step against a designated operator test contact
- What to add to your core files (AGENTS.md, TOOLS.md, MEMORY.md) after setup
- **Unified 11-alias LOCATION-PIT resolver** — the single `GOHIGHLEVEL_API_KEY`
  canonical name plus 10 accepted aliases; the resolver searches all 11 across
  every env store before raising. Agency PITs (`GOHIGHLEVEL_AGENCY_PIT` and
  variants) are a separate credential set — never substituted for a LOCATION PIT

## Files in This Folder and Reading Order

1. **SKILL.md** - You are here. Start here for the overview.
2. **ghl-setup-full.md** - The complete guide. Covers every step from getting credentials to testing the connection, with example commands and a full self-test checklist.
3. **INSTALL.md** - Quick install reference.
4. **INSTRUCTIONS.md** - Step-by-step execution instructions.
5. **EXAMPLES.md** - Real examples of GHL API calls.
6. **CORE_UPDATES.md** - Exactly what to add to your core .md files.
7. **ghl-setup.skill** - Machine-readable skill definition.

## Priority Operations to Test First

After setup, test these three things first because they are used the most:
1. **Contacts** - Search, create, and update contacts
2. **Media Library** - Upload and list media files
3. **Conversations** - Send SMS and email messages

## Important Rules

- Never use the built-in GHL node in n8n (a workflow tool) - it is too limited. Always use HTTP Request nodes instead.
- GHL has rate limits: 100 requests per minute for most operations. Do not blast it with hundreds of calls at once.
- Do NOT tell the user "GHL is set up" until all 5 self-tests in the full guide pass successfully.
- NEVER send an SMS or an email from a client's account to test that setup worked. All 5 self-tests are read-only, and setup is complete without a send. A send delivers a real message to a real person; it requires explicit operator approval against a designated operator test contact, never a client contact. See SEND VERIFICATION in the full guide.
- After setup, only add summaries and file paths to your core files - not the full documentation.
