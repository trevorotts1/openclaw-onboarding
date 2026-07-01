---
name: ghl-mcp-setup
description: Install and configure the 6-tier GoHighLevel access chain — Tier 0 Convert and Flow CLI (skill 44), Official MCP (36 tools), Community MCP (588 tools, on-demand curl), direct REST API, agent-browser/Playwright, and Codex Computer Use — so the agent always picks the cheapest path first and falls back gracefully. Registers ghl-mcp under nested mcp.servers via the openclaw mcp set CLI.
---

# GHL MCP Setup — Multi-Tier Access for GoHighLevel

## What This Is

This skill teaches your AI agent how to connect to GoHighLevel (also called "Convert and Flow") through a **6-tier access chain** that always picks the cheapest, fastest path first and falls back gracefully when needed.

The chain:

0. **Tier 0 — Convert and Flow CLI** (`caf`/`convertandflow`/`ghl`, skill 44) — for everything the CLI covers: contacts, opportunities, calendars, conversations, documents, payments, forms, social, locations, workflows (PIT for standard ops; Firebase token for workflow writes)
1. **Tier 1 — Official GHL MCP** (36 tools, hosted by GHL, free, no install) — for blogs and CLI gaps
2. **Tier 2 — Community GHL MCP** (588 tools, on-demand via curl — NOT registered in mcp.servers) — for products, invoices, billing, subscriptions, estimates, store, coupons, Voice AI, Phone System, Agent Studio
3. **Tier 3 — Direct REST API** with Private Integration Token (uses skill 29's reference files) — for anything no MCP covers; media uploads (POST /medias/upload-file)
4. **Tier 4 — Browser: agent-browser (Vercel) FIRST, Playwright fallback** (skill 03) — for UI-only flows; workflow-write backstop when no Firebase token
5. **Tier 5 — Codex Computer Use** (`codex/gpt-5.5`) — visual automation, approval-gated, last resort

## Why This Skill Exists

Before this skill, agents would either:
- Skip Tier 2 entirely and jump from Tier 1 to Tier 3 (raw API) because Tier 2 felt abstract
- Hardcode port numbers from stale session memory, hit Cognee on port 8000, declare Tier 2 dead, and fall through
- Forget to disclose which tier they used, making escalation violations invisible

This skill installs a **canonical state block**, a **disclosure header protocol**, **anti-skip enforcement**, and an **env var (`$GHL_COMMUNITY_MCP_URL`)** that makes the right URL the shortest path. Documented failures on 2026-05-12 (skipping Tier 2, hardcoding wrong port) drove the design.

## When to Use This Skill

- You are setting up GHL on a brand-new OpenClaw install for the first time
- Your agent currently goes straight to the raw GHL API and you want it to use MCPs first
- You want to add product / invoice / subscription / billing automation to an existing GHL setup
- A previous community MCP setup is broken and you need to redeploy it cleanly
- You're onboarding a new client and want their agent to follow a strict tier escalation rule

## Aliases (treat all as the same platform)

- GHL
- GoHighLevel
- Go High Level
- LeadConnector (`leadconnectorhq.com` is GHL's API host)
- "Convert and Flow" (or whatever the client's white-label brand is named)

## Prerequisites

You MUST have these installed first:

1. **Skill 01 — Teach Yourself Protocol (TYP)** — governs how this skill's content gets stored
2. **Skill 02 — Back Yourself Up Protocol (BYUP)** — for config backups before modifying `openclaw.json`
3. **Skill 05 — GHL Setup** — provides the basic credential discovery foundation
4. **Skill 29 — GHL Convert and Flow** — provides the Tier 3 reference files (`references/*.md`) and the master API reference
5. An active GoHighLevel or Convert and Flow account with permission to create a Private Integration Token
6. **Node.js ≥ 20** installed (community MCP requires it)
7. **Platform:** macOS (with launchd) OR Linux/VPS (with systemd) — both are supported

## Critical Things Your Agent Must Know

These are the most common mistakes agents make with the MCP setup. Read them carefully.

1. **GHL community MCP runs on port 8765, NOT 8000.** Port 8000 is Cognee on most OpenClaw installs. If your agent reaches for port 8000 for GHL work, it has stale session context. Use `$GHL_COMMUNITY_MCP_URL` — the env var resolves to the correct URL.

2. **Tier order is binding. Do not skip tiers.** If Tier 1 lacks the tool, try Tier 2 BEFORE Tier 3. Skipping Tier 2 because Tier 3 looks more concrete is a documented past failure.

3. **Every GHL response must disclose the tier used.** Format: `[GHL tier used: N — tool_name]`. If the agent fell through tiers, the header must show the chain: `[GHL tier used: 2 (Tier 1 lacked tool: products) — ghl_list_products]`. Missing disclosure = protocol violation.

4. **"It looked broken earlier" is not an excuse for skipping.** If a tier crashed in earlier session work, attempt it fresh. Recover with `launchctl kickstart` (Mac) or `pm2 restart ghl-community-mcp` (VPS; `systemctl restart ghl-mcp` on systemd boxes) before falling through.

5. **Same Private Integration Token used for both tiers.** Tier 1 sends the PIT as `Authorization: Bearer ...` header. Tier 2 reads it from `~/mcp-servers/ghl-community-mcp/.env` as `GHL_API_KEY`. Both reference the same canonical secrets file (`~/.openclaw/secrets/.env` on Mac, `~/.openclaw/secrets/.env` on VPS).

6. **The official MCP is stateless.** Initialize does NOT return an `Mcp-Session-Id` header. Do not gate follow-up calls on a session ID — each request is independent.

7. **MCP tools are ORCHESTRATOR-ONLY.** Spawned sub-agents receive no MCP tool injection. Any contact lookup inside a sub-agent MUST use `caf contacts search/get` (Tier 0 CLI) or raw HTTPS (Tier 3). Never tell a sub-agent to call `ghl-mcp__*` tools — it will fail.

8. **Raw HTTP to the MCP endpoint MUST send BOTH Accept values.** The GHL hosted MCP endpoint requires `Accept: application/json, text/event-stream`. Sending only `Accept: application/json` returns HTTP 406 (content-negotiation error, not auth). Both values are mandatory.

9. **Never use `grep -P` on a Mac client box.** BSD grep (macOS default) has no -P flag. Parse JSON/SSE responses with `python3 -c "import json,sys; ..."` or `jq`.

10. **Use `deepseek-v4-flash` (direct) for lookup inference — never a metered `:cloud` model.** Contact lookups are cheap data-retrieval tasks. Metered cloud models burn quota for work a free model handles fine.

11. **🔴 GHL rate limits apply to ALL tiers — they share the same backend bucket.** Switching tiers does NOT bypass the limit.
   - **Burst limit:** 100 requests per 10 seconds per location
   - **Daily limit:** 200,000 requests per day per location
   - **Response headers on every call:** `X-RateLimit-Remaining`, `X-RateLimit-Daily-Remaining`, `X-RateLimit-Limit-Daily`, `X-RateLimit-Daily-Reset` (seconds until reset)
   - **Documented past failure (2026-05-13):** location `[REDACTED]` burned its 200k daily quota — Tier 1 returned 200 SSE wrapping a 429, Tier 2 returned 500 wrapping a 429, Tier 3 returned 429 direct. All three failed simultaneously because they all hit the same backend.
   - **Before bulk operations:** make ONE cheap probe call (`locations_get-location` or `tools/list`), read `X-RateLimit-Daily-Remaining` from the response. If less than 1000 remaining, STOP and tell the owner the daily-reset time in plain English ("Rate limit will reset around 11 PM ET tonight"). Do NOT proceed.
   - **On 429:** read `X-RateLimit-Daily-Reset` (seconds-until-reset), compute clock time, surface to owner. NEVER retry blindly. NEVER fall through tiers (they share the bucket).
   - **Always batch:** use `limit=100` page size, cache list results in MEMORY.md for at least 5 minutes, never re-fetch the same data per agent turn.

## What This Skill Covers

- How to detect platform (Mac vs VPS) and pick correct paths
- How to hunt for existing PIT + Location ID across 7 standard credential locations BEFORE asking the client
- How to register the Official GHL MCP (Tier 1) with `openclaw mcp set`
- How to clone, build, and deploy the Community GHL MCP (Tier 2 — BusyBee3333 2026 fork, 588 tools)
- How to wire `$GHL_COMMUNITY_MCP_URL` env var so agents never hardcode ports
- How to install launchd plist (macOS) OR pm2 supervision (VPS; systemd fallback) — no Docker dependency
- How to add cardinal rules to AGENTS.md, TOOLS.md, MEMORY.md (SOUL.md stays unchanged — the Tier Escalation Protocol lives in AGENTS.md)
- A 20-point QC script that runs end-to-end verification
- 5 test prompts to confirm the agent routes correctly after install

## Files in This Folder and Reading Order

1. **SKILL.md** — You are here. Start here for the overview.
2. **INSTALL.md** — Step-by-step autonomous setup. Run this first.
3. **INSTRUCTIONS.md** — How to USE the MCPs day-to-day after install.
4. **EXAMPLES.md** — Real working curl examples for both MCPs, the fall-through pattern, and sub-agent-safe lookup examples.
5. **GHL-LOOKUP-SOP.md** — Authoritative SOP for contact lookups and two-axis READ/BUILD routing. Covers: orchestrator-vs-sub-agent MCP rules, dual Accept header contract, no `grep -P`, fail-fast preflight, model selection, and per-path decision table.
6. **CORE_UPDATES.md** — Exact text to add to AGENTS.md, TOOLS.md, MEMORY.md (SOUL.md is left unchanged — the Tier Escalation Protocol lives in AGENTS.md).
7. **QC.md** — 7-section quality control checklist. The QC script itself ships separately as `qc-ghl-mcp-setup.sh` in this folder (do not extract from QC.md — the standalone is the single source of truth).
8. **ghl-mcp-setup-full.md** — Long-form complete reference with troubleshooting cheat sheet.
9. **CHANGELOG.md** — Skill version history.
10. **ghl-mcp-setup.skill** — Machine-readable bundled archive.

## Priority Operations to Test First

After setup, run these three smoke tests in order:

1. **Tier 1 test:** `locations_get-location` — should return your real BlackCEO / client business info
2. **Tier 2 test:** `ghl_list_products` (limit 3) — should return real products from the store
3. **Disclosure test:** Ask the agent in Telegram or main chat: *"How many products are in my store?"* — response should open with `[GHL tier used: 2 — ghl_list_products]`

## Cross-References to Other Skills

- **Skill 05 (`05-ghl-setup`):** Handles the foundational credential discovery. This skill (36) builds on top of it by adding the MCP layer. If a client only has 05 installed, this skill 36 elevates them to MCP-first.
- **Skill 29 (`29-ghl-convert-and-flow`):** Provides the Tier 3 reference files. When MCPs lack a tool, this skill's instructions fall through to skill 29's `references/[module].md` lookups.
- **Skill 35 (`35-social-media-planner`):** Runs a SELF-CONTAINED 15+6 subagent publishing pipeline that posts to GHL Blog + Social Planner and uploads media via the DIRECT LeadConnector API (POST /medias/upload-file). That internal pipeline is EXEMPT from tier routing — do not redirect it through an MCP. Only AD-HOC interactive requests (a person asking the agent in chat to post something or look something up) follow the tier chain.
- **`38-conversational-ai-system/references/GHL_AI_LAYERS.md`:** The authoritative 3-layer GHL AI architecture reference. **MCP tools (Tiers 1-2 above) cover contacts/conversations/calendar/tags reads and writes. They do NOT build GHL workflows.** Workflow builds use Skill 44's internal Build API (Tier 0, Firebase token required) or the Build-with-AI manual paste (fallback). These are orthogonal surfaces — MCP and Build API are not interchangeable. See GHL_AI_LAYERS.md for the full Layer 0 / Layer 1 / Layer 2 decision table.

## Important Rules

- Always reference `$GHL_COMMUNITY_MCP_URL` instead of hardcoding a port number
- Always prefix GHL-data responses with the `[GHL tier used: N — tool_name]` header
- Never skip Tier 2 just because Tier 3 has a clearer code path
- Never expose the PIT or Location ID in chat logs, commits, or shared docs
- Test in a dev / test sub-account before production for any write operation (create_invoice, send_invoice, etc.)
