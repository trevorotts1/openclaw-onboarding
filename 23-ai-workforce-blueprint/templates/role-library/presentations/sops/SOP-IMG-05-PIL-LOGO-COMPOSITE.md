# SOP-IMG-05: LOGO IDENTITY MECHANISMS AND THE LOCAL-CANVAS BAN (PIPELINE DETERMINISM)

> **File name note:** the file keeps its historical name `SOP-IMG-05-PIL-LOGO-COMPOSITE.md` because other documents link to it. The shipped renderer does NOT run a Pillow logo composite (see Rule A). This SOP describes exactly what `scripts/build_deck.py` does today.
>
> **Decision 5C (AF-OVERLAY-DELIVERED):** the native-text overlay half of this pipeline is ELIMINATED. Garbled or mis-styled HERO TEXT is fixed by the Slide Image Creator's re-prompt and re-seed loop, then human escalation, never an overlay. A `pptx_text_overlays.json`, or any native (non-notes) on-slide text run, is AF-OVERLAY-DELIVERED.

**Cluster:** Image-Design System (pipeline determinism)
**Version:** v2.0.2 (2026-10-06)
**Master authority:** universal-sops/CLIENT-WEBINAR-DECK-SOP.md; SOP-DESIGN-04-LOGO-CONSISTENCY.md; SOP-IMG-01-KIE-CALL-MECHANICS.md; `07-kie-setup/references/kie-common-rules.md`
**Owning role at write time:** Slide Image Creator (declares the logo reference in the prompt); Slide Submitter (confirms the local logo file is configured before the render); PPTX Assembly Specialist (the assembly step places a local logo file)
**Enforced at the gate by:** QC Specialist - Presentations (AF-LOGO, AF-GRAD, AF-TYPE)
**Purpose:** Make logo identity deterministic where code can guarantee it, and keep Pillow out of slide creation.

---

## 1. THE PIPELINE DETERMINISM RULES (Rule A logo mechanisms; Rule B eliminated; Rule C scope ban)

### Rule A -- Logo identity: the two mechanisms the shipped renderer has

`build_deck.py` resolves the logo from a `--logo` argument if it is run with one, otherwise from `working/copy/intake.json` `brand.logo_image_path`, and does exactly one of two things with it. Nothing else touches the logo.

**What the canonical command reaches today:** `presentation-canonical-entry.sh` and `run_signature_deck.py` have NO `--logo` option (the entry exits with "unknown argument") and do not forward one to `build_deck.py`. Through the canonical path only mechanism 2 is reachable, fed by `intake.json` `brand.logo_image_path` (a LOCAL PNG file, absolute or relative to the run directory; a URL there makes the renderer exit 2). A logo that exists only as a hosted URL is downloaded once to a local PNG in the run directory and `brand.logo_image_path` is pointed at it, or the Slide Submitter escalates to the Director.

1. **`--logo` is a public https URL.** Reachable today only by invoking `build_deck.py` with `--logo`, which the canonical entry does not forward, so it needs the entry and runner to be changed (lane D) before any agent can use it. Every slide is rendered image-to-image with that URL as the single reference in `input.input_urls` (the pinned image-to-image model from `presentation_job/model_catalog.json`, alias `image.i2i`). The model places the mark; the prompt carries the "place, do not redraw, recolor, or restyle it" sentence (SOP-IMG-01 check 3). No local file is composited in this mode.
2. **A local file path** (`brand.logo_image_path` in `intake.json`, the canonical route, or a local `--logo` on a direct `build_deck.py` run). The render stays text-to-image (alias `image.t2i`). At assembly, `assemble_pptx` places that exact PNG file on every slide as a PICTURE shape on top of the full-bleed slide image, top-right, about 13 percent of the slide width (`LOGO_WIDTH_FRACTION` 0.13) with a 0.25 inch margin (`LOGO_MARGIN_IN`), the same size and position on every slide, bytes written verbatim so transparency is preserved. A picture shape is not native text, so this is not AF-OVERLAY-DELIVERED.

What the renderer does NOT do (never describe or ask for these as if they existed): a Pillow composite onto `working/renders/slide-NN.png`, a lower-right white chip with a gold border, a `working/checkpoints/logo_composite_log.json`, a post-render logo step on a URL-logo deck, or any automatic fallback from image-to-image to a composite after two failed renders.

**Why this matters:** a logo that must be pixel-exact belongs in the local-file mechanism (the exact file is placed, no model creativity). The image-to-image mechanism conditions the model on the logo but cannot guarantee pixel-perfect reproduction, so QC checks the result (AF-LOGO, AF-F7).

**Failure handling:** if the logo mutates or garbles on a URL-logo deck, tighten the logo sentence and negative twin and re-render through the canonical render command (re-prompt and re-seed, SOP-IMG-01). If it still mutates after two image-to-image attempts, escalate to the Director, who may switch the deck to a local logo file (mechanism 2) by having the intake owner set `brand.logo_image_path` to that file. Never hand-edit a PNG, never write a local compositing script into the run directory (Rule C), and never hand-submit to KIE.ai.

---

### Rule B -- ELIMINATED: Native Text Overlay for Hero Strings (Decision 5C, AF-OVERLAY-DELIVERED)

The former native-text overlay rule is REMOVED. ALL text (hero price numbers, callout strings, headlines, gradient-risk strings, struck prices) is baked into the SINGLE composed image from the pinned model (`image.t2i` in `presentation_job/model_catalog.json`) by the model. There is no NATIVE-OVERLAY-PRIMARY class, no "render the background only and overlay the text later" instruction, and no `pptx_text_overlays.json`.

When a critical verbatim string garbles or mis-styles at render (including the gradient-risk strings the gradient ban in Section 2 targets), the remedy is the Slide Image Creator's RE-PROMPT / RE-SEED loop (tighten the spelling-lock + negative block, new seed, re-render the composed image), then HUMAN ESCALATION if it persists. A native PPTX text box is never the remedy.

The presence of a `pptx_text_overlays.json` at assembly, or any native (non-notes) on-slide text run in the delivered PPTX, is AF-OVERLAY-DELIVERED, enforced by `scripts/build_deck.py` `_chk_no_overlay`. The gradient ban (Section 2) is enforced inside the prompt and AF-GRAD, not by extracting text to an overlay.

---

### Rule C -- PIL/Pillow NEVER fabricates or edits a slide canvas (the hard scope ban)

Pillow/PIL is NOT authorized anywhere in the Presentations pipeline to create or modify `working/renders/slide-NN.png`. The only logo step with a local file is Rule A mechanism 2, which is done by python-pptx at assembly and never writes a PNG.

**BANNED, each an auto-fail (`AF-LOCAL-CANVAS` / `AF-CANONICAL-RENDER-BYPASS`):**

- `Image.new('RGB', (2048,1152), ...)` / `Image.new('RGB', (2560,1440), ...)` / any `Image.new` that fabricates a full-slide canvas (a flat cream card, a color wash, a "typography" card, a background plate).
- `ImageDraw`-drawn headlines, hook lines, body text, or any slide text. Drawing words with PIL is the local-render defect, never a remedy.
- Using PIL to produce a "pure-typography hook slide" because it "has no photo." Pure-typography hook slides are KIE.ai image renders (SOP-DESIGN-02 section 2.0; SOP-IMG-01 section 1A) and carry a real KIE task id.
- Any PIL/Pillow write to `slide-NN.png`, before or after KIE.ai returns it.

The QC cross-check reads, for every slide, a real KIE task id (in `working/checkpoints/pending_tasks.json` and the render record in `process_manifest.json`) and a PNG above the 51,200-byte floor (`PLACEHOLDER_MIN_BYTES`); a slide whose PNG was born from `Image.new` (the roughly 26 to 30 KB flat-card signature, no KIE task id) is the exact defect this rule kills.

---

## 2. GRADIENT BAN (producing rule)

The following prompt language is PROHIBITED on any slide in any presentation deck:

- "liquid-gold gradient (#B8860B to #E6C66E)" or any gold-to-gold gradient on type
- "metallic warm gold glowing" or "warm metallic" on type regions
- "soft warm radial glow" or "radial glow" on type or behind type
- "raspberry glowing result line" or any glow/bloom applied to a text element
- Any gradient FILL on a typographic element (text region, price number, headline)

Replace with: flat brand-color hero type (solid brand color, high contrast against the white base). The STYLE BLOCK gold is used as a flat solid color on kicker labels and divider rules only. Gradients are permitted in the photographic/atmospheric layer (a soft scrim gradient behind type is allowed; the scrim is on the image, not the text itself).

**The QC enforcement of this ban is AF-GRAD (qc-specialist-presentations-sops.md).** Any gradient or glow detected on a type region via the gradient/glow detector is a hard auto-fail. The producing ban here is the write-time guard; AF-GRAD is the read-time guard.

---

## 3. INTEGRATION WITH SOP-DESIGN-04 AND SOP-IMG-01

- SOP-DESIGN-04-LOGO-CONSISTENCY.md describes the logo-consistency goal. Where it mentions a composite after two failed image-to-image attempts, Rule A above governs what actually exists: escalate to the Director, who may supply a local logo file (mechanism 2).
- SOP-IMG-01-KIE-CALL-MECHANICS.md check 9 (logo identity) is unchanged. AF-P15 (write time) requires the prompt to carry the directive of the logo mechanism in use. Rule A is the authority because `build_deck.py` sends the prompt verbatim and never edits it for a logo: on the canonical command (mechanism 2) the prompt must NOT draw, describe or name any logo, declares no reference image, keeps the top-right corner free of type and imagery, and carries the negative twin "Do not draw, invent, redesign or place any logo, monogram, icon or brand mark anywhere on the slide; the real logo is added after generation" (otherwise the model draws a mark and `assemble_pptx` places a second one on top). In URL image-to-image mode (mechanism 1) the prompt declares image-to-image with LOGO_URL as the first reference and carries "place, do not redraw, recolor, or restyle it" and "do not invent or redesign any mark".
- The AF-LOGO check in the QC gate reads the rendered slide (and, for mechanism 2, the assembled slide). The SSIM threshold (>= 0.97 on the logo region against LOGO_URL or the local logo file) is the read-time enforcement.

---

## 4. OUTPUTS PRODUCED

- Mechanism 1 (URL logo, not reachable through the canonical command today): nothing beyond the normal renders; the logo is part of each rendered PNG.
- Mechanism 2 (local logo file): the logo picture shape on every slide of the assembled `.pptx`; `working/renders/slide-NN.png` is left exactly as KIE.ai returned it.
- (NO `pptx_text_overlays.json` and NO `logo_composite_log.json`. The native-text overlay path is eliminated, Decision 5C.)
