---
name: ghl-mcp-setup
description: Install and configure the GoHighLevel access chain — Tier 0 Convert and Flow CLI (skill 44), the official MCP connection (client-specific OAuth v2 endpoints, four documented tools), direct REST API, agent-browser/Playwright, and Codex Computer Use — so the agent always picks the cheapest path first and falls back gracefully. The self-hosted community MCP is RETIRED: fresh installs omit it and updated boxes must verify it is off. Registers ghl-mcp under nested mcp.servers via the openclaw mcp set CLI.
---

> **GHL PIT aliases:** `GOHIGHLEVEL_API_KEY` is the preferred name; 10 additional aliases resolve the same LOCATION PIT. See **`TERMINOLOGY.md`** (repo root) for the canonical alias set and backend-equivalence notes (Convert & Flow / leadconnectorhq.com = one platform).

# GHL MCP Setup — Multi-Tier Access for GoHighLevel

## What This Is

This skill teaches your AI agent how to connect to GoHighLevel (also called "Convert and Flow") through a **tiered access chain** that always picks the cheapest, fastest path first and falls back gracefully when needed.

The chain:

0. **Tier 0 — Convert and Flow CLI** (`caf`/`convertandflow`/`ghl`, skill 44) — for everything the CLI covers: contacts, opportunities, calendars, conversations, documents, payments, forms, social, locations, workflows (PIT for standard ops; Firebase token for workflow writes)
1. **Tier 1 — Official GHL MCP** (hosted by GHL, free, no install) — for blogs and CLI gaps. Client-specific OAuth v2 endpoints; see "Official MCP endpoints" below.
2. **Tier 2 — RETIRED: community GHL MCP** — not installed, not required, not a fallback. Verify it is OFF (see below). Routing goes Tier 1 → Tier 3.
3. **Tier 3 — Direct REST API** with Private Integration Token (uses skill 29's reference files) — for anything no MCP covers; also the replacement route for the retired community tool surface; media uploads (POST /medias/upload-file)
4. **Tier 4 — Browser: agent-browser (Vercel) FIRST, Playwright fallback** (skill 03) — for UI-only flows; workflow-write backstop when no Firebase token
5. **Tier 5 — Codex Computer Use** (`codex/gpt-5.5`) — visual automation, approval-gated, last resort

## Official MCP endpoints and authentication (Tier 1)

HighLevel publishes client-specific **version 2** MCP endpoints. They are the documented
path. The original `/mcp/` endpoint is still served, but it is **transitional** and must not
be presented as equivalent.

| Client | Documented endpoint |
|---|---|
| Claude (Claude Code / Claude MCP client) | `https://services.leadconnectorhq.com/mcp/anthropic/v2` |
| ChatGPT / Codex / other OpenAI clients | `https://services.leadconnectorhq.com/mcp/openai/v2/` |
| OpenClaw gateway | **Not a documented MCP client.** A Claude model routed through OpenClaw is NOT proof of a Claude MCP client. Register through the gateway's own adapter and treat the result as unverified until a `tools/list` capture exists. |

(A `muse/v2` endpoint exists in the same family for Muse clients.)

**Authentication is OAuth.** The official page documents a sign-in/consent flow for these
endpoints and mentions no Private Integration Token. A PIT bearer sent to an MCP endpoint is
an **unverified compatibility mode**, never an equivalent auth path. The REST API (Tier 0/3)
still uses the location PIT; the official MCP connection does not inherit it.

**Documented catalog — exactly four tools:**
`list_locations`, `search_operations`, `describe_operation`, `execute_operation`.
That is the whole documented catalog. `search` and `fetch` are legacy names from earlier
documentation: **UNVERIFIED** — do not teach them as current, and do not delete this note
until a live `tools/list` capture proves or disproves them. The underlying operation catalog
(the "more than 550 active operations across 38 domains" figure) is discovered at runtime
through `search_operations`; it is not a static tool list, and a count is never parity proof.

**The original endpoint** `https://services.leadconnectorhq.com/mcp/` — one tool per
operation, PIT bearer plus `locationId`/`Version` headers in existing registrations — stays
supported during the transition. Do not call it "legacy" or "deprecated" (HighLevel does
not); call it transitional. Do not infer its tool count.

### Four evidence levels for MCP — do not collapse them

| Level | What it means | Can this repo assert it? |
|---|---|---|
| **1. Documented endpoint** | The vendor documentation publishes the URL for a named client | **Yes** — cite the docs page and fetch date |
| **2. Documented catalog** | The vendor documentation publishes the tool names (`list_locations`, `search_operations`, `describe_operation`, `execute_operation`) | **Yes** — names only |
| **3. Account / tenant grant** | The target account actually authorizes this connection, with the scopes and sub-account(s) claimed | **No** — requires an authorized OAuth connect on that account |
| **4. Actually observed on this box** | This box completed a `tools/list` and at least one real call, and the capture is recorded | **No** — requires a per-box receipt |

This repository asserts levels 1 and 2 only. Any statement that a box "has official MCP" is
level 4 and must carry that box's own capture.

### Tier 2 is RETIRED — verify it is OFF

The self-hosted community MCP (`ghl-community-mcp`, historically described as the
"588-tool" server) is **no longer installed or required**. Fresh installs omit it; updated
boxes must verify it is off. The required end state:

- `ghl-community-mcp` absent from `openclaw mcp list`
- no launchd / pm2 / systemd unit for it loaded or enabled
- no listener on `127.0.0.1:8765`
- `GHL_COMMUNITY_MCP_URL` absent from `openclaw.json` `env.vars`

Do **not** clone, pin, build, supervise, probe, or "repair" it, and do **not** rebuild it
because a tool count looks low. The last vetted profile was `curated` = **43 crm tools**
(smoke tool `crm_list_workspaces`); the 588 / 858 / 500 figures describe other profiles or
history and prove nothing about parity. The only retained MCP surfaces are the **official
connection** and the **custom courier MCP**. Retirement must never touch either — and must
never string-match `ghl-mcp` when stopping the community systemd unit of the same name (the
official `mcp.servers` entry is also called `ghl-mcp`; they are different things). Historical
rollback requires an explicit operator decision; see INSTALL.md → "Historical manual
rollback".

## Why This Skill Exists

Before this skill, agents would either:
- Fall through to the raw API without disclosing why
- Hardcode port numbers from stale session memory and declare a tier dead without checking the canonical state
- Forget to disclose which tier they used, making escalation violations invisible

This skill installs a **canonical state block**, a **disclosure header protocol**, and **anti-skip enforcement**. Documented failures on 2026-05-12 (hardcoding a wrong port, skipping a live tier) drove the design. The community tier that originally motivated part of that design is now retired; the state block teaches its absence.

## When to Use This Skill

- You are setting up GHL on a brand-new OpenClaw install for the first time
- Your agent currently goes straight to the raw GHL API and you want it to use the official MCP first
- You want product / invoice / subscription / billing automation in an existing GHL setup (Tier 0 CLI or Tier 3 REST; the community tier is not a route)
- A box still carries the retired community MCP and you must verify it is off
- You're onboarding a new client and want their agent to follow a strict tier escalation rule

## Aliases (treat all as the same platform)

GHL = Convert & Flow = Go High Level — one white-label platform; default app URL is `app.convertandflow.com`. All names below refer to the same product and the same API backend (`services.leadconnectorhq.com`):

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
5. An active GoHighLevel or Convert and Flow account. Tier 0/3 need permission to create a Private Integration Token. Tier 1 needs an OAuth grant from the account owner.
6. **Platform:** macOS OR Linux/VPS — both are supported for the retained surfaces
7. **Node.js ≥ 20** is **not** required for the required end state. It was required only by the retired community MCP.

## Critical Things Your Agent Must Know

These are the most common mistakes agents make with the MCP setup. Read them carefully.

1. **The community MCP is RETIRED — port 8765 must be free.** If something still listens on `127.0.0.1:8765` for GHL, that box was not fully retired. Verify: no listener, no `ghl-community-mcp` registration, no loaded unit. Do not "fix" it by restarting it. (Port 8000 is Cognee on most OpenClaw installs and is never a GHL port.)

2. **Tier order is binding. Do not skip tiers.** If Tier 1 lacks the operation, go to **Tier 3** (REST) next. Tier 2 is retired and is not part of the chain.

3. **Every GHL response must disclose the tier used on the operator channel.** Format: `[GHL tier used: N — tool_name]`. If the agent fell through tiers, the header must show the chain: `[GHL tier used: 3 (Tier 1 lacked operation: products.list) — raw API GET /products/]`. Missing disclosure = protocol violation. Strip it from client-facing replies.

4. **"It looked broken earlier" is not an excuse for skipping.** If a tier failed in earlier session work, attempt it fresh. Tier 1 recovery is a re-authorized OAuth connection plus a `tools/list` capture — never a community-service restart.

5. **Two separate credential classes — never substitute one for the other.** The REST CLI and raw API (Tier 0/3) use the **location PIT** resolved from `~/.openclaw/secrets/.env` (aliases per skill 29's Credentials section). The official MCP (Tier 1) uses **OAuth**; a PIT bearer is an unverified compatibility mode. Never send the PIT to a v2 MCP endpoint and call it equivalent, and never assume an account-level OAuth grant exists because the PIT works. The custom courier MCP keeps its own credentials and is out of scope for this skill.

6. **The official MCP is stateless.** Initialize does NOT return an `Mcp-Session-Id` header. Do not gate follow-up calls on a session ID — each request is independent.

7. **MCP tools are ORCHESTRATOR-ONLY.** Spawned sub-agents receive no MCP tool injection. Any contact lookup inside a sub-agent MUST use `caf contacts search/get` (Tier 0 CLI) or raw HTTPS (Tier 3). Never tell a sub-agent to call `ghl-mcp__*` tools — it will fail.

8. **Raw HTTP to the transitional `/mcp/` endpoint MUST send BOTH Accept values.** That endpoint requires `Accept: application/json, text/event-stream`; sending only `Accept: application/json` returns HTTP 406 (content-negotiation error, not auth). Do not assume the same requirement transfers to the v2 client endpoints without a capture.

9. **Never use `grep -P` on a Mac client box.** BSD grep (macOS default) has no -P flag. Parse JSON/SSE responses with `python3 -c "import json,sys; ..."` or `jq`.

10. **Use the cheapest non-metered model configured on THIS box for lookup inference — never a metered `:cloud` model.** Contact lookups are cheap data-retrieval tasks. Preflight the box's actual providers (inspect the configured model list — e.g. `openclaw config get models` / the client's OpenClaw config) and pick the lowest-cost non-metered model the client genuinely has (a free local Ollama model, or an `openrouter/free`-tier model). Never hardcode a specific model id — the configured providers differ per box, and hardcoding one that isn't provisioned strands the lookup. Metered cloud models burn quota for work a free model handles fine.

11. **🔴 The documented rate limits are the REST API's — MCP publishes none.** The 100/10s burst and 200,000/day per-location figures are documented for the REST API. HighLevel publishes **no rate limits** for the MCP endpoints. Assume the shared backend bucket applies, probe before bulk work, and never quote the REST figures as MCP limits.
   - **REST burst limit:** 100 requests per 10 seconds per location
   - **REST daily limit:** 200,000 requests per day per location
   - **Response headers on REST calls:** `X-RateLimit-Remaining`, `X-RateLimit-Daily-Remaining`, `X-RateLimit-Limit-Daily`, `X-RateLimit-Daily-Reset` (seconds until reset)
   - **Documented past failure (2026-05-13):** location `[REDACTED]` burned its 200k daily quota — Tier 1 returned 200 SSE wrapping a 429, Tier 2 (then live) returned 500 wrapping a 429, Tier 3 returned 429 direct. All three hit the same backend.
   - **Before bulk operations:** make ONE cheap probe call (`locations_get-location` or `tools/list`), read `X-RateLimit-Daily-Remaining` from the response. If less than 1000 remaining, STOP and tell the owner the daily-reset time in plain English ("Rate limit will reset around 11 PM ET tonight"). Do NOT proceed.
   - **On 429:** read `X-RateLimit-Daily-Reset` (seconds-until-reset), compute clock time, surface to owner. NEVER retry blindly. NEVER fall through tiers (they share the bucket).
   - **Always batch:** use `limit=100` page size, cache list results in MEMORY.md for at least 5 minutes, never re-fetch the same data per agent turn.

## What This Skill Covers

- How to detect platform (Mac vs VPS) and pick correct paths
- How to hunt for existing PIT + Location ID across 7 standard credential locations BEFORE asking the client
- How to register the Official GHL MCP (Tier 1) with `openclaw mcp set`, and which client-specific v2 endpoint applies
- How to **verify the retired community MCP is off** (registration absent, no unit, no listener, env var absent) without reinstalling it
- How to keep the retirement transaction from touching the official connection or the custom courier MCP
- How to add cardinal rules to AGENTS.md, TOOLS.md, MEMORY.md (SOUL.md stays unchanged — the Tier Escalation Protocol lives in AGENTS.md)
- A QC checklist and the bundled QC script
- Test prompts to confirm the agent routes correctly after install

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

After setup, run these three checks in order:

1. **Tier 1 test:** connect with OAuth and run `list_locations` (or the client's equivalent) — should return the real location; record the `tools/list` capture.
2. **Retirement test:** `ghl-community-mcp` absent from `openclaw mcp list`; nothing listening on `127.0.0.1:8765`; no launchd/pm2/systemd unit for it.
3. **Disclosure test:** Ask the agent in Telegram or main chat: *"How many products are in my store?"* — with the community tier retired, the expected operator answer is Tier 0 (`caf products list`) or Tier 3 (`GET /products/`), e.g. `[GHL tier used: 0 — convertandflow products list]`.

## Cross-References to Other Skills

- **Skill 05 (`05-ghl-setup`):** Handles the foundational credential discovery. This skill (36) builds on top of it by adding the MCP layer. If a client only has 05 installed, this skill 36 elevates them to MCP-first.
- **Skill 29 (`29-ghl-convert-and-flow`):** Provides the Tier 3 reference files. When MCPs lack a tool, this skill's instructions fall through to skill 29's `references/[module].md` lookups.
- **Skill 35 (`35-social-media-planner`):** Runs a SELF-CONTAINED 15+6 subagent publishing pipeline that posts to GHL Blog + Social Planner and uploads media via the DIRECT LeadConnector API (POST /medias/upload-file). That internal pipeline is EXEMPT from tier routing — do not redirect it through an MCP. Only AD-HOC interactive requests (a person asking the agent in chat to post something or look something up) follow the tier chain.
- **`38-conversational-ai-system/references/GHL_AI_LAYERS.md`:** The authoritative 3-layer GHL AI architecture reference. **The official MCP covers lookup operations and contact enrollment/removal through contact operations; it does NOT build or publish GHL workflows.** Workflow builds use Skill 44's internal Build API (Tier 0, Firebase token required) or the Build-with-AI manual paste (fallback). These are orthogonal surfaces — MCP and Build API are not interchangeable. See GHL_AI_LAYERS.md for the full Layer 0 / Layer 1 / Layer 2 decision table.

## Important Rules

- The retired community MCP is never re-installed on a fresh box and never restarted to "fix" one
- Always prefix GHL-data responses with the `[GHL tier used: N — tool_name]` header **on the operator channel only**
- Never skip Tier 1 for an operation it can serve; never route through the retired Tier 2
- Never expose the PIT, OAuth token, Location ID, or account data in chat logs, commits, or shared docs
- Test in a dev / test sub-account before production for any write operation
