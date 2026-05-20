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
for skill in 01-teach-yourself-protocol 02-back-yourself-up-protocol 22-book-to-persona-coaching-leadership-system 31-upgraded-memory-system 36-ghl-mcp-setup 30-fish-audio-api-reference; do
  if [ -d "$HOME/.openclaw/skills/$skill" ] || [ -d "~/.openclaw/skills/$skill" ]; then
    echo "  ✓ $skill installed"
  else
    echo "  ✗ $skill MISSING"
  fi
done
```

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

### Step 4: Detect Skill 36 (GHL MCPs) and configure routing

```bash
if [ -d "$HOME/.openclaw/skills/36-ghl-mcp-setup" ] || [ -d "~/.openclaw/skills/36-ghl-mcp-setup" ]; then
  ROUTING_MODE="mcp-first"
  echo "  ✓ Skill 36 detected — Skill 35 will route GHL operations through MCPs first"
else
  ROUTING_MODE="direct-api"
  echo "  ⚠ Skill 36 NOT installed — Skill 35 will use direct GHL Social Planner API"
  echo "    STRONGLY RECOMMENDED: install Skill 36 first for better reliability"
fi
```

If `ROUTING_MODE=mcp-first`, the production playbook uses MCP tools by default:
- **Social posting:** Tier 1 `social-media-posting_create-post` → Tier 2 `create_social_post` → direct API as last resort
- **Blog publish:** Tier 1 `blogs_create-blog-post` → Tier 2 `create_blog_post` → direct API
- **Media upload:** Tier 1 not available → Tier 2 `upload_media_file` → direct API
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
4. Create the client's Google Sheet via n8n webhook:

```bash
curl -X POST "https://main.blackceoautomations.com/webhook/social-planner-sheet-create" \
  -H "Content-Type: application/json" \
  -d "{\"brandName\":\"$BRAND_NAME\",\"clientEmail\":\"$CLIENT_EMAIL\"}"
```

Store `sheetUrl` and `sheetId` from response in MEMORY.md.

5. Ask: "What action link should I include in social media comments this week?" → store as `SOCIAL_MEDIA_ACTION_LINK` in MEMORY.md.
6. Ask: "How many videos per week — 0, 2, or 7?" → store as `VIDEO_PREFERENCE` in MEMORY.md.
7. Ask: "Where should I send weekly notifications — Telegram, email, or text?" → store as `NOTIFICATION_CHANNEL` in MEMORY.md.
8. Ask about podcast: "Do you want podcast episodes produced? Needs Fish Audio + Podbean. (yes/no/later)" → handle per response.

### Step 8: Apply CORE_UPDATES.md surgically

Add the LABELED sections from CORE_UPDATES.md ONLY to:
- `AGENTS.md` — social planner routing rules + MCP-first language
- `TOOLS.md` — GHL Social Planner tool reference
- `MEMORY.md` — weekly logging structure

Do NOT touch IDENTITY.md, HEARTBEAT.md, USER.md, or SOUL.md from this skill.

### Step 9: Add weekly theme request to HEARTBEAT.md

```markdown
### Saturday 8:00 AM — Social Media Theme Request
Ask client: "What's the theme for next week's social media content?"
- If no response by 12:00 PM: ask again
- If no response by 6:00 PM: ask again
- If no response by Sunday 7:00 AM: use "evergreen" theme
```

### Step 10: Run QC.md and require 8.5+ to pass

Execute the QC.md checklist. Score against the v2.0.0 rubric. If score is **below 8.5**, loop back and fix until passing (max 5 loops, then escalate to client/Trevor).

If a bundled `qc-skill35.sh` script is present in this skill folder, run it. It MUST exit 0.

### Step 11: Confirm completion to client

Send the client this exact summary:

> ✅ Social Media Planner activated.
>
> • Google Sheet created and shared with you: [link]
> • GHL Social Planner connected via [MCP / direct API]
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
- [ ] Prerequisites verified (skills 01, 02, 22, 31 installed; 30 and 36 detected/handled)
- [ ] Platform detected + canonical paths resolved
- [ ] `GOHIGHLEVEL_API_KEY` present at `$SECRETS_ENV` (NOT deprecated `GHL_PRIVATE_TOKEN`)
- [ ] `GOHIGHLEVEL_LOCATION_ID` present at `$SECRETS_ENV`
- [ ] All required PIT scopes confirmed (smoke test returned 200 + real data, no 403s)
- [ ] `KIE_API_KEY` present
- [ ] `FISH_AUDIO_API_KEY` + `FISH_AUDIO_VOICE_ID` present OR podcast deferred
- [ ] `PODBEAN_PODCAST_ID` present OR podcast deferred
- [ ] Skill 36 routing mode detected (mcp-first or direct-api), routing rules applied
- [ ] FFmpeg ≥4.0 working
- [ ] ImageMagick working
- [ ] First-Run Protocol complete (brand info, Google Sheet, action link, video preference, notifications)
- [ ] CORE_UPDATES.md applied surgically to AGENTS.md / TOOLS.md / MEMORY.md
- [ ] HEARTBEAT.md updated with Saturday theme-request schedule
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
