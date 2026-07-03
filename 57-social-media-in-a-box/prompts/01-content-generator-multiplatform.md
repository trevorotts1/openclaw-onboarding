# Prompt 01 — Multi-Day Multi-Platform Content Generator

- **Source workflow:** `02-content-generator` (02-Social Media in a Box Content Generator)
- **Model at export time:** OpenAI-node (model left blank at export; runtime = client-configured provider)
- **Purpose:** Single-call generator: N days of platform-specific content (post/story/reel/video/short variants) as a JSON array, from theme + CTA + link + platform list.
- **Anonymization:** verified clean — no client names or secrets in this prompt text. Client-identifying data in this workflow family lives ONLY in raw-export `pinData` (see ANALYSIS.md `client_name_locations`); it is excluded here.

## User

_Source: node `Generate Content with AI` → messages.values[0].content_

```
You are a social media content strategist. Generate engaging content for {{ $json.numberOfDays }} days based on this theme: {{ $json.theme }}

Special Instructions: {{ $json.specialInstructions }}
Call to Action: {{ $json.callToAction }}
Link: {{ $json.clickThroughLink }}

Platforms needed: {{ JSON.stringify($json.platforms) }}

Create varied, engaging content for each day. For each day, provide:
1. Base content (150-200 characters)
2. Platform-specific variations based on the post types requested

For Facebook/Instagram: If Story or Reel is in postTypes, create specific content for those formats
For YouTube: If both Video and Short are requested, create different content for each

Return as JSON array with this structure:
[
  {
    "day": 1,
    "date": "YYYY-MM-DD",
    "baseContent": "Main message",
    "platforms": {
      "facebook": {
        "post": "Facebook post content",
        "story": "Story-specific content",
        "reel": "Reel script/content"
      },
      "instagram": {
        "post": "Instagram post with hashtags",
        "story": "Story content",
        "reel": "Reel content"
      },
      "linkedin": "Professional version",
      "youtube": {
        "video": "Video description",
        "short": "Short description"
      },
      "tiktok": "TikTok caption with trends",
      "pinterest": "Pinterest description",
      "google": "Google Business post"
    }
  }
]

Only include the platforms and post types that were requested. Make content authentic and engaging for each platform's audience.
```


---

## v0.2.0 — CREATIVE-LAYER dynamic-input slots (merge plan §4 / CREATIVE-INTERJECTION-DESIGN)

**The one-sentence law:** provers freeze the FRAME (shape/size/count/safety/de-dup/provenance),
never the PICTURE (topic/angle/voice/image aesthetic). The SYSTEM message above is the hash-pinned
FRAME. Creativity flows through the NEVER-hashed USER message via the slots below. Adding these slots
is the sanctioned widening path: a prompt version bump + re-pin in `PROMPT-HASHES.json`, NOT a runtime
prompt mutation. Every slot is OPTIONAL; absent, the prompt reproduces v0.1.0 behavior exactly.

| Slot | Injection point | Enters via | Provers touch (FORM only) |
|---|---|---|---|
| `CREATIVE BRIEF` | I4 hooks / angles / mustInclude / neverSay / openingLine / refrains | `working/creative/brief.json` | bands on the finished output only; the brief text is unproven creative payload |
| `PLATFORM VOICE` | I8 per-platform voice/persona deltas | `platformVoice{}` + per-run `platformNotes` | per-platform bands unchanged (same frame, different picture) |
| `ARC / SERIES-LENGTH` | I11 arcTemplate / pitchCurve / seriesLength / nextSeasonTease | config + brief | series prover iterates N days; a non-7 count is a LOGGED client-exact override; arc SHAPE is never proven |
| `ART DIRECTION` | I9 artDirection / brandColors / brandFonts / stylePick | config + `brief.visual` | image-prompt LENGTH bands only; Gemini loops repair WITHIN the client's direction, never taste-gate |
| `BAND OVERRIDES` | R1-R5 client-exact counts | `overrides.json` (run) / `bandOverrides` (config) | resolution run > config > default; every applied override is LOGGED or `AF-SM-OVERRIDE-UNLOGGED` refuses the certificate |

**Intake rule:** the client interjects in natural language on any channel; the agent normalizes into
the right slot. NEVER talk the client out of it, NEVER floor/cap a stated number (the client gets
EXACTLY what they ask for), NEVER require field names. "Just this week or from now on?" is asked once
(run-level auto-reverts / config-level persists). The em-dash ban stays the DEFAULT on content
fields with a per-client logged `emDashPolicy: allow-content` opt-out (R4); machine-reinjected
JSON-safe fields keep the ban forever (technical).
