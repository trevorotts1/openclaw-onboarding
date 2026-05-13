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
   On a VPS it is in /data/Downloads/. The folder may be named:
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
   - VPS: create /data/Downloads/openclaw-master-files/
   Ask the user for permission before creating if there is any ambiguity.

   Save this skill's `ghl-mcp-setup-full.md` to:
     [MASTER_FILES_FOLDER]/36-ghl-mcp-setup/

2. DO NOT DUMP FULL CONTENT INTO CORE .MD FILES
   AGENTS.md, TOOLS.md, MEMORY.md, and SOUL.md must stay lean.
   Only add the labeled summaries from CORE_UPDATES.md and a file path
   reference to where the full documentation lives. Never paste thousands
   of lines into core files.

3. USE THE LABELED SECTIONS IN CORE_UPDATES.md TO KNOW WHAT GOES WHERE
   Look for sections marked:
   [ADD TO SOUL.md]
   [ADD TO AGENTS.md]
   [ADD TO TOOLS.md]
   [ADD TO MEMORY.md]
   Only add what is labeled. Nothing else goes into core files.

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
When you believe you are finished, run the bundled `qc-ghl-setup.sh` from
QC.md. Do NOT tell the user "setup is complete" until the script exits 0.
If anything failed, fix it and re-run. The QC script is the gate.

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

This guide enables AI agent autonomous setup of the 5-tier GHL access chain.
After completing these steps, the agent will route GHL requests through:
Official MCP → Community MCP → REST API → Playwright → Codex Computer Use.

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
- VPS: `/data/.openclaw/secrets/.env`

Env var names: `GOHIGHLEVEL_API_KEY` (= the Location PIT, despite the legacy name)
and `GOHIGHLEVEL_LOCATION_ID`. Secondary mirror: `openclaw.json` `env.vars`.

If older versions of skill 05 stored creds at `~/clawd/secrets/.env`, MIGRATE
them to `~/.openclaw/secrets/.env` before installing this skill.

## Autonomous Setup Execution

### Pre-Action 0: Detect Platform

```bash
if [ -d "/data/.openclaw" ]; then
  export PLATFORM="vps"
  export SECRETS_ENV="/data/.openclaw/secrets/.env"
  export CONFIG_JSON="/data/.openclaw/openclaw.json"
  export CANONICAL_MASTER="/data/Downloads/openclaw-master-files"
  export WORKSPACE="/data/clawd"
else
  export PLATFORM="desktop"
  export SECRETS_ENV="$HOME/.openclaw/secrets/.env"
  export CONFIG_JSON="$HOME/.openclaw/openclaw.json"
  export CANONICAL_MASTER="$HOME/Downloads/openclaw-master-files"
  export WORKSPACE="$HOME/clawd"
fi
echo "Platform detected: $PLATFORM"
echo "Workspace: $WORKSPACE"
```

### Pre-Action 1: Locate the openclaw-master-files Folder

```bash
MASTER_FILES_DIR=""
for r in "$HOME/Downloads" "/data/Downloads" "/root/Downloads" "/data" "$HOME"; do
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
# 1. Canonical secrets file (the source of truth)
grep -iE "GHL_API_KEY|GHL_PIT|GOHIGHLEVEL_API_KEY|GHL_LOCATION_ID|GOHIGHLEVEL_LOCATION_ID" "$SECRETS_ENV" 2>/dev/null

# 2. OpenClaw config env.vars (gateway runtime)
python3 -c "
import json
cfg=json.load(open('$CONFIG_JSON'))
ev=cfg.get('env',{}).get('vars',{})
for k,v in ev.items():
    if any(s in k.upper() for s in ['GHL','GOHIGH','LEADCONN','LOCATION']):
        print(f'{k} = {str(v)[:10]}...')
"

# 3. Legacy location (skill 05 pre-v2.0)
grep -iE "GHL_API_KEY|GHL_PIT|GOHIGHLEVEL_API_KEY|GHL_LOCATION_ID" "$WORKSPACE/secrets/.env" 2>/dev/null

# 4. Live env
printenv | grep -iE "GHL|GOHIGH|LEADCONN|LOCATION_ID" | sed 's/=\(.\{0,10\}\).*/=\1.../'

# 5. Home dotfile
grep -iE "GHL|GOHIGH|LOCATION_ID" ~/.env 2>/dev/null

# 6. clawd repo env files
grep -riE "GHL_API_KEY|GOHIGHLEVEL_API_KEY|leadconnector" "$WORKSPACE"/.env* "$WORKSPACE"/*/.env* 2>/dev/null

# 7. Master files folder
grep -riE "GHL_API_KEY|GOHIGHLEVEL_API_KEY|GHL_LOCATION_ID" "$MASTER_FILES_DIR/" 2>/dev/null
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

If this returns anything other than 36, STOP — credentials may be wrong or scopes missing.

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
if [ -d "$MCP_DIR/.git" ]; then
  cd "$MCP_DIR" && git pull && npm install --no-audit --no-fund && npm run build
else
  git clone https://github.com/busybee3333/Go-High-Level-MCP-2026-Complete.git "$MCP_DIR"
  cd "$MCP_DIR" && npm install --no-audit --no-fund && npm run build
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

#### 5.6 Install service — Linux/VPS (systemd)

```bash
if [ "$PLATFORM" = "vps" ]; then
  mkdir -p /data/logs
  NODE_PATH=$(which node)
  sudo tee /etc/systemd/system/ghl-mcp.service > /dev/null <<EOF
[Unit]
Description=GHL Community MCP Server
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=${MCP_DIR}
ExecStart=${NODE_PATH} ${MCP_DIR}/dist/main.js
Restart=on-failure
RestartSec=10
EnvironmentFile=${MCP_DIR}/.env
StandardOutput=append:/data/logs/ghl-mcp.log
StandardError=append:/data/logs/ghl-mcp.err.log

[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable --now ghl-mcp
fi
```

#### 5.7 Register with OpenClaw

```bash
openclaw mcp set ghl-community-mcp "{\"url\":\"http://localhost:${GHL_MCP_PORT}/mcp\",\"transport\":\"streamable-http\",\"connectionTimeoutMs\":30000}"
```

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
- SOUL.md (Tier Escalation Protocol)
- AGENTS.md (canonical state block + tier order + anti-patterns + disclosure protocol)
- TOOLS.md (community MCP tool reference)
- MEMORY.md (install record)

DO NOT TOUCH: IDENTITY.md, HEARTBEAT.md, USER.md.

### Action 8: Save Full Reference to Master Files

```bash
mkdir -p "$MASTER_FILES_DIR/36-ghl-mcp-setup"
cp "$(pwd)/ghl-mcp-setup-full.md" "$MASTER_FILES_DIR/36-ghl-mcp-setup/"
cp "$(pwd)/QC.md" "$MASTER_FILES_DIR/36-ghl-mcp-setup/"
```

### Action 9: Run the QC Script

Read `QC.md` for the bundled `qc-ghl-setup.sh` script. Save it to:
```
$MASTER_FILES_DIR/36-ghl-mcp-setup/qc-ghl-setup.sh
```

Run it:
```bash
bash "$MASTER_FILES_DIR/36-ghl-mcp-setup/qc-ghl-setup.sh"
```

Exit code 0 = setup complete. Any non-zero = fix the failed items and re-run.

### Action 10: Final User Verification

Ask the user to test in their main chat or Telegram with this prompt:

> "How many products do I have in my store right now, and what are the 3 most recently created ones?"

Expected response opens with `[GHL tier used: 2 — ghl_list_products]` and lists real products.

If the response uses Tier 3 or has no disclosure header, the agent isn't loading SOUL.md/AGENTS.md properly. Investigate channel routing.

---

## Done When

- [ ] Tier 1 (`ghl-mcp`) registered, `/tools` returns 36
- [ ] Tier 2 (`ghl-community-mcp`) registered, `/health` returns 588 tools
- [ ] `GHL_COMMUNITY_MCP_URL` env var set
- [ ] launchd plist (Mac) or systemd unit (VPS) running
- [ ] SOUL.md / AGENTS.md / TOOLS.md / MEMORY.md updated per CORE_UPDATES.md
- [ ] Full reference copied to `$MASTER_FILES_DIR/36-ghl-mcp-setup/`
- [ ] `qc-ghl-setup.sh` exits 0
- [ ] User verification prompt returns correct disclosure header
