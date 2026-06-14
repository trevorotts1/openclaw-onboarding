# NEGATIVE PROMPTING SOP — The Avoid-List System
**Version:** 1.1 | **Last Updated:** 2026-06-14
**Audience:** AI agents. One negative system, two delivery mechanisms. Read before assembling ANY generation prompt.

---

## 1. THE THREE-LAYER STACK

Every generation merges three negative layers, deduplicated, in this order:

| Layer | Lives in | Scope |
|---|---|---|
| 1. Universal baseline | This file, §2 | Every generation, library-wide |
| 2. Category baseline | Each category `_RULES.md` | Every generation in that category |
| 3. Style-specific | The style card's AVOID-LIST | Generations using that card |

At generation time: merge 1+2+3 → dedupe → deliver per §3.

## 2. UNIVERSAL BASELINE AVOID-LIST

Applies to EVERY generation:
```
misspelled text, garbled or duplicated letters, watermark, signature, UI artifacts,
distorted hands, extra fingers, warped facial features,
text overlapping any face,
ashy or greyed skin tones, desaturated deep skin, blown-out highlights on skin,
muddy low-contrast shadows, banding in gradients,
unintended borders or frames, cropped-off text at edges
```
People-specific additions (when humans appear):
```
identity drift from reference, lightened skin tone, plastic over-smoothed skin,
mismatched eyes, distorted teeth, unnatural body proportions
```

## 3. DELIVERY MECHANISMS (per model)

### 3a. Ideogram V3 — TRUE negative prompt
The ONLY endpoint with a real `negative_prompt` field (5,000 chars). Deliver the merged avoid-list there as a comma-separated phrase list. Do NOT also repeat negatives in the main prompt — wasted characters.

### 3b. Everything else — inline conversion
GPT-Image 2 (both endpoints), Nano Banana 2, Seedream 4.5 (both endpoints), Wan 2.7 have no negative field. Convert and embed:
1. Select the **10 strongest** merged items (more = prompt pollution; negatives compete with style instructions for attention). **Exception, the long-budget GPT-Image 2 path:** on a LONG-tier GPT-Image 2 prompt (the up-to-18,000-character budget; for example the Presentations slide-image-creator path, slide-image-creator SOP 9.8), the 10-strongest cap is LIFTED. With that much room the full defect-mapped block fits and pollution is not a concern at this length; state every required negative class, not a top ten. The cap still applies on SHORT and MEDIUM prompts and on the small-budget endpoints (see Seedream below).
2. Convert each to an explicit imperative sentence: `"misspelled text"` → `"Do not misspell or garble any text."`
3. Place as the **final paragraph** of the prompt (models weight endings heavily).
4. **Pair every critical negative with its positive twin** stated earlier in the prompt. Negatives steer away; positives steer toward, and you need both. This rule applies even when the 10-strongest cap is lifted:
   - Negative: "Do not render skin as ashy or desaturated."
   - Positive twin (earlier): "Rich, warm, dimensional deep brown skin with golden highlights."

## 4. WRITING RULES

- **Specific beats vague.** "no bad anatomy" does nothing. "Do not add extra fingers" works.
- **Never negate composition.** "Don't center the subject" is unreliable — use positive zone instructions instead ("subject anchored in the right third").
- **No contradictions.** If the prompt says "dramatic high-contrast lighting," the avoid-list cannot contain "harsh shadows." Audit the merged list against the positive prompt before sending.
- **Don't negate what can't appear.** Skip "no photorealism" on a flat-vector style card whose prompt already locks the render style — spend the slot on a real risk.
- **Seedream 3,000-char budget:** inline negatives max ~5 items, one sentence each. Choose by what the Test Log says this style actually gets wrong.

## 5. AVOID-LIST GROWTH PROTOCOL

The avoid-list is a living defense built from real failures:
1. A generation exhibits a defect → TEST-PROTOCOL patch loop adds it to the relevant layer (style-specific if one card, category if pattern across cards, universal if library-wide).
2. Every addition gets a Changelog line stating which failed generation motivated it.
3. Quarterly prune: items that haven't been relevant in 10+ generations of that style get demoted, keeping lists sharp.
