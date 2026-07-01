# GHL API Skill - Installation Guide

> **N24 — Use the teach-yourself-protocol (Skill 01):** Before any action in this skill, the installing sub-agent MUST read every file under skills/01-teach-yourself-protocol/ and follow its procedural read-order. No shortcuts.


> **TYP Read Order:** Read ALL files in this folder before using the skill.
> This file covers environment variables, dependency checks, and a smoke test.

---

## TYP Mandatory Read Order

Read these files in sequence before doing any GHL API work:

1. `SKILL.md` - Overview, trigger map, quick reference (read first - always)
2. `INSTALL.md` - This file. Environment setup and smoke test.
3. `INSTRUCTIONS.md` - How to execute GHL workflows step by step.
4. `EXAMPLES.md` - Real examples you can adapt immediately.
5. `CORE_UPDATES.md` - Text to add to TOOLS.md and MEMORY.md (do this once at install).
6. `references/<domain>.md` - Read ONLY the specific domain file you need at query time.

**Do NOT read all reference files upfront.** They are large. Read them on demand.

---

## Environment Variables Required

| Variable | Purpose | Example |
|----------|---------|---------|
| `GOHIGHLEVEL_API_KEY` | Your LOCATION-scoped Private Integration Token | `pit-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `GOHIGHLEVEL_LOCATION_ID` | Your sub-account (location) ID | `abc123XYZlocationId` |

### Where to Find These Values

**GOHIGHLEVEL_API_KEY (Private Integration Token):**

1. Open your browser and go to: `https://app.gohighlevel.com` (or your white-label URL)
2. Log in to your agency account
3. Click **Settings** in the left sidebar
4. Click **Integrations**
5. Click the **Private Integrations** tab
6. If you already have a private integration, click its name to view the token
7. If you need to create one:
   - Click **+ Add Private Integration**
   - Give it a name (example: "OpenClaw Agent")
   - Select the permission scopes you need (see scope requirements in each reference file)
   - Click **Create**
   - Copy the token that appears - it will only show once
8. This token is your `GOHIGHLEVEL_API_KEY`

**GOHIGHLEVEL_LOCATION_ID (Sub-Account ID):**

1. In GHL, click on the sub-account (location) you want to work with
2. Look at the URL in your browser - it will look like: `https://app.gohighlevel.com/location/abc123XYZlocationId/...`
3. The part after `/location/` and before the next `/` is your location ID
4. Alternatively: Go to **Settings > Business Profile** inside the sub-account - the location ID appears there

---

## Setting Up Environment Variables

Add these to your shell profile or OpenClaw secrets file:

### Option A: Shell profile (persistent across sessions)

```bash
# Add to ~/.zshrc or ~/.bash_profile
export GOHIGHLEVEL_API_KEY="your_private_integration_token_here"
export GOHIGHLEVEL_LOCATION_ID="your_location_id_here"
```

Then reload: `source ~/.zshrc`

### Option B: OpenClaw secrets file (recommended for agent access)

```bash
# Add to ~/.openclaw/secrets/.env
GOHIGHLEVEL_API_KEY=your_private_integration_token_here
GOHIGHLEVEL_LOCATION_ID=your_location_id_here
```

### Option C: Per-session export (temporary, for testing)

```bash
export GOHIGHLEVEL_API_KEY="your_private_integration_token_here"
export GOHIGHLEVEL_LOCATION_ID="your_location_id_here"
```

---

## Smoke Test

Run this command to confirm your credentials work. It should return JSON describing your location/sub-account.

```bash
# Load creds (resolver: maps legacy aliases, blocks loudly if unset — see SKILL.md "Credentials")
[ -f ~/.openclaw/secrets/.env ] && { set -a; . ~/.openclaw/secrets/.env; set +a; }
: "${GOHIGHLEVEL_API_KEY:=${GHL_API_KEY:-${GHL_PIT:-${GHL_TOKEN:-${GHL_PRIVATE_INTEGRATION_TOKEN:-${PRIVATE_INTEGRATION_TOKEN:-${GHL_PRIVATE_TOKEN:-${PIT_TOKEN:-${GHL_PIT_TOKEN:-${GOHIGHLEVEL_LOCATION_PIT:-${GHL_LOCATION_PIT:-}}}}}}}}}}}}"
: "${GOHIGHLEVEL_LOCATION_ID:=${GHL_LOCATION_ID:-}}"
if [ -z "${GOHIGHLEVEL_API_KEY:-}" ] || [ -z "${GOHIGHLEVEL_LOCATION_ID:-}" ]; then
  echo "BLOCKED: set GOHIGHLEVEL_API_KEY + GOHIGHLEVEL_LOCATION_ID in ~/.openclaw/secrets/.env (chmod 600) first." >&2
else
  curl -s \
    -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
    -H "Version: 2021-04-15" \
    "https://services.leadconnectorhq.com/locations/$GOHIGHLEVEL_LOCATION_ID" | python3 -m json.tool
fi
```

**Expected result:** JSON object with `id`, `name`, `email`, `address`, and other location fields.

**If you see a 401 error:**
- Your token may be expired or invalid
- Check that you copied the full token (they are long - do not truncate)
- Verify the token was created as a Private Integration Token (not an API key - those are deprecated)

**If you see a 403 error:**
- Your token exists but lacks the required scope for this endpoint
- Go back to GHL Settings > Integrations > Private Integrations
- Edit the integration and add the `locations.readonly` scope
- Save and retry

**If you see a 404 error:**
- Your `GOHIGHLEVEL_LOCATION_ID` is wrong
- Double-check the location ID from the URL or Settings page

---

## Dependencies

This skill uses standard shell tools only. No extra packages needed.

| Tool | Purpose | Check |
|------|---------|-------|
| `curl` | Make API calls | `curl --version` |
| `python3` | Pretty-print JSON | `python3 --version` |
| `jq` (optional) | Advanced JSON filtering | `jq --version` |

### Optional: jq for Better JSON Handling

```bash
# macOS
brew install jq

# Usage example - get just the location name
curl -s \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-04-15" \
  "https://services.leadconnectorhq.com/locations/$GOHIGHLEVEL_LOCATION_ID" | jq '.name'
```

---

## CORE_UPDATES.md - One-Time Step

After confirming the smoke test works:

1. Open `CORE_UPDATES.md` in this folder
2. Copy the exact text blocks shown for TOOLS.md and MEMORY.md
3. Paste them into the corresponding sections of your core files
4. This registers the skill with your agent's memory - done once, permanent

---

## What the Agent Needs to Know at Runtime

The agent does NOT need to keep all reference files loaded. At runtime:

1. Check if `GOHIGHLEVEL_API_KEY` and `GOHIGHLEVEL_LOCATION_ID` are set in environment or secrets
2. Read the trigger map in `SKILL.md` to identify the right domain file
3. Read only the specific `references/*.md` file needed
4. Build the API call from the template in that file
5. Execute with real env var values substituted in

---

## 🔴 GATEWAY RESTART PROTOCOL - NEVER TRIGGER AUTONOMOUSLY

**During this installation, you may encounter instructions to restart the OpenClaw gateway.**

**YOU ARE FORBIDDEN from triggering gateway restarts yourself.**

### Correct Process
When a gateway restart is needed:
1. **STOP** - Do NOT execute the restart command
2. **NOTIFY** the user: "This installation requires an OpenClaw gateway restart to complete."
3. **INSTRUCT**: "Type `/restart` in Telegram to trigger it"
4. **WAIT** for user action - do NOT proceed until confirmed

### Forbidden Actions
- Do NOT run `openclaw gateway restart` without explicit user permission
- Do NOT say "I will restart the gateway now" without asking first
- Do NOT assume the user wants the restart

---
