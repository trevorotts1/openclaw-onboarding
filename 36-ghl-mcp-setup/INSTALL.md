╔══════════════════════════════════════════════════════════════╗
  MANDATORY TYP CHECK - READ THIS BEFORE ANYTHING ELSE
DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.

STEP 1: CHECK IF YOU HAVE BEEN TAUGHT THE TEACH YOURSELF PROTOCOL (TYP)

Before you read, learn, or execute ANY instruction in this document, you must
verify that you have already been taught the Teach Yourself Protocol (TYP).

HOW TO CHECK:
- Look in your AGENTS.md, TOOLS.md, or MEMORY.md for any mention of:
  "Teach Yourself Protocol" or "TYP"
- Look in your session context for prior TYP training
- Look for a tab called "Teach Yourself Protocol" in this same document

IF YOU HAVE BEEN TAUGHT TYP:
Proceed to the instructions below. Follow the TYP file storage structure.

IF YOU HAVE NOT BEEN TAUGHT TYP:
NOTE: TYP is recommended. If not yet installed, continue and revisit TYP
later if needed. You can still safely execute this skill without TYP - just
be mindful not to dump large blocks of content into core .md files. Add only
brief summaries and file path references to AGENTS.md, TOOLS.md, MEMORY.md,
and SOUL.md.

CONFLICT RULE (applies to all skill installs):
If this skill's SKILL.md, CORE_UPDATES.md, or any other file in this skill
folder conflicts with TYP regarding WHICH core .md files to update or WHAT
content to add, always follow this skill's files. The skill takes precedence
over TYP on core file update decisions. TYP governs the storage method (lean
summaries + file paths). The skill governs the content and which files it
touches. When in doubt: skill docs win.


TYP FILE STORAGE INSTRUCTIONS (only read this if TYP confirmed)

WHEN LEARNING THIS DOCUMENT, FOLLOW THIS STRUCTURE:

1. SAVE FULL DOCUMENTATION TO MASTER FILES FOLDER
   Find the OpenClaw master files folder. On macOS it is in ~/Downloads/.
   On a VPS it is in ~/Downloads/. The folder may be named:
   - OpenClaw Master Files
   - OpenClaw Master Documents
   - OpenClaw Documents
   - openclaw-master-files
   - openclaw master files
   - OpenClaw Files
   - openclaw-documents
   - Any variation of "openclaw" + "master" or "files" or "documents"
   Search case-insensitively. One word or two words. Plural or singular.
   If no folder is found:
   - macOS: create ~/Downloads/openclaw-master-files/
   - VPS: create ~/Downloads/openclaw-master-files/
   Ask the user for permission before creating if there is any ambiguity.

   Save this skill's `ghl-mcp-setup-full.md` to:
     [MASTER_FILES_FOLDER]/36-ghl-mcp-setup/

2. DO NOT DUMP FULL CONTENT INTO CORE .MD FILES
   AGENTS.md, TOOLS.md, MEMORY.md, and SOUL.md must stay lean.
   Only add the labeled summaries from CORE_UPDATES.md and a file path
   reference to where the full documentation lives. Never paste thousands
   of lines into core files.

3. USE THE LABELED SECTIONS IN CORE_UPDATES.md TO KNOW WHAT GOES WHERE
   CORE_UPDATES.md marks each core file "UPDATE REQUIRED" or "NO UPDATE NEEDED":
   - SOUL.md — NO UPDATE NEEDED (the Tier Escalation Protocol lives in AGENTS.md, not SOUL.md)
   - AGENTS.md — UPDATE REQUIRED
   - TOOLS.md — UPDATE REQUIRED
   - MEMORY.md — UPDATE REQUIRED
   Only add what CORE_UPDATES.md marks UPDATE REQUIRED. Nothing else goes into core files.

EXECUTION DISCIPLINE - MANDATORY BEFORE YOU START
╚══════════════════════════════════════════════════════════════╝

These rules apply every single time you execute instructions from this document.
No exceptions. No shortcuts. No improvising.

RULE 1: READ EVERYTHING BEFORE YOU TOUCH ANYTHING
Read this entire document from top to bottom before executing a single step.
Do not start executing while still reading. Finish reading first. Then start.

RULE 2: DO NOT CHANGE THE OPERATOR'S INTENT
These instructions say exactly what to do. Execute them exactly as written.
- Do NOT reinterpret steps
- Do NOT "improve" the instructions
- Do NOT skip steps because they seem unnecessary
- Do NOT add steps that are not in the document
- Do NOT change the order of steps
If a step says do X, do X. Not Y. Not a better version of X. X.

RULE 3: NEVER MODIFY THESE WITHOUT PERMISSION
- API keys / PITs / Location IDs — copy them exactly, character for character
- Terminal commands — run them exactly as written, no edits
- Config values — use the exact values specified
- Port numbers — 8765 is the canonical Tier 2 port; never substitute
- File paths — use the exact paths specified for the detected platform
If you are unsure whether something should be changed, the answer is NO.
Ask the operator. Do not guess. Do not assume.

RULE 4: BUILD YOUR CHECKLIST BEFORE EXECUTING
Before you run a single command or make a single change, create a numbered
checklist of every action this document requires you to take. Write it out.
Show it to the user before starting. Get confirmation. Then execute.

RULE 5: CHECK YOURSELF AGAINST THE CHECKLIST WHEN DONE
When you believe you are finished, run the bundled `qc-ghl-mcp-setup.sh`
shipped in this skill folder. Do NOT extract or rewrite it from QC.md — the
standalone file is the single source of truth. Do NOT tell the user "setup
is complete" until the script exits 0. If anything failed, fix it and
re-run. The QC script is the gate.

RULE 6: REPORT WHAT YOU DID
When finished, give the user a clear summary:
- What was completed
- What commands were run
- What files were changed
- Any errors encountered and how they were resolved
- The output of the QC script
- Confirmation that the checklist was fully satisfied

══════════════════════════════════════════════════════════════════

# GHL MCP Setup — Installation Guide

> **N24 — Use the teach-yourself-protocol (Skill 01):** Before any action in this skill, the installing sub-agent MUST read every file under skills/01-teach-yourself-protocol/ and follow its procedural read-order. No shortcuts.


This guide enables AI agent autonomous setup of the 6-tier GHL access chain.
After completing these steps, the agent will route GHL requests through:
Convert and Flow CLI (Tier 0, skill 44) → Official MCP → Community MCP (on-demand) → REST API → agent-browser/Playwright → Codex Computer Use.

## Important Things to Know Before You Start

### Convert and Flow IS GoHighLevel
Same platform, same backend, same login. The client may use the white-label
brand name — verify with the client which name they use in customer-facing
communications, then use that name in any user-facing output.

### GHL Uses a Private Integration Token, NOT an API Key
Same PIT works for both MCPs and for the raw API. Required scopes for FULL
MCP coverage (Tier 1 + Tier 2):
- contacts.readonly, contacts.write
- conversations.readonly, conversations.write
- opportunities.readonly, opportunities.write
- calendars.readonly, calendars.write
- locations.readonly, locations.write
- workflows.readonly
- blogs.readonly, blogs.write
- users.readonly
- custom_objects.readonly, custom_objects.write
- invoices.readonly, invoices.write
- payments.readonly
- products.readonly, products.write
- medias.write

### Where Credentials Get Stored (CANONICAL — overrides any older skill)
- macOS: `~/.openclaw/secrets/.env`
- VPS: `~/.openclaw/secrets/.env`

Env var names: `GOHIGHLEVEL_API_KEY` (= the Location PIT, despite the legacy name)
and `GOHIGHLEVEL_LOCATION_ID`. Secondary mirror: `openclaw.json` `env.vars`.

If older versions of skill 05 stored creds at `~/clawd/secrets/.env`, MIGRATE
them to `~/.openclaw/secrets/.env` before installing this skill.

## Autonomous Setup Execution

### Pre-Action 0: Canonical Mac Paths

```bash
export SECRETS_ENV="$HOME/.openclaw/secrets/.env"
export CONFIG_JSON="$HOME/.openclaw/openclaw.json"
export CANONICAL_MASTER="$HOME/Downloads/openclaw-master-files"
export WORKSPACE="$HOME/clawd"
[ ! -d "$WORKSPACE" ] && WORKSPACE="$HOME/.openclaw/workspace"
echo "Workspace: $WORKSPACE"
```

### Pre-Action 0.5: Command Center — Report Install Start (fail-soft)

Open (or reuse) the operator-visibility card and move it to `in_progress` so a
stuck install is visible on the Command Center board. This is the implementing
call for the "install start" emit moment documented in INSTRUCTIONS.md — it is
**best-effort operator visibility, never a blocker**: with no `MC_API_TOKEN` (or
no Command Center reachable) it prints one operator-only stderr note and exits 0.

```bash
SKILL36_DIR="$HOME/.openclaw/skills/36-ghl-mcp-setup"
[ -x "$SKILL36_DIR/scripts/cc-task.sh" ] && bash "$SKILL36_DIR/scripts/cc-task.sh" start || true
```

The matching `review` transition fires automatically from the QC PASS branch of
`qc-ghl-mcp-setup.sh` when the install passes (RULE 5). The independent Command
Center auto-scorer — not this skill — promotes `review` to done. See the
"Command Center hooks" section of INSTRUCTIONS.md for the four emit moments and
the required config (`MC_API_TOKEN`, `MISSION_CONTROL_URL`, and the optional
`MC_SKILL36_AGENT_ID` / `MC_SKILL36_SOP_ID` leave-backlog Triad ids).

### Pre-Action 1: Locate the openclaw-master-files Folder

```bash
MASTER_FILES_DIR=""
for r in "$HOME/Downloads" "~/Downloads" "/root/Downloads" "/data" "$HOME"; do
  [ -d "$r" ] || continue
  found=$(find "$r" -maxdepth 2 -type d \
    \( -iname "*openclaw*master*file*" -o -iname "*open*claw*master*file*" \) \
    ! -iname "*backup*" ! -iname "*.zip*" 2>/dev/null | head -1)
  [ -n "$found" ] && MASTER_FILES_DIR="$found" && break
done
echo "Master files: ${MASTER_FILES_DIR:-NOT FOUND}"
```

If `MASTER_FILES_DIR` is empty, STOP and ask the user:

> "I can't find an openclaw-master-files folder anywhere. I'd like to create it at `$CANONICAL_MASTER`. Do I have permission?"

Only proceed after explicit permission.

### Pre-Action 2: Environment Credential Check

Before asking the user, search ALL standard locations:

```bash
# Every check below is EXISTENCE-ONLY: it reports which credential key NAMES are
# present, never their values. Never grep a secrets file in a way that prints the
# matched line — the repo qc-static secret-printing gate fails any secret-pattern
# grep that lacks -q/-l/-L.

# 1. Canonical secrets file (the source of truth) — names only
for k in GOHIGHLEVEL_API_KEY GHL_API_KEY GHL_PIT GHL_TOKEN GHL_PRIVATE_INTEGRATION_TOKEN PRIVATE_INTEGRATION_TOKEN GHL_PRIVATE_TOKEN PIT_TOKEN GHL_PIT_TOKEN GOHIGHLEVEL_LOCATION_PIT GHL_LOCATION_PIT GHL_LOCATION_ID GOHIGHLEVEL_LOCATION_ID; do
  grep -qE "^(export )?${k}=" "$SECRETS_ENV" 2>/dev/null && echo "$k=SET"
done

# 2. OpenClaw config env.vars (gateway runtime) — names only, values never printed
python3 -c "
import json
cfg=json.load(open('$CONFIG_JSON'))
ev=cfg.get('env',{}).get('vars',{})
for k in ev:
    if any(s in k.upper() for s in ['GHL','GOHIGH','LEADCONN','LOCATION']):
        print(f'{k}=SET')
"

# 3. Legacy location (skill 05 pre-v2.0) — names only
for k in GHL_API_KEY GHL_PIT GOHIGHLEVEL_API_KEY GHL_LOCATION_ID; do
  grep -qE "^(export )?${k}=" "$WORKSPACE/secrets/.env" 2>/dev/null && echo "$k=SET"
done

# 4. Live env — key NAMES only (cut strips the value before grep ever sees it)
printenv | cut -d= -f1 | grep -iE "GHL|GOHIGH|LEADCONN|LOCATION_ID" || true

# 5. Home dotfile — key NAMES only
cut -d= -f1 ~/.env 2>/dev/null | grep -iE "GHL|GOHIGH|LOCATION_ID" || true

# 6. clawd repo env files — matching FILE names only (-l), never the values
grep -rilE "GHL_API_KEY|GOHIGHLEVEL_API_KEY|leadconnector" "$WORKSPACE"/.env* "$WORKSPACE"/*/.env* 2>/dev/null

# 7. Master files folder — matching FILE names only (-l), never the values
grep -rilE "GHL_API_KEY|GOHIGHLEVEL_API_KEY|GHL_LOCATION_ID" "$MASTER_FILES_DIR/" 2>/dev/null
```

**Decision tree:**
- If both PIT and Location ID are found in ANY of the above: skip Action 1.
- If creds were found in legacy locations (`$WORKSPACE/secrets/.env`) but not canonical: copy to canonical (`$SECRETS_ENV`) before proceeding. Document the migration in MEMORY.md.
- If creds are missing: proceed to Action 1.

### Action 1: Retrieve GHL Credentials (only if missing)

Tell the user exactly this:

> "I checked your environment files and could not find your GHL credentials. I need your GHL Location ID and Private Integration Token (PIT).
>
> To get them:
> 1. Log into your GoHighLevel or Convert and Flow account
> 2. Go to Settings → Company → Locations → click the location → copy the Location ID at the top (22 characters)
> 3. Go to Settings → Integrations → Private Integrations → Create New Private Integration → enable the scopes I list below → Save → copy the generated token (starts with `pit-`)
>
> Required scopes: contacts.readonly+write, conversations.readonly+write, opportunities.readonly+write, calendars.readonly+write, locations.readonly+write, workflows.readonly, blogs.readonly+write, users.readonly, custom_objects.readonly+write, invoices.readonly+write, payments.readonly, products.readonly+write, medias.write
>
> Paste both values here when ready, or type 'skip' to continue without GHL credentials."

**If user skips:** note in MEMORY.md, do not block install. Tiers 1–3 will not work until creds are added.

### Action 2: Store Credentials

```bash
mkdir -p "$(dirname "$SECRETS_ENV")"
# Append if not already present
grep -q "^GOHIGHLEVEL_API_KEY=" "$SECRETS_ENV" 2>/dev/null || echo "GOHIGHLEVEL_API_KEY=pit-XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX" >> "$SECRETS_ENV"
grep -q "^GOHIGHLEVEL_LOCATION_ID=" "$SECRETS_ENV" 2>/dev/null || echo "GOHIGHLEVEL_LOCATION_ID=YYYYYYYYYYYYYYYYYYYYYY" >> "$SECRETS_ENV"
chmod 600 "$SECRETS_ENV"

# Mirror to openclaw.json env.vars (gateway reads here at runtime)
openclaw config set env.vars.GOHIGHLEVEL_API_KEY "pit-XXXXXXXX-..."
openclaw config set env.vars.GOHIGHLEVEL_LOCATION_ID "YYYYYYYYYYYYYYYYYYYYYY"
```

Replace `pit-XXX...` and `YYY...` with the actual user-provided values.

### Action 3: Register Tier 1 — Official GHL MCP

```bash
openclaw mcp set ghl-mcp '{
  "url": "https://services.leadconnectorhq.com/mcp/",
  "transport": "streamable-http",
  "headers": {
    "Authorization": "Bearer '"$GOHIGHLEVEL_API_KEY"'",
    "locationId": "'"$GOHIGHLEVEL_LOCATION_ID"'",
    "Version": "2021-07-28"
  },
  "connectionTimeoutMs": 30000
}'

# Verify
openclaw mcp list | grep ghl-mcp
```

### Action 4: Tier 1 Smoke Test

```bash
source "$SECRETS_ENV"
curl -sS -X POST "https://services.leadconnectorhq.com/mcp/" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "locationId: $GOHIGHLEVEL_LOCATION_ID" \
  -H "Version: 2021-07-28" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | grep "^data:" | head -1 | sed 's/^data: //' \
  | python3 -c "import json,sys; print('Tier 1 tool count:', len(json.load(sys.stdin).get('result',{}).get('tools',[])))"

# Expected output: Tier 1 tool count: 36
```

If this returns fewer than 36, STOP — credentials may be wrong or scopes missing.

### Action 5: Deploy Tier 2 — Community GHL MCP

#### 5.1 Pick a free port (8765 is canonical)

```bash
for p in 8765 8766 8888 8001; do
  if ! lsof -i :$p >/dev/null 2>&1; then export GHL_MCP_PORT=$p; break; fi
done
echo "Using port $GHL_MCP_PORT"
```

#### 5.2 Clone, install, build (idempotent)

```bash
if [ "$PLATFORM" = "vps" ]; then
  export MCP_DIR="/data/mcp-servers/ghl-community-mcp"
else
  export MCP_DIR="$HOME/mcp-servers/ghl-community-mcp"
fi

mkdir -p "$(dirname "$MCP_DIR")"

# PINNED COMMIT — reproducibility + supply-chain/drift protection.
# 3dd9006a (2026-05-15) is the commit this skill was built and verified against:
#   - package.json main = dist/main.js (the launchd/pm2 entrypoint)
#   - src/main.ts:55 reads `process.env.PORT || process.env.MCP_SERVER_PORT` (the
#     PORT-precedence behaviour the 5.5/5.6 supervision fix depends on)
#   - HTTP server exposes GET /health ({"status":"healthy",...}), GET /tools, POST /execute
#     (the exact surface QC Section D and INSTRUCTIONS.md probe).
# Tracking `main` HEAD instead pulls the 2026-06-11+ "mcp-apps / easy-setup / curated
# tool-profile" changes, which alter the default /tools surface — so we PIN.
# To bump: change the SHA, then re-run qc-ghl-mcp-setup.sh (it range-checks /health
# tool count + /execute) and confirm /health, /tools, /execute still behave as documented.
GHL_MCP_PIN_SHA="3dd9006ac5242762612e6d22b9a51a0a17aeca79"

if [ -d "$MCP_DIR/.git" ]; then
  cd "$MCP_DIR" && git fetch -q origin && git checkout -q "$GHL_MCP_PIN_SHA" && npm install --no-audit --no-fund && npm run build
else
  git clone https://github.com/busybee3333/Go-High-Level-MCP-2026-Complete.git "$MCP_DIR"
  cd "$MCP_DIR" && git checkout -q "$GHL_MCP_PIN_SHA" && npm install --no-audit --no-fund && npm run build
fi
```

#### 5.3 Write the .env

```bash
cat > "$MCP_DIR/.env" <<EOF
GHL_API_KEY=${GOHIGHLEVEL_API_KEY}
GHL_BASE_URL=https://services.leadconnectorhq.com
GHL_LOCATION_ID=${GOHIGHLEVEL_LOCATION_ID}
MCP_SERVER_PORT=${GHL_MCP_PORT}
NODE_ENV=production
EOF
chmod 600 "$MCP_DIR/.env"
```

#### 5.4 Set the canonical URL env var (CRITICAL — prevents hardcoded-port failures)

```bash
openclaw config set env.vars.GHL_COMMUNITY_MCP_URL "http://localhost:${GHL_MCP_PORT}"
```

#### 5.5 Install service — macOS (launchd)

> **v10.15.48 — AUTOSTART IS NOW EXECUTED, NOT PROSE.** The steps in 5.1–5.7
> below are the canonical reference, but you no longer have to run them by hand:
> `install.sh` (Step 14a) and `update-skills.sh` (GHL MCP wiring) both run
> `scripts/ghl-mcp-autostart.sh`, which builds the server if needed, writes this
> exact `com.clawd.ghl-mcp` launchd plist, boots it with KeepAlive on :8765,
> health-checks `/health`, and registers the MCP. It is idempotent and prints a
> `STATUS:` line. Run it manually only to re-verify:
>
> **v12.24.0 — SUPERVISION HARDENED (fleet incident: 12/19 boxes went down/unsupervised).**
> Two root causes are now fixed in `scripts/ghl-mcp-autostart.sh` and the VPS
> overlay `platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh`, and a
> hard QC gate (`scripts/qc-system-integrity.sh` **CHECK X.13**, backed by
> `scripts/qc-assert-ghl-mcp-supervised.sh`) blocks any regression from shipping:
>
> 1. **PORT IS PINNED EXPLICITLY.** The community MCP's `main.js` reads
>    `process.env.PORT` **before** `process.env.MCP_SERVER_PORT` (`src/main.ts:55`).
>    Without an explicit `PORT`, a stray inherited `PORT` made the server bind a
>    random port (49032/63703) instead of 8765. Every launch surface (launchd
>    plist, pm2 env, systemd `Environment=`, the server `.env`, the supervisor
>    loop) now pins **BOTH** `PORT=8765` **and** `MCP_SERVER_PORT=8765`.
> 2. **NO BARE NOHUP.** A bare `nohup node …` does NOT survive session/exec
>    teardown and is never restarted on crash. VPS now runs under **pm2**
>    (`ecosystem.config.js` + `pm2 save` + an `@reboot pm2 resurrect` hook) so it
>    survives reboot/container restart; systemd is the non-container fallback; a
>    detached `setsid` **supervised relaunch loop** is the last resort. Mac uses
>    the launchd `KeepAlive` + `RunAtLoad` plist below (now with `PORT` pinned).
>
> ```bash
> bash ~/.openclaw/onboarding/scripts/ghl-mcp-autostart.sh
> # STATUS: ghl-mcp-autostart=HEALTHY (server on :8765 healthy + registered ...)
> ```
>
> Registration WITHOUT a running server = GHL tools that never resolve. The
> server MUST be up (this is what 5.5 starts) AND registered (5.7).

```bash
if [ "$PLATFORM" = "desktop" ]; then
  mkdir -p ~/Library/Logs/ghl-mcp
  NODE_PATH=$(which node)
  cat > ~/Library/LaunchAgents/com.clawd.ghl-mcp.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.clawd.ghl-mcp</string>
    <key>ProgramArguments</key><array>
        <string>${NODE_PATH}</string>
        <string>${MCP_DIR}/dist/main.js</string>
    </array>
    <key>WorkingDirectory</key><string>${MCP_DIR}</string>
    <key>EnvironmentVariables</key><dict>
        <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>NODE_ENV</key><string>production</string>
        <!-- main.js reads PORT before MCP_SERVER_PORT (src/main.ts:55). Pin BOTH
             to ${GHL_MCP_PORT} so a stray inherited PORT can never bind random. -->
        <key>PORT</key><string>${GHL_MCP_PORT}</string>
        <key>MCP_SERVER_PORT</key><string>${GHL_MCP_PORT}</string>
    </dict>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><dict>
        <key>SuccessfulExit</key><false/>
        <key>Crashed</key><true/>
    </dict>
    <key>ThrottleInterval</key><integer>10</integer>
    <key>StandardOutPath</key><string>${HOME}/Library/Logs/ghl-mcp/stdout.log</string>
    <key>StandardErrorPath</key><string>${HOME}/Library/Logs/ghl-mcp/stderr.log</string>
    <key>ProcessType</key><string>Background</string>
</dict>
</plist>
EOF

  # Boot service
  launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.clawd.ghl-mcp.plist 2>/dev/null
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.clawd.ghl-mcp.plist
fi
```

#### 5.6 Install service — Linux/VPS (pm2 preferred; systemd fallback)

> **v12.24.0:** On a Hostinger Docker VPS there is NO systemd and NO launchd, so
> the legacy systemd unit never ran and the old fallback was a bare `nohup` that
> died on teardown — the fleet-killer. The canonical VPS path is now **pm2**
> (the fleet-standard supervisor) with `pm2 save` + an `@reboot pm2 resurrect`
> hook (and the Docker `command:` override below for `docker compose restart`).
> `PORT` and `MCP_SERVER_PORT` are BOTH pinned. `scripts/ghl-mcp-autostart.sh`
> and `platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh` write the
> `ecosystem.config.js` and run pm2 for you — these blocks are the reference.

```bash
if [ "$PLATFORM" = "vps" ]; then
  mkdir -p /data/logs
  # PORT + MCP_SERVER_PORT BOTH pinned (main.js reads PORT first → random bind otherwise).
  cat > "${MCP_DIR}/ecosystem.config.js" <<ECO
module.exports = {
  apps: [{
    name: "ghl-community-mcp",
    cwd: "${MCP_DIR}",
    script: "dist/main.js",
    interpreter: "node",
    autorestart: true,
    max_restarts: 50,
    restart_delay: 5000,
    env: {
      NODE_ENV: "production",
      PORT: "${GHL_MCP_PORT}",
      MCP_SERVER_PORT: "${GHL_MCP_PORT}",
      GHL_API_KEY: "${GOHIGHLEVEL_API_KEY}",
      GHL_BASE_URL: "https://services.leadconnectorhq.com",
      GHL_LOCATION_ID: "${GOHIGHLEVEL_LOCATION_ID}"
    },
    out_file: "/data/logs/ghl-mcp.log",
    error_file: "/data/logs/ghl-mcp.err.log"
  }]
};
ECO
  cd "${MCP_DIR}" && pm2 startOrReload ecosystem.config.js
  pm2 save
  pm2 startup >/dev/null 2>&1 || true
  # Reboot/container-restart survival: @reboot resurrect + Docker command override.
  ( crontab -l 2>/dev/null | grep -Fq "pm2 resurrect" ) || \
    ( crontab -l 2>/dev/null; echo "@reboot $(command -v pm2) resurrect >/data/logs/pm2-resurrect.log 2>&1" ) | crontab -
fi
```

For a Hostinger Docker box, also add a delayed `pm2 resurrect` to the project's
`command:` override (same pattern the Command Center uses, so the MCP returns
after `docker compose restart` — see skill 32 INSTALL.md Phase 6c).

> **systemd fallback (non-container VPS only):** if pm2 is genuinely unavailable
> and the box has systemd, install a unit with `Environment=PORT=${GHL_MCP_PORT}`
> and `Environment=MCP_SERVER_PORT=${GHL_MCP_PORT}` (the autostart script does
> this automatically). Never fall back to a bare `nohup`.

#### 5.7 Tier 2 = ON-DEMAND via curl (NO native registration)

As of skill 36 v1.1.0 the community MCP is NOT registered under
`mcp.servers` — its 588 tool schemas would ride in every session's context
whether or not GHL is touched (measurement recorded in CHANGELOG). The local
service still runs (launchd/systemd from 5.5/5.6, unchanged); only the
registration mode changes. The agent invokes Tier 2 tools on demand:

```bash
# Discover the tool surface live (no standing context cost):
curl -sS "$GHL_COMMUNITY_MCP_URL/tools" | python3 -m json.tool

# Invoke a tool via JSON-RPC over HTTP:
curl -sS -X POST "$GHL_COMMUNITY_MCP_URL/execute" \
  -H "Content-Type: application/json" \
  -d '{"name":"ghl_list_products","arguments":{"limit":3}}'
```

If a prior install registered `ghl-community-mcp`, remove it:
`openclaw mcp remove ghl-community-mcp` (the migration in the wire.sh does this on
live boxes).

### Action 6: Tier 2 Smoke Test

```bash
sleep 5   # allow server to boot
URL=$(openclaw config get env.vars.GHL_COMMUNITY_MCP_URL | tr -d '\n')

# Health
curl -sS "$URL/health"
# Expected: {"status":"healthy","tools":588,...}

# Real-data call
curl -sS -X POST "$URL/execute" \
  -H "Content-Type: application/json" \
  -d '{"name":"ghl_list_products","arguments":{"limit":3}}' \
  | python3 -m json.tool | head -20
# Expected: success:true with real product data
```

If `/health` returns Cognee's response (`status:ready, version:0.5.3-local`), you hit the wrong port. Move to a different port from the 5.1 list.

### Action 7: Update Core .md Files

Read `CORE_UPDATES.md` for exact text to add to:
- AGENTS.md (canonical state block + 🔴 Tier Escalation Protocol + tier order + anti-patterns + disclosure protocol)
- TOOLS.md (community MCP tool reference)
- MEMORY.md (install record)

SOUL.md — NO UPDATE NEEDED (the Tier Escalation Protocol is OPERATING LAW and lives in the shared AGENTS.md so sub-agents inherit it; leave SOUL.md byte-identical).

DO NOT TOUCH: IDENTITY.md, HEARTBEAT.md, USER.md, SOUL.md.

### Action 8: Save Full Reference to Master Files

```bash
mkdir -p "$MASTER_FILES_DIR/36-ghl-mcp-setup"
cp "$(pwd)/ghl-mcp-setup-full.md" "$MASTER_FILES_DIR/36-ghl-mcp-setup/"
cp "$(pwd)/QC.md" "$MASTER_FILES_DIR/36-ghl-mcp-setup/"
```

### Action 9: Run the QC Script

The QC script ships in this folder as `qc-ghl-mcp-setup.sh` — single source
of truth, do NOT extract it from QC.md (earlier versions instructed that;
the standalone is now authoritative and has rate-limit probe logic that an
extracted copy would silently lose).

```bash
chmod +x "$MASTER_FILES_DIR/36-ghl-mcp-setup/qc-ghl-mcp-setup.sh"
bash    "$MASTER_FILES_DIR/36-ghl-mcp-setup/qc-ghl-mcp-setup.sh"
```

Exit code 0 = setup complete. Any non-zero = fix the failed items and re-run.

### Action 10: Final User Verification

Ask the user to test in their main chat or Telegram with this prompt:

> "How many products do I have in my store right now, and what are the 3 most recently created ones?"

Expected response opens with `[GHL tier used: 2 — ghl_list_products]` and lists real products.

If the response uses Tier 3 or has no disclosure header, the agent isn't loading AGENTS.md properly. Investigate channel routing.

---

## Done When

- [ ] Tier 1 (`ghl-mcp`) registered, `/tools` returns >= 36
- [ ] Tier 2 service running + `/tools` curl returns >= 500; NOT registered in mcp.servers
- [ ] `GHL_COMMUNITY_MCP_URL` env var set
- [ ] launchd plist (Mac) or systemd unit (VPS) running
- [ ] AGENTS.md / TOOLS.md / MEMORY.md updated per CORE_UPDATES.md (SOUL.md unchanged)
- [ ] Full reference copied to `$MASTER_FILES_DIR/36-ghl-mcp-setup/`
- [ ] `qc-ghl-mcp-setup.sh` exits 0
- [ ] User verification prompt returns correct disclosure header
