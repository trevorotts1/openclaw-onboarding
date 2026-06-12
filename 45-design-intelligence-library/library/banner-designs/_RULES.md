# CATEGORY RULES — Banner Designs (BN-)
**Read before any BN- analysis or generation. These rules override style cards where they conflict.**

## Formats & aspect ratios
| Use | Ratio | Model ratio param | Models that support it |
|---|---|---|---|
| Website hero | 21:9 or 3:1 | `21:9` / `3:1` | 21:9 widely; 3:1 GPT-Image 2 only |
| Leaderboard / super-wide web | 8:1 | `8:1` | **Nano Banana 2 or Wan 2.7 ONLY** |
| Mid-wide promo strip | 4:1 | `4:1` | **Nano Banana 2 ONLY** |
| Social cover (FB/LinkedIn/YouTube) | ~2.6–6.2:1 | generate `21:9` or `4:1`, crop to spec | — |
| Vertical web skyscraper | 1:8 | `1:8` | Nano Banana 2 or Wan 2.7 |

## Hard rules
- **Ultra-wide (8:1, 4:1, 1:8, 1:4) routes to Nano Banana 2. No other primary option exists.** Wan 2.7 is backup for 8:1/1:8 only.
- Horizontal eye-flow: left-anchor or right-anchor the subject; text occupies the opposite half. Never center-stack in ultra-wide.
- Edge-safe margins: keep text ≥5% of width from left/right edges (responsive crops eat edges).
- Subject crop discipline: ultra-wide frames crop people aggressively — specify crop (bust/face) explicitly in every prompt.
- Social cover banners: critical content in the center 60% horizontally (mobile crops sides hard).
- Text renders smallest in banners — typography instructions need maximum redundancy; consider generating type-led banners on GPT-Image 2 at 3:1 and outpainting/cropping.

## Model routing
- Ultra-wide → Nano Banana 2 (mandatory). Standard wide (21:9, 16:9) → GPT-Image 2 or Nano Banana 2. Typography-led at supported preset → Ideogram V3 (landscape_16_9) then crop.
