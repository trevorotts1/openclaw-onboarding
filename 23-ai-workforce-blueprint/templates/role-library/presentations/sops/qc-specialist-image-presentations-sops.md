# SOPs Mirror -- Image QC Specialist

**Source:** presentations/qc-specialist-image-presentations.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md. Independence doctrine: generalized AF-QC-INDEPENDENCE.

### SOP 9.1 — Multimodal grade of rendered slides + independent provenance

**When to run:** Phase P-IMAGE-QC, after `build_deck.py` renders the slides.

**Steps:**

1. Open each rendered slide PNG with a real vision pass.
2. Grade each against the WRITTEN RUBRIC: (a) copy-vs-pixel parity — every word in `slides_copy.md` appears correctly spelled on the render; (b) text is BAKED into the image, not overlaid/composited (no flat dark slabs); (c) asset contrast passes (no invisible/vanishing asset); (d) no bracket/placeholder token on the render; (e) the slide is a real KIE bake (above the placeholder floor), not a native render. Score each 1–10.
2a. **Grade the INTELLIGENCE-ENGINE vision VERDICT half (the perceptual call the prompt-token gate cannot make).** With a real vision pass, on every people/scene slide grade and LOG to `working/qc/vision_qc_log.json` (one record per slide, with a non-null `vision_api_response`): **AF-FACE-MOOD** — the face reads the slide's emotion/words (a smile on a pain slide fails); **world-grounding** (AF-WORD-IMAGE-MISMATCH) — would this exact person be in this exact room; **AF-LIGHT-SKINTONE** — the subject is lit for their skin tone (no deep-skin silhouette / no flat-white "Casper" / a rim or hair light is present); **AF-HAIR-INAUTHENTIC** (verdict half) — the hair is not the melted "AI plastic hair" failure. These are the verdict twins of the prompt-side mechanical codes Prompt-QC already enforced (AF-FACE-PROMPT-MISSING / AF-WORLD-SCALE / AF-LIGHT-PROMPT-MISSING / AF-HAIR-INAUTHENTIC). The vision log being non-empty with per-slide records is itself required by AF-NO-VISION-QC. Source: SOP-SLIDE-00 §8b; SOP-ENGINE-00 perceptual-engine mechanical-half doctrine.
3. Compute the average (pass threshold 8.5). Any triggered autofail forces FAIL.
4. Write `working/qc/image_qc_report.json`: `gate: "Phase Image-QC"`, `average`, `triggered_autofails: []`, `pass: true|false`, and a `qc_independence` block `{graded_by: "qc-specialist-image-presentations", independent: true, builder: "slide-image-creator", self_graded: false}`.
5. NEVER name the renderer/self as `graded_by` — a self-graded report is refused (AF-IMAGE-QC).
