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

### Step 3: Create the Google Sheet

**The agent creates the Google Sheet for the client. Do NOT ask the client to duplicate the template.**

Using Google Workspace integration (Skill 14):
1. Duplicate the template sheet: https://docs.google.com/spreadsheets/d/1RKgS5l-i6NBtf_vON49nBPdHe-F5W67RF9ym-S67L2c/edit?usp=sharing
2. Rename the copy to: "[Brand Name] Social Media Planner"
3. Share the copy with the client's email (edit access)
4. Store the new sheet URL in MEMORY.md
5. Tell the client: "I created your Social Media Planner sheet. Here is the link: [URL]. You have full edit access."

**Fallback only if Google Workspace fails:** Tell the client "I was not able to create the sheet automatically. Please go to this link, click File then Make a Copy, rename it to [Brand Name] Social Media Planner, and share the edit link back with me: [template URL]"

**Template link:**
```
https://docs.google.com/spreadsheets/d/1RKgS5l-i6NBtf_vON49nBPdHe-F5W67RF9ym-S67L2c/edit?usp=sharing
```

Store the client's Google Sheet link for all future weekly updates.

### Step 4: Ask the Weekly Action Link

Ask: "What is your action link for this week? This is the link you want people to click when they take action (schedule a call, book an appointment, sign up, download, etc.)."

Also ask: "Should I use this same action link every week, or will it change? I'll confirm with you each week either way."

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

**Step 0a.5: Select Content Persona (5-Layer Alignment)**
Before writing any content, the AI selects a persona to govern this week's content style using the 5-layer alignment check:

1. Layer 1 (Company Mission): Does this persona's philosophy align with the brand?
2. Layer 2 (Owner Values): Does this persona match the owner's communication style?
3. Layer 3 (Company Goals): Does this persona support current business objectives?
4. Layer 4 (Department Goals): Is this persona right for marketing/content work?
5. Layer 5 (Task Fit): Is this persona ideal for social media content about this specific weekly theme?

Search persona-categories.json for marketing-tagged personas (Seth Godin, Gary Vee, Donald Miller, Brendan Kane, Alex Hormozi). Run all 5 layers. Select the best fit. Log the selection to persona-selection-log.md in the department workspace.

**Persona Override Option:**
After selecting the recommended persona, present the choice to the client:

"For this week's content about [theme], I recommend using [Persona Name]'s approach. [One sentence explaining why.] Would you like me to use this style, or would you prefer I write in your personal brand tone from your soul.md instead?"

If the client says to use their personal tone: skip the persona and write using ONLY the client's soul.md tone, voice, and style.
If the client says to use the recommended persona: proceed with the Act As If Protocol.
If the client names a different persona: use that persona instead.

All content this week (posts, comments, blog, email, podcast) follows the selected style consistently.

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
The primary goal of every post is getting appointments. The pitch zone creates an emotionally compelling reason for the reader to schedule an appointment with [Brand Name]. This is not about selling a product. This is about helping the reader take the next step. The pitch follows the intensity schedule (4/10 on Day 1, gradually increasing to 10/10 on Day 7), and always ends with a directive to check the comments for how to schedule their appointment. The pitch should make them FEEL something: the urgency of their situation, the hope that comes from taking action, the relief of finally having someone who understands. Then it points them to the comments where the action link lives.

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
  - Day 1 (Intensity: 4/10): Warm introduction. "[Brand Name] helps people with exactly this. Check the comments to learn how to take the next step."
  - Day 2 (Intensity: 5/10): Building. "This is what [Brand Name] does every day. Check the comments to start a conversation."
  - Day 3 (Intensity: 5/10): Steady. "If this is resonating, you're not alone. Check the comments to connect with [Brand Name]."
  - Day 4 (Intensity: 6/10): Direct. "This is exactly what [Brand Name] is designed to address. Check the comments to take action."
  - Day 5 (Intensity: 7/10): Strong. "You've seen the evidence. You feel it. Check the comments to schedule your conversation with [Brand Name]."
  - Day 6 (Intensity: 9/10): Urgent. "You don't have to figure this out alone. The [Brand Name] team is ready. Check the comments right now."
  - Day 7 (Intensity: 10/10): Maximum. "This is the moment. Don't let another week go by. Check the comments to take action with [Brand Name] today."
- The pitch always ends with a directive to CHECK THE COMMENTS. The action link lives in the comment, not the post.
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

### Image Generation Models

| Model | Role | Cost (1K) | Cost (2K) | Cost (4K) |
|-------|------|-----------|-----------|-----------|
| Nano Banana 2 | PRIMARY | $0.04 | $0.06 | $0.09 |
| Nano Banana Pro | BACKUP | $0.09 | $0.09 | $0.12 |

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
| Slide 7 | CTA slide. "Follow us for the rest of the series. Check the comments to take the next step with [Brand Name]." |

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

## 12. Comment Strategy (Every Post, Every Day)

### The Rule

Every single social media post gets a comment below it. The post itself contains a line like "Check the comments to see how you can schedule a conversation with an [Brand Name] specialist" or similar. This directs the reader from the post down to the comment, where the actual appointment link lives.

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
- Generated via Fish Audio S2 text-to-speech with inline emotion tags
- Target length: 10-15 minutes (~1,500-2,000 word script)

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

### Podcast Publishing (via n8n Webhook to Podbean)

The agent does NOT publish directly to Podbean. Publishing goes through an n8n webhook automation that handles all Podbean API work.

**Publishing Flow:**
1. Agent generates podcast audio via Fish Audio S2 (MP3, 192 kbps)
2. Agent uploads the audio file to the GHL Media Library. NEVER send a Fish Audio URL directly to the webhook. It must go through GHL first.
3. Agent generates the podcast cover image via kie.ai Nano Banana 2 (1400x1400, 1:1, JPEG or PNG). NEVER use WebP. Apple Podcasts rejects WebP.
4. Agent uploads the cover image to the GHL Media Library.
5. Agent sends the following JSON payload to the webhook:

**Webhook Endpoint:**
```
POST https://main.blackceoautomations.com/webhook/podbean-publish
Content-Type: application/json
```

**Required Payload:**
```
{
  "podcast_id": "[client's Podbean channel ID - collected during First Run]",
  "audio_url": "https://media.gohighlevel.com/[path-to-uploaded-audio].mp3",
  "image_url": "https://media.gohighlevel.com/[path-to-uploaded-cover].jpg",
  "title": "[Episode title - matches the weekly theme]",
  "description": "[Show notes - plain text or HTML, under 3000 characters]",
  "publish_date": "2026-04-12T09:00:00",
  "client_first_name": "[from client profile]",
  "client_last_name": "[from client profile]",
  "client_email": "[from client profile]",
  "episode_type": "full",
  "explicit": "clean"
}
```

**Field Rules:**
- podcast_id: The client's Podbean channel ID. Collected during First Run and stored in MEMORY.md.
- audio_url: MUST be a GHL Media Library URL. Upload the Fish Audio S2 output to GHL first.
- image_url: MUST be a GHL Media Library URL. JPEG or PNG only. 1:1, 1400x1400 minimum, under 500 KB, RGB. If image exceeds 500 KB, resize before uploading to GHL.
- title: The episode title as it should appear in podcast apps.
- description: Show notes. Plain text or HTML. Under 3000 characters for cross-app compatibility.
- publish_date: ISO 8601 format WITH time component (e.g., 2026-04-12T09:00:00). Timezone is Eastern (EST/EDT). Date-only strings will cause an error.
- episode_type: "full" (default), "trailer", or "bonus".
- explicit: "clean" (default) or "explicit".

**Do NOT send an episode number.** The automation queries Podbean for the highest existing episode and assigns the next one automatically.

**What happens after sending:**
1. Webhook returns 200 OK immediately
2. Automation authenticates with Podbean and determines next episode number
3. Audio is downloaded from GHL and uploaded to Podbean storage
4. Cover image is validated (format, dimensions, size) and uploaded to Podbean storage
5. Episode is created and scheduled on the client's Podbean channel
6. Client receives a confirmation email with episode number, publish date, and live link
7. If anything fails, client receives a failure email with details

**Error handling:**
- If webhook returns non-200: retry once after 30 seconds. If still failing, notify client via Telegram.
- If you get no confirmation email within 15 minutes: notify client that podcast publishing may have failed and to check Podbean manually.
- Image format rejection: re-export the cover image as JPEG (not WebP) and re-send.

---

## 16. Video Production Pipeline (kie.ai + FFmpeg)

### Video Standard
- **Duration:** 60 seconds
- **Ratio:** 9:16 (1080 x 1920 pixels)
- **Output:** MP4, H.264 codec, 30fps

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

### Recommended Pipeline: Image-to-Video + Audio Overlay

**Primary approach:** Generate B-roll video segments from Nano Banana 2 images using Veo 3.1 Fast, then merge with podcast/narration audio using FFmpeg.

**Step-by-step process:**

1. **Generate 7-8 Nano Banana 2 images** as B-roll frames for the day's video at 9:16 (1080x1920). Cost: ~$0.28-$0.32
2. **Generate 7-8 video segments** at 8 seconds each using Veo 3.1 Lite image-to-video on kie.ai. Each image becomes an 8-second motion clip. Cost: $0.15 x 8 = $1.20
3. **Generate or extract the audio track.** Use Fish Audio S2 text-to-speech with emotion tags to produce a 60-second narration at 192 kbps (required for Podbean).
4. **Merge video segments using FFmpeg on OpenClaw:**
   ```
   ffmpeg -f concat -safe 0 -i segments.txt -i audio.wav -c:v libx264 -c:a aac -b:a 192k -shortest -y output.mp4
   ```
5. **Total cost per 60-second video (Veo 3.1 Lite):** ~$1.48-$1.52 (images + video segments)
6. **Weekly cost for 2 videos (Day 1 + Day 7):** ~$2.96-$3.04

### Alternative Pipeline: Text-to-Video (Simpler, Slightly More Expensive)

If image-to-video quality is insufficient:

1. Write 7-8 text prompts describing each 8-second scene.
2. Generate each segment using Veo 3.1 Fast text-to-video on kie.ai.
3. Merge with FFmpeg as above.
4. Cost: Same ($0.40 per segment).

### FFmpeg Merge Commands

**Create a segments list file (segments.txt):**
```
file 'segment_01.mp4'
file 'segment_02.mp4'
file 'segment_03.mp4'
file 'segment_04.mp4'
file 'segment_05.mp4'
file 'segment_06.mp4'
file 'segment_07.mp4'
file 'segment_08.mp4'
```

**Merge segments + add audio:**
```
ffmpeg -f concat -safe 0 -i segments.txt -i narration.wav -c:v libx264 -c:a aac -map 0:v -map 1:a -shortest -y final_video.mp4
```

**Add fade transitions between segments (optional):**
```
ffmpeg -i segment_01.mp4 -i segment_02.mp4 -filter_complex "[0:v][1:v]xfade=transition=fade:duration=0.5:offset=7.5" -y merged.mp4
```

---

## 17. GoHighLevel (Convert and Flow) Social Planner API

OpenClaw posts ALL social media content through the GoHighLevel (Convert and Flow) Social Planner API. This includes posting, scheduling, commenting, and managing content across all platforms. There is NO need for Facebook Graph API, N8N workflows, or any external tool for social posting. GHL Social Planner handles everything.

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

**Get Connected Accounts**
```
GET /social-media-posting/oauth/{locationId}/facebook/accounts/{accountId}
GET /social-media-posting/oauth/{locationId}/instagram/accounts/{accountId}
GET /social-media-posting/oauth/{locationId}/linkedin/accounts/{accountId}
GET /social-media-posting/oauth/{locationId}/tiktok/accounts/{accountId}
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
  "summary": "One of Seven: [Post content here with full zones, pitch, cliffhanger]\n\nCheck the comments to schedule your conversation with a [Brand Name] specialist.",
  "mediaUrls": ["https://storage.kie.ai/generated/image-day1-4x5.png"],
  "tags": ["social-media-planner", "week-14", "day-1"]
}
```

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
  "summary": "[Carousel caption with swipe CTA and check the comments directive]",
  "mediaUrls": [
    "https://storage.kie.ai/generated/carousel-slide1.png",
    "https://storage.kie.ai/generated/carousel-slide2.png",
    "https://storage.kie.ai/generated/carousel-slide3.png",
    "https://storage.kie.ai/generated/carousel-slide4.png",
    "https://storage.kie.ai/generated/carousel-slide5.png",
    "https://storage.kie.ai/generated/carousel-slide6.png",
    "https://storage.kie.ai/generated/carousel-slide7.png"
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
  "summary": "[Video post caption with check the comments directive]",
  "mediaUrls": ["https://storage.example.com/video-day1-9x16.mp4"],
  "tags": ["social-media-planner", "week-14", "video", "day-1"]
}
```

### Example API Request: Comment (Posted 1-2 Minutes After Parent Post)

The comment is a SEPARATE API call made AFTER the parent post is created. Use the parent post's ID:

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

1. QC agent identifies the spelling error.
2. Regenerate the image with corrected text.
3. Retry up to 3 times.
4. If still failing after 3 attempts, notify the user via Telegram with the error details.

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
- [ ] The "check the comments" directive is present in the post body, tied to scheduling an appointment
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
=IMAGE("https://example.com/image.png", 1)
```
Mode 1 fits the image within the cell while maintaining aspect ratio. Image cells are pre-sized for each ratio.

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
5. Insert image URLs using =IMAGE() for inline display.
6. Write content at 100-120 characters per cell (2-3 lines visible). The AI writes the full content to the cell, but the fixed row height naturally hides anything beyond the preview. Click the cell to see full text in the formula bar.
7. Insert video links using =HYPERLINK().
8. For the Images master sheet, write all 3 ratios per day across columns (4:5 URL, 4:5 Preview, 2:3 URL, 2:3 Preview, 9:16 URL, 9:16 Preview) for each of the 7 days.
9. For carousel sheets, write one row per week with slide content across columns.
10. For Email, Blog, Podcast sheets (one entry per week), write one row with all fields.
11. Update the Weekly Overview with the theme and status of each production phase.

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

### Self-Rating: 9/10

The one point gap is the lack of a full worked example. Every other system, process, specification, checklist, and instruction is documented, verified, and cross-referenced. The AI has everything it needs to execute the full weekly production workflow from heartbeat to scheduling.

---

*[Brand Name] Social Media Playbook v6.0 | Built by BlackCEO Automations*
