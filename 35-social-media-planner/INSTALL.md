# Social Media Planner (Skill 35) — Installation Guide

> **N24 — Use the teach-yourself-protocol (Skill 01):** Before any action in this skill, the installing sub-agent MUST read every file under skills/01-teach-yourself-protocol/ and follow its procedural read-order. No shortcuts.


**Skill version:** v2.0.0 (canonical env-var migration + MCP-first routing)

---

## Mandatory pre-install discipline contract

Before you touch anything, read **`INSTALL-CONTRACT.md`** at the root of this onboarding repo. It binds you to:
- Read EVERY .md file in this skill folder before executing any step
- Follow INSTALL.md step order verbatim — no skipping, no reordering, no improvising
- Pass QC.md with score 8.5/10+ or LOOP back and fix (max 5 loops, then escalate)
- Never use `--force`, `--break-system-packages`, `--no-verify`, model substitution, or step invention
- Sub-agents NEVER call `openclaw gateway restart` — that's master-orchestrator only, and only when `openclaw subagents list` is empty

If you have not read the contract, STOP and read it now.

---

## Prerequisites

### Required Skills (install these BEFORE Skill 35)

| Skill | Why it's needed |
|-------|---|
| **01 — Teach Yourself Protocol** | Required by INSTALL-CONTRACT.md. Governs how you store knowledge from this skill. |
| **02 — Back Yourself Up Protocol** | Required before any config change for this skill. |
| **22 — Book-to-Persona** | Content uses persona governance (5-layer alignment). Without it, content defaults to soul.md tone only. |
| **31 — Upgraded Memory System** | Weekly content logs go into memory-core. Without it, logs land in MEMORY.md directly. |
| **36 — GHL MCP Setup** | **STRONGLY RECOMMENDED.** When installed, ALL GHL operations in this skill route through MCPs first (Tier 1 → Tier 2 → fall to raw API as last resort). Without skill 36, this skill falls back to direct GHL Social Planner API. |
| **30 — Fish Audio API Reference** | OPTIONAL. Required only if the client wants podcast episodes. If absent, podcast production is skipped and other content continues. |

**Auto-check the prerequisites:**
```bash
# Required prerequisites — Skill 35 install BLOCKS if any of these are missing.
for skill in 01-teach-yourself-protocol 02-back-yourself-up-protocol 22-book-to-persona-coaching-leadership-system 31-upgraded-memory-system; do
  if [ -d "$HOME/.openclaw/skills/$skill" ]; then
    echo "  ✓ $skill installed (required)"
  else
    echo "  ✗ $skill MISSING (required — install before continuing)"
  fi
done

# Optional prerequisites — Skill 35 still installs without these. Missing = info, not error.
for skill in 36-ghl-mcp-setup 30-fish-audio-api-reference; do
  if [ -d "$HOME/.openclaw/skills/$skill" ]; then
    echo "  ✓ $skill installed (optional — feature enabled)"
  else
    case "$skill" in
      36-ghl-mcp-setup)              REASON="MCP-first routing disabled; falls back to direct GHL API";;
      30-fish-audio-api-reference)   REASON="podcast voiceover production disabled; all other features run normally";;
    esac
    echo "  ⓘ $skill not installed (optional — $REASON)"
  fi
done
```

> **Skill 30 (Fish Audio) is OPTIONAL.** If it is not installed, Skill 35 still installs and runs. The podcast production step (`Phase 2 → Audio Generator + Podcast Publisher`) is skipped gracefully and Skill 35 writes `PODCAST_DEFERRED=true` to MEMORY.md so QC, the weekly heartbeat, and downstream agents all know the skip is intentional, not a failure. If Fish Audio is installed later, edit MEMORY.md to remove `PODCAST_DEFERRED` and the next weekly run will re-enable the podcast pipeline.

---

## Required credentials — CANONICAL paths and env-var names

⚠️ **This skill uses the same canonical credential paths as Skill 05 and Skill 36. DO NOT invent new variable names. DO NOT use deprecated paths.**

### Canonical storage locations
- **macOS:** `~/.openclaw/secrets/.env`
- **VPS:** `~/.openclaw/secrets/.env`
- **Secondary mirror:** `openclaw.json` `env.vars` (gateway reads here at runtime)

### Required env-var names (DO NOT rename — Skill 36 and Skill 05 use these)

| Conceptual value | Canonical env-var name | Format |
|---|---|---|
| GoHighLevel Location Private Integration Token | **`GOHIGHLEVEL_API_KEY`** (legacy name — its value IS a PIT, despite the "_API_KEY" suffix) | `pit-xxxxxxxx-xxxx-...` |
| GoHighLevel Location ID | **`GOHIGHLEVEL_LOCATION_ID`** | 22-char alphanumeric |
| kie.ai API key | `KIE_API_KEY` | provider-specific |
| Fish Audio API key (OPTIONAL) | `FISH_AUDIO_API_KEY` | provider-specific |
| Fish Audio Voice ID (OPTIONAL) | `FISH_AUDIO_VOICE_ID` | string |
| Podbean Channel ID (OPTIONAL) | `PODBEAN_PODCAST_ID` | provider-specific |

⛔ **DEPRECATED names you may see in older skill docs — DO NOT use:** `GHL_PRIVATE_TOKEN`, `GHL_API_KEY` (Skill 36 era reusable but Skill 35 uses `GOHIGHLEVEL_API_KEY` now), `GHL_LOCATION_ID` (use `GOHIGHLEVEL_LOCATION_ID`). If you see these in `secrets/.env`, the auto-search step below will detect both old and new and surface a migration note.

### Required GHL PIT scopes

The Private Integration Token must have these scopes (matches Skill 36's recommended set since this skill cross-uses MCP tools):

- `contacts.readonly` + `contacts.write`
- `conversations.readonly` + `conversations.write`
- `opportunities.readonly` + `opportunities.write`
- `calendars.readonly` + `calendars.write`
- `locations.readonly` + `locations.write`
- `workflows.readonly`
- `blogs.readonly` + `blogs.write`
- `users.readonly`
- `custom_objects.readonly` + `custom_objects.write`
- `invoices.readonly` + `invoices.write`
- `payments.readonly`
- `products.readonly` + `products.write`
- **`medias.write`** (REQUIRED for this skill — media uploads to GHL CDN)
- **`social-media-posting.readonly` + `social-media-posting.write`** (REQUIRED for this skill)

⚠️ If the PIT lacks any required scope, the install will surface a specific 403 error from GHL. DO NOT "auto-fix" by trying a different env var — STOP and ask the client to add the missing scope in GHL Settings → Integrations → Private Integrations.

### Required software

```bash
ffmpeg -version | head -1     # must be ≥4.0
convert -version | head -1    # ImageMagick
python3 --version             # ≥3.8
```

If any are missing: `brew install ffmpeg imagemagick python3` (Mac) / `sudo apt install ffmpeg imagemagick python3` (VPS).

---

## Installation Steps (follow IN ORDER — no skipping)

### Step 0: Confirm contract loaded + read all 5 files

Before any system change:
1. Verify INSTALL-CONTRACT.md was read this session (the cron orchestrator session, or a fresh `/new` session if this is a manual install)
2. Read these 5 files in this skill folder in this exact order:
   - `SKILL.md` — overview + 15+6 agent model
   - `INSTALL.md` — this file
   - `CORE_UPDATES.md` — what to add to client core files
   - `QC.md` — quality control (with new 0–10 rubric in v2.0.0)
   - `references/playbook.md` — the 1,656-line production playbook

Do NOT proceed until all 5 are read.

### Step 1: Canonical Mac paths

```bash
SECRETS_ENV=$HOME/.openclaw/secrets/.env
WORKSPACE=$HOME/clawd                # most existing Mac clients
[ ! -d "$WORKSPACE" ] && WORKSPACE=$HOME/.openclaw/workspace   # fresh OpenClaw default
```

### Step 2: Search ALL canonical credential locations before asking

```bash
# Search canonical first, then legacy locations
for FILE in "$SECRETS_ENV" \
            "$HOME/.openclaw/secrets/.env" \
            "~/.openclaw/secrets/.env" \
            "$HOME/clawd/secrets/.env" \
            "$HOME/.env"; do
  [ -f "$FILE" ] && grep -E "^(GOHIGHLEVEL_API_KEY|GOHIGHLEVEL_LOCATION_ID|KIE_API_KEY|FISH_AUDIO_API_KEY|FISH_AUDIO_VOICE_ID|PODBEAN_PODCAST_ID)=" "$FILE" 2>/dev/null
done

# Also check openclaw.json env.vars
python3 -c "
import json
for path in ['$HOME/.openclaw/openclaw.json', '~/.openclaw/openclaw.json']:
  try:
    cfg=json.load(open(path))
    ev=cfg.get('env',{}).get('vars',{})
    for k in ['GOHIGHLEVEL_API_KEY','GOHIGHLEVEL_LOCATION_ID','KIE_API_KEY','FISH_AUDIO_API_KEY','FISH_AUDIO_VOICE_ID','PODBEAN_PODCAST_ID']:
      v=ev.get(k,'')
      if v: print(f'  ✓ {k}=<set, prefix {v[:8]}...>')
  except: pass
"

# Live env
env | grep -E "^(GOHIGHLEVEL_API_KEY|GOHIGHLEVEL_LOCATION_ID|KIE_API_KEY|FISH_AUDIO)" | sed 's/=\(.\{0,10\}\).*/=\1.../'
```

**If both `GOHIGHLEVEL_API_KEY` AND `GOHIGHLEVEL_LOCATION_ID` are found, skip to Step 4.**

**If you find them under DEPRECATED names** (`GHL_PRIVATE_TOKEN`, `GHL_API_KEY`, `GHL_LOCATION_ID`): copy the values to the canonical names in `$SECRETS_ENV`. Keep the old entries too (for backwards-compat). Do not delete originals.

**If they're missing from everywhere:** proceed to Step 3.

### Step 3: Ask client for missing credentials (only if Step 2 failed)

Send the client this exact message:

> "I couldn't find your GoHighLevel credentials in your environment. I need two things:
>
> 1. **Location ID** — open your GHL/Convert and Flow account → Settings → Company → Locations → click the location → copy the ID at the top (22 characters).
>
> 2. **Private Integration Token** — Settings → Integrations → Private Integrations → Create New Private Integration → enable ALL these scopes:
>    - contacts.readonly + write
>    - conversations.readonly + write
>    - opportunities.readonly + write
>    - calendars.readonly + write
>    - locations.readonly + write
>    - workflows.readonly
>    - blogs.readonly + write
>    - users.readonly
>    - custom_objects.readonly + write
>    - invoices.readonly + write
>    - payments.readonly
>    - products.readonly + write
>    - **medias.write**
>    - **social-media-posting.readonly + write**
>
>    Save, copy the token (starts with `pit-`), and paste both values here."

Store them:
```bash
mkdir -p "$(dirname "$SECRETS_ENV")"
chmod 600 "$SECRETS_ENV" 2>/dev/null
cat >> "$SECRETS_ENV" <<EOF
GOHIGHLEVEL_API_KEY=pit-XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
GOHIGHLEVEL_LOCATION_ID=YYYYYYYYYYYYYYYYYYYYYY
EOF

openclaw config set env.vars.GOHIGHLEVEL_API_KEY "pit-XXXXXXXX-..."
openclaw config set env.vars.GOHIGHLEVEL_LOCATION_ID "YYYYYYYYYYYYYYYYYYYYYY"
```

Never echo the PIT into chat logs.

### Step 4: Detect Skill 44 (Tier 0 CLI) + Skill 36 (GHL MCPs) and configure routing

```bash
if [ -d "$HOME/.openclaw/skills/44-convert-and-flow-operator" ] || [ -d "~/.openclaw/skills/44-convert-and-flow-operator" ]; then
  CAF_AVAILABLE="yes"
  echo "  ✓ Skill 44 (Tier 0 caf) detected — social posting/scheduling routes through caf FIRST"
else
  CAF_AVAILABLE="no"
fi
if [ -d "$HOME/.openclaw/skills/36-ghl-mcp-setup" ] || [ -d "~/.openclaw/skills/36-ghl-mcp-setup" ]; then
  ROUTING_MODE="mcp-first"
  echo "  ✓ Skill 36 detected — Skill 35 will route GHL operations through MCPs (after Tier 0 caf)"
else
  ROUTING_MODE="direct-api"
  echo "  ⚠ Skill 36 NOT installed — Skill 35 falls to direct GHL Social Planner API after Tier 0"
  echo "    STRONGLY RECOMMENDED: install Skill 44 (Tier 0) and Skill 36 first for better reliability"
fi
```

The production playbook follows the 6-tier chain (skill 36), highest applicable tier first:
- **Social posting:** Tier 0 `caf social schedule` (if Skill 44 installed) → Tier 1 `social-media-posting_create-post` → Tier 2 `create_social_post` → direct API as last resort
- **Blog publish:** Tier 1 `blogs_create-blog-post` → Tier 2 `create_blog_post` → direct API
- **Media upload:** Tier 0/Tier 1 not available (no caf/official-MCP media command) → Tier 2 `upload_media_file` → direct API (`POST /medias/upload-file` — documented Tier 3 exception)
- **Email templates:** Tier 1 `emails_create-template` → Tier 2 `create_email_template` → direct API

Every GHL-data response from this skill MUST include the `[GHL tier used: N — tool_name]` disclosure header (Skill 36 protocol).

### Step 5: Verify GHL access — test ONE platform connection

Pick Facebook as the smoke test. Use whichever tier matches `ROUTING_MODE`.

**MCP-first (Skill 36 installed):**
```bash
curl -sS -X POST "$GHL_COMMUNITY_MCP_URL/execute" \
  -H "Content-Type: application/json" \
  -d '{"name":"get_platform_accounts","arguments":{"limit":1}}' | python3 -m json.tool | head -20
```

**Direct API (Skill 36 NOT installed):**
```bash
. "$SECRETS_ENV"
curl -sS \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-07-28" \
  "https://services.leadconnectorhq.com/social-media-posting/oauth/$GOHIGHLEVEL_LOCATION_ID/facebook/accounts" \
  | python3 -m json.tool | head -20
```

Expected: JSON with at least one connected account. If you get 403, the PIT is missing a scope — go back to Step 3 and have the client add it.

### Step 6: Verify FFmpeg + ImageMagick

```bash
ffmpeg -version | head -1 || { echo "FFmpeg missing — install: brew install ffmpeg"; exit 1; }
convert -version | head -1 || { echo "ImageMagick missing — install: brew install imagemagick"; exit 1; }
```

### Step 7: Run First-Run Protocol (references/playbook.md Section 0)

Read brand info from core files, then ask only what's missing:
1. Read `identity.md`, `soul.md`, `memory.md`, `agents.md`, `heartbeat.md`
2. Extract: brand name, founder, target audience, brand colors, tone, voice, products/services
3. Ask ONLY for items not found in core files
4. Establish the client's content Google Sheet — **ADOPT EXISTING SHEET FIRST, then create**:

   **4a. Check MEMORY.md** for an existing `content_sheet_id` or `content_sheet_url`. If found, use it — never create a duplicate. Skip to step 4d.

   **4b. Check if an existing sheet ID was provided during onboarding** (e.g. Angeleen's is `1RKgS5l-i6NBtf_vON49nBPdHe-F5W67RF9ym-S67L2c`). If yes, adopt it — skip to 4d.

   **4c. If no existing sheet:** create via n8n webhook (no client credentials required — the webhook uses the BlackCEO Automations service account):
   ```bash
   RESPONSE=$(curl -s -X POST "https://main.blackceoautomations.com/webhook/social-planner-sheet-create" \
     -H "Content-Type: application/json" \
     -d "{\"brandName\":\"$BRAND_NAME\",\"clientEmail\":\"$CLIENT_EMAIL\"}")
   SHEET_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['sheetId'])")
   SHEET_URL=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['sheetUrl'])")
   ```
   If the webhook fails after 3 retries: use Angeleen's template ID `1RKgS5l-i6NBtf_vON49nBPdHe-F5W67RF9ym-S67L2c` as a fallback reference — tell the client to go to `https://docs.google.com/spreadsheets/d/1RKgS5l-i6NBtf_vON49nBPdHe-F5W67RF9ym-S67L2c/edit`, click File → Make a Copy, rename it, share the link back.

   **4d. Record `content_sheet_id` and `content_sheet_url` in MEMORY.md and skill config:**
   ```bash
   # Write to MEMORY.md (under ## Skill 35 — Social Media Planner section)
   # content_sheet_id: $SHEET_ID
   # content_sheet_url: $SHEET_URL

   # Wire into openclaw config so the agent can read it at runtime
   openclaw config set env.vars.SKILL35_CONTENT_SHEET_ID "$SHEET_ID"
   openclaw config set env.vars.SKILL35_CONTENT_SHEET_URL "$SHEET_URL"
   ```

   **4e. Verify the agent knows the link:**
   After writing config, the agent MUST be able to answer "what is my social media planner link?" by reading `content_sheet_url` from MEMORY.md. Test this before proceeding.

   **4f. Google Sheets write auth — TWO webhooks, TWO purposes (do NOT confuse them):**
   - **`social-planner-sheet-create`** (`POST https://main.blackceoautomations.com/webhook/social-planner-sheet-create`): used ONCE at install time to create a new Google Sheet for the client (copies the template, sets permissions). Payload: `{brandName, clientEmail}`. Never call this for row logging.
   - **`social-planner-row-append`** (`POST https://main.blackceoautomations.com/webhook/social-planner-row-append`): used on EVERY publish cycle to append a content row to the client's existing sheet. Payload: `{sheetId, row: {Week Of, Theme of the Week, Core Content, ..., Notes}}`. This is the row-log step in the Media Delivery Contract.

   The agent does NOT use Google Workspace OAuth or a `client_secret.json`. Both webhooks run on the BlackCEO Automations operator n8n and use the operator's Google service account — clients need no Google credentials. **The agent itself never calls the Google Sheets API directly.** If either webhook is unavailable, log to `~/.openclaw/data/skill35/content-log.jsonl` and queue for retry. The agent NEVER responds "gws is not authenticated" or "I don't have a client_secret.json".

5. Ask: "What action link should I include in social media comments this week?" → store as `SOCIAL_MEDIA_ACTION_LINK` in MEMORY.md.
6. Ask: "How many videos per week — 0, 2, or 7?" → store as `VIDEO_PREFERENCE` in MEMORY.md.
7. Ask: "Where should I send weekly notifications — Telegram, email, or text?" → store as `NOTIFICATION_CHANNEL` in MEMORY.md.
8. Ask about podcast — but FIRST auto-detect Fish Audio availability:
   ```bash
   if [ -d "$HOME/.openclaw/skills/30-fish-audio-api-reference" ] && [ -n "${FISH_AUDIO_API_KEY:-}" ] && [ -n "${FISH_AUDIO_VOICE_ID:-}" ]; then
     PODCAST_AVAILABLE=yes
   else
     PODCAST_AVAILABLE=no
   fi
   ```
   - If `PODCAST_AVAILABLE=yes`: ask "Do you want podcast episodes produced? Fish Audio + Podbean are configured. (yes/no/later)" → handle per response.
   - If `PODCAST_AVAILABLE=no`: do NOT ask. Auto-defer the podcast pipeline by appending `PODCAST_DEFERRED=true` to MEMORY.md (under a `## Skill 35 — Social Media Planner` section). Send the client this informational note:
     > "Your social media planner is installing without podcast production. Podcasts need Fish Audio (voice) + Podbean (hosting). To add podcasts later, install Skill 30 and set `FISH_AUDIO_API_KEY` + `FISH_AUDIO_VOICE_ID` + `PODBEAN_PODCAST_ID`, then ask me to remove `PODCAST_DEFERRED` from MEMORY.md. Everything else — images, videos, blogs, carousels, emails, comments — runs normally starting this week."

### Step 8: Apply CORE_UPDATES.md surgically

Add the LABELED sections from CORE_UPDATES.md ONLY to:
- `AGENTS.md` — social planner routing rules + MCP-first language
- `TOOLS.md` — GHL Social Planner tool reference
- `MEMORY.md` — weekly logging structure

Do NOT touch IDENTITY.md, HEARTBEAT.md, USER.md, or SOUL.md from this skill.

### Step 8.5: (v2.1.0) Set up the content calendar (optional, enables `weekly-batch.sh`)

The cron line documented in `INSTRUCTIONS.md` (`0 9 * * 1 bash …/weekly-batch.sh`) reads `~/.openclaw/config/content-calendar.json` and runs `run-publishing-cycle.sh` once per scheduled topic. The file is **opt-in** — `weekly-batch.sh` exits 0 with an informational message if it's missing.

```bash
mkdir -p ~/.openclaw/config
cp ~/.openclaw/skills/35-social-media-planner/scripts/content-calendar.example.json \
   ~/.openclaw/config/content-calendar.json
```

**Schema (v1.0):**

```json
{
  "version": "v1.0",
  "entries": [
    {
      "date": "2026-05-25",
      "topic": "...",
      "platforms": ["linkedin", "medium", "x", "wordpress"],
      "schedule": "auto"
    }
  ]
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `date` | yes | `YYYY-MM-DD` local timezone. |
| `topic` | yes | Passed to `run-publishing-cycle.sh --topic`. |
| `platforms` | yes | Same list `run-publishing-cycle.sh --platforms` accepts. |
| `schedule` | no  | `"auto"`, `"now"`, or ISO 8601 timestamp. |

### Step 9: Register the weekly theme cron (AUTOMATED — FAIL-LOUD)

> **FURNACE RULE — HARD BLOCK:** Do NOT add the Saturday theme-request task to HEARTBEAT.md. The agent reads HEARTBEAT.md on every heartbeat tick. Any recurring real-work task written there fires on every tick (potentially every 5–30 minutes) with no day-of-week gate, burning the metered model continuously. This is the proven root cause of the fleet-wide heartbeat token furnace. The correct enforcement mechanism is a hard cron.

Run the bundled registration script now. It is **fail-loud** — it exits non-zero if registration fails and the install MUST NOT proceed to Step 10 until exit 0 is confirmed.

```bash
# Resolve the skill directory (handles both Mac and VPS canonical paths)
SKILL35_DIR="${HOME}/.openclaw/skills/35-social-media-planner"
if [ ! -d "$SKILL35_DIR" ]; then
  SKILL35_DIR="/data/.openclaw/skills/35-social-media-planner"
fi

REGISTER_SCRIPT="${SKILL35_DIR}/scripts/register-weekly-cron.sh"
if [ ! -f "$REGISTER_SCRIPT" ]; then
  echo "ERROR: register-weekly-cron.sh not found at $REGISTER_SCRIPT" >&2
  echo "Skill 35 may not be installed at the expected path. Verify skill installation." >&2
  exit 1
fi

bash "$REGISTER_SCRIPT" || {
  echo "HARD FAIL: register-weekly-cron.sh exited non-zero." >&2
  echo "Skill 35 install INCOMPLETE — cron not registered. Fix the error above and re-run Step 9." >&2
  exit 1
}
```

The script:
- Is idempotent — skips if a healthy `skill35-weekly-theme` main-target cron already exists.
- Deduplicates — removes stale/erroring duplicate entries before registering a clean single entry.
- Asserts exactly 1 entry post-registration (hard-fail if count != 1).
- Pins the schedule to `0 8 * * 6` (Saturday 8:00 AM weekly only — furnace-safe).
- Uses `sessionTarget=main` (isolated + channel-deliver is rejected by the gateway).
- Marker path: `~/.openclaw/data/skill35/weekly-theme-last-run.json` (persistent across reboots; written by the cron on each fire to skip double-fires within the same ISO week).
- Model: cheap/free (flash or free OpenRouter fallback) — NOT the metered primary pro model.

**If the client's HEARTBEAT.md already contains the Saturday theme-request block** (from a prior install of this skill), remove it:

```bash
WORKSPACE_HEARTBEAT="${HOME}/.openclaw/workspace/HEARTBEAT.md"
if [ -f "$WORKSPACE_HEARTBEAT" ] && grep -q "Saturday 8:00 AM" "$WORKSPACE_HEARTBEAT"; then
  cp "$WORKSPACE_HEARTBEAT" "${WORKSPACE_HEARTBEAT}.bak-$(date +%Y%m%d%H%M%S)"
  python3 - <<'PYEOF'
import re, pathlib, os
p = pathlib.Path(os.environ['HOME'] + '/.openclaw/workspace/HEARTBEAT.md')
txt = p.read_text()
txt = re.sub(r'###\s+Saturday 8:00 AM.*?(?=\n###|\Z)', '', txt, flags=re.DOTALL).strip() + '\n'
p.write_text(txt)
print("Removed ungated Saturday block from HEARTBEAT.md")
PYEOF
else
  echo "No ungated Saturday block found — nothing to remove"
fi
```

### Step 10: Run QC.md and require 8.5+ to pass

Execute the QC.md checklist. Score against the v2.0.0 rubric. If score is **below 8.5**, loop back and fix until passing (max 5 loops, then escalate to client/Trevor).

If a bundled `qc-skill35.sh` script is present in this skill folder, run it. It MUST exit 0.

### Step 11: Confirm completion to client

Send the client this exact summary:

> ✅ Social Media Planner activated.
>
> • Content calendar sheet: [content_sheet_url from MEMORY.md]
> • GHL Social Planner connected via [MCP / direct API]
> • Finished media delivered as public links (GHL CDN — no attachment size limits)
> • Weekly theme heartbeat scheduled (Saturdays 8 AM)
> • Video preference: [0/2/7] per week
> • Podcast: [enabled / deferred]
> • Notification channel: [Telegram/email/text]
> • QC score: [N/10]
>
> Pending items needing your attention: [list, or "nothing"]

---

## Completion Checklist

- [ ] INSTALL-CONTRACT.md read this session
- [ ] All 5 skill files read (Step 0 complete)
- [ ] Required prerequisites verified (skills 01, 02, 22, 31 ALL installed)
- [ ] Optional prerequisites detected and handled (Skill 30 / Fish Audio: present → podcast enabled / absent → `PODCAST_DEFERRED=true` written to MEMORY.md; Skill 36 / GHL MCP: present → MCP-first / absent → direct-api fallback)
- [ ] Platform detected + canonical paths resolved
- [ ] `GOHIGHLEVEL_API_KEY` present at `$SECRETS_ENV` (NOT deprecated `GHL_PRIVATE_TOKEN`)
- [ ] `GOHIGHLEVEL_LOCATION_ID` present at `$SECRETS_ENV`
- [ ] All required PIT scopes confirmed (smoke test returned 200 + real data, no 403s)
- [ ] `KIE_API_KEY` present
- [ ] `FISH_AUDIO_API_KEY` + `FISH_AUDIO_VOICE_ID` present OR `PODCAST_DEFERRED=true` in MEMORY.md (OPTIONAL — either state is acceptable, install does not block)
- [ ] `PODBEAN_PODCAST_ID` present OR `PODCAST_DEFERRED=true` in MEMORY.md (OPTIONAL — either state is acceptable, install does not block)
- [ ] Skill 36 routing mode detected (mcp-first or direct-api), routing rules applied
- [ ] FFmpeg ≥4.0 working
- [ ] ImageMagick working
- [ ] First-Run Protocol complete (brand info, Google Sheet, action link, video preference, notifications)
- [ ] `content_sheet_id` present in MEMORY.md and `openclaw config env.vars.SKILL35_CONTENT_SHEET_ID`
- [ ] `content_sheet_url` present in MEMORY.md and `openclaw config env.vars.SKILL35_CONTENT_SHEET_URL`
- [ ] Agent can answer "what is my social media planner link?" without error
- [ ] Finished media delivery verified: upload to GHL Media Library → return CDN link → no raw Telegram file attachment for files >10 MB
- [ ] CORE_UPDATES.md applied surgically to AGENTS.md / TOOLS.md / MEMORY.md
- [ ] `register-weekly-cron.sh` exited 0 (Step 9 — hard fail if not)
- [ ] QC assert: `openclaw cron list | grep -c skill35-weekly-theme` == 1 (exactly one entry, main target, `0 8 * * 6`)
- [ ] HEARTBEAT.md does NOT contain the Saturday 8:00 AM theme-request block (ungated block removed if present)
- [ ] QC.md run with score 8.5/10+ (or loop completed)
- [ ] `qc-skill35.sh` exit 0 (if present)
- [ ] Client confirmation message sent

---

## What v2.0.0 changed (May 13, 2026)

- **Replaced `GHL_PRIVATE_TOKEN` with `GOHIGHLEVEL_API_KEY`** everywhere — eliminates the "auto-fix during install" bug where the agent had to remap names every time.
- **Migrated all credential paths** from `~/clawd/secrets/.env` (deprecated) to `~/.openclaw/secrets/.env` (Mac) / `~/.openclaw/secrets/.env` (VPS).
- **Expanded required PIT scope list** to match the full set Skill 36 uses, plus the two social-media-specific scopes this skill needs.
- **Added MCP-first routing detection in Step 4** — when Skill 36 is installed, this skill prefers MCP tools. Direct API only as fallback.
- **Made the install order explicitly numbered** with Step 0 (contract check) at the top. Steps are no longer reorderable.
- **Added 8.5/10 QC gate** — the install isn't complete until QC scores 8.5+. Loop and fix below threshold.
- **Resolved the long-pending `PPSA` placeholder** — removed (was unused for 9 months).
