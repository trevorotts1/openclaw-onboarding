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
2a. **Run the AF-SPEECH-HOOK-COUNT auto-fail (SOP-PITCH-06 1.8):** `python3 scripts/pitch_engines_check.py --run-dir <run_dir> --phase SPEECH-QC --json`. The check counts char-exact occurrences of `intake.json.hook` in `PRESENTERS-SPEECH.md` and asserts `5 <= count <= 20`. exit 4 = triggered (record `AF-SPEECH-HOOK-COUNT` in `triggered_autofails`); below 5 = under-sung, above 20 = wallpaper. A `defer` (speech absent) is not a fail. The hook is SUNG 5-20x — this is the SPOKEN floor; the slide-side visual ceiling (`AF-HOOK-1`, 3-4 dedicated slides) is a separate VISUAL rule and is unchanged.
3. Compute the average (pass threshold 8.5). Any triggered autofail forces FAIL.
4. Write `working/qc/speech_qc_report.json`: `gate: "Phase Speech-QC"`, `average`, `triggered_autofails: []`, `pass: true|false`, and a `qc_independence` block `{graded_by: "qc-specialist-speech-presentations", independent: true, builder: "presenters-speech-writer", self_graded: false}`.
5. NEVER name the Speech Writer/self as `graded_by` — a self-graded report is refused (AF-SPEECH-QC).
