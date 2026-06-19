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
3. Compute the average (pass threshold 8.5). Any triggered autofail forces FAIL.
4. Write `working/qc/image_qc_report.json`: `gate: "Phase Image-QC"`, `average`, `triggered_autofails: []`, `pass: true|false`, and a `qc_independence` block `{graded_by: "qc-specialist-image-presentations", independent: true, builder: "slide-image-creator", self_graded: false}`.
5. NEVER name the renderer/self as `graded_by` — a self-graded report is refused (AF-IMAGE-QC).
