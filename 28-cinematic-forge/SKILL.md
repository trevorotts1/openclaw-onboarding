---
name: cinematic-forge
description: End-to-end AI video production from concept to finished upload — structured intake, VEO 3.1 Fast video generation via KIE.ai, ElevenLabs and Suno audio production, image generation, FFmpeg assembly, and media library upload.
---

# Cinematic Forge

> **Skill Name:** cinematic-forge
> **Version:** 1.0
> **Author:** (redacted for client-generic distribution)
> **Priority:** HIGH
> **Description:** An AI-powered video production skill that takes a user from concept to finished, uploaded video through a structured intake process, AI video generation (VEO 3.1 Fast via KIE.ai), AI audio production (ElevenLabs + Suno via KIE.ai), image generation (Nano Banana Pro via KIE.ai), FFmpeg assembly, and media library upload.

## Prerequisites

**MANDATORY: The agent MUST know the Teach Yourself Protocol before executing this skill.**

If the agent does not know the Teach Yourself Protocol:
1. STOP execution
2. Tell the user: "I need to learn the Teach Yourself Protocol before I can use this skill. Do you have it? If so, please share it with me."
3. Do NOT proceed until the Teach Yourself Protocol has been learned

**Other requirements:**
- FFmpeg installed (`ffmpeg -version` to verify)
- KIE.ai API key (stored in environment or secrets file)
- GHL/Convert and Flow Private Integration Token (PIT) for media library upload (the canonical env vars are `GOHIGHLEVEL_API_KEY` + `GOHIGHLEVEL_LOCATION_ID`). An imgBB API key is an optional fallback for reference **images** only — imgBB cannot host the final MP4.
- ElevenLabs access via KIE.ai (for voice generation)
- Suno access via KIE.ai (for music generation)
- Nano Banana Pro access via KIE.ai (for image generation)
- VEO 3.1 Fast access via KIE.ai (for video generation)

**Optional but recommended (for Q12 reference video analysis):**
- `video-frames` skill (ships with OpenClaw, requires FFmpeg) - extracts frames from videos
- `summarize` CLI (`brew install steipete/tap/summarize`) - transcribes/summarizes YouTube videos and URLs
- At least one LLM API key for summarize: `GEMINI_API_KEY` or `OPENAI_API_KEY`

If these aren't installed when a user provides a reference video, the agent should install them on the spot rather than skipping the analysis.

## What This Skill Does

Cinematic Forge is a complete AI video production pipeline. It:

1. Walks the user through 14 structured intake questions (one at a time)
2. Generates reference images for all characters and settings
3. Produces video segments using VEO 3.1 Fast (8-second segments)
4. Creates all audio layers separately (dialogue, narration, sound effects, music)
5. Assembles everything with FFmpeg (video + audio sync)
6. Uploads the final video to the user's media library
7. Returns the download link to the user wherever they started the conversation
8. Allows revision/edit cycles
9. Offers Topaz upscale to 1080p or 4K after client approval

## When to Use This Skill

- User asks to create a video from scratch
- User asks to produce a promotional video, ad, or reel
- User provides a video concept and wants it produced
- User says "make me a video," "create a video," "produce a video," or any variation

## When NOT to Use This Skill

- User wants to EDIT an existing video (use video-editor skill instead)
- User wants to cut/trim/resize an existing video (use video-editor skill)
- User wants to download a YouTube video (use video-editor skill)
- User just wants a single image generated (use image generation directly)

---

## THE INTAKE PROCESS

### How the Intake Works

When a user triggers this skill, the agent says:

> "I'm going to help you create a video from scratch. To make sure I build exactly what you're envisioning, I have 14 questions I need to ask you. I'll ask them one at a time so we can really dial in each detail. If any question doesn't make sense, just ask me to clarify. Let's get started."

**Rules for asking questions:**
- Ask ONE question at a time. Wait for the answer before asking the next one.
- EXPLAIN what you mean with each question so the user understands WHY you're asking
- If the user's answer is vague or unclear, ask for clarification before moving on
- Do NOT rush. The quality of the intake determines the quality of the video.
- Keep track of all answers - you'll reference them throughout production

### Question 1: The Concept

> "First up - what is this video about? Give me the big picture. What's the story, the message, or the concept you want to communicate? Don't worry about being perfect here - just tell me what's in your head and I'll help shape it."

**What you're looking for:** The core idea. A pharmaceutical parody ad. A motivational story. A product demo. A brand introduction. This sets the foundation for everything else.

### Question 2: Target Audience

> "Who is this video for? Who's going to be watching it? The more specific you can be, the better I can tailor the visuals, tone, and messaging. For example: 'Women entrepreneurs ages 30-50' or 'Small business owners who are just getting started.'"

**What you're looking for:** Demographics, psychographics, pain points. This affects everything from color choices to music style to how characters look and speak.

### Question 3: Tone and Mood

> "What's the vibe you want this video to have? Should it be funny? Serious? Empowering? Emotional? Edgy? Think about how you want people to FEEL when they watch it. You can mix tones too - like 'funny but with an empowering message at the end.'"

**What you're looking for:** Emotional direction. This drives the music choices, color grading decisions, pacing, and script tone.

### Question 4: Video Duration

> "How long should this video be? Here are common lengths and what they work best for:
> - **15-30 seconds** - Quick social media ads, Instagram Stories
> - **60 seconds** - Standard social media content, TikTok, Instagram Reels
> - **90 seconds** - Maximum for Facebook Reels (fits every major platform)
> - **2-3 minutes** - YouTube content, website landing pages, detailed explainers
>
> Keep in mind: shorter usually performs better on social media. 90 seconds is the sweet spot that works on every platform without needing to re-edit."

**What you're looking for:** Duration in seconds. This determines how many 8-second segments you'll need. Formula: ceil(duration / 8) segments. The last segment gets trimmed in FFmpeg to hit the exact target length.

**Math note:** VEO 3.1 Fast produces 8-second segments. If someone wants 90 seconds: 11 full segments (88 seconds) + 1 segment trimmed to 2 seconds = 90 seconds exactly. Cost = number of segments x $0.40 (Fast mode).

### Question 5: Characters

> "Tell me about the characters in this video. Who appears on screen? For each character, I need to know:
> - What they look like (skin tone, hair, body type, age range, clothing)
> - What role they play in the video (main character, supporting, background)
> - Their personality or energy (confident, nervous, funny, authoritative)
>
> The more detail you give me, the more consistent they'll look across every scene. I'll be creating AI reference images for each character to make sure they look the same throughout the entire video."

**What you're looking for:** Detailed character descriptions. These become the anchor reference images that maintain character consistency across all segments. Minimum 2-3 reference images per main character (front face, full body, profile).

### Question 6: Setting and Location

> "Where does this video take place? Describe the locations or settings. It can be one location or multiple. For example: 'A modern doctor's office, then transitions to a beach scene, then ends in a cozy living room.' I'll create reference images for each setting to keep the environments consistent."

**What you're looking for:** Location descriptions that become setting anchor images. Each unique location needs 1-2 reference images.

### Question 7: Key Scenes or Moments

> "Are there any specific scenes or moments you absolutely want in this video? Maybe a dramatic reveal, a funny punchline, a transformation moment, or a specific action sequence? This is where you tell me the moments that MUST be in the final product."

**What you're looking for:** Non-negotiable creative beats. These get mapped to specific segments in the storyboard.

### Question 8: Audio and Music

This question has multiple parts. Ask them in sequence:

> **8a:** "Let's talk about the sound design. Do you want sound effects as part of the video? Things like footsteps, door opening, ambient office noise, dramatic swooshes, applause - stuff that makes the scenes feel real and alive?"

Wait for answer.

> **8b:** "What about music? Do you want background music playing during the video? If so, should it play throughout the entire video, or just during certain parts? What style of music are you thinking? (Upbeat pop, cinematic orchestral, soft piano, hip hop, etc.)"

Wait for answer.

> **8c:** "Now for dialogue - do you want me to write the scripts that the characters will be speaking in the video, or do you already have the dialogue written? If you have it, send it over. If not, I'll write it based on everything you've told me so far."

Wait for answer.

> **8d:** "Last audio question - is there a narrator in this video? A narrator is a voice that speaks OVER the video but isn't one of the characters on screen. Think of it like:
> - **Dukes of Hazzard style** - a warm, storytelling voice that guides you through what's happening ('Now ol' Bo and Luke didn't know what was comin' next...')
> - **Sex and the City style** - a reflective, personal voice that adds inner thoughts and commentary ('I couldn't help but wonder...')
> - **Pharmaceutical ad style** - a smooth, professional voice delivering information while lifestyle footage plays
>
> If you want a narrator, do you want me to write the narrator script or do you already have it written?"

**What you're looking for:** Whether narration exists, the style of narration, and whether the agent needs to write it.

**CRITICAL RULE: Narrator voiceover and character dialogue NEVER overlap in the same segment.** If a segment has characters speaking on screen (lips moving), there is no narrator in that segment. If a segment has narrator voiceover, characters on screen do NOT speak (no lip movement). This is a hard rule - mixing them sounds amateur and confusing.

### Question 8e: Text Overlays and Captions

> "Do you want any text on screen during the video? This could be:
> - **Captions/subtitles** - text showing what's being said (great for social media since most people watch on mute)
> - **Title cards** - a bold title at the beginning
> - **Call-to-action text** - something like 'Book Now' or 'Link in Bio' at the end
> - **Lower thirds** - name/title bars when characters appear ('Dr. Sarah Mitchell, Financial Strategist')
> - **Key phrases or stats** that appear on screen to emphasize a point
>
> Don't worry about the exact wording right now - we'll dial that in later. I just need to know what types of text you want so I can plan for it."

**What you're looking for:** Whether post-production text overlays are needed. Text is NOT generated by VEO (AI video is bad at text rendering). All text overlays are added AFTER video assembly using FFmpeg text filters or the caption skill. This question just establishes the intent so the agent knows to offer it after delivery.

**Technical note:** Captions/subtitles can be auto-generated from the audio track using Whisper (speech-to-text) and burned onto the video with FFmpeg. Custom text overlays are positioned manually with FFmpeg drawtext filters.

### Question 8f: Logo and Branding

> "Do you have a logo or brand watermark you want on the video? If so, send me the image file (PNG with transparent background works best). I can place it:
> - **Throughout the entire video** - small watermark in a corner
> - **Intro/outro only** - logo appears at the beginning and/or end
> - **End card only** - logo on the final 'Thank You' or CTA screen
>
> If you don't have a logo, no problem - we'll skip this."

**What you're looking for:** Whether branding needs to be overlaid. Like text, logos are NOT generated by VEO (it will butcher the spelling and design). The actual logo file is overlaid on the finished video using FFmpeg's overlay filter. The agent needs the logo image file and placement preference.

### Question 9: Reference Images

> "Do you have any reference images for the characters or settings? These could be:
> - **Photos of real people** the characters should look like
> - **AI-generated images** you've already created
> - **Mood board images** showing the visual style you want
>
> If you have images, you can:
> 1. **Send me the link** if they're already in your GHL/Convert and Flow media library or hosted somewhere online
> 2. **Send me the actual image file** and I'll upload it to your media library for you
>
> If you don't have any reference images, that's fine - I'll generate them based on your character and setting descriptions."

**Media library handling:**
- If user has GHL/Convert and Flow: Upload via their Private Integration Token (PIT). GHL does NOT use API keys - it uses PITs.
- If user does NOT have GHL/Convert and Flow: imgBB (free) is fine for **reference images** — it gives permanent image hosting links. It is a REFERENCE-IMAGE host and only that: it hosts still images and animated GIFs, and will not host the final MP4. For the finished video the client needs a VIDEO-CAPABLE store they control (their own object storage or CDN, their site's media library, or a video host they own); ask for that separately at intake so delivery is not blocked at the end.
- Always prefer GHL/Convert and Flow if available - it keeps everything in one ecosystem.

### Question 10: Intended Use Case

> "Last question - what's the intended purpose of this video? Where are you planning to use it? For example:
> - **Facebook ad** (paid promotion)
> - **Instagram Reel** (organic social content)
> - **Google/YouTube ad** (paid search/video ad)
> - **Website landing page** (brand/sales video)
> - **Email marketing** (embedded in emails or linked)
> - **TikTok** (organic social)
> - **Presentation or pitch deck** (business use)
> - **General brand awareness** (multi-platform)
>
> This helps me optimize the video format, pacing, and call-to-action for your specific platform. A Facebook ad has different requirements than an Instagram Reel, which is different from a YouTube pre-roll."

**What you're looking for:** Platform-specific optimization. This affects:
- Aspect ratio priority (9:16 for Reels/TikTok, 16:9 for YouTube/web, 1:1 for feed posts)
- Pacing (ads need hooks in first 3 seconds, organic content can build slower)
- CTA placement (ads need clear CTAs, organic content can be softer)
- Duration constraints (platform-specific max lengths)

### Question 11: Call to Action

> "What do you want the viewer to DO after watching this video? Every good video drives the viewer toward a specific action. For example:
> - 'Book a free consultation' (with a link or phone number)
> - 'Follow us on Instagram @handle'
> - 'Visit our website at example.com'
> - 'DM me the word READY'
> - 'Click the link in bio'
> - 'Share this with a friend who needs to hear this'
>
> This determines what goes on your end card and any text overlays. If you don't have a specific CTA, we can make the ending more general - but videos with a clear CTA perform significantly better."

**What you're looking for:** The specific action and any associated URLs, handles, phone numbers, or keywords. This directly shapes the final segment (end card) and any CTA text overlays.

### Question 12: Inspiration or Reference Videos (Optional)

> "This one's optional but really helpful - have you seen any videos that feel similar to what you're going for? It could be a competitor's ad, a viral reel, a movie scene, a commercial - anything that made you think 'I want something like THAT.' If you have a link, send it over. Even if it's just the vibe or energy you liked, not the exact content.
>
> I can actually watch the video and analyze the style, pacing, colors, and transitions so I can match that feel for yours. If you don't have any references, no problem - I'll work from everything else you've told me."

**What you're looking for:** Visual and tonal references. These are gold for the agent - instead of guessing what "cinematic and empowering" looks like in the user's head, you can see what they actually respond to.

**How the agent analyzes a reference video:**

**Required skills for Q12 analysis:**
Before attempting to analyze a reference video, check that these two skills are installed:

1. **video-frames** - Extracts frames from video files using FFmpeg
   - Check: `ls ~/.npm-global/lib/node_modules/openclaw/skills/video-frames/` or `ls ~/.openclaw/skills/video-frames/`
   - If not installed: `brew install ffmpeg` (the skill ships with OpenClaw but needs FFmpeg)

2. **summarize** - Transcribes/summarizes YouTube videos and URLs
   - Check: `which summarize`
   - If not installed: `brew install steipete/tap/summarize`
   - Also needs at least one API key set: `GEMINI_API_KEY` or `OPENAI_API_KEY`

If either skill is missing, install it. Do NOT skip the analysis just because a tool isn't there - get the tool and do the job.

**Installation and self-teaching instructions:**

**video-frames** (frame extraction from videos):
- This skill ships with OpenClaw but requires FFmpeg as a dependency
- GitHub: https://github.com/FFmpeg/FFmpeg
- Install FFmpeg: `brew install ffmpeg` (macOS) or `sudo apt install ffmpeg` (Ubuntu/Debian)
- The skill itself is at: `~/.npm-global/lib/node_modules/openclaw/skills/video-frames/`
- If the skill folder doesn't exist, FFmpeg alone is sufficient - the agent can run frame extraction directly:
  ```bash
  ffmpeg -i /path/to/video.mp4 -ss 00:00:30 -frames:v 1 /tmp/frame_30s.jpg
  ```
- After installing, use the Teach Yourself Protocol to learn the skill: read the SKILL.md, write a lightweight summary in TOOLS.md, note it in MEMORY.md

**summarize** (transcript/summary extraction from YouTube and URLs):
- GitHub: https://github.com/steipete/summarize
- Install: `brew install steipete/tap/summarize`
- Requires at least one LLM API key: `GEMINI_API_KEY` or `OPENAI_API_KEY`
- Key usage for video analysis:
  ```bash
  # Get transcript/summary from YouTube
  summarize "https://youtube.com/watch?v=XXXXX" --youtube auto --length medium
  
  # Extract transcript only (no summary)
  summarize "https://youtube.com/watch?v=XXXXX" --youtube auto --extract-only
  ```
- After installing, use the Teach Yourself Protocol to learn the skill: read `summarize --help`, write a lightweight summary in TOOLS.md, note it in MEMORY.md
- Optional but recommended: set `APIFY_API_TOKEN` for YouTube fallback transcript extraction

**Image analysis** (visually analyzing extracted frames):
- This is a built-in capability of the agent (uses the vision/image model)
- No installation needed - the agent can analyze images natively
- If the agent's current model does not support image analysis, switch to a client-available vision model (Ollama Cloud first — never Anthropic): `ollama/qwen3-vl:235b-cloud` or `ollama/minimax-m3:cloud` (primary), `openrouter/qwen/qwen3-vl-235b-a22b-instruct` or `google/gemini-3.1-pro-preview` (fallback) all support vision

**The self-teaching flow:**
1. Agent detects the missing skill
2. Agent tells the user: "To analyze your reference video, I need to install a tool. Let me set that up now."
3. Agent installs the tool (brew install or direct download)
4. Agent activates the Teach Yourself Protocol to learn the new skill
5. Agent writes lightweight summaries in its core files so it knows the skill exists in future sessions
6. Agent proceeds with the Q12 video analysis

This ensures the skill is not just installed but LEARNED - the agent will know how to use it in every future session, not just this one.

The agent does NOT need to watch the entire video. Even for a 40-minute video, the first 2-3 minutes contain enough information to extract the visual style, pacing, and tone.

1. **Get the video transcript/summary** using the `summarize` skill:
   ```bash
   summarize "https://youtube.com/watch?v=XXXXX" --youtube auto --length medium
   ```
   This gives the agent the content/message of the video without needing to watch it all.

2. **Extract key frames** from the first 2-3 minutes using the `video-frames` skill:
   ```bash
   # Extract frames at strategic timestamps (intro, 30s, 60s, 90s, 120s)
   video-frames /path/to/video.mp4 --time 00:00:03 --out /tmp/ref_frame_1.jpg
   video-frames /path/to/video.mp4 --time 00:00:30 --out /tmp/ref_frame_2.jpg
   video-frames /path/to/video.mp4 --time 00:01:00 --out /tmp/ref_frame_3.jpg
   video-frames /path/to/video.mp4 --time 00:01:30 --out /tmp/ref_frame_4.jpg
   video-frames /path/to/video.mp4 --time 00:02:00 --out /tmp/ref_frame_5.jpg
   ```

3. **Visually analyze the extracted frames** using the image analysis tool. Look for:
   - Color palette (warm/cool, saturated/muted, specific dominant colors)
   - Lighting style (soft/harsh, natural/studio, backlit/front-lit)
   - Composition (centered subjects, rule of thirds, wide shots vs close-ups)
   - Text style (font weight, placement, animation style, colors)
   - Overall energy (clean and minimal, busy and dynamic, cinematic and moody)
   - Transition patterns (hard cuts, dissolves, wipes)

4. **Summarize findings to the user:**
   > "I watched your reference video. Here's what I picked up on the style:
   > - Warm color palette with golden tones
   > - Mix of close-up face shots and wide lifestyle shots
   > - Bold white text overlays with subtle drop shadow
   > - Fast cuts (2-3 seconds per shot) building energy
   > - Cinematic orchestral music underneath
   >
   > I'll match this feel for your video. Sound right?"

**If the reference is a YouTube link:** Use `summarize` with `--youtube auto` to get the transcript, then download the first 3 minutes for frame extraction.

**If the reference is a direct video file:** Use `video-frames` directly for frame extraction.

**If the reference is a social media link (Instagram, TikTok):** Try to download via the URL. If that fails, ask the user to screen-record a 30-second clip and send the file directly.

**Cap analysis at 3 minutes.** No matter how long the reference video is, the agent only needs the first 2-3 minutes. The visual style, pacing, and tone are established in the opening. Don't waste time analyzing a 40-minute video.

### Question 13: Timeline

> "When do you need this video finished by? If you have a specific deadline - like a launch date, an event, or a campaign start - let me know so I can plan the production timeline accordingly. If there's no rush, I'll prioritize quality over speed."

**What you're looking for:** Urgency level. This affects whether the agent generates segments sequentially (higher quality, slower) or finds ways to parallelize. It also sets expectations - a 90-second video takes approximately 30-45 minutes of generation time, plus revision cycles.

### Question 14: Anything Else?

> "That's all my structured questions. Before I start building, is there anything else that's important to you about this video that I haven't asked about? Any specific requirements, brand colors, phrases that must be included, or anything at all that would affect how I create this? Now's the time to tell me - it's much easier to build it right the first time than to fix it later."

**What you're looking for:** Anything the structured questions missed. Brand colors, specific fonts for text overlays, competitor references ("make it look like X but not Y"), legal disclaimers, specific hashtags for the post, or creative preferences the user didn't get to express earlier. This is the catch-all safety net.

---

## POST-INTAKE: PRODUCTION PIPELINE

After all 14 questions are answered, the agent proceeds through these phases:

### Phase 0: Project Setup and Budget Confirmation

**Before any generation begins, the agent MUST:**

0. **Resolve platform-correct paths.** This skill runs on both a Mac and a headless VPS — the presence of `/data/.openclaw` means VPS (a VPS Docker container has no `~/Downloads`). Set the secrets file, output root, and skills dir from the platform, source the secrets ONCE here, and resolve binaries with `command -v` rather than hardcoding paths:
   ```bash
   if [ -d /data/.openclaw ]; then
     SECRETS_ENV="/data/.openclaw/secrets/.env"          # VPS
     OUTPUT_ROOT="/data/cinematic-forge-projects"
     SKILL_DIR="/data/.openclaw/skills/28-cinematic-forge"
   else
     SECRETS_ENV="$HOME/.openclaw/secrets/.env"           # Mac
     OUTPUT_ROOT="$HOME/Downloads/cinematic-forge-projects"
     SKILL_DIR="$HOME/.openclaw/skills/28-cinematic-forge"
   fi
   [ -f "$SECRETS_ENV" ] && { set -a; . "$SECRETS_ENV"; set +a; }   # loads KIE_API_KEY, GOHIGHLEVEL_API_KEY, GOHIGHLEVEL_LOCATION_ID, etc.
   FFMPEG="$(command -v ffmpeg)"; FFPROBE="$(command -v ffprobe)"
   ```
   Use `$OUTPUT_ROOT` as the project root, `$SECRETS_ENV` for every credential load below, and `$SKILL_DIR` to locate this skill's helper scripts (e.g. `qc-output.sh`).

1. **Create the project folder structure:**
   ```
   $OUTPUT_ROOT/[project-name]/
     images/          (reference images, start images, derived images)
     segments/        (individual VEO video segments)
     audio/
       dialogue/      (character voice clips)
       narrator/      (narrator voiceover clips)
       sfx/           (sound effects)
       music/         (background music tracks)
     final/           (merged video, upscaled versions)
     project-state.json  (session recovery file - see below)
   ```

   The `[project-name]` is derived from the concept (kebab-case). Example: `money-shame-syndrome`, `beach-lifestyle-reel`.

2. **Check KIE.ai credit balance** (credentials were loaded from `$SECRETS_ENV` in step 0):
   ```bash
   curl -s "https://api.kie.ai/api/v1/user/credits" \
     -H "Authorization: Bearer $KIE_API_KEY"
   ```
   If the balance is insufficient for the estimated cost, tell the user BEFORE starting. Do not begin generation and fail at segment 6 because credits ran out.

3. **Calculate and present the budget estimate:**

   > "Based on what you've described, here's the approximate cost and timeline:
   >
   > **Video:** [X] segments x $0.40 = $[Y] (VEO 3.1 Fast)
   > **Reference Images:** ~[X] images x $0.10 = $[Y] (Nano Banana Pro)
   > **Voice/Dialogue:** ~[X] clips x $0.15 = $[Y] (ElevenLabs)
   > **Sound Effects:** ~[X] clips x $0.10 = $[Y] (ElevenLabs SFX)
   > **Music:** ~[X] tracks x $0.35 = $[Y] (Suno)
   > **Estimated Total: ~$[TOTAL]**
   >
   > **Estimated Production Time:** [X] minutes for video generation, [X] minutes for audio, [X] minutes for assembly. Total approximately [X] minutes from start to finished video.
   >
   > Your current KIE.ai balance is [X] credits ($[Y]). [Sufficient / You'll need to add credits before we start.]
   >
   > Want me to proceed?"

   **Do NOT start generation until the user confirms.** Once the user confirms the budget, if this job is tracked on the Command Center board, move its task to `in_progress` (see **COMMAND CENTER (KANBAN) INTEGRATION** below). If KIE credits are insufficient, return the task to the orchestrator instead of starting.

4. **Write the DELIVERY REQUIREMENTS RECORD — before any generation starts.**

   Everything the delivery gate later checks the finished file against comes from
   the *approved intake*, not from whatever numbers the caller happens to pass at
   delivery time. Derive the record the moment the client approves the budget and
   the brief, and never edit it afterwards:

   ```bash
   mkdir -p "$PROJECT/final/receipts"
   cat > "$PROJECT/final/delivery-requirements.json" <<JSON
   {
     "approval_ref": "intake-approved-<YYYY-MM-DDTHH:MM:SSZ>",
     "aspect_ratio": "9:16",
     "dimensions": "1080x1920",
     "duration_seconds": 90,
     "duration_tolerance_seconds": 0.75,
     "requires_captions": true,
     "requires_text_overlays": false,
     "requires_logo": true
   }
   JSON
   ```

   - `aspect_ratio` / `dimensions` / `duration_seconds` come from Questions 3, 4
     and 8; the three `requires_*` flags come from Questions 8e and 8f. Set a
     flag `true` only if the client asked for that thing.
   - `approval_ref` is the client's approval. Without it the delivery gate
     refuses to certify anything — a requirements record that is not bound to an
     approval attests to nothing.

   **Why this exists (T0-46).** The output gate's contract is "safe to deliver",
   and every value it used to compare against was supplied by its own caller. A
   correctly encoded video of the wrong length, the wrong aspect ratio, or
   missing every requested overlay passed, because the caller passed in the
   numbers it wanted checked. The certification was real; what it certified was
   that the file is a video.

5. **Initialize the project state file** (`project-state.json`):
   ```json
   {
     "project_name": "money-shame-syndrome",
     "created": "2026-02-23T22:45:00Z",
     "status": "pre-production",
     "intake_answers": { ... },
     "segments": [
       { "number": 1, "status": "pending", "taskId": null, "file": null },
       { "number": 2, "status": "pending", "taskId": null, "file": null }
     ],
     "audio": {
       "dialogue": [],
       "narrator": [],
       "sfx": [],
       "music": []
     },
     "voice_ids": {},
     "reference_images": [],
     "total_cost": 0,
     "final_video": null
   }
   ```
   
   **Why this exists:** If the session dies mid-production (compaction, crash, timeout), a new session can read this file and resume exactly where it left off. Update this file after EVERY completed step (segment generated, audio clip created, etc.).

### Phase 1: Pre-Production

1. **Summarize the intake** back to the user for confirmation
2. **Create the storyboard** - map each segment (8 seconds each) with:
   - Scene description
   - Characters present
   - Audio type (dialogue, narration, SFX, music)
   - Camera/motion notes
3. **Generate anchor reference images** using Nano Banana Pro via KIE.ai
   - Minimum 2-3 per main character (front face, full body, profile)
   - 1-2 per unique setting/location
   - Upload all to media library, save permanent URLs
4. **Write scripts** (if agent is writing them):
   - Character dialogue for speaking segments
   - Narrator script for voiceover segments
   - NEVER overlap narrator and character dialogue in the same segment
5. **Voice selection:**
   - Ask the user: "Do you want me to select voices that match your characters, or would you like me to give you a few options to choose from?"
   - If the user wants options: Present 2-3 ElevenLabs voice samples per character with descriptions (e.g., "Warm, confident African-American woman, mid-30s" or "Deep, authoritative male narrator")
   - If the user wants the agent to choose: Select voices that best match the character descriptions from intake and confirm the choices
   - Lock the voice IDs once selected - the same voice ID is used for every clip of that character throughout the entire video
6. **Get user approval** on storyboard, reference images, scripts, and voice selections before proceeding

### Phase 2: Video Generation

**Model:** VEO 3.1 Fast via KIE.ai (`veo3_fast`)
**Cost:** $0.40 per 8-second segment
**Aspect ratio:** 9:16 vertical (primary). 16:9 horizontal created ONLY after 9:16 is approved.

1. **Segment 1:** VEO 3.1 Fast Image-to-Video using Nano Banana Pro start image
   - `generationType: "FIRST_AND_LAST_FRAMES_2_VIDEO"` with one imageUrl (start image only)
   - Establishes characters and initial scene
2. **Segments 2+:** VEO 3.1 Fast Extend from previous segment's taskId
   - `POST https://api.kie.ai/api/v1/veo/extend`
   - Requires: taskId (from previous segment), prompt (scene description), model: "fast"
   - Scene changes driven by prompt cues ("dissolve to beach scene", "transition to home setting")
   - No start or end images needed - VEO maintains internal state
3. **Final segment:** Generate full 8 seconds, but will be trimmed in FFmpeg to hit exact target duration
   - Design final segment as a static card (logo, "Thank You", CTA) so trimming doesn't cut mid-action
4. **Poll each segment** until complete:
   - `GET https://api.kie.ai/api/v1/veo/record-info?taskId=XXX`
   - Check `successFlag` - 0 = processing, 1 = complete
   - Poll every 20-30 seconds
5. **Download completed segments** to the project folder (`segments/segment_N.mp4`)
6. **Send progress updates to the user** after each segment completes:
   > "Segment 4 of 12 complete. Estimated 8 minutes remaining. Cost so far: $1.60"
   
   Don't leave the user waiting in silence. Every completed segment gets an update.
7. **Update project-state.json** after each segment (taskId, file path, status)
8. **Validate each segment** before proceeding to the next:
   - Character consistency vs reference images
   - Scene matches storyboard description
   - No visual artifacts or glitches
   - If segment fails validation, regenerate before extending

### Phase 3: Audio Production

Audio is generated SEPARATELY from video. VEO's built-in audio is DISCARDED and replaced entirely.

**Why:** VEO generates a different voice every segment. By segment 6, the narrator sounds like a completely different person. Generating audio separately with locked voice IDs ensures consistency.

**Audio Layers:**

1. **Character Dialogue** (ElevenLabs Text-to-Speech via KIE.ai)
   - One locked voice ID per character - same voice every segment
   - Only in segments where characters speak on screen (lips moving)
   - `POST https://api.kie.ai/api/v1/jobs/create` with model `eleven_multilingual_v2`

2. **Narrator Voiceover** (ElevenLabs Text-to-Speech via KIE.ai)
   - One locked voice ID for the narrator - never changes
   - Only in segments where NO characters are speaking on screen
   - NEVER overlaps with character dialogue in the same segment

3. **Sound Effects** (ElevenLabs Sound Effects via KIE.ai)
   - Ambient sounds (office noise, beach waves, crowd murmur)
   - Action sounds (footsteps, door opening, pen writing)
   - Transition sounds (swooshes, impacts)
   - `POST https://api.kie.ai/api/v1/jobs/create` with model `eleven_sound_effects`

4. **Background Music** (Suno via KIE.ai)
   - Generated based on user's music preferences from Question 8b
   - Plays underneath dialogue/narration at 20-30% volume
   - NOT in every segment - only where appropriate
   - `POST https://api.kie.ai/api/v1/jobs/create` with model `suno_v4`

### Phase 4: Assembly (FFmpeg)

1. **Strip VEO audio** from all video segments:
   ```bash
   ffmpeg -i segment_N.mp4 -an -c:v copy segment_N_silent.mp4
   ```

2. **Trim final segment** to hit exact target duration:
   ```bash
   ffmpeg -i segment_last.mp4 -t [REMAINING_SECONDS] -c copy segment_last_trimmed.mp4
   ```

3. **Create concat list** and merge all video segments:
   ```bash
   # concat_list.txt:
   file 'segment_1_silent.mp4'
   file 'segment_2_silent.mp4'
   ...
   file 'segment_N_trimmed_silent.mp4'

   ffmpeg -f concat -safe 0 -i concat_list.txt -c copy merged_video.mp4
   ```

4. **Mix audio layers** with the silent video:
   ```bash
   ffmpeg -i merged_video.mp4 \
     -i dialogue_track.aac \
     -i narrator_track.aac \
     -i sfx_track.aac \
     -i music_track.aac \
     -filter_complex "[1:a][2:a][3:a]amix=inputs=3:duration=longest[voice_sfx]; \
       [voice_sfx][4:a]amix=inputs=2:duration=longest:weights=1 0.25[final_audio]" \
     -map 0:v -map "[final_audio]" \
     -c:v copy -c:a aac \
     final_video.mp4
   ```
   
   Note: Music volume is set to ~25% (weight 0.25) so it supports but doesn't compete with voices.

5. **Verify final duration:**
   ```bash
   ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 final_video.mp4
   ```

6. **Establish the ONE authoritative final artifact, then run the TECHNICAL gate.**

   ```bash
   # THE authoritative artifact variable. Every later stage reads and advances
   # THIS; nothing downstream ever names a fixed filename again.
   FINAL_ARTIFACT="$PROJECT/final/final_video.mp4"

   bash "$SKILL_DIR/qc-output.sh" "$FINAL_ARTIFACT" <target_seconds> <WIDTHxHEIGHT>
   # example for a 90s 9:16 assembly:
   bash "$SKILL_DIR/qc-output.sh" "$FINAL_ARTIFACT" 90 1080x1920
   ```

   In this positional form `qc-output.sh` runs TECHNICAL checks only: the file
   exists and is non-empty, the resolution matches, BOTH a video and an audio
   stream are present, the audio is non-silent (proving the VEO audio was
   actually replaced, not silently dropped), and the duration is within 0.75s of
   what you told it to expect. It prints, in as many words, that this is **not**
   a delivery verdict — every number it compared against came from you.

   If it exits non-zero, FIX the problem (re-mix audio, re-trim, or re-render the
   offending segment) and re-run. **The delivery gate runs after post-production,
   in Phase 6 — not here.** (`$SKILL_DIR` was resolved in Phase 0.)

### Phase 5: Text Overlays, Captions, and Logo (Post-Production)

This phase only runs if the user requested text overlays, captions, or logo
placement during intake (Questions 8e and 8f) — that is, if the corresponding
`requires_*` flag in `final/delivery-requirements.json` is `true`.

**THE RULE THAT MAKES THIS PHASE CORRECT.** Every transformation reads
`$FINAL_ARTIFACT`, writes a NEW file, and — only if the command SUCCEEDS —
advances `$FINAL_ARTIFACT` to that new file and writes a receipt. Nothing after
this phase ever names a fixed filename.

**Why (T0-47).** Captions used to be written to `final_video_captioned.mp4` and
the logo overlay to `final_video_branded.mp4` — and then Phase 6 uploaded
`final_video.mp4`. Both transformations read the ORIGINAL file and wrote
elsewhere; the upload read the original. The work was performed correctly,
verified correctly, and then the un-transformed file was the one that shipped.
Every stage reported success, and the pipeline's own records said the client's
captions and branding had been delivered.

Use this helper for every step in this phase:

```bash
# apply_step <step-name> <output-path> <ffmpeg args...>
#   Runs the transformation from the CURRENT $FINAL_ARTIFACT, advances the
#   variable only on success, and writes the receipt the delivery gate reads.
apply_step() {
  local step="$1" out="$2"; shift 2
  local in="$FINAL_ARTIFACT"
  local in_sha; in_sha="$(shasum -a 256 "$in" | awk '{print $1}')"

  if ! "$FFMPEG" -y -i "$in" "$@" "$out"; then
    echo "POST-PRODUCTION FAILED at step '$step' — NOT advancing the final artifact." >&2
    return 1
  fi
  [ -s "$out" ] || { echo "step '$step' produced an empty file" >&2; return 1; }

  local out_sha; out_sha="$(shasum -a 256 "$out" | awk '{print $1}')"
  mkdir -p "$PROJECT/final/receipts"
  cat > "$PROJECT/final/receipts/$step.json" <<JSON
{
  "step": "$step",
  "input": "$in",
  "input_sha256": "$in_sha",
  "output": "$out",
  "output_sha256": "$out_sha",
  "completed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
JSON
  FINAL_ARTIFACT="$out"          # <-- the ONLY place this variable advances
  echo "step '$step' applied; final artifact is now $FINAL_ARTIFACT"
}
```

1. **Auto-generated captions/subtitles** (if `requires_captions`):
   - Extract audio from the assembled video
   - Run through Whisper (speech-to-text) to generate the subtitle file (`.srt`)
   - Burn the subtitles onto the CURRENT artifact:
   ```bash
   apply_step captions "$PROJECT/final/final_video_captioned.mp4" \
     -vf "subtitles=captions.srt:force_style='FontSize=24,FontName=Arial,PrimaryColour=&Hffffff,OutlineColour=&H000000,Outline=2,MarginV=40'" \
     -c:a copy
   ```

2. **Custom text overlays** (title cards, CTAs, lower thirds — if `requires_text_overlays`):
   ```bash
   apply_step text_overlays "$PROJECT/final/final_video_text.mp4" \
     -vf "drawtext=text='Book Your Free Consultation':fontsize=48:fontcolor=white:borderw=3:bordercolor=black:x=(w-text_w)/2:y=h-120:enable='between(t,85,90)'" \
     -c:a copy
   ```
   - Position and timing come from the storyboard
   - The user approves text placement before finalizing

3. **Logo overlay** (if `requires_logo`):
   ```bash
   # Corner watermark (entire video)
   apply_step logo "$PROJECT/final/final_video_branded.mp4" \
     -i logo.png -filter_complex "overlay=W-w-20:20" -c:a copy

   # End card only (last 5 seconds) — use INSTEAD of the watermark, not as well
   # apply_step logo "$PROJECT/final/final_video_branded.mp4" \
   #   -i logo.png -filter_complex "overlay=(W-w)/2:(H-h)/2:enable='gte(t,85)'" -c:a copy
   ```

4. **If the user needs a more advanced caption/subtitle skill**, recommend the caption skill or video-editor skill for additional formatting options (animated text, custom fonts, word-by-word highlighting, etc.). Cinematic Forge handles basic overlays; complex motion graphics are a separate workflow.

At the end of this phase, `$FINAL_ARTIFACT` names the file that carries every
requested transformation, and `final/receipts/` holds one receipt per applied
step. Both are what Phase 6 delivers and what the delivery gate reads.

### Phase 6: Upload and Delivery

**0. RUN THE DELIVERY GATE — on `$FINAL_ARTIFACT`, after post-production, before the upload.**

```bash
bash "$SKILL_DIR/qc-output.sh" \
  --artifact     "$FINAL_ARTIFACT" \
  --requirements "$PROJECT/final/delivery-requirements.json" \
  --receipts     "$PROJECT/final/receipts"
```

This is the only mode that says "safe to deliver". It checks the artifact
against the requirements record derived from the APPROVED intake — approved
aspect ratio, approved duration, and every overlay the client actually asked for
— and requires, for each requested transformation, a receipt whose output hash
IS this artifact. A file that skipped a transformation, or a transformation
applied to some other file, cannot pass. If it exits non-zero, fix the pipeline
and re-run: **do not upload, and do not send a link.**

1. **Upload `$FINAL_ARTIFACT` to the client's GHL/Convert and Flow Media Library.** Credentials come from the platform-correct secrets file resolved in Phase 0 (`$SECRETS_ENV`): the Private Integration Token is `GOHIGHLEVEL_API_KEY` and the sub-account is `GOHIGHLEVEL_LOCATION_ID`. Pass the location (the v2 endpoint behaves differently for agency vs sub-account tokens — omitting it is fragile), check the HTTP status, KEEP THE WHOLE RESPONSE BODY, and retry ONCE on failure before reporting. Never assume the upload succeeded.
   ```bash
   : "${GOHIGHLEVEL_API_KEY:?set GOHIGHLEVEL_API_KEY in $SECRETS_ENV}"
   : "${GOHIGHLEVEL_LOCATION_ID:?set GOHIGHLEVEL_LOCATION_ID in $SECRETS_ENV}"

   upload_to_ghl() {
     curl -sS -w $'\n%{http_code}' -X POST \
       "https://services.leadconnectorhq.com/medias/upload-file" \
       -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
       -H "Version: 2021-07-28" \
       -F "file=@$FINAL_ARTIFACT" \
       -F "hosted=true" \
       -F "locationId=$GOHIGHLEVEL_LOCATION_ID" \
       -F "fileProcessingOpts={\"forceReprocess\": true}"
   }

   RAW="$(upload_to_ghl)"; CODE="$(printf '%s' "$RAW" | tail -n1)"; BODY="$(printf '%s' "$RAW" | sed '$d')"
   if [ "$CODE" != "200" ] && [ "$CODE" != "201" ]; then
     sleep 3                                    # one retry
     RAW="$(upload_to_ghl)"; CODE="$(printf '%s' "$RAW" | tail -n1)"; BODY="$(printf '%s' "$RAW" | sed '$d')"
   fi
   if [ "$CODE" = "200" ] || [ "$CODE" = "201" ]; then
     printf '%s' "$BODY" > "$PROJECT/final/upload-response.json"
   else
     echo "GHL upload FAILED (HTTP $CODE). Response: $BODY" >&2
     # Do not deliver — surface the failure to the operator and stop.
   fi
   ```

   - The upload is performed on `$FINAL_ARTIFACT`, the same variable the gate
     just certified — never on a fixed filename.
   - **Verify the HOSTED object before sending anything**, by re-running the
     delivery gate with the saved response:
     ```bash
     bash "$SKILL_DIR/qc-output.sh" \
       --artifact        "$FINAL_ARTIFACT" \
       --requirements    "$PROJECT/final/delivery-requirements.json" \
       --receipts        "$PROJECT/final/receipts" \
       --upload-response "$PROJECT/final/upload-response.json"
     ```
     The gate resolves the asset IDENTIFIER the upload returned, requires the
     response's own filename/size metadata to match the artifact, downloads the
     object bound to that identifier, and probes it against the same approved
     requirements. **Why (T0-48):** the old check was a ranged request for the
     first byte plus a content-type match, on a URL grepped out of the response
     body — any reachable video URL satisfied it, including a previous client's
     asset or a stale upload. It confirmed only that the host was up.
   - Read the link to send from the verified response:
     ```bash
     MEDIA_URL="$(jq -r '.url // .fileUrl // .location // .data.url' "$PROJECT/final/upload-response.json")"
     ```
   - **If the client has no GHL/Convert and Flow:** host the finished MP4 on a
     real VIDEO-CAPABLE store the client controls — their own object storage or
     CDN (S3/R2/GCS + a CDN), their own site's media library, or a video host
     they own. Verify it exactly the same way: the store's upload response must
     yield an asset identifier and a URL bound to it, and the gate must download
     and probe the hosted object. **Never imgBB for the final video** — imgBB
     hosts still images and animated GIFs only and will not host an MP4. imgBB is
     a REFERENCE-IMAGE host, and only that (Q9).

2. **Return the link to the user** in the same channel where they started the conversation (Telegram, Slack, etc.):

   > "Your video is ready! Here's the link: $MEDIA_URL
   >
   > Watch it and let me know:
   > - Want any changes? I can re-generate specific segments, adjust audio, or make edits.
   > - Happy with it? We can move to the next step - upgrading the quality."

   After the draft link is delivered, if this job is tracked on the Command Center board, move its task to `review` (see **COMMAND CENTER (KANBAN) INTEGRATION**). The builder must NOT self-promote the task to `done` — the independent QC scorer advances it.

3. **Handle revision requests:**
   - User identifies specific segments or issues
   - Re-generate only the affected segments
   - Re-assemble with FFmpeg, then re-run Phase 5 so `$FINAL_ARTIFACT` and the
     receipts describe the NEW file
   - Re-run the delivery gate, re-upload and return the new link

4. **Topaz upscale (after user approves the draft):**
   - Offer 1080p or 4K upgrade
   - Use Topaz Video AI for quality upscaling
   - Only AFTER the user has approved the content - don't waste upscale processing on drafts

### Phase 7: Two-Version Workflow (If Applicable)

1. **9:16 vertical** is ALWAYS created first (primary format for social media)
2. Only AFTER 9:16 is approved, create the **16:9 horizontal** version if needed
3. Each version gets its own upload and link

---

## COMMAND CENTER (KANBAN) INTEGRATION — OPTIONAL

Some client boxes run a local Command Center (mission-control Kanban). A video build is a long-running, multi-phase task that belongs on that board. This integration is **optional and reachability-gated**: if the Command Center is not reachable, or no task token is set, **skip every step below silently** — never mention it to the client and never block the build on it.

**Gate (evaluate once; cache the result):**
```bash
CC_OK=0
if [ -n "${MC_API_TOKEN:-}" ] && curl -fsS -m 5 localhost:4000/api/health >/dev/null 2>&1; then CC_OK=1; fi
```

**Helpers — HTTP only. NEVER write the Command Center SQLite DB directly; that bypasses the board's gates, QC, and live updates:**
```bash
cc_patch() {                      # cc_patch <task_id> <status>
  [ "$CC_OK" = "1" ] || return 0
  curl -fsS -m 10 -X PATCH "http://localhost:4000/api/tasks/$1" \
    -H "Authorization: Bearer $MC_API_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"status\":\"$2\",\"updated_by_agent_id\":\"${AGENT_ID:-cinematic-forge}\"}" >/dev/null 2>&1 || true
}
cc_return_to_orchestrator() {     # cc_return_to_orchestrator <task_id> <reason>
  [ "$CC_OK" = "1" ] || return 0
  curl -fsS -m 10 -X POST "http://localhost:4000/api/tasks/$1/return-to-orchestrator" \
    -H "Authorization: Bearer $MC_API_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"reason\":\"$2\",\"updated_by_agent_id\":\"${AGENT_ID:-cinematic-forge}\"}" >/dev/null 2>&1 || true
}
```

**When to call (only when a Command Center task id is associated with this job):**
- **Budget approved, generation starting** → `cc_patch "$TASK_ID" in_progress` (this auto-fires dispatch; respect the board's Triad before a task leaves backlog).
- **Draft link delivered to the client** → `cc_patch "$TASK_ID" review`. The builder must **NOT** self-promote to `done` — the independent QC scorer / master advances `review` → `done` (a worker that tries to set `done` is rejected with 403).
- **Insufficient KIE credits, or waiting on client approval/assets** → `cc_return_to_orchestrator "$TASK_ID" "<reason>"`. Workers cannot set `blocked` directly (only the master can); return-to-orchestrator is the worker-safe signal.

---

## CRITICAL PRODUCTION RULES

1. **Narrator and character dialogue NEVER overlap** in the same segment. Period.
2. **Character consistency is non-negotiable.** Every segment must match the anchor reference images. If a character's face, hair, or skin tone shifts - regenerate.
3. **VEO 3.1 Fast only.** Do not use VEO 3.1 Quality ($2.00) unless the user explicitly requests it.
4. **9:16 vertical is primary.** Never create 16:9 first.
5. **All VEO audio is discarded.** Replace entirely with ElevenLabs + Suno layers.
6. **Only provide START image to VEO for Segment 1.** End images constrain generation and produce stiff video.
7. **Design the final segment as a static card** (logo, CTA, "Thank You") so FFmpeg trimming doesn't cut mid-action.
8. **No Topaz upscale until the user approves the draft.** Don't waste processing on unapproved content.
9. **The agent executing this skill MUST support tool calls.** Use MiniMax M2.5 or similar. NEVER use Kimi K2.5 (cannot make API calls).
10. **Budget confirmation is MANDATORY.** Never start generation without telling the user the estimated cost and getting their approval.
11. **Check KIE.ai credit balance** before starting. If insufficient, tell the user immediately.
12. **Update project-state.json after EVERY step.** This is how sessions recover from crashes. If you skip this and the session dies, all progress is lost.
13. **Send progress updates** after every completed segment. Never leave the user waiting in silence.
14. **Text and logos are NEVER generated by VEO.** All text overlays, captions, and logo placement happen in post-production via FFmpeg.

---

## SESSION RECOVERY

If the agent starts a new session and finds an existing project-state.json in a cinematic-forge project folder:

1. **Read the project-state.json** to understand where production left off
2. **Report to the user:** "I found an in-progress video project: [project name]. It was at [phase] with [X] of [Y] segments complete. Want me to pick up where I left off?"
3. **Resume from the last completed step** - don't re-generate segments that are already downloaded
4. **Verify existing files** - make sure downloaded segments and audio clips are intact before resuming
5. **If taskIds are available but files weren't downloaded**, re-check the KIE.ai status endpoints to see if the generated content is still available (KIE.ai stores media for 14 days)

---

## COST REFERENCE

| Item | Cost | Notes |
|------|------|-------|
| VEO 3.1 Fast (per segment) | $0.40 | 8 seconds per segment |
| VEO 3.1 Fast Extend (per segment) | $0.40 | Same price as generation |
| Nano Banana Pro (per image) | ~$0.10 | Reference images, start images |
| ElevenLabs TTS (per clip) | ~$0.10-0.30 | Varies by length |
| ElevenLabs SFX (per clip) | ~$0.10 | Sound effects |
| Suno music (per track) | ~$0.20-0.50 | Background music |

**Example: 90-second video**
- 12 segments x $0.40 = $4.80 (video)
- ~12 reference images x $0.10 = $1.20 (images)
- ~12 audio clips x $0.15 = $1.80 (voice/SFX)
- ~1-2 music tracks x $0.35 = $0.70 (music)
- **Total: ~$8.50** (before Topaz upscale)

---

## KIE.ai API REFERENCE

**Base URL:** `https://api.kie.ai/api/v1`
**Auth:** `Authorization: Bearer [KIE_API_KEY]`
**Rate limit:** 20 requests per 10 seconds per account

### Key Endpoints

| Action | Method | Endpoint |
|--------|--------|----------|
| Generate video (VEO) | POST | `/veo/generate` |
| Check video status | GET | `/veo/record-info?taskId=XXX` |
| Extend video (VEO) | POST | `/veo/extend` |
| Generate image (Nano Banana Pro) | POST | `/jobs/create` |
| Check job status | GET | `/jobs/query?taskId=XXX` |
| Generate voice (ElevenLabs) | POST | `/jobs/create` |
| Generate music (Suno) | POST | `/jobs/create` |
| Generate sound effects | POST | `/jobs/create` |

**Full KIE.ai API Reference:** Check for `kie-ai-api-reference.md` in the master files folder. If it doesn't exist, the agent should flag this to the user and request the API documentation.

---

## PLATFORM OPTIMIZATION REFERENCE

| Platform | Max Duration | Format | Notes |
|----------|-------------|--------|-------|
| Facebook Reels | 90 seconds | 9:16 | Best for organic reach to non-followers |
| Instagram Reels | 20 minutes | 9:16 | Algorithm favors 30-90 seconds |
| Instagram Stories | 90 sec/clip | 9:16 | Disappears after 24 hours |
| TikTok | 10 minutes | 9:16 | Algorithm favors 15-60 seconds |
| YouTube Shorts | 3 minutes | 9:16 | Must be under 60 sec for Shorts feed |
| YouTube (standard) | No limit | 16:9 | Longer form, different audience |
| Facebook Ads | No hard limit | 9:16 or 16:9 | 15-30 sec performs best for ads |
| Google Ads | 15-30 sec typical | 16:9 | Short, punchy, clear CTA |

---

## FULL PROTOCOL DOCUMENT

For a complete worked example of this entire pipeline — every storyboard decision, every segment prompt, every audio layer, and every FFmpeg command for a full 90-second production — see the detailed example PRD in your master files folder, if your operator has provided one.

If no example PRD is present, this SKILL.md is self-contained: follow the phases above end to end.
