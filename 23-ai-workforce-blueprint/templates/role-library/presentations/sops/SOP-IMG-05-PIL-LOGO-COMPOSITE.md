# SOP-IMG-05: PIL LOGO COMPOSITE + NATIVE TEXT OVERLAY (PIPELINE DETERMINISM)

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

### Rule B -- Native Text Overlay for Hero Strings (triggered by two-failed-attempts OR by SOP directive)

The native text overlay fallback (SOP 9.5 step 7 in slide-image-creator-sops.md) is generalized: it applies to ANY critical verbatim string that garbles or mis-styles twice at render. In addition, the following string classes are declared as NATIVE-OVERLAY-PRIMARY -- meaning the prompt instructs the model to render the visual background without baking these strings, and the strings are composited by code as PPTX native text after image generation:

- Hero price numbers and callout strings on offer / CTA slides (the `$97`, `15 Minutes`, and any per-rung price).
- Gradient-risk strings: any headline or sub that the producing SOP (slide-image-creator-sops.md SOP 9.6 Part A, gradient ban) identifies as "gradient-risk" (typically value/price/headline on offer slides where the prior prompt language used "liquid-gold gradient" or "radial glow").

**Why native overlay for gradient-risk strings:** the model cannot be reliably instructed to render a gradient-free flat font on strings that prior training associated with gradient/glow effects. The native overlay guarantees flat brand-color type at any weight and size without relying on the model.

**The native overlay procedure:**

1. In the prompt, where a native-overlay-primary string appears, instruct the model: "Render the visual background and scene only. The string '[HEADLINE]' will be composited as a native text layer in post-processing. Do not render this text in the image."
2. Record the intended string in `working/checkpoints/pptx_text_overlays.json`:
   ```json
   {
     "slide": "slide-NN",
     "text": "<exact string>",
     "font_family": "Montserrat",
     "font_weight": "Black",
     "font_size_pt": 78,
     "color_hex": "#1A1A1A",
     "position_zone": "lower-left third",
     "strike": false,
     "note": "native overlay primary -- gradient-risk string"
   }
   ```
3. The PPTX Assembly Specialist reads `pptx_text_overlays.json` and composites every entry as a native PPTX text box at Phase 6, per the font, size, color, and position declared.
4. For struck prices, set `"strike": true` and include both the old price (strike=true) and the new price (strike=false) as separate entries.

**Failure mode:** If the PPTX Assembly Specialist cannot composite a native overlay entry (font unavailable, coordinate out of bounds), escalate to the Director. A slide missing its declared native overlay is an AF-TYPE risk and must not ship.

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

- `working/renders/slide-NN.png` (overwritten with PIL-composited logo, for every slide)
- `working/checkpoints/logo_composite_log.json` (one entry per slide)
- `working/checkpoints/pptx_text_overlays.json` (appended with native-overlay-primary strings)
