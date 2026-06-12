# CATEGORY RULES — Magazine Cover Designs (MAG-)
**Read before any MAG- analysis or generation. These rules override style cards where they conflict.**

## Formats & aspect ratios
| Use | Ratio | Model ratio param |
|---|---|---|
| Standard US magazine (8.375×10.875) | ~3:4 | `3:4` |
| Digital-only cover | 3:4 or 4:5 | `3:4` / `4:5` |

## Hard rules
- The densest text format in the library: masthead {MASTHEAD_TEXT}, main coverline {HEADLINE_TEXT}, 2–5 secondary coverlines {COVERLINE_1..N}, issue/date line. Every MAG card must zone ALL of these.
- Masthead owns the top band (upper-left → upper-right). Subject's head may overlap the masthead bottom edge (classic editorial move) — record whether the style does this.
- Coverlines hug left and/or right rails; the subject owns the center column. Face stays fully clear of all type.
- Subject eye contact: editorial covers almost always use direct-to-camera gaze — record gaze direction as a hard rule per style.
- Coverline hierarchy: main coverline ≥2.5× secondary size. All text high-contrast against its local background (record per-zone contrast strategy).
- Barcode zone: reserve lower-left or lower-right clean corner.

## Model routing
- Default: GPT-Image 2 LONG — only model that reliably handles 6+ exact text strings in one layout.
- Backup: Nano Banana 2 LONG. Never Seedream (3K chars cannot hold a full cover spec).
