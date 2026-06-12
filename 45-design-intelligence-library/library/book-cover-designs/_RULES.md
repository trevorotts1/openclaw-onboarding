# CATEGORY RULES — Book Cover Designs (BC-)
**Read before any BC- analysis or generation. These rules override style cards where they conflict.**

## Formats & aspect ratios
| Use | Ratio | Model ratio param |
|---|---|---|
| Standard trade (6×9 in) | 2:3 | `2:3` (GPT-Image 2, Nano Banana 2, Seedream) |
| Square-ish workbook (8×10) | 4:5 | `4:5` |
| Ebook/thumbnail master | 2:3 | `2:3`, must read at 80px wide |

## Hard rules
- Front cover only (spine/back are layout work, not generation work). Generate at 2:3, 2K minimum; 4K for print.
- Mandatory text slots: {TITLE} dominant, {SUBTITLE} secondary, {AUTHOR_NAME} tertiary. Every BC card's typography dimension must define all three slots and their zone assignments.
- Title legibility at thumbnail size is the #1 success criterion — Amazon sells at 160px tall. High contrast title-vs-background is non-negotiable.
- NEVER text over faces. Author photos and subject faces get a protected zone.
- Spine-safe margin: keep critical elements ≥7% from the left edge (binding side).
- Genre signaling: record in every BC card what genre cues the style sends (business/memoir/self-help/anthology) — style transfer across genres needs operator confirmation.
- Anthology/client context: covers often carry many contributor names — when {ADDITIONAL_NAMES} present, assign a dedicated zone (typically lower band), never scattered.

## Model routing
- Default: GPT-Image 2 LONG (multiple exact text strings demand the 20K budget).
- Typography-as-art covers → Ideogram V3 DESIGN (portrait preset, expand_prompt false).
- Iterating an approved cover → Seedream 4.5 Edit.
