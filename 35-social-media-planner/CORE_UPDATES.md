# Social Media Planner (Skill 35) - Core File Updates

After installing this skill, add the following to the client's core .md files.

> **MCP-First Routing Update (skill 36, May 13, 2026):** If **skill 36 (`36-ghl-mcp-setup`)** is installed, all GHL operations in this skill (social posting, blog publish, media upload, campaign scheduling) MUST route through the MCP layer first:
>
> - **Tier 1 (Official MCP):** `social-media-posting_create-post`, `social-media-posting_edit-post`, `social-media-posting_get-account`, `blogs_create-blog-post`, `blogs_update-blog-post`, `emails_create-template`
> - **Tier 2 (Community MCP):** `create_social_post`, `update_social_post`, `bulk_delete_social_posts`, `upload_media_file`, `bulk_update_media_files`, `create_email_template`, `view_email_center`, `view_campaign_stats`
> - **Tier 3 (raw API — what this skill historically describes):** Only as a fallback when MCPs lack the call.
>
> The agent must emit the disclosure header `[GHL tier used: N — tool_name]` on every GHL-data response per skill 36's protocol. If skill 36 is NOT installed, this skill falls back to the direct API workflow below.

---

## Add to AGENTS.md

### Social Media Production System (Skill 35)

This skill produces a 7-part weekly content series across Facebook, Instagram, LinkedIn, YouTube, TikTok, and Pinterest.

**How it works:**
- Every Saturday, the AI requests the weekly theme from the client via HEARTBEAT.md
- The AI selects a content persona using 5-layer alignment (client can override with personal brand tone)
- Content production uses up to 8 parallel sub-agents: Facebook Writer, Instagram Writer, LinkedIn Writer, YouTube/Pinterest/TikTok Writer, Image Generator, Blog and Email Writer, Podcast Script Writer, Video Producer
- **Posting path (if skill 36 installed):** route through `social-media-posting_create-post` (Tier 1 Official MCP) by default. Fall to Tier 2 `create_social_post` if Tier 1 lacks a needed field. Fall to direct GoHighLevel Social Planner API (Tier 3) only as last resort.
- **Posting path (if skill 36 NOT installed):** direct GoHighLevel (Convert and Flow) Social Planner API using Private Integration Token.
- Every post gets a unique comment with the client's weekly action link posted 1-2 minutes after the main post
- QC runs 40+ checks before anything is scheduled
- All content is logged to the client's Google Sheet

**Post types:**
- Regular posts: image + content bundled in one MCP/API call
- Carousel posts (Thursdays): multiple images + content in one MCP/API call
- Video posts: video + content in one MCP/API call
- Comments: separate MCP/API call 1-2 minutes after parent post, contains the action link

### Video Production Process (Skill 35)

The agent produces every 55-60s Reel end-to-end. It NEVER asks the client to record video. Client self-recording is a last-resort fallback only after all clip generation retries are exhausted.

**Full pipeline (mandatory primary path):**

1. **Storyboard:** compute `scene_count = ceil(target_seconds / 8)` (e.g. ceil(60/8) = 8 scenes). For each scene write a visual prompt with continuity cues (consistent subject, wardrobe, setting, color grade, camera style). Mark each scene's incoming transition as `cut` or `crossfade`.
2. **Generate clips:** one clip per scene via kie.ai (`video_generate model=google/veo-3.1-lite-preview durationSeconds=8`), 9:16 vertical. Retry any failed clip up to 3 times before marking it failed.
3. **Voiceover:** generate ONE continuous 55-60s VO from the full script via Fish Audio (`sag --voice [from secrets/.env: FISH_AUDIO_VOICE_ID]`). Save as `voiceover.mp3`.
4. **Normalize every clip** (mandatory before concat — prevents codec/resolution mismatch failures):
   ```bash
   ffmpeg -i raw_scene_N.mp4 \
     -vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,fps=30,setsar=1" \
     -c:v libx264 -pix_fmt yuv420p -c:a aac -ar 48000 \
     norm_scene_N.mp4
   ```
5. **Merge — jump cuts** (hard cuts, energetic; storyboard says `cut`): list normalized files in `clips.txt` as `file 'norm_scene_N.mp4'`, then:
   ```bash
   ffmpeg -f concat -safe 0 -i clips.txt -c copy merged.mp4
   ```
   **Merge — crossfades** (smoother; storyboard says `crossfade`): chain xfade filters (`offset = clip_duration - xfade_duration = 8 - 0.5 = 7.5` for each additional clip):
   ```bash
   ffmpeg -i norm_scene_01.mp4 -i norm_scene_02.mp4 \
     -filter_complex "[0][1]xfade=transition=fade:duration=0.5:offset=7.5,format=yuv420p" \
     -c:a aac merged.mp4
   ```
6. **Lay voiceover over merged video:**
   ```bash
   ffmpeg -i merged.mp4 -i voiceover.mp3 \
     -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -shortest \
     final_reel.mp4
   ```
7. **QC:** `ffprobe -v error -show_entries format=duration -of csv=p=0 final_reel.mp4` must be within 55-60s; resolution must be 1080x1920; codec must be h264. If a clip failed after retries, assemble from passing clips or offer client a shorter cut before considering self-record.

Use `bash ~/.openclaw/skills/35-social-media-planner/scripts/merge_reel.sh clips.txt voiceover.mp3 final_reel.mp4` to run steps 4-7 in one command.

### Podcast Publishing Process (Skill 35)

The agent produces every podcast episode end-to-end. It NEVER asks the client to record audio. Client self-recording is a last-resort fallback only after all retries are exhausted and the operator has been notified via Telegram.

**Full pipeline (mandatory primary path):**

1. **Write script** — 1,500-2,000 word script covering all 7 days of content. Save as `podcast_script_draft.txt`.

2. **Tag the script heavily** — annotate every paragraph shift, reveal, fact, and CTA with Fish Audio S2-Pro emotion tags in [square brackets] before TTS. Minimum: one tag per paragraph. Goal: the script reads like a director's script. Save tagged version as `podcast_script_tagged.txt`.
   - Examples: `[warm, conversational tone]`, `[excited]`, `[pause]`, `[whispering]`, `[passionate, building energy]`, `[leaning in, like sharing something important]`, `[the calm confidence of someone who has seen this work]`, `[urgent but caring]`
   - S2-Pro uses [square brackets] — NOT parentheses (that is S1 syntax and produces poor results on s2-pro)

3. **Select model** — use `s2-pro` (current Fish Audio recommended model as of June 2026). Specified via HTTP header `model: s2-pro`. Default to `s2-pro` if model detection fails.

4. **Generate audio autonomously** — run the helper script which calls Fish Audio `/v1/tts` (synchronous binary stream, no polling needed), writes MP3, verifies file, retries up to 3x:
   ```bash
   bash ~/.openclaw/skills/35-social-media-planner/scripts/generate_podcast_audio.sh \
     podcast_script_tagged.txt \
     [from secrets/.env: FISH_AUDIO_VOICE_ID] \
     s2-pro \
     podcast_audio.mp3
   ```
   Fish Audio API: `POST https://api.fish.audio/v1/tts` with `Authorization: Bearer [FISH_AUDIO_API_KEY]`, `Content-Type: application/json`, `model: s2-pro` headers. Body: `{"text": "...", "reference_id": "[FISH_AUDIO_VOICE_ID]", "format": "mp3", "latency": "normal", "normalize": true, "chunk_length": 300}`.

5. **Verify file** — `ffprobe -v error -show_entries format=duration -of csv=p=0 podcast_audio.mp3` must return 600-900 seconds (10-15 min). File must exist and be non-zero. No ffprobe errors. Script handles this automatically.

6. **On failure: diagnose and retry** — the script diagnoses common causes (invalid API key, invalid voice ID, network error, rate limit, model unavailable) and retries up to 3x. After 3 failures: notify operator via Telegram with diagnostic output, then (only then) offer client the self-record fallback.

7. **Generate 1,400x1,400 cover JPEG** via kie.ai Nano Banana 2 (2K resolution required for Podbean minimum). JPEG only — never WebP (Apple Podcasts rejects it). If over 500 KB: `convert input.png -resize 1400x1400 -quality 85 output.jpg`.

8. **Upload audio + cover to GHL Media Library** — NEVER send Fish Audio URLs directly to the webhook.

9. **Prepare webhook payload** with `[from secrets/.env: PODBEAN_PODCAST_ID]`, `audio_url` (GHL), `image_url` (GHL).

10. **Set publish_date** — Day 7 ISO 8601 with time (e.g. `2026-04-19T09:00:00-04:00`). Date-only strings error.

11. **POST to n8n webhook** `https://main.blackceoautomations.com/webhook/podbean-publish`

12. **Verify response: 200 OK** — retry once after 30s on non-200. If still failing, notify client via Telegram.

13. **Log to Google Sheet Podcast tab.**

14. **Notify client via Telegram** with episode number and scheduled publish date.

15. **ffprobe audio.mp3** — confirm no errors and bitrate ≥ 128kbps.

16. **Check Podbean dashboard** for live episode within 15 minutes of webhook confirmation.

### Email Newsletter Process (Skill 35)

1. Compile Day 2 content into HTML table (3-col: image | recap | CTA)
2. Inline CSS only (no external stylesheets)
3. Subject: 60 chars max, e.g. "[Day 2 Theme]: [from identity.md: brand name] Weekly Update"
4. Preview text: 120 chars max
5. Deferred send: schedule Tuesday 9AM via GHL Campaigns
6. Upload images to GHL Media, embed <img src="[media_url]">

---

## Add to TOOLS.md

### Social Media Planner Tools (Skill 35)

| Tool | Purpose | Credentials |
|------|---------|-------------|
| GoHighLevel Social Planner API | Post scheduling, commenting, media attachment across all 6 platforms | GHL_PRIVATE_TOKEN + GHL_LOCATION_ID |
| kie.ai API | Image generation (Nano Banana 2) at 4:5, 2:3, 9:16, 16:9, 1:1 ratios. Video generation (Veo 3.1 Lite) | KIE_API_KEY |
| Fish Audio S2 API | Podcast TTS with inline [emotion] tags (depends on Skill 30) | FISH_AUDIO_API_KEY + FISH_AUDIO_VOICE_ID |
| Google Sheets API | Content logging across 19 worksheets with inline image previews | **Sheet created automatically via n8n webhook** - no client credentials needed |
| FFmpeg | Video segment merging (audio + video, 192 kbps, H.264, 30fps) | Installed locally |
| ImageMagick / Python Pillow | LinkedIn PDF carousel generation from 4:5 images | Installed locally |
| Podbean | Podcast episode hosting (MP3, 192 kbps, 1400x1400 cover art) | Podbean account |

### Podbean Podcast Publishing (Skill 35)

Podcast episodes are published via n8n webhook.

**Endpoint:** `POST https://main.blackceoautomations.com/webhook/podbean-publish`

**Required fields:**
- `podcast_id` - from memory.md or secrets/.env: PODBEAN_PODCAST_ID
- `audio_url` - GHL Media Library URL (must upload generated MP3 first)
- `image_url` - GHL Media Library URL (must upload cover art first, JPEG/PNG, 1:1, 1400x1400 min, under 500 KB)
- `title` - episode title based on this week's theme
- `description` - show notes from podcast script (under 3000 chars)
- `publish_date` - Day 7 date in ISO format
- `client_first_name` - from identity.md: owner first name
- `client_last_name` - from identity.md: owner last name
- `client_email` - from identity.md: owner email

**Payload:**
```json
{
  "podcast_id": "[from memory.md or secrets/.env: PODBEAN_PODCAST_ID]",
  "audio_url": "[GHL Media Library URL after uploading the generated MP3]",
  "image_url": "[GHL Media Library URL after uploading the generated cover art]",
  "title": "[episode title based on this week's theme]",
  "description": "[show notes from the podcast script, under 3000 chars]",
  "publish_date": "[Day 7 date in ISO format]",
  "client_first_name": "[from identity.md: owner first name]",
  "client_last_name": "[from identity.md: owner last name]",
  "client_email": "[from identity.md: owner email]"
}
```

### Google Sheet Creation Webhook (Skill 35)

**Endpoint:** `POST https://main.blackceoautomations.com/webhook/social-planner-sheet-create`

**Payload:**
```json
{
  "brandName": "[from identity.md: brand name]",
  "clientEmail": "[from identity.md: owner email]"
}
```

---

## Add to MEMORY.md

### Social Media Planner Status (Skill 35)

- Installed: [date]
- Video preference: [0, 2, or 7 per week]
- content_sheet_id: [Google Sheet ID — agent reads this to answer "what's my content sheet?"]
- content_sheet_url: [Full Google Sheet URL — agent surfaces this on demand, NEVER says "I don't have the link"]
- Current action link: [confirmed weekly]
- Content persona: [auto-selected via 5-layer alignment, or client's personal tone]
- Weekly themes log: [AI logs themes here each week]
- Performance notes: [AI logs engagement insights here for Dreaming to process]
- Media delivery: GHL CDN (https://assets.cdn.filesafe.space/[LOCATION_ID]/media/...) — all finished media uploaded here, delivered as public links
