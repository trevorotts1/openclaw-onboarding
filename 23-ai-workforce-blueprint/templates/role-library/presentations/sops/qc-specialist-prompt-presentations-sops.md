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
2. Grade each against the WRITTEN RUBRIC: (a) >= 5,000 chars (`PROMPT_CHAR_FLOOR`), (b) ARCHETYPE on line 1, (c) all 15 structural elements present, (d) a dedicated NEGATIVE BLOCK with >= 3 "Do not …" imperatives, (e) a spelling-lock of every on-slide word, (f) no hardcoded demographic-default split (AF-R3). Score each criterion 1–10.
3. Compute the average. The pass threshold is 8.5. Any triggered autofail forces FAIL regardless of average.
4. Write `working/qc/prompt_qc_report.json` with: `gate: "Phase Prompt-QC"`, `average`, `triggered_autofails: []`, `pass: true|false`, and a `qc_independence` block: `{graded_by: "qc-specialist-prompt-presentations", independent: true, builder: "prompt-author-presentations", self_graded: false}`.
5. NEVER set `graded_by` to the builder/author/self. A self-graded report is refused (AF-PROMPT-QC via the generalized independence check).
