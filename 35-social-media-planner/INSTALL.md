# Social Media Planner (Skill 35) - Installation Guide

## Prerequisites

Before installing this skill, verify the following:

### Required Skills (install these first)

| Skill | Check | If Missing |
|-------|-------|-----------|
| Skill 01 (Teach Yourself Protocol) | `ls ~/.openclaw/skills/01-teach-yourself-protocol/` | Install before any other skill |
| Skill 22 (Book-to-Persona) | `ls ~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/` | Needed for persona-governed content. Without it, content uses soul.md tone only |
| Skill 30 (Fish Audio API Reference) | `ls ~/.openclaw/skills/30-fish-audio-api-reference/` | OPTIONAL for podcast production. Without it, podcast is skipped but all other content proceeds |
| Skill 31 (Upgraded Memory System) | `ls ~/.openclaw/skills/31-upgraded-memory-system/` | Needed for memory-core integration. Without it, logs to MEMORY.md directly |

### Required API Keys and Credentials

| Credential | Where to Get It | What to Store | Env Variable |
|-----------|----------------|---------------|-------------|
| GHL Private Integration Token | GoHighLevel > Settings > Integrations > Private Integrations. Create a new private integration with `social-media-posting.write` scope. | The token string | GHL_PRIVATE_TOKEN |
| GHL Location ID | GoHighLevel > Settings > Business Profile. Copy the Location ID. | The location ID string | GHL_LOCATION_ID |
| kie.ai API Key | Sign up at kie.ai, go to API dashboard, generate key | The API key string | KIE_API_KEY |
| Fish Audio API Key (OPTIONAL) | Sign up at fish.audio, go to API keys | The API key string | FISH_AUDIO_API_KEY |
| Fish Audio Voice ID (OPTIONAL) | fish.audio > Voices > select or clone a voice > copy the Voice ID | The voice ID string | FISH_AUDIO_VOICE_ID |
| Podbean Channel ID (OPTIONAL) | Podbean dashboard > Podcast Settings. Each client has their own channel. | The channel ID string | PODBEAN_PODCAST_ID |
| PPSA Information | [PENDING: Trevor to confirm specific PPSA fields needed] | [PENDING] | [PENDING] |

All credentials go in `secrets/.env` on the client's OpenClaw instance.

### Required Software

| Software | Check | Install (Mac) | Install (Linux) |
|----------|-------|---------------|----------------|
| FFmpeg | `ffmpeg -version` | `brew install ffmpeg` | `sudo apt install ffmpeg` |
| ImageMagick | `convert -version` | `brew install imagemagick` | `sudo apt install imagemagick` |
| Python 3 | `python3 --version` | Pre-installed on Mac | `sudo apt install python3` |

### Required Accounts

| Account | Purpose | Sign Up |
|---------|---------|---------|
| GoHighLevel (Convert and Flow) | Social media posting, email, CRM | Client should already have this |
| kie.ai | Image generation (Nano Banana 2) and video generation (Veo 3.1 Lite) | kie.ai |
| Fish Audio (OPTIONAL) | Text-to-speech for podcast episodes | fish.audio |
| Podbean (OPTIONAL) | Podcast hosting (MP3, 192 kbps) | podbean.com |
| Google Sheets | Content logging and tracking | **Created automatically via n8n webhook - no client action needed** |

---

## Agent vs Client Responsibilities

### AGENT HANDLES (You Don't Need to Do These)

| Task | What Agent Does |
|------|-----------------|
| Google Sheet creation | Duplicates template, configures layout, shares with client |
| Brand info extraction | Reads identity.md, soul.md, memory.md to extract brand details |
| Persona selection | Uses 5-layer alignment to recommend persona, asks client to confirm |
| Content production | Writes all posts, generates images, produces videos |
| Scheduling via GHL | Posts all content via Social Planner API |
| QC checks | Runs 40+ item checklist before posting |
| Weekly logging | Updates Google Sheet with all content |

### CLIENT PROVIDES (Agent Will Ask For These)

| Item | Why Needed | Search Before Asking |
|------|-----------|---------------------|
| API keys (GHL, kie.ai, Fish Audio) | Authentication | Check all .env files first |
| Weekly action link | CTA in comments | Confirm weekly if changed |
| Video preference (0/2/7 per week) | Production planning | Ask once, store in MEMORY.md |
| Podcast channel ID | Optional for podcast | Skip if declined |

**Google Sheet:** Created automatically via n8n webhook. No client credentials needed.

**SEARCH BEFORE ASKING:** The agent checks ALL these locations before asking:
- ~/clawd/secrets/.env
- ~/.openclaw/.env
- ~/.openclaw/openclaw.json env.vars
- printenv output
- Match similar variable names (e.g., GHL_TOKEN = GHL_PRIVATE_TOKEN)

---

## Installation Steps

### Step 1: Run Teach Yourself Protocol

Read all files in this skill folder in this order:
1. SKILL.md (overview, quick reference, dependencies)
2. INSTALL.md (this file)
3. CORE_UPDATES.md (what to add to core files)
4. QC.md (quality control checklist)
5. references/playbook.md (the full production playbook, 1,656 lines)

Do NOT run the skill until all 5 files have been read in this session.

### Step 2: Verify API Keys

Check that secrets/.env contains all required credentials:

```
GHL_PRIVATE_TOKEN=pit_xxxxxxxxxxxxxxxx
GHL_LOCATION_ID=xxxxxxxxxxxxxxxx
KIE_API_KEY=xxxxxxxxxxxxxxxx
FISH_AUDIO_API_KEY=xxxxxxxxxxxxxxxx
FISH_AUDIO_VOICE_ID=xxxxxxxxxxxxxxxx
```

If any are missing, ask the client:
- "I need your GoHighLevel Private Integration Token to schedule social media posts. Go to GoHighLevel > Settings > Integrations > Private Integrations, create a new integration, and share the token with me."
- "I need your kie.ai API key for generating images and videos. You can get this from your kie.ai dashboard."
- "I need your Fish Audio API key and Voice ID for podcast production. You can get these from fish.audio."

### Step 3: Verify GHL Social Planner Access

Test the GHL API by listing connected social accounts:
```
curl -H "Authorization: Bearer {GHL_PRIVATE_TOKEN}" \
  "https://services.leadconnectorhq.com/social-media-posting/oauth/{GHL_LOCATION_ID}/facebook/accounts/{accountId}"
```
If this returns account data, GHL Social Planner is connected and the token works.

### Step 4: Verify FFmpeg and ImageMagick

```
ffmpeg -version 2>/dev/null && echo "FFmpeg: OK" || echo "FFmpeg: MISSING"
convert -version 2>/dev/null && echo "ImageMagick: OK" || echo "ImageMagick: MISSING"
```

If missing, ask the client to install them or install automatically if you have permission.

### Step 5: Run First Run Protocol

On the very first activation for a new client, follow references/playbook.md Section 0: First Run Protocol. This:
1. Reads all OpenClaw core .md files (identity.md, soul.md, memory.md, agents.md, heartbeat.md)
2. Extracts brand name, founder, target audience, colors, tone, voice, products/services
3. Asks ONLY for information not found in core files
4. Creates the client's Google Sheet via n8n webhook (automatic - client does nothing)
5. Gets the weekly action link
6. Asks video preference (0, 2, or 7 per week)
7. Confirms notification channels (Telegram > Email > Text)

### Step 6: Apply CORE_UPDATES.md

Add the entries from CORE_UPDATES.md to the client's:
- AGENTS.md
- TOOLS.md
- MEMORY.md

### Step 7: Configure Heartbeat

Add the weekly theme request to the client's HEARTBEAT.md. See references/playbook.md Section 24 for the exact heartbeat configuration.

---

## Completion Checklist

- [ ] All 5 files read (Teach Yourself Protocol complete)
- [ ] GHL_PRIVATE_TOKEN in secrets/.env and verified working
- [ ] GHL_LOCATION_ID in secrets/.env
- [ ] KIE_API_KEY in secrets/.env
- [ ] FISH_AUDIO_API_KEY in secrets/.env (OPTIONAL)
- [ ] FISH_AUDIO_VOICE_ID in secrets/.env (OPTIONAL)
- [ ] PODBEAN_PODCAST_ID in secrets/.env (OPTIONAL - client's Podbean channel ID)
- [ ] PPSA information collected [PENDING: Trevor to confirm fields]
- [ ] GHL Social Planner API test successful
- [ ] FFmpeg installed and working
- [ ] ImageMagick installed and working
- [ ] First Run Protocol complete (brand info, Google Sheet via webhook, action link, video preference, notifications)
- [ ] CORE_UPDATES.md applied to AGENTS.md, TOOLS.md, MEMORY.md
- [ ] HEARTBEAT.md updated with weekly theme request schedule
- [ ] Skill 30 (Fish Audio) installed (OPTIONAL for podcast production)
- [ ] Skill 22 (Book-to-Persona) installed (for persona-governed content)
- [ ] Skill 31 (Upgraded Memory) installed (for memory-core integration)
