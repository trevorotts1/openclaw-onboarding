---
name: social-media-planner
description: "Automated 7-part weekly social media content production system. Use this skill whenever a client needs weekly social media content created, scheduled, and posted across Facebook, Instagram, LinkedIn, YouTube, TikTok, and Pinterest. Triggers on any mention of social media posting, content calendars, weekly content series, social media automation, social media scheduling, content production, or social media management. Also triggers when a client asks about their weekly theme, content series, social planner sheet, carousel posts, blog posts tied to social media, podcast episodes tied to social media, or anything related to producing and scheduling social media content at scale. This skill handles the entire pipeline from theme request through content creation, image generation, video production, QC, scheduling via GoHighLevel Social Planner API, and logging to Google Sheets."
---

## MANDATORY: Teach Yourself Protocol (TYP)

**Before using this skill, complete the Teach Yourself Protocol (Skill 01) on this folder.**

Required read order:
1. SKILL.md (this file)
2. INSTALL.md (prerequisites and setup)
3. CORE_UPDATES.md (what to add to core files)
4. QC.md (quality control checklist)
5. references/playbook.md (full 1,656-line production playbook)

Do NOT run the skill or produce any content before completing all 5 reads.

---

## ⚠️ ACTIVATION REQUIRED

**Reading files is NOT activation. You must EXECUTE the activation steps.**

After reading all 5 files, follow the **ACTIVATION** section in INSTALL.md:
1. CREATE Google Sheet via webhook
2. ASK client (videos, action link)
3. ASK about podcast (skip-but-keep-asking)
4. SEARCH .env for GHL credentials
5. ADD heartbeat to HEARTBEAT.md
6. APPLY CORE_UPDATES.md
7. RUN QC.md checks
8. CONFIRM to client

**Teach Yourself means READ. Activate means EXECUTE.**

---

# Social Media Planner (Skill 35)

A complete automated system for producing, scheduling, and managing weekly social media content across 6 platforms using a 7-part cliffhanger series framework.

## What This Skill Does

Every week, this skill:
1. Requests the weekly theme from the client (via heartbeat.md)
2. Selects a content persona using 5-layer alignment (client can override with personal brand tone)
3. Researches the theme and creates 7 days of core content
4. Rewrites content for 6 platforms (Facebook, Instagram, LinkedIn, YouTube, TikTok, Pinterest)
5. Generates images at platform-correct ratios (4:5, 2:3, 9:16, 16:9, 1:1)
6. Produces videos (0, 2, or 7 per week based on client preference)
7. Creates a blog post, podcast episode, email newsletter, and carousel posts
8. Writes unique emotionally-driven comments with the client's action link for every post
9. Runs QC on all content (40+ checklist items)
10. Schedules everything via GoHighLevel (Convert and Flow) Social Planner API
11. Logs all content to the client's Google Sheet
12. Logs weekly summary to memory (memory-core integration)

## Dependencies

| Skill | Required? | What For |
|-------|-----------|----------|
| Skill 01 (Teach Yourself Protocol) | REQUIRED | Must read this skill's files before first use |
| Skill 22 (Book-to-Persona) | RECOMMENDED | Persona-governed content style via 5-layer alignment |
| Skill 30 (Fish Audio API Reference) | OPTIONAL (for podcast) | Fish Audio S2 API key + Voice ID for podcast TTS |
| Skill 31 (Upgraded Memory System) | RECOMMENDED | Memory-core, Dreaming, and Memory Wiki integration |

## Required Stack

- **AI Brain:** OpenClaw
- **Image Generation:** kie.ai (Nano Banana 2 primary, Nano Banana Pro backup)
- **Video Generation:** kie.ai (Veo 3.1 Lite primary, Grok Imagine backup)
- **Audio/Podcast:** Fish Audio S2 with inline emotion tags (requires Fish Audio API key + Voice ID)
- **Podcast Hosting:** Podbean (MP3, 192 kbps, cover art 1400x1400 minimum)
- **Social Posting:** GoHighLevel (Convert and Flow) Social Planner API (Private Integration Token)
- **Content Logging:** Google Sheets (template provided, client duplicates it)
- **Email:** GoHighLevel (Convert and Flow)
- **Notifications:** Telegram (primary), Email (fallback), Text (last resort)

## Required Credentials

| Credential | Where to Get It | Store In |
|-----------|----------------|----------|
| GHL Private Integration Token | GHL > Settings > Integrations > Private Integrations | secrets/.env as GHL_PRIVATE_TOKEN |
| GHL Location ID | GHL > Settings > Business Profile | secrets/.env as GHL_LOCATION_ID |
| kie.ai API Key | kie.ai dashboard | secrets/.env as KIE_API_KEY |
| Fish Audio API Key | fish.audio dashboard | secrets/.env as FISH_AUDIO_API_KEY |
| Fish Audio Voice ID | fish.audio > Voices | secrets/.env as FISH_AUDIO_VOICE_ID |
| PPSA Information | [PENDING: Trevor to confirm specific fields] | secrets/.env |

## Persona Integration

This skill uses the 5-layer persona alignment to select a content governing persona each week. Marketing-tagged personas (Seth Godin, Gary Vee, Donald Miller, Brendan Kane, Alex Hormozi) are the primary candidates.

After selection, the AI presents the recommendation to the client:
"For this week's content about [theme], I recommend using [Persona Name]'s approach. Would you like me to use this style, or would you prefer I write in your personal brand tone instead?"

The client can: accept the recommendation, request their personal tone, or name a different persona.

## How Posting Works

**Regular posts:** Image + content are bundled together in ONE GHL API call via the `mediaUrls` field. They are never sent separately.

**Carousel posts:** Multiple images are included in the `mediaUrls` array in ONE GHL API call.

**Video posts:** Video URL is included in `mediaUrls` in ONE GHL API call with the caption.

**Comments:** Posted as a SEPARATE API call 1-2 minutes AFTER the parent post, using the parent post's ID. The comment contains the action link.

## First Run

On the very first activation for a new client, read `references/playbook.md` Section 0: First Run Protocol. This walks through:

1. Reading all OpenClaw core .md files
2. Extracting brand name, founder, target audience, colors, tone, voice, products/services
3. Asking only for information not found in core files
4. Creating the client's Google Sheet automatically via n8n webhook (client does nothing)
5. Getting the weekly action link
6. Asking video preference (0, 2, or 7 per week)
7. Confirming notification channels (Telegram > Email > Text)

**Google Sheet Creation (Automatic):**
- **Webhook:** `POST https://main.blackceoautomations.com/webhook/social-planner-sheet-create`
- **Fields:** `brandName` (from identity.md: brand name), `clientEmail` (from identity.md: owner email)
- **Response:** `sheetUrl`, `sheetId`, `sheetName`
- Store `sheetUrl` in MEMORY.md
- **Fallback:** Template link for manual copy if webhook fails

## Weekly Workflow

After first run is complete, the weekly cycle is:

### Saturday: Theme Request (Heartbeat)
- 8:00 AM: Ask client for the weekly theme
- 12:00 PM: If no response, ask again
- 6:00 PM: If no response, ask again
- Sunday 7:00 AM: Final ask if still no response

### Once Theme is Received: Production
Read `references/playbook.md` Section 3 for the full 55-step workflow. Summary:

**Phase 1: Research and Core Content (Main Agent, Sequential)**
- Select content persona via 5-layer alignment (with client override option)
- Research the theme, find 3+ credible sources
- Write 7 days of core content following the Television Show Framework
- Pitch intensity: 4/10 on Day 1, scaling to 5, 5, 6, 7, 9, 10/10 on Day 7

**Phase 2: Content Production (Up to 8 Sub-Agents, Parallel)**
1. Facebook Writer
2. Instagram Writer
3. LinkedIn Writer
4. YouTube/Pinterest/TikTok Writer
5. Image Generator (all ratios, all platforms, text overlays with brand colors)
6. Blog and Email Writer
7. Podcast Script Writer (Fish Audio S2 emotion tags)
8. Video Producer (kie.ai Veo 3.1 Lite + FFmpeg merge)

**Phase 3: QC (Parallel)**
- 40+ checklist items across 8 categories
- Text, Comments, Images, Scheduling, Blog, Podcast, Audio, Video
- Persona governance check (did content follow the selected style?)
- 3 retries before notification to client
- See QC.md for the standalone checklist

**Phase 4: Schedule and Log (Main Agent, Sequential)**
- Schedule all posts via GHL Social Planner API, 7 days ahead, starting Sunday at 9:00 AM
- Post comments with action link 1-2 minutes after each post
- Log everything to the client's Google Sheet
- Log weekly summary to memory (memory-core integration)

## Weekly Schedule

| Day | Content |
|-----|---------|
| Sunday (Day 1) | Series opener + Video 1 (if video enabled) |
| Monday (Day 2) | Day 2 content |
| Tuesday (Day 3) | Day 3 content + Email newsletter at 9:00 AM |
| Wednesday (Day 4) | Day 4 content |
| Thursday (Day 5) | Day 5 content + Carousel posts |
| Friday (Day 6) | Day 6 content |
| Saturday (Day 7) | Grand finale + Video 2 + Blog + Podcast |

## Podcast Deferred Workflow

If no Fish Audio API key or Podbean credentials available:

- Skip podcast production but proceed with ALL other content (do NOT block the skill)
- Log "PODCAST_DEFERRED" entry in the client's MEMORY.md with current timestamp, client name, and setup status
- Include weekly reminder in Saturday heartbeat: "Still no podcast setup? Fish Audio API key + Podbean account ready? I can help set it up!"
- Stop reminding ONLY if client explicitly declines permanently (e.g., "no podcasts ever" or equivalent - log as "PODCAST_DECLINED_PERMANENTLY")

## Key Principles

1. **Every post includes "check the comments" directing to the action link**
2. **Comments are unique every day, emotionally visceral, tied to that day's topic**
3. **The action link is confirmed weekly (it may change)**
4. **Images use the client's brand colors from their core .md files**
5. **Content tone and voice come from the selected persona OR the client's soul.md (if personal tone override)**
6. **One set of 4:5 carousel images is reused across Facebook, Instagram, and LinkedIn (as PDF)**
7. **The Google Sheet uses a horizontal 7-day storyboard layout (days go across, weeks go down)**
8. **All posting AND commenting is handled through GHL Social Planner API using Private Integration Token**
9. **Error handling: retry 3x, then notify via Telegram > Email > Text**
10. **Insufficient funds on kie.ai: no retry, immediate notification**
11. **Image and content are ALWAYS bundled together in one API call (mediaUrls field)**
12. **Comments are ALWAYS separate calls, 1-2 minutes after the parent post**

## Reference

The full playbook with all specifications, examples, checklists, and instructions is at:

```
references/playbook.md
```

Read this file before producing any content. It contains:
- Platform-specific character limits and image ratios (Section 7)
- Content zone system with 6 zones (Section 5)
- Comment strategy with industry examples (Section 12)
- Email newsletter pitch cadence (Section 13)
- Blog post pitch structure (Section 14)
- Podcast production with Fish Audio S2 emotion tags (Section 15)
- Video production pipeline with kie.ai pricing (Section 16)
- GHL Social Planner API endpoints with full request body examples (Section 17)
- Image text overlay requirements (Section 18)
- Full QC checklist (Section 19)
- Error handling and notification format (Section 20)
- LinkedIn PDF carousel generation commands (Section 21)
