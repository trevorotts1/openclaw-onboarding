---
name: kie-setup
description: >
  Complete setup and API reference for KIE.ai, a unified API platform that
  gives you access to dozens of AI models for generating images, videos, and
  audio - all through one API key and one consistent pattern.
metadata:
  
  version: "1.0"
  priority: CRITICAL
---

# KIE.ai Setup and API Reference

KIE.ai is a single API that connects you to many different AI models for
creating images, videos, and audio. Instead of signing up for separate accounts
at OpenAI, Google, Runway, Sora, and others, you use one KIE.ai API key and
one set of endpoints to access all of them.

Think of KIE.ai as a universal remote control for AI media generation.

## When to Use This Skill

- The user asks you to generate an image using AI
- The user asks you to create a video from text or from an image
- The user asks you to generate music or audio
- You need to use any of these models: Nano Banana Pro, Veo 3.1, Sora 2,
  Kling, Runway, Flux, GPT Image, Imagen, Seedream, Hailuo, Wan, or others
- The user mentions KIE.ai or asks about image/video generation pricing
- You need to upscale an image or video, remove a background, or do lip sync

## Prerequisites

- Teach Yourself Protocol (TYP) must be learned first (skill 01)
- Backup Protocol must be learned first (skill 02)
- A KIE.ai account with an API key (from https://kie.ai/api-key)
- Credits loaded on the KIE.ai account (pay as you go)

## What This Skill Covers

1. **API key setup** - How to get your key from kie.ai, add it to the OpenClaw
   config file, and verify it works with a test image generation.
2. **How the API pattern works** - All KIE.ai tasks follow the same two-step
   pattern: (a) send a POST request to create a task, (b) poll or use a
   callback to get the result when it finishes. Every model works this way.
3. **Image generation models** - Nano Banana Pro (Google Gemini 3, $0.09),
   Flux 2 Pro/Flex ($0.025), GPT Image 1.5, Imagen 4, Seedream 4.5 ($0.032),
   Grok Imagine ($0.10), Z-Image ($0.004), Ideogram V3, Qwen, and more.
4. **Video generation models** - Veo 3.1 Fast ($0.40) and Quality ($2.00),
   Sora 2 ($0.15) and Sora 2 Pro ($0.75), Kling 3.0, Runway, Hailuo 2.3
   ($0.15), Wan 2.6, ByteDance Seedance, Grok Imagine video ($0.10).
5. **Audio generation** - Suno music generation (V4, V4.5, V5), with lyrics
   or instrumental, custom audio uploads, and extend/remix features.
6. **Specialized tools** - Topaz upscaling (image and video), Recraft
   background removal and upscaling, Infinitalk lip sync, Kling AI Avatar
   (lip sync from audio), Luma video modification, and Sora watermark removal.
7. **File upload** - How to upload images and videos to KIE.ai's temporary
   storage (files kept for 3 days) before using them as inputs.
8. **Polling best practices** - How often to check task status without hitting
   rate limits. Start at 2-3 seconds, slow down after 30 seconds, stop after
   10-15 minutes. For large decks (more than 5 slides), prefer the callback
   architecture in Skill 46 over direct polling.
9. **Error codes** - What 401, 402, 429, and other errors mean and how to fix
   them (wrong key, no credits, rate limited, etc.).
10. **Callback architecture (large decks)** - For decks with more than 5 slides,
    use the centralized Cloudflare Worker callback system (Skill 46:
    kie-callback-relay). The Worker receives Kie callbacks at
    https://kie-callback.zerohumanworkforce.com/, verifies the HMAC once,
    and stores results in Worker KV for the box to poll. This is webhook-primary
    with a single-poll fallback and a crash-safe on-disk task registry.
    For 5 slides or fewer, efficient batch polling is faster and simpler.

## Files in This Folder (Reading Order)

1. **SKILL.md** - You are here. Start with this file.
2. **kie-setup-full.md** - The massive complete reference with every model's
   endpoint, parameters, curl examples, constraints, and pricing. This is
   your go-to when you need exact API details for a specific model.
3. **INSTRUCTIONS.md** - Operational instructions for the setup process.
4. **INSTALL.md** - Steps to install the API key into OpenClaw config.
5. **EXAMPLES.md** - Example API calls for common tasks.
6. **CORE_UPDATES.md** - What to add to AGENTS.md, TOOLS.md, and MEMORY.md.

## Critical Things to Know

- **NEVER use OpenAI's endpoint format** (/v1/images/generations). KIE.ai has
  its own endpoints. Images use /api/v1/jobs/createTask. Veo uses
  /api/v1/veo/generate. Runway uses /api/v1/runway/generate. Each model
  family has its own path.
- **All tasks are asynchronous.** A 200 response means the task was created,
  NOT that it is finished. You must poll for the result or use a callback URL.
- **Rate limits:** Maximum 20 new tasks per 10 seconds per account (source:
  https://docs.kie.ai/, verified 2026-06-14). Maximum 10 status queries per
  second per API key. Going over returns a 429 error.
- **Generated files expire.** Most URLs are valid for 24 hours (some 14 days).
  Flux origin/result image URLs are valid for only 10 minutes. Download
  results immediately and store them locally.
- **For slide decks larger than 5 slides:** use Skill 46 (kie-callback-relay)
  instead of polling each image sequentially. Submit the full batch first,
  then wait for results in parallel via the Worker KV endpoint.
- **Nano Banana Pro is the default image model** for this workspace. Never
  use DALL-E 3. Always use KIE.ai with Nano Banana Pro unless told otherwise.
- **The API key goes in** ~/clawd/secrets/.env as KIE_API_KEY. It is also
  used as a Bearer token in the Authorization header of every API call.
- **Always run the self-test** after setup: create a simple image, poll for
  the result, and verify you get a valid image URL back.

## Skill 46 Companion (Callback Architecture)

Skill 46 (46-kie-callback-relay) extends this skill with the centralized
callback Worker. Use it when:
- The deck has more than 5 slides
- You want to minimize Kie API query budget consumption
- You need crash-safe resume for a large batch job

The callback URL format for createTask requests:
```
callBackUrl: "https://kie-callback.zerohumanworkforce.com/cb?c=<clientSlug>&j=<submitId>&s=<perTaskSecret>"
```

Where:
- `c` = client identifier (alphanumeric)
- `j` = submitId (a local UUID you control -- NOT the Kie taskId)
- `s` = per-task secret (64 hex chars generated per slide)
