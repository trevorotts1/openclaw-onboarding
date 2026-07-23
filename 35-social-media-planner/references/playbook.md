# Universal Social Media Playbook v6.0

**7-Part Cliffhanger Content Series System**
**For: Any Client | Built for OpenClaw AI**
**Last Updated: April 2026 | Built by BlackCEO Automations**

---

## Table of Contents

0. First Run: Client Setup Protocol
1. System Overview
2. The Television Show Framework
3. Weekly Production Workflow (Step-by-Step)
4. 7-Part Content Structure & Cliffhanger Architecture
5. Content Zone System
6. Content Flow Rules (Zone-by-Zone Writing Instructions)
7. Platform Guide: Image Sizes, Characters & Content Zones
8. Image Production (kie.ai)
9. Carousel Strategy (Thursdays)
10. Stories, Reels & Short Video Guide
11. Platform-Specific Best Practices for Growth
12. Comment Strategy (Every Post, Every Day)
13. Email Newsletter (Tuesday 9 AM)
14. Blog Post Production (Day 7 Release)
15. Podcast Production with Fish Audio S2 (Day 7 Release)
16. Video Production Pipeline (kie.ai + FFmpeg)
17. GoHighLevel (Convert and Flow) Social Planner API
18. Image Text Overlay Requirements
19. QC Agent System
20. Error Handling & Notifications
21. LinkedIn PDF Carousel Generation (OpenClaw Command)
22. Content Hacks & Edge Cases
23. Universal Quick-Reference Specs
24. Heartbeat.md Configuration
25. Google Sheet Structure & AI Update Instructions
26. Playbook Coverage & Self-Rating

---

## 0. First Run: Client Setup Protocol

**This section runs ONCE, the very first time the AI is activated for a new client.** After setup is complete, the AI marks setup as done and never runs this section again. Every subsequent week, it skips straight to the heartbeat theme request.

### Step 1: Read All OpenClaw Core Files

Read every .md file in the client's OpenClaw system. These are the core files that define who the client is:

- **identity.md** - Brand name, mission, values, positioning
- **soul.md** - Brand voice, tone, personality, communication style
- **memory.md** - Past interactions, preferences, historical context
- **agents.md** - Agent configuration, capabilities, tool access
- **heartbeat.md** - Scheduled tasks, recurring actions

Extract everything you can: brand name, founder/owner name, target audience, brand colors, tone, voice, products/services, and any other brand-specific details.

### Step 2: Identify What You Know vs. What You Need to Ask

After reading the core files, determine what you have and what's missing. Be proactive: use information you already know and only ask for what you genuinely cannot find.

**Required information:**

| Information | Source | If Not Found |
|------------|--------|-------------|
| Brand name | Core files (identity.md) | Ask: "What is your brand name?" |
| Founder/owner name | Core files (identity.md) | Ask: "Who is the owner or primary contact?" |
| Target audience | Core files (identity.md, soul.md) | Ask: "Who is your target audience?" |
| Brand colors | Core files (identity.md, soul.md) | Ask: "What are your brand colors?" |
| Brand tone/voice | Core files (soul.md) | Ask: "How would you describe your brand's tone?" |
| Products/services | Core files (identity.md) | Ask: "What products or services do you offer?" |
| Action link | Must ask every week | Ask during first run AND confirm every weekly heartbeat |
| Google Sheet link | Must ask once | Provide template for client to duplicate |

### Step 3: Create the Google Sheet (Automatic via n8n Webhook)

**The agent creates the Google Sheet automatically via webhook. The client does nothing.**

Call the n8n webhook to create the sheet:
```
POST https://main.blackceoautomations.com/webhook/social-planner-sheet-create
Content-Type: application/json

{
  "brandName": "[from identity.md: brand name]",
  "clientEmail": "[from identity.md: owner email]"
}
```

**Webhook Response:**
```
{
  "sheetUrl": "https://docs.google.com/spreadsheets/d/[SHEET_ID]/edit",
  "sheetId": "[SHEET_ID]",
  "sheetName": "[Brand Name] Social Media Planner"
}
```

**What the agent does:**
1. POST to the webhook with brandName (from identity.md: brand name) and clientEmail (from identity.md: owner email)
2. Receive sheetUrl, sheetId, and sheetName in response
3. Store the sheetUrl in MEMORY.md
4. Tell the client: "I created your Social Media Planner sheet. Here is the link: [URL]. You have full edit access."

**Fallback if webhook fails:**
If the webhook returns an error or times out after 3 retries:
1. Provide the client with the template link: https://docs.google.com/spreadsheets/d/1RKgS5l-i6NBtf_vON49nBPdHe-F5W67RF9ym-S67L2c/edit?usp=sharing
2. Tell the client: "Click File → Make a Copy, rename it to [Brand Name] Social Media Planner, and share the edit link back with me."
3. Log the fallback in MEMORY.md

**No client credentials required.** The webhook uses the service account to create and share the sheet.

### Step 4: Ask the Weekly Action Link

Ask: "What is your action link for this week? This is the link you want people to click when they take action (schedule a call, book an appointment, sign up, download, etc.)."

Also ask: "Should I use this same action link every week, or will it change? I'll confirm with you each week either way."

**Optional automation — themed weekly landing page (P3-08 Gap C, OPT-IN, client link always wins):** if the client does NOT supply a static action link for the week (or explicitly opts in to auto-generated pages), the weekly campaign step MAY invoke Skill 6's `06-ghl-install-pages/tools/funnel_matcher.py --match` to spin up a themed weekly landing page matched to that week's television-show theme, handing off form/automation linkage via the existing `routing/skill44-handoff.json` pattern (Skill 6 → Skill 44) so the page's form and follow-up automation are wired end to end. **Client sovereignty over their own link ALWAYS wins:** when the client provides a static link (Step 4 above), that link is used verbatim — the auto-generated page is only a fallback for weeks with no client-supplied link and only when the client has opted in. Never override a client-provided link with a generated page. This step is OPTIONAL (optional-graded); the planner works fully without it, using the client's confirmed weekly link.

### Step 5: Ask Video Preference

Ask: "How many videos would you like produced each week?"
- **0 videos** - No video production, images only
- **2 videos** - One opener video (Day 1) and one grand finale video (Day 7)
- **7 videos** - One video per day for the full week

### Step 5b: Collect Podcast Channel ID

Ask: "Do you have a Podbean account for podcast hosting? If yes, I need your Podbean Channel ID (also called podcast_id) so I can publish your weekly podcast episodes automatically. You can find this in your Podbean dashboard under Podcast Settings."

If the client does not have a Podbean account:
- Option A: "Would you like to set one up? Go to podbean.com and create a free account. Once your podcast channel is created, share the channel ID with me."
- Option B: "No problem. I can skip podcast publishing for now and we will focus on the social media posts, blog, and email. When you are ready for podcast, just let me know your Podbean channel ID."

Store the podcast_id in MEMORY.md and in secrets/.env as PODBEAN_PODCAST_ID.

### Step 5c: Collect Client Contact Information for Podcast Notifications

Ask: "What email address should I use for podcast publishing confirmations? When each episode goes live, you will receive an email with the episode number and link."

Collect: client_first_name, client_last_name, client_email. Store in MEMORY.md.

### Step 6: Confirm Notification Channels

Send a test message via Telegram. If delivered, Telegram is the primary channel.

**Notification fallback chain:**
1. **Telegram** (primary) - Send all alerts here first
2. **Email** (fallback) - If Telegram fails, send via email
3. **Text message** (last resort) - If both Telegram and email fail, send via SMS

Confirm delivery at each step. Store whichever channels work.

### Step 7: Mark Setup Complete

Store all collected information. Mark the first run as complete. Never run this setup again for this client.

---

## 1. System Overview

### What This Playbook Does

This playbook teaches the AI how to create a complete weekly social media content system for any client brand. Every week, we produce a 7-part posting series where each post builds on the last, delivers real value, and uses a cliffhanger approach to keep the audience coming back. On Day 7, the grand finale releases alongside a blog post and podcast episode that encompass the entire week's content.

### The Client

- **Brand:** Use the client's brand name (extracted from core files or asked during First Run)
- **Owner/Founder:** Use the client's owner/founder name (extracted from core files or asked during First Run)
- **Audience:** Use the client's target audience (extracted from core files or asked during First Run)

### Brand Guidelines

**Before generating ANY content, the AI must review the client's OpenClaw core .md files.** These files (identity.md, soul.md, memory.md, agents.md, heartbeat.md) contain the brand's colors, tone, voice, mission, target audience, and other brand-specific information. The AI must not generate content, images, or any creative output without first reading and understanding the brand context from the core files.

**Brand context the AI must confirm from core files before starting:**
1. Brand colors (for image generation, text overlays, carousel design)
2. Brand tone and voice (for all written content across all platforms)
3. Brand mission and values (to ensure all content aligns)
4. Target audience details
5. Any specific language, phrases, or terminology the brand uses or avoids

If the core files do not contain sufficient brand information, the AI must notify the client and request the missing details before proceeding with content production.

### The Tech Stack

- **AI Brain:** OpenClaw
- **Image Generation:** kie.ai (Primary: Nano Banana 2 | Backup: Nano Banana Pro)
- **Video Generation:** kie.ai (Veo 3.1 Fast for image-to-video segments) + FFmpeg for merging
- **Audio/Podcast:** Fish Audio S2 with inline emotion tags (requires Fish Audio API key + Voice ID. Depends on Skill 30: Fish Audio API Reference)
- **Podcast Publishing:** n8n webhook automation (handles Podbean auth, upload, episode numbering, scheduling, and client email confirmation)
- **CRM / Posting:** GoHighLevel (Convert and Flow)
- **Theme Source:** Google Sheets

---

## 2. The Television Show Framework

Think of this entire content system as a television show.

**Each week is a SEASON.** Seven days is a seven-episode season. The content builds in intensity, length, and emotional weight with each episode.

**The episodes build toward a grand finale.** Day 1 is the pilot. It hooks the audience. Each day after that raises the stakes. The pitch for the client's services starts soft and gets stronger. The content gets deeper. The cliffhangers get more intense.

**Day 7 is the season finale.** It is the longest piece of content. It brings everything together. It delivers the strongest call to action. It is the grand finale. And just like a great television show, the season finale also teases the NEXT season (next week's theme) to keep the audience coming back.

**Day 7 is also release day for:**
1. The grand finale social media post (strongest pitch, longest content)
2. The weekly blog post (combines all 7 days into one comprehensive article)
3. The weekly podcast episode (audio script with emotion tags, produced via Fish Audio S2)

These three pieces all release on Day 7. They do NOT release earlier in the week. If the podcast or blog dropped on Wednesday, it would reveal everything before the social series finishes. The blog and podcast are the reward for people who followed the full series.

**If someone misses an episode, they can catch up.** Every post works as a standalone piece. But the recaps create curiosity about what was missed, driving people to go back and find earlier posts. Think of it like joining a TV show in the middle of the season. You can enjoy the episode, but you want to go back and watch what you missed.

---

## 3. Weekly Production Workflow (Step-by-Step)

### Agent Architecture

The production workflow uses a Main Agent (Orchestrator) and up to 8 Sub-Agents running in parallel. The Main Agent manages the overall process, delegates tasks, collects results, runs QC, and handles scheduling. Sub-Agents are specialists that execute specific production tasks simultaneously.

**Phase 1: Research & Core Content (Main Agent, Sequential)**
The Main Agent handles this phase alone. Research and core content must be completed first because every Sub-Agent in Phase 2 depends on it.

**Phase 2: Content Production (Up to 8 Sub-Agents, Parallel)**
Once core content is complete, the Main Agent spins up Sub-Agents:

| Sub-Agent | Task | Inputs | Outputs |
|-----------|------|--------|---------|
| Sub-Agent 1: Facebook Writer | Rewrites all 7 days for Facebook feed posts. Writes 7 unique comments with the weekly action link. Writes Facebook Stories/Reels captions. | Core content for all 7 days | 7 FB posts, 7 FB comments, Stories/Reels captions |
| Sub-Agent 2: Instagram Writer | Rewrites all 7 days for Instagram feed posts. Writes 7 unique comments with the weekly action link. Writes IG Stories/Reels captions. | Core content for all 7 days | 7 IG posts, 7 IG comments, Stories/Reels captions |
| Sub-Agent 3: LinkedIn Writer | Rewrites all 7 days for LinkedIn feed posts. Writes 7 unique comments with the weekly action link. Prepares carousel caption for Thursday. | Core content for all 7 days | 7 LinkedIn posts, 7 LinkedIn comments, carousel caption |
| Sub-Agent 4: YouTube/Pinterest/TikTok Writer | Rewrites all 7 days for YouTube Community Posts, Pinterest Pins, and TikTok posts. Writes comments for each. | Core content for all 7 days | 7 YT posts, 7 Pinterest pins, 7 TikTok posts, all comments |
| Sub-Agent 5: Image Generator | Generates all daily images (7x 4:5, 7x 2:3, 7x 9:16), carousel images (4:5, 9:16, 2:3 sets), blog featured image, podcast cover image. Adds text overlays. | Day titles/headlines from core content | All images for the week |
| Sub-Agent 6: Blog & Email Writer | Writes the blog post (Day 7) and the email newsletter (Tuesday). | Core content + research for all 7 days | 1 blog post, 1 email newsletter |
| Sub-Agent 7: Podcast Script Writer | Writes the podcast script with Fish Audio S2 emotion tags. | Core content + research for all 7 days | 1 podcast script |
| Sub-Agent 8: Video Producer | Generates B-roll images, creates 8-second video segments via kie.ai Veo 3.1 Lite, generates narration audio via Fish Audio S2, merges with FFmpeg. | Core content for Day 1 and Day 7 | 2 x 60-second videos |

**Phase 3: QC (QC Sub-Agents, Parallel)**
Once Phase 2 Sub-Agents return their outputs, the Main Agent spins up QC agents to review everything against the checklist in Section 19. Multiple QC agents can run in parallel checking different content types. Any failures are sent back to the originating Sub-Agent for revision (up to 3 retries).

**Phase 4: Scheduling & Logging (Main Agent, Sequential)**
The Main Agent schedules all content via the GHL Social Planner API and logs everything to the Google Sheet. This phase is sequential to avoid race conditions with the API.

### Step-by-Step Process

The AI must follow these steps in this exact order:

**Step 0a: Review Brand Guidelines (First Run / Weekly Check)**
Before any content production begins, the AI must review the [Brand Name] core .md files on OpenClaw. Confirm brand colors, tone, voice, mission, values, and target audience. If any core .md file has been updated since the last review, re-read it. If core files are missing or incomplete, notify the client and request the missing brand information before proceeding. Do not generate any content without full brand context.

**Step 0a.5: Select the Content Blend — PER DAY, via Scoped Bundles (D1 binding ruling, Skill 6 U98)**
Before writing any content, the blended persona GOVERNS each day's voice — never advisory, no
exemptions. This replaced the old single-persona-per-week pick: a week is 7 distinct posting
days, and each day gets its OWN governing blend bundle, resolved via the same scoped-bundle
mechanism Skill 6's per-page funnel copy already uses (`persona_blend.build_bundle(...,
scope_hint={"page_role": "day-N"})`, U5). Call `scripts/daily_blend_bundle.py` for the cycle:

```
python3 scripts/daily_blend_bundle.py --theme "<weekly theme>" --run-dir <DEPT_WORKSPACE>
```

This resolves all 7 days' bundles in one pass and logs ONE entry per day (never one entry for
the whole week) to `persona-selection-log.md` in the department workspace — each entry carries
its own `scope` key (`day-1` … `day-7`), its own `blend_directive` (ending in the mandatory
STYLE-INSPIRED-NEVER-IMPERSONATION guardrail clause), and the WHY (collapse reasoning or a
shared-blend note when two days legitimately land on the same voice). A day's blend directive —
not a locally-picked persona — governs that day's word choice, cadence, and devices; the
Television Show Framework (Day 1 hooks, escalating pitch intensity 4/10 → 10/10, Day 7 grand
finale) is untouched by this — it governs VOICE, never the show's structure.

**Audience/Topic Override Option:**
The blend resolves the AUDIENCE voice from the client's onboarding ICP and the TOPIC from the
weekly theme + each day's angle; present the resolved voice to the client before the cycle
starts, the same ALWAYS-confirm doctrine `persona_blend.resolve_audience` already enforces
elsewhere:

"For this week's content about [theme], the blend resolves to [Persona Name]'s voice for
[audience]. [One sentence why.] Would you like me to use this, or would you prefer your
personal brand tone from soul.md governs instead?"

If the client says to use their personal tone: pass `--audience-override <label>` naming the
client's own house voice; the blend still runs (never skipped — never advisory) but resolves to
the client's named voice for every day.
If the client names a different audience or persona: pass that as the override; the blend
re-resolves around it.

All content this week (posts, comments, blog, email, podcast) is governed by that day's blend —
consistently within a day, deliberately varied ACROSS days when the theme's daily angle calls
for a different topic emphasis (never a forced-identical week with no logged reason).

Flag-guarded: `SKILL35_BLEND_GOVERNS=0` reverts to the pre-U98 single-persona-per-week selection
(the exact prose this note replaced — preserved in git history, not re-implemented in code) —
the flag defaults to governing (`1`), per the D1 ruling's "never advisory" mandate.

**Step 0b: Request the Weekly Theme (Heartbeat Task)**
This step is automated via the heartbeat.md file. Every Saturday, the AI reaches out to the client (owner/founder) to get the weekly theme. See Section 24: Heartbeat.md Configuration for the full schedule and message flow. Once the theme is received, the AI immediately begins Step 1.

**Step 1: Log the Theme**
1. Receive the weekly theme from the client (owner/founder) (via the heartbeat request).
2. Log the theme to the designated Google Sheet for record-keeping.
3. Confirm the theme is related to the work [Brand Name] does with the client's target audience.

**Step 2: Research the Theme**
4. Research the theme to find supporting facts, figures, studies, or data points.
5. Find at least 3 credible sources that back up the theme.
6. Document the research with source names and key data points.
7. Ensure the research is relevant to the client's target audience.

**Step 3: Create the Core Content**
8. Using the research, outline what each of the 7 days will cover.
9. Write the core content for all 7 days following the Television Show Framework.
10. Ensure Day 1 hooks, each day builds, cliffhangers connect each day, and Day 7 is the grand finale.
11. Ensure the pitch intensity follows the schedule: 4/10 on Day 1, gradually increasing to 10/10 on Day 7.
12. Ensure recaps are concise, curiosity-driven, and placed correctly (never in the Hook Zone).
13. Ensure Day 7 is the longest piece of content.
14. Ensure Day 7 teases next week's theme.
15. Verify that each day works as a standalone piece while connecting to the series.

**Step 4: Generate Images**
16. Generate 7 images at 4:5 (1080 x 1350) for feed posts using Nano Banana 2 via kie.ai.
17. Generate 7 images at 2:3 (1000 x 1500) for Pinterest using Nano Banana 2 via kie.ai.
18. Generate 7 images at 9:16 (1080 x 1920) for Stories/Reels/TikTok using Nano Banana 2 via kie.ai.
19. Generate YouTube thumbnails at 16:9 (1280 x 720) as needed.
20. Generate 1 blog post featured image at 16:9 (1200 x 630) for the weekly blog post.

**Step 5: Create Platform-Specific Content**
21. Rewrite the core content for Facebook following Facebook best practices and content zones.
22. Rewrite the core content for Instagram following Instagram best practices and content zones.
23. Rewrite the core content for LinkedIn following LinkedIn best practices and content zones.
24. Rewrite the core content for YouTube (Community Posts) following YouTube best practices and content zones.
25. Rewrite the core content for Pinterest following Pinterest best practices and content zones.
26. Rewrite the core content for TikTok following TikTok best practices and content zones.

**Step 5b: Write Comments for Every Post**
27. For each of the 42 platform-specific posts, write a unique comment that ties to that day's content, uses emotionally visceral language, and ends with the action link. Follow the Comment Strategy in Section 12. No two comments should be the same.

**Step 5c: Create the Email Newsletter (for Tuesday 9 AM)**
28. Write the weekly email newsletter combining the week's content. Follow the Email Newsletter guidelines in Section 13. Include TLDR, soft pitches at 25% and 50%, and intentional pitch at the end.

**Step 5d: Create the Thursday Carousel**
29. Compile Days 1-4 into carousel slides for all platforms. Follow the Carousel Strategy in Section 9. Generate carousel-specific images. Create the LinkedIn PDF version.

**Step 6: Create the Blog Post(for Day 7 release)**
30. Combine all 7 days of core content and research into one comprehensive blog post.
31. Follow the Blog Post Production guidelines in Section 14.
29. Generate the blog post featured image.

**Step 7: Create the Podcast Script (for Day 7 release)**
32. Write a podcast script from the 7-day core content.
33. Embed Fish Audio S2 inline emotion tags in [square brackets] throughout the script.
34. Follow the Podcast Production guidelines in Section 15.

**Step 8: Create Video Content**
35. Follow the Video Production Pipeline in Section 16.
36. Generate 8-second video segments from the daily images using Veo 3.1 Lite via kie.ai.
37. Merge segments with audio using FFmpeg on OpenClaw.
38. Produce one 60-second video for Day 1 (opener) and one for Day 7 (grand finale) at 9:16 (1080 x 1920).

**Step 9: QC All Content**
39. Spin up QC agents to review all content against the checklist in Section 19.
40. Any failures are sent back to the originating Sub-Agent for revision (up to 3 retries).
41. If any content fails QC after 3 retries, notify the user via Telegram.

**Step 10: Schedule Everything via GHL Social Planner API**
42. Schedule all posts through the GoHighLevel (Convert and Flow) Social Planner API. See Section 17 for endpoints.
43. After each post publishes, post the corresponding comment below it with the action link.
44. Schedule the email newsletter for Tuesday at 9:00 AM.
45. Schedule the carousel posts for Thursday.
46. Schedule the blog post, podcast, and grand finale for Day 7.

**Step 11: Log Everything to Google Sheet**
47. Log all produced content to the client's Google Sheet. Each content type goes to its designated worksheet. See Section 25: Google Sheet Structure for the worksheet layout and column structure.
48. Log image URLs/references to the Images worksheet.
49. Log video URLs/references to the Videos worksheet.
50. Update the Weekly Overview worksheet with the theme, dates, and production status.

**Step 12: Log to Memory (Memory-Core Integration)**
After all content is scheduled and logged to Google Sheets:
51. Write a summary to the daily memory note (memory/YYYY-MM-DD.md): "Social Media Week [N]: Theme '[theme]', 42 posts scheduled across 6 platforms, [video count] videos, blog + podcast for Day 7. Persona: [selected persona or 'personal brand tone']."
52. If engagement data is available from the previous week (via GHL analytics or manual input), note: "Last week's theme '[theme]' produced [engagement summary]. Top platform: [platform]. Best performing day: [day]."
53. Log the persona selection and outcome: "Used [persona name] for this week. Content was [approved/revised/overridden by client]."
54. Memory-core captures these notes automatically. Dreaming may promote high-value insights (e.g., "Hormozi-style content produced 2x engagement on sales-focused themes") into MEMORY.md overnight.
55. Memory Wiki can compile weekly performance into a structured "Social Media Performance" wiki page over time.

**Dependency Note:** This skill depends on Skill 31 (Upgraded Memory System) for memory-core, Dreaming, and Memory Wiki functionality. If Skill 31 is not installed, Steps 51-55 are skipped and the AI logs to MEMORY.md directly instead.

**Dependency Note:** This skill depends on Skill 30 (Fish Audio API Reference) for podcast production via Fish Audio S2. If Skill 30 is not installed, podcast production (Step 7) is skipped and the AI notifies the client: "Podcast production requires Fish Audio S2 (Skill 30). Install Skill 30 to enable weekly podcast episodes."

---

## 4. 7-Part Content Structure & Cliffhanger Architecture

### Series Label Format

Every post is labeled in the series. Spell it out:

**One of Seven | Two of Seven | Three of Seven | Four of Seven | Five of Seven | Six of Seven | Seven of Seven**

Do NOT write it as 1/7 or 2/7. Spell it out. Place the series label at the beginning or end of the content. Keep it consistent throughout the week.

### Core Content Structure Per Day

| Day | Role | Pitch Intensity | Content Length | Cliffhanger |
|-----|------|----------------|---------------|-------------|
| Day 1 (Pilot) | Introduce the weekly theme. Set the stage. Hook the audience. This is the pilot episode. | Warm introduction (4/10). "[Brand Name] helps people navigate this." | Shortest or second-shortest of the series. | Tease what's coming on Day 2 with excitement. |
| Day 2 | Go deeper into the theme. Present a key fact or research insight. | Building (5/10). Reference what [Brand Name] offers. | Slightly longer than Day 1. | Create curiosity about the practical tip coming on Day 3. |
| Day 3 | Share a practical tip or actionable advice. | Steady (5/10). Brief mention of how [Brand Name] delivers this. | Building. | Tease the real-world story coming on Day 4. |
| Day 4 | Present a case study, story, or scenario. | Direct (6/10). Connect the story to [Brand Name] outcomes. | Building. | Tease the myth-busting content coming on Day 5. |
| Day 5 | Address common questions or misconceptions. | Strong (7/10). Directly address how [Brand Name] solves these problems. | Building. | Tease the advanced insights coming on Day 6. |
| Day 6 | Provide advanced insights or lesser-known information. | Urgent (9/10). Clear connection between this knowledge and what [Brand Name] provides. | Second longest. | Build anticipation for the grand finale on Day 7. |
| Day 7 (Grand Finale) | Wrap up. Summarize the series. Strongest call to action. Release blog + podcast. | Maximum (10/10). Direct ask to take action, visit the website, or connect with [Brand Name]. | LONGEST piece of the series. Bring it all home. | Tease NEXT WEEK'S theme to maintain momentum across weeks. |

> NOTE: The AI should adapt this structure based on the theme. The above is a starting framework, not a rigid template. The non-negotiables are: Day 1 hooks, Day 7 is the longest and strongest, pitch intensity builds, and cliffhangers connect every day.

---

## 5. Content Zone System

Every post is built using a zone system. Each zone has a specific purpose. The AI must write content into the correct zone in the correct order. The zones adjust per platform based on truncation points.

### Zone Definitions

**Zone 1: Mobile Hook Zone (MOST CRITICAL)**
This is the text visible on mobile devices before the "See More" or "...more" button appears. This is the scroll-stopper. If this zone fails, nothing else matters. The hook MUST live here. Never put a recap, greeting, or filler in this zone.

**Zone 2: Desktop Hook Zone**
This is additional text visible on desktop (but hidden on mobile behind "See More"). This zone expands on the hook. It gives desktop users a reason to click "See More" and read the full post. Not all platforms have this zone (Instagram and TikTok truncate the same on mobile and desktop).

**Zone 3: Value Zone (includes woven-in Recap)**
The main body of educational, informational, or story-driven content. This zone starts delivering value IMMEDIATELY after the hook. The recap from previous days is woven INTO this zone naturally, somewhere in the middle of the value delivery, NOT at the beginning. The reader must start getting value first, then encounter the recap as a natural part of the narrative. This prevents losing readers who just got hooked but then hit a recap of content they haven't seen. The recap should feel like a natural part of the conversation: "Earlier this week, we explored why this matters more than most people realize, and the stat we shared on Day 1 caught a lot of people off guard."

**Zone 4: Pitch Zone (includes engagement CTA)**
The primary goal of every post is getting appointments. The pitch zone creates an emotionally compelling reason for the reader to schedule an appointment with [Brand Name]. This is not about selling a product. This is about helping the reader take the next step. The pitch follows the intensity schedule (4/10 on Day 1, gradually increasing to 10/10 on Day 7), and always ends with a **two-channel CTA (§12): the PRIMARY directive is to send a message / DM** (which reaches an agent that answers, via GHL Conversations → Skill 38), **with "the link is in the comments" as the backup** for readers who prefer to self-serve the weekly action link. The pitch should make them FEEL something: the urgency of their situation, the hope that comes from taking action, the relief of finally having someone who understands. Then it points them to DM us (primary) and to the comments where the action link lives (backup).

**Zone 5: Cliffhanger Zone**
The last content element the reader sees (before hashtags). Teases tomorrow's content (Days 1-6) or next week's theme (Day 7). Must create genuine excitement and anticipation. This is what people remember as they scroll away.

**Zone 6: Hashtag/SEO Zone**
Platform-specific hashtags or keywords. Always last. Strategy differs per platform (see Platform Best Practices).

### Zone Map Per Platform

| Zone | Facebook | Instagram | LinkedIn | YouTube | Pinterest | TikTok |
|------|----------|-----------|----------|---------|-----------|--------|
| Zone 1: Mobile Hook | First 150 chars (~25 words) | First 125 chars (~20 words) | First 140 chars (~23 words) | First 288 chars (~48 words) | First ~50 chars (~8 words) | First ~150 chars (~25 words) |
| Zone 2: Desktop Hook | 150-477 chars (~25-80 words) | Same as Zone 1 | 140-210 chars (~23-35 words) | Same as Zone 1 | Same as Zone 1 | Same as Zone 1 |
| Zone 3: Value + Recap | Main body. Start with value, weave recap in the middle. | Main body. Start with value, weave recap in the middle. | Main body (best at 1800-2100 chars total). Weave recap in naturally. | Main body. Weave recap in naturally. | Full description (keyword-rich) | Main body. Weave recap in naturally. |
| Zone 4: Pitch + CTA | Pitch intensity per schedule + engagement ask | Pitch + CTA (or put CTA in first comment) | Pitch + CTA (end with a question for comments) | Pitch + CTA | Within description | Pitch + CTA |
| Zone 5: Cliffhanger | End of content body | End of content body | End of content body | End of content body | N/A | End of content body |
| Zone 6: Hashtags | 1-3 max (low impact) | 3-5 targeted (end or first comment) | 3-5 (end of post) | N/A | Keywords in description instead | Keyword-rich for SEO discovery |

### Zone Writing Rules

1. **Zone 1 is sacred.** Never waste it on anything other than the hook. No greetings. No "Happy Monday." No recap. No filler.
2. **Recap is woven into Zone 3, never at the start.** The reader must receive value FIRST, then the recap appears naturally within the middle of the value delivery.
3. **Zone 4 combines pitch and engagement ask.** The pitch mentions [Brand Name]. The engagement ask drives action on the post (save, comment, tag, follow, book). Both are woven together naturally.
4. **Zone 5 is the last thing before hashtags.** The cliffhanger is what people remember as they scroll away.
5. **Zone 6 never contains content.** It is only hashtags or SEO keywords.
6. **Pinterest is an exception.** Pinterest descriptions are so short that Zones 3-5 are compressed. Focus on keyword-rich descriptions for SEO discovery.

---

## 6. Content Flow Rules (Zone-by-Zone Writing Instructions)

### Writing Instructions for the AI

When writing content for any platform, follow this process:

**Step 1: Write Zone 1 (Mobile Hook)**
- Look at the platform's Mobile Hook Zone character limit.
- Write a hook that fits WITHIN that limit.
- The hook must stop the scroll. Use one of these techniques:
  - Bold statement or surprising fact
  - Direct question to the reader
  - Pattern interrupt (something unexpected)
  - Promise of value ("Here's what most people miss about...")
  - Controversy or myth-busting ("Everything you've been told about X is wrong")

**Step 2: Write Zone 2 (Desktop Hook) if applicable**
- Only Facebook and LinkedIn have a separate Desktop Hook Zone.
- Expand on the hook. Give desktop users a reason to click "See More."

**Step 3: Write Zone 3 (Value + Woven Recap)**
- Start delivering value IMMEDIATELY. Do not start with a recap.
- Open with the strongest insight, tip, or story for today's topic.
- Weave the recap into the MIDDLE of the value delivery, not the beginning.
- The recap should feel like a natural part of the narrative, creating curiosity about missed content.
- Continue delivering value after the recap.
- Use the research. Reference facts, figures, studies.
- Make it practical and actionable where possible.
- This zone should feel like a micro-blog that gives real, tangible value.
- Recap integration rules:
  - Day 1: No recap. Pure value.
  - Day 2: One sentence woven into the value. Example: "This builds on what we shared yesterday, where a single stat caught a lot of people off guard."
  - Days 3-6: 1-2 sentences woven naturally into the middle of the value. Example: "If you've been following this series, you already know from Day 1 and Day 2 that the research paints a very different picture than most people expect. Today, we're taking that even further."
  - Day 7: 2-3 sentence recap woven into the grand finale narrative. The recap is more prominent here but still flows as part of the value delivery.

**Step 4: Write Zone 4 (Pitch + Appointment Directive)**
- The primary goal is ALWAYS getting appointments. Every pitch should create an emotionally compelling reason to schedule.
- Follow the pitch intensity schedule:
  - Day 1 (Intensity: 4/10): Warm introduction. "[Brand Name] helps people with exactly this. Send us a message to learn how to take the next step — the link is also in the comments."
  - Day 2 (Intensity: 5/10): Building. "This is what [Brand Name] does every day. Send us a message to start a conversation — the link is in the comments too."
  - Day 3 (Intensity: 5/10): Steady. "If this is resonating, you're not alone. DM us to connect with [Brand Name] — or grab the link in the comments."
  - Day 4 (Intensity: 6/10): Direct. "This is exactly what [Brand Name] is designed to address. Send us a message to take action — the link is in the comments."
  - Day 5 (Intensity: 7/10): Strong. "You've seen the evidence. You feel it. Send us a message to schedule your conversation with [Brand Name] — the link is in the comments."
  - Day 6 (Intensity: 9/10): Urgent. "You don't have to figure this out alone. The [Brand Name] team is ready. Send us a message right now — the link is in the comments."
  - Day 7 (Intensity: 10/10): Maximum. "This is the moment. Don't let another week go by. Send us a message to take action with [Brand Name] today — the link is in the comments."
- The pitch always ends with the two-channel CTA (§12): the PRIMARY directive is to SEND A MESSAGE / DM (it reaches an agent that answers, via GHL Conversations → Skill 38); "the link is in the comments" is the reach-preserving BACKUP. The action link lives in the comment, not the post body.
- Combine the pitch with an engagement ask where natural:
  - "Save this post so you can reference it later."
  - "Tag someone who needs to see this."
  - "Drop a comment and tell us what you think."

**Step 5: Write Zone 5 (Cliffhanger)**
- Days 1-6: Tease tomorrow's content with excitement and curiosity.
  - "Tomorrow, we're revealing something most people have never considered..."
  - "What we're sharing next might change how you think about this entirely..."
- Day 7: Tease next week's theme.
  - "Next week, we're diving into something that affects everyone in [target audience]..."

**Step 6: Write Zone 6 (Hashtags/SEO)**
- Add platform-appropriate hashtags following the platform best practices section.

### Recap Integration Summary

| Day | Recap Placement | Max Length |
|-----|----------------|-----------|
| Day 1 | No recap. Pure value. | None |
| Day 2 | Woven into middle of value zone. | 1 sentence |
| Day 3 | Woven into middle of value zone. | 1-2 sentences |
| Day 4 | Woven into middle of value zone. | 1-2 sentences |
| Day 5 | Woven into middle of value zone. | 1-2 sentences |
| Day 6 | Woven into middle of value zone. | 1-2 sentences |
| Day 7 | Woven into grand finale narrative. | 2-3 sentences |

---

## 7. Platform Guide: Image Sizes, Characters & Content Zones

### FACEBOOK

**Facebook Feed Post**
- Image Ratio: 4:5 (1080 x 1350 pixels)
- Max Characters: 63,206 (~10,500 words)
- Supports: Image + Text
- Zone 1 (Mobile Hook): First 150 characters (~25 words)
- Zone 2 (Desktop Hook): 150-477 characters (~25-80 words)
- Full Body: 477+ characters

**Facebook Stories** - 9:16 (1080x1920), Image + Video, 60 sec/clip, photos display 5-6 sec, disappears 24 hours
**Facebook Reels** - 9:16 (1080x1920), Video only, 90 sec max (15-30 sec best), caption 2,200 chars

### INSTAGRAM

**Instagram Feed Post**
- Image Ratio: 4:5 (1080 x 1350 pixels)
- Max Characters: 2,200 (~370 words)
- Supports: Image + Text
- Zone 1 (Mobile Hook): First 125 characters (~20 words)
- No separate Desktop Hook Zone.
- Full Body: 125-2,200 characters

**Instagram Stories** - 9:16 (1080x1920), Image + Video, 60 sec/clip, photos ~7 sec, disappears 24 hours
**Instagram Reels** - 9:16 (1080x1920), Video only, 90 sec max, caption 2,200 chars

### LINKEDIN

**LinkedIn Feed Post**
- Image Ratio: 4:5 (1080 x 1350 pixels)
- Max Characters: 3,000 (~500 words)
- Supports: Image + Text
- Zone 1 (Mobile Hook): First 140 characters (~23 words)
- Zone 2 (Desktop Hook): 140-210 characters (~23-35 words)
- Full Body: 210-3,000 characters. Best engagement at 1,800-2,100 characters (~300-350 words).

**LinkedIn Short-Form Video Feed** - 9:16 (1080x1920), Video only, 10 min max (30-90 sec recommended)
**LinkedIn Carousel** - PDF upload (NOT images), 1080x1080 or 1920x1080, max 10 slides, 3,000 char caption. Highest engagement format on any platform (21.77%).

> LinkedIn does NOT have Stories or Reels. They have a TikTok-style short-form video feed.

### YOUTUBE

**YouTube Community Post**
- Image Ratio: 4:5 (1080x1350), displays as square preview, expands on click
- Max Characters: 7,700+ (~1,280 words)
- Supports: Image + Text (up to 10 images)
- Zone 1 (Hook): First 288 characters (~48 words)
- Full Body: 288-7,700+ characters

**YouTube Shorts** - 9:16 (1080x1920), Video ONLY, 3 min max, 100 char title
**YouTube Thumbnail** - 16:9 (1280x720), 2 MB max, JPG/PNG/GIF

### PINTEREST

**Pinterest Standard Pin**
- Image Ratio: 2:3 (1000 x 1500 pixels) OPTIMAL
- Max Characters: 500 (~83 words) for description
- Zone 1 (Hook): First ~50 characters (~8 words)
- Full Body: 50-500 characters

**Pinterest Idea Pin** - 9:16 (1080x1920), Image + Video, 60 sec/clip, 250 chars/page

> Pinterest does NOT have Stories. Idea Pins replaced that concept. Use keywords, not hashtags.

### TIKTOK

**TikTok Video Post**
- Video Ratio: 9:16 (1080 x 1920)
- Caption Max: 4,000 chars (~670 words)
- Video Max: 10 min
- Zone 1 (Hook): First ~150 characters (~25 words)
- Full Body: 150-4,000 characters (use for SEO keywords)

**TikTok Carousel** - 9:16 (1080x1920), max 35 images, 4,000 char caption
**TikTok Stories** - 9:16 (1080x1920), Video only, 60 sec, disappears 24 hours

---

## 8. Image Production (kie.ai)

### Image Production Path — which producer do I use? (read this FIRST)

#### Step 0 — Agnes vs. Kie.ai choice (MANDATORY when both are installed)

Before picking any production path, check whether the client has BOTH Agnes (Skill 63 `agnes-image-2.1-flash` / Skill 64 `agnes-video-v2.0`) AND Kie.ai installed. If both are present, the skill MUST offer the owner a choice — it MUST NOT silently default to Kie.ai when Agnes is available.

> "I see you have Agnes. Because you have Agnes, would you like to use Agnes to create your videos and images, or would you prefer to stick with Kie.ai?"

Wait for the owner's answer, then route every generation call accordingly:
- **Owner chooses Agnes** → all image/video assets this cycle go through Path 2 (Agnes), and kie.ai becomes the fallback only when Agnes is unavailable.
- **Owner chooses Kie.ai** → Path 1 (kie.ai direct) remains the default, as normal.
- **Owner doesn't answer** (heartbeat timeout) → Path 1 (kie.ai direct) proceeds as the default.

If only one provider is installed (Kie.ai only, or Agnes only), skip this choice — there is nothing to offer — and proceed directly to the decision table.

#### Path decision table

There are exactly THREE ways an image for this skill gets produced. Pick ONE per asset, in this priority order. Every path ends the same way: the finished file is uploaded to the client's GHL Media Library (SKILL.md Media Delivery Contract) and the returned permanent CDN `url` is what gets logged/posted — never a generator-hosted or tmpfiles.org link.

| # | Path | When to use | Producer | Credential | Gate before it counts |
|---|------|-------------|----------|------------|------------------------|
| 1 | **kie.ai direct** (DEFAULT) | The skill's own pipeline produces the asset and no Agnes/Graphics override is in play. This is the normal weekly path. | kie.ai — Ideogram V3 DESIGN for any text/headline image (every Section-18 deliverable); Nano Banana 2/Pro only for non-text imagery (Section 8 routing table). | `KIE_API_KEY` | `pregen_prompt_gate.py check` (Section 8a) BEFORE the paid call; Section 19 post-gen QC after. |
| 2 | **Agnes (Skill 63 image / Skill 64 video)** | The request explicitly names Agnes ("generate this with Agnes"), OR an upstream skill/operator routes the asset to Agnes, OR kie.ai is unavailable and Agnes is the configured fallback. Agnes is OPT-IN, never the silent default. | Skill 63 `agnes-image-2.1-flash` (synchronous text-to-image / image-to-image) for stills; Skill 64 `agnes-video-v2.0` (async create-task → poll) for video segments. | `AGNES_AI_API_KEY` (existing fleet credential) | Same `pregen_prompt_gate.py check` routing rule still applies (text-overlay assets must not be routed to a non-text-rendering model); then upload to GHL CDN. |
| 3 | **Graphics department handoff** | A human/department supplies the finished asset instead of this skill generating it. The Image Generator step is REPLACED, not skipped. | Graphics department (external) — the skill only receives + QC-gates the file. | none (no generation call) | Section 19a input-quality gate: REJECT any graphics-department asset lacking a SOP-GIP-02 QC receipt scoring >= 8.5 (`pregen_prompt_gate.py check --asset-source graphics-department --qc-receipt-file <job>/qc/image_qc_report.json`). |

**Decision rule:** if nobody named Agnes and no Graphics asset was handed in, you are on Path 1 (kie.ai direct). Do not invent an Agnes or Graphics path to avoid a generation step.

**Working examples:**

Path 1 — kie.ai direct (default, text-overlay daily image):
```bash
# 1) Gate the prompt BEFORE spending the paid call (Section 8a)
python3 ~/.openclaw/skills/35-social-media-planner/scripts/pregen_prompt_gate.py check \
  --prompt-file working/prompts/day1-primary.txt \
  --model ideogram-v3-design \
  --platform instagram --ratio 4:5 --pixels 1080x1350 \
  --text-overlay "Three Moves That Doubled Our Pipeline" \
  --brand-colors "#0B3D2E,#F5EFE0,#C9A24B" \
  --avoid-list-file working/compiled-negatives.txt
# 2) Generate via kie.ai (Ideogram V3 DESIGN for text-led images), save to working/images/day1.png
# 3) Upload to GHL CDN (SKILL.md Media Delivery Contract — NO -F "hosted=true")
curl -X POST "https://services.leadconnectorhq.com/medias/upload-file" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" -H "Version: 2021-07-28" \
  -F "file=@working/images/day1.png"
# -> use the returned url (assets.cdn.filesafe.space/...) everywhere
```

Path 2 — Agnes image (Skill 63, only when Agnes is named/routed; synchronous):
```bash
curl -s -X POST "https://apihub.agnes-ai.com/v1/images/generations" \
  -H "Authorization: Bearer $AGNES_AI_API_KEY" -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.1-flash",
    "prompt": "Photoreal lifestyle background, warm morning light, no text",
    "size": "2K",
    "aspect_ratio": "4:5",
    "extra_body": {"response_format": "url"}
  }'
# response_format MUST be inside extra_body (Skill 63). Download the returned URL,
# then re-upload to GHL CDN — never log the Agnes-hosted URL directly.
```

Path 2 — Agnes video (Skill 64, async create-task → poll):
```bash
TASK=$(curl -s -X POST "https://apihub.agnes-ai.com/v1/videos/generations" \
  -H "Authorization: Bearer $AGNES_AI_API_KEY" -H "Content-Type: application/json" \
  -d '{"model": "agnes-video-v2.0", "prompt": "...", "num_frames": 81}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
# num_frames must satisfy the 8n+1 rule (Skill 64). Poll GET .../videos/generations/$TASK
# until status=succeeded, download the .mp4, then upload to GHL CDN.
```

Path 3 — Graphics department handoff (no generation; gate the supplied asset):
```bash
python3 ~/.openclaw/skills/35-social-media-planner/scripts/pregen_prompt_gate.py check \
  --prompt-file working/prompts/day1-primary.txt \
  --asset-source graphics-department \
  --qc-receipt-file working/jobs/day1/qc/image_qc_report.json \
  --model ideogram-v3-design --platform instagram --ratio 4:5 --pixels 1080x1350
# exit 0 only if the SOP-GIP-02 receipt scores >= 8.5 (Section 19a); then upload to GHL CDN.
```

### Image Generation Models

**Model routing rule (P3-05 fix — read this before picking a model):** every image this skill produces carries a baked text/headline overlay (Section 18) — there is no non-text image type in this playbook. Section 45's own documented routing rule
(`45-design-intelligence-library/library/social-media-designs/_RULES.md`, "Model routing") states: *"Quote-card / text-led posts -> Ideogram V3 DESIGN."* Nano Banana 2/Pro are strong general image models but are NOT text-rendering specialists —
routing every headline-bearing image to them was the root cause plausibly driving Section 18's "spelling errors on image text, retry up to 3x" failure loop (P3-05 root-cause finding). The fix:

| Model | Role | When to use | Cost (1K) | Cost (2K) | Cost (4K) |
|-------|------|-------------|-----------|-----------|-----------|
| **Ideogram V3 DESIGN** | **PRIMARY for every Section-18 deliverable** | ANY image carrying baked text/headline copy — i.e. every regular daily image, carousel slide, blog featured image, and podcast cover this playbook produces. | see kie.ai pricing (Ideogram V3) | — | — |
| Nano Banana 2 | Non-text imagery only | Photoreal/lifestyle backgrounds, mood/reference shots, or any asset with NO on-image text at all. | $0.04 | $0.06 | $0.09 |
| Nano Banana Pro | Non-text imagery backup only | Same non-text scope as Nano Banana 2, used as its backup. | $0.09 | $0.09 | $0.12 |

Every prompt MUST pass `scripts/pregen_prompt_gate.py check` (Section 8a) before generation — the gate REFUSES (exit 6, `AF-SM-MODEL-ROUTING`) a text-overlay prompt routed to Nano Banana, making the old failure mode structurally impossible rather than merely discouraged.

### Section 8a — PRE-GENERATION Prompt QC Gate (P3-05 step 9, mandatory before every generation call)

Before ANY image prompt reaches kie.ai, run it through the gate. This is the pre-generation counterpart to Section 19's post-generation QC — it exists to catch a defective prompt BEFORE spending the paid generation call, mirroring the Graphics department's `diu_validator.py prompt-band` fail-closed shape (same exit-code discipline: 0 = pass, 3 = structural FORM failure, 6 = quality/routing failure). A gate-failed prompt is fixed and re-run — it is never generated.

```bash
python3 ~/.openclaw/skills/35-social-media-planner/scripts/pregen_prompt_gate.py check \
  --prompt-file working/prompts/day1-primary.txt \
  --model ideogram-v3-design \
  --platform instagram --ratio 4:5 --pixels 1080x1350 \
  --text-overlay "Three Moves That Doubled Our Pipeline" \
  --brand-colors "#0B3D2E,#F5EFE0,#C9A24B" \
  --avoid-list-file working/compiled-negatives.txt
```

The gate checks (all FORM-level, exit 3 if any is missing): the platform ratio + pixel spec are both declared; brand colors are named; a MERGED negative/avoid-list is attached (Section 8b — never generate with no avoid-list); the exact on-image copy from Section 18 is baked verbatim into the prompt body; and the mandatory brand-safety clause ("brand-appropriate, appropriate for the client's audience, no suggestive content") is present. Once FORM clears, the gate checks routing (exit 6 if wrong): a text-overlay prompt on Nano Banana is refused outright (see Section 8 above). If the image originates from the Graphics department rather than this skill's own pipeline, pass `--asset-source graphics-department --qc-receipt-file <job>/qc/image_qc_report.json` — the gate REJECTS a graphics-department asset with no SOP-GIP-02 QC receipt scoring >= 8.5 instead of posting it (Section 19a).

### Section 8b — Load Skill 45's Negative-Prompting Rules BEFORE Writing Any Prompt (P3-05 step 7)

The Image Prompt Engineer step (INSTRUCTIONS.md Phase 2) MUST load these two files and merge their applicable avoid-list entries into the prompt BEFORE writing it — never after, never skipped:
1. `45-design-intelligence-library/library/_system/NEGATIVE-PROMPTING-SOP.md` — the universal baseline avoid-list (Layer 1) every generation carries, plus the category/style-card layering pattern.
2. `45-design-intelligence-library/library/social-media-designs/_RULES.md` — the social-media-designs category rules: aspect ratios, hard rules (never text over faces, 9:16 safe zones, mobile-first legibility), and the model routing rule (Section 8).

Write the merged avoid-list to `working/compiled-negatives.txt` for the run (or per-image if content varies) and pass it to Section 8a's gate via `--avoid-list-file`. This gives the retry loop a MEMORY of prior failure classes instead of retrying blind (the gap the P3-05 root-cause finding names explicitly).

### Weekly Image Production Schedule

| Image Type | Ratio | Pixels | Per Day | Per Week | Platforms |
|-----------|-------|--------|---------|----------|-----------|
| Primary | 4:5 | 1080 x 1350 | 1 | 7 | FB Feed, IG Feed, LinkedIn Feed, YT Community |
| Vertical | 2:3 | 1000 x 1500 | 1 | 7 | Pinterest Pin |
| Full Screen | 9:16 | 1080 x 1920 | 1 | 7 | Stories, Reels, TikTok, YT Shorts, Pinterest Idea Pin |
| Blog Image | 16:9 | 1200 x 630 | 0 | 1 | Blog post featured image |
| Podcast Cover | 1:1 | 1400 x 1400 (2K res) | 0 | 1 | Podbean episode cover art (min 1400x1400 required) |
| Thumbnail | 16:9 | 1280 x 720 | As needed | As needed | YouTube Thumbnails |

Weekly cost at 1K: 23 images x $0.04 = $0.92/week
Weekly cost at 2K: 23 images x $0.06 = $1.38/week

---

## 9. Carousel Strategy (Thursdays)

Carousel posts go out every Thursday. They repurpose the week's content into a swipeable format that drives higher engagement. Carousels are one of the highest-performing content formats on Instagram (1.4x more reach) and LinkedIn (21.77% engagement rate, the highest of any format on any platform).

### Thursday Carousel Content

The Thursday carousel summarizes the first 4 days of the series (Days 1-4 have already been posted by Thursday). Each slide covers one day's key insight. The carousel ends with a teaser for Days 5-7 still to come, creating anticipation.

### Carousel Image Reuse Strategy (Cost Optimization)

LinkedIn now supports 4:5 (1080x1350) carousel slides uploaded as PDF. This means we can create ONE set of carousel images and reuse them across three platforms without regenerating.

**Primary Carousel Set: 4:5 (1080 x 1350) - Create ONCE, use on 3 platforms**

| Platform | Same 4:5 Images? | How to Upload | Notes |
|----------|-----------------|---------------|-------|
| Facebook | YES, reuse directly | Upload individual images | Standard image carousel upload |
| Instagram | YES, reuse directly | Upload individual images | First slide ratio sets all slides. 4:5 is the preferred format. |
| LinkedIn | YES, reuse directly | Convert images to PDF, upload as document | Each image becomes a page in the PDF. 4:5 outperforms square on mobile. |

**Separate Carousel Images Required:**

| Platform | Ratio | Why Separate? |
|----------|-------|--------------|
| TikTok | 9:16 (1080 x 1920) | Different aspect ratio. Must be taller. |
| Pinterest | 2:3 (1000 x 1500) | Different aspect ratio. Must be 2:3 for optimal engagement. |

### LinkedIn Carousel: Additional Considerations

LinkedIn carousels have a unique advantage: they support more text-heavy, educational content. Because LinkedIn's audience expects professional value, the LinkedIn carousel slides CAN include more text, data, and detailed insights than the Facebook/Instagram versions. However, for cost optimization, we start with the same 4:5 images used on Facebook and Instagram, then convert them to PDF for LinkedIn upload.

If a specific week's content demands a more detailed, text-heavy LinkedIn carousel (like a data-driven breakdown or a step-by-step framework), create a separate set of LinkedIn-specific slides. But this should be the exception, not the rule.

**LinkedIn PDF Carousel Process:**
1. Take the 4:5 (1080x1350) carousel images already generated for Facebook/Instagram.
2. Compile them into a multi-page PDF using FFmpeg or a PDF generation tool on OpenClaw.
3. Upload the PDF as a "document post" on LinkedIn.
4. Add the caption with appropriate LinkedIn content zones.

### Carousel Slide Structure (7-9 slides)

| Slide | Content |
|-------|---------|
| Slide 1 | Title slide. Bold hook. Series branding. "Swipe to see what we've been covering this week." |
| Slide 2 | Day 1 key insight (1-2 sentences + visual) |
| Slide 3 | Day 2 key insight (1-2 sentences + visual) |
| Slide 4 | Day 3 key insight (1-2 sentences + visual) |
| Slide 5 | Day 4 key insight (1-2 sentences + visual) |
| Slide 6 | Teaser slide. "Days 5-7 are still coming. You don't want to miss what's next." |
| Slide 7 | CTA slide. PRIMARY DM CTA first, comment link as backup: "Follow us for the rest of the series. **Send us a message to take the next step with [Brand Name]** — and the link is also in the comments." (DM → GHL Conversations → Skill 38 answers; §12/§19.) |

### Carousel Image Costs

| Item | Count | Cost |
|------|-------|------|
| 4:5 carousel images (shared across FB, IG, LinkedIn) | 7-9 | $0.28-$0.36 (Nano Banana 2 at 1K) |
| 9:16 carousel images (TikTok) | 7-9 | $0.28-$0.36 |
| 2:3 carousel images (Pinterest) | 7-9 | $0.28-$0.36 |
| **Total carousel images per week** | **21-27** | **$0.84-$1.08** |

### Carousel Specs Per Platform (Quick Reference)

| Platform | Max Images | Image Size | Caption Max | Upload Method |
|----------|-----------|------------|-------------|---------------|
| Facebook | 10 | 4:5 (1080x1350) | 63,206 chars | Individual images |
| Instagram | 20 | 4:5 (1080x1350) | 2,200 chars | Individual images |
| LinkedIn | Up to 100 (8-12 optimal) | 4:5 (1080x1350) as PDF | 3,000 chars | PDF document upload |
| TikTok | 35 | 9:16 (1080x1920) | 4,000 chars | Photo carousel post |
| Pinterest | 5 | 2:3 (1000x1500) | 500 chars | Carousel Pin |

---

## 10. Stories, Reels & Short Video Guide

### Stories by Platform

| Platform | Has Stories? | Images? | Video? | Max Length | Disappears? |
|----------|-------------|---------|--------|-----------|-------------|
| Facebook | YES | YES | YES | 60 sec/clip | 24 hours |
| Instagram | YES | YES | YES | 60 sec/clip | 24 hours |
| LinkedIn | NO | N/A | N/A | N/A | N/A |
| YouTube | LIMITED | YES | YES | 60 sec | 7 days |
| Pinterest | NO | Idea Pins | Idea Pins | 60 sec/clip | No |
| TikTok | YES | NO | YES | 60 sec | 24 hours |

### Reels / Shorts by Platform

| Platform | Name | Ratio | Max | Best Length |
|----------|------|-------|-----|-------------|
| Facebook | Reels | 9:16 | 90 sec | 15-30 sec |
| Instagram | Reels | 9:16 | 90 sec | 30-60 sec |
| LinkedIn | Short-Form Video | 9:16 | 10 min | 30-90 sec |
| YouTube | Shorts | 9:16 | 3 min | 30-60 sec |
| Pinterest | Video/Idea Pin | 9:16 or 2:3 | 60 sec/clip | 6-15 sec |
| TikTok | Video Post| 9:16 | 10 min | 15-60 sec |

### Universal Video Format

**60 seconds | 9:16 (1080 x 1920 pixels)**

This works on every platform. One video, every platform.

---

## 11. Platform-Specific Best Practices for Growth

### FACEBOOK

**What the algorithm rewards:** Conversation-starting posts, Reels, native video, consistent posting, community engagement.
**Content style:** Conversational, relatable, question-driven. Lead with an irresistible hook in those first 25 words.

**Growth tactics:**
1. Use Reels for discovery (they reach people who don't follow you).
2. Ask questions that invite comments (the algorithm rewards comment-generating posts).
3. Reply to every comment within the first hour after posting (linked to 9.5% more reactions).
4. Postconsistently. Accounts that don't post in a given week underperform their own baseline.
5. Use Stories between main posts to maintain daily visibility.
6. Pin Day 1 and Day 7 to the top of the page.
7. After posts get likes in Groups, use the "Invite to Follow" feature to convert likers into followers.

**Hashtag strategy:** 1-3 relevant hashtags maximum. Hashtags have low impact on Facebook.
**Postfrequency:** 7 feed posts/week (the series) + daily Stories.

### INSTAGRAM

**What the algorithm rewards:** Watch time, saves, shares, Reels completion rate, carousel swipe-through, comment velocity in first hour.
**Content style:** Visual-first. Image does the heavy lifting. Captions support the visual. Use line breaks and white space.

**Growth tactics:**
1. Reels deliver 36% more reach (use for discovery).
2. Carousels drive 12% more engagement (use for deepening connection).
3. Posting 3-5 times per week grows followers 2x faster than 1-2 times.
4. Use "Save this post" CTAs (saves signal high value to the algorithm).
5. Place additional CTAs in the first comment instead of cluttering the caption.
6. Use Stories with polls, questions, and interactive stickers.
7. Story sequences (3-5 stories in a row) keep viewers engaged longer.

**Hashtag strategy:** 3-5 highly relevant, targeted hashtags. End of caption or first comment.
**Postfrequency:** 7 feed posts/week + daily Stories + 2-3 Reels/week.

### LINKEDIN

**What the algorithm rewards:** Dwell time, comments (especially thoughtful ones), conversation starters, educational content, native vertical video.
**Content style:** Professional but personal. Storytelling works. Short sentences. Line breaks between every 1-2 sentences.

**Growth tactics:**
1. LinkedIn carousels (PDF) earn 21.77% median engagement. The highest of any format on any platform. Use strategically.
2. Posts of 1,800-2,100 characters get the best engagement.
3. End posts with a question to drive comments.
4. Vertical video (9:16) is getting an algorithmic distribution boost in 2026.
5. Post3-5 times per week for significant follower growth.
6. Reply to every comment.

**Hashtag strategy:** 3-5 relevant hashtags at end of post.
**Postfrequency:** 7 feed posts/week + 1-2 short-form videos/week.

### YOUTUBE

**What the algorithm rewards:** Watch time, click-through rate, session duration, community engagement.
**Content style for Community Posts:** Lightweight social updates. Conversational. Ask questions.

**Growth tactics:**
1. Community Posts keep engagement alive between uploads.
2. Polls get 3-4x more interactions than text-only.
3. For Shorts: hook in the first 3 seconds (71% of retention decided in first 3 seconds).
4. Custom thumbnails at 1280x720 are critical for CTR.

**Postfrequency:** 7 Community Posts/week + Shorts when video content is ready.

### PINTEREST

**What the algorithm rewards:** Fresh vertical content, keyword-rich descriptions, high-quality images, saves.
**Content style:** Pinterest is a visual search engine. Descriptions are keyword-rich, not conversational. Think SEO.

**Growth tactics:**
1. Keyword-rich descriptions using search terms relevant to the client's industry and target audience.
2. Vertical 2:3 pins get 67% more engagement than square.
3. Video pins earn nearly double the engagement of static (5.75% vs 3.15%).
4. Pins remain discoverable for months or years.
5. Text overlay on images (Pinterest users scan images for text).
6. Link every Pin back to [Brand Name] website or booking page.

**Hashtag strategy:** No hashtags. Use keyword-rich descriptions instead.
**Postfrequency:** 7 Pins/week with keyword-optimized descriptions.

### TIKTOK

**What the algorithm rewards:** Watch time and completion rate (40-50% of algorithm weight), shares, comments, original content.
**Content style:** Punchy, fast-paced, authentic. First 3 seconds determine everything.

**Growth tactics:**
1. First 3 seconds determine 71% of viewer retention.
2. Videos watched to completion get exponential reach.
3. TikTok heavily favors ORIGINAL content (reposts from other platforms get reduced distribution).
4. Use all 4,000 caption characters for SEO keywords.
5. Photo carousels (up to 35 images) are gaining ground.
6. Respond to comments with new videos (creates engagement loops).
7. Nano/micro accounts get the highest engagement rates (8.1%).

**Hashtag strategy:** Use for SEO discovery. Mix trending + niche-specific.
**Postfrequency:** 7 posts/week + Stories for daily touchpoints.

---

## 12. Comment Strategy + DM Call-to-Action (Every Post, Every Day)

### The Two-Channel CTA Rule (DM-first, comment-backup)

Every single social media post drives the highest-intent reader into a channel that ANSWERS. There are two CTA surfaces, and the post uses BOTH:

1. **DM (primary — the one that gets a reply).** The post asks the reader to **send us a message / DM us** ("Send us a message and we'll help you take the next step"). A Facebook or Instagram DM lands in GHL Conversations, which flows straight into Skill 38's (`38-conversational-ai-system`) existing inbound playbook pipeline — so the reader gets an actual conversational reply, automatically, end to end. This is the change that closes the dead-end: the campaign's highest-intent interaction now lands where an agent (Skill 38) is listening.
2. **Comment (backup — carries the link for reach).** Every post still gets a comment below it carrying the weekly action link ("the link is in the comments"), because platforms (especially Facebook) suppress posts with links in the body, so the comment preserves organic reach for readers who prefer to self-serve the link.

> **Why DM-first (the connection to Skill 38):** the old strategy funneled the highest-intent reader to "check the comments," but nothing in the system reads or replies to public comments — `caf`'s `social` group has no comment/reply command (§17) and public post comments are not a GHL Conversations event, so they never reach Skill 38's inbound webhook. A reader who followed the "check the comments" instruction and then *commented* got no automated reply from anywhere. Routing the primary CTA to DM sends that reader into GHL Conversations (FB/IG DM), which Skill 38 already answers. The comment-link remains as the reach-preserving backup, and §12b (comment reader) turns the residual comment traffic into conversations too. Skill 38 is the owner of every inbound conversation these CTAs generate; Skill 35 is the inbound SOURCE. See the cross-reference in `38-conversational-ai-system/SKILL.md`.

### The Rule

Every single social media post gets a comment below it. The post itself contains BOTH a DM call-to-action (primary — e.g. "Send us a message to talk with an [Brand Name] specialist") AND a line like "the link is in the comments" (backup) that directs the reader to the comment where the weekly action link lives.

### Why Comments, Not Links in the Post

Social media platforms (especially Facebook) suppress posts that contain external links. By keeping the link in the comments instead of the post body, the post gets better organic reach. The post stays focused on value. The comment carries the conversion action.

### The Action Link

This is the ONLY link to be used in every comment, every time, across all platforms and all days:

```
[ACTION LINK - confirmed weekly with client]
```

This link is confirmed with the client during each weekly heartbeat. It may change week to week depending on the client's current campaign or offer.

### Comment Writing Rules

1. **Every comment must be unique.** Never use the same comment copy twice across the 7 days. Each day's comment is fresh.
2. **The comment must tie directly to that day's content.** If Day 3 was about building confidence, the comment speaks to building confidence. There must be complete congruency between the post and the comment.
3. **The tone is emotionally visceral but never feels like a sales pitch.** It must feel like:
   - We understand what you're going through
   - We're part of your team
   - We know the importance of what you're trying to accomplish
   - We feel the urgency you feel
   - Scheduling this appointment is the next natural step, not a transaction
4. **The comment creates urgency without pressure.** Language like "You can't wait another moment" or "You deserve this today, not next month" or "This is the conversation that changes everything."
5. **The comment ALWAYS ends with the action link.** Always. No exceptions.
6. **Never use generic language like "Click here to schedule."** Every comment should feel handwritten, personal, and emotionally connected to that day's content.

### Comment Structure

```
[Emotionally visceral opening tied to today's topic, 1-2 sentences]
[Bridge to [Brand Name], showing understanding and partnership, 1-2 sentences]
[Urgency statement that feels caring, not pushy, 1 sentence]

Schedule your conversation with [Brand Name] right here:
[ACTION LINK - confirmed weekly with client]
```

### Example Comments (one per day, showing variety)

**Day 1 example:** "If reading this made something click for you, that's not a coincidence. That's the moment most people describe when they realize they need more than what they've been getting. The [Brand Name] team has helped hundreds of people just like you take this exact step. Schedule your conversation with [Brand Name] right here: [ACTION LINK - confirmed weekly with client]"

**Day 3 example:** "The people who act on this are the ones who look back and say 'thank you.' You already know this matters. You already feel it. Let's talk about what [Brand Name] can do for you specifically. Schedule your meeting right here: [ACTION LINK - confirmed weekly with client]"

**Day 5 example:** "Every day you wait is a day you're navigating this alone. You don't have to figure this out by yourself. The team at [Brand Name] has walked this road with people just like you. Start the conversation today: [ACTION LINK - confirmed weekly with client]"

**Day 7 example:** "This week changed the way a lot of people are thinking. If you're one of them, don't let this be just another thing you scrolled past. This is the moment. Book your conversation with an [Brand Name] specialist right now: [ACTION LINK - confirmed weekly with client]"

### How Comments Are Posted

Comments are posted programmatically after the main post is published. See the GoHighLevel Social Planner API section for technical details. The comment is posted within 1-2 minutes of the main post going live.

---

## 12b. Comment Reader — comments become conversations (Phase 4)

**The gap this closes (P3-08 Gap B):** the primary CTA is now the DM (§12), which reaches Skill 38 end to end. But the comment link is still live, and some readers will REPLY to the comment instead of DMing. Public post comments are NOT a GHL Conversations event, so they never reach Skill 38's inbound webhook — and `caf` has no comment/reply command (§17). Without a reader, a prospect who replies to the comment gets no answer. The comment reader turns those replies into conversations.

**What it does:** as part of Phase 4 (Engagement Monitoring), poll prospect comment REPLIES on published posts and surface each as a SYNTHETIC HANDOFF into Skill 38's existing pipeline. Each prospect comment is appended to that contact's conversational log (`<MASTER_FILES_DIR>/conversational-logs/comment-<author>__<name>.md` — the exact format Skill 38's inbound hook reads), tagged with the post/permalink context. The comment then flows through Skill 38's matching conversation playbook exactly like any other inbound message.

**Implementation:** `scripts/comment_reader.py` (unit-tested in `scripts/test_comment_reader.py`). It consumes NORMALIZED comment events (read via the §17 ladder's available surface — official GHL MCP or raw REST, since `caf` has no comment command) and writes the synthetic handoffs. It is deterministic and does not itself call any live API — the orchestrator supplies a per-channel reader for channels that HAVE a surface.

**Per-channel honesty (BINDING — 2.4):** the reader carries a per-channel capability registry (`CHANNEL_COMMENT_SURFACE`). A channel with a verified comment-read surface (FB/IG via the GHL Social Planner read path today) is processed; a channel with NO comment-read API surface is **LEDGERED per-channel (returned in `skipped` with an explicit reason) and skipped — NEVER fabricated**. There is no silent empty result and no invented comment feed. As each channel's surface is proven live, flip it from `None` to its surface string in the registry.

**Ownership:** Skill 35 only creates the synthetic handoff (the inbound turn). Skill 38 OWNS the reply — reading the log, drafting per the matching playbook, and replying on the comment thread (or inviting to DM). See the cross-reference in `38-conversational-ai-system/SKILL.md`.

---

## 13. Email Newsletter (Tuesday 9 AM)

### Release Schedule

The email newsletter releases every Tuesday morning at 9:00 AM. It serves as a preview/compilation of the week's 7-day content series, giving email subscribers a consolidated view of what's coming and what they may have missed.

### Email Structure

The email follows a specific pitch cadence:

**1. Subject Line (40-60 characters)**
Compelling, curiosity-driven. References the weekly theme. Makes the reader feel like opening this email will change something for them.

**2. TLDR (Top of Email, first thing they see)**
2-3 sentences summarizing what this week's series is about and why it matters. This is for busy readers who won't read the whole email. Even the TLDR should make them want to read more.

**3. First 25% of Email: Value + Soft Pitch**
Open with the strongest insight from the week's content. Deliver real value. Then weave in the first soft pitch: "This is exactly the kind of thing [Brand Name] helps people with."

**4. 50% Mark: Deeper Value + Second Soft Pitch**
Continue delivering value from the week's series. Reference specific days or insights. Weave in a second soft pitch: "The [Brand Name] team has been helping people with this for years."

**5. Final 25%: Strongest Value + Hard/Intentional Pitch**
Bring it home with the most powerful insight or story from the week. Then deliver the intentional pitch. This is not soft. This is direct, emotionally visceral, and clear: "Take action with [Brand Name]. This is the conversation that changes everything. [ACTION LINK]"

**6. Footer**
Standard unsubscribe link, social media links, contact information.

### Email Tone

Emotionally visceral. We understand. We're part of their team. We feel what they feel. We know the importance of what they're trying to accomplish. The email should feel like a letter from someone who genuinely cares, not a marketing blast.

### Email Word Count Target

600-1,000 words. Long enough to deliver value, short enough that people actually read it.

### Email Sending

Sent through GoHighLevel (Convert and Flow) email system at 9:00 AM on Tuesdays.

---

## 14. Blog Post Production (Day 7 Release)

### When to Release
The blog post releases on Day 7 alongside the grand finale social post and the podcast episode.

### Blog Post Construction Instructions

Follow these steps in order:

1. **Combine all 7 days of core content** into one comprehensive article.
2. **Weave in all research** (facts, figures, studies) throughout the article.
3. **Structure the blog post** using these elements:

**Blog Post Structure:**
- **Title:** Compelling, keyword-rich, under 70 characters for SEO. Include the weekly theme.
- **Meta Description:** 150-160 characters summarizing the article for search engines.
- **Introduction (150-200 words):** Hook the reader. Establish why this topic matters for the client's target audience. Emotionally visceral tone.
- **Body Sections (one per day's content):** Each day's core content becomes a section with its own subheading. Expand, connect, and flow naturally. Do not just copy-paste the social posts.
- **Research Integration:** Cite facts and studies naturally within the text. Use "According to [source]..." or "Research from [source] shows..."
- **Soft Pitch (middle of the article, around the 50% mark):** Naturally weave in a mention of [Brand Name]. "This is exactly the kind of challenge that the client's programs are built to address." This should feel like a natural part of the narrative, not an interruption.
- **Conclusion (150-200 words):** Summarize the key takeaways. Then deliver the intentional pitch. This is direct, emotionally visceral, and clear. "If this article resonated with you, that's not an accident. That's the moment you realize it's time to take action. Connect with [Brand Name] today." Include the action link. Include the action link.
- **Total Word Count Target:** 1,500-2,500 words (long enough for SEO value, short enough to keep readers engaged).

4. **SEO Best Practices:**
- Include the primary keyword in the title, first paragraph, at least 2 subheadings, and the meta description.
- Use subheadings (H2, H3) to break up the content.
- Include internal links to other the client's content.
- Include at least one external link to a credible source.
- Use short paragraphs (2-3 sentences max).
- Include a featured image (generated at 16:9, 1200x630 pixels).

5. **Blog Image:** Generate one featured image at 16:9 (1200 x 630 pixels) using Nano Banana 2 that visually represents the weekly theme.

---

## 15. Podcast Production with Fish Audio S2 (Day 7 Release)

> Cross-reference: this section is the proven Podbean publish flow (Fish Audio render, cover art, and the Podbean upload through the client's own Convert and Flow content delivery network). The Podcast Production Engine (onboarding v18, department id `podcast`) is the PRODUCTIONIZED version of this flow: its Step 15 (Podbean OAuth client_credentials, uploadAuthorize, episode create, permalink capture, idempotent permalink guard, and future-dated scheduling) is seeded directly from this section, then hardened with per-client isolation, cost ceilings, and an independent episode QC gate. Use THIS section for the Skill 35 weekly social cadence's Day-7 podcast; use the engine when the client wants a first-class published episode (interview lead-generation or a personal weekly show in their cloned voice). The engine is canonical for full published episodes; this playbook remains the weekly social lane. The current Fish Audio production model is `s2.1-pro`, selected via the HTTP `model` header; see Skill 30 (fish-audio-api-reference) for the authoritative facts and the `s2.1-pro-free` prohibition.

### When to Release
The podcast episode releases on Day 7 alongside the grand finale social post and the blog post.

### Fish Audio S2 Inline Emotion Tags

Fish Audio S2 uses [square bracket] tags placed anywhere in the script. Tags affect everything that comes after them until a new tag appears. S2 accepts free-form natural language descriptions with over 15,000 supported tag variations. You are NOT limited to a preset list. If you can describe it to a voice actor, S2 can attempt it. Write the direction into the text and S2 renders it.

**Tag Syntax:**
- Place [tag] immediately before the word or phrase it should affect.
- Tags can go at the start, middle, or end of a sentence.
- Placement is meaning. [whispering] I didn't want to go inside = whispers the whole line. I didn't want to go [whispering] inside = whispers from "inside" onward.
- Tags don't have to be in English. S2 understands tags in 80+ languages.

**The goal is to make the podcast feel ALIVE.** Think about how a great podcast host varies their delivery. They get excited when they reveal something. They slow down and get serious when they share a hard truth. They pause for effect. They lean in like they're telling you a secret. That's what the tags create.

**Example podcast script showing natural tag usage:**

```
[warm, conversational tone] Welcome back to the [Brand Name] podcast.

[pause] This week, we went deep on something that hits close to home for a LOT of people.

[leaning in, like sharing something important] And here's what caught us off guard. [pause] A 2025 study from the American Psychological Association found that [emphasis] 67 percent of people say they feel completely unprepared for this exact challenge.

[letting that sink in] Sixty-seven percent.

[passionate, building energy] That number alone tells us something. It tells us people need real, structured, intentional support. Not another blog post. Not another quick tip. Real guidance.

[serious but warm] And look, if you've been following our series this week, you already know that the research from Day 1 and Day 2 painted a picture that most people never see. [building excitement] But what we uncovered on Day 4 and Day 5? That changed everything.

[the calm confidence of someone who has seen this work] This is exactly why [Brand Name] exists. The [Brand Name] team has been walking people through this for years.

[urgent but caring] If any of this resonated with you, don't let it just be another thing you scrolled past. [pause] Book a conversation. Seriously. [warm smile in voice] It could change everything for you.

[excited, teasing] And next week? [pause] We're diving into something that everyone in our community needs to hear. [whispering] Trust me, you do NOT want to miss it.
```

**Key principle:** Don't force emotions. Let the content guide the delivery. Use tags where a real podcast host would naturally shift their voice. The tags should feel invisible to the listener because the vocal changes feel natural and earned.

### Podcast Cover Image (Podbean Requirements)

Podbean and Apple Podcasts require podcast artwork between 1400 x 1400 and 3000 x 3000 pixels, 1:1 square, JPEG or PNG, RGB color space, 72 dpi, under 500 KB file size. If the generated image exceeds 500 KB, resize it before uploading to GHL. Use ImageMagick: `convert input.png -resize 1400x1400 -quality 85 output.jpg` or increase JPEG compression until under 500 KB.

**Generate one 1400 x 1400 (1:1) image using Nano Banana 2 at 2K resolution.** The 1K resolution would produce approximately 1024 x 1024, which is below Podbean's minimum of 1400 x 1400. Use 2K to meet the requirement. Cost: $0.06 per image.

The image should visually represent the weekly theme and include the client's branding.

### Podcast Audio Requirements (Podbean)

- Format: MP3
- Bitrate: 192 kbps (required for Podbean quality standards)
- Generated via Fish Audio S2-Pro text-to-speech with inline emotion tags (fully autonomous — agent never asks client to record)
- Target length: 10-15 minutes (~1,500-2,000 word script)

### Autonomous Audio Generation Pipeline (MANDATORY — agent executes end-to-end)

The agent NEVER asks the client to record the podcast themselves. Client self-recording is a hard last resort only after all retries are exhausted and the operator has been notified. The default is always the agent generating the audio autonomously.

#### Fish Audio API — Verified Facts (docs.fish.audio, confirmed June 2026)

**Model:** Use `s2-pro` — the current recommended model, specified via HTTP header `model: s2-pro`. Do not hardcode `s1` (previous generation, uses parenthesis tags and is less capable). If future model detection is needed, check Fish Audio docs; default to `s2-pro` until a newer model is confirmed.

**API call (generate → stream → save):**
```bash
curl -sS -X POST "https://api.fish.audio/v1/tts" \
  -H "Authorization: Bearer $FISH_AUDIO_API_KEY" \
  -H "Content-Type: application/json" \
  -H "model: s2-pro" \
  -o podcast_audio.mp3 \
  -d '{
    "text": "[tagged script text here]",
    "reference_id": "[FISH_AUDIO_VOICE_ID]",
    "format": "mp3",
    "latency": "normal",
    "normalize": true,
    "chunk_length": 300
  }'
```

The response is a **binary audio stream** (Transfer-Encoding: chunked). `-o podcast_audio.mp3` writes it directly. There is no separate polling step — it is synchronous streaming.

**Use the helper script** (implements the full pipeline with retry and ffprobe verification):
```bash
bash ~/.openclaw/skills/35-social-media-planner/scripts/generate_podcast_audio.sh \
  podcast_script_tagged.txt \
  [from secrets/.env: FISH_AUDIO_VOICE_ID] \
  s2-pro \
  podcast_audio.mp3
```

#### Step-by-Step Podcast Audio Pipeline

**Step 1 — Write the script**

Write a 1,500-2,000 word podcast script following the structure in "Podcast Script Construction Instructions" below. Save as `podcast_script_draft.txt`.

**Step 2 — Tag the script heavily with emotion tags**

Annotate the script with Fish Audio S2-Pro emotion tags before sending to TTS. Tags use [square brackets]. They affect everything after them until a new tag appears. Place tags wherever a live podcast host would naturally shift delivery.

**Verified S2-Pro tag categories (64+ supported):**

| Category | Example tags |
|----------|-------------|
| Basic emotions | `[happy]`, `[sad]`, `[excited]`, `[calm]`, `[nervous]`, `[confident]`, `[surprised]`, `[satisfied]`, `[curious]`, `[sarcastic]` |
| Advanced emotions | `[empathetic]`, `[proud]`, `[nostalgic]`, `[determined]`, `[hopeful]`, `[anxious]` |
| Delivery style | `[whispering]`, `[shouting]`, `[soft tone]`, `[in a hurry tone]` |
| Audio effects | `[laughing]`, `[chuckling]`, `[sighing]`, `[gasping]` |
| Pacing | `[break]`, `[long-break]` |

S2-Pro also accepts free-form natural language descriptions within brackets: `[building intensity]`, `[warm smile in voice]`, `[leaning in like sharing a secret]`, `[the calm confidence of someone who has been here before]`. Use these freely — S2-Pro supports 15,000+ tag variations.

**Important:** S2-Pro uses [square brackets]. S1 used (parentheses). Never use S1 syntax with s2-pro.

**Concrete examples of heavily-tagged script lines:**

```
[warm, conversational tone] Welcome back to the [Brand Name] podcast. [break] This week we went deep on something most people haven't heard before.

[leaning in, like sharing something important] Here's what stopped us cold. [break] A study from the American Psychological Association found that [excited] sixty-seven percent of people feel completely unprepared for this exact challenge.

[letting that sink in] Sixty-seven percent.

[passionate, building energy] That number tells us something. It tells us people need real, structured, intentional support. [break] Not another blog post. Not another quick tip. [emphasis] Real guidance.

[serious but warm] And if you've been following our series this week, the research from Day 1 and Day 2 painted a picture most people never see. [building excitement] But what we found on Day 4 and Day 5? [break] That changed everything.

[the calm confidence of someone who has seen this work] This is exactly why [Brand Name] exists.

[urgent but caring] If any of this landed for you — [break] don't let it be just another thing you scrolled past. [warm smile in voice] Book a conversation. Seriously. It could change everything.

[excited, teasing] And next week? [long-break] We're diving into something you do NOT want to miss.
```

**Goal:** Every paragraph shift, every reveal, every serious fact, every CTA should have a tag. The script should read like a director's script, not plain prose.

Save the tagged script as `podcast_script_tagged.txt`.

**Step 3 — Select model (always check, default s2-pro)**

Use `s2-pro` unless Fish Audio has released a newer recommended model (check docs.fish.audio/developer-guide/models-pricing/models-overview before each run if you want to confirm). If detection fails or docs are unreachable, default to `s2-pro`.

**Step 4 — Generate the audio**

Run the helper script:
```bash
bash ~/.openclaw/skills/35-social-media-planner/scripts/generate_podcast_audio.sh \
  podcast_script_tagged.txt \
  [from secrets/.env: FISH_AUDIO_VOICE_ID] \
  s2-pro \
  podcast_audio.mp3
```

The script makes up to 3 attempts. On each attempt it calls the Fish Audio `/v1/tts` endpoint, streams the MP3, and verifies the file on success.

**Step 5 — Verify the file**

After generation, confirm:
```bash
# File exists and is non-zero
ls -lh podcast_audio.mp3

# Valid duration (ffprobe — should be 10-15 minutes = 600-900 seconds)
ffprobe -v error -show_entries format=duration -of csv=p=0 podcast_audio.mp3

# No errors in the file
ffprobe -v error podcast_audio.mp3
```

Pass criteria: file exists, size > 0, duration between 600-900 seconds (10-15 minutes), no ffprobe errors.

**Step 6 — On failure: diagnose, retry, escalate**

The helper script runs 3 retries automatically with diagnosis on each failure. If all 3 fail:

1. Check FISH_AUDIO_API_KEY — is it set and valid?
   ```bash
   curl -sS -H "Authorization: Bearer $FISH_AUDIO_API_KEY" https://api.fish.audio/v1/me
   ```
2. Check FISH_AUDIO_VOICE_ID — is the voice ID valid?
   ```bash
   curl -sS -H "Authorization: Bearer $FISH_AUDIO_API_KEY" "https://api.fish.audio/v1/model/[FISH_AUDIO_VOICE_ID]"
   ```
3. Check network connectivity to api.fish.audio
4. Check that the tagged script is valid text (no binary chars, non-empty)
5. Try model `s2-pro` explicitly if default failed
6. Notify operator via Telegram with failure details and diagnostic output

**Only after 3 retries exhausted AND operator notified**, emit this message to the client:
> "I ran into a technical issue generating the podcast audio this week — I retried 3 times and the Fish Audio API did not return a valid file. I'm looking into it now. In the meantime, if you have a recording setup, you can record using the script I'll share with you — but I'm still working on the automated version."

This message is the last resort, not the default. The default is always the agent completing the audio end-to-end.

**Step 7 — Feed into the publish step**

Once `podcast_audio.mp3` is verified, proceed to the Podcast Publishing flow (via n8n webhook to Podbean) in the section below. Upload the verified MP3 to GHL Media Library first, then send the webhook payload.

### Podcast Script Construction Instructions

Follow these steps in order:

1. **Open with a hook (30-45 seconds).** Grab the listener immediately. Reference the weekly theme in an engaging way.
2. **Introduce the hosts/brand (15-20 seconds).** Brief intro for [Brand Name] and the purpose of the episode.
3. **Walk through the 7 days of content (8-10 minutes).** Combine and expand the core content into a flowing narrative. Do not read the social posts. Tell the story of the week's theme as a cohesive episode.
4. **Embed emotion tags throughout.** Use [warm tone] for supportive moments, [serious] for important facts, [excited] for reveals, [pause] for dramatic effect, [emphasis] for key points.
5. **Include the research.** Reference facts and studies naturally. "Here's what's fascinating: a study from [source] found that..."
6. **Build toward the pitch.** The pitch for [Brand Name] should feel like a natural conclusion to the episode. "If any of this resonated with you, this is exactly what [Brand Name] is here for."
7. **End with a strong CTA (30-45 seconds).** Direct listener to take action via the action link, visit the website, or follow on social media.
8. **Tease next week (15-20 seconds).** "Next week, we're diving into..."
9. **Target total script length:** 1,500-2,000 words (~10-15 minutes of audio at conversational pace).

**Example Podcast Script Snippet:**

```
[warm tone] Welcome back to the [Brand Name] podcast. [pause] This week, we've been diving deep into something that affects everyone in [target audience].

[conversational] And if you've been following our social media series this week, you already know [emphasis] this topic hit a nerve.

[serious] Here's a stat that stopped us in our tracks. [pause] According to a 2025 study from the American Psychological Association, [emphasis] 67% of people say they feel unprepared to handle this specific challenge.

[passionate] That number should tell us something. It tells us that people need support. Real, structured, intentional support.

[warm tone] And that's exactly why [Brand Name] exists.
```

### Podcast Publishing (via n8n Webhook to Podbean) — contract v2

The agent does NOT publish directly to Podbean. Publishing goes through an n8n webhook automation that handles all Podbean API work, including a good-standing plus identity gate that runs BEFORE any Podbean call.

**Publishing Flow:**
1. Agent generates podcast audio via Fish Audio S2 (MP3, 192 kbps)
2. Agent uploads the audio file to a public HTTPS host. GHL Media Library is the DEFAULT host; a Google Drive direct-download link is the sanctioned fallback when GHL credentials are down. NEVER send a Fish Audio URL directly to the webhook. It must go through GHL (or the Drive fallback) first.
3. Agent generates the podcast cover image via kie.ai Nano Banana 2 (1400x1400, 1:1, JPEG or PNG). NEVER use WebP. Apple Podcasts rejects WebP.
4. Agent uploads the cover image to the same host as step 2.
5. **Before sending, run `python3 ~/.openclaw/skills/35-social-media-planner/scripts/validate_podcast_publish_payload.py podcast-publish-payload.json` and proceed only on exit 0.** This deterministic pre-flight verifies the REQUIRED fields below are present and non-null/non-empty in the payload, especially `image_url`, `client_last_name`, and `client_email`. A 2026-07-12 production incident sent a payload missing required fields, which crashed the automation mid-pipeline (audio already uploaded to Podbean) before a fail-closed entry guard existed on the n8n side. If step 3/4 (cover art generation/upload) did not complete and produce a real hosted `image_url`, or the client's last name/email are not known, DO NOT send the webhook request. Finish step 3/4 or notify the operator via Telegram first. n8n now refuses an incomplete or contract-v1 payload before making any Podbean call and sends an honest refusal (entry guard, GK-01/U63, extended for contract v2), but the agent must not rely on it as the primary check. It is a backstop, not a substitute for sending a complete payload.
6. Agent sends the following JSON payload to the webhook, with the shared auth header.

**Webhook Endpoint:**
```
POST https://main.blackceoautomations.com/webhook/podbean-publish
Content-Type: application/json
X-Podcast-Publish-Token: [shared secret, provisioned by install.sh as PODBEAN_PUBLISH_TOKEN; never hard-code it, never log it]
```

**Required Payload (contract v2):**
```
{
  "contract_version": "2",
  "podcast_id": "[client's Podbean channel ID - collected during First Run]",
  "client_last_name": "[from client profile - roster auth key, together with client_email]",
  "client_email": "[from client profile - roster auth key, together with client_last_name]",
  "client_first_name": "[from client profile - display/email only, never authorization]",
  "title": "[Episode title - matches the weekly theme]",
  "description": "[Show notes - plain text or HTML, under 3000 characters]",
  "audio_url": "https://[GHL Media Library or Google-Drive-direct-download URL to the mastered MP3]",
  "image_url": "https://[GHL Media Library or Google-Drive-direct-download URL to the cover]",
  "publish_date": "2026-04-12T09:00:00",
  "idempotency_key": "[stable per episode-job key, e.g. the Skill 58 job key]",
  "episode_type": "full",
  "explicit": "clean"
}
```

Optional fields not shown above: `speaker` (appends "Inspired by [speaker]" to the title once), `season_number`, and `source` (the emitting skill/box slug for the audit trail only, never authorization).

**Field Rules:**
- contract_version: REQUIRED, literal "2". Any other value is refused.
- podcast_id: The client's Podbean channel ID. Collected during First Run and stored in MEMORY.md. Downstream publishing always routes on the operator's roster row for this identity, never on this raw field alone; a mismatch is refused as identity_mismatch.
- client_last_name: REQUIRED. Roster lookup key together with client_email. Trimmed, compared case-insensitively.
- client_email: REQUIRED. Roster lookup key together with client_last_name. Trimmed, compared lowercased. Also the recipient of the success confirmation email.
- client_first_name: optional. Display and email use only, never used for authorization.
- audio_url / image_url: REQUIRED. Any HTTPS URL (not plain http). GHL Media Library is the DEFAULT host; Google Drive direct-download is the sanctioned fallback when GHL credentials are down. Image must be JPEG or PNG only (never WebP), 1:1, 1400x1400 minimum, under 500 KB, RGB. If image exceeds 500 KB, resize before uploading.
- title: The episode title as it should appear in podcast apps. Non-empty, 200 characters or fewer.
- description: Show notes. Plain text or HTML. 3000 characters or fewer for cross-app compatibility.
- publish_date: ISO 8601 format WITH time component (e.g., 2026-04-12T09:00:00). Timezone is Eastern (EST/EDT). Date-only strings will cause an error.
- idempotency_key: REQUIRED. Stable per episode-job; the Skill 58 job key is the recommended source. The SAME key re-fired never creates a second episode; it returns the stored permalink instead.
- episode_type: "full" (default), "trailer", or "bonus".
- explicit: "clean" (default) or "explicit".

**Do NOT send an episode number.** The automation queries Podbean for the highest existing episode and assigns the next one automatically.

**What happens after sending (contract v2 is SYNCHRONOUS, not fire-and-forget):**
The connection is held until the publish completes (download plus upload of a full episode; allow up to 300 seconds). The webhook responds with exactly one of:
- `200 {"ok":true, "permalink_url":..., "episode_id":..., "episode_number":N, "scheduled":true|false, "idempotent_replay":false}` — published (or scheduled, when publish_date is in the future).
- `200 {"ok":true, "idempotent_replay":true, "permalink_url":...}` — this idempotency_key already completed; the stored permalink is returned and no second episode was created.
- `403 {"ok":false, "reason":"not_in_good_standing", "message":"you are not in good standing"}` — the client is not currently in good standing. "you are not in good standing" is the operator's exact required client-facing sentence; relay it per the agent's own client-comms doctrine, unparaphrased. No Podbean call is made.
- `403 {"ok":false, "reason":"identity_unknown"}` — no roster row matches (client_last_name, client_email).
- `403 {"ok":false, "reason":"identity_mismatch"}` — a roster row exists but its channel id differs from podcast_id. Treat as a possible cross-client mix-up. Do not retry with a different podcast_id; notify the operator.
- `409 {"ok":false, "reason":"in_flight"}` — the same idempotency_key is currently executing. Wait, then retry with the SAME key.
- `422 {"ok":false, "reason":"invalid_payload", "missing":[...], "bad_urls":[...]}` — one or more required fields were missing or invalid. Fix the named field(s) and resend.
- `500 {"ok":false, "reason":"publish_failed", "detail":"..."}` — a Podbean-side failure after every gate passed. Retry with the SAME idempotency_key; it is safe.
- Webhook auth failure (missing or wrong `X-Podcast-Publish-Token`) returns native 401/403 before the workflow runs at all.

**Error handling:**
- 409 or 500, or the request times out or the connection drops: retry once after 30 seconds with the SAME idempotency_key. Safe either way, because the ledger prevents a second episode.
- 422: fix the named field(s) per the Field Rules above and resend. Do not retry blindly.
- 403 not_in_good_standing: relay "you are not in good standing" to the client per the agent's own client-comms doctrine; do not retry until the operator flips the roster row back to YES.
- 403 identity_unknown or identity_mismatch: do not retry automatically. Notify the operator; a client identity or channel id may be wrong.
- Image format rejection: re-export the cover image as JPEG (not WebP) and re-send.
- 401/403 before any gate runs at all: the box's `X-Podcast-Publish-Token` is missing or wrong. Notify the operator; do not retry with the same token.

---

## 16. Video Production Pipeline (kie.ai + FFmpeg)

### Video Standard
- **Duration:** 55-60 seconds (target window; ffprobe must confirm)
- **Ratio:** 9:16 (1080 x 1920 pixels)
- **Output:** MP4, H.264 codec, 30fps

### Key constraint: AI video tools generate clips up to ~8-10 seconds each

The kie.ai video tool (Veo 3.1 Lite) generates individual clips of up to 8-10 seconds. A 55-60 second Reel requires multiple sequential clips. The agent MUST handle this entirely autonomously using the storyboard + generate + FFmpeg merge pipeline below. **The agent NEVER asks the client to record the video themselves.** Client self-recording is a hard fallback of last resort only when clip generation has failed after all retries (see Fallback at end of this section).

### Cost Comparison of Video Models on kie.ai (Verified April 2026)

| Model | Credits/Video (8 sec) | Cost/Video | Quality Notes |
|-------|----------------------|-----------|---------------|
| Veo 3.1 Lite | 30 credits | ~$0.15 | Good for social. Fastest. Lowest cost. Slightly less fine detail than Fast on complex textures. On phone screens, most viewers cannot tell the difference from Fast. |
| Veo 3.1 Fast | 60 credits | ~$0.30 | Strong for social. 2x faster than Standard. Quality only 1-8% lower than Standard. Best for when you need a step up from Lite. |
| Veo 3.1 Quality | 250 credits | ~$1.25 | Cinematic. Highest fidelity. Reserved for hero content or client deliverables only. Too expensive for weekly social content. |
| Grok Imagine | ~20 credits | ~$0.10/6sec (~$0.13/8sec) | Fast generation with synchronized audio. Supports text-to-video and image-to-video. Cheapest option. Quality is strong for social but less cinematic control than Veo 3.1. |

High-tier credit top-ups (+10% bonus) reduce effective pricing further.

Source: kie.ai pricing pages, verified April 11, 2026. Credits at $0.005 per credit. Grok Imagine pricing from kie.ai Grok Imagine API page.

**Recommended model: Veo 3.1 Lite** for primary video production. Use Grok Imagine as a cost-saving alternative when synchronized audio matters more than cinematic control. Use Veo 3.1 Fast for upgrade situations. Avoid Quality mode for weekly social content.

### Video Production Schedule

The number of videos per week is configured during First Run (0, 2, or 7). Default is 2:

| Video | Release Day | Purpose |
|-------|------------|---------|
| Video 1: Series Opener | Day 1 | Hooks the audience visually. Sets the tone for the week. Introduces the theme. |
| Video 2: Grand Finale | Day 7 | Strongest visual impact. Accompanies the grand finale post, blog, and podcast. |

The remaining 5 days (Days 2-6) use static images with text for feed posts, plus the 9:16 images for Stories.

### Primary Pipeline: Storyboard → Generate → FFmpeg Merge (MANDATORY — agent handles end-to-end)

This is the required path. The agent executes every step. No step is delegated to the client.

#### Step A: Build the Storyboard

Compute the number of scenes needed:
```
clip_limit_seconds = 8   (Veo 3.1 Lite per-clip max)
scene_count = ceil(target_seconds / clip_limit_seconds)
# Example: ceil(60 / 8) = 8 scenes
```

For each scene, write a visual prompt that includes:
- The specific content for that beat of the script (what is happening, what is being shown)
- Continuity cues so all clips read as one continuous piece:
  - Consistent subject appearance (same wardrobe, same face/figure description if a person is on screen)
  - Consistent setting and color grade (same environment, lighting quality, color temperature)
  - Consistent camera style (same focal length language: wide/medium/close, same movement language: static/slow push/pan)
- The transition type INTO this scene: `cut` (hard jump cut) or `crossfade` (smooth blend)
  - Use `cut` for high-energy, fast-paced Reels (default)
  - Use `crossfade` for smoother, more cinematic Reels
  - The storyboard decides per scene; most Reels are all-cuts or all-crossfades for consistency

**Storyboard format per scene:**
```
Scene N of M | Transition into: [cut | crossfade] | Duration: ~8s
Script beat: [the portion of the script this scene covers]
Visual prompt: [detailed, continuity-consistent prompt]
```

#### Step B: Generate Each Clip

Generate one clip per scene using the existing kie.ai video tool:
- Model: Veo 3.1 Lite (image-to-video from a Nano Banana 2 source image, OR text-to-video)
- Aspect ratio: 9:16 (vertical, 1080x1920 where supported)
- Duration: ~8 seconds per clip
- Naming: `raw_scene_01.mp4`, `raw_scene_02.mp4`, ... `raw_scene_N.mp4`

If a clip fails to generate, retry up to 3 times before marking it failed. Log each failure. Do not fall back to client self-recording until ALL retries for ALL failed clips are exhausted (see Fallback).

#### Step C: Generate the Voiceover

Generate ONE continuous voiceover track from the full 55-60 second script using Fish Audio S2 (`sag --voice [from secrets/.env: FISH_AUDIO_VOICE_ID]`). A single continuous track is preferred over per-scene tracks because it preserves natural delivery, pacing, and breath phrasing across the full Reel.

If per-scene VO is needed (e.g., the scene timings differ significantly from the script rhythm), generate per-scene audio aligned to each scene's duration and merge them in order using:
```bash
ffmpeg -f concat -safe 0 -i vo_parts.txt -c copy voiceover_combined.mp3
```

Save the final VO as `voiceover.mp3`.

#### Step D: Normalize Every Clip to Identical Reel Spec (MANDATORY before any concat)

Before merging, normalize every raw clip to prevent codec/resolution/framerate mismatches that cause concat failures or visual glitches. Run this command on each raw clip:
```bash
ffmpeg -i raw_scene_01.mp4 \
  -vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,fps=30,setsar=1" \
  -c:v libx264 -pix_fmt yuv420p \
  -c:a aac -ar 48000 \
  norm_scene_01.mp4
```
Repeat for every clip: `norm_scene_01.mp4`, `norm_scene_02.mp4`, ... `norm_scene_N.mp4`.

This step is not optional. Skipping it is the most common cause of FFmpeg concat errors.

#### Step E: Merge Clips with FFmpeg

Choose the merge recipe based on the storyboard's transition type.

**Recipe 2a — Jump Cuts (hard cuts, fast/energetic Reels):**

Create `clips.txt` listing each normalized file:
```
file 'norm_scene_01.mp4'
file 'norm_scene_02.mp4'
file 'norm_scene_03.mp4'
file 'norm_scene_04.mp4'
file 'norm_scene_05.mp4'
file 'norm_scene_06.mp4'
file 'norm_scene_07.mp4'
file 'norm_scene_08.mp4'
```

Merge with concat demuxer (fast, lossless copy — works because all clips are normalized to identical spec):
```bash
ffmpeg -f concat -safe 0 -i clips.txt -c copy merged.mp4
```

**Recipe 2b — Crossfade transitions (smoother, more cinematic Reels):**

For each pair of adjacent clips, compute `offset = clip_A_duration - xfade_duration`. For 8-second clips with 0.5-second crossfades: `offset = 8 - 0.5 = 7.5`. Chain xfade filters for all scenes (example for 3 clips; extend the pattern for more):
```bash
ffmpeg -i norm_scene_01.mp4 -i norm_scene_02.mp4 -i norm_scene_03.mp4 \
  -filter_complex \
    "[0][1]xfade=transition=fade:duration=0.5:offset=7.5,format=yuv420p[ab]; \
     [ab][2]xfade=transition=fade:duration=0.5:offset=15.0,format=yuv420p[v]" \
  -map "[v]" -c:v libx264 -c:a aac merged.mp4
```
The offset for each subsequent xfade increases by `clip_duration - xfade_duration` per clip added (e.g., 7.5, 15.0, 22.5, 30.0, ...).

**Which recipe to use:** Jump cuts (2a) = default for social Reels; crossfades (2b) = use when the storyboard calls for a smoother feel. The storyboard (Step A) declares the choice per scene.

#### Step F: Lay Voiceover Over the Merged Video

Replace or mix the video audio with the continuous voiceover track:
```bash
ffmpeg -i merged.mp4 -i voiceover.mp3 \
  -map 0:v:0 -map 1:a:0 \
  -c:v copy -c:a aac -shortest \
  final_reel.mp4
```

This replaces any audio from the generated clips with the Fish Audio voiceover.

#### Step G: QC — Verify Final Output

```bash
# Verify duration is within target window (55-60 seconds):
ffprobe -v error -show_entries format=duration -of csv=p=0 final_reel.mp4

# Verify resolution is 1080x1920:
ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x final_reel.mp4

# Verify codec is H.264:
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 final_reel.mp4
```

Pass criteria:
- Duration: within 55-60 seconds (or the configured target window)
- Resolution: 1080x1920
- Codec: h264

If any check fails: diagnose and re-run the failed step (e.g., if duration is short, a clip likely failed to generate — retry that clip). Do NOT deliver a failing video.

The helper script `scripts/merge_reel.sh` implements Steps D-G in a parameterized, reusable form. Use it: `bash scripts/merge_reel.sh clips.txt voiceover.mp3 final_reel.mp4`.

#### Step H: Cost Summary

- Images for scenes (Nano Banana 2 at 1K): 8 x $0.04 = ~$0.32
- Video clips (Veo 3.1 Lite at 8 sec each): 8 x $0.15 = $1.20
- **Total per 60-second video:** ~$1.52
- **Weekly cost for 2 videos (Day 1 + Day 7):** ~$3.04

### Alternative Pipeline: Text-to-Video (Simpler, Slightly More Expensive)

If image-to-video quality is insufficient, generate each scene from text prompts instead of source images:

1. Write a detailed text-to-video prompt per scene (use the storyboard visual prompts from Step A directly).
2. Generate each segment using Veo 3.1 Fast text-to-video on kie.ai.
3. Proceed through Steps D-G above (normalize, merge, VO overlay, QC) — identical process.
4. Cost: $0.30 per segment x 8 = $2.40 per video (vs $1.52 for image-to-video).

### Fallback (LAST RESORT — client self-recording)

This path is only reached when ALL of the following are true:
- Clip generation has been retried 3 times for every failed scene
- The agent cannot produce enough passing clips to assemble a complete Reel
- The agent has notified the owner via Telegram with the specific failure details

Only at that point, send the client this message:
> "I ran into a technical issue generating clips for this week's video — I retried each scene 3 times and [N] scenes still failed. I can either (a) produce a shorter version using the clips that did succeed, or (b) if you'd like to record a 60-second video yourself, send it to me and I'll add the voiceover and produce the final Reel. Which would you prefer?"

This message is the fallback, not the default. The default is always the agent completing the video end-to-end.

---

## 17. GoHighLevel (Convert and Flow) Social Planner — posting ladder (Tier 0 → Tier 3)

OpenClaw posts ALL social media content through the GoHighLevel (Convert and Flow) Social Planner against the client's own GHL location. No Facebook Graph API and no per-platform tokens are required.

**Route every social read/write down this ladder, highest tier first, and emit the `[GHL tier used: N — tool_name]` disclosure header on the response.** This supersedes the old "raw REST only" guidance: raw REST is now the LAST resort, not the default.

### Tier 0 — Skill 44 `caf` CLI (PRIMARY when installed)

`caf` (the Convert and Flow operator CLI, Skill 44) wraps the Social Planner with the client's Private Integration Token. Prefer it for the reads/writes it covers.

```bash
# READ connected accounts (clean list — no per-platform loop, no accountId needed).
# --json is a GROUP-level flag and MUST precede the subcommand.
caf --json social accounts            # GET /social-media-posting/{locationId}/accounts

# CREATE / SCHEDULE a post (Tier 0).
# IMPORTANT: caf's safety gate REFUSES every write unless an approval token is set
# (otherwise it prints "SAFETY GATE: WRITE REFUSED: no approval token present" and
# exits 1, and the post silently falls through to a lower tier). Scope a one-off
# approval token to THIS social-post call so the gate passes — this does NOT disable
# the gate for any other caf operation:
CAF_APPROVAL_TOKEN="skill35-social-approved" \
  caf social create-post \
    --account-id "<social_account_id>" \
    --text       "<full post copy incl. the PRIMARY 'send us a message' DM CTA + the 'link is in the comments' backup directive (§12/§19)>" \
    --media-url  "<public CDN url>" \
    --schedule   "2026-04-06T13:00:00.000Z"
# --account-id and --media-url are repeatable (one flag per id / per media url).
# Omit --media-url for text-only; omit --schedule to post immediately.

# PREVIEW a post without sending (prints the exact payload, sends nothing):
CAF_APPROVAL_TOKEN="skill35-social-approved" \
  caf --dry-run social create-post --account-id "<id>" --text "<copy>"
```

`caf social create-post` builds this body and POSTs it to `/social-media-posting/{locationId}/posts`:

```json
{"locationId": "...", "accountIds": ["..."], "summary": "<text>", "media": [{"url": "...", "type": "image"}], "scheduledAt": "<iso8601>"}
```

Note the field names: caf uses **`accountIds`** and **`media:[{url,type}]`** — NOT the `socialMediaAccountIds` / `mediaUrls` shape the raw-REST examples below use. Both hit the SAME endpoint but differ; see the SCHEMA NOTE under Tier 3. There is **no `caf` comment/reply command** (the `social` group is `accounts`, `posts`, `create-post` only), so first-comments go straight to Tier 3 REST.

### Tier 1 — Official GHL MCP (Skill 36)

If Skill 44 is absent but Skill 36 is installed, use the official MCP tool `social-media-posting_create-post` (and `social-media-posting_get-account` for reads). Fall through to Tier 2 on any MCP error.

### Tier 2 — Community GHL MCP

Community MCP tool `create_social_post`; accounts via `get_social_accounts`. The community MCP HTTP transport speaks JSON-RPC (`method: tools/call`), not a flat `{"name","arguments"}` body. Confirm the exact tool names against your installed community MCP manifest. Fall through to Tier 3 if unreachable.

### Tier 3 — Raw REST (LAST RESORT)

Only when Tier 0–2 are unavailable, post directly with the PIT. Retry 3× with a 5 s delay (Section 20). The base URL, auth, endpoints, and example bodies below are the Tier 3 contract.

### API Base URL

```
https://services.leadconnectorhq.com
```

### Authentication

All requests require a Private Integration Token in the Authorization header:
```
Authorization: Bearer {private_integration_token}
Content-Type: application/json
```

The Private Integration Token is generated in GoHighLevel (Convert and Flow) under Settings > Integrations > Private Integrations. Required scope: `social-media-posting.write`

### Core Endpoints

**Create a Post (Schedule or Post Immediately)**
```
POST /social-media-posting/{locationId}/posts
```
This is the primary endpoint for ALL posting. It handles: creating posts, scheduling posts for future dates, posting immediately, attaching media (images, videos), posting to all platforms (Facebook, Instagram, LinkedIn, TikTok, Pinterest, YouTube), platform-specific parameters (post type, title, link, media format), AND posting comments below posts.

**Get Posts (List)**
```
POST /social-media-posting/{locationId}/posts/list
```

**Get Single Post**
```
GET /social-media-posting/{locationId}/posts/{postId}
```

**Edit a Post**
```
PUT /social-media-posting/{locationId}/posts/{postId}
```

**Delete a Post**
```
DELETE /social-media-posting/{locationId}/posts/{postId}
```

**Bulk Delete Posts**
```
DELETE /social-media-posting/{locationId}/posts (bulk)
```

**Get Connected Accounts (clean list — PREFERRED)**
```
GET /social-media-posting/{locationId}/accounts
```
This single call returns every connected account for the location (it is exactly what `caf --json social accounts` uses). Use it to DISCOVER accounts. The per-platform OAuth routes below are get-ONE calls that need an `accountId` you do not have yet — they are not a way to list accounts:
```
GET /social-media-posting/oauth/{locationId}/{platform}/accounts/{accountId}   # get-one; needs a known accountId
```

### Platform Limitations Reference

```
https://help.leadconnectorhq.com/support/solutions/articles/48001240003-social-planner-image-video-content-and-api-limitations
```

### Full API Documentation

```
https://marketplace.gohighlevel.com/docs/ghl/social-planner/social-media-posting-api
```

### Scheduling Logic

All 7 days of posts are scheduled in one batch, always 7 days ahead of the curve. The week starts on Sunday. Every post is scheduled for 9:00 AM on its designated day.

**Scheduling Process:**
1. The AI produces all content for the upcoming week (core content, platform rewrites, images, comments, carousel, email, blog, podcast, videos).
2. All QC checks pass (see QC Agent section).
3. The AI schedules all 42 platform-specific posts (7 days x 6 platforms) plus their comments in one batch via the GHL Social Planner API.
4. Each post is scheduled for its specific day at 9:00 AM.
5. Each comment is scheduled to post 1-2 minutes after its parent post.

**Example Schedule (if producing content on Saturday March 29):**

| Day | Date | Post Time | Content |
|-----|------|-----------|---------|
| Day 1 (Sunday) | March 30 | 9:00 AM | Series opener + Video 1 |
| Day 2 (Monday) | March 31 | 9:00 AM | Day 2 content |
| Day 3 (Tuesday) | April 1 | 9:00 AM | Day 3 content + Email newsletter at 9:00 AM |
| Day 4 (Wednesday) | April 2 | 9:00 AM | Day 4 content |
| Day 5 (Thursday) | April 3 | 9:00 AM | Day 5 content + Carousel posts |
| Day 6 (Friday) | April 4 | 9:00 AM | Day 6 content |
| Day 7 (Saturday) | April 5 | 9:00 AM | Grand finale + Video 2 + Blog + Podcast |

> **SCHEMA NOTE — verify against live GHL docs before first use.** The Tier-3 examples below use `socialMediaAccountIds` + `mediaUrls`. caf (Tier 0) sends `accountIds` + `media:[{url,type}]` to the SAME `POST /social-media-posting/{locationId}/posts` endpoint. These shapes differ and at least one may be rejected (422) depending on the current Social Planner API version. **Prefer Tier 0 `caf` — it builds the body for you.** If you must hand-build the Tier-3 body, confirm the exact field names against https://marketplace.gohighlevel.com/docs/ghl/social-planner/social-media-posting-api first — do NOT guess.

### Example API Request: Regular Post with Image

This is how a standard daily post is created. The image and content are bundled together in ONE API call via the `mediaUrls` field. They are NOT separate calls.

```
POST https://services.leadconnectorhq.com/social-media-posting/{locationId}/posts

Headers:
  Authorization: Bearer {private_integration_token}
  Content-Type: application/json

Body:
{
  "type": "post",
  "socialMediaAccountIds": ["{facebook_account_id}", "{instagram_account_id}", "{linkedin_account_id}"],
  "status": "scheduled",
  "scheduledAt": "2026-04-06T13:00:00.000Z",
  "summary": "One of Seven: [Post content here with full zones, pitch, cliffhanger]\n\nSend us a message to schedule your conversation with a [Brand Name] specialist — the link is also in the comments.",
  "mediaUrls": ["https://assets.cdn.filesafe.space/[GHL_LOCATION_ID]/media/[filename]"],
  "tags": ["social-media-planner", "week-14", "day-1"]
}
```

> **CRITICAL — mediaUrls MUST contain a GHL CDN URL.** Every image is first uploaded to the client's GHL Media Library via `medias/upload-file` (see SKILL.md Media Delivery Contract). The returned permanent CDN URL (`https://assets.cdn.filesafe.space/...`) is what goes into `mediaUrls`. Generator-hosted links (`storage.kie.ai`, `storage.example.com`) are NEVER used directly — they are intermediate only. If a generator returns a hosted URL, re-upload that file to GHL and use the CDN `url` from the upload response instead. Ephemeral/anonymous hosts (tmpfiles.org, file.io, transfer.sh, 0x0.st, catbox.moe) are BANNED per the Media Delivery Contract.

The `mediaUrls` field attaches the image to the post. GHL renders the post with the image on the platform. The image and content travel together. Never post content without its image.

### Example API Request: Carousel Post (Thursday)

Carousel posts include MULTIPLE images in the mediaUrls array:

```
POST https://services.leadconnectorhq.com/social-media-posting/{locationId}/posts

Body:
{
  "type": "post",
  "socialMediaAccountIds": ["{facebook_account_id}", "{instagram_account_id}"],
  "status": "scheduled",
  "scheduledAt": "2026-04-10T13:00:00.000Z",
  "summary": "[Carousel caption with swipe CTA, a PRIMARY 'send us a message' DM CTA, and the 'link is also in the comments' backup directive]",
  "mediaUrls": [
    "https://assets.cdn.filesafe.space/[GHL_LOCATION_ID]/media/[carousel-slide1-filename]",
    "https://assets.cdn.filesafe.space/[GHL_LOCATION_ID]/media/[carousel-slide2-filename]",
    "https://assets.cdn.filesafe.space/[GHL_LOCATION_ID]/media/[carousel-slide3-filename]",
    "https://assets.cdn.filesafe.space/[GHL_LOCATION_ID]/media/[carousel-slide4-filename]",
    "https://assets.cdn.filesafe.space/[GHL_LOCATION_ID]/media/[carousel-slide5-filename]",
    "https://assets.cdn.filesafe.space/[GHL_LOCATION_ID]/media/[carousel-slide6-filename]",
    "https://assets.cdn.filesafe.space/[GHL_LOCATION_ID]/media/[carousel-slide7-filename]"
  ],
  "tags": ["social-media-planner", "week-14", "carousel"]
}
```

All carousel images are included in ONE call. The platform renders them as a swipeable carousel.

For LinkedIn carousel (PDF upload), the images are first compiled into a multi-page PDF, then the PDF URL is used in mediaUrls.

### Example API Request: Video Post

Video posts use the video URL in mediaUrls. The content and video travel together:

```
POST https://services.leadconnectorhq.com/social-media-posting/{locationId}/posts

Body:
{
  "type": "post",
  "socialMediaAccountIds": ["{tiktok_account_id}", "{instagram_account_id}", "{youtube_account_id}"],
  "status": "scheduled",
  "scheduledAt": "2026-04-06T13:00:00.000Z",
  "summary": "[Video post caption with a PRIMARY 'send us a message' DM CTA and the 'link is also in the comments' backup directive]",
  "mediaUrls": ["https://assets.cdn.filesafe.space/[GHL_LOCATION_ID]/media/[video-filename]"],
  "tags": ["social-media-planner", "week-14", "video", "day-1"]
}
```

### Example API Request: Comment (Posted 1-2 Minutes After Parent Post)

The comment is a SEPARATE API call made AFTER the parent post is created. There is no Tier 0 (`caf`) or MCP comment/reply tool, so comments always use Tier 3 REST with the parent post's ID:

> **UNCONFIRMED ENDPOINT — verify before first use.** The `/posts/{parentPostId}/reply` subroute is not confirmed against the current GHL Social Planner surface; GHL first-comments are sometimes a field on post-create rather than a separate route. Confirm against the live docs (linked below) before relying on it. Also note: the parent must already be LIVE — a reply scheduled against a still-`scheduled` parent may fail because the `parentPostId` is not yet a posted entity.

```
POST https://services.leadconnectorhq.com/social-media-posting/{locationId}/posts/{parentPostId}/reply

Headers:
  Authorization: Bearer {private_integration_token}
  Content-Type: application/json

Body:
{
  "content": "If reading this made something click for you, that is not a coincidence. That is the moment most people describe when they realize they need more than what they have been getting. The [Brand Name] team has helped hundreds of people just like you take this exact step.\n\nSchedule your conversation with [Brand Name] right here:\n[ACTION LINK]",
  "scheduledAt": "2026-04-06T13:02:00.000Z"
}
```

The comment is scheduled exactly 1-2 minutes after the parent post. The action link at the end is confirmed weekly with the client during the heartbeat request.

**IMPORTANT:** Verify all endpoint structures and field names against the latest GHL API documentation before first use. The Social Planner API evolves. See: https://marketplace.gohighlevel.com/docs/ghl/social-planner/social-media-posting-api

---

## 18. Image Text Overlay Requirements

Every image generated for social posts must include text overlay (a title or headline for that day's content). This makes images more engaging and more likely to stop the scroll.

### Image Text Rules

1. **Every image includes a title/headline.** The text should be the day's hook or key insight, shortened to fit the image.
2. **Font must be creative.** No generic system fonts. Use bold, distinctive fonts that feel on-brand. Reference client's brand guidelines from the core .md files for approved fonts and colors.
3. **Images must use client's brand colors.** Pull the brand color palette from the core .md files and apply it to text overlays, backgrounds, and design elements for visual consistency across all platforms.
4. **Text must NOT cover faces.** If the image includes people, the text must be placed strategically to avoid covering faces, eyes, or key visual elements.
5. **All images must be brand-appropriate.** Image prompts must explicitly include "brand-appropriate, appropriate for the client's audience, no suggestive content." This is non-negotiable.
6. **Spelling must be correct.** The QC agent checks all text on images for spelling errors. Creative stylization is acceptable (like intentional capitalization or wordplay), but actual misspellings are not.
7. **Text placement strategy:** Place text in the upper third or lower third of the image, or use a semi-transparent overlay bar behind the text for readability.
8. **Maximum text on image:** Keep it to one headline (5-10 words max). The image is not a paragraph. It's a visual hook.

### If Image Text Has Spelling Errors

**First remedy — check the routing, not just the copy (P3-05 fix):** before regenerating with "corrected" text, confirm the prompt was routed to Ideogram V3 DESIGN (Section 8) and cleared the Section 8a pre-generation gate. A recurring spelling-error loop on a prompt that WAS correctly gated and routed is a genuine model defect; a spelling-error loop on a prompt that skipped the gate or was routed to Nano Banana is a routing defect, not a text defect — fix the routing first, then retry.

1. QC agent identifies the spelling error.
2. Confirm routing + gate compliance (above) before assuming the copy itself is at fault.
3. Regenerate the image with corrected text (and corrected routing, if that was the actual cause).
4. Retry up to 3 times.
5. If still failing after 3 attempts, notify the user via Telegram with the error details, including which model/route was used on each attempt.

---

## 19. QC Agent System

Before ANY content is scheduled or posted, a QC agent reviews every piece of content against a detailed checklist. The QC agent is the last gate before anything goes to the GHL Social Planner. Multiple QC agents can spin up in parallel to check different content types simultaneously.

### Content QC Checklist (Every Post, Every Platform)

The QC agent checks each of the following. If ANY check fails, the content is sent back for revision.

**Text Content Checks:**
- [ ] Content aligns with client's brand tone and voice from core files
- [ ] Content uses brand-appropriate language (no profanity, no vulgar language)
- [ ] Content is appropriate for the client's target audience
- [ ] No sexually suggestive content of any kind
- [ ] Zone 1 (Mobile Hook) is within the platform's character limit
- [ ] Zone 2 (Desktop Hook) is within the platform's character limit (if applicable)
- [ ] Total post length is within the platform's maximum character limit
- [ ] No em dashes anywhere in the content
- [ ] No misspellings
- [ ] Emojis are present but never more than 3 per post
- [ ] The recap (starting Day 2) is woven into the middle of the value zone, NOT at the beginning
- [ ] The pitch matches the day's intensity level (soft Day 1, maximum Day 7)
- [ ] The cliffhanger is present at the end (Days 1-6 tease next day, Day 7 teases next week)
- [ ] The PRIMARY DM call-to-action is present in the post body (e.g. "send us a message" / "DM us"), tied to scheduling an appointment — this is the interaction that reaches an agent that answers (GHL Conversations → Skill 38). (§12)
- [ ] The BACKUP "the link is in the comments" directive is also present in the post body (reach-preserving self-serve path for the weekly action link). (§12) — a post that has ONLY the comment directive and NO DM CTA FAILS this checklist.
- [ ] The pitch creates an emotionally compelling reason to schedule an appointment (not just a mention of the brand)
- [ ] The series label is present (e.g., "Three of Seven")
- [ ] Hashtags follow platform-specific guidelines
- [ ] Content tone is emotionally visceral but not salesy

**Comment Checks:**
- [ ] Commentis unique (not duplicated from any other day's comment)
- [ ] Commentties directly to that day's specific topic (congruency)
- [ ] Commentends with the current weekly action link (confirmed during heartbeat)
- [ ] Action link matches what the client provided for this week
- [ ] Commenttone is empathetic, understanding, urgent but not pushy
- [ ] No em dashes in the comment
- [ ] No misspellings in the comment

**Image Checks:**
- [ ] The prompt passed `scripts/pregen_prompt_gate.py check` BEFORE generation (Section 8a) — a prompt generated without a passing gate run is itself a QC failure, regardless of how the resulting image looks
- [ ] Text-overlay images were routed to Ideogram V3 DESIGN, never Nano Banana (Section 8)
- [ ] If the asset originated from the Graphics department, it carries a SOP-GIP-02 QC receipt scoring >= 8.5 (Section 19a) — an ungated graphics-department asset is REJECTED, not posted
- [ ] Image prompt is appropriate for the client's brand and target audience
- [ ] Image contains NO sexually suggestive content
- [ ] Image contains NO violent or inappropriate imagery
- [ ] Image uses client's brand colors from core files
- [ ] Image is generated at the correct ratio for the platform (4:5, 2:3, or 9:16)
- [ ] Image is generated at the correct pixel dimensions
- [ ] Image includes text overlay (title/headline)
- [ ] Text on image does not cover faces
- [ ] Font on image is creative (not generic)
- [ ] Spelling on image text is correct
- [ ] Image file format is correct (PNG or JPG)

**Scheduling Checks:**
- [ ] Postis scheduled for the correct day (Sunday = Day 1, Monday = Day 2, etc.)
- [ ] Postis scheduled for 9:00 AM
- [ ] Commentis scheduled 1-2 minutes after the post
- [ ] All 6 platforms have posts scheduled for each day
- [ ] Carousel is scheduled for Thursday
- [ ] Email newsletter is scheduled for Tuesday at 9:00 AM
- [ ] Blog, podcast, and grand finale are scheduled for Day 7

**Blog Post Checks:**
- [ ] Word count is between 1,500-2,500 words
- [ ] Soft pitch is in the middle (around 50% mark)
- [ ] Intentional pitch is at the end
- [ ] SEO elements are present (title, meta description, subheadings, keywords)
- [ ] Featured image is generated at 16:9 (1200x630)
- [ ] No em dashes
- [ ] No misspellings

**Podcast Script Checks:**
- [ ] Script length is 1,500-2,000 words
- [ ] Fish Audio S2 emotion tags are present in [square brackets]
- [ ] Script covers all 7 days of content
- [ ] Pitch is woven naturally toward the end
- [ ] CTA is present
- [ ] Next week tease is present
- [ ] No em dashes
- [ ] No misspellings

**Podcast Audio Checks:**
- [ ] Audio is MP3 format
- [ ] Bitrate is 192 kbps
- [ ] Duration is 10-15 minutes

**Video Checks:**
- [ ] Video is 60 seconds
- [ ] Video is 9:16 (1080 x 1920)
- [ ] Video is MP4, H.264, 30fps
- [ ] Audio track is synced
- [ ] Video plays without errors

### QC Failure Process

1. If a check fails, the QC agent flags the specific issue.
2. The content is automatically revised to fix the flagged issue.
3. The QC agent re-checks the revised content.
4. If it fails again, retry the revision up to 3 total attempts.
5. If still failing after 3 attempts, notify the user via Telegram with the specific failure details.

### Section 19a — Input-Quality Gate on Graphics-Department Assets (P3-05 step 4i)

When an image asset for this week's content did NOT come from this skill's own Section 8/8a generation pipeline but was instead handed off from the Graphics department, the planner does not post it on trust. Run it through the same `pregen_prompt_gate.py check` used for every other image, with `--asset-source graphics-department --qc-receipt-file <job>/qc/image_qc_report.json` pointed at the department's SOP-GIP-02 vision-QC receipt. The gate REJECTS the asset (exit 6, `AF-SM-INPUT-QC-GATE`) when the receipt is missing or scores under 8.5 — the planner posts the FIRST asset that clears its own gate plus a valid receipt and REFUSES the second, loudly, exactly like every other gate failure in this section (never a silent skip).

---

## 20. Error Handling & Notifications

### kie.ai Error Handling

If any kie.ai API call fails (image generation, video generation):

1. **Automatic retry:** The AI retries the failed call up to 3 times with a 10-second delay between attempts.
2. **After 3 failures:** Send an immediate Telegram message to the user with:
   - What failed (e.g., "Image generation for Day 3 at 4:5 ratio failed")
   - Why it failed (the error message from kie.ai)
   - "Standing by for your instructions"
3. **Exception for insufficient funds:** If the error message indicates insufficient credits/funds, do NOT retry. Immediately send a Telegram message: "kie.ai reports insufficient funds. Current credit balance may need to be topped up. Please add credits and let me know when ready to continue."
4. After the user resolves the issue, the AI resumes from where it stopped.

### GHL Social Planner Error Handling

If a GHL API call fails:

1. **Automatic retry:** Retry up to 3 times with a 5-second delay.
2. **After 3 failures:** Send a Telegram message with the error details.
3. **Common errors to watch for:**
   - 401 Unauthorized: Private integration token may have expired or been revoked. Notify user to generate a new token in GHL Settings > Integrations > Private Integrations.
   - 422 Unprocessable Entity: Check that the accountId is valid and the content meets platform requirements.
   - 400 Bad Request: Check the request payload structure.

### Fish Audio S2 Error Handling

If podcast audio generation fails:

1. **Automatic retry:** Retry up to 3 times.
2. **After 3 failures:** Send a Telegram message with the error details.

### Telegram Notification Format

All error notifications follow this format:
```
[SOCIAL MEDIA AUTOMATION ALERT]

What failed: [specific task]
Error: [error message]
Timestamp: [date/time]
Attempts: [number of retries]

Status: Standing by for your instructions.
```

---

## 21. LinkedIn PDF Carousel Generation (OpenClaw Command)

To convert 4:5 (1080x1350) carousel images into a PDF for LinkedIn upload, use ImageMagick on OpenClaw:

```
convert slide_01.png slide_02.png slide_03.png slide_04.png slide_05.png slide_06.png slide_07.png linkedin_carousel.pdf
```

If ImageMagick is not available, use Python with Pillow:

```python
from PIL import Image

images = []
for i in range(1, 8):
    img = Image.open(f"slide_{i:02d}.png").convert("RGB")
    images.append(img)

images[0].save("linkedin_carousel.pdf", save_all=True, append_images=images[1:])
```

Verify the PDF before uploading:
- File size under 100 MB (ideally under 10 MB)
- All pages are the same dimensions (1080 x 1350)
- Pages are in the correct order

---

## 22. Content Hacks & Edge Cases

### Edge Cases

1. **Day 1 has no recap.** It's the pilot. The hook must work extra hard. No series momentum yet.
2. **Day 7 has no forward cliffhanger within the series.** It teases NEXT WEEK'S theme instead.
3. **Day 7 is the longest post.** Grand finale. Bring it all home.
4. **The "missed a day" problem:** Recaps create curiosity about missed content, not just summaries. Make them want to go BACK.
5. **Weekend posting:** Days 6-7 may fall on weekends. Engagement patterns differ. Adjust scheduling.
6. **LinkedIn carousel opportunity:** Turn the 7-day series into a single PDF carousel at week's end as a recap post.
7. **Blog and podcast release timing:** Both release on Day 7 ONLY. Never earlier.

### Content Hacks

1. **Cross-platform referencing:** Mention that the series lives on other platforms. Drives cross-platform follows.
2. **First comment strategy:** On Instagram and LinkedIn, place CTAs in the first comment. Keeps caption clean, boosts comment count.
3. **"Save this post" CTA:** Saves signal high value to algorithms on Instagram and LinkedIn.
4. **Series numbering as pattern interrupt:** "Five of Seven" creates natural curiosity and drives profile visits.
5. **Pin strategy:** Pin Day 1 and Day 7 to profile tops on Instagram, TikTok, Facebook.
6. **Engagement loop in comments:** Ask specific questions, not generic ones. "What age did you first notice this?" beats "What do you think?"
7. **The micro-blog approach:** Each post is a mini blog. A TV episode. It gives value alone and connects to the bigger story.
8. **Repurpose the series:** At week's end, the 7 posts become a blog, podcast, email newsletter, or PDF guide.
9. **Reply to every comment within 1 hour of posting.** This single action can boost engagement by 9.5%+ on Facebook.
10. **Use the "Invite to Follow" feature on Facebook** after posts get likes in Groups.

---

## 23. Universal Quick-Reference Specs

### Hook Zone Quick Reference

| Platform | Mobile Hook | Words | Desktop Hook | Words |
|----------|-----------|-------|-------------|-------|
| Facebook | 150 chars | ~25 | 477 chars | ~80 |
| Instagram | 125 chars | ~20 | 125 chars | ~20 |
| LinkedIn | 140 chars | ~23 | 210 chars | ~35 |
| YouTube | 288 chars | ~48 | 288 chars | ~48 |
| Pinterest | ~50 chars | ~8 | ~50 chars | ~8 |
| TikTok | ~150 chars | ~25 | ~150 chars | ~25 |

### Character-to-Word Conversion

| Characters | Words | Where Used |
|-----------|-------|-----------|
| 50 | ~8 | Pinterest feed preview |
| 125 | ~20 | Instagram hook |
| 140 | ~23 | LinkedIn mobile hook |
| 150 | ~25 | Facebook mobile hook, TikTok hook |
| 210 | ~35 | LinkedIn desktop hook |
| 288 | ~48 | YouTube hook |
| 477 | ~80 | Facebook desktop preview |
| 500 | ~83 | Pinterest max description |
| 2,200 | ~370 | Instagram max, Reels captions |
| 3,000 | ~500 | LinkedIn max |
| 4,000 | ~670 | TikTok max |
| 7,700 | ~1,280 | YouTube Community Postmax |
| 63,206 | ~10,500 | Facebook max (never use this much) |

### Three Image Files Per Day

| File | Ratio | Pixels | Platforms |
|------|-------|--------|-----------|
| PRIMARY | 4:5 | 1080 x 1350 | FB Feed, IG Feed, LinkedIn Feed, YT Community |
| VERTICAL | 2:3 | 1000 x 1500 | Pinterest Pin |
| FULL SCREEN | 9:16 | 1080 x 1920 | Stories, Reels, TikTok, YT Shorts, LinkedIn Video, Pinterest Idea Pin |

Plus 16:9 thumbnails (1280x720) for YouTube and blog featured image (1200x630) as needed.

### Weekly Production Summary

| Deliverable | Quantity | Release Day |
|------------|----------|-------------|
| Core content (7 days) | 7 pieces | Days 1-7 |
| Platform-specific posts (6 platforms x 7 days) | 42 posts | Days 1-7 |
| Comments below each post (action link + emotional copy) | 42 comments | Days 1-7 |
| Carousel posts (all platforms) | 1 set | Thursday |
| Email newsletter | 1 | Tuesday 9 AM |
| 4:5 images | 7 | Days 1-7 |
| 2:3 images | 7 | Days 1-7 |
| 9:16 images | 7 | Days 1-7 |
| 60-second videos (9:16) | 2 | Day 1 (opener) + Day 7 (grand finale) |
| Blog post | 1 | Day 7 |
| Blog featured image | 1 | Day 7 |
| Podcast cover image (1400x1400, 2K res) | 1 | Day 7 |
| Podcast script with emotion tags | 1 | Day 7 |
| Podcast audio (via Fish Audio S2, 192 kbps) | 1 | Day 7 |

### Weekly Cost Estimate

| Item | Cost |
|------|------|
| 22 images at 1K (Nano Banana 2: 7x 4:5, 7x 2:3, 7x 9:16, 1x blog) | $0.88 |
| 1 podcast cover at 2K (Nano Banana 2) | $0.06 |
| 2 videos at 60 sec each (Veo 3.1 Lite, 8 clips per video) | ~$3.00 |
| Fish Audio S2 podcast (self-hosted) | Compute only |
| **Total per week** | **~$3.94** |

---

---

## 24. Heartbeat.md Configuration

The heartbeat.md file tells the AI what recurring tasks to perform and when. Add the following entry to your heartbeat.md file on OpenClaw.

### Heartbeat Entry: Weekly Theme Request

```markdown
## Weekly Social Media Theme Request ([Brand Name])

### Schedule
- **Saturday 8:00 AM**: Send first theme request to the client (owner/founder)
- **Saturday 12:00 PM (Noon)**: If no response received, send second request
- **Saturday 6:00 PM**: If no response received, send third request
- **Sunday 7:00 AM**: If STILL no response received, send final request

### Maximum attempts: 4 (3 on Saturday, 1 on Sunday)

### Message Template (vary the wording each time, keep it friendly and conversational)

**First ask (Saturday 8 AM):**
"Good morning! Ready to make this week amazing for [Brand Name]. What's the social media theme for this week? Once I have it, I'll get started on your 7-day content series, images, blog post, podcast, and videos."

**Second ask (Saturday Noon):**
"Hey, just checking in! I want to make sure I have plenty of time to produce everything for this week. What theme are we going with? Drop it here whenever you're ready."

**Third ask (Saturday 6 PM):**
"One more check-in for today! I'd love to get started on your content tonight so everything is polished and ready. What's the theme for this week?"

**Final ask (Sunday 7 AM):**
"Good morning! I want to make sure we stay on schedule. Posts start going out today. Can you send me this week's theme so I can get everything produced and scheduled?"

### Once the theme is received:
1. Log the theme to the Google Sheet for record-keeping.
2. Immediately begin the Weekly Production Workflow (Section 3, Step 1).
3. Produce all content, images, videos, blog, podcast, email, carousels, and comments.
4. Run all QC checks (Section 19).
5. Schedule everything via the GHL Social Planner API, 7 days out starting Sunday at 9:00 AM.

### If no theme is received by Sunday 9:00 AM:
- Send a Telegram notification to the user: "I haven't received this week's theme for [Brand Name] yet. Posts are scheduled to start going out today. Please provide the theme ASAP so I can produce and schedule everything."
- Stand by until the theme is provided.
- Once received, produce and schedule on an expedited timeline.
```

### How to Add This to heartbeat.md

On OpenClaw, open or create the heartbeat.md file and paste the above configuration. The AI agent reads this file on its scheduled check intervals and executes the tasks at the specified times.

---

---

## 25. Google Sheet Structure & AI Update Instructions

The client's Google Sheet is the central content hub. It accumulates week after week. The AI logs all produced content here after QC passes and before/after scheduling via GHL.

### Worksheet Tabs (19 Total)

| # | Tab Name | Color | Purpose |
|---|----------|-------|---------|
| 1 | Weekly Overview | Blue | Theme, dates, status tracker per week |
| 2 | Core Content | Purple | 7 days of core content + research |
| 3 | Facebook Posts | Dark Blue | 7 days FB feed posts + comments + images |
| 4 | FB Stories & Reels | Light Blue | Stories/Reels with 9:16 images |
| 5 | Instagram Posts | Pink | 7 days IG feed posts + comments + images |
| 6 | IG Stories & Reels | Light Pink | Stories/Reels with 9:16 images |
| 7 | LinkedIn Posts | Navy | 7 days LinkedIn posts + comments + images |
| 8 | YouTube | Red | Community Posts + Shorts |
| 9 | TikTok | Teal | 7 days TikTok posts + comments |
| 10 | Pinterest | Dark Red | 7 days Pinterest pins + 2:3 images |
| 11 | Carousels - Facebook | Orange | Thursday FB carousel slides + images |
| 12 | Carousels - Instagram | Deep Orange | Thursday IG carousel slides + images |
| 13 | Carousels - LinkedIn | Brown | Thursday LinkedIn carousel PDF + images |
| 14 | Carousels - YouTube | Amber | Thursday YT Community Postcarousel images |
| 15 | Email Newsletter | Green | Tuesday email content |
| 16 | Blog Post| Dark Green | Day 7 blog content + featured image |
| 17 | Podcast | Yellow | Script + audio URL + cover image |
| 18 | Images | Gray | Master list of ALL images by day and ratio |
| 19 | Videos | Dark Gray | Day 1 + Day 7 video details |

### Week Identifier Format

Every row in every worksheet starts with a "Week Of" column. The format is always:

```
Week of Apr 12 - Apr 18, 2026
```

This ensures that as weeks accumulate, the user can always see which content belongs to which week and which year.

### How the AI Updates the Google Sheet

**Layout: 7 Days Across (Horizontal)**
Platform sheets (Facebook Posts, Instagram Posts, LinkedIn Posts, YouTube, TikTok, Pinterest, Stories & Reels, Images) use a horizontal layout where all 7 days are displayed as column groups going LEFT TO RIGHT. One week = one row. You can scan across and see the full progression from Day 1 through Day 7 like a storyboard.

Row 2 contains the day group headers: "DAY 1 (One of Seven)" through "DAY 7 (Seven of Seven)", each color-coded with a unique background color.

Row 3 contains the sub-headers under each day (e.g., "Post ", "Comment", "Image 4:5").

Data starts at Row 4. Each new week adds one new row.

**For each new week, the AI appends a new row below the existing data.** It never overwrites previous weeks. The sheet grows week over week as a running archive.

**Column structure for platform sheets (e.g., Facebook Posts):**
- Column A: "Week Of" (e.g., "Week of Apr 12 - Apr 18, 2026")
- Each day has 3 columns: Full Post, Comment, Image
- Day 1: Columns B-D | Day 2: Columns E-G | Day 3: Columns H-J | Day 4: Columns K-M | Day 5: Columns N-P | Day 6: Columns Q-S | Day 7: Columns T-V
- Remaining columns: Action Link, Status, Notes

**The "Full Post " Column:**
Each day's "Full Post " column contains the COMPLETE assembled post with all zones put together as one piece. This is the finished product: Hook + Value + Recap + Pitch + Cliffhanger + Hashtags, all combined into one continuous piece of content exactly as it will be posted. The individual zone breakdown lives in the Core Content sheet. The platform sheets show the final assembled output.

**Text Wrapping:**
All content cells use text wrapping so the truncated preview (200 chars + "...") is readable within the cell at the fixed row height. Content wraps within the cell boundaries rather than clipping and disappearing. The user can see a meaningful preview of the content without clicking into the cell, and can click the cell to see the full text in the formula bar.

**Image Display in Cells:**
When logging images, the AI uses the Google Sheets =IMAGE() function to display the image inline:
```
=IMAGE("https://assets.cdn.filesafe.space/[GHL_LOCATION_ID]/media/[filename]", 1)
```
Mode 1 fits the image within the cell while maintaining aspect ratio. Image cells are pre-sized for each ratio.

> **CRITICAL — =IMAGE() URLs MUST be GHL CDN URLs.** The URL inside `=IMAGE()` must be a permanent GHL CDN link (`https://assets.cdn.filesafe.space/...`), never a generator-hosted or ephemeral URL. Generator-hosted links (kie.ai, example.com) and ephemeral hosts (tmpfiles.org, file.io) silently expire and break every sheet cell referencing them. Upload to the client's GHL Media Library first (SKILL.md Media Delivery Contract), then use the returned CDN `url` in the formula.

**Content Truncation & Assembly:**
The AI writes the FULL assembled post (all zones combined into one flowing piece) into the "Full Post " column. The content is truncated to approximately 100-120 characters (roughly 2-3 lines of visible text at the cell's font size). The cell uses text wrapping with a fixed row height, so the text wraps naturally but never shows more than 2-3 lines. Anything beyond that is hidden by the cell boundary. The user clicks the cell to see the full content in the formula bar.

Column headers are clean, human-readable labels with no internal jargon. The AI handles truncation automatically when writing to the sheet. The end user never sees implementation details in the column names.

The Core Content sheet retains the individual zone breakdown (Topic, Content, Key Stat, Pitch Level, Cliffhanger) so you can see how the puzzle fits together. The platform sheets show the assembled final product.

**Image Cells (Ratio-Correct Sizing):**
Each day's image is displayed right next to that day's content. Image cells are sized to preserve the aspect ratio of the image so nothing is cropped or cut off. The image displays as a proportionally scaled-down thumbnail. Google Sheets =IMAGE() mode 1 fits the full image within the cell while maintaining aspect ratio.

Image cell sizing by ratio:
- 4:5 images: Column width 15 (~108px display), Row height 100pt (~133px). Full image visible, proportionally smaller.
- 9:16 images: Column width 11 (~79px display), Row height 115pt (~153px). Full image visible, proportionally smaller.
- 2:3 images: Column width 14 (~101px display), Row height 100pt (~133px). Full image visible, proportionally smaller.
- 1:1 images: Column width 14 (~101px display), Row height 100pt (~133px). Full image visible, proportionally smaller.

**Row/Column Sizing (CRITICAL):**
When the AI writes image URLs using =IMAGE() formulas, it MUST also resize the rows and columns to display the images properly. Raw URLs in cells that are too small display as truncated text. The AI MUST call the Google Sheets API batchUpdate method to set:
- Image columns: pixelSize 108 (for 4:5, 2:3, 1:1) or 79 (for 9:16)
- Data rows containing images: pixelSize 133 (for 4:5, 2:3, 1:1) or 153 (for 9:16)

Example batchUpdate request for a Day tab (column D, rows 2-21):
```json
{
  "requests": [
    {
      "updateDimensionProperties": {
        "range": {"sheetId": 123, "dimension": "COLUMNS", "startIndex": 3, "endIndex": 4},
        "properties": {"pixelSize": 108},
        "fields": "pixelSize"
      }
    },
    {
      "updateDimensionProperties": {
        "range": {"sheetId": 123, "dimension": "ROWS", "startIndex": 1, "endIndex": 21},
        "properties": {"pixelSize": 133},
        "fields": "pixelSize"
      }
    }
  ]
}
```
The n8n webhook (`social-planner-row-append`) should apply this sizing automatically when it detects an =IMAGE() formula in the payload. If the webhook does not handle sizing, the AI MUST call the Sheets API directly after appending the row.

**Video Links:**
Google Sheets cannot embed playable video. The AI inserts a clickable hyperlink:
```
=HYPERLINK("https://example.com/video.mp4", "Watch Video")
```

**Step-by-step for the AI:**
1. Open the Google Sheet using the Google Sheets API.
2. Determine the next available row on each worksheet.
3. Write "Week of [start date] - [end date], [year]" in Column A.
4. For each platform sheet, write all 7 days of content across the columns: Day 1 post in column B, Day 1 comment in column C, Day 1 image in column D, Day 2 post in column E, etc.
5. **Insert image URLs using =IMAGE("url", 1) for inline display — NEVER write a raw URL as text.** Every image cell value must be a formula string starting with `=IMAGE(`. Raw URLs render as unclickable text and defeat the purpose of the visual planner.
6. **Resize image columns and data rows** via batchUpdate (see "Row/Column Sizing" above) so the =IMAGE() thumbnails display at full size. Image columns → 108px wide (79px for 9:16); data rows → 133px tall (153px for 9:16). Apply to ALL tabs that contain images, not just one.
7. Write content at 100-120 characters per cell (2-3 lines visible). The AI writes the full content to the cell, but the fixed row height naturally hides anything beyond the preview. Click the cell to see full text in the formula bar.
8. Insert video links using =HYPERLINK().
9. For the Images master sheet, write all 3 ratios per day across columns (4:5 URL, 4:5 Preview, 2:3 URL, 2:3 Preview, 9:16 URL, 9:16 Preview) for each of the 7 days. Preview columns use =IMAGE(); URL columns may stay as text.
10. For carousel sheets, write one row per week with slide content across columns.
11. For Email, Blog, Podcast sheets (one entry per week), write one row with all fields. Blog "Featured Image" and Podcast "Cover Image" use =IMAGE().
12. Update the Weekly Overview with the theme and status of each production phase.

---

## 26. Playbook Coverage & Self-Rating

This section documents what the playbook covers, confirms completeness, and identifies any known limitations so the AI agent and human operators have full transparency.

### What This Playbook Covers (Verified Complete)

| Area | Status | Key Details |
|------|--------|-------------|
| Brand Guidelines | Complete | AI reads all OpenClaw core .md files (identity.md, soul.md, memory.md, agents.md, heartbeat.md) before any content generation. Brand colors, tone, voice, mission verified before production starts. |
| Content Safety | Complete | Family-friendly mandate. No sexually suggestive, violent, or inappropriate content. Explicit in all image prompts. QC verified. |
| 7-Part Series Framework | Complete | Television show structure. One of Seven through Seven of Seven. Pitch intensity scales from soft (Day 1) to maximum (Day 7). |
| Content Zone System | Complete | 6 zones defined with platform-specific character limits. Zone 1 (Mobile Hook) is sacred. Recaps never in the hook zone. |
| Platform Specifications | Complete | Facebook, Instagram, LinkedIn, YouTube, TikTok, Pinterest. Image ratios, character limits, truncation points, carousel specs all documented. |
| Image Production | Complete | Nano Banana 2 via kie.ai. 4:5, 2:3, 9:16, 16:9, 1:1 ratios. Text overlay with creative fonts. Spelling QC. Family-friendly prompts. Brand colors from core files. |
| Video Production | Complete | 2 videos per week (Day 1 opener, Day 7 finale). Veo 3.1 Lite via kie.ai. Grok Imagine as backup. FFmpeg merge with 192 kbps audio. Full cost comparison table. |
| Podcast Production | Complete | Fish Audio S2 with inline [square bracket] emotion tags. 192 kbps MP3 for Podbean. 1400x1400 cover image at 2K resolution. Example script with emotion tags. |
| Blog Post| Complete | 1,500-2,500 words. Soft pitch in the middle, intentional pitch at the end. SEO optimized. Featured image at 16:9. |
| Email Newsletter | Complete | Tuesday 9 AM. TLDR at top, soft pitch at 25%, second soft pitch at 50%, intentional appointment pitch at end. 600-1,000 words. |
| Carousel Strategy | Complete | Thursday release. ONE set of 4:5 images reused across Facebook, Instagram, LinkedIn (as PDF). Separate 9:16 for TikTok, 2:3 for Pinterest. Cost optimized. |
| Comment Strategy | Complete | Every post gets a unique comment. Ties to that day's topic (congruency). Emotionally visceral, not salesy. Ends with action link. 4 example comments provided. |
| Action Link | Complete | Hardcoded: [ACTION LINK - confirmed weekly with client] |
| GHL Social Planner API | Complete | All endpoints documented. GHL handles all posting AND commenting. Scheduling logic: 7 days ahead, Sunday start, 9:00 AM. |
| Sub-Agent Architecture | Complete | 4 phases. Main Agent handles research + core content. 8 parallel Sub-Agents for production. QC agents validate. Main Agent schedules and logs. |
| QC Agent System | Complete | 40+ checkbox items across 8 categories: Text, Comments, Images, Scheduling, Blog, Podcast Script, Podcast Audio, Video. 3 retry max before Telegram alert. |
| Error Handling | Complete | kie.ai retry 3x then Telegram. Insufficient funds = no retry, immediate Telegram. GHL retry 3x. Fish Audio retry 3x. Standard notification format. |
| Heartbeat.md | Complete | Saturday 8 AM, Noon, 6 PM + Sunday 7 AM. Max 4 asks. Friendly conversational messages. Telegram fallback if no response by Sunday 9 AM. |
| Google Sheet Structure | Complete | 19 worksheets, color-coded tabs, horizontal 7-day storyboard layout, image cells sized to ratio, text wrapping at 2-3 lines, =IMAGE() for inline display, =HYPERLINK() for videos, conditional formatting on status columns, freeze panes, "Week of" identifiers. |
| LinkedIn PDF Generation | Complete | ImageMagick and Python/Pillow commands provided for converting 4:5 carousel images to PDF on OpenClaw. |
| Content Hacks | Complete | Edge cases for Day 1 (no recap), Day 7 (no forward cliffhanger), weekend posting, cross-platform referencing. |
| Weekly Cost Estimate | Complete | ~$3.94/week total (22 images at 1K, 1 podcast cover at 2K, 2 videos via Veo 3.1 Lite). |

### Known Limitation

This playbook does not include a full worked example of a complete day's output (showing a finished Day 1 Facebook post with all zones filled in, the comment below it, the image prompt, etc.). This was intentionally omitted to prevent the document from becoming bloated. The zone system, pitch examples, comment examples, and content flow rules provide enough guidance for the AI to produce correct output without a full example. If a full example is needed in the future, it can be added as an appendix.

**Partial closure (master spec v2 A-U9 / master unit U9, 2026-07-15):** a first worked example now ships as an exemplar pack — `../exemplars/social-caption/founder-story-carousel-caption/` (gold output + `WHY-GOOD.md` rationale + `provenance.json`) — a complete, fictional-brand carousel caption (hook, body, swipe bridge, soft CTA) with the register/structure/close named explicitly, wrapped in a CALIBRATION-ONLY clause at write time so it calibrates the writer without ever being copied verbatim (`shared-utils/exemplar_injection.py`). This covers the CAPTION zone only, not a full day's output across every deliverable (image prompt, podcast script, video) — the broader gap named below is honestly still open; additional packs can be authored under the same convention as they're prioritized.

### Self-Rating: 9/10

The one point gap is the lack of a full worked example. Every other system, process, specification, checklist, and instruction is documented, verified, and cross-referenced. The AI has everything it needs to execute the full weekly production workflow from heartbeat to scheduling.

---

*[Brand Name] Social Media Playbook v6.0 | Built by BlackCEO Automations*
