# golden-creative — a client-directed (M1 `brief`) week that PASSES end-to-end with a creative block

The fictional brand **Northwind Bakehouse** runs `--mode brief` through the ONE sanctioned entry, on
a **WILDCARD-resolved theme** (I2: `themeQueue` + `wildcard: true`, seeded-deterministic pick), with
a client creative brief written as **letters from a 1962 lighthouse keeper to his daughter** (no pitch
until day 5). It walks P0 -> P1 -> P2-BRIEF -> P3 -> P4 -> P5 -> P6 -> P7 -> P8 and mints a
`PROCESS-CERTIFICATE` whose `creative` block proves BOTH 'nothing unsafe happened' AND 'the client got
EXACTLY what they asked for.'

## Reproduce

```
bash social-media-entry.sh --run-dir examples/golden-creative/run --mode brief
```

`../../verify.sh` step 2c re-runs it in a read-only temp copy and asserts the certificate below.

## What the certificate proves (creativity flows through the spine, zero gates weakened)

- **Wildcard theme** -> `creative.theme_source == "wildcard"`; `_chk_plan` still requires the resolved
  theme be non-empty (the frame), never reads what it says (the picture).
- **Two client-exact overrides, both LOGGED** (`applied.json` subset of `overrides.json`, so
  **AF-SM-OVERRIDE-UNLOGGED does NOT fire**):
  - `caption_fb_ig` **widened** to `[2000,2400]` -> the 2,393-char letter-style caption clears a band
    whose default max is 1,800. A widening the client asked for, in their own words, on the record.
  - `carousel_slides_fb_ig` reshaped to `{exact:3}` -> a short teaser carousel, accepted within the
    real 2-image assembly floor (R2).
- **Verbatim client copy** -> a supplied LinkedIn line whose `published` == `supplied` + the configured
  `ctaLink` append (the engine may only APPEND, never edit) -> **AF-SM-CLIENT-COPY-MUTATED does NOT
  fire**; `client_copy_shas` length 1.
- `emDashPolicy: allow-content`, `seriesLength: 5`, `arcTemplate: custom`, `stylePick: editorial-mono`
  all logged on the certificate.

The FB carousel caption and its 3 slide image prompts are **genuinely authored** in the lighthouse-
keeper voice (the caption is a real 2,393-char letter; each slide prompt is a distinct 1,000-1,700-char
editorial-monochrome art direction) and clear the exact bands `prove_bands.py` enforces with the
logged overrides applied. Provers froze the FRAME; the client owned the PICTURE.
