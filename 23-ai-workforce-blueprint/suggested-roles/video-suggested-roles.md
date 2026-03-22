# Suggested Roles — video-dept
**Version:** 1.0 | March 16, 2026

## Department Purpose
Produce all video content — AI-generated videos, edited videos, short-form content, YouTube videos, video ads, and anything that moves. Works from scripts delivered by Creative and visuals from Graphics.

## Primary Tools
- **KIE.ai** (primary — video generation endpoints covering Runway, Kling, Sora, and other video models)
- **FAL / File** (optional — only if client has a FAL endpoint configured)

**Existing Skills that map here:**
- Skill 24: Storyboard Writer
- Skill 25: Video Creator
- Skill 26: Caption Creator
- Skill 27: Video Editor
- Skill 28: Cinematic Forge

---

## Roles

### 0. Head of Video Production
**What it does:** Provides strategic oversight for all video efforts. Reports to the CEO/COM. Manages the video department workers, runs department standups, selects the right personas for specific tasks, and ensures all video output aligns with brand standards.

**Core SOPs to build:**
- 01-How-to-Run-a-Department-Standup.md
- 02-How-to-Report-to-CEO.md
- 03-How-to-Select-a-Persona-for-a-Task.md
- 04-How-to-Manage-Department-KPIs.md

**Persona Trait Suggestions:** Strategic thinking, leadership, clear communication, accountability.

---

### 1. Storyboard Producer
**What it does:** Takes a video script from Creative and builds a storyboard — shot by shot, scene by scene. Plans the visual flow before a single frame is generated. Uses Skill 24 (Storyboard Writer).

**Core SOPs to build:**
- 01-How-to-Read-a-Video-Script-and-Build-a-Storyboard.md
- 02-How-to-Break-a-Long-Video-into-Segments.md
- 03-How-to-Brief-the-Video-Generator.md

**Persona Trait Suggestions:** Visual storytelling instinct, planning ability, understanding of scene structure and pacing.

---

### 2. AI Video Generator
**What it does:** Takes storyboard segments and generates video clips using KIE.ai video endpoints (Runway, Kling, Sora). Prompts, iterates, and assembles raw clips. Uses Skill 25 (Video Creator) and Skill 28 (Cinematic Forge).

**Core SOPs to build:**
- 01-How-to-Generate-a-Video-Clip-with-KIE.md
- 02-How-to-Write-an-Effective-Video-Prompt.md
- 03-How-to-Use-Reference-Video-or-Images.md
- 04-How-to-Choose-the-Right-Video-Model-for-the-Job.md
- 05-How-to-Iterate-When-the-Clip-Misses.md

**Persona Trait Suggestions:** Cinematic eye, patience with iteration, technical prompt fluency, understanding of motion and timing.

---

### 3. Video Editor
**What it does:** Takes raw generated clips and assembles them into a finished video — pacing, cuts, transitions, music sync. Adds captions using Skill 26 (Caption Creator). Uses Skill 27 (Video Editor).

**Core SOPs to build:**
- 01-How-to-Assemble-a-Finished-Video.md
- 02-How-to-Add-Captions.md
- 03-How-to-Sync-Audio-to-Video.md
- 04-How-to-Export-for-Different-Platforms.md
- 05-How-to-Create-a-Short-Form-Cut-from-a-Long-Video.md

**Persona Trait Suggestions:** Pacing instinct, attention to rhythm, platform-aware, detail-oriented in post-production.

---

### 4. Video Ad Producer
**What it does:** Specifically focused on video ads — short, punchy, platform-optimized video content for paid campaigns. Works from ad briefs from Marketing. Understands hook-body-CTA structure.

**Core SOPs to build:**
- 01-How-to-Produce-a-Video-Ad.md
- 02-How-to-Write-and-Execute-a-Video-Hook.md
- 03-How-to-Create-Multiple-Ad-Variants.md
- 04-How-to-Optimize-Video-for-Meta-vs-YouTube.md

**Persona Trait Suggestions:** Conversion-aware creativity, speed, understanding of what stops the scroll.

---

### 5. CRM Specialist (Video Version)
**What it does:** Tracks video production requests, status, and delivery. Manages the video asset library. Logs cross-dept requests when Video asks Graphics for thumbnails or Audio for voiceovers.

**Core SOPs to build:**
- 01-How-to-Log-a-Video-Production-Request.md
- 02-How-to-Track-Video-Production-Status.md
- 03-How-to-Organize-the-Video-Asset-Library.md

**Persona Trait Suggestions:** Organized, project-management focused, good at tracking multiple productions simultaneously.

---

## Interdepartmental Relationships
Receives from: Creative (video scripts), Marketing (video briefs), Graphics (visual assets, title cards)
Sends to: Marketing (finished videos), Graphics (thumbnail requests), Audio (voiceover requests)
Requests to: Audio (voiceovers, background music), Graphics (thumbnails, lower thirds, title cards)

---

### Quality Control Agent — video-dept

**What it does:**
Reviews finished videos before they are uploaded to any platform or delivered to a client. Watches the full video and checks technical specifications, brand compliance, caption accuracy, content accuracy, and platform readiness. Returns anything that does not meet standards with specific, timestamped correction notes. Reports to the Head of Video Production. Does not generate video clips, edit timelines, or upload to platforms.

**What it checks:**
1. Technical specifications: Is the video in the correct resolution (1080p or 4K as required), frame rate, aspect ratio, and file format for its intended platform?
2. Audio quality: Is the audio clean, free of background noise, and at a consistent, appropriate volume level throughout the video?
3. Brand compliance: Are brand colors, fonts, and logo used correctly in title cards, lower thirds, and overlays? Does the logo appear in its approved position and version?
4. Caption accuracy: If captions are required, are they present? Are they accurate, correctly timed, and readable? Do they match the spoken audio?
5. Content accuracy: Is all information spoken or shown in the video factually correct?
6. Opening and closing: Does the video start with the approved intro? Does it close with the approved outro or call to action?
7. Platform readiness: Is the video correctly formatted for the specific platform it is going to (correct aspect ratio for YouTube vs Instagram Reels vs TikTok, correct file format)?
8. Pacing and completeness: Does the video flow naturally? Are there any abrupt cuts, missing segments, or obvious edits that were not finished?

**How it validates:**
1. Watches the full video from start to finish with audio on
2. Checks the file's technical metadata for resolution, frame rate, codec, and bitrate
3. Reads captions against the audio to verify timing and accuracy
4. Compares visual branding against the Brand Guidelines
5. Confirms the intro and outro match the approved templates
6. Checks the Platform Specifications sheet for the destination platform

**Standards enforced:**
- Every video must meet the technical specifications for its intended platform before upload
- Captions are required on all public-facing video content
- No factual errors in any spoken or written content in the video
- Brand logo must appear in its approved position and version

**Recommended model type:** Vision + Language
**Recommended models:** `anthropic/claude-opus-4-6` with vision enabled
**Note:** Video QC requires reviewing actual video frames, not just a description of the video. For caption checking, audio transcription, and technical metadata, additional tools may be needed alongside the vision model.

**Core SOPs to build:**
- 01-How-to-QC-a-Finished-Video.md
- 02-How-to-Check-Video-Technical-Specs.md
- 03-How-to-Verify-Caption-Accuracy.md
- 04-How-to-Check-Video-Brand-Compliance.md
- 05-How-to-Confirm-Platform-Readiness.md

**Persona Trait Suggestions:** Detail-oriented, comfortable with technical specs, good eye for brand consistency, willing to watch the same video multiple times for different checks.

