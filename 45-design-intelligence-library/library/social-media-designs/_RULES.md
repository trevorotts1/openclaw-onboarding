# CATEGORY RULES — Social Media Designs (SM-)
**Read before any SM- analysis or generation. These rules override style cards where they conflict.**

**One source of truth (P3-05 fix):** Skill 35 (`35-social-media-planner`) is the fleet's high-volume producer against this category and previously diverged from it silently (neither skill cross-referenced the other — confirmed both directions). Skill 35's own pixel-exact specs and brand-safety clause are folded in below rather than left to drift in two places; where Skill 35's playbook carries the full operational detail (weekly schedule, per-platform character limits, carousel mechanics), this file points to it instead of duplicating it. See `35-social-media-planner/references/playbook.md` Sections 7, 8, 8a, 8b, 18, 19.

## Formats & aspect ratios
| Placement | Ratio | Pixels (Skill 35 exact spec) | Model ratio param |
|---|---|---|---|
| IG/FB feed post (primary/carousel) | 4:5 | 1080 x 1350 | `4:5` |
| IG/FB feed post (square) | 1:1 | 1080 x 1080 | `1:1` |
| IG/TikTok Story-Reel, Stories, Full Screen | 9:16 | 1080 x 1920 | `9:16` |
| X/Twitter post | 16:9 | 1600 x 900 | `16:9` |
| LinkedIn post | 1:1 or 4:5 | 1200 x 627 (or 1080x1350 shared carousel set) | `1:1` / `4:5` |
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
- Default: Nano Banana 2 (people/lifestyle) or GPT-Image 2 (graphic/quote posts) — **non-text imagery only.**
- **Quote-card / text-led posts -> Ideogram V3 DESIGN.** This is not optional: it is the routing rule that fixes a confirmed cross-skill defect (P3-05). Skill 35 bakes a text/headline overlay into EVERY image it produces (playbook.md Section 18) — meaning every Skill 35 deliverable is a "text-led post" under this rule and MUST route to Ideogram V3 DESIGN, never Nano Banana 2/Pro (which are not text-rendering specialists). Skill 35's own pre-generation gate (`pregen_prompt_gate.py`) enforces this mechanically (`AF-SM-MODEL-ROUTING`, exit 6) so a misroute is refused before the paid generation call, not caught after a spelling-error retry loop.
- **Band<->routing reconciliation (GK-20, 2026-07-15):** a Graphics-authored quote-card/text-led prompt targeting this route uses GIP band `text_bearing_medium` (`_system/prompt-bands.json`) — the ONLY text-bearing band that names an Ideogram endpoint, sized (1,600–4,500 chars) to Ideogram V3's own verified 5,000-char API cap (MODEL-SPECS.md). `nano-banana-2`/`nano-banana-pro` never appear in a `text_bearing: true` band; `text_bearing_long` (5,000–18,000, GPT-Image 2 only) is architecturally too large for Ideogram and is not a legal fallback for this route.
- Volume series (5+ variants) → draft on Wan 2.7 (n=4, seed-locked), finalize winners on the default model.
