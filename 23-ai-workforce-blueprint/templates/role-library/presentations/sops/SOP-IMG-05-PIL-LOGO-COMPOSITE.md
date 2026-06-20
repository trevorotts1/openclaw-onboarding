# SOP-IMG-05: PIL LOGO IMAGE COMPOSITE (PIPELINE DETERMINISM)

> **Decision 5C (AF-OVERLAY-DELIVERED):** the native-text overlay half of this SOP is ELIMINATED. This SOP now composites ONLY the locked logo IMAGE onto the slide PNG (image compositing — the real mark, baked into the image before assembly). It NEVER writes `pptx_text_overlays.json` and NEVER routes any text to a native PPTX text box. Garbled/mis-styled HERO TEXT is fixed by the Slide Image Creator's re-prompt/re-seed loop, then human escalation — never an overlay.

**Cluster:** Image-Design System (pipeline post-processing)
**Version:** v1.0.0 (2026-06-14)
**Master authority:** universal-sops/CLIENT-WEBINAR-DECK-SOP.md; SOP-DESIGN-04-LOGO-CONSISTENCY.md; SOP-IMG-01-KIE-CALL-MECHANICS.md
**Owning role at write time:** Slide Image Creator (declares the composite in the prompt and the post-render manifest); PPTX Assembly Specialist (executes the PIL step)
**Enforced at the gate by:** QC Specialist - Presentations (AF-LOGO, AF-GRAD, AF-TYPE)
**Purpose:** Make logo identity and hero-string rendering deterministic via code, eliminating two entire defect classes -- logo drift and gradient-on-type / weak-type -- at the pipeline level before QC ever runs.

---

## 1. THE TWO PIPELINE DETERMINISM RULES

### Rule A -- PIL Logo Composite (every slide, mandatory)

After Kie.ai returns a rendered PNG, a Python PIL post-processing step runs on every slide before QC. It composites the one locked logo PNG (referenced by `LOGO_URL` in the brief) into the lower-right chip at a fixed position and scale. This step is mandatory and unconditional on every slide in the deck.

Why: the image model cannot guarantee pixel-perfect logo reproduction. Even image-to-image mode with the logo as the first reference drifts. The PIL composite is the write-once, read-many identity lock that pairs with the read-time AF-LOGO check (SOP: qc-specialist-presentations-sops.md). With this step in place the logo on every slide is exactly LOGO_URL, no model creativity involved.

**The PIL composite procedure:**

1. Download the current slide PNG from `working/renders/slide-NN.png`.
2. Download `LOGO_URL` once per deck run, cache as `working/brand/logo-ref.png`. Verify the download is non-empty before proceeding.
3. Composite the logo into the lower-right chip:
   - Scale the logo PNG to approximately 9% of the slide width (230 px on a 2560-px wide slide), maintaining aspect ratio.
   - Place the top-left corner of the scaled logo at: `x = slide_width - logo_width - margin`, `y = slide_height - logo_height - margin`, where `margin = max(40px, floor(0.025 * min(slide_width, slide_height)))`.
   - Apply a white chip behind the logo (padding 8px on all sides, 1px gold border: `#C4A44D` or the client's primary gold hex from the STYLE BLOCK) using PIL `ImageDraw.rectangle`.
   - Use `Image.paste(logo_img, (x, y), mask=logo_img.split()[3] if logo_img.mode == 'RGBA' else None)` to composite with transparency if the logo has an alpha channel.
4. Write the composited result back to `working/renders/slide-NN.png`, overwriting the raw Kie output.
5. Record the composite in `working/checkpoints/logo_composite_log.json`: `{"slide": "slide-NN", "logo_url": "<LOGO_URL>", "chip_x": x, "chip_y": y, "logo_width_px": logo_width, "logo_height_px": logo_height, "composite_ts": "<ISO-timestamp>"}`.

**Do not** rely on the image model's interpretation of the logo -- even a correct image-to-image call is treated as a layout hint only. The PIL composite is the identity guarantee.

**Failure mode:** If the PIL step fails (network error downloading LOGO_URL, corrupt PNG, PIL exception), halt and flag to the Director. Do not advance a slide without the composite: an uncomposited slide is a logo-drift risk and is treated as a composite-failure auto-fail at QC (AF-LOGO sub-condition "composite not logged").

---

### Rule B -- ELIMINATED: Native Text Overlay for Hero Strings (Decision 5C, AF-OVERLAY-DELIVERED)

The former native-text overlay rule is REMOVED. ALL text — hero price numbers, callout strings, headlines, gradient-risk strings, struck prices — is baked into the SINGLE composed gpt-image-2 image by the model. There is no NATIVE-OVERLAY-PRIMARY class, no "render the background only and overlay the text later" instruction, and no `pptx_text_overlays.json`.

When a critical verbatim string garbles or mis-styles at render (including the gradient-risk strings the gradient ban in Section 2 targets), the remedy is the Slide Image Creator's RE-PROMPT / RE-SEED loop (tighten the spelling-lock + negative block, new seed, re-render the composed image), then HUMAN ESCALATION if it persists. A native PPTX text box is never the remedy.

**Why no native overlay:** a native PPTX text run is not part of the composed image; it is the exact defect Decision 5C eliminates. The mere presence of a `pptx_text_overlays.json` at assembly, or any native (non-notes) on-slide text run in the delivered PPTX, is AF-OVERLAY-DELIVERED, enforced by `scripts/build_deck.py` `_chk_no_overlay`. The gradient ban (Section 2) is enforced inside the prompt + AF-GRAD, not by extracting text to an overlay.

This SOP's ONLY post-render composite is Rule A — the locked logo IMAGE onto the PNG.

---

## 2. GRADIENT BAN (producing rule -- striped from the prompt SOP)

Effective with this SOP, the following prompt language is PROHIBITED on any slide in any presentation deck:

- "liquid-gold gradient (#B8860B to #E6C66E)" or any gold-to-gold gradient on type
- "metallic warm gold glowing" or "warm metallic" on type regions
- "soft warm radial glow" or "radial glow" on type or behind type
- "raspberry glowing result line" or any glow/bloom applied to a text element
- Any gradient FILL on a typographic element (text region, price number, headline)

Replace with: flat brand-color hero type (solid brand color, high contrast against the white base). The STYLE BLOCK gold is used as a flat solid color on kicker labels and divider rules only. Gradients are permitted in the photographic/atmospheric layer (a soft scrim gradient behind type is allowed; the scrim is on the image, not the text itself).

**The QC enforcement of this ban is AF-GRAD (qc-specialist-presentations-sops.md).** Any gradient or glow detected on a type region via the gradient/glow detector is a hard auto-fail. The producing ban here is the write-time guard; AF-GRAD is the read-time guard.

---

## 3. INTEGRATION WITH SOP-DESIGN-04 AND SOP-IMG-01

- SOP-DESIGN-04-LOGO-CONSISTENCY.md step 2 already defines the PIL composite as the belt-and-suspenders fallback after two failed image-to-image render attempts. This SOP promotes the PIL composite to a MANDATORY first-pass step on every slide (not a fallback). SOP-DESIGN-04 step 2 is superseded: the composite runs unconditionally.
- SOP-IMG-01-KIE-CALL-MECHANICS.md check 9 (logo identity) is unaffected. The PIL composite is a post-Kie step; the image-to-image prompt directive (AF-P15 at write time) remains required for layout conditioning.
- The AF-LOGO check in the QC gate reads the composited slide PNG, not the raw Kie output. The SSIM threshold (>= 0.97 on the logo chip region against LOGO_URL) is the read-time enforcement.

---

## 4. OUTPUTS PRODUCED

- `working/renders/slide-NN.png` (overwritten with PIL-composited logo IMAGE, for every slide)
- `working/checkpoints/logo_composite_log.json` (one entry per slide)
- (NO pptx_text_overlays.json — the native-text overlay path is eliminated, Decision 5C; its presence is AF-OVERLAY-DELIVERED)
