# SOP-GIP-01 — Graphics Prompt Anatomy (BINDING)

**ID:** SOP-GIP-01
**Classification:** ZHC SOP — Graphics Image Protocol (GIP)
**Owner Role:** Prompt Author (authoring, per decision GK-D2) + Prompt QC Specialist (independent grading, judge != writer) + Generation Operator (mechanical preflight backstop, brand verification via Brand Systems Specialist)
**Version:** 1.1 | **Date:** 2026-07-15
**Status:** CANONICAL
**Library-version pin:** MODEL-SPECS v1.4, prompt-bands.json v1 (§-refs verified 2026-07-10)

---

## Why this exists

The Graphics department had MAX-only prompt caps (`diu_validator.py prompt-caps`, SHORT ≤500 /
MEDIUM ≤2,800 / LONG ≤18,000) and **no minimum floor anywhere** — a one-line prompt could reach
the paid Kie.ai / GPT-Image 2 API unchallenged (diagnosis G1). This SOP is the graphics analogue
of the Presentations 9,000-character prompt floor + quality gate: every production image prompt is
authored to a TEN-ELEMENT anatomy and validated by `diu_validator.py prompt-band` **before**
submission. SOP-DIU-601 preflight step 2 now runs the **BAND** check (floor + cap + quality), not
just the cap check.

> Design principle (copied from Presentations): *"Enforcement, not description — a rule without a
> gate is a suggestion."* Clearing the floor is **NECESSARY, never SUFFICIENT**: the quality gate
> (elements 4, 5, 8, 10) fails independently of length (AF-GIP-PROMPT-QUALITY).

Band floors/caps live in `45-design-intelligence-library/library/_system/prompt-bands.json`
(operator-ratifiable). The bands:

| Band | Tier | MIN (floor) | MAX (cap) | Distinct-word floor | Text-bearing |
|---|---|---|---|---|---|
| `text_bearing_long` | LONG | 5,000 | 18,000 | 150 | yes |
| `visual_long` | LONG | 2,500 | 18,000 | 120 | no |
| `medium` | MEDIUM | 800 | 2,800 | 60 | no |
| `short_draft` | SHORT | 200 | 500 | 25 | no (NEVER a client deliverable) |

---

## The TEN-ELEMENT anatomy (every production prompt)

1. **ASSET CLASS + BAND declaration (first line):** `ASSET: <class> | BAND: <band-id>`. The band id
   selects the floor/cap/quality contract the validator enforces.
2. **SUBJECT + SCENE:** who/what, action, environment — specific, never generic stock language.
3. **COMPOSITION GRID:** thirds + zone percentages; focal hierarchy; safe margins for the target surface.
4. **STYLE BLOCK:** the style-card DNA or BRAND.md tokens (`{BRAND_COLOR_1/2}`, `{FONT_NOTE}`,
   `{LOGO_NOTE}`), verified by the Brand Systems Specialist BEFORE submission (existing rule,
   brand-systems-specialist.md §Brand Systems Verification). Include at least one brand HEX and an
   explicit type size on any text-bearing surface.
5. **TYPOGRAPHY + VERBATIM COPY (text-bearing bands only):** every baked string verbatim, each
   wrapped in a spelling-lock: *"Render this exact string, letter-for-letter, correctly spelled, with
   no added, dropped, doubled, or substituted characters: '<STRING>'."* A verbatim string without its
   lock is an AUTO-FAIL (AF-GIP-PROMPT-QUALITY).
6. **LIGHTING + COLOR GRADE:** direction, mood, grading block with brand hexes.
7. **PEOPLE / REPRESENTATION:** explicit casting; likeness work routes to the Photo Shoot Director via
   the Likeness Rights Officer (existing DIU law); **no demographic default** (a hardcoded split such
   as "60/30/10" is a hard AF-R3 fail — representation comes from the client's captured audience).
8. **LOGO / REFERENCE DIRECTIVE:** image-to-image `input_urls` handling; the STYLE-REFERENCE-ONLY
   sentence whenever refs are stylistic (MODEL-SPECS §4 — MANDATORY for GPT-Image 2 I2I and
   Nano Banana 2): *"Use the attached images only as style reference for color grading, lighting, and
   composition — do not copy their subjects, faces, or text."*
9. **TECHNICAL:** endpoint id, aspect ratio (REQUIRED on Seedream), resolution, `output_format`
   (`png` for text-bearing), `watermark:false` on Wan.
10. **NEGATIVE BLOCK (final paragraph):** imperative "Do not…" sentences covering the eight defect
    classes (garbled text, logo mutation, anatomy, contrast/legibility, placeholder tokens,
    demographic default, watermark, style-drift). The validator requires the block to name **≥ 6 of
    the 8** classes.

---

## Mandatory gate (run before every `createTask`)

```
python3 45-design-intelligence-library/scripts/diu_validator.py prompt-band \
    --band <band-id> --prompt-file <assembled.txt> \
    [--copy "<verbatim string>" ...] [--style-ref] [--run-dir <job-dir>]
```

Exit codes: **0** pass; **3** = AF-GIP-PROMPT-FLOOR (under the band MIN) or AF-DIU-PROMPT-CAP (over the
band MAX) — the prompt is NOT submitted and NOT rendered; re-author (never truncate up to the floor);
**6** = AF-GIP-PROMPT-QUALITY (length cleared but a quality tooth failed). A standalone CI prover
(`scripts/prove_gip_prompt_floor.py --self-test`) exercises the same functions on fixtures so the
floor can never become a length-only rubber stamp.

**Handoff:** on a floor/cap/quality failure, return the itemized problem list to the prompt author
(the Generation Operator does not improvise fixes). On pass, proceed to SOP-DIU-601 preflight steps
3–10, then submit.

**Authoring + independent grading (GK-21, decision GK-D2 — Option A phased):** production prompts are
assembled by the dedicated Prompt Author (`prompt-author-graphics.md`), never self-authored by the 15
producing roles, and independently graded by the Prompt QC Specialist (`qc-specialist-prompt-graphics.md`,
judge != writer) BEFORE the Generation Operator's own preflight re-runs this same gate as a mechanical
backstop — dispatched per `chief-design-officer.md` SOP 9.9. The gate above is unchanged; only WHO runs
it first and WHO authors the prompt text has moved off the 15 self-authoring roles onto this dedicated pair.
