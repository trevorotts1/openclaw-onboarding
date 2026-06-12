# CATEGORY RULES — Facebook Ad Designs (FB-)
**Read before any FB- analysis or generation. These rules override style cards where they conflict.**

## Formats & aspect ratios
| Placement | Ratio | Model ratio param |
|---|---|---|
| Feed (default) | 1:1 | `1:1` |
| Feed alternate | 4:5 | `4:5` (GPT-Image 2, Nano Banana 2) |
| Stories / Reels | 9:16 | `9:16` |
| Link/landscape | 16:9 (1.91:1 cropped) | `16:9`, design center-weighted |

## Hard rules
- Text-light by design: Facebook deprioritizes text-heavy creative. Target ≤20% of frame as text; headline ≤8 words.
- NEVER place text over faces. Reserve one full vertical third for the subject's face zone.
- Safe zones for 9:16: keep all text/logos inside the middle 80% vertically — top 250px and bottom 320px (at 1080×1920) are covered by platform UI.
- Single focal point. One subject, one headline, one CTA. Ads with competing focal points fail.
- CTA visual weight: the CTA element must be identifiable within 1 second at thumbnail size. Test: does the design read at 200px wide?
- High thumb-stop contrast: dominant color must contrast hard with Facebook's white/dark-mode feed background.
- Brand default: bold, vibrant, high saturation, cinematic (client brand standard — see workspace brand config) unless card says otherwise.

## Model routing (overrides MODEL-SPECS defaults)
- Default: GPT-Image 2 (layout adherence) or Nano Banana 2 (people-led creative).
- Photoreal person + minimal text → Nano Banana 2.
- Text/offer-led creative → GPT-Image 2 LONG or Ideogram V3 DESIGN.
