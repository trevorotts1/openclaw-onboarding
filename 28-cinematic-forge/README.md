# Cinematic Forge

**AI-Powered Video Production from Concept to Upload**

Cinematic Forge is an OpenClaw skill that produces complete videos using AI. It walks users through a structured intake process, generates all visual and audio assets, assembles them with FFmpeg, and delivers the final product to the user's media library.

## Quick Overview

| Detail | Value |
|--------|-------|
| **Skill Name** | cinematic-forge |
| **Version** | 1.0 |
| **Author** | (redacted for client-generic distribution) |
| **Prerequisite** | Teach Yourself Protocol |
| **Primary Tools** | VEO 3.1 Fast, Nano Banana Pro, ElevenLabs, Suno, FFmpeg |
| **API Provider** | KIE.ai (all generation models) |
| **Primary Format** | 9:16 vertical |
| **Cost Example** | ~$8.50 for a 90-second video |

## What It Does

1. **Intake** - 14 structured questions asked one at a time
2. **Pre-Production** - Storyboard, reference images, scripts
3. **Video Generation** - VEO 3.1 Fast segments with Extend chaining
4. **Audio Production** - ElevenLabs voices + Suno music + SFX (all separate from video)
5. **Assembly** - FFmpeg merges video + audio layers
6. **Delivery** - Upload to GHL media library, return link to user
7. **Revision** - User requests changes, agent re-generates affected parts
8. **Upscale** - Topaz 1080p/4K upgrade after user approval

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | Complete skill reference (intake questions, production pipeline, FFmpeg commands, API endpoints, cost reference) |
| `INSTALL.md` | Step-by-step installation and setup instructions |
| `README.md` | This file - quick overview |

## Installation

See `INSTALL.md` for full instructions. Short version:

1. Install the Teach Yourself Protocol skill first
2. Install this skill to `~/.openclaw/skills/28-cinematic-forge/`
3. Tell your agent: "Teach yourself this skill" and provide SKILL.md
4. Verify API access (KIE.ai, GHL/Convert and Flow)
5. Test with a simple short video
