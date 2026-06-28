# SOPs Mirror -- Prompt QC Specialist

**Source:** presentations/qc-specialist-prompt-presentations.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md. Independence doctrine: generalized AF-QC-INDEPENDENCE.

### SOP 9.1 — Grade prompts and stamp independent provenance

**When to run:** Phase P-PROMPT-QC, after the Prompt Author finishes and before render.

**Steps:**

1. Read every `working/prompts/slide-NN.txt`.
2. Grade each against the WRITTEN RUBRIC: (a) >= 9,000 chars (`PROMPT_CHAR_FLOOR`), (b) ARCHETYPE on line 1, (c) all 15 structural elements present, (d) a dedicated NEGATIVE BLOCK with >= 3 "Do not …" imperatives, (e) a spelling-lock of every on-slide word, (f) no hardcoded demographic-default split (AF-R3). Score each criterion 1–10.
2a. **Run the INTELLIGENCE-ENGINE prompt-side mechanical gate (the perceptual engines' gateable half).** Execute `python3 scripts/intelligence_engines_check.py working --phase prompt`. This asserts, on every people/scene prompt, the four required token classes and triggers a deck/slide auto-fail on any miss: **AF-FACE-PROMPT-MISSING** (an explicit Expression-Vocabulary-Table term, never a bare "smiling"), **AF-WORLD-SCALE** (a stated setting AND a believability/scale justification string), **AF-LIGHT-PROMPT-MISSING** (a key/fill/rim direction AND a rim/hair separation-light token), **AF-HAIR-INAUTHENTIC** (an age-appropriate hairstyle token from `working/brand/hairstyle_catalog.json`). Exit 4 = one or more triggered; record each in `triggered_autofails`. The vision VERDICT halves (AF-FACE-MOOD, world-grounding, AF-LIGHT-SKINTONE, plastic-hair) are NOT graded here — they are logged to `vision_qc_log.json` and graded at Image-QC. Source: SOP-SLIDE-00 §8b; producing doctrine slide-image-creator-sops.md SOP 9.3b + brand-steward-sops.md SOP 9.2b.
3. Compute the average. The pass threshold is 8.5. Any triggered autofail forces FAIL regardless of average.
4. Write `working/qc/prompt_qc_report.json` with: `gate: "Phase Prompt-QC"`, `average`, `triggered_autofails: []`, `pass: true|false`, and a `qc_independence` block: `{graded_by: "qc-specialist-prompt-presentations", independent: true, builder: "prompt-author-presentations", self_graded: false}`.
5. NEVER set `graded_by` to the builder/author/self. A self-graded report is refused (AF-PROMPT-QC via the generalized independence check).
