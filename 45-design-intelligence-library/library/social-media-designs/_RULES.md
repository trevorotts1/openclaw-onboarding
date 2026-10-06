# CATEGORY RULES — Social Media Designs (SM-)
**Read before any SM- analysis or generation. These rules override style cards where they conflict.**

**One source of truth (P3-05 fix):** Skill 35 (`35-social-media-planner`) is the fleet's high-volume producer against this category and previously diverged from it silently (neither skill cross-referenced the other — confirmed both directions). Skill 35's own pixel-exact specs and brand-safety clause are folded in below rather than left to drift in two places; where Skill 35's playbook carries the full operational detail (weekly schedule, per-platform character limits, carousel mechanics), this file points to it instead of duplicating it. See `35-social-media-planner/references/playbook.md` Sections 7, 8, 8a, 8b, 18, 19.

## Formats & aspect ratios
| Placement | Ratio | Pixels (Skill 35 exact spec) | Model ratio param |
|---|---|---|---|
| IG/FB feed post (primary/carousel) | 4:5 | 1080 x 1350 | `3:4` on GPT Image 2.5 (N43 substitution for 4:5, then crop/resize to 1080 x 1350); `4:5` only on the labeled Nano Banana 2 fallback |
| IG/FB feed post (square) | 1:1 | 1080 x 1080 | `1:1` |
| IG/TikTok Story-Reel, Stories, Full Screen | 9:16 | 1080 x 1920 | `9:16` |
| X/Twitter post | 16:9 | 1600 x 900 | `16:9` |
| LinkedIn post | 1:1 or 4:5 | 1200 x 627 (or 1080x1350 shared carousel set) | `1:1` / `3:4` on GPT Image 2.5 (N43 substitution for 4:5) |
| Pinterest pin / Vertical | 2:3 | 1000 x 1500 | `2:3` |
| Blog featured image | 16:9 | 1200 x 630 | `16:9` |
| Podcast cover | 1:1 | 1400 x 1400 (2K min) | `1:1` |
| Carousel master | 1:1, design with edge-continuity noted | 1080 x 1080 | `1:1` |

## Hard rules
- 9:16 safe zones: text inside middle 75% vertically; bottom 25% is covered by captions/UI on TikTok/Reels.
- Mobile-first legibility: minimum effective text size ≈ 4% of frame height; max ~12 words on screen (Skill 35 caps on-image headline copy at 5-10 words, playbook.md Section 18 rule 8).
- NEVER text over faces.
- **Brand-safety clause (mandatory on every prompt, Skill 35 playbook.md Section 18 rule 5, verbatim):** *"brand-appropriate, appropriate for the client's audience, no suggestive content."* This is a required, checkable string in the assembled prompt — not an implied tone. Gated by both `diu_validator.py prompt-band` (Graphics-authored assets) and `pregen_prompt_gate.py check` (Skill 35-authored assets, `AF-SM-PROMPT-FORM` on absence).
- Per-platform energy (matches the platform-agent system): IG = polished aspirational; LinkedIn = authoritative clean; TikTok = raw high-energy; Pinterest = bright instructional. Record the platform register in every SM card.
- Series consistency: SM styles are usually generated in sets — every SM card must define what stays FIXED across a series (palette, type, layout skeleton) vs. what VARIES (subject, accent color, background hue).
- Brand default: bold, vibrant, high saturation (client brand standard — see workspace brand config).

## Model routing
- **GPT Image 2.5 Sunburst (`gpt-image-2-5-sunburst-text-to-image` / `-image-to-image`) for ALL social images**, text-led quote cards and people/lifestyle imagery included (owner order 2026-10, AGENTS.md N43; Skill 66 registry ids). Legacy `gpt-image-2-*` is used only for the ratios 3:1, 1:3 and 9:21. The N43 ratio substitutions apply on the default model: 5:4 -> 4:3, 4:5 -> 3:4, 2:1 -> 16:9, 1:2 -> 9:16.
- **Nano Banana 2 is a labeled fallback only** (used when the default route hard-fails, and recorded as a fallback in the receipt; Skill 35's pre-generation gate refuses it otherwise). It is never the primary for any social asset.
- **There is no Ideogram V3 route for social images.** Skill 35 routes every image to GPT Image 2.5 Sunburst, so the earlier claim that every Skill 35 deliverable must route to Ideogram V3 DESIGN was wrong and is removed.
- **Prompt bands:** social-planner image prompts (Skills 35/57) use the scoped 9,000-19,000 character override on GPT Image 2.5 (`_system/prompt-bands.json` `social_planner_image_scoped_override`, `shared-utils/social_prompt_policy.json`). Graphics-authored (non-planner) assets use the GIP bands in `prompt-bands.json`; its legacy `text_bearing_medium` band names an Ideogram endpoint and is NOT a social route.
- Volume series (5+ variants) -> draft on Wan 2.7 (n=4, seed-locked), finalize winners on the default model.
