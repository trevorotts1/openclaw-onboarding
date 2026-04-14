# Social Media Planner (Skill 35) - Core File Updates

After installing this skill, add the following to the client's core .md files.

---

## Add to AGENTS.md

### Social Media Production System (Skill 35)

This skill produces a 7-part weekly content series across Facebook, Instagram, LinkedIn, YouTube, TikTok, and Pinterest.

**How it works:**
- Every Saturday, the AI requests the weekly theme from the client via HEARTBEAT.md
- The AI selects a content persona using 5-layer alignment (client can override with personal brand tone)
- Content production uses up to 8 parallel sub-agents: Facebook Writer, Instagram Writer, LinkedIn Writer, YouTube/Pinterest/TikTok Writer, Image Generator, Blog and Email Writer, Podcast Script Writer, Video Producer
- All posting goes through GoHighLevel (Convert and Flow) Social Planner API using a Private Integration Token
- Every post gets a unique comment with the client's weekly action link posted 1-2 minutes after the main post
- QC runs 40+ checks before anything is scheduled
- All content is logged to the client's Google Sheet

**Post types:**
- Regular posts: image + content bundled in one GHL API call
- Carousel posts (Thursdays): multiple images + content in one GHL API call
- Video posts: video + content in one GHL API call
- Comments: separate API call 1-2 minutes after parent post, contains the action link

### Video Production Process (Skill 35)

1. Generate 5x 15s video segments via kie.ai (`video_generate model=google/veo-3.1-lite-preview durationSeconds=15`)
2. Write per-segment voiceover scripts with [emotion] tags
3. Synthesize audio segments via Fish Audio (`sag --voice [from secrets/.env: FISH_AUDIO_VOICE_ID]`)
4. FFmpeg mux segment 1: `ffmpeg -i video_seg1.mp4 -i audio_seg1.mp3 -c:v copy -c:a aac -shortest seg1_final.mp4`
5. FFmpeg crossfade segments: `ffmpeg -f concat -safe 0 -i segments.txt -c copy video_pre_final.mp4` (with crossfade filter_complex)
6. Add brand intro/outro: `ffmpeg -i intro.mp4 -i pre_final.mp4 -filter_complex "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[outv][outa]" -map "[outv]" -map "[outa]" final.mp4`
7. ffprobe final.mp4: verify duration=60s, resolution=1080x1920, codec=H.264, 30fps, no errors

### Podcast Publishing Process (Skill 35)

1. Write 1500-2000 word script covering 7 days
2. Embed Fish Audio [emotion] tags
3. Synthesize MP3 via Fish Audio (192kbps)
4. Generate 1400x1400 cover JPEG via kie.ai
5. Upload audio+cover to GHL Media Library
6. Prepare webhook payload with [from secrets/.env: PODBEAN_PODCAST_ID], audio_url, image_url
7. Set publish_date Day 7 ISO (e.g. 2026-04-19T09:00:00-04:00)
8. POST to n8n webhook `https://main.blackceoautomations.com/webhook/podbean-publish`
9. Verify response: episode_id, status=draft
10. Update to publish: PATCH /episodes/[episode_id] status=published
11. Log to Google Sheet Podcast tab
12. Notify client via Telegram
13. ffprobe audio.mp3: bitrate=192kbps, no errors
14. Check Podbean dashboard for live episode

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
- Google Sheet: [client's sheet URL]
- Current action link: [confirmed weekly]
- Content persona: [auto-selected via 5-layer alignment, or client's personal tone]
- Weekly themes log: [AI logs themes here each week]
- Performance notes: [AI logs engagement insights here for Dreaming to process]
