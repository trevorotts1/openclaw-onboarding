# GoHighLevel MCP Setup — Universal Agent Instructions

**Audience:** an AI agent (OpenClaw, Claude Code, or any MCP-aware client) setting up GoHighLevel access for a new client.
**Last verified:** 2026-10-18 against `https://marketplace.gohighlevel.com/docs/other/mcp` (client-specific OAuth v2 endpoints; four documented tools) and the retirement record for the community MCP. The community tier is **retired**; its historical pin is `32628c979dd8f46e7952f85ce2d98f8028a26c32`.

---

## 0. WHAT THIS IS AND HOW TO USE IT

You are an AI agent. You have been asked to set up GoHighLevel (GHL) integration for a client. Follow this document end-to-end. Do not skip phases. Do not improvise on tier order. The whole point is a clean, layered fallback chain so that ANY GHL task can be served by the cheapest tier that works.

### Aliases (treat all of these as the same platform)
- GHL
- GoHighLevel
- Go High Level
- LeadConnector (`leadconnectorhq.com` is GHL's API host)
- The client's white-label name (e.g. "Convert and Flow", "Your Brand CRM"). Ask the client what they call it.

### The tiered access chain you are setting up (the old Tier 2 is retired)

| Tier | What | When |
|------|------|------|
| 0 | Convert and Flow CLI (`caf`/`convertandflow`/`ghl`, skill 44) — PRIMARY | Contacts, opportunities, calendars, conversations, documents, payments, forms, social, locations, workflow READS (PIT); workflow BUILD/EDIT (Firebase token). The cheapest, fastest path — no MCP overhead, no manual UI. |
| 1 | Official GHL MCP (hosted by GHL; client-specific OAuth v2 endpoints; four documented tools) | Blogs + anything the CLI doesn't cover among contacts, calendars, conversations, opportunities, social media, emails, locations |
| 2 | **RETIRED: community GHL MCP** | Nothing. Not a route. Verify it is OFF (registration absent, no unit, no listener on 8765, no `GHL_COMMUNITY_MCP_URL`). |
| 3 | Direct REST API (GHL skill in `openclaw-master-files/29-ghl-convert-and-flow/`) | Products, invoices, billing, subscriptions, estimates, store, coupons, Voice AI, Phone System, Agent Studio, full payments; anything the CLI/official MCP does not cover; media uploads (`POST /medias/upload-file`) |
| 4 | agent-browser (Vercel) FIRST, Playwright fallback at `app.gohighlevel.com` (skill 03) | UI-only flows the API doesn't expose; workflow-write backstop when no Firebase token |
| 5 | Codex Computer Use (`codex/gpt-5.5`) | Last-resort visual automation |

**Rule:** Try each tier in numerical order, **starting at Tier 0**. Do NOT skip tiers. If Tier N fails fresh on this request, recover it before falling through.

---

---

## MASTER SETUP CHECKLIST — work top-to-bottom, do not skip

Tick each box as you complete it. **No box is optional.** If any box can't be ticked, do not proceed — stop and resolve before continuing.

```
PRE-FLIGHT
[ ]  1.A  Teach Yourself Protocol invoked (or this doc loaded as bootstrap)
[ ]  1.B  Platform detected (desktop or VPS) — $CANONICAL_MASTER set
[ ]  1.B  openclaw-master-files folder located OR permission to create granted
[ ]  1.B  $MASTER_FILES_DIR exported and confirmed to exist
[ ]  1.B  GHL skill subfolder present inside master files (or flagged as missing)

CREDENTIALS
[ ]  2    Searched all 7 credential locations for existing PIT + Location ID
[ ]  3    If missing: asked client with exact template; received both values
[ ]  3    PIT written to $SECRETS_ENV with chmod 600
[ ]  3    Both values added to openclaw.json env.vars
[ ]  3    Neither value echoed to chat/logs/commits

RESEARCH
[ ]  4    Verified current Official MCP endpoints and OAuth requirement via web fetch
[ ]  4    Confirmed the documented catalog is four tools; recorded that a count is not parity

TIER 1 INSTALL
[ ]  5    Client-appropriate v2 endpoint chosen; OAuth authorized (Claude or ChatGPT/Codex)
[ ]  5    `openclaw mcp set ghl-mcp` succeeded (transitional /mcp/ registration, preserved)
[ ]  5    `tools/list` capture recorded with tool names (not a count assertion)
[ ]  5    A real read (e.g. `list_locations`) returned real data

TIER 2 RETIREMENT (do not install)
[ ]  6    Confirmed `ghl-community-mcp` absent from `openclaw mcp list`
[ ]  6    Confirmed `GHL_COMMUNITY_MCP_URL` absent from `openclaw.json` env.vars
[ ]  6    Confirmed no launchd/pm2/systemd unit loaded or enabled (a stopped RunAtLoad job is NOT retired)
[ ]  6    Confirmed no listener on `127.0.0.1:8765`
[ ]  6    Confirmed probe job removed or retirement-aware
[ ]  6    Legacy tree, if any, archived with a redacted manifest (keys only) — no secret-bearing .env
[ ]  6    Official connection and custom courier MCP verified still present

FALLBACK TIERS
[ ]  7    GHL skill at $MASTER_FILES_DIR/[skill folder] confirmed readable
[ ]  7    Playwright route documented (Tier 4)
[ ]  7    Codex Computer Use available (Tier 5)

CORE FILES WIRED
[ ]  8    SOUL.md LEFT UNCHANGED (Tier Escalation Protocol lives in AGENTS.md, not SOUL.md)
[ ]  8    AGENTS.md updated with canonical state block + Tier Escalation Protocol + tier order + anti-patterns
[ ]  8    TOOLS.md updated with tool-name reference
[ ]  8    MEMORY.md updated with install record + credential references
[ ]  8    USER.md updated (if file exists) with brand aliases

VERIFICATION
[ ]  9    All 5 test prompts produced correct disclosure headers
[ ]  9    No prompt produced "tier used: 3" when "tier used: 2" was expected
[ ]  9    All prompts answered from live GHL data (not hallucinated)

QC FINAL (run Section 11 before declaring done)
[ ]  11   Bundled QC script qc-ghl-mcp-setup.sh executed end-to-end with exit 0
[ ]  11   Every assertion in the QC script passed
[ ]  11   This document copied into $MASTER_FILES_DIR/XX-ghl-mcp-setup/
[ ]  11   Setup record appended to MEMORY.md with date + client name
[ ]  11   Final security checklist (Appendix) all 9 items ticked
```

If you're a human reviewing an AI agent's work: any unticked box = setup is NOT complete. Send the agent back with the specific unfinished items.

---

## 1. PRE-FLIGHT — TEACH YOURSELF + LOCATE MASTER FILES

### 1.A Use the Teach Yourself Protocol

Before you start, invoke the **Teach Yourself Protocol** that lives in your appliance computer's bootstrap. This will:
- Re-read this document section by section into your working context
- Build a TODO checklist of phases below
- Bind the credentials you discover in Phase 1 to the right env-var names automatically

If you do not have a Teach Yourself Protocol available, treat this entire document as your bootstrap and check off each phase as you complete it.

### 1.B Locate the `openclaw-master-files` folder

The Tier 3 fallback (REST API + skill set), the install of this document, and several phases below all reference an `openclaw-master-files/` folder. **You must locate it before proceeding.** The folder name varies across installs (uppercase / lowercase, hyphens / spaces / underscores, "open claw" as two words vs one, "master files" as two words vs one). The locator below tolerates all of these.

#### Where the folder lives by platform

| Platform | Canonical location |
|---|---|
| **macOS / desktop install** | `~/Downloads/openclaw-master-files/` |
| **VPS / Docker / server install** | `~/Downloads/openclaw-master-files/` (VPS has no `~/Downloads/` — the persistent volume is `/data/`, with `~/Downloads/`, `~/clawd/`, and `~/.openclaw/` as the twins of the Mac home-dir equivalents) |
| **Other Linux desktop** | `$HOME/Downloads/openclaw-master-files/` |

#### Smart locator (run this before anything else)

```bash
# Detect platform — macOS is Darwin; everything else (VPS/Docker/Linux) is treated as vps.
# (Do NOT test `[ -d "~/.openclaw" ]` — the tilde does NOT expand inside quotes, so the
#  test is for a literal "~/.openclaw" dir that never exists, and ~/.openclaw exists on
#  BOTH platforms anyway. uname is the reliable discriminator.)
if [ "$(uname -s)" = "Darwin" ]; then
  PLATFORM="desktop"
else
  PLATFORM="vps"
fi
CANONICAL_MASTER="$HOME/Downloads/openclaw-master-files"
echo "Platform detected: $PLATFORM"
echo "Canonical path if missing: $CANONICAL_MASTER"

# Search across all reasonable roots for the folder, tolerating spelling variants
MASTER_FILES_DIR=""
ROOTS=(
  "$HOME/Downloads"        # macOS / Linux / VPS canonical (always $HOME — never a quoted "~")
  "/root/Downloads"        # some root-shell VPS setups
  "/data"                  # in case it was placed at the volume root
  "$HOME"                  # in case the client dropped it in home
  "$HOME/clawd"            # in case it lives next to the workspace
  "/opt"                   # some server installs
  "/srv"                   # some server installs
)
for r in "${ROOTS[@]}"; do
  [ -d "$r" ] || continue
  # Two-arm pattern handles "openclaw" as one token AND "open claw" as two tokens,
  # case-insensitively, with hyphens / underscores / spaces as separators.
  # Excludes .zip archives and timestamped backup folders.
  found=$(find "$r" -maxdepth 2 -type d \
    \( -iname "*openclaw*master*file*" -o -iname "*open*claw*master*file*" \) \
    ! -iname "*backup*" ! -iname "*.zip*" ! -iname "*.bak*" \
    2>/dev/null | head -1)
  if [ -n "$found" ]; then
    MASTER_FILES_DIR="$found"
    break
  fi
done

if [ -n "$MASTER_FILES_DIR" ]; then
  echo "✅ Found openclaw-master-files at: $MASTER_FILES_DIR"
  # Confirm it has the GHL skill inside — that's our Tier 3 dependency
  GHL_SKILL=$(find "$MASTER_FILES_DIR" -maxdepth 2 -type d -iname "*ghl*convert*flow*" 2>/dev/null | head -1)
  if [ -n "$GHL_SKILL" ]; then
    echo "✅ GHL skill folder present at: $GHL_SKILL"
  else
    echo "⚠️  Master files found but no GHL skill folder inside. Tier 3 fallback won't work until the skill is installed there."
  fi
else
  echo "❌ openclaw-master-files folder NOT FOUND under any expected root."
  echo "   Default canonical path for this platform: $CANONICAL_MASTER"
  echo "   STOP. Ask the client/Trevor for permission to create it."
fi
```

#### If the folder is NOT found — DO NOT silently create it

Stop and ask the client/Trevor with this exact message:

> "I can't find an `openclaw-master-files` folder anywhere under `~/Downloads/`, `~/Downloads/`, or the other usual locations. This folder holds the GHL API skill set that the Tier 3 fallback depends on. I'd like to create it at `$CANONICAL_MASTER` and then either (a) copy in the GHL skill from a known-good source, or (b) flag that the skill is missing and proceed with Tiers 1+2 only.
>
> Do I have permission to create the folder? If yes, also tell me whether you have a backup of the skill set I should restore into it."

**After permission is granted:**

```bash
mkdir -p "$CANONICAL_MASTER"
echo "Created $CANONICAL_MASTER"
export MASTER_FILES_DIR="$CANONICAL_MASTER"
```

Then ask the client whether they have a backup of the GHL skill set to restore. If no backup exists, proceed with Tier 3 disabled — note this clearly in the agent's MEMORY.md so the agent knows not to attempt Tier 3 until the skill is installed.

#### Save this document into the master files folder when you're done

When setup is complete, copy this document into the master files folder under a sensibly named subfolder (e.g. `29-ghl-convert-and-flow/` or `XX-ghl-mcp-setup/`) so it's available for future re-installs:

```bash
mkdir -p "$MASTER_FILES_DIR/XX-ghl-mcp-setup"
cp "$(pwd)/GHL-MCP-Setup.md" "$MASTER_FILES_DIR/XX-ghl-mcp-setup/"
```

(Replace `$(pwd)/GHL-MCP-Setup.md` with the actual current path of this file — typically `~/Downloads/GHL-MCP-Setup.md` after the original install.)

---

## 2. PHASE 1 — HUNT FOR EXISTING CREDENTIALS BEFORE ASKING

The client likely already has a GHL Private Integration Token (PIT) and Location ID somewhere. **Search exhaustively before asking — asking is a tax on the client's time.**

### Files and locations to check (in order)

```bash
# Canonical paths are identical on Mac and VPS (both under $HOME). Use $HOME — never a
# quoted "~" (it does not expand inside quotes and would yield a literal "~/..." path).
SECRETS_ENV="$HOME/.openclaw/secrets/.env"
CONFIG_JSON="$HOME/.openclaw/openclaw.json"
WORKSPACE="$HOME/clawd"
[ ! -d "$WORKSPACE" ] && WORKSPACE="$HOME/.openclaw/workspace"

# Every check below is EXISTENCE-ONLY: it reports which credential key NAMES are
# present, never their values (the repo qc-static secret-printing gate fails any
# secret-pattern grep that lacks -q/-l/-L).

# 1. OpenClaw secrets file (canonical — same names on Mac and VPS, different paths) — names only
for k in GHL_API_KEY GOHIGHLEVEL_API_KEY GHL_PIT GHL_LOCATION_PIT LEADCONNECTOR_PIT GHL_PRIVATE_INTEGRATION_TOKEN PRIVATE_INTEGRATION_TOKEN GHL_LOCATION_ID GOHIGHLEVEL_LOCATION_ID; do
  grep -qE "^(export )?${k}=" "$SECRETS_ENV" 2>/dev/null && echo "$k=SET"
done

# 2. OpenClaw main config env block — names only, values never printed
python3 -c "
import json
cfg=json.load(open('$CONFIG_JSON'))
ev=cfg.get('env',{}).get('vars',{})
for k in ev:
    if any(s in k.upper() for s in ['GHL','GOHIGH','LEADCONN','LOCATION']):
        print(f'{k}=SET')
"

# 3. Live process env — key NAMES only (cut strips the value before grep ever sees it)
printenv | cut -d= -f1 | grep -iE "GHL|GOHIGH|LEADCONN|LOCATION_ID" || true

# 4. Home-level dotfile — key NAMES only
cut -d= -f1 ~/.env 2>/dev/null | grep -iE "GHL|GOHIGH|LEADCONN|LOCATION" || true

# 5. clawd / repo-level env files — matching FILE names only (-l), never the values
grep -rilE "GHL_API_KEY|GOHIGHLEVEL_API_KEY|GHL_LOCATION_ID|GOHIGHLEVEL_LOCATION_ID|leadconnector" \
  "$WORKSPACE"/.env* "$WORKSPACE"/*/.env* 2>/dev/null

# 6. openclaw-master-files (uses the $MASTER_FILES_DIR from Section 1.B) — file names only (-l)
grep -rilE "GHL_API_KEY|GOHIGHLEVEL_API_KEY|GHL_LOCATION_ID|GOHIGHLEVEL_LOCATION_ID" \
  "$MASTER_FILES_DIR/" 2>/dev/null

# 7. Existing MCP server configs (in case a previous community MCP install left .env behind)
find ~/mcp-servers ~/mcp ~/services /data/mcp-servers 2>/dev/null -maxdepth 4 -name ".env" -exec grep -l "GHL\|GOHIGH" {} \;
```

### What you are looking for

| Conceptual value | Env var names you may find it under |
|---|---|
| **Private Integration Token (PIT)** for the **Location** (sub-account) | `GHL_API_KEY`, `GOHIGHLEVEL_API_KEY`, `GHL_PIT`, `GHL_LOCATION_PIT`, `LEADCONNECTOR_PIT`. Value format: `pit-xxxxxxxx-xxxx-...` |
| **Location ID** (sub-account ID) | `GHL_LOCATION_ID`, `GOHIGHLEVEL_LOCATION_ID`. Value format: 22-char alphanumeric (e.g. `AbCdEfGhIjKlMnOpQrStUv`) |
| (Optional) **Agency PIT** for agency-wide ops | `GHL_AGENCY_PIT`, `GOHIGHLEVEL_AGENCY_PIT` |
| (Optional) **User ID** | `GHL_USER_ID`, `GOHIGHLEVEL_USER_ID` |

### Decision

- **Both found:** record them, redact in any logs, proceed to Phase 4 (skip Phase 3).
- **Only Location ID found:** proceed to Phase 3 (ask for PIT only).
- **Only PIT found:** proceed to Phase 3 (ask for Location ID only).
- **Neither found:** proceed to Phase 3 (ask for both).

**Never echo the PIT or full key into chat logs.** Reference env-var names only.

---

## 3. PHASE 2 — IF NOT FOUND, ASK THE CLIENT

Use this exact request template (adapt the client's white-label brand name):

> "I'm setting up [BRAND]'s AI integration. To do that without scraping the UI, I need two things from your GHL/[BRAND] account:
>
> 1. **Location ID** — open [BRAND] → Settings → Company → Locations → click the location → copy the ID at the top (22 characters, looks like `AbCdEfGhIjKlMnOpQrStUv`).
>
> 2. **Private Integration Token** with these scopes:
>    - `contacts.readonly`, `contacts.write`
>    - `conversations.readonly`, `conversations.write`
>    - `opportunities.readonly`, `opportunities.write`
>    - `calendars.readonly`, `calendars.write`
>    - `locations.readonly`, `locations.write`
>    - `workflows.readonly`
>    - `blogs.readonly`, `blogs.write`
>    - `users.readonly`
>    - `custom_objects.readonly`, `custom_objects.write`
>    - `invoices.readonly`, `invoices.write`
>    - `payments.readonly`
>    - `products.readonly`, `products.write`
>    - `medias.write` (for media uploads)
>
> To create it: Settings → Integrations → Private Integrations → Create New Private Integration → Name: 'MCP Server Integration' → enable all scopes above → Save → copy the generated PIT (starts with `pit-`)."

### Storing what the client sends back

**Write to BOTH locations:**

```bash
# Canonical secrets dir is the same on Mac and VPS. Use $HOME, never a quoted "~".
SECRETS_DIR="$HOME/.openclaw/secrets"

# 1. Canonical secrets file
mkdir -p "$SECRETS_DIR"
cat >> "$SECRETS_DIR/.env" <<EOF
GOHIGHLEVEL_API_KEY=pit-XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
GOHIGHLEVEL_LOCATION_ID=YYYYYYYYYYYYYYYYYYYYYY
EOF
chmod 600 "$SECRETS_DIR/.env"

# 2. OpenClaw main config env.vars (gateway reads from here at runtime)
openclaw config set env.vars.GOHIGHLEVEL_API_KEY "pit-XXXXXXXX-..."
openclaw config set env.vars.GOHIGHLEVEL_LOCATION_ID "YYYYYYYYYYYYYYYYYYYYYY"
```

**Never** commit either file to git. **Never** paste the PIT into a chat that may be logged or quoted later.

---

## 4. PHASE 3 — WEB RESEARCH REFRESH (DO THIS EVEN IF YOU "KNOW")

Documentation drifts. Always re-verify against current sources before you wire MCPs:

- **OpenClaw MCP CLI docs:** https://docs.openclaw.ai/cli/mcp
- **Official GHL MCP docs:** https://marketplace.gohighlevel.com/docs/other/mcp/
- **HighLevel support article:** https://help.gohighlevel.com/support/solutions/articles/155000005741-how-to-use-the-highlevel-mcp-server
- **Community MCP (historical — DO NOT CLONE):** https://github.com/trevorotts1/ghl-community-mcp-mirror
  (org-controlled mirror, retained only as rollback material. The retired vetted pin is
  `32628c979dd8f46e7952f85ce2d98f8028a26c32`, profile `curated` = 43 crm tools, smoke tool
  `crm_list_workspaces`. Do not clone, build, or supervise it during setup.)
- **Community MCP upstream (historical, read-only, do not clone):** https://github.com/busybee3333/Go-High-Level-MCP-2026-Complete
- **Community MCP original (historical):** https://github.com/mastanley13/GoHighLevel-MCP
- **MCPorter (optional config manager):** https://github.com/openclaw/mcporter

Confirm:
- The official endpoints are client-specific: `https://services.leadconnectorhq.com/mcp/anthropic/v2`
  (Claude) and `https://services.leadconnectorhq.com/mcp/openai/v2/` (ChatGPT/Codex); auth is OAuth
- The original `https://services.leadconnectorhq.com/mcp/` is **transitional**, still supported
- The documented catalog is exactly four tools: `list_locations`, `search_operations`,
  `describe_operation`, `execute_operation`
- The `Version` header is selected **per operation** (documented values include `v3`,
  `2023-02-21`, `2021-07-28`, `2021-04-15`, `legacy`). There is no global default and no
  sweep. `v4` workflow contracts are staging-only evidence.
- No tool count is an interface. The old 588 / 858 / 500 figures describe other profiles or
  history and prove nothing about parity.

**Community retirement is the target state, and no pin lives on this page.** Retirement means:
no registration, no loaded/enabled supervisor, no listener on `127.0.0.1:8765`, no
`GHL_COMMUNITY_MCP_URL`. A `RunAtLoad=true` job that is merely stopped will come back at login;
unload **and** disable it, and remove or make retirement-aware the probe. Historical rollback
requires an explicit operator decision and the archive path recorded in that box's retirement
receipt — never an installer or update script.

---

## 5. PHASE 4 — SET UP TIER 1 (OFFICIAL GHL MCP)

The official MCP is **hosted by GHL** — no local install, no deployment. The documented path is
a client-specific endpoint with OAuth:

| Client | Documented endpoint | Auth |
|---|---|---|
| Claude Code / Claude MCP client | `https://services.leadconnectorhq.com/mcp/anthropic/v2` | OAuth |
| ChatGPT / Codex / OpenAI clients | `https://services.leadconnectorhq.com/mcp/openai/v2/` | OAuth |
| OpenClaw gateway | transitional `/mcp/` registration below | transitional; PIT bearer is unverified as an auth path |

```bash
# Claude Code:
claude mcp add --transport http leadconnector https://services.leadconnectorhq.com/mcp/anthropic/v2
```

**Preserved OpenClaw registration.** The `openclaw mcp set ghl-mcp` connection stays. It points
at the original `/mcp/` endpoint and carries a PIT bearer; treat that as **transitional**. A
Claude model routed through the OpenClaw gateway is not proof of a Claude MCP client — the
gateway registers servers itself, and this repo does not establish its transport.

```bash
openclaw mcp set ghl-mcp '{
  "url": "https://services.leadconnectorhq.com/mcp/",
  "transport": "streamable-http",
  "headers": {
    "Authorization": "Bearer ${GOHIGHLEVEL_API_KEY}",
    "locationId": "${GOHIGHLEVEL_LOCATION_ID}",
    "Version": "2021-07-28"
  },
  "connectionTimeoutMs": 30000
}'
```

If `${...}` interpolation isn't supported by your OpenClaw version, substitute the literal env-var values at write time — but the env vars themselves must still be in `openclaw.json` `env.vars` so other tooling can resolve them.

### Four evidence levels for MCP — do not collapse them

| Level | What it means | Can this repo assert it? |
|---|---|---|
| **1. Documented endpoint** | Vendor docs publish the URL for a named client | **Yes** |
| **2. Documented catalog** | Vendor docs publish exactly four tool names | **Yes** — names only |
| **3. Account / tenant grant** | This account actually authorizes the connection and scopes | **No** — needs an authorized OAuth connect |
| **4. Actually observed on this box** | `tools/list` plus one real call, captured here | **No** — needs this box's receipt |

### Verify Tier 1 works

```bash
# Transitional /mcp/ reachability. Record the NAMES, not a count.
curl -sS -X POST "https://services.leadconnectorhq.com/mcp/" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "locationId: $GOHIGHLEVEL_LOCATION_ID" \
  -H "Version: 2021-07-28" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | grep "^data:" | sed 's/^data: //' \
  | python3 -c "import json,sys; print([t.get('name') for t in json.load(sys.stdin).get('result',{}).get('tools',[])])"

# Documented catalog (the assertion that matters):
#   list_locations, search_operations, describe_operation, execute_operation
# A count from this endpoint is an observation, never an interface.
```

### Real-data smoke test

```bash
curl -sS -X POST "https://services.leadconnectorhq.com/mcp/" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "locationId: $GOHIGHLEVEL_LOCATION_ID" \
  -H "Version: 2021-07-28" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"list_locations\",\"arguments\":{}}}" \
  | grep "^data:" | sed 's/^data: //' | python3 -m json.tool

# Expect: real location data. If the transitional endpoint names the tool
# differently, record the observed name — do not assert an undocumented one.
```

### Critical detail: official MCP is STATELESS

It returns `event: message\ndata: {...}` (SSE-framed) but does NOT issue an `Mcp-Session-Id` header. **Do not gate follow-up calls on a session ID** — there isn't one. Each request is independent.

---

## 6. PHASE 5 — VERIFY THE RETIRED COMMUNITY MCP IS OFF (do not install)

The community MCP is **retired from the update and install paths**. Fresh installs omit it;
updated boxes verify it is off. The required end state is **community OFF**, and the only
retained MCP surfaces are the **official connection** and the **custom courier MCP**.

Do not clone, pin, build, write `.env`, install launchd/pm2/systemd supervision, run the
autostart, or run the probe for `ghl-community-mcp`. There is no tool-count target: the old
588 / 858 / 500 figures describe other profiles or history. The last vetted profile was
`curated` = **43 crm tools**, smoke tool `crm_list_workspaces`, loopback `127.0.0.1:8765` —
and that describes a service that must now be absent.

### 6.1 Required end state (run every check)

```bash
# 1. No registration (exact name)
openclaw mcp list | grep -w ghl-community-mcp && echo "STILL REGISTERED" || echo "registration: absent"

# 2. URL env var gone
openclaw config get env.vars.GHL_COMMUNITY_MCP_URL 2>&1 | grep -q "http" && echo "ENV VAR STILL SET" || echo "env var: absent"

# 3. macOS — job not loaded, and disabled
launchctl print gui/$(id -u)/com.clawd.ghl-mcp >/dev/null 2>&1 && echo "LAUNCHD JOB STILL LOADED" || echo "launchd: not loaded"
launchctl print-disabled gui/$(id -u) | grep -q '"com.clawd.ghl-mcp" => disabled' && echo "launchd: disabled" || echo "launchd: check disabled state"

# 4. VPS — no pm2 app, no enabled systemd unit
pm2 list 2>/dev/null | grep -w ghl-community-mcp && echo "PM2 APP STILL PRESENT" || echo "pm2: absent"
systemctl is-enabled ghl-mcp 2>/dev/null | grep -qx enabled && echo "SYSTEMD UNIT STILL ENABLED" || echo "systemd: not enabled"

# 5. No listener on the canonical loopback port
lsof -nP -iTCP:8765 -sTCP:LISTEN 2>/dev/null | grep -q LISTEN && echo "LISTENER STILL PRESENT" || echo "listener: absent"

# 6. Probe job gone or retirement-aware
launchctl print gui/$(id -u)/com.clawd.ghl-mcp-probe >/dev/null 2>&1 && echo "PROBE JOB STILL LOADED" || echo "probe: not loaded"
crontab -l 2>/dev/null | grep -q "ghl-mcp-probe" && echo "PROBE CRON STILL PRESENT" || echo "probe cron: absent"
```

`RunAtLoad=true` means a stopped job returns at the next login. **Stopped is not retired.**
Unload **and** disable it. A probe that expects the service can resurrect it or fail the box
falsely — remove it or make it retirement-aware **before** stopping the service.

### 6.2 De-registration (exact verbs)

```bash
openclaw mcp unset ghl-community-mcp
openclaw config unset env.vars.GHL_COMMUNITY_MCP_URL 2>/dev/null || true
openclaw mcp list   # re-read: the gateway can rewrite openclaw.json and undo a file-level removal
```

> The verb is `unset`, not `remove`. `openclaw mcp remove` exits 1 on OpenClaw 2026.7.1-2
> ("Too many arguments for this command"), and every old call site swallowed that with
> `|| true` — which is why Tier 2 was never actually de-registered on any box.

### 6.3 Disable supervision, do not just stop it

- **macOS:** `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.clawd.ghl-mcp.plist`,
  then disable the label and archive the plist. Do not delete the archive.
- **VPS (pm2):** `pm2 delete ghl-community-mcp` under the **derived** `PM2_HOME`, then
  `pm2 save`. Delete without save leaves the resurrect list intact and the next
  `pm2 resurrect` brings it back. Never `pm2 kill` — it would take every other app in that
  home with it.
- **systemd:** `systemctl disable --now ghl-mcp` on a non-container box that actually has it.

### 6.4 Name collision and preserved surfaces

The official `mcp.servers` entry is `ghl-mcp`; the retired community **systemd unit** is also
`ghl-mcp`. They are different things. Never stop, delete, or disable anything by matching the
bare string `ghl-mcp`.

Retirement must not touch: the official MCP connection (`ghl-mcp` / `leadconnector`), the
**custom courier MCP**, shared credentials and customer data, or `~/.openclaw/secrets/.env`
(Tier 0/3 still need the PIT).

### 6.5 Historical manual rollback (operator decision only)

- Mirror: `https://github.com/trevorotts1/ghl-community-mcp-mirror.git`
- Vetted pin: `32628c979dd8f46e7952f85ce2d98f8028a26c32`
- Vetted profile: `curated` (43 crm tools), smoke tool `crm_list_workspaces`
- Loopback: `127.0.0.1:8765`
- Archive path: the path recorded in that box's retirement receipt (archive path + digest).
  The source tree it captures is `~/mcp-servers/ghl-community-mcp` (Mac) or
  `/data/mcp-servers/ghl-community-mcp` (VPS). Never archive a secret-bearing `.env`; archive a
  redacted manifest (key names only).

Restoration requires an **explicit operator decision**, must be proven on one box first, and
must restore supervision, the probe, and registration together. No installer or update script
may perform it.

### 6.6 Verify off

Run 6.1 again and record the output as the retirement receipt. There is no `/health` or
`/execute` smoke test any more. If `/health` on 8765 answers, the box is not retired — finish
the retirement; do not restart the service to "check" it. If something else owns 8765, it is
not a GHL service and must not be killed on sight.

---

## 7. PHASE 6 — TIER 3, 4, 5 SETUP NOTES

### Tier 3 — Direct REST API

The client already has the **GHL skill set** installed inside `$MASTER_FILES_DIR` (located in Section 1.B). Common subfolder names:
- `29-ghl-convert-and-flow/` (the numbered skill folder used in Trevor's reference install)
- `ghl-convert-and-flow/` (un-numbered variant)
- `ghl-skill/` or similar — verify by listing the master files folder

Inside whichever subfolder it's in, you should find:
- `ghl-convert-and-flow.skill` — the skill manifest
- `references/modules.md` — overview of all GHL API modules
- `references/[module].md` — per-module endpoint reference

Resolve it dynamically:
```bash
GHL_SKILL_DIR=$(find "$MASTER_FILES_DIR" -maxdepth 2 -type d -iname "*ghl*convert*flow*" 2>/dev/null | head -1)
echo "GHL skill dir: ${GHL_SKILL_DIR:-NOT FOUND}"
```

If the skill is missing, fetch the latest GHL API v2 master reference from `https://marketplace.gohighlevel.com/docs/` and stage it locally before relying on Tier 3.

**Tier 3 call shape:**
```bash
curl -sS "https://services.leadconnectorhq.com/products/?locationId=$GOHIGHLEVEL_LOCATION_ID&limit=100" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-04-15"
```

Note: products module uses `Version: 2021-04-15`. Most others use `2021-07-28`. Always check `references/[module].md` per call.

### Tier 4 — Browser (agent-browser FIRST, Playwright fallback)

PRIMARY engine is **agent-browser** (Vercel Labs, skill 03), headless + isolated
`--session`. Playwright is the scripted fallback for known-hard flows only; if
used, `launchPersistentContext` (NEVER `launch()`) so login state persists.
- URL: the client's white-label root, e.g. `https://app.convertandflow.com/`
  (the login form mounts at root, NOT `/login`), or `https://app.gohighlevel.com`.
- Auth: prefer the seeded Firebase refresh token (logged-in session, no typing);
  fallback creds `GHL_AGENCY_EMAIL` / `GHL_AGENCY_PASSWORD` in `~/.openclaw/secrets/.env`.
- **Funnel / Website / Page building is the Tier-4 UI-only surface and is owned by
  skill 06 (`ghl-install-pages`).** Use skill 06's `ghl-browser-builder-full.md`
  (v3.0) + `tools/` — do NOT build a parallel page-builder path here.

### Tier 5 — Codex Computer Use

- Route through OpenClaw's `codex-computer-use` sub-agent
- Model: `codex/gpt-5.5` (not `openai/...` — that's API-key route)
- Default timeout: 45 minutes (`runTimeoutSeconds: 2700`)
- Use only when Tiers 1–4 are confirmed unavailable

---

## 8. PHASE 7 — WIRE THE 6-TIER CHAIN INTO THE CLIENT'S CORE `.md` FILES

The client's agent has bootstrap files at the workspace root (e.g. `~/clawd/`). Names vary; common conventions:
- `SOUL.md` — voice/stance, cardinal behavioral rules
- `AGENTS.md` — operating rules, the WHAT-TO-DO
- `TOOLS.md` — WHERE-THINGS-LIVE
- `MEMORY.md` — durable facts and project state
- `USER.md` — user identity and preferences

Verify which the client uses by running:
```bash
ls ~/clawd/{SOUL,AGENTS,TOOLS,MEMORY,USER,CLAUDE}.md 2>/dev/null
```

### 8.1 SOUL.md — NO UPDATE NEEDED (as of skill 36 v1.1.0)

**Do NOT add the GHL Tier Escalation Protocol to SOUL.md.** The protocol is OPERATING LAW,
not identity/voice, so it lives in the SHARED **AGENTS.md** (§8.2 below) where sub-agents —
including the convert-and-flow-agent — actually inherit it. In the multi-agent model every
agent has its OWN SOUL.md but shares AGENTS.md + TOOLS.md; a protocol placed only in the
main agent's SOUL.md never reaches sub-agents. SOUL.md is therefore left **byte-identical**
by this skill (matches CORE_UPDATES.md and the fleet convention skills 05/06/38/39/41 state).

If a pre-v1.1.0 install previously appended a `## 🔴 GHL Tier Escalation Protocol` block to
SOUL.md, `wire.sh` migration **M1** removes it on live boxes. The full protocol text is
maintained in §8.2 (AGENTS.md), not here.

### 8.2 What to add to AGENTS.md (operating block — the WHAT-TO-DO)

**Append** a top-level GHL section. Adapt aliases to client white-label:

```markdown
## GHL / [Client white-label] access order

[GHL, GoHighLevel, Go High Level, LeadConnector, and {client name}] refer to the same platform.

### 🟢 Canonical current state — override stale session memory

These values are authoritative. If your session history disagrees, trust this block.

| Fact | Current canonical value |
|---|---|
| Official MCP — Claude | `https://services.leadconnectorhq.com/mcp/anthropic/v2` — OAuth |
| Official MCP — ChatGPT/Codex | `https://services.leadconnectorhq.com/mcp/openai/v2/` — OAuth |
| Transitional registration | `openclaw mcp set ghl-mcp` against the original `/mcp/` endpoint — preserved, not the documented auth path |
| Documented catalog | Exactly four tools: `list_locations`, `search_operations`, `describe_operation`, `execute_operation` |
| Community MCP (old Tier 2) | **RETIRED.** Required state: no `ghl-community-mcp` registration, no loaded/enabled unit, no listener on `127.0.0.1:8765`, no `GHL_COMMUNITY_MCP_URL` |
| Retirement guard | A `RunAtLoad=true` job that is merely stopped is NOT retired. Unload **and** disable it; remove or make retirement-aware the probe |
| Name collision | Official `mcp.servers` entry is `ghl-mcp`; the retired community **systemd unit** is also `ghl-mcp`. Different things — never act on the bare string |
| Preserved | Official MCP connection, **custom courier MCP**, shared credentials, customer data |

### Tier order (try in sequence; do not skip — START AT TIER 0)

**Tier 0 — Convert and Flow CLI (PRIMARY)**
- Wrapper: `caf` / `convertandflow` / `ghl` at `~/.openclaw/tools/convert-and-flow-cli/` — owned by SKILL 44
- Covers: contacts, opportunities, calendars, conversations, documents, payments, forms, social, locations, workflow READS (PIT); workflow BUILD/EDIT (Firebase token)
- Works in the orchestrator AND in sub-agents (it is a subprocess, not an injected MCP tool)
- Use FIRST for everything the CLI covers; health check `caf doctor`

**Tier 1 — Official GHL MCP**
- Server name in OpenClaw: `ghl-mcp`
- Documented endpoints: Claude `https://services.leadconnectorhq.com/mcp/anthropic/v2`; ChatGPT/Codex `https://services.leadconnectorhq.com/mcp/openai/v2/`. **Auth is OAuth.** The original `/mcp/` registration is transitional.
- Documented catalog: exactly four tools — `list_locations`, `search_operations`, `describe_operation`, `execute_operation`
- A Claude model routed through OpenClaw is not proof of a Claude MCP client
- A tool count is never parity proof

**Tier 2 — RETIRED Community GHL MCP**
- Not installed, not required, not a fallback. The required state is absence: no registration, no loaded/enabled unit, no listener on `127.0.0.1:8765`, no `GHL_COMMUNITY_MCP_URL`
- Never restart, probe, or rebuild it. Historical rollback requires an explicit operator decision

**Tier 3 — Direct REST API with PIT**
- Skill set at `$MASTER_FILES_DIR/29-ghl-convert-and-flow/` (Mac default: `~/Downloads/openclaw-master-files/29-ghl-convert-and-flow/`; VPS default: `~/Downloads/openclaw-master-files/29-ghl-convert-and-flow/`)
- Read `references/[module].md` for endpoint specifics
- Base URL: `https://services.leadconnectorhq.com`
- **Version header is per operation** (documented values include `v3`, `2023-02-21`, `2021-07-28`, `2021-04-15`, `legacy`). No global default; `v4` workflow contracts are staging-only evidence.
- This is the replacement route for the retired community tool surface

**Tier 4 — Browser: agent-browser (Vercel, skill 03) FIRST, Playwright fallback**
- Primary: agent-browser, headless + isolated `--session` (prefer accessibility-snapshot text over screenshots)
- Fallback: Playwright `launchPersistentContext`, never `launch()`
- URL: client white-label root (login mounts at `/`) or `https://app.gohighlevel.com`
- Auth: seeded Firebase refresh token preferred; `GHL_AGENCY_EMAIL` / `GHL_AGENCY_PASSWORD` in `~/.openclaw/secrets/.env` as fallback

**Tier 5 — Codex Computer Use**
- `codex/gpt-5.5`, 45-min default timeout
- Last resort only

> The exact AGENTS.md text that actually gets installed (canonical state block, the
> numbered 🔴 Tier Escalation Protocol, token-aware routing, the 429 carve-out, the tier
> table and anti-patterns) is maintained in **CORE_UPDATES.md** — paste from there, not
> from this reference summary, so the two never drift.

### Verify-before-fallthrough protocol (REQUIRED before declaring any tier dead)

On 404 / 502 / connection refused:
1. Re-read the canonical state block above. Compare endpoint / transport / credential class against what you actually called.
2. Separate auth from transport. Tier 1: 401/403 is an OAuth grant or scope problem; 406 is `Accept` negotiation (documented for the transitional `/mcp/` endpoint); DNS/TLS/timeout is transport. Re-authorize and record a fresh `tools/list`. Tier 3: re-check the per-operation `Version` literal, the PIT, and the rate-limit headers.
3. Tier 2 is retired — there is nothing to recover. Do not start it to test it.
4. Only after call shape and auth are ruled out, fall through. Disclosure must reflect the true cause.

### Anti-patterns (documented past failures — do not repeat)

- ❌ "Tier 1 doesn't have X → I'll use Tier 3." Wrong reasoning. Use Tier 3 because Tier 1 does not cover the operation. Tier 2 is retired and is never the answer.
- ❌ Hardcoding a port number from session memory. There is no community URL any more; the required state is no listener on 8765.
- ❌ Restarting the community service because it "crashed earlier." It is retired. Do not start it.
- ❌ "Tier 3 is faster / cleaner / I prefer raw API." Personal preference is not a routing override.
```

### 8.3 What to add to TOOLS.md (WHERE-THINGS-LIVE — reference material)

**Append** a GHL MCP surface section. Do **not** copy the retired full tool catalog into TOOLS.md. The block below records the retained surfaces and maps historical tool names to live routes.

```markdown
## GHL MCP surfaces (skill 36)

Retained: the official connection (`ghl-mcp`) and the custom courier MCP. The community MCP
(`ghl-community-mcp`) is **RETIRED**: no registration, no loaded/enabled unit, no listener on
`127.0.0.1:8765`, no `GHL_COMMUNITY_MCP_URL`.

Official: Claude `https://services.leadconnectorhq.com/mcp/anthropic/v2`; ChatGPT/Codex
`https://services.leadconnectorhq.com/mcp/openai/v2/`; **OAuth**. Documented catalog: four
tools (`list_locations`, `search_operations`, `describe_operation`, `execute_operation`).
The original `/mcp/` registration is transitional.

The domain table below is HISTORICAL: these are the retired community names, **UNVERIFIED**,
and none is a valid call path. Map the intent to Tier 0 (`caf`) or Tier 3 (REST).

Domain → historical tool names (RETIRED):

| Domain | Tools (call these directly) |
|---|---|
| Products | `ghl_list_products`, `ghl_get_product`, `ghl_create_product`, `ghl_update_product`, `ghl_delete_product`, `ghl_create_price`, `ghl_list_prices`, `ghl_create_product_collection`, `ghl_list_product_collections`, `ghl_list_inventory`, `ghl_bulk_edit_products` |
| Invoices | `list_invoices`, `get_invoice`, `create_invoice`, `update_invoice`, `delete_invoice`, `send_invoice`, `record_order_payment`, `view_invoice`, `generate_invoice_number` |
| Recurring billing / subscriptions | `list_invoice_schedules`, `get_invoice_schedule`, `create_invoice_schedule`, `list_subscriptions`, `get_subscription_by_id`, `update_saas_subscription`, `rebilling_update` |
| Estimates | `list_estimates`, `create_estimate`, `send_estimate`, `create_invoice_from_estimate`, `generate_estimate_number` |
| Payments / orders / coupons | `list_orders`, `get_order_by_id`, `list_order_fulfillments`, `create_order_fulfillment`, `list_transactions`, `get_transaction_by_id`, `list_coupons`, `create_coupon`, `update_coupon`, `delete_coupon`, `get_coupon`, `record_order_payment` |
| Contacts (extended) | `search_contacts`, `create_contact`, `update_contact`, `upsert_contact`, `add_contact_tags`, `remove_contact_tags`, `add_contact_to_workflow`, `remove_contact_from_workflow`, `bulk_update_contact_tags`, `bulk_update_contact_business`, `get_duplicate_contact` |
| Voice AI | `create_voice_ai_agent`, `update_voice_ai_agent`, `delete_voice_ai_agent`, `get_voice_ai_agent`, `list_voice_ai_agents`, `create_voice_ai_action`, `update_voice_ai_action`, `delete_voice_ai_action`, `get_voice_ai_action`, `get_voice_ai_call_log`, `list_voice_ai_call_logs` |
| Phone System | `ghl_buy_phone_number`, `ghl_release_phone_number`, `ghl_list_phone_numbers`, `ghl_get_phone_number`, `update_phone_number`, `ghl_get_call_recording`, `ghl_list_call_recordings`, `get_call_forwarding_settings`, `update_call_forwarding`, `ghl_configure_call_forwarding`, `purchase_phone_number`, `release_phone_number`, `search_available_numbers`, `list_active_numbers_by_location`, `list_number_pools` |
| Agent Studio | `ghl_create_agent`, `ghl_update_agent`, `ghl_update_agent_version`, `ghl_delete_agent`, `ghl_get_agent`, `ghl_list_agents`, `ghl_list_agent_versions`, `ghl_deploy_agent` |
| Workflows | `ghl_list_workflows`, `ghl_get_workflow`, `ghl_get_workflow_full`, `ghl_list_workflows_full`, `ghl_get_workflow_executions`, `ghl_create_workflow`, `ghl_clone_workflow`, `ghl_update_workflow_status`, `ghl_update_workflow_actions`, `ghl_delete_workflow`, `ghl_publish_workflow`, `ghl_trigger_workflow` |
| Affiliates | `get_affiliates`, `create_affiliate`, `update_affiliate`, `delete_affiliate`, `approve_affiliate`, `reject_affiliate`, `get_affiliate`, `get_affiliate_campaigns`, `create_affiliate_campaign`, `update_affiliate_campaign`, `delete_affiliate_campaign`, `get_affiliate_campaign`, `get_affiliate_commissions`, `get_affiliate_stats`, `get_payouts`, `create_payout`, `get_referrals` |
| Calendars | (extended set, ~39 tools — see Reference B) |
| Social Media | (extended set, ~19 tools — see Reference B) |
| Courses / Memberships | (~15 tools — see Reference B) |
| Reports / Analytics | `get_attribution_report`, `get_call_reports`, `get_appointment_reports`, `get_pipeline_reports`, `get_email_reports`, `get_sms_reports`, `get_funnel_reports`, `get_ad_reports`, `get_agent_reports`, `get_dashboard_stats`, `get_conversion_reports`, `get_revenue_reports` |
| Reviews | `get_reviews`, `get_review`, `reply_to_review`, `update_review_reply`, `delete_review_reply`, `get_review_stats`, `send_review_request`, `get_review_links`, `update_review_links`, `get_review_widget_settings`, `update_review_widget_settings` |
| SaaS / Snapshots | `enable_saas_location`, `bulk_enable_saas`, `bulk_disable_saas`, `get_saas_locations`, `get_saas_location`, `get_saas_agency_plans`, `get_saas_plan`, `get_saas_subscription`, `update_saas_subscription`, `create_snapshot`, `get_snapshots`, `get_snapshot`, `push_snapshot_to_subaccounts` |

For anything not in this table, use the official connection's discovery tools
(`search_operations`, then `describe_operation`) or the skill 29 REST reference. There is no
community `/tools` endpoint any more.
```

### 8.4 What to add to MEMORY.md (durable facts about THIS client's GHL setup)

**Append** as a durable record:

```markdown
## GHL MCP setup ([INSTALL DATE])

MCP surfaces installed for [client white-label brand]:

0. **Convert and Flow CLI (Tier 0, PRIMARY)** — `caf` / `convertandflow` / `ghl`, owned by skill 44. First stop for everything the CLI covers; workflow writes need the Firebase token.

1. **Official GHL MCP (Tier 1)** — OpenClaw entry `ghl-mcp`. Documented endpoints: Claude `https://services.leadconnectorhq.com/mcp/anthropic/v2`, ChatGPT/Codex `https://services.leadconnectorhq.com/mcp/openai/v2/`; **OAuth**. Documented catalog: four tools (`list_locations`, `search_operations`, `describe_operation`, `execute_operation`). The original `/mcp/` registration is transitional.

2. **Community GHL MCP (Tier 2) — RETIRED [DATE]** — verified off: no registration, no loaded/enabled unit, no listener on `127.0.0.1:8765`, no `GHL_COMMUNITY_MCP_URL`. Do not reinstall or rebuild. Historical rollback reference only: mirror `trevorotts1/ghl-community-mcp-mirror`, pin `32628c979dd8f46e7952f85ce2d98f8028a26c32`, profile `curated` (43 crm tools, smoke `crm_list_workspaces`); restoration requires an explicit operator decision.

2b. **Custom courier MCP** — preserved; out of scope for skill 36.

3. **Tier 3 fallback** — GHL skill at `$MASTER_FILES_DIR/29-ghl-convert-and-flow/` (Mac default: `~/Downloads/openclaw-master-files/29-ghl-convert-and-flow/`; VPS default: `~/Downloads/openclaw-master-files/29-ghl-convert-and-flow/`). Pre-installed for all clients unless Section 1.B noted otherwise.

4. **Tier 4 fallback** — agent-browser (skill 03) FIRST, Playwright fallback, at `[client white-label URL]`.

5. **Tier 5 fallback** — Codex Computer Use, `codex/gpt-5.5`.

Decision table and full setup details in TOOLS.md. Cardinal operating rule (`GHL Tier Escalation Protocol`) lives in **AGENTS.md** (shared by all agents); SOUL.md is left unchanged.

### Credentials

- Location PIT stored as `GOHIGHLEVEL_API_KEY` in `~/.openclaw/secrets/.env` and `openclaw.json` env.vars.
- Location ID stored as `GOHIGHLEVEL_LOCATION_ID` in same locations.
- **Never echo these in chat logs.** Reference env-var names only.
```

### 8.5 What to add to USER.md (optional, if the file exists)

```markdown
## GHL / [Client brand]

- Brand white-label name (client-facing): [Brand]
- Internal name: GHL / GoHighLevel (use these for technical discussions)
- Aliases: GHL, GoHighLevel, Go High Level, LeadConnector, [Brand]
```

---

## 9. PHASE 8 — VERIFY WITH REAL TEST PROMPTS

Before declaring setup complete, run the agent through these tests. Each tests a different tier and verifies the disclosure header is being generated.

| # | Prompt | Expected disclosure header | Tests |
|---|--------|---------------------------|-------|
| 1 | "What's my business name, address, and main phone number on [Brand]?" | `[GHL tier used: 1 — list_locations]` (or the recorded operation name) | Tier 1 baseline |
| 2 | "How many products do I have in my [Brand] store right now?" | `[GHL tier used: 0 — convertandflow products list]` or `[GHL tier used: 3 — raw API GET /products/]` | Tier 0/3 — the community tier no longer exists |
| 3 | "How many recurring subscriptions do I have running right now, and what's the next one set to charge?" | `[GHL tier used: 3 — raw API GET /payments/subscriptions]` | Tier 3 routing |
| 4 | "Show me my last 5 payment transactions." | `[GHL tier used: 3 — raw API GET /payments/transactions]` | Trap: "payments" word; no Tier 2 tool exists |
| 5 | "Pull the webhook delivery log for my account from the last 24 hours." | Expect fall-through: `[GHL tier used: 3 (Tier 1 lacked operation) — raw API]` | Verifies clean Tier 1 → Tier 3 fall-through |

**Passing:** every prompt response opens with the correct disclosure header.
**Failing:** missing header → AGENTS.md (where the Tier Escalation Protocol + disclosure rule live) isn't loading into the agent's system prompt. Investigate channel-routing / bootstrap injection.
**Failing on wrong tier:** docs are loading but agent is misrouting. Tighten the canonical state block.

---

## 11. FINAL QC & COMPLETION VERIFICATION — RUN THIS BEFORE DECLARING DONE

This section is **mandatory**. Setup is not complete until the QC script below exits with status 0 and every assertion passes. Do not tell the client "it's done" until you have run this.

### 11.A The QC routine — what it checks

The script asserts each of these. Any failure = setup is incomplete:

1. **Platform detected correctly** — `$CANONICAL_MASTER` is set to the right path for this machine
2. **Master files folder exists** — `$MASTER_FILES_DIR` resolves to a real directory
3. **GHL skill exists inside master files** OR explicitly flagged as missing
4. **Both credentials are reachable** — `$GOHIGHLEVEL_API_KEY` starts with `pit-`, `$GOHIGHLEVEL_LOCATION_ID` is 22 chars
5. **Credentials are in BOTH locations** — secrets `.env` file AND `openclaw.json` env.vars
6. **Tier 1 MCP is registered** in `openclaw mcp list`; the documented OAuth path is recorded for the client this box runs
7. **The four documented tool names are recorded** (`list_locations`, `search_operations`, `describe_operation`, `execute_operation`) and a `tools/list` capture exists. **No tool count is asserted.**
8. **Tier 1 returns real location data** via a documented read
9. **Tier 2 is RETIRED** — `ghl-community-mcp` is ABSENT from `openclaw mcp list`
10. **No Tier 2 supervisor is loaded or enabled** (launchd / pm2 / systemd). A stopped `RunAtLoad=true` job is NOT retired
11. **No listener on `127.0.0.1:8765`**
12. **No probe restarts the retired service**
13. **`GHL_COMMUNITY_MCP_URL` is ABSENT** from `openclaw.json` env.vars
14. **AGENTS.md contains the Tier Escalation Protocol section** (relocated from SOUL.md; SOUL.md is left unchanged)
15. **AGENTS.md contains the canonical state block, the retirement state, and the tier-skip enforcement block**
16. **TOOLS.md records the retained MCP surfaces and the retirement state** (no community catalog asserted as live)
17. **MEMORY.md contains the install record for this client**
18. **This document is copied into `$MASTER_FILES_DIR/XX-ghl-mcp-setup/`**
19. **No PIT or Location ID is echoed in any .md or log file** (security)
20. **Secrets file is chmod 600**

### 11.B The bundled QC script — ships as `qc-ghl-mcp-setup.sh` in this folder

The QC script is the standalone file `qc-ghl-mcp-setup.sh` shipped alongside this reference. It is the single source of truth — do NOT extract a copy from this document or from QC.md (earlier versions of this skill embedded a copy here; the embedded copy is now removed to prevent drift, because the standalone has rate-limit probe logic and other v9.3.5+ additions that an extracted copy would silently lose).

### 11.C How to run

```bash
# Locate the master files folder (where install.sh placed the skill).
# Canonical on both Mac and VPS — use $HOME, never a quoted "~".
MASTER_FILES_DIR="$HOME/Downloads/openclaw-master-files"

chmod +x "$MASTER_FILES_DIR/36-ghl-mcp-setup/qc-ghl-mcp-setup.sh"
bash    "$MASTER_FILES_DIR/36-ghl-mcp-setup/qc-ghl-mcp-setup.sh"
```

What the script does (summary — read the source for details):
- Detects platform (Mac vs VPS) and resolves canonical secrets / config / workspace paths
- Sources `~/.openclaw/secrets/.env` (or `~/.openclaw/secrets/.env`), reads `GOHIGHLEVEL_API_KEY` (PIT) and `GOHIGHLEVEL_LOCATION_ID`
- Probes Tier 1 (Official MCP) — reachability and recorded tool names. **Do not assert a count**; the documented catalog is four tools
- Verifies Tier 2 retirement — `ghl-community-mcp` absent from `mcp.servers`, no loaded/enabled unit, no listener on `127.0.0.1:8765`, `GHL_COMMUNITY_MCP_URL` absent. The legacy ">= 500 tools / supervised" assertions are superseded by W07's retirement update; a failure there is the known-stale set and must never be fixed by reinstalling
- Probes Tier 3 (direct REST) — reads `X-RateLimit-Daily-Remaining` and surfaces the reset clock time in plain English if quota is low (v9.3.5 incident-response logic)
- Asserts AGENTS.md / TOOLS.md / MEMORY.md contain the canonical state block and disclosure-header protocol, and that SOUL.md does NOT carry the legacy protocol (relocated to AGENTS.md in v1.1.0)
- Verifies secrets file is `chmod 600` and the PIT does not appear in any tracked `.md` file

Exit code 0 = all clear. Non-zero = the script prints which assertions failed and why; fix and re-run.

### 11.D Pass/fail thresholds

| Result | Meaning | What to do |
|---|---|---|
| Exit 0, 0 warnings | All clear | Tell the client setup is complete. Ask for the 5 test prompts from Phase 8 to be run. |
| Exit 0, warnings only | Setup is technically complete but some non-critical things flagged | Review warnings with the client. Likely candidates: GHL skill missing (= Tier 3 disabled), retirement receipt not filed, etc. A "community tool count" warning is stale and must not be fixed by reinstalling. |
| Exit 1, any failures | Setup is INCOMPLETE | Read the failure list, fix each one, re-run. Do NOT tell the client "done" until exit 0. |

### 11.E Self-audit — agent's own honesty check

Before running the QC script, the agent must answer these honestly. If any answer is "no" or "I'm not sure," fix it before claiming done:

1. Did I actually run every smoke test in Phases 5 and 6, or did I assume they would pass?
2. Did I verify the .md edits landed (read the files back), or did I trust the Edit tool?
3. Did I run the agent through at least one Phase 8 test prompt and observe the disclosure header?
4. Is the launchd / systemd service genuinely running, or did I just bootstrap and assume?
5. Did I copy this setup doc to `$MASTER_FILES_DIR` for the next install?
6. Did any output anywhere contain the PIT in cleartext that the client would object to?

If you can't answer all six with a confident "yes," the setup is not done. Loop back.

---

## REFERENCE A — OFFICIAL GHL MCP: LEGACY `/mcp/` TOOL NAMES BY DOMAIN

**The documented catalog is four tools:** `list_locations`, `search_operations`,
`describe_operation`, `execute_operation`. The per-operation names below were observed against
the transitional `https://services.leadconnectorhq.com/mcp/` on 2026-05-13. They are
**UNVERIFIED** as current catalog and are not a count contract. Do not cite them as the
official catalog; discover operations with `search_operations`.

### Contacts (8 tools)
- `contacts_get-contact` — Retrieve full contact profile by contact ID (personal details, contact info, tags, custom fields)
- `contacts_get-contacts` — Paginated list of contacts; supports name/email/phone search and tag/location filtering
- `contacts_create-contact` — Create a new contact record with personal and business info
- `contacts_update-contact` — Modify existing contact (any property)
- `contacts_upsert-contact` — Create-or-update using duplicate detection
- `contacts_add-tags` — Append tags to a contact (preserves existing tags)
- `contacts_remove-tags` — Remove specific tags from a contact (preserves others)
- `contacts_get-all-tasks` — List all tasks attached to a contact

### Conversations (3 tools)
- `conversations_search-conversation` — Filter conversations by contact, assignee, followers, mentions, status, message type
- `conversations_send-a-new-message` — Send SMS, Email, WhatsApp, Instagram, Facebook, Custom, or Live Chat message
- `conversations_get-messages` — Retrieve messages from a conversation with optional type filtering

### Opportunities (4 tools)
- `opportunities_get-opportunity` — Get full opportunity by ID
- `opportunities_update-opportunity` — Modify name, pipeline, stage, status, monetary value
- `opportunities_search-opportunity` — Filter by pipeline, stage, contact, custom fields
- `opportunities_get-pipelines` — List all sales pipelines (ID, name, stages, visibility)

### Calendars (2 tools)
- `calendars_get-calendar-events` — Events/appointments within a time range; filter by user/group/calendar
- `calendars_get-appointment-notes` — Paginated notes for a specific appointment

### Locations / Sub-accounts (2 tools)
- `locations_get-location` — Full sub-account details (name, address, business info, social, settings)
- `locations_get-custom-fields` — Custom fields for the location; filter by model (contact, opportunity, etc.)

### Blogs (7 tools)
- `blogs_check-url-slug-exists` — Validate slug availability before publishing
- `blogs_get-blog-post` — Retrieve blog posts for a blog site (filter by publication state, paginated)
- `blogs_get-blogs` — List blog sites for a location (paginated, search)
- `blogs_get-all-categories-by-location` — All blog categories for a location (paginated)
- `blogs_get-all-blog-authors-by-location` — All blog authors for a location (paginated)
- `blogs_create-blog-post` — Create blog post with full content + metadata
- `blogs_update-blog-post` — Modify content, metadata, categories, tags, publication settings

### Emails (2 tools)
- `emails_fetch-template` — List email templates with filtering by name/folder
- `emails_create-template` — New template (HTML, builder, blank, folder, imported types)

### Social Media Posting (6 tools)
- `social-media-posting_create-post` — New social post across FB/IG/Twitter/LinkedIn/Google/TikTok
- `social-media-posting_edit-post` — Modify existing post (content, media, schedule, platform settings)
- `social-media-posting_get-post` — Full post details by ID
- `social-media-posting_get-posts` — List posts with filtering (recent, all, scheduled), paginated
- `social-media-posting_get-account` — Connected social accounts and groups for a location
- `social-media-posting_get-social-media-statistics` — 7-day analytics with previous-period comparison

### Payments (2 tools — read-only)
- `payments_get-order-by-id` — Full order details by order ID
- `payments_list-transactions` — Paginated transactions with payment mode, date, status filters

**Observed: 36 legacy per-operation names on that endpoint (2026-05-13).** That is an
observation, not an interface. The documented catalog is four tools. For products, invoices,
subscriptions/schedules, estimates, coupons, store, Voice AI, Phone System, or Agent Studio,
use Tier 0 (CLI) or Tier 3 (REST) — Tier 2 is retired.

---

## REFERENCE B — RETIRED COMMUNITY MCP: HISTORICAL TOOL SURFACE (DO NOT INSTALL)

**This entire section is historical.** The community MCP is retired; fresh installs omit it and
updated boxes verify it is off. The list below was observed against a `full`-profile
BusyBee3333 fork on 2026-05-13 via `GET /tools`. The vetted fleet profile was `curated` =
**43 crm tools** (smoke `crm_list_workspaces`), so most names below did not exist under the
profile the fleet actually ran. The 588 / 858 / 500 figures describe other profiles or history
and prove nothing about parity. Historical rollback pin:
`32628c979dd8f46e7952f85ce2d98f8028a26c32`; archive path is recorded in the box's retirement
receipt. Restoration requires an explicit operator decision.

### CREATE (79)
create_contact, create_contact_task, create_contact_note, create_conversation, create_blog_post, create_opportunity, create_calendar, create_appointment, create_block_slot, create_calendar_group, create_appointment_note, create_calendar_resource_equipment, create_calendar_resource_room, create_calendar_notifications, create_email_template, create_location, create_location_tag, create_location_custom_field, create_location_custom_value, create_recurring_task, create_social_post, create_media_folder, create_object_schema, create_object_record, ghl_create_association, ghl_create_relation, ghl_create_custom_field, ghl_create_custom_field_folder, ghl_create_survey, ghl_create_shipping_zone, ghl_create_shipping_rate, ghl_create_shipping_carrier, ghl_create_store_setting, ghl_create_product, ghl_create_price, ghl_create_product_collection, create_affiliate_campaign, create_affiliate, create_payout, create_business, create_campaign, create_company, create_course_importer, create_course_product, create_course_category, create_course, create_course_post, create_course_offer, create_funnel_redirect, create_invoice_template, create_invoice_schedule, create_invoice, create_estimate, create_invoice_from_estimate, create_link, create_whitelabel_integration_provider, create_order_fulfillment, create_coupon, create_custom_provider_integration, create_custom_provider_config, create_ivr_menu, create_smart_list, create_snapshot, create_snapshot_share_link, create_sms_template, create_voicemail_template, create_social_template, create_whatsapp_template, create_snippet, create_trigger, create_user, create_webhook, ghl_create_byoc_trunk, create_voice_ai_agent, create_voice_ai_action, create_custom_menu, create_billing_charge, ghl_create_agent, ghl_create_workflow

### GET (195)
get_contact, get_contact_tasks, get_contact_task, get_contact_notes, get_contact_note, get_duplicate_contact, get_contacts_by_business, get_contact_appointments, get_conversation, get_recent_messages, get_email_message, get_message, get_message_recording, get_message_transcription, get_blog_posts, get_blog_sites, get_blog_authors, get_blog_categories, get_pipelines, get_opportunity, get_calendar_groups, get_calendars, get_calendar, get_calendar_events, get_free_slots, get_appointment, get_appointment_notes, get_calendar_resources_equipments, get_calendar_resource_equipment, get_calendar_resources_rooms, get_calendar_resource_room, get_calendar_notifications, get_calendar_notification, get_blocked_slots, get_email_campaigns, get_email_templates, get_location, get_location_tags, get_location_tag, get_location_custom_fields, get_location_custom_field, get_location_custom_values, get_location_custom_value, get_location_templates, get_timezones, get_recurring_task, ghl_get_domain_dns_records, ghl_get_email_stats, get_social_post, get_social_accounts, get_csv_upload_status, get_social_categories, get_social_category, get_social_tags, get_social_tags_by_ids, get_platform_accounts, get_social_media_statistics, get_media_files, get_all_objects, get_object_schema, get_object_record, ghl_get_all_associations, ghl_get_association_by_id, ghl_get_association_by_key, ghl_get_association_by_object_key, ghl_get_relations_by_record, ghl_get_custom_field_by_id, ghl_get_custom_fields_by_object_key, ghl_get_workflows, ghl_get_workflow, ghl_get_workflow_executions, ghl_get_surveys, ghl_get_survey_submissions, ghl_get_survey, ghl_get_survey_submission, ghl_get_survey_stats, ghl_get_shipping_zone, ghl_get_available_shipping_rates, ghl_get_shipping_rate, ghl_get_shipping_carrier, ghl_get_store_setting, ghl_get_product, get_affiliate_campaigns, get_affiliate_campaign, get_affiliates, get_affiliate, get_affiliate_commissions, get_affiliate_stats, get_payouts, get_referrals, get_businesses, get_business, get_campaigns, get_campaign, get_campaign_stats, get_campaign_recipients, get_scheduled_messages, get_companies, get_company, get_course_importers, get_course_products, get_course_product, get_course_categories, get_courses, get_course, get_course_instructors, get_course_posts, get_course_post, get_course_offers, get_course_enrollments, get_student_progress, get_forms, get_form_submissions, get_form_by_id, get_funnels, get_funnel, get_funnel_pages, get_funnel_redirects, get_invoice_template, get_invoice_schedule, get_invoice, get_links, get_link, get_order_by_id, get_transaction_by_id, get_subscription_by_id, get_coupon, get_custom_provider_config, get_order_notes, get_phone_numbers, get_phone_number, get_call_forwarding_settings, get_ivr_menus, get_voicemail_settings, get_voicemails, get_caller_ids, get_attribution_report, get_call_reports, get_appointment_reports, get_pipeline_reports, get_email_reports, get_sms_reports, get_funnel_reports, get_ad_reports, get_agent_reports, get_dashboard_stats, get_conversion_reports, get_revenue_reports, get_reviews, get_review, get_review_stats, get_review_requests, get_connected_review_platforms, get_review_links, get_review_widget_settings, get_saas_locations, get_saas_location, get_saas_agency_plans, get_saas_subscription, get_saas_plan, get_smart_lists, get_smart_list, get_smart_list_contacts, get_smart_list_count, get_snapshots, get_snapshot, get_snapshot_push_status, get_latest_snapshot_push, get_sms_templates, get_sms_template, get_voicemail_templates, get_social_templates, get_whatsapp_templates, get_snippets, get_triggers, get_trigger, get_trigger_types, get_trigger_logs, get_users, get_user, get_webhooks, get_webhook, get_webhook_events, get_webhook_logs, ghl_get_phone_number, ghl_get_call_recording, ghl_get_voicemail, ghl_get_byoc_trunk, get_voice_ai_agent, get_voice_ai_action, get_voice_ai_call_log, get_custom_menu, get_billing_charge, ghl_get_agent, ghl_get_workflow_full

### UPDATE (73)
update_contact, update_contact_task, update_task_completion, update_contact_note, update_conversation, update_message_status, update_blog_post, update_opportunity_status, update_opportunity, update_calendar, update_appointment, update_block_slot, update_calendar_group, update_appointment_note, update_calendar_resource_equipment, update_calendar_resource_room, update_calendar_notification, update_email_template, update_location, update_location_tag, update_location_custom_field, update_location_custom_value, update_recurring_task, update_social_post, update_media_file, update_object_schema, update_object_record, ghl_update_association, ghl_update_custom_field, ghl_update_custom_field_folder, ghl_update_workflow_status, ghl_update_survey, ghl_update_shipping_zone, ghl_update_shipping_rate, ghl_update_shipping_carrier, ghl_update_product, update_affiliate_campaign, update_affiliate, update_business, update_campaign, update_company, update_course_product, update_course_category, update_course, update_course_post, update_course_offer, update_lesson_completion, update_funnel_redirect, update_invoice_template, update_link, update_coupon, update_phone_number, update_call_forwarding, update_ivr_menu, update_voicemail_settings, update_review_reply, update_review_links, update_review_widget_settings, update_saas_subscription, update_smart_list, update_sms_template, update_snippet, update_trigger, update_user, update_webhook, ghl_update_phone_number, update_voice_ai_agent, update_voice_ai_action, update_custom_menu, ghl_update_agent, ghl_update_agent_version, ghl_update_workflow_actions, update_opportunity

### DELETE (69)
delete_contact, delete_contact_task, delete_contact_note, delete_conversation, delete_opportunity, delete_calendar, delete_appointment, delete_calendar_group, delete_appointment_note, delete_calendar_resource_equipment, delete_calendar_resource_room, delete_calendar_notification, delete_email_template, delete_location, delete_location_tag, delete_location_custom_field, delete_location_custom_value, delete_location_template, delete_recurring_task, ghl_delete_email_domain, delete_social_post, delete_social_account, delete_media_file, delete_object_record, ghl_delete_association, ghl_delete_relation, ghl_delete_custom_field, ghl_delete_custom_field_folder, ghl_delete_workflow, ghl_delete_survey, ghl_delete_shipping_zone, ghl_delete_shipping_rate, ghl_delete_shipping_carrier, ghl_delete_product, delete_affiliate_campaign, delete_affiliate, delete_business, delete_campaign, delete_company, delete_course_product, delete_course_category, delete_course, delete_course_post, delete_course_offer, delete_funnel_redirect, delete_invoice_template, delete_link, delete_coupon, delete_custom_provider_integration, delete_ivr_menu, delete_voicemail, delete_caller_id, delete_review_reply, delete_smart_list, delete_sms_template, delete_voicemail_template, delete_social_template, delete_whatsapp_template, delete_snippet, delete_trigger, delete_user, delete_webhook, delete_voice_ai_agent, delete_voice_ai_action, delete_custom_menu, delete_marketplace_installation, delete_billing_charge, ghl_delete_agent

### LIST (37)
ghl_list_email_domains, ghl_list_email_providers, ghl_list_workflows, ghl_list_survey_submissions, ghl_list_shipping_zones, ghl_list_shipping_rates, ghl_list_shipping_carriers, ghl_list_products, ghl_list_prices, ghl_list_inventory, ghl_list_product_collections, list_invoice_templates, list_invoice_schedules, list_invoices, list_estimates, list_whitelabel_integration_providers, list_orders, list_order_fulfillments, list_transactions, list_subscriptions, list_coupons, list_saas_locations_by_company, list_number_pools, list_active_numbers_by_location, ghl_list_phone_numbers, ghl_list_call_recordings, ghl_list_byoc_trunks, list_voice_ai_agents, list_voice_ai_call_logs, list_proposals_documents, list_proposal_templates, list_custom_menus, list_marketplace_installations, list_billing_charges, ghl_list_agents, ghl_list_agent_versions, ghl_list_workflows_full

### VIEW (34 — UI launcher tools)
view_contact_grid, view_pipeline_board, view_quick_book, view_opportunity_card, view_calendar, view_invoice, view_campaign_stats, view_agent_stats, view_contact_timeline, view_workflow_status, view_dashboard, view_conversation_inbox, view_phone_log, view_course_manager, view_store_front, view_payment_dashboard, view_social_media_hub, view_reputation_monitor, view_funnel_builder, view_form_manager, view_email_center, view_blog_manager, view_affiliate_dashboard, view_workflow_builder, view_reporting_hub, view_smart_list_manager, view_custom_fields_manager, view_media_library, view_location_settings, view_user_manager, view_voice_ai_console, view_proposal_builder, view_saas_admin, view_link_trigger_manager

### SEARCH (11)
search_contacts, search_conversations, search_opportunities, search_locations, search_location_tasks, search_social_posts, search_object_records, search_links, search_available_numbers, search_users, ghl_search_available_numbers

### SEND (7)
send_sms, send_email, send_invoice, send_estimate, send_review_request, send_proposal_document, send_proposal_template

### ADD (10)
add_contact_tags, add_contact_followers, add_contact_to_campaign, add_contact_to_workflow, add_inbound_message, add_outbound_call, add_opportunity_followers, ghl_add_email_domain, add_course_instructor, add_caller_id

### REMOVE (7)
remove_contact_tags, remove_contact_followers, remove_contact_from_campaign, remove_contact_from_all_campaigns, remove_contact_from_workflow, remove_opportunity_followers, remove_course_enrollment

### BULK (8)
bulk_update_contact_tags, bulk_update_contact_business, bulk_delete_social_posts, bulk_update_media_files, bulk_delete_media_files, ghl_bulk_edit_products, bulk_disable_saas, bulk_enable_saas

### UPLOAD (4)
upload_message_attachments, upload_social_csv, upload_media_file, upload_form_custom_files

### OTHER VERBS (each 1–4 tools)
- **upsert (2):** upsert_contact, upsert_opportunity
- **cancel (3):** cancel_scheduled_message, cancel_scheduled_email, cancel_scheduled_campaign_message
- **pause / resume (3):** pause_campaign, pause_saas_location, resume_campaign
- **start (2):** start_social_oauth, start_campaign
- **enable / disable (4):** enable_saas_location, enable_trigger, disable_calendar_group, disable_trigger
- **duplicate (2):** duplicate_smart_list, duplicate_trigger
- **trigger (1):** ghl_trigger_workflow
- **publish (1):** ghl_publish_workflow
- **clone (1):** ghl_clone_workflow
- **deploy (1):** ghl_deploy_agent
- **approve / reject (2):** approve_affiliate, reject_affiliate
- **buy / purchase / release (4):** ghl_buy_phone_number, purchase_phone_number, release_phone_number, ghl_release_phone_number
- **configure (1):** ghl_configure_call_forwarding
- **connect / disconnect (3):** connect_google_business, disconnect_custom_provider_config, disconnect_review_platform
- **count (1):** count_funnel_pages
- **check (2):** check_url_slug, check_billing_funds
- **download (1):** download_transcription
- **enroll (1):** enroll_contact_in_course
- **filter (1):** filter_users_by_email
- **generate (3):** generate_invoice_number, generate_estimate_number, generate_ghl_view
- **live (1):** live_chat_typing
- **push (1):** push_snapshot_to_subaccounts
- **rebilling (1):** rebilling_update
- **record (1):** record_order_payment
- **reply (1):** reply_to_review
- **retry (1):** retry_webhook
- **set (3):** ghl_set_default_email_provider, set_csv_accounts, set_social_media_accounts
- **test (2):** test_trigger, test_webhook
- **validate (1):** validate_group_slug
- **verify (3):** verify_email, ghl_verify_email_domain, verify_caller_id

**Historical total: 588 names in the `full` profile.** There is no live endpoint to query and
no count to chase. The service must be absent.

---

## REFERENCE C — TROUBLESHOOTING CHEAT SHEET

| Symptom | Likely cause | Fix |
|---|---|---|
| Community `/health` answers | The box is **not retired** | Finish retirement: unset registration, unload **and disable** the unit, remove the probe. Do not restart it "to check" |
| `/health` returns Cognee's response (`status:ready, version:0.5.3-local`) | Port 8000 is Cognee | Never use 8000 for GHL. The retired community port was 8765; nothing should listen there now |
| A doc tells you to rebuild because fewer than 588 tools appear | Stale installation instruction | Ignore it. The service is retired; there is no count to reach. Verify absence, not a tool count |
| Official tool call returns "not found" | Operation not exposed on this connection | Discover with `search_operations` and inspect with `describe_operation`; never guess a tool id |
| 401 / 403 on Tier 1 | OAuth grant or scope problem | Re-authorize in the client; record a fresh `tools/list`. Not a PIT fix |
| 401 / 403 on Tier 3 | PIT lacks scope, or PIT was rotated | Check the PIT in `~/.openclaw/secrets/.env` and `openclaw.json` env.vars. This is the REST credential, not the MCP one |
| Agent tries Tier 2 | Stale session context or stale docs | Start a fresh session; verify AGENTS.md carries the retirement state. Do not "restore" Tier 2 |
| Agent hardcodes a port for GHL | Stale memory of the retired service | There is no community URL env var. The correct state is no listener; a port literal is a bug |
| `launchctl bootstrap` fails with "service already loaded" | Plist already loaded from a previous boot | `bootout` it, then **disable** the label and archive the plist. Do not bootstrap it again |
| WorkflowBuilderTools init warning on boot | Historical community-service behaviour | Not applicable — the service is retired. Build workflows through Skill 44 |

---

## REFERENCE D — MCPORTER (OPTIONAL)

**Not required for GHL setup.** `openclaw mcp set` handles registration natively. MCPorter is a config manager that adds these capabilities:

- Auto-discover MCP servers already configured in Cursor / Claude Code / Claude Desktop / Codex / local overrides
- Call MCPs as if they were typed TypeScript functions
- Package MCPs as standalone CLIs
- Import / export MCP configurations across machines

Install if needed:
```bash
# Try without install
npx @openclaw/mcporter --help

# Or install globally
npm i -g @openclaw/mcporter

# Auto-import already-configured MCP servers from common clients
mcporter config import --from cursor
mcporter config import --from claude-desktop
mcporter config import --from openclaw

# List configured MCPs
mcporter config list
```

Source: https://github.com/openclaw/mcporter

---

## APPENDIX — SECURITY CHECKLIST (DO THIS BEFORE DECLARING SETUP COMPLETE)

- [ ] PIT stored in `~/.openclaw/secrets/.env` with `chmod 600` (REST credential — Tier 0/3)
- [ ] No unarchived community `.env`; any archived copy carries a redacted manifest (key names only)
- [ ] Official MCP authorized by **OAuth**; no PIT is taught as an equivalent MCP credential
- [ ] No PIT, OAuth token, Location ID, or account id echoed into chat logs, commit history, or shared docs
- [ ] `~/.openclaw/secrets/` and any archived `*/.env` listed in `.gitignore` for tracked repos
- [ ] `GHL_COMMUNITY_MCP_URL` env var **absent** from `openclaw.json` env.vars
- [ ] No retired launchd/systemd unit is loaded or enabled; archived logs checked for leaked auth; no listener on 8765
- [ ] Official smoke test passes with real data; retirement checks pass; **custom courier MCP still present**
- [ ] All 5 test prompts (Phase 8) produce correct disclosure headers and none says Tier 2
- [ ] This document copied to `$MASTER_FILES_DIR/XX-ghl-mcp-setup/` (Mac: `~/Downloads/openclaw-master-files/XX-ghl-mcp-setup/`; VPS: `~/Downloads/openclaw-master-files/XX-ghl-mcp-setup/`) for future re-use

---

## END

If anything is unclear or fails to work as described, first run:
```bash
openclaw doctor
openclaw mcp list
launchctl print gui/$(id -u)/com.clawd.ghl-mcp >/dev/null 2>&1 && echo "STILL LOADED" || echo "community: not loaded"
lsof -nP -iTCP:8765 -sTCP:LISTEN 2>/dev/null | grep -q LISTEN && echo "LISTENER STILL PRESENT" || echo "listener: absent"
```

Then check the troubleshooting cheat sheet (Reference C) before falling back to manual debugging.
