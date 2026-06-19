# SOPs Mirror -- Typography QC Specialist

**Source:** presentations/qc-specialist-typography-presentations.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md. Independence doctrine: generalized AF-QC-INDEPENDENCE.

### SOP 9.1 — Grade the design system + independent provenance

**When to run:** Phase P-TYPO-QC, after the Typography Architect locks `working/typography/design_system.json` and before prompt authoring.

**Steps:**

1. Read `working/typography/design_system.json` and the design brief.
2. Grade against the WRITTEN RUBRIC: (a) a real weight ladder exists; (b) each slide maps to one of several named archetypes; (c) NO single archetype covers more than 60% of slides (`ARCHETYPE_DOMINANCE_CEILING`) — over that is template-sameness (AF-CREATIVITY); (d) no two consecutive slides share an archetype (SOP-DESIGN-03); (e) the price-typography rule is set for price slides; (f) the type-scale stays within 4–5 steps, no platform-default family. Score each 1–10.
3. Compute the average (pass threshold 8.5). Any triggered autofail (including AF-CREATIVITY) forces FAIL.
4. Write `working/qc/typography_qc_report.json`: `gate: "Phase Typography-QC"`, `average`, `triggered_autofails: []`, `pass: true|false`, and a `qc_independence` block `{graded_by: "qc-specialist-typography-presentations", independent: true, builder: "typography-architect", self_graded: false}`.
5. NEVER name the Architect/self as `graded_by` — a self-graded report is refused (AF-TYPOGRAPHY-QC).
