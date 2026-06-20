# SOPs Mirror -- Speech QC Specialist

**Source:** presentations/qc-specialist-speech-presentations.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md. Independence doctrine: generalized AF-QC-INDEPENDENCE.

### SOP 9.1 — Grade the presenter speech + independent provenance

**When to run:** Phase P-SPEECH-QC, after the Presenters Speech Writer produces the speech and before delivery closeout.

**Steps:**

1. Read the presenter speech (`working/delivery/PRESENTERS-SPEECH.md` or the working speech file).
2. Grade against the WRITTEN RUBRIC: (a) pacing lands in the verified 120–140 wpm band against `target_talk_minutes`; (b) on-slide sync — each spoken block maps to the slide it narrates; (c) persuasion-arc fidelity — hook / stakes / promise / proof / offer / re-pitch beats are spoken in order; (d) audience-facing voice — no internal pitch-doctrine or stage-direction read aloud. Score each 1–10.
3. Compute the average (pass threshold 8.5). Any triggered autofail forces FAIL.
4. Write `working/qc/speech_qc_report.json`: `gate: "Phase Speech-QC"`, `average`, `triggered_autofails: []`, `pass: true|false`, and a `qc_independence` block `{graded_by: "qc-specialist-speech-presentations", independent: true, builder: "presenters-speech-writer", self_graded: false}`.
5. NEVER name the Speech Writer/self as `graded_by` — a self-graded report is refused (AF-SPEECH-QC).
