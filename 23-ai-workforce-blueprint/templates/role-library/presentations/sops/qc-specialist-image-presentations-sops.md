# SOPs Mirror -- Image QC Specialist

**Source:** presentations/qc-specialist-image-presentations.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md. Independence doctrine: generalized AF-QC-INDEPENDENCE.

### SOP 9.1 — Multimodal grade of rendered slides + independent provenance

**When to run:** Phase P-IMAGE-QC, after `build_deck.py` renders the slides.

**MANDATORY VISION + FULL SCOPE (AF-IMAGE-QC-VISION):** A real multimodal vision read of EVERY slide PNG is required, with a non-null `vision_api_response` record per slide in `working/qc/vision_qc_log.json`. NO slide may be excluded from scope — cover, section dividers, and pure-typography / hook slides are all graded with the full auto-fail battery. A pixel-blind report, a self-typed score, or any scope exclusion is REFUSED. This is the exact failure that let the bad deck pass at 8.66.

**Steps:**

1. Open each rendered slide PNG with a real vision pass.
2. Check ALL auto-fail conditions FIRST (before scoring). Any triggered auto-fail forces FAIL on that slide:
   - **AF-LOCAL-CANVAS** (cream-template): a flat cream / typography card with no photographic or designed visual subject (the local-Pillow `#FFFBF1` signature, type dropped on a blank surface). Pure-typography slides are kie.ai bakes, not local cards.
   - **AF-OVERLAY-DELIVERED** (words-overlaid / double-print): native PowerPoint text stamped over the image, or the same headline appearing both baked into the image and reprinted as a native run on top. Only baked words + the off-slide notes pane are legitimate.
   - **AF-UNDER-BYTE**: slide PNG below the kie-bake floor of 51,200 bytes (`PLACEHOLDER_MIN_BYTES`) — hard auto-fail here, never deferred.
   - **AF-CANONICAL-RENDER-BYPASS**: pixels not traceable to a canonical `build_deck.py` / `run_signature_deck.py` kie.ai job (no real kie `taskId` / recordInfo provenance).
   - **AF-IMAGE-QC-VISION**: no real per-PNG vision read for the slide, or the slide was excluded from scope.
   - Plus the AF-I battery (AF-I1 garbled text … AF-I10 hook footer) from the role file.
3. Grade each slide that clears the auto-fail gate against the WRITTEN RUBRIC: (a) copy-vs-pixel parity — every word in `slides_copy.md` appears correctly spelled on the render; (b) text is BAKED into the image, not overlaid/composited (no flat dark slabs, no double-print); (c) asset contrast passes (no invisible/vanishing asset); (d) no bracket/placeholder token on the render; (e) the slide is a real KIE bake (above the 51,200-byte placeholder floor), not a native render or a local cream card. Score each 1–10.

**FORBIDDEN RUBRIC CRITERIA (removed — never reintroduce):** no `typography_overlay_readiness` criterion and no "overlay the canonical headlines" / "apply headlines in post" / "the typography system renders the slide" recommendation. Words are baked by kie.ai inside the single image; there is no post-production text layer to be "ready" for. A report scoring overlay-readiness is itself a failed report.
4. **Grade the INTELLIGENCE-ENGINE vision VERDICT half (the perceptual call the prompt-token gate cannot make).** With a real vision pass, on every people/scene slide grade and LOG to `working/qc/vision_qc_log.json` (one record per slide, with a non-null `vision_api_response`): **AF-FACE-MOOD** — the face reads the slide's emotion/words (a smile on a pain slide fails); **world-grounding** (AF-WORD-IMAGE-MISMATCH) — would this exact person be in this exact room; **AF-LIGHT-SKINTONE** — the subject is lit for their skin tone (no deep-skin silhouette / no flat-white "Casper" / a rim or hair light is present); **AF-HAIR-INAUTHENTIC** (verdict half) — the hair is not the melted "AI plastic hair" failure. These are the verdict twins of the prompt-side mechanical codes Prompt-QC already enforced (AF-FACE-PROMPT-MISSING / AF-WORLD-SCALE / AF-LIGHT-PROMPT-MISSING / AF-HAIR-INAUTHENTIC). The vision log being non-empty with per-slide records is itself required by AF-NO-VISION-QC (and AF-IMAGE-QC-VISION). Source: SOP-SLIDE-00 §8b; SOP-ENGINE-00 perceptual-engine mechanical-half doctrine.
5. Compute the average (pass threshold 8.5). Any triggered autofail forces FAIL.
6. Write `working/qc/image_qc_report.json`: `gate: "Phase Image-QC"`, `average`, `triggered_autofails: []`, `pass: true|false`, and a `qc_independence` block `{graded_by: "qc-specialist-image-presentations", independent: true, builder: "slide-image-creator", self_graded: false}`.
7. NEVER name the renderer/self as `graded_by` — a self-graded report is refused (AF-IMAGE-QC).
