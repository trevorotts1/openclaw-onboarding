# TEST PROTOCOL — Style Fidelity Verification & Card Patching
**Version:** 1.1 | **Last Updated:** 2026-06-13
**Audience:** AI agents. No style card reaches `production` status without passing this protocol. Untested cards generate untested results.

> **SCOPE BANNER - READ BEFORE USE:** Style-card fidelity ONLY - NOT the QC for a webinar deck. This protocol grades the RAW PNG for 12-dimension style transfer. It does not assess assembled slides, collision/contrast/legibility on composed PPTX files, representation tally against a client audience, or image-grounding against a client's methodology. Webinar-deck QC is the Presentations department qc-specialist final-deck QC (CLIENT-WEBINAR-DECK-SOP SOP 9.5). Do NOT cite a passing TEST-PROTOCOL score as the deliverable gate for a webinar deck - those are different gates for different artifacts.

---

## 1. WHEN TO RUN

- After creating any new style card (mandatory before status `tested`).
- After any card edit that changes a prompt template (regression check).
- When a production card produces an off-style result (diagnosis mode, §5).

## 2. THE TEST DESIGN

The whole point of a style card is **transfer**. Therefore tests must use subjects DIFFERENT from the source image — testing with a similar subject proves nothing.

**Standard test set (3 generations minimum):**
1. **Near transfer** — same subject class, different specifics (source was a businesswoman → test with a businessman).
2. **Far transfer** — different subject class entirely (source was a person → test with a product or scene).
3. **Text stress** — different and longer text strings than the source (tests typography rules + face-clearance under pressure).

Run tests on the card's **recommended model + tier** first. If the card claims multi-model compatibility, spot-check one alternate model.

## 3. SCORING RUBRIC

Score each test image on the 12 dimensions, 1–5 each:
- **5** — indistinguishable from the source style
- **4** — on-style, minor drift
- **3** — recognizably related but visibly off in this dimension
- **2** — wrong, but salvageable with a prompt patch
- **1** — dimension failed entirely

**Pass criteria for `production` status:**
- Average across all 12 dimensions ≥ **4.0**, AND
- No single dimension below **3**, AND
- ZERO hard-rule violations (one violation = automatic fail regardless of scores; "text on face" fails the whole test)

Record every test as a row in the card's Test Log: date, model, tier, test subject, score, notes.

## 4. THE PATCH LOOP

When a test fails:
1. **Diagnose** the lowest-scoring dimension(s). Identify WHICH prompt language under-specified it.
2. **Patch with redundancy**, in order of force:
   a. Strengthen the adjective ("gold" → "rich saturated metallic gold")
   b. Repeat the instruction at the END of the prompt (models weight endings)
   c. Add the failure to the avoid-list ("Do not render the gold as pale yellow")
   d. Add a Model Note if the failure is model-specific
3. **Re-run only the failed test**, not the full set.
4. **Log everything**: failure mode + fix in the Test Log, version bump + reason in the Changelog. NEVER delete failure notes — they are the card's institutional memory.
5. Three consecutive failed patch attempts on the same dimension → escalate to the human operator with the test images and your diagnosis. Do not silently keep burning generations.

## 5. DIAGNOSIS MODE (production card misbehaving)

1. Check the Test Log FIRST — the failure mode may already be documented with a known fix.
2. Verify the variables were filled correctly and tier/model routing followed MODEL-SPECS.md (operator error is the most common cause).
3. Verify the model hasn't changed underneath us (provider model updates can shift behavior — check MODEL-SPECS.md date vs. today).
4. Only then enter the Patch Loop.

## 6. COMMON FAILURE MODES & STANDARD FIXES

| Failure | Standard fix |
|---|---|
| Text on or touching a face | Move text instruction earlier in prompt; add explicit zone separation ("headline confined to upper-left zone; subject's face occupies upper-right zone; minimum clear margin between them"); add to avoid-list; restate at prompt end |
| Misspelled rendered text | Quote text + "render this text exactly, correctly spelled"; route to Ideogram V3 (DESIGN) or GPT-Image 2; shorten the string if possible |
| Reference image copied verbatim (subjects/text reproduced) | Mandatory Nano Banana 2 style-reference-only directive (MODEL-SPECS §4); reduce ref count to 1; strengthen "do not copy" language |
| Washed-out / ashy deep skin tones | Add "rich, warm, dimensional deep brown skin with golden highlights"; specify lighting warmth; avoid-list "ashy, greyed, desaturated skin" |
| Saturation drift (output flatter than style) | Name the saturation explicitly ("vivid, high-saturation, punchy color throughout"); name each key color twice |
| Composition ignored (subject centered when card says right-third) | Lead the prompt with composition before subject description; use 9-zone language; restate at end |
| Style collapses on far-transfer test | Card is over-fitted to source content — re-run the Golden Rule separation test on every DNA line and strip residual content language |
| Output too busy / extra elements invented | Add density instruction ("clean composition, exactly these elements and nothing more"); list elements exhaustively; extend avoid-list |

## 7. REPRODUCIBILITY

On models with `seed` support (Ideogram V3, Wan 2.7): record the seed of every PASSING test in the Test Log. A known-good seed + prompt pair is the fastest regression check after future edits.
