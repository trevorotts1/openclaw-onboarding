# CATEGORY RULES — Advertisement Designs (AD-)
**Read before any AD- analysis or generation. For Facebook-specific ads use FB- instead; AD- covers general/display/print advertising.**

## Formats & aspect ratios
| Use | Ratio | Model ratio param |
|---|---|---|
| Display rectangle (300×250 class) | ~4:3 | `4:3` |
| Display half-page (300×600 class) | 1:2 | `1:2` (GPT-Image 2) |
| Print full page | 3:4 | `3:4` |
| Print spread | 3:2 | `3:2` |
| Flyer/one-sheet | 3:4 portrait | `3:4` |

## Hard rules
- Full message stack: {HEADLINE_TEXT}, {SUBHEAD_TEXT}, {CTA_TEXT}, {LOGO_NOTE}, optional {OFFER_TEXT} (price/discount). Every AD card zones the complete stack.
- Offer prominence: when {OFFER_TEXT} exists it gets second-highest visual weight after the headline — record the offer treatment (burst/band/oversized numeral) per style.
- NEVER text over faces.
- Print-destined styles: note CMYK-safe color behavior (extreme neons shift in print) and request 4K.
- Visual hierarchy must sequence: hook (subject/headline) → value (subhead/offer) → action (CTA). Record the sequence as the eye-flow path.
- Clutter ceiling: max 5 distinct elements (subject, headline, subhead, offer, CTA+logo counted together).

## Model routing
- Default: GPT-Image 2 (layout + multiple text strings).
- People-led brand ads → Nano Banana 2. Offer/typography-led → Ideogram V3 DESIGN.
