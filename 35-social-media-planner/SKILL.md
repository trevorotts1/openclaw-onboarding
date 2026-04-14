---
skill_name: content-publishing-engine
version: v1.4.0
author: Stefanie
created_date: 2026-04-14
---

# Content Publishing Engine Skill

## Purpose
The Content Publishing Engine orchestrates multi-agent workflows to research, create, produce, publish, and monitor content across 8 platforms: WordPress, Medium, Substack, LinkedIn articles, GHL blog, YouTube, X/Twitter, and Facebook. It handles text, images, videos (with FFmpeg processing), podcasts, and HTML email newsletters.

## Key Principles
- **15+6 Agent Model**: 15 primary agents for core execution + 6 QC (Quality Control) agents for validation.
- **Variable-based Configuration**: All platform credentials, URLs, and settings pulled from `[from identity.md: brand name]`, `[from secrets/.env: GHL_LOCATION_ID]`, etc. NO hardcoded values.
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
   | GHL Blog | `https://services.leadconnectorhq.com/blogs?locationId=[from secrets/.env: GHL_LOCATION_ID]` |
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
Spawn via Antfarm or TaskFlow:
```
node ~/.openclaw/workspace/antfarm/dist/cli/cli.js workflow run content-publishing-engine "Publish: [topic]" --vars="brand=[from identity.md: brand name]"
```
Or subagent: `sessions_spawn task="Run Content Publishing Engine on [topic]" runtime="subagent" model="openrouter/xiaomi/mimo-v2-pro"`

## Variable Reference
- `[from identity.md: brand name]`, `[from identity.md: brand voice]`
- `[from secrets/.env: GHL_LOCATION_ID]`, `[from secrets/.env: WORDPRESS_URL]`, `[from secrets/.env: MEDIUM_TOKEN]`, etc.
- `[from config: video specs]`, `[from config: image model]`, `[from config: monitor_interval]`
- Pull via `read` tools before agent prompts.
