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
- Port numbers — 8765 was the retired community port; the required end state is **no listener**. Never start a service there to "match the docs"
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


This guide enables AI agent autonomous setup of the GHL access chain.
After completing these steps, the agent will route GHL requests through:
Convert and Flow CLI (Tier 0, skill 44) → Official MCP → REST API → agent-browser/Playwright → Codex Computer Use.
The self-hosted community MCP (the old "Tier 2") is **retired**: fresh installs omit it, and
updated boxes must verify it is off. It is not a fallback and must not be cloned, built,
supervised, or probed. The only retained MCP surfaces are the official connection and the
custom courier MCP.

## Important Things to Know Before You Start

### Convert and Flow IS GoHighLevel
Same platform, same backend, same login. The client may use the white-label
brand name — verify with the client which name they use in customer-facing
communications, then use that name in any user-facing output.

### Credential classes are separate — PIT for REST, OAuth for the official MCP
GHL uses a **Private Integration Token (PIT), not an API key**, for the REST API (Tier 0 CLI
and Tier 3). The **official MCP uses OAuth**; a PIT bearer sent to an MCP endpoint is an
unverified compatibility mode and is never equivalent. The PIT scope list below therefore
describes REST coverage only — it grants nothing on the MCP connection. The retired
community MCP's own PIT store is gone with it.

Required PIT scopes for the REST surface:
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

# Detect platform (used by Actions 5 & the pm2/desktop branches below). macOS is
# Darwin -> "desktop"; everything else (VPS/Docker/Linux) -> "vps". uname is the
# reliable discriminator (a `[ -d ~/.openclaw ]` test is useless — ~/.openclaw exists
# on both platforms). Every later `[ "$PLATFORM" = "vps"|"desktop" ]` branch depends
# on this; without it $PLATFORM is empty and the platform-specific steps silently skip.
if [ "$(uname -s)" = "Darwin" ]; then export PLATFORM="desktop"; else export PLATFORM="vps"; fi
echo "Platform: $PLATFORM"
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
# Set these to the ACTUAL user-provided values (do NOT leave the placeholders).
GHL_PIT="pit-XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX"   # <-- replace with the real Location PIT
GHL_LOC="YYYYYYYYYYYYYYYYYYYYYY"                      # <-- replace with the real Location ID

# SK1-72: refuse to persist a PLACEHOLDER credential. A pit-XXXX / all-Y / empty value is
# not a real secret — writing it silently breaks Tiers 1-3 and leaves a fake token on disk.
is_placeholder() {
  case "$1" in ""|pit-XXXX*|*XXXX-XXXX-XXXX*|*YYYYYY*) return 0 ;; *) return 1 ;; esac
}
if is_placeholder "$GHL_PIT" || is_placeholder "$GHL_LOC"; then
  echo "ERROR: GHL_PIT/GHL_LOC still hold a placeholder — set the real values first; refusing to write." >&2
else
  mkdir -p "$(dirname "$SECRETS_ENV")"
  # Append if not already present
  grep -q "^GOHIGHLEVEL_API_KEY=" "$SECRETS_ENV" 2>/dev/null || echo "GOHIGHLEVEL_API_KEY=$GHL_PIT" >> "$SECRETS_ENV"
  grep -q "^GOHIGHLEVEL_LOCATION_ID=" "$SECRETS_ENV" 2>/dev/null || echo "GOHIGHLEVEL_LOCATION_ID=$GHL_LOC" >> "$SECRETS_ENV"
  chmod 600 "$SECRETS_ENV"

  # Mirror to openclaw.json env.vars (gateway reads here at runtime)
  openclaw config set env.vars.GOHIGHLEVEL_API_KEY "$GHL_PIT"
  openclaw config set env.vars.GOHIGHLEVEL_LOCATION_ID "$GHL_LOC"
fi
```

`GHL_PIT`/`GHL_LOC` must be the actual user-provided values — the guard above refuses the `pit-XXX...` / `YYY...` placeholders.

### Action 3: Register Tier 1 — Official GHL MCP

The **documented** path is a client-specific OAuth endpoint. Register the connection for the
client the box actually runs:

| Client | Documented endpoint | Auth |
|---|---|---|
| Claude Code / Claude MCP client | `https://services.leadconnectorhq.com/mcp/anthropic/v2` | OAuth |
| ChatGPT / Codex / OpenAI clients | `https://services.leadconnectorhq.com/mcp/openai/v2/` | OAuth |
| OpenClaw gateway | see the `openclaw mcp set` registration below — **transitional** | see below |

```bash
# Claude Code registration (documented endpoint, OAuth):
claude mcp add --transport http leadconnector https://services.leadconnectorhq.com/mcp/anthropic/v2
```

**Preserved OpenClaw registration.** The `openclaw mcp set ghl-mcp` connection stays. It
points at the original `/mcp/` endpoint and carries a PIT bearer; that endpoint is
**transitional** during the migration, and the PIT bearer is an unverified compatibility mode
against an OAuth-documented service. Do not remove this connection. Do not describe a Claude
model routed *through* the gateway as proof of a Claude MCP client — the gateway registers
servers itself, and its transport is not established by this repo.

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

# Verify the connection exists (exact name — never string-match a bare "ghl-mcp"
# when operating on the retired community systemd unit of the same name)
openclaw mcp list | grep -w ghl-mcp
```

### Four evidence levels for MCP — do not collapse them

| Level | What it means | Can this repo assert it? |
|---|---|---|
| **1. Documented endpoint** | Vendor docs publish the URL for a named client | **Yes** — cite the docs page and fetch date |
| **2. Documented catalog** | Vendor docs publish exactly four tool names: `list_locations`, `search_operations`, `describe_operation`, `execute_operation` | **Yes** — names only |
| **3. Account / tenant grant** | The target account actually authorizes the connection, with the scopes and sub-account(s) claimed | **No** — requires an authorized OAuth connect |
| **4. Actually observed on this box** | This box completed `tools/list` and one real call, captured | **No** — requires a per-box receipt |

The repo can assert levels 1 and 2. Levels 3 and 4 are per-account and per-box facts.

### Action 4: Tier 1 Smoke Test

**The four documented tool names are the catalog.** Do not gate setup on a tool count. A
count from the transitional endpoint is not an interface and proves nothing about the v2
endpoints or about entitlement.

For Claude Code (documented path), authorize OAuth in the client, then confirm the four
documented tools appear in the client's server view (or record `tools/list` yourself if the
client exposes it). Save the capture as the level-4 evidence for this box.

For the transitional OpenClaw registration, this probe is a reachability check only:

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
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('transitional /mcp/ tools:', [t.get('name') for t in d.get('result',{}).get('tools',[])])"
```

Record the names. Expected documented names for the official catalog are the four above;
anything else is a legacy surface and is **UNVERIFIED** as current catalog. Do not STOP on a
count. If the call fails, distinguish auth/scope (401/403) from transport (DNS/TLS/406) and
report the exact failure.

### Action 5: Verify the retired community MCP is OFF — do not install it

The self-hosted community MCP (`ghl-community-mcp`) is **retired from the update and install
paths**. Fresh installs omit it. Updated boxes must verify it is off, not repair it.

**Do not** clone it, check out its pin, run `npm install` / `npm run build`, write its `.env`,
install a launchd / pm2 / systemd unit for it, or run its autostart / probe scripts. There is
no tool-count target to chase: the old 588 / 858 / 500 figures describe other profiles or
history and prove nothing about parity. (For the record, the last vetted profile was
`curated` = **43 crm tools**, smoke tool `crm_list_workspaces`, loopback `127.0.0.1:8765` —
but that describes a service that must now be **absent**.)

#### 5.1 Required end state (verify each line)

```bash
# 1. No registration (exact name)
openclaw mcp list | grep -w ghl-community-mcp && echo "STILL REGISTERED" || echo "registration: absent"

# 2. URL env var gone
openclaw config get env.vars.GHL_COMMUNITY_MCP_URL 2>&1 | grep -q "http" && echo "ENV VAR STILL SET" || echo "env var: absent"

# 3. macOS — job not loaded, plist archived (not deleted; archive is evidence)
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

A `RunAtLoad=true` job that is merely stopped will resurface at the next login. Stopped is not
retired. Unload **and** disable it, and remove or make retirement-aware every probe that would
kickstart it.

#### 5.2 De-registration (exact verbs)

```bash
# The verb is `unset`, not `remove`. `openclaw mcp remove` exits 1 on OpenClaw 2026.7.1-2
# ("Too many arguments for this command"), and every old call site swallowed that with
# `|| true` — which is why Tier 2 was never actually de-registered on any box.
openclaw mcp unset ghl-community-mcp

# Remove the URL var (it belonged to the retired service)
openclaw config unset env.vars.GHL_COMMUNITY_MCP_URL 2>/dev/null || true

# RE-READ: the gateway can rewrite openclaw.json from memory and undo a file-level removal.
openclaw mcp list
```

**Name collision — do not break the official connection.** The official `mcp.servers` entry is
also named `ghl-mcp`, and the retired community **systemd unit** is named `ghl-mcp` too. They
are different things. Never stop, delete, or disable anything by matching the bare string
`ghl-mcp`; de-register only `ghl-community-mcp`, and stop only the unit you have first proven
belongs to the community service.

**Preserved surfaces.** Retirement must not touch:
- the official MCP connection (`ghl-mcp` / `leadconnector`)
- the custom courier MCP
- shared credentials and customer data
- `~/.openclaw/secrets/.env` (do not delete the PIT; Tier 0/3 still use it)

#### 5.3 Historical manual rollback (operator decision only)

The community tier can be restored only by an explicit operator decision, never by an
installer, an update script, or an agent "repairing" a box.

- Mirror: `https://github.com/trevorotts1/ghl-community-mcp-mirror.git`
- Vetted pin: `32628c979dd8f46e7952f85ce2d98f8028a26c32`
- Vetted profile: `curated` (43 crm tools), smoke tool `crm_list_workspaces`
- Loopback: `127.0.0.1:8765`
- Archive path: the path recorded in that box's retirement receipt (archive path + digest).
  The source tree it captures is `~/mcp-servers/ghl-community-mcp` (Mac) or
  `/data/mcp-servers/ghl-community-mcp` (VPS). Never archive a secret-bearing `.env`; archive
  a redacted manifest (key names only).

Restoration is an explicit, recorded operator decision. It must be proven on one box first,
and it must restore supervision, the probe, and registration together — a half-restored
service is the deaf-server failure this retirement ends.

### Action 6: Verify the retirement on this box

Run the six checks in 5.1 and record the output as the box's retirement receipt. Expected:

- registration, env var, pm2 app, systemd enablement, listener, and probe: **absent**
- official MCP connection: **present**
- custom courier MCP: **present and untouched**

There is no Tier 2 smoke test any more. If `/health` on 8765 answers, the box is not retired.
Do not "fix" that by restarting the service; finish the retirement. If something else owns
8765, that is not a GHL service — do not kill it (port 8000 belongs to Cognee on most boxes;
8765 can be claimed by unrelated processes after the fact).

### Action 7: Update Core .md Files

Read `CORE_UPDATES.md` for exact text to add to:
- AGENTS.md (canonical state block + 🔴 Tier Escalation Protocol + tier order + anti-patterns + disclosure protocol)
- TOOLS.md (official MCP surface + retirement state; no community tool reference)
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

Expected operator-channel response opens with a Tier 0 or Tier 3 disclosure — e.g.
`[GHL tier used: 0 — convertandflow products list]` or
`[GHL tier used: 3 (Tier 1 lacked operation: products.list) — raw API GET /products/]` — and
lists real products. There is no Tier 2 route; a Tier 2 disclosure means stale docs are loaded.

If the response has no disclosure header, the agent isn't loading AGENTS.md properly.
Investigate channel routing.

---

## Done When

- [ ] Official MCP connection present (`ghl-mcp` / `leadconnector`), authorized on the
      client-appropriate v2 endpoint where the client supports it; documented four-tool
      catalog recorded; `tools/list` capture saved as this box's level-4 evidence
- [ ] **Community MCP retired**: `ghl-community-mcp` absent from `openclaw mcp list`
- [ ] `GHL_COMMUNITY_MCP_URL` env var absent
- [ ] No listener on `127.0.0.1:8765`; no loaded/enabled launchd / pm2 / systemd unit
      (`com.clawd.ghl-mcp`, `ghl-community-mcp`, `ghl-mcp.service`) — the
      `RunAtLoad=true` job must be unloaded and disabled, not merely stopped
- [ ] Probe job removed or retirement-aware (no kickstart of the retired service)
- [ ] Custom courier MCP present and untouched; shared credentials and customer data intact
- [ ] No community `.env` remains unarchived with a secret in it; archived material is a
      redacted manifest (key names only)
- [ ] AGENTS.md / TOOLS.md / MEMORY.md updated per CORE_UPDATES.md (SOUL.md unchanged)
- [ ] Full reference copied to `$MASTER_FILES_DIR/36-ghl-mcp-setup/`
- [ ] `qc-ghl-mcp-setup.sh` exits 0 (or its community assertions are the known-stale W07
      set and are recorded as such — do not reinstall the service to make them pass)
- [ ] User verification prompt returns correct disclosure header
