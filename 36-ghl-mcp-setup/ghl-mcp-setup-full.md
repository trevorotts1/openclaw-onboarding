# GoHighLevel MCP Setup — Universal Agent Instructions

**Audience:** an AI agent (OpenClaw, Claude Code, or any MCP-aware client) setting up GoHighLevel access for a new client.
**Last verified:** 2026-05-13 against live `services.leadconnectorhq.com/mcp/` (36 tools) and `busybee3333/Go-High-Level-MCP-2026-Complete` (588 tools).

---

## 0. WHAT THIS IS AND HOW TO USE IT

You are an AI agent. You have been asked to set up GoHighLevel (GHL) integration for a client. Follow this document end-to-end. Do not skip phases. Do not improvise on tier order. The whole point is a clean, layered fallback chain so that ANY GHL task can be served by the cheapest tier that works.

### Aliases (treat all of these as the same platform)
- GHL
- GoHighLevel
- Go High Level
- LeadConnector (`leadconnectorhq.com` is GHL's API host)
- The client's white-label name (e.g. "Convert and Flow", "Your Brand CRM"). Ask the client what they call it.

### The 6-tier access chain you are setting up

| Tier | What | When |
|------|------|------|
| 0 | Convert and Flow CLI (`caf`/`convertandflow`/`ghl`, skill 44) — PRIMARY | Contacts, opportunities, calendars, conversations, documents, payments, forms, social, locations, workflow READS (PIT); workflow BUILD/EDIT (Firebase token). The cheapest, fastest path — no MCP overhead, no manual UI. |
| 1 | Official GHL MCP (hosted by GHL, 36 tools) | Blogs + anything the CLI doesn't cover among contacts, calendars, conversations, opportunities, social media, emails, locations, read-only payments |
| 2 | Community GHL MCP (local, 588 tools) | Products, invoices, billing, subscriptions, estimates, store, coupons, Voice AI, Phone System, Agent Studio, full payments |
| 3 | Direct REST API (GHL skill in `openclaw-master-files/29-ghl-convert-and-flow/`) | Anything neither the CLI nor either MCP covers; media uploads (`POST /medias/upload-file`) |
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
[ ]  4    Verified current Official MCP endpoint via web fetch
[ ]  4    Verified Community MCP repo latest commit / tool count

TIER 1 INSTALL
[ ]  5    `openclaw mcp set ghl-mcp` succeeded
[ ]  5    `tools/list` returns 36 tools
[ ]  5    `locations_get-location` returns real location data

TIER 2 INSTALL
[ ]  6    Port selected (default 8765; confirmed free with lsof)
[ ]  6    Repo cloned to ~/mcp-servers/ghl-community-mcp (or VPS equivalent)
[ ]  6    `npm install` completed without errors
[ ]  6    `npm run build` produced dist/main.js
[ ]  6    .env file written with correct PIT + Location ID + port + chmod 600
[ ]  6    GHL_COMMUNITY_MCP_URL env var set in openclaw.json
[ ]  6    launchd plist (macOS) OR systemd unit (Linux/VPS) installed + loaded
[ ]  6    Service shows state=running after bootstrap/start
[ ]  6    `openclaw mcp set ghl-community-mcp` registered the URL
[ ]  6    /health returns tools:588
[ ]  6    /execute call with real tool returns real GHL data

FALLBACK TIERS
[ ]  7    GHL skill at $MASTER_FILES_DIR/[skill folder] confirmed readable
[ ]  7    Playwright route documented (Tier 4)
[ ]  7    Codex Computer Use available (Tier 5)

CORE FILES WIRED
[ ]  8    SOUL.md updated with Tier Escalation Protocol
[ ]  8    AGENTS.md updated with canonical state block + tier order + anti-patterns
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
# Detect platform — VPS is the one with ~/.openclaw populated
if [ -d "~/.openclaw" ]; then
  PLATFORM="vps"
  CANONICAL_MASTER="~/Downloads/openclaw-master-files"
else
  PLATFORM="desktop"
  CANONICAL_MASTER="$HOME/Downloads/openclaw-master-files"
fi
echo "Platform detected: $PLATFORM"
echo "Canonical path if missing: $CANONICAL_MASTER"

# Search across all reasonable roots for the folder, tolerating spelling variants
MASTER_FILES_DIR=""
ROOTS=(
  "$HOME/Downloads"        # macOS / Linux desktop canonical
  "~/Downloads"        # VPS canonical
  "/root/Downloads"        # some root-shell VPS setups
  "/data"                  # in case it was placed at the volume root
  "$HOME"                  # in case the client dropped it in home
  "$HOME/clawd"            # in case it lives next to the workspace
  "~/clawd"            # VPS twin of above
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
# Resolve platform-correct paths first
if [ -d "~/.openclaw" ]; then
  SECRETS_ENV="~/.openclaw/secrets/.env"
  CONFIG_JSON="~/.openclaw/openclaw.json"
  WORKSPACE="~/clawd"
else
  SECRETS_ENV="$HOME/.openclaw/secrets/.env"
  CONFIG_JSON="$HOME/.openclaw/openclaw.json"
  WORKSPACE="$HOME/clawd"
fi

# 1. OpenClaw secrets file (canonical — same names on Mac and VPS, different paths)
cat "$SECRETS_ENV" 2>/dev/null | grep -iE "GHL|GOHIGH|LEADCONN|LOCATION_ID|PIT|PRIVATE_INTEGRATION"

# 2. OpenClaw main config env block
python3 -c "
import json
cfg=json.load(open('$CONFIG_JSON'))
ev=cfg.get('env',{}).get('vars',{})
hits={k:v for k,v in ev.items() if any(s in k.upper() for s in ['GHL','GOHIGH','LEADCONN','LOCATION'])}
for k,v in hits.items():
    redacted=str(v)[:8]+'...' if isinstance(v,str) and len(str(v))>12 else v
    print(f'{k} = {redacted}')
"

# 3. Live process env
printenv | grep -iE "GHL|GOHIGH|LEADCONN|LOCATION_ID" | sed 's/=\(.\{0,10\}\).*/=\1.../'

# 4. Home-level dotfile
cat ~/.env 2>/dev/null | grep -iE "GHL|GOHIGH|LEADCONN|LOCATION"

# 5. clawd / repo-level env files
grep -riE "GHL_API_KEY|GOHIGHLEVEL_API_KEY|GHL_LOCATION_ID|GOHIGHLEVEL_LOCATION_ID|leadconnector" \
  "$WORKSPACE"/.env* "$WORKSPACE"/*/.env* 2>/dev/null | head -20

# 6. openclaw-master-files (uses the $MASTER_FILES_DIR from Section 1.B)
grep -riE "GHL_API_KEY|GOHIGHLEVEL_API_KEY|GHL_LOCATION_ID|GOHIGHLEVEL_LOCATION_ID" \
  "$MASTER_FILES_DIR/" 2>/dev/null | head -10

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
# Pick the right secrets path for this platform
if [ -d "~/.openclaw" ]; then
  SECRETS_DIR="~/.openclaw/secrets"
else
  SECRETS_DIR="$HOME/.openclaw/secrets"
fi

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
- **Community MCP repo (active fork):** https://github.com/busybee3333/Go-High-Level-MCP-2026-Complete
- **Community MCP original:** https://github.com/mastanley13/GoHighLevel-MCP
- **MCPorter (optional config manager):** https://github.com/openclaw/mcporter

Confirm:
- Official MCP endpoint URL is still `https://services.leadconnectorhq.com/mcp/`
- Required header versions (currently `Version: 2021-07-28`; some legacy endpoints use `2021-04-15`)
- Whether the BusyBee3333 fork's tool count has changed since 2026-05-13 (was 588)

---

## 5. PHASE 4 — SET UP TIER 1 (OFFICIAL GHL MCP)

The official MCP is **hosted by GHL** — no local install, no deployment. Just register it with OpenClaw.

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

### Verify Tier 1 works

```bash
# Initialize handshake — server is STATELESS, no Mcp-Session-Id needed
curl -sS -X POST "https://services.leadconnectorhq.com/mcp/" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "locationId: $GOHIGHLEVEL_LOCATION_ID" \
  -H "Version: 2021-07-28" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | grep "^data:" | sed 's/^data: //' | python3 -m json.tool

# Expect: 36 tools listed
```

### Real-data smoke test

```bash
curl -sS -X POST "https://services.leadconnectorhq.com/mcp/" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "locationId: $GOHIGHLEVEL_LOCATION_ID" \
  -H "Version: 2021-07-28" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"locations_get-location\",\"arguments\":{\"locationId\":\"$GOHIGHLEVEL_LOCATION_ID\"}}}" \
  | grep "^data:" | sed 's/^data: //' | python3 -m json.tool

# Expect: success:true, location:{name, address, phone, email...}
```

### Critical detail: official MCP is STATELESS

It returns `event: message\ndata: {...}` (SSE-framed) but does NOT issue an `Mcp-Session-Id` header. **Do not gate follow-up calls on a session ID** — there isn't one. Each request is independent.

---

## 6. PHASE 5 — SET UP TIER 2 (COMMUNITY GHL MCP)

The community MCP runs **locally on the client's machine**. We use the BusyBee3333 2026 fork (588 tools — significantly expanded over the original mastanley13 269-tool version).

### 6.1 Choose a port that doesn't collide

Default port is `8000`, but Cognee and many other dev tools also use `8000`. **Check what's free:**

```bash
# Pick the first free port from this list
for p in 8765 8766 8888 8001 8002; do
  if ! lsof -i :$p >/dev/null 2>&1; then echo "Free: $p"; break; fi
done
```

Recommend `8765` as default — memorable, low collision risk, used in reference implementations.

### 6.2 Clone, install, build

```bash
mkdir -p ~/mcp-servers
cd ~/mcp-servers
git clone https://github.com/busybee3333/Go-High-Level-MCP-2026-Complete.git ghl-community-mcp
cd ghl-community-mcp
npm install --no-audit --no-fund
npm run build   # builds dist/main.js and dist/app-ui/
```

**Idempotency note:** Section 6 is safe to re-run. The locator at the top of the script (`git clone`) will fail if the repo already exists, but you can detect that and `git pull` instead:

```bash
if [ -d ~/mcp-servers/ghl-community-mcp/.git ]; then
  cd ~/mcp-servers/ghl-community-mcp && git pull && npm install && npm run build
else
  mkdir -p ~/mcp-servers && cd ~/mcp-servers
  git clone https://github.com/busybee3333/Go-High-Level-MCP-2026-Complete.git ghl-community-mcp
  cd ghl-community-mcp && npm install --no-audit --no-fund && npm run build
fi
```

The `.env` write (Section 6.3) overwrites — if you re-run, your existing values are clobbered. Check and skip if it already exists:

```bash
[ -f ~/mcp-servers/ghl-community-mcp/.env ] && echo "EXISTS — backup before overwrite" || echo "OK to write"
```

The launchd plist (Section 6.5) install is idempotent if you `bootout` before `bootstrap`. The OpenClaw MCP registration (Section 6.7) is idempotent — `mcp set` overwrites cleanly.

### 6.2.1 Common install failures and how to recover

| Symptom | Cause | Fix |
|---|---|---|
| `npm install` fails with `EACCES` | npm cache permission issue | `sudo chown -R $(whoami) ~/.npm` then retry |
| `npm install` fails with `node-gyp` errors | Native module compile needs Xcode CLT (Mac) or build-essential (Linux) | Mac: `xcode-select --install`. Linux: `sudo apt install build-essential python3` |
| `npm install` hangs forever | Slow registry or network | Add `--prefer-offline --no-audit --no-fund --no-progress` or set `npm config set registry https://registry.npmjs.org/` |
| `npm run build` fails — "Cannot find module 'typescript'" | Devependencies missing | Re-run `npm install` (full, not `--production`) |
| Build succeeds but `dist/main.js` not present | Wrong build script — older fork uses `dist/server.js` | `ls dist/` to confirm entrypoint; update launchd plist accordingly |
| `npm run build` UI step fails — vite or React error | Node version too old | Require Node ≥ 20 (`node --version`); use `nvm install 22` if older |
| Port 8765 reported free but server crashes on bind | IPv6 vs IPv4 mismatch, or systemd-resolved on Linux holding it | Force IPv4 in `.env`: `MCP_SERVER_HOST=0.0.0.0`. Or pick a different port from the list in 6.1 |
| `launchctl bootstrap` returns "service already loaded" | Plist already loaded from previous boot | `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.clawd.ghl-mcp.plist` first, then bootstrap |
| `launchctl bootstrap` succeeds but service immediately exits | Path to node in plist is wrong (Apple Silicon vs Intel Mac) | Apple Silicon: `/opt/homebrew/bin/node`. Intel: `/usr/local/bin/node`. Check with `which node` and update plist |
| systemd `Failed to start ghl-mcp.service` | Wrong user or path in unit file | `journalctl -u ghl-mcp -n 50` reveals the line; fix in `/etc/systemd/system/ghl-mcp.service` |
| /health returns Cognee's response | Wrong port — Cognee occupies 8000 | Update `MCP_SERVER_PORT` in .env + `GHL_COMMUNITY_MCP_URL` env var + restart |
| /tools returns < 588 | Tool registry init failed during boot — check logs | `tail -50 ~/Library/Logs/ghl-mcp/stderr.log` (Mac) or `journalctl -u ghl-mcp -n 50` (Linux) |
| Server boots but real tool call returns 401 | PIT in .env doesn't match Location ID, or PIT was rotated | Re-verify both values from `~/.openclaw/secrets/.env`; rotate PIT in GHL if needed |
| `npm install` complains about peer-deps for `@modelcontextprotocol/sdk` | Strict peer-dep policy in npm 9+ | Add `--legacy-peer-deps` flag |

### 6.3 Write the `.env`

```bash
cat > ~/mcp-servers/ghl-community-mcp/.env <<EOF
GHL_API_KEY=${GOHIGHLEVEL_API_KEY}
GHL_BASE_URL=https://services.leadconnectorhq.com
GHL_LOCATION_ID=${GOHIGHLEVEL_LOCATION_ID}
MCP_SERVER_PORT=8765
NODE_ENV=production
EOF
chmod 600 ~/mcp-servers/ghl-community-mcp/.env
```

### 6.4 Add a helper env var for canonical URL (CRITICAL)

This step **prevents agents from hardcoding the wrong port** in curl commands. Hardcoded ports are the #1 cause of Tier 2 failure post-install.

```bash
openclaw config set env.vars.GHL_COMMUNITY_MCP_URL "http://localhost:8765"
```

Document for the agent: **ALWAYS use `$GHL_COMMUNITY_MCP_URL` in shell commands. Never type a literal port.**

### 6.5 Set up launchd auto-start (macOS — no Docker dependency)

```bash
mkdir -p ~/Library/Logs/ghl-mcp

cat > ~/Library/LaunchAgents/com.clawd.ghl-mcp.plist <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.clawd.ghl-mcp</string>
    <key>ProgramArguments</key><array>
        <string>/opt/homebrew/bin/node</string>
        <string>/Users/USERNAME/mcp-servers/ghl-community-mcp/dist/main.js</string>
    </array>
    <key>WorkingDirectory</key><string>/Users/USERNAME/mcp-servers/ghl-community-mcp</string>
    <key>EnvironmentVariables</key><dict>
        <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>NODE_ENV</key><string>production</string>
    </dict>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><dict>
        <key>SuccessfulExit</key><false/>
        <key>Crashed</key><true/>
    </dict>
    <key>ThrottleInterval</key><integer>10</integer>
    <key>StandardOutPath</key><string>/Users/USERNAME/Library/Logs/ghl-mcp/stdout.log</string>
    <key>StandardErrorPath</key><string>/Users/USERNAME/Library/Logs/ghl-mcp/stderr.log</string>
    <key>ProcessType</key><string>Background</string>
</dict>
</plist>
EOF

# Substitute the real username
sed -i '' "s|USERNAME|$(whoami)|g" ~/Library/LaunchAgents/com.clawd.ghl-mcp.plist

# Boot it
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.clawd.ghl-mcp.plist
```

### 6.6 Linux / VPS alternative: systemd

```bash
sudo tee /etc/systemd/system/ghl-mcp.service > /dev/null <<EOF
[Unit]
Description=GHL Community MCP Server
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=/home/$(whoami)/mcp-servers/ghl-community-mcp
ExecStart=/usr/bin/node /home/$(whoami)/mcp-servers/ghl-community-mcp/dist/main.js
Restart=on-failure
RestartSec=10
StandardOutput=append:/home/$(whoami)/logs/ghl-mcp.log
StandardError=append:/home/$(whoami)/logs/ghl-mcp.err.log

[Install]
WantedBy=multi-user.target
EOF

mkdir -p ~/logs
sudo systemctl daemon-reload
sudo systemctl enable --now ghl-mcp
```

### 6.7 Register with OpenClaw

```bash
openclaw mcp set ghl-community-mcp '{
  "url": "http://localhost:8765/mcp",
  "transport": "streamable-http",
  "connectionTimeoutMs": 30000
}'
```

### 6.8 Verify Tier 2 works

```bash
# Health
curl -sS $GHL_COMMUNITY_MCP_URL/health
# Expect: {"status":"healthy","tools":588,...}

# Tools count
curl -sS $GHL_COMMUNITY_MCP_URL/tools | python3 -c "import json,sys; print('tools:', len(json.load(sys.stdin).get('tools',[])))"
# Expect: tools: 588

# Real-data call (bypasses MCP protocol via REST /execute)
curl -sS -X POST $GHL_COMMUNITY_MCP_URL/execute \
  -H "Content-Type: application/json" \
  -d '{"name":"ghl_list_products","arguments":{"limit":3}}' | python3 -m json.tool
# Expect: success:true with a real products array
```

### 6.9 Critical port-collision warning

**Port 8000 is commonly used by Cognee, FastAPI dev servers, jupyter, and other tools.** If your client has any of those, port 8000 will be taken. The GHL community MCP must NOT be moved back to 8000 on any machine where another service has claimed it. The env var `GHL_COMMUNITY_MCP_URL` is the canonical source of truth — update both the `.env` `MCP_SERVER_PORT` AND the env var if you change ports.

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

### Tier 4 — Playwright browser

Use `launchPersistentContext` (NEVER `launch()`) so login state persists.
- URL: `https://app.gohighlevel.com` or the client's white-label (e.g. `https://app.convertandflow.com`)
- Creds: `GHL_AGENCY_EMAIL`, `GHL_AGENCY_PASSWORD` (or location-level creds) in `~/.openclaw/secrets/.env`
- Browser MUST be Playwright + Kimi K2.5 model. Never Gemini with Playwright (documented incompatibility).

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

### 8.1 What to add to SOUL.md (cardinal rule — survives across all sessions)

**Append** at the end (do not insert — respect existing structure):

```markdown
## 🔴 GHL Tier Escalation Protocol

When asked to do anything involving GHL / GoHighLevel / [client white-label name] / LeadConnector:

1. **Tier order is binding. Do not skip tiers.** Try Tier 1 (official MCP) first. Fall to Tier 2 (community MCP) if Tier 1 lacks the tool. Fall to Tier 3 (API + skill) only if neither MCP covers it. Fall to Tier 4/5 only if Tier 3 fails fresh.

2. **Always use `$GHL_COMMUNITY_MCP_URL`** in shell commands for Tier 2. Never type a literal port number. Hardcoded ports from session memory have caused documented failures.

3. **Session memory is not authoritative — the canonical state block in AGENTS.md is.** Before declaring a tier dead, re-read the canonical state block and verify your actual call matches. If you get 404 / connection refused, first hypothesis is "I used the wrong URL," not "the server is broken."

4. **Required disclosure on every GHL response:** prefix your final answer with a one-line header in this exact format: `[GHL tier used: N — tool_name]`. If you fell through tiers, include the chain: `[GHL tier used: 2 (Tier 1 lacked tool: products) — ghl_list_products]`. Missing disclosure = protocol violation.

5. **"It looked broken earlier" is not an excuse.** If a tier crashed in earlier session work, attempt it fresh anyway. If it actually fails this time, recover it (kickstart / systemctl restart) before falling through.
```

### 8.2 What to add to AGENTS.md (operating block — the WHAT-TO-DO)

**Append** a top-level GHL section. Adapt aliases to client white-label:

```markdown
## GHL / [Client white-label] access order

[GHL, GoHighLevel, Go High Level, LeadConnector, and {client name}] refer to the same platform.

### 🟢 Canonical current state — override stale session memory

These values are authoritative. If your session history disagrees, trust this block.

| Fact | Current canonical value |
|---|---|
| Community MCP base URL env var | `$GHL_COMMUNITY_MCP_URL` (always use this, never hardcode a port) |
| Health probe | `curl $GHL_COMMUNITY_MCP_URL/health` |
| MCP endpoint (OpenClaw transport) | `$GHL_COMMUNITY_MCP_URL/mcp` (streamable-http) |
| REST execute (debugging) | `POST $GHL_COMMUNITY_MCP_URL/execute` with `{"name":"tool","arguments":{...}}` |
| Live tool discovery | `curl $GHL_COMMUNITY_MCP_URL/tools` |
| Lifecycle | launchd plist `~/Library/LaunchAgents/com.clawd.ghl-mcp.plist` (macOS) or systemd `ghl-mcp.service` (Linux). Restart: `launchctl kickstart gui/$(id -u)/com.clawd.ghl-mcp` (macOS) / `sudo systemctl restart ghl-mcp` (Linux). |

### Tier order (try in sequence; do not skip)

**Tier 1 — Official GHL MCP**
- Server name in OpenClaw: `ghl-mcp`
- Endpoint: `https://services.leadconnectorhq.com/mcp/` (streamable-http, stateless)
- 36 tools: contacts, calendars, conversations, opportunities, social media, blogs, emails, locations, read-only payments
- Use first for anything in those domains

**Tier 2 — Community GHL MCP**
- Server name in OpenClaw: `ghl-community-mcp`
- Endpoint: `$GHL_COMMUNITY_MCP_URL/mcp`
- 588 tools: FULL API including products, invoices, billing, subscriptions, estimates, store, coupons, Voice AI, Phone System, Agent Studio
- Use when Tier 1 lacks the needed tool

**Tier 3 — Direct REST API with PIT**
- Skill set at `$MASTER_FILES_DIR/29-ghl-convert-and-flow/` (Mac default: `~/Downloads/openclaw-master-files/29-ghl-convert-and-flow/`; VPS default: `~/Downloads/openclaw-master-files/29-ghl-convert-and-flow/`)
- Read `references/[module].md` for endpoint specifics
- Base URL: `https://services.leadconnectorhq.com`
- Version header: `2021-07-28` (some modules use `2021-04-15`)

**Tier 4 — Playwright browser**
- URL: `https://app.gohighlevel.com` (or client white-label)
- Use `launchPersistentContext`, never `launch()`
- Creds in `~/.openclaw/secrets/.env`

**Tier 5 — Codex Computer Use**
- `codex/gpt-5.5`, 45-min default timeout
- Last resort only

### Verify-before-fallthrough protocol (REQUIRED before declaring any tier dead)

On 404 / 502 / connection refused:
1. Re-read the canonical state block above. Compare URL/port/path against what you actually called.
2. Hit `/health`. If healthy, the server is fine — your call shape is wrong. Fix and retry.
3. Only after 1 + 2 both confirm dead state, attempt recovery (kickstart). Retry once.
4. Only after step 3 fails, fall through. Disclosure must reflect the true cause.

### Anti-patterns (documented past failures — do not repeat)

- ❌ "Tier 1 doesn't have X → I'll use Tier 3." Wrong. Try Tier 2.
- ❌ Hardcoding a port number from session memory. Always `$GHL_COMMUNITY_MCP_URL`.
- ❌ "Tier 2 crashed earlier in this session → skip." Wrong. Restart and retry.
- ❌ "Tier 3 is faster / cleaner / I prefer raw API." Personal preference is not a routing override.
```

### 8.3 What to add to TOOLS.md (WHERE-THINGS-LIVE — reference material)

**Append** a Community MCP reference section. The full 588-tool list is in **Reference B** of this document — copy that section in directly, or summarize as:

```markdown
## GHL Community MCP — tool name reference

Server: `ghl-community-mcp` at `$GHL_COMMUNITY_MCP_URL`. 588 tools.

Domain → primary tools:

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

For anything not in this table, run live discovery:
`curl $GHL_COMMUNITY_MCP_URL/tools | python3 -m json.tool`
```

### 8.4 What to add to MEMORY.md (durable facts about THIS client's GHL setup)

**Append** as a durable record:

```markdown
## GHL MCP setup ([INSTALL DATE])

Two MCP servers configured for [client white-label brand]:

1. **Official GHL MCP** — OpenClaw entry `ghl-mcp`, hosted at `https://services.leadconnectorhq.com/mcp/`. 36 tools. Stateless.

2. **Community GHL MCP — DEPLOYED** — OpenClaw entry `ghl-community-mcp`, BusyBee3333 2026 fork. 588 tools. Runs locally on `$GHL_COMMUNITY_MCP_URL` (env var resolves to `http://localhost:8765` unless port collision required a different port). Repo at `~/mcp-servers/ghl-community-mcp`. Lifecycle: launchd plist `~/Library/LaunchAgents/com.clawd.ghl-mcp.plist` (macOS) or `ghl-mcp.service` (Linux). Auto-starts at login, restarts on crash. **No Docker dependency.**

3. **Tier 3 fallback** — GHL skill at `$MASTER_FILES_DIR/29-ghl-convert-and-flow/` (Mac default: `~/Downloads/openclaw-master-files/29-ghl-convert-and-flow/`; VPS default: `~/Downloads/openclaw-master-files/29-ghl-convert-and-flow/`). Pre-installed for all clients unless Section 1.B noted otherwise.

4. **Tier 4 fallback** — Playwright browser at `[client white-label URL]`.

5. **Tier 5 fallback** — Codex Computer Use, `codex/gpt-5.5`.

Decision table and full setup details in TOOLS.md. Cardinal behavioral rule in SOUL.md (`GHL Tier Escalation Protocol`).

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
| 1 | "What's my business name, address, and main phone number on [Brand]?" | `[GHL tier used: 1 — locations_get-location]` | Tier 1 baseline |
| 2 | "How many products do I have in my [Brand] store right now?" | `[GHL tier used: 2 — ghl_list_products]` | Tier 2 routing |
| 3 | "How many recurring subscriptions do I have running right now, and what's the next one set to charge?" | `[GHL tier used: 2 — list_invoice_schedules]` | Tier 2 routing (trap: word "subscriptions" might mistarget Tier 1) |
| 4 | "Show me my last 5 payment transactions." | `[GHL tier used: 2 — list_transactions]` | Trap: "payments" word — official MCP has read-only payments but `list_transactions` is Tier 2 only |
| 5 | "Pull the webhook delivery log for my account from the last 24 hours." | Expect fall-through: `[GHL tier used: 3 (Tier 1+2 lacked tool) — raw API]` | Verifies clean tier-3 fall-through |

**Passing:** every prompt response opens with the correct disclosure header.
**Failing:** missing header → SOUL.md isn't loading into the agent's system prompt. Investigate channel-routing / bootstrap injection.
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
6. **Tier 1 MCP is registered** in `openclaw mcp list`
7. **Tier 1 returns 36 tools** via `tools/list`
8. **Tier 1 returns real location data** via `locations_get-location`
9. **Tier 2 MCP is registered** in `openclaw mcp list`
10. **Tier 2 server is running** (launchd or systemd reports active)
11. **Tier 2 /health returns `tools:588`**
12. **Tier 2 /execute returns real GHL data** for a sample tool (e.g. `ghl_list_products`)
13. **`GHL_COMMUNITY_MCP_URL` env var is set** and resolves to the right host:port
14. **SOUL.md contains the Tier Escalation Protocol section**
15. **AGENTS.md contains the canonical state block AND the tier-skip enforcement block**
16. **TOOLS.md contains the community MCP tool-name reference**
17. **MEMORY.md contains the install record for this client**
18. **This document is copied into `$MASTER_FILES_DIR/XX-ghl-mcp-setup/`**
19. **No PIT or Location ID is echoed in any .md or log file** (security)
20. **Secrets file is chmod 600**

### 11.B The bundled QC script — ships as `qc-ghl-mcp-setup.sh` in this folder

The QC script is the standalone file `qc-ghl-mcp-setup.sh` shipped alongside this reference. It is the single source of truth — do NOT extract a copy from this document or from QC.md (earlier versions of this skill embedded a copy here; the embedded copy is now removed to prevent drift, because the standalone has rate-limit probe logic and other v9.3.5+ additions that an extracted copy would silently lose).

### 11.C How to run

```bash
# Locate the master files folder (where install.sh placed the skill)
if [ -d "~/.openclaw" ]; then
  MASTER_FILES_DIR=~/Downloads/openclaw-master-files
else
  MASTER_FILES_DIR=$HOME/Downloads/openclaw-master-files
fi

chmod +x "$MASTER_FILES_DIR/36-ghl-mcp-setup/qc-ghl-mcp-setup.sh"
bash    "$MASTER_FILES_DIR/36-ghl-mcp-setup/qc-ghl-mcp-setup.sh"
```

What the script does (summary — read the source for details):
- Detects platform (Mac vs VPS) and resolves canonical secrets / config / workspace paths
- Sources `~/.openclaw/secrets/.env` (or `~/.openclaw/secrets/.env`), reads `GOHIGHLEVEL_API_KEY` (PIT) and `GOHIGHLEVEL_LOCATION_ID`
- Probes Tier 1 (Official MCP) — confirms 36 tools available
- Probes Tier 2 (Community MCP) — hits `$GHL_COMMUNITY_MCP_URL/health`, confirms tool count
- Probes Tier 3 (direct REST) — reads `X-RateLimit-Daily-Remaining` and surfaces the reset clock time in plain English if quota is low (v9.3.5 incident-response logic)
- Asserts SOUL.md / AGENTS.md / TOOLS.md / MEMORY.md contain the canonical state block and disclosure-header protocol
- Verifies secrets file is `chmod 600` and the PIT does not appear in any tracked `.md` file

Exit code 0 = all clear. Non-zero = the script prints which assertions failed and why; fix and re-run.

### 11.D Pass/fail thresholds

| Result | Meaning | What to do |
|---|---|---|
| Exit 0, 0 warnings | All clear | Tell the client setup is complete. Ask for the 5 test prompts from Phase 8 to be run. |
| Exit 0, warnings only | Setup is technically complete but some non-critical things flagged | Review warnings with the client. Likely candidates: tool count below 500 (= old fork), GHL skill missing (= Tier 3 disabled), etc. |
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

## REFERENCE A — OFFICIAL GHL MCP: ALL 36 TOOLS BY DOMAIN

Verified against `https://services.leadconnectorhq.com/mcp/` on 2026-05-13.

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

**Total: 36 tools.** No products, no invoices, no subscriptions/schedules, no estimates, no coupons, no store, no Voice AI, no Phone System, no Agent Studio. For any of those, use Tier 2.

---

## REFERENCE B — COMMUNITY GHL MCP: ALL 588 TOOLS BY VERB CATEGORY

Verified against the running BusyBee3333 fork on 2026-05-13 via `GET /tools`.

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

**Total: 588 tools.** Run `curl $GHL_COMMUNITY_MCP_URL/tools` for the live, definitive list.

---

## REFERENCE C — TROUBLESHOOTING CHEAT SHEET

| Symptom | Likely cause | Fix |
|---|---|---|
| `/health` returns nothing | Server not running | `launchctl kickstart gui/$(id -u)/com.clawd.ghl-mcp` (macOS) or `sudo systemctl restart ghl-mcp` (Linux) |
| `/health` returns Cognee's response (`status:ready, version:0.5.3-local`) | Wrong port — you hit Cognee | Check `MCP_SERVER_PORT` in `.env` and `GHL_COMMUNITY_MCP_URL`; ensure they match |
| Server registers <588 tools | Stale build | `cd ~/mcp-servers/ghl-community-mcp && git pull && npm install && npm run build && launchctl kickstart gui/$(id -u)/com.clawd.ghl-mcp` |
| Tool returns "Tool 'X' not found or not active" | PIT lacks the required scope OR tool name is misspelled | Re-check tool name against `/tools`; if name is correct, verify PIT scopes in GHL Settings → Integrations → Private Integrations |
| 401 / 403 on Tier 1 or Tier 3 | PIT lacks scope, or PIT was rotated and `.env` is stale | Check `GHL Settings → Integrations → Private Integrations` for token validity; update both `~/.openclaw/secrets/.env` and `openclaw.json` env.vars |
| Agent skips Tier 2 | Stale session context, or `.md` files not loading | Start fresh session; verify SOUL.md + AGENTS.md are in agent's workspace bootstrap |
| Agent hardcodes wrong port | Stale memory of port 8000 from earlier setup | Ensure `GHL_COMMUNITY_MCP_URL` env var is set AND AGENTS.md says "always use the env var" |
| `launchctl bootstrap` fails with "service already loaded" | Plist already loaded from previous boot | `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.clawd.ghl-mcp.plist` then bootstrap again |
| WorkflowBuilderTools init warning on boot | Visual workflow builder needs additional tokens (Firebase or v2 JWT refresh) | Non-blocking — other 588 tools work without it. Ignore unless client needs visual workflow authoring via MCP |

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

- [ ] PIT stored in `~/.openclaw/secrets/.env` with `chmod 600`
- [ ] `.env` for community MCP at `~/mcp-servers/ghl-community-mcp/.env` with `chmod 600`
- [ ] No PIT or Location ID echoed into chat logs, commit history, or shared docs
- [ ] `~/.openclaw/secrets/` and `~/mcp-servers/*/.env` listed in `.gitignore` for any tracked repos
- [ ] `GHL_COMMUNITY_MCP_URL` env var set in `openclaw.json` env.vars
- [ ] launchd / systemd unit owns logs that don't contain the PIT (check `~/Library/Logs/ghl-mcp/stdout.log` for any leaked auth)
- [ ] Smoke tests pass for both MCPs (verified with real data)
- [ ] All 5 test prompts (Phase 8) produce correct disclosure headers
- [ ] This document copied to `$MASTER_FILES_DIR/XX-ghl-mcp-setup/` (Mac: `~/Downloads/openclaw-master-files/XX-ghl-mcp-setup/`; VPS: `~/Downloads/openclaw-master-files/XX-ghl-mcp-setup/`) for future re-use

---

## END

If anything is unclear or fails to work as described, first run:
```bash
openclaw doctor
curl $GHL_COMMUNITY_MCP_URL/health
openclaw mcp list
launchctl print gui/$(id -u)/com.clawd.ghl-mcp | grep -E "state|pid"
```

Then check the troubleshooting cheat sheet (Reference C) before falling back to manual debugging.
