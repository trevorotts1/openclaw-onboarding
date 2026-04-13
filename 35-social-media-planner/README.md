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
- Produces videos using kie.ai (Veo 3.1 Lite)
- Writes a blog post, podcast episode (with Fish Audio S2 emotion tags), and email newsletter
- Creates Thursday carousel posts optimized per platform (including LinkedIn PDF upload)
- Writes unique, emotionally compelling comments with the client's action link for every post
- Runs 40+ QC checks (including persona governance) before anything goes live
- Schedules everything via GoHighLevel (Convert and Flow) Social Planner API using Private Integration Token
- Logs all content to the client's Google Sheet with inline image previews
- Logs weekly summary to memory for Dreaming insights

## Requirements

- OpenClaw instance with core .md files configured
- Skill 01 (Teach Yourself Protocol)
- Skill 22 (Book-to-Persona) for persona-governed content
- Skill 30 (Fish Audio API Reference) for podcast production
- Skill 31 (Upgraded Memory System) for memory-core integration
- GoHighLevel (Convert and Flow) account with Private Integration Token and Social Planner API access
- kie.ai API access (Nano Banana 2 for images, Veo 3.1 Lite for videos)
- Fish Audio API key and Voice ID
- Podbean account for podcast hosting
- Google Sheets access (template provided for client to duplicate)
- Telegram for notifications (email and SMS as fallback)
- FFmpeg and ImageMagick installed locally

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

- ~22 images at 1K resolution (Nano Banana 2): ~$0.88
- 1 podcast cover at 2K resolution: ~$0.06
- 2 videos at 60 seconds each (Veo 3.1 Lite): ~$3.00
- Fish Audio S2 podcast: compute only (self-hosted) or API cost
- **Total: ~$3.94/week**

## File Structure

```
35-social-media-planner/
  SKILL.md              Skill trigger, overview, quick reference, dependencies
  README.md             This file
  INSTALL.md            Prerequisites, setup steps, completion checklist
  CORE_UPDATES.md       What to add to AGENTS.md, TOOLS.md, MEMORY.md
  QC.md                 Standalone 40+ item quality control checklist
  CHANGELOG.md          Version history
  skill-version.txt     Current version (v1.0.0)
  references/
    playbook.md         Full 1,656-line production playbook with all specs
```

## Version

v1.0.0 (April 13, 2026)

## License

Proprietary. Built by BlackCEO Automations for client deployment.
