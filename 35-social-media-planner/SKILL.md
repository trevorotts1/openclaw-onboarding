---
# CANONICAL OpenClaw skill name — this is the field OpenClaw uses to register
# the skill, derive its slash command, and key its allowlist (docs.openclaw.ai
# /tools/skills: "The skill's name, slash command, and allowlist key all come
# from the `name` frontmatter field"). It MUST stay identical across Mac and VPS
# platforms in the unified repo (trevorotts1/openclaw-onboarding, platform/mac +
# platform/vps overlays). Canonical name: `social-media-planner`. Do NOT rename.
name: social-media-planner
description: Multi-agent content publishing engine that researches, creates, produces, schedules, and publishes content across 8 platforms (WordPress, Medium, Substack, LinkedIn, GHL blog, YouTube, X/Twitter, Facebook) — handles text, images, videos, podcasts, and HTML email newsletters using a 15+6 agent model.
# `pipeline_id` is the internal identifier for the content publishing pipeline
# run via OpenClaw subagents. It is NOT the skill name and OpenClaw never
# registers from it.
pipeline_id: content-publishing-engine
version: v1.4.0
author: Stefanie
created_date: 2026-04-14
---

# Content Publishing Engine Skill

## Purpose
The Content Publishing Engine orchestrates multi-agent workflows to research, create, produce, publish, and monitor content across 8 platforms: WordPress, Medium, Substack, LinkedIn articles, GHL blog, YouTube, X/Twitter, and Facebook. It handles text, images, videos (with FFmpeg processing), podcasts, and HTML email newsletters.

## Key Principles
- **15+6 Agent Model**: 15 primary agents for core execution + 6 QC (Quality Control) agents for validation.
- **Variable-based Configuration**: All platform credentials, URLs, and settings pulled from `[from identity.md: brand name]`, `[from secrets/.env: GOHIGHLEVEL_LOCATION_ID]`, etc. NO hardcoded values.
- **Phase-based Execution**: Research → Create → Produce → Schedule → Publish.
- **8-Platform Publishing**: Seamless cross-posting with platform-specific formatting.
- **Video Pipeline**: FFmpeg-based crossfades, stitching, and optimization (e.g., `[from config: video specs]`).
- **HTML Email Newsletters**: Table-based layouts for compatibility.

## Agent Roster

| Agent | Role |
|-------|------|
| Researcher | Gathers data, trends, keywords from web/memory. |
| Strategist | Defines angles, hooks, SEO targets. |
| Writer | Drafts core content (articles, scripts). |
| Editor | Refines tone, structure, readability. |
| Image Prompt Engineer | Crafts prompts for visuals. |
| Image Generator | Produces images via `[from config: image model]`. |
| Video Script Writer | Writes video/podcast scripts. |
| Video Producer | Assembles clips with FFmpeg crossfades. |
| Audio Generator | Creates voiceovers/narration. |
| Thumbnail Designer | Generates platform-optimized thumbnails. |
| Publisher | Posts to 8 platforms. |
| Podcast Publisher | Uploads audio to hosting. |
| Email Designer | Builds HTML newsletters. |
| Email Publisher | Sends via `[from secrets/.env: EMAIL_SERVICE]`. |
| Engagement Monitor | Tracks metrics post-publish. |

**QC Agents (6)**:
| QC Agent | Role |
|----------|------|
| Grammar QC | Checks language, spelling. |
| Fact-Check QC | Verifies claims against sources. |
| Visual QC | Ensures image/video quality. |
| Compliance QC | Screens for legal/brand guidelines. |
| Performance QC | Optimizes load times, SEO. |
| Final QC | Holistic approval gate. |

## Phase Playbooks

### Phase 1: Content Research & Strategy
1. Researcher: `memory_search` + `web_search` on topic → raw data dump.
2. Strategist: Analyze for hooks → output strategy doc with variables like `[from identity.md: brand voice]`.

### Phase 2: Content Creation
1. Writer + Editor: Draft → refine article.
2. Image Prompt Engineer + Image Generator: Create visuals.
3. Video Script Writer: Script video/podcast.
4. Video Producer: 
   - Generate clips via `video_generate`.
   - FFmpeg crossfade: `ffmpeg -i clip1.mp4 -i clip2.mp4 -filter_complex "[0:v][0:a][1:v][1:a]xfade=transition=fade:offset=[from config: clip_duration]s[v][a]" -map "[v]" -map "[a]" output.mp4`.
   - Optimize: `ffmpeg -i input.mp4 -vf scale=[from config: video_width]:[from config: video_height] -c:a aac output.mp4`.
5. Audio Generator: TTS voiceover.
6. Thumbnail Designer: Images for platforms.
QC: Grammar, Fact-Check, Visual.

### Phase 3: Multi-Platform Publishing
1. Publisher: Format per platform:
   | Platform | Endpoint/API |
   |----------|-------------|
   | WordPress | `[from secrets/.env: WORDPRESS_URL]/wp-json/wp/v2/posts` |
   | Medium | `[from secrets/.env: MEDIUM_TOKEN]` |
   | Substack | `[from secrets/.env: SUBSTACK_API]` |
   | LinkedIn | `[from secrets/.env: LINKEDIN_TOKEN]` |
   | GHL Blog | `https://services.leadconnectorhq.com/blogs?locationId=[from secrets/.env: GOHIGHLEVEL_LOCATION_ID]` |
   | YouTube | `[from secrets/.env: YOUTUBE_KEY]` |
   | X/Twitter | `[from secrets/.env: TWITTER_TOKEN]` |
   | Facebook | `[from secrets/.env: FACEBOOK_TOKEN]` |
2. Upload media first, embed links.
QC: Compliance.

### Phase 4: Engagement Monitoring
1. Engagement Monitor: Poll APIs for likes/views (e.g., every [from config: monitor_interval]h).
2. Report anomalies to `[from identity.md: owner telegram]`.
QC: Performance.

### Phase 5: Email Newsletter
1. Email Designer: HTML table:
   ```html
   <table width="100%">
     <tr><td>[headline]</td></tr>
     <tr><td><img src="[thumbnail_url]" alt="[title]"></td></tr>
     <tr><td>[excerpt] <a href="[main_url]">Read More</a></td></tr>
   </table>
   ```
2. Email Publisher: Send via service.
QC: Final.

## Usage

Spawn the Content Publishing Engine via OpenClaw subagent runtime (model must be from the Ollama-Cloud-first chain — see `shared-utils/select_model.py --purpose-tier mid`):

```
sessions_spawn task="Run Content Publishing Engine on [topic]" runtime="subagent" model="ollama/minimax-m2.7:cloud"
```

Fallback if Ollama Cloud Minimax isn't available: `model="openrouter/xiaomi/mimo-v2-pro"`. Never hardcode the OpenRouter option as the primary.

The subagent will read `identity.md`, pull credentials from `[from secrets/.env: GOHIGHLEVEL_LOCATION_ID]`, run the 15+6 agent pipeline (Research → Create → Produce → Schedule → Publish), upload finished media to the client's GHL Media Library, and return public CDN links — it does NOT require any external CLI tools.

## Config Fields

The following fields are stored in the skill config and MUST be populated during setup. The agent reads them before every run.

| Field | Description | Where set |
|-------|-------------|-----------|
| `content_sheet_id` | Google Sheet ID for the client's content calendar (e.g. `1RKgS5l-i6NBtf_vON49nBPdHe-F5W67RF9ym-S67L2c`) | MEMORY.md + `openclaw config set` during INSTALL.md Step 7 |
| `content_sheet_url` | Full Google Sheet URL the agent uses to answer "what's my social media planner link?" | MEMORY.md during INSTALL.md Step 7 |

**The agent can always answer "what is my social media planner link?"** by reading `content_sheet_url` from MEMORY.md. It never responds "gws is not authenticated" or "I don't have the link."

## Media Delivery Contract

All finished media (assembled Reels, podcast MP3s, image sets) MUST be delivered via a public link — never as a raw Telegram file attachment (Telegram's Bot API cap is 50 MB send / 20 MB receive for bots; large files silently fail). The canonical delivery path:

1. **Produce** the file locally (FFmpeg merge, Fish Audio generation, etc.).
2. **Upload to the client's own GHL Media Library** via:
   ```bash
   curl -X POST "https://services.leadconnectorhq.com/medias/upload-file" \
     -H "Authorization: Bearer [from secrets/.env: GOHIGHLEVEL_API_KEY]" \
     -H "Version: 2021-07-28" \
     -F "file=@/path/to/file.mp4" \
     -F "hosted=true" \
     -F "fileProcessingOpts={\"forceReprocess\": true}"
   ```
   The response body contains a `url` field with a permanent public CDN link of the form `https://assets.cdn.filesafe.space/[LOCATION_ID]/media/[filename]`. This is the authoritative GHL media URL — confirmed from Skill 28 (cinematic-forge) which documents the same endpoint and CDN format.
3. **Extract the `url` field** from the response JSON.
4. **Log a row** in the content sheet by calling the `social-planner-row-append` webhook:
   ```bash
   curl -s -X POST "https://main.blackceoautomations.com/webhook/social-planner-row-append" \
     -H "Content-Type: application/json" \
     -d "{
       \"sheetId\": \"[from memory.md: content_sheet_id]\",
       \"row\": {
         \"Week Of\": \"[current week string e.g. Week of Jun 9 - Jun 15, 2026]\",
         \"Theme of the Week\": \"[theme]\",
         \"Core Content\": \"[title]\",
         \"[platform column]\": \"[status e.g. published|scheduled|draft]\",
         \"Blog\": \"[blog status if applicable]\",
         \"Scheduled\": \"[YYYY-MM-DD publish date]\",
         \"Overall\": \"published\",
         \"Notes\": \"[CDN link from step 3]\"
       }
     }"
   ```
   The webhook appends directly to the **Weekly Overview** tab of the client's Google Sheet using the operator service account (no client credentials required). If the webhook call fails: log to `~/.openclaw/data/skill35/content-log.jsonl` and retry on next cycle. **Do NOT call `social-planner-sheet-create` here** — that webhook is for first-time sheet creation only.
5. **Reply to owner** with the CDN link only — never attach the raw file to Telegram.

**Size threshold:** Any file over 10 MB MUST go through GHL CDN delivery. Files under 10 MB MAY be attached directly only if the operator explicitly configures `direct_attach_under_10mb=true` in MEMORY.md; default is always link delivery.

**If GHL upload fails:** retry once after 30 seconds. If still failing, notify owner via Telegram that media is queued for retry, log the error, and do NOT send the raw file attachment.

## Variable Reference
- `[from identity.md: brand name]`, `[from identity.md: brand voice]`
- `[from secrets/.env: GOHIGHLEVEL_API_KEY]`, `[from secrets/.env: GOHIGHLEVEL_LOCATION_ID]`, `[from secrets/.env: WORDPRESS_URL]`, `[from secrets/.env: MEDIUM_TOKEN]`, etc.
- `[from config: video specs]`, `[from config: image model]`, `[from config: monitor_interval]`
- `[from memory.md: content_sheet_id]`, `[from memory.md: content_sheet_url]`
- Pull via `read` tools before agent prompts.
