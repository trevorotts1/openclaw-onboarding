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

---

## Add to TOOLS.md

### Social Media Planner Tools (Skill 35)

| Tool | Purpose | Credentials |
|------|---------|-------------|
| GoHighLevel Social Planner API | Post scheduling, commenting, media attachment across all 6 platforms | GHL_PRIVATE_TOKEN + GHL_LOCATION_ID |
| kie.ai API | Image generation (Nano Banana 2) at 4:5, 2:3, 9:16, 16:9, 1:1 ratios. Video generation (Veo 3.1 Lite) | KIE_API_KEY |
| Fish Audio S2 API | Podcast TTS with inline [emotion] tags (depends on Skill 30) | FISH_AUDIO_API_KEY + FISH_AUDIO_VOICE_ID |
| Podbean Publishing (n8n webhook) | Podcast episode publishing. POST to https://main.blackceoautomations.com/webhook/podbean-publish with audio URL, cover image URL, title, description, publish date. Audio and image must go through GHL Media Library first. | PODBEAN_PODCAST_ID + client contact info |
| Google Sheets API | Content logging across 19 worksheets with inline image previews | **Sheet created automatically via n8n webhook** - no client credentials needed |
| FFmpeg | Video segment merging (audio + video, 192 kbps, H.264, 30fps) | Installed locally |
| ImageMagick / Python Pillow | LinkedIn PDF carousel generation from 4:5 images | Installed locally |
| Podbean | Podcast episode hosting (MP3, 192 kbps, 1400x1400 cover art) | Podbean account |

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
