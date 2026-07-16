---
# CANONICAL OpenClaw skill name — this is the field OpenClaw uses to register
# the skill, derive its slash command, and key its allowlist (docs.openclaw.ai
# /tools/skills: "The skill's name, slash command, and allowlist key all come
# from the `name` frontmatter field"). It MUST stay identical across Mac and VPS
# platforms in the unified repo (trevorotts1/openclaw-onboarding, platform/mac +
# platform/vps overlays). Canonical name: `social-media-planner`. Do NOT rename.
name: social-media-planner
description: Multi-agent content publishing engine that researches, creates, produces, schedules, and publishes content across every social channel the client has enabled in GHL — primary platforms include Facebook (posts + carousels + Stories), Instagram (posts + Reels + carousels + Stories), LinkedIn (posts + PDF carousels), X/Twitter, TikTok, Pinterest, and Google Business Profile, plus optional add-ons (WordPress, Medium, Substack, YouTube, email newsletter, podcast). Handles text, images, videos, carousels, comments, blog posts, podcasts, and HTML email newsletters using a 15+6 agent model.
# `pipeline_id` is the internal identifier for the content publishing pipeline
# run via OpenClaw subagents. It is NOT the skill name and OpenClaw never
# registers from it.
pipeline_id: content-publishing-engine
version: v2.9.13
author: Stefanie
created_date: 2026-04-14
---

# Content Publishing Engine Skill

## Purpose
The Content Publishing Engine orchestrates multi-agent workflows to research, create, produce, publish, and monitor content across every social channel the client has enabled in their GHL Social Planner. It handles text posts, images, videos/Reels, carousels, comments, blog posts, podcasts, and HTML email newsletters.

**Primary GHL Social Planner channels (published through GoHighLevel):**
Facebook (feed posts + carousels + Stories/Reels), Instagram (feed posts + Reels + carousels + Stories), LinkedIn (feed posts + PDF carousels), X/Twitter, TikTok, Pinterest, Google Business Profile.

The agent publishes to **every channel the client has connected inside GHL**. The exact enabled set is determined at runtime by a live GHL connected-accounts query — not by a fixed list.

**Optional add-on channels (direct integrations, not required):**
WordPress (blog), Medium (articles), Substack (newsletter), YouTube (videos), email newsletter (GHL Campaigns). These are supplementary and never block the skill if absent.

**Content types produced every week:**
- Daily social posts (7 days × all enabled platforms)
- Thursday carousels (multi-image, platform-specific formats: LinkedIn PDF, Facebook/Instagram image-stack)
- Short-form videos / Reels (Facebook, Instagram, TikTok, YouTube Shorts when enabled)
- Emotionally-driven comments with the client's weekly action link (posted 1-2 min after each post)
- Blog post (Day 7)
- HTML email newsletter (Tuesday)
- Podcast episode (if Fish Audio / Skill 30 is configured — gracefully skipped otherwise)

## Key Principles
- **15+6 Agent Model**: 15 primary agents for core execution + 6 QC (Quality Control) agents for validation.
- **Variable-based Configuration**: All platform credentials, URLs, and settings pulled from `[from identity.md: brand name]`, `[from secrets/.env: GOHIGHLEVEL_LOCATION_ID]`, etc. NO hardcoded values.
- **Phase-based Execution**: Research → Create → Produce → Schedule → Publish.
- **Enabled-channels-first Publishing**: The agent ALWAYS queries the client's live GHL connected accounts before reporting scope or producing content. It publishes to EVERY connected channel — never a fixed generic list.
- **Full Platform + Content-Type Matrix**: Primary channels (Facebook, Instagram, LinkedIn, X/Twitter, TikTok, Pinterest, Google Business Profile) + carousels, Reels, Stories, comments, blog, email newsletter, podcast. Optional add-ons (WordPress, Medium, Substack, YouTube) enabled per client.
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
| Publisher | Posts to every channel connected in GHL (live-queried — not a fixed list). |
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
1. Publisher: Query live GHL connected accounts first (see INSTRUCTIONS.md `check-social-connections`). Format and post per enabled channel:

   **Primary GHL Social Planner channels (publish through GHL API):**
   | Platform | GHL API path |
   |----------|-------------|
   | Facebook | GHL Social Planner API — feed posts, carousels, Stories/Reels captions |
   | Instagram | GHL Social Planner API — feed posts, Reels, carousels, Stories captions |
   | LinkedIn | GHL Social Planner API — feed posts + PDF carousel upload |
   | X / Twitter | GHL Social Planner API |
   | TikTok | GHL Social Planner API |
   | Pinterest | GHL Social Planner API |
   | Google Business Profile | GHL Social Planner API |

   **Optional add-on channels (direct integrations — only if configured):**
   | Platform | Credential |
   |----------|------------|
   | WordPress | `[from secrets/.env: WORDPRESS_URL]/wp-json/wp/v2/posts` |
   | Medium | `[from secrets/.env: MEDIUM_TOKEN]` |
   | Substack | `[from secrets/.env: SUBSTACK_API]` |
   | YouTube | `[from secrets/.env: YOUTUBE_KEY]` |
   | GHL Blog | `https://services.leadconnectorhq.com/blogs?locationId=[from secrets/.env: GOHIGHLEVEL_LOCATION_ID]` |

2. Upload media first (GHL Media Library CDN), embed links.
3. Post comments as a separate call 1-2 minutes after each parent post.
QC: Compliance.

### Phase 4: Engagement Monitoring
1. Engagement Monitor: Poll APIs for likes/views (e.g., every [from config: monitor_interval]h).
2. Report anomalies to `[from identity.md: owner telegram]`.
3. **Comment reader (comments → conversations):** poll prospect comment REPLIES on published posts and surface each as a synthetic inbound handoff into Skill 38's pipeline (see `scripts/comment-reader.py` and `references/playbook.md` §12b). Comments are not a GHL Conversations event, so without this a reader who follows the campaign's own "the link is in the comments" instruction and then comments would get no reply. Per-channel: use the §17 posting ladder's available read surface (official MCP or REST — `caf` has NO comment command); if a channel exposes no comment-read API, ledger it per-channel and skip — never fabricate a comment feed.
QC: Performance.

> **Cross-reference — Skill 38 owns the conversations these CTAs generate.** Skill 35's CTAs (the primary DM call-to-action, §12, and the comment-reader handoff, §12b) are INBOUND SOURCES; `38-conversational-ai-system` (Skill 38) is the OWNER of every inbound conversation they generate — DM → GHL Conversations → Skill 38's inbound playbook; comment reply → synthetic handoff → Skill 38's `<MASTER_FILES_DIR>/conversational-logs/`. Skill 35 never answers a conversation itself; it routes the highest-intent interaction to the skill that does. See the reciprocal cross-reference in `38-conversational-ai-system/SKILL.md`.

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

The subagent will read `identity.md`, pull credentials from `[from secrets/.env: GOHIGHLEVEL_LOCATION_ID]`, run the 15+6 agent pipeline (Research → Create → Produce → Schedule → Publish), upload finished media to the client's GHL Media Library, and return public CDN links. Social posting follows the Tier 0→3 ladder (see `references/playbook.md` Section 17): when Skill 44 is installed it posts via the `caf` CLI (Tier 0) first, then GHL MCP (Tier 1/2), then raw REST as a last resort.

### Per-role model tiering (client providers only — NEVER Anthropic/Claude)

The orchestrator above drives tool-calls and sub-agent fan-out. Tier each sub-agent's model to its job — **Ollama Cloud is the preference, the OpenRouter equivalent is the backup, and reasoning effort is HIGH**:

| Role group | Job type | Model (Ollama Cloud preferred → OpenRouter backup) |
|---|---|---|
| Researcher, Strategist | high reasoning / strategy | DeepSeek v4 pro **or** GLM 5.2 |
| Writer, Editor, Image Prompt Engineer, Email Designer (article/script/HTML/caption copy) | content & HTML writing | GLM 5.2 |
| Publisher (GHL tool-calls / scheduling) + all 6 QC agents | browser control / tool-calls / QC | MiniMax 3 |
| Video Producer (FFmpeg), Audio Generator, media upload | mechanical (no model judgement) | client's configured/default model |

Resolve concrete model IDs via `shared-utils/select_model.py` (Ollama-Cloud-first). NEVER recommend, hardcode, or default any client agent to an Anthropic/Claude model (Opus/Sonnet/Haiku/`claude-*`) — every client runs their own providers (Ollama Cloud / OpenRouter).

## Owner Q&A Playbook — "What does the planner do?" / "How do I use it?"

When an owner asks what the social media planner does, how it works, or what it handles, the agent MUST follow this playbook. Answering from memory or from a fixed generic list is a BANNED failure — it is exactly how an agent can omit platforms that are actually connected.

### Mandatory steps before answering:

1. **Run the live GHL connected-accounts check** (INSTRUCTIONS.md `check-social-connections` — Tier 0 `caf social accounts` → Tier 1 MCP → Tier 2 direct API). This is NOT optional for scope questions.
2. **Build the enabled-platforms list** from the live query result only.
3. **Answer with the full picture**: what the skill produces, what platforms it covers (using the live list), and how to trigger it.

### Required elements in the answer:

The answer MUST include all of the following — missing any element is a failure:

- **Full platform list** (from live query): state each enabled platform by name and which content types it receives (posts, Reels, carousels, Stories, comments, etc.)
- **Content types statement**: "I produce daily posts, Thursday carousels, short-form videos/Reels, comments with your action link, a weekly blog post, an HTML email newsletter, and (if Fish Audio is configured) a podcast episode."
- **Scope statement**: "I update every channel you have connected in GHL — currently: [live list from query]."
- **How to trigger it**: tell the owner the two ways to start a run — (a) say "update my social media" or "run my planner" and (b) the automated Saturday-morning theme prompt.
- **Optional add-ons clarification**: mention that WordPress, Medium, Substack, and YouTube are optional extras that extend the skill if the client has those integrations configured — they are never required.

### Example complete answer (fill in [LIVE CHANNELS] from the actual query result):

> "Your social media planner handles everything automatically every week. Here's exactly what I do and what I update:
>
> **Channels I'm publishing to right now** (based on your connected GHL accounts): [LIVE CHANNELS — e.g., Facebook, Instagram, LinkedIn, TikTok, Pinterest]
>
> **What I produce for each channel every week:**
> - Facebook: 7 daily feed posts (image + caption), Thursday carousel (multi-image), Stories/Reels captions, plus a unique comment with your action link on every post
> - Instagram: 7 daily feed posts, Reels, Thursday carousel, Stories captions, plus comments with your action link
> - LinkedIn: 7 daily posts, Thursday PDF carousel, plus comments with your action link
> - TikTok: 7 posts (when enabled), plus comments
> - Pinterest: 7 pins, plus comments
> - [Any other connected channel from the live query]
>
> **Also produced every week (regardless of social channels):**
> - Blog post (Day 7, published to GHL blog)
> - HTML email newsletter (sent Tuesday at 9 AM via GHL Campaigns)
> - Podcast episode (if Fish Audio is configured — automatically skipped if not)
>
> **How to run it:** Just say 'update my social media' or 'run my content plan' and I'll start the weekly cycle. Every Saturday morning I'll also ask you for the theme for next week. You can answer any time before Sunday and I'll handle the rest — research, writing, images, videos, scheduling, comments, everything.
>
> **Optional extras** (if you ever want to add them): WordPress blog, Medium, Substack, and YouTube have direct integrations available. Let me know and I can set those up."

This example answer must be adapted to reflect the ACTUAL live connected channels — never copy-paste the example platforms list without running the live check first.

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
