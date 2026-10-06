# Social Media Planner (Skill 35)

**Built by BlackCEO Automations**

A complete automated weekly social media content production system for OpenClaw. Produces a 7-part cliffhanger content series across 6 platforms, with images, videos, blog posts, podcasts, email newsletters, carousels, and emotionally-driven comments with action links.

## What It Does

Every week, this skill automatically:
- Requests the weekly theme from the client via heartbeat
- Selects a content persona using 5-layer alignment (client can override with personal brand tone)
- Researches the theme and builds 7 days of content
- Generates platform-specific posts for Facebook, Instagram, LinkedIn, YouTube, TikTok, and Pinterest
- Creates images at correct ratios (4:5, 2:3, 9:16, 16:9, 1:1) with brand-colored text overlays
- Produces videos using kie.ai through Skill 67 (default request: Veo 3.1 Lite)
- Writes a blog post and email newsletter (always); podcast episode with Fish Audio S2 emotion tags (only if Fish Audio is configured — otherwise podcast production is skipped gracefully)
- Creates Thursday carousel posts optimized per platform (including LinkedIn PDF upload)
- Writes unique, emotionally compelling comments with the client's action link for every post
- Runs 40+ QC checks (including persona governance) before anything goes live
- Schedules everything via GoHighLevel (Convert and Flow) Social Planner API using Private Integration Token
- Logs all content to the client's Google Sheet with inline image previews
- Logs weekly summary to memory for Dreaming insights

## Requirements

**REQUIRED (skill will not run without these):**
- OpenClaw instance with core .md files configured
- Skill 01 (Teach Yourself Protocol)
- Skill 22 (Book-to-Persona) for persona-governed content
- Skill 31 (Upgraded Memory System) for memory-core integration
- GoHighLevel (Convert and Flow) account with Private Integration Token and Social Planner API access
- kie.ai API access with the client's own `KIE_API_KEY` (images: KIE GPT Image 2.5 Sunburst, following the newest GPT Image generation; video models through Skill 67; every paid job runs the Skill 74 live-adapter chain: policy, prompt budget, validate, preflight, run)
- Google Sheets (**created automatically via n8n webhook - no client action needed**)
- Telegram for notifications (email and SMS as fallback)
- FFmpeg and ImageMagick installed locally

**OPTIONAL (skill installs and runs without these; only podcast production is skipped):**
- Skill 30 (Fish Audio API Reference) — enables podcast voiceover via Fish Audio S2
- Fish Audio API key and Voice ID (`FISH_AUDIO_API_KEY`, `FISH_AUDIO_VOICE_ID`)
- Podbean account for podcast hosting (`PODBEAN_PODCAST_ID`)

> **Without Fish Audio:** Skill 35 still produces images, videos, blog posts, email newsletters, carousels, comments, and full multi-platform scheduling. The podcast pipeline is gracefully skipped and Skill 35 logs `PODCAST_DEFERRED` to MEMORY.md so QC understands the skip is intentional, not a failure. The client can always add Fish Audio later and re-enable podcasts without reinstalling.

## How Posting Works

**Regular posts:** Image + content bundled in ONE GHL API call via `mediaUrls` field
**Carousel posts:** Multiple images + content in ONE GHL API call
**Video posts:** Video + content in ONE GHL API call
**Comments:** Separate API call 1-2 minutes AFTER parent post, contains the action link

## Installation

See INSTALL.md for the full installation guide with prerequisites, setup steps, and completion checklist.

## Google Sheet Template

Clients duplicate this template for their content hub:
```
https://docs.google.com/spreadsheets/d/1RKgS5l-i6NBtf_vON49nBPdHe-F5W67RF9ym-S67L2c/edit?usp=sharing
```

## Weekly Cost Estimate

This README holds no dollar figures, so there is one price authority: `python3 74-kie-live-adapter/scripts/kie_live_adapter.py price --model <id>` (Skill 74, live `pricingDesc`; fallback snapshot `74-kie-live-adapter/references/kie-model-registry.json`). Weekly cost = about 22 images, 1 podcast cover, and 2 videos of 8 clips each, each priced live. Fish Audio podcast cost is compute only (or its own API cost); nothing is charged for it if Fish Audio is not configured.

## File Structure

```
35-social-media-planner/
  SKILL.md              Skill trigger, overview, quick reference, dependencies
  README.md             This file
  INSTALL.md            Prerequisites, setup steps, completion checklist
  CORE_UPDATES.md       What to add to AGENTS.md, TOOLS.md, MEMORY.md
  QC.md                 Standalone 40+ item quality control checklist
  CHANGELOG.md          Version history
  skill-version.txt     Current version (see the file)
  references/
    playbook.md         Full production playbook with all specs
```

## Version

See `skill-version.txt` and `CHANGELOG.md` for the current version.

## License

Proprietary. Built by BlackCEO Automations for client deployment.
