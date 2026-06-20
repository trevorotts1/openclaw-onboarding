# SOP: Logo Consistency (One Locked Mark, Image-to-Image)

**Cluster:** Design System
**Owner roles:** Brand Steward (locks the single logo asset, pins it in the STYLE BLOCK) + Slide Image Creator (composites it image-to-image on every slide). Enforced by: QC Specialist (Phase 5 image QC, Phase 6 final deck QC).
**Master authority:** universal-sops/CLIENT-WEBINAR-DECK-SOP.md (Section 7.2 logo chip device, 7.3 element 10, Appendix A Kie.ai image-to-image)
**Version:** 1.0

> ONE locked logo mark, used identically on every slide it appears on. The forensic reference deck's logomark MUTATED across the deck into at least four-plus different marks (ringed leaf, bare leaf, a serif monogram, mountain peak, founders-tagline lockup; in V8 a roundel, a sprout, a tall tree, a mountain mark, a generic monogram) because it was generated text-to-image per slide. This SOP forces the image-to-image path with one canonical asset at a fixed size and position, and auto-fails any drift or misspelled render.

---

## 1. Purpose

Guarantee that when a logo asset exists, the SAME mark appears at the SAME size in the SAME position on every slide. The root cause of the forensic reference deck's mutation was that the mark was re-drawn (text-to-image) on each slide, so the model reinvented it, and the existing logo auto-fail only checked for absent or distorted, not "a different mark than the locked asset." This SOP closes both gaps: it mandates the image-to-image composite path and it makes logo DRIFT an auto-fail.

---

## 2. The Hard Rule

1. The Brand Steward locks ONE canonical logo asset (a single file URL) for the client and records it in the STYLE BLOCK as `LOGO_URL`. No other variant, monogram, icon, mountain mark, sprout, or tagline lockup is ever used. If the client supplied multiple lockups, the Brand Steward picks ONE and forbids the rest in the STYLE BLOCK.
2. When `LOGO_ON_SLIDES = true`, the logo is placed via IMAGE-TO-IMAGE: the locked `LOGO_URL` is passed as a reference image in `input.input_urls` to gpt-image-2-image-to-image, so the model COMPOSITES the real asset rather than DRAWING a new mark. Text-to-image generation of the logo mark is banned.
3. The logo placement is fixed and identical on every slide: bottom-right corner, approximately 9% of slide width, on a clean white chip with a subtle 1px gold border, minimum 40px (about 5%) from any edge, never recolored, never distorted, never clipped. (Hero placement, bottom-center ~10 to 11%, is reserved for the few pivotal/close slides and is the ONLY permitted deviation; it is declared in the treatment table.)
4. Any TEXT inside the logo (the brand name/tagline) must render correctly spelled. If the logo carries text and the render misspells or garbles it, that is a logo failure (and a text-render failure).

---

## 3. The Enforcement Check (what auto-fails the slide/deck)

| Trigger | Verdict |
|---------|---------|
| `LOGO_ON_SLIDES = true` but the prompt does not pass `LOGO_URL` via `input.input_urls` (i.e. it is being drawn text-to-image) | FAIL that prompt at Phase 3 |
| The rendered logo on a slide is a DIFFERENT mark than the locked asset (different shape, different icon, a monogram where the asset is a wordmark, a mountain/sprout/tree variant) | AUTO-FAIL that slide (logo drift) |
| The logo mark DRIFTS slide to slide (two slides show two different marks) | AUTO-FAIL the deck (logo not locked) |
| The logo is absent, illegible, distorted, recolored, clipped, or wrongly placed when `LOGO_ON_SLIDES = true` | AUTO-FAIL that slide (existing AF-I4) |
| The brand name/tagline INSIDE the logo is misspelled or garbled in the render | AUTO-FAIL that slide (logo text + text-render) |
| The logo size/position varies beyond the locked spec (other than the declared hero-placement slides) | FAIL that slide |

**How QC detects drift (Phase 6 final deck QC):** the QC agent pulls the logo region from every slide and compares the mark to the locked `LOGO_URL` asset. If any slide's mark differs from the asset, or if two slides differ from each other, it is a drift auto-fail. This is a cross-slide check, not a single-slide check, so it runs at the final deck gate over all rendered pages, in addition to the per-slide check at Phase 5.

---

## 4. PASS vs FAIL Examples (from the actual forensic reference deck defects)

**FAIL (the forensic reference deck, original deck):** the logomark mutated across the deck into at least four marks (ringed leaf, bare leaf, a serif monogram, mountain peak, founders-tagline lockup, seen across slides 9, 10, 19, 21, 28, 36 and others), proving it was generated text-to-image per slide. Verdict: deck-level AUTO-FAIL (logo not locked, drifting).

**FAIL (the forensic-deck V8 regression):** the logo still mutated into a roundel, a sprout, a tall tree, a mountain mark, a generic monogram, and varying lockups across s02, s07, s22, s24, s28, s32, s40, s58. Also a logo-text render bug: "GRABLED BRANDCO" on s16 (garbled brand name). Verdict: deck-level AUTO-FAIL plus per-slide AUTO-FAIL on s16 (logo text garbled).

**PASS (the gold-standard reference deck):** ONE logo (the brand wordmark), bottom-right, ~9% width, on a white chip with a 1px gold border, "never recolored, never distorted, never clipped," identical on every slide via the image-to-image composite path, with hero placement (bottom-center ~10 to 11%) reserved only for the pivotal moments (s50, s64) and the close. Verdict: PASS.

**PASS (single slide):** the prompt declares "the first reference image is the logo; composite it bottom-right at 9% width on a white chip with a 1px gold border, do not redraw it," `LOGO_URL` is in `input.input_urls`, and the rendered slide shows the exact locked mark. Verdict: PASS.

---

## 5. Escalation / Repair Path

1. Phase 3 prompt FAIL (logo being drawn text-to-image): QC loops the prompt back to the Slide Image Creator; the writer adds the image-to-image reference instruction and the `LOGO_URL` is passed in `input.input_urls`.
2. Phase 5 / Phase 6 logo-drift AUTO-FAIL: the affected slides regenerate via the image-to-image path with the locked asset. If the composite path still drifts after two attempts, the REAL logo IMAGE is composited onto the rendered slide PNG via the PIL image-composite path (SOP-IMG-05), baked into the image BEFORE assembly. This is an IMAGE composite of the real mark and GUARANTEES the locked mark — it is NOT a native PPTX text/element overlay. The native-text overlay path is ELIMINATED (Decision 5C): no `pptx_text_overlays.json`, and any native (non-notes) on-slide text run is AF-OVERLAY-DELIVERED. Critical TEXT that garbles is fixed by the Slide Image Creator's re-prompt/re-seed loop then human escalation — never an overlay.
3. Logo text garbled (e.g. "GRABLED BRANDCO"): treat as the text-render failure; composite the logo (with its text) as a native layer so the brand name is guaranteed correct.
4. Multiple lockups supplied and the wrong one rendered: the Brand Steward re-confirms the single canonical `LOGO_URL` and forbids the others in the STYLE BLOCK; affected slides regenerate.
5. 3 loops on the same logo failure: escalate to the Director, then the human owner. File a bug ticket.

---

## 6. The Gold-Standard Design Proof (the full design system this cluster encodes)

This is the gold-standard design system the whole design-system cluster ports to every client. It is recorded here as the single reference so the Typography Architect, Brand Steward, and Slide Image Creator share one source.

- **5-archetype layout system:** A1 full-bleed photo + headline overlay; A2 photo one side + text opposite (~45/55); A3 photo-top / data-bottom; A4 type-dominant punch; A5 portrait/selfie (image-to-image). Rotated across the deck so independently generated images read as ONE deck. (Variable Layout SOP.)
- **Locked weight ladder:** Montserrat (or client family) with BLACK = headlines/hero numbers, ExtraBold = sub-heads, Bold = labels/banners/tag prices, Medium/SemiBold + Italic = body/tertiary/captions. (Creative Typography Guide SOP.)
- **Locked brand hexes (example, the client supplies their own):** warm off-white base #FBF7F4, accent #C8104E, gold #C9A24B, charcoal headlines #231F20; white base dominant, brand colors as accents only, no black backgrounds unless DARK_OK.
- **Price/effect typography:** metallic gold gradient (#B8860B to #E6C66E "liquid gold") on hero price numerals; soft radial GLOW in the accent on the LIVE price; double-thick DRAWN gold diagonal STRIKETHROUGH on DEAD prices; per-word color emphasis; giant faint watermark numerals on section reveals. Applied across the WHOLE ladder, not one beat. (Creative Typography Guide + master SOP 7.4.)
- **Pure-typography hook slides:** the hook line large over a low-opacity image, no competing imagery, no footer band. (Pure-Typography Hook Slides SOP.)
- **Logo:** ONE locked mark, bottom-right ~9% width, white chip with 1px gold border, never recolored/distorted/clipped, composited image-to-image on every slide; hero placement bottom-center ~10 to 11% reserved for pivotal/close slides only. (This SOP.)

---

## 7. Research Base

- The gold-standard design proof (the locked logo spec, the image-to-image composite path, the bottom-right ~9% placement).
- Master SOP Section 7.2 (logo chip device), 7.3 element 10 (logo placement + contrast plate), Appendix A (the Kie.ai gpt-image-2-image-to-image path and `input.input_urls` reference-image mechanics).
- The forensic Dimension F (logo mutation root-caused to text-to-image-per-slide generation; this SOP forces image-to-image and adds the drift auto-fail).
