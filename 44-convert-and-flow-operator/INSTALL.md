# Skill 44 — Convert and Flow Operator: Install Guide

## Prerequisites

- Skill 01 (TYP) installed
- Skill 02 (BYUP) installed — back up config before editing
- Skill 36 (GHL MCP Setup) installed — skill 44 is Tier 0 in skill 36's chain
- Skill 41 (Build With AI Playbook) installed — skill 44 consumes its dependency-first contract
- Python 3.9+ on the install box
- Active GHL / Convert and Flow account with a Location PIT

---

## Action 1: Detect platform

```bash
if [[ "$(uname)" == "Darwin" ]]; then
  PLATFORM="mac"
  TOOLS_ROOT="$HOME/.openclaw/tools"
else
  PLATFORM="vps"
  TOOLS_ROOT="/data/.openclaw/tools"
fi
CAF_DIR="$TOOLS_ROOT/convert-and-flow-cli"
```

## Action 2: Create venv and install engine

```bash
mkdir -p "$CAF_DIR"
python3 -m venv "$CAF_DIR/.venv"
source "$CAF_DIR/.venv/bin/activate"

# Copy engine from master files
cp -r "$MASTER_FILES_DIR/44-convert-and-flow-operator/tools/engine/." "$CAF_DIR/engine/"
cd "$CAF_DIR/engine"
pip install -e . --quiet
deactivate
```

## Action 3: Write the wrapper (maps canonical env -> engine env at runtime)

```bash
cat > "$CAF_DIR/caf" <<'WRAPPER'
#!/usr/bin/env bash
# Convert and Flow CLI wrapper — maps canonical GOHIGHLEVEL_* env to engine env
# Also accepts CAF_* aliases for backwards compatibility.
set -euo pipefail

VENV="$(dirname "$0")/.venv"
ENGINE="$(dirname "$0")/engine"

# Canonical -> engine mapping (engine uses GHL_API_KEY internally)
export GHL_API_KEY="${GOHIGHLEVEL_API_KEY:-${CAF_API_KEY:-}}"
export GHL_LOCATION_ID="${GOHIGHLEVEL_LOCATION_ID:-${CAF_LOCATION_ID:-}}"
export GHL_FIREBASE_REFRESH_TOKEN="${GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN:-${CAF_FIREBASE_REFRESH_TOKEN:-}}"
export GHL_ALLOWED_LOCATION_IDS="${GOHIGHLEVEL_ALLOWED_LOCATION_IDS:-${CAF_ALLOWED_LOCATION_IDS:-}}"
export GHL_DRAFT_ONLY="${GOHIGHLEVEL_DRAFT_ONLY:-${CAF_DRAFT_ONLY:-true}}"

# Snapshot dir for workflow rollbacks
export GHL_SNAPSHOT_DIR="${HOME}/.openclaw/tools/convert-and-flow-cli/data/snapshots"
mkdir -p "$GHL_SNAPSHOT_DIR"

exec "$VENV/bin/python" -m cli_anything.gohighlevel.main "$@"
WRAPPER
chmod +x "$CAF_DIR/caf"

# Create aliases
ln -sf "$CAF_DIR/caf" "$CAF_DIR/convertandflow"
ln -sf "$CAF_DIR/caf" "$CAF_DIR/ghl"
```

## Action 4: Add wrapper dir to PATH (persistent)

### Mac
```bash
# Add to .zshrc (or .bash_profile)
echo "export PATH=\"$CAF_DIR:\$PATH\"" >> "$HOME/.zshrc"
source "$HOME/.zshrc"

# Also wire via openclaw config
openclaw config set env.vars.PATH "$CAF_DIR:\${PATH}"
```

### VPS
```bash
# Add to openclaw gateway env
openclaw config set env.vars.PATH "$CAF_DIR:/usr/local/bin:/usr/bin:/bin"
```

## Action 5: Set credentials

Source from the canonical secrets file:
```bash
source ~/.openclaw/secrets/.env

# Verify required vars are set
[ -n "$GOHIGHLEVEL_API_KEY" ]    || { echo "ERROR: GOHIGHLEVEL_API_KEY not set"; exit 1; }
[ -n "$GOHIGHLEVEL_LOCATION_ID" ] || { echo "ERROR: GOHIGHLEVEL_LOCATION_ID not set"; exit 1; }
```

Wire into openclaw config (gateway reads from env.vars at runtime):
```bash
openclaw config set env.vars.GOHIGHLEVEL_API_KEY     "$GOHIGHLEVEL_API_KEY"
openclaw config set env.vars.GOHIGHLEVEL_LOCATION_ID "$GOHIGHLEVEL_LOCATION_ID"
openclaw config set env.vars.GOHIGHLEVEL_DRAFT_ONLY  "true"
```

Firebase token (workflow writes — OPTIONAL at install time):
```bash
# If the client has already captured their Firebase token:
openclaw config set env.vars.GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN "$GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN"
```

---

## Action 5b: Load the Token Grabber Chrome Extension (first time)

> **What this does:** The Token Grabber is a small Chrome extension that reads your
> Firebase refresh token from the logged-in GHL / Convert and Flow page and copies it
> to your clipboard. It makes **zero network calls** — it only reads from your own
> browser's storage.

### Get the extension folder

The extension folder is already included in this skill at:
```
44-convert-and-flow-operator/tools/chrome-extension/
```
It contains four files: `manifest.json`, `popup.html`, `popup.js`, `icon48.png`.

> **Do NOT upload this to the Chrome Web Store.** We are using the "load unpacked"
> method — the extension lives as a folder on your computer, not in the Chrome store.

### Install steps (one time)

1. Open Chrome and go to: **chrome://extensions**
2. Flip the **Developer mode** toggle in the top-right corner to **ON**.
3. Click the **"Load unpacked"** button that appears.
4. Navigate to the `tools/chrome-extension/` folder inside this skill and click **Select**.
5. The "Convert and Flow Token Grabber" extension will appear in your list. Done.

### Grab your token

1. Open any logged-in page on:
   - `https://app.convertandflow.com`
   - `https://app.gohighlevel.com`
   - `https://app.leadconnectorhq.com`
2. Click the extension icon in your Chrome toolbar.
3. Click **"Grab Refresh Token"**.
4. Click **"Copy to Clipboard"** — the token is now on your clipboard.

### Store the token

Paste the value into your secrets file:
```
GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=<paste token here>
```

Then wire it into OpenClaw:
```bash
openclaw config set env.vars.GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN "$GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN"
```

### After editing extension files

Because the extension is "unpacked" (not from the Chrome store), it does **not**
auto-update. If you ever edit the extension files, go back to **chrome://extensions**
and click the **↻ (refresh)** icon on the extension card to reload it.

> **Note on extension IDs:** Chrome assigns a unique extension ID when you load unpacked.
> Each computer gets its own ID — that is normal and expected. (The operator's installed
> copy has ID `mghmjilakepcjpjinhcgnnghenlfigid` as a reference example only; your ID
> will be different and does not affect how the extension works.)

---

## Action 6: Run `caf doctor`

```bash
caf doctor
```

Expected output: all checks green. If the Firebase token is absent, `caf doctor` should report
WARN (not FAIL) — the skill works for standard ops without it.

---

## Client-Facing Disclosure: Firebase Token Auto-Re-Grab (Mac installs only)

> **PLAIN LANGUAGE (binding transparency requirement — PRD Section 3.2):**
>
> On Mac installs, your AI agent can refresh the Convert and Flow / GoHighLevel
> access token automatically when it expires. Here is what that means in plain language:
>
> - This token is the same one you copied from your browser at onboarding.
> - When it expires, your agent reads a fresh copy from your own logged-in Chrome
>   profile on THIS Mac — the same profile you normally browse in.
> - The token never leaves your Mac except into your own secrets file on this same machine.
> - Every time the agent refreshes the token, it logs a notification to your Telegram channel.
>   Nothing is silent.
> - If you ever want to turn this off, remove `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN` from your
>   secrets file. The agent will ask you to re-grab it manually next time it needs a workflow build.
>
> **VPS installs:** there is no Chrome in the container, so the agent cannot auto-re-grab.
> On a VPS, the agent will notify you via Telegram: "I need you to grab the Convert and Flow
> token to build workflows directly" — you copy it from your browser and paste it in.

---

## Done When

- [ ] `caf doctor` exits green (or WARN for missing Firebase token — not FAIL)
- [ ] `caf contacts list --limit 3` returns real contacts
- [ ] `caf workflows list` returns the workflow list
- [ ] `caf` resolves on PATH inside openclaw gateway
- [ ] `qc-convert-and-flow.sh` exits 0
- [ ] CORE_UPDATES.md sentinel written to AGENTS.md / TOOLS.md / MEMORY.md
