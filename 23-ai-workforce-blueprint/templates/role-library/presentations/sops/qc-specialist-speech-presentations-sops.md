# SOPs Mirror -- Speech QC Specialist

**Source:** presentations/qc-specialist-speech-presentations.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md. Independence doctrine: generalized AF-QC-INDEPENDENCE.

### AUTO-FAIL RULE: an auto-fail condition forces FAIL for the affected speech section regardless of any average. Auto-fails are checked FIRST, before scoring.

### SOP 9.1 -- Coverage Audit (Every Slide Has a Talk Track)

**When to run:** Phase P-SPEECH-QC, after the Presenters Speech Writer hands off the completed speech. This is the first check.

**Frequency:** Once per speech per QC cycle. Re-runs after Presenters Speech Writer remediation.

**Inputs:**
- `working/deliverables/PRESENTERS-SPEECH.md` (the speech manuscript -- the P9-SPEECH artifact)
- `working/copy/slides_copy.md` (the assembled deck copy, one entry per slide)
- `working/copy/intake.json` (total slide count, `target_talk_minutes`)

**Steps:**

1. Parse the speech manuscript into per-slide or per-section blocks. Most speech formats include a slide number or slide title as a section header.
2. Build a coverage map: for each slide in `slides_copy.md`, verify a corresponding talk-track block exists in the speech. The talk track must be substantive (more than a single sentence for any content slide -- a slide that communicates a significant idea should have 2-5 sentences of narration).
3. Check each talk-track block against the slide's ONE BIG IDEA: the talk track must reinforce the slide's singular point, not contradict it, not introduce a second idea, and not merely describe the image ("As you can see in this picture...").
4. Verify the persuasion-arc beat sequence is spoken in order:
   - HOOK beat spoken at the hook slides (per `hook_package.json`)
   - STAKES / PAIN beats spoken at the pain slides
   - PROMISE beat spoken before the offer
   - PROOF beats spoken at the proof slides (Wall of Wins, testimonials)
   - OFFER / DROP beats spoken at each price-ladder slide (per `price_ladder.json`)
   - RE-PITCH beat spoken after the FINAL price
5. Auto-fail conditions for the coverage audit:
   - **AF-SPEECH-COVERAGE-1**: Any content slide (not a pure transition or visual-rest slide) has no talk-track block in the speech. A missing talk track for a content slide is a hard fail -- the audience hears silence or an off-topic line while the slide is displayed.
   - **AF-SPEECH-COVERAGE-2**: The persuasion-arc beats are out of sequence (e.g., the OFFER beat appears before the PROOF beats). The sequence is not negotiable per the master SOP.
   - **AF-SPEECH-COVERAGE-3**: The hook refrain is NOT spoken at a scheduled hook slide (per `hook_package.json`). The hook must be spoken at its scheduled beat -- it cannot be silently shown without the speaker delivering the line.
6. For slides that pass the coverage check, score the talk-track quality (1-10) per slide: does the narration reinforce the slide's one big idea with the owner's authentic voice? A generic coaching platitude that could belong to any deck scores below 7.

**Outputs:**
- Per-slide coverage map (covered / uncovered / thin)
- Persuasion-arc sequence check result (PASS / FAIL with specific out-of-order beats)
- Any triggered auto-fail codes (AF-SPEECH-COVERAGE-1, -2, -3)
- Per-slide talk-track quality scores (1-10)

**Hand to:** SOP 9.2 (timing and pacing check).

**Failure mode:** If the speech manuscript uses a format that does not label slides by number or title, attempt to map talk-track blocks to slides by matching their content to the slide's headline. If mapping is ambiguous for more than 3 slides, return the speech to the Presenters Speech Writer with a request to add slide-number labels before QC continues.

---

### SOP 9.2 -- Timing and Pacing Check

**When to run:** After SOP 9.1. Covers the full speech as a whole-document check.

**Frequency:** Once per speech per QC cycle.

**Inputs:**
- `working/deliverables/PRESENTERS-SPEECH.md` (the speech manuscript -- the P9-SPEECH artifact)
- `working/copy/intake.json` (`target_talk_minutes` -- the owner's stated presentation length goal)

**Steps:**

1. Count the total word count of the speech manuscript (excluding section headers, stage directions, and expression tags -- count only the words the owner will SPEAK).
2. Compute the estimated runtime at both ends of the target pacing band:
   - At 120 wpm: `word_count / 120 = runtime_minutes_at_slow`
   - At 140 wpm: `word_count / 140 = runtime_minutes_at_fast`
3. Compare the computed runtime range against `target_talk_minutes` from intake.json (with a 10% tolerance on each end):
   - If `runtime_minutes_at_slow` > `target_talk_minutes * 1.10`: the speech is too long at the slowest acceptable pacing. The owner will run over by more than 10% if they speak at the bottom of the natural range. AF-SPEECH-PACING-LONG.
   - If `runtime_minutes_at_fast` < `target_talk_minutes * 0.90`: the speech is too short even at the fastest acceptable pacing. The owner will run short by more than 10% if they speak briskly. AF-SPEECH-PACING-SHORT.
   - If the runtime range brackets `target_talk_minutes` (it falls within the range): PASS.
4. Perform a per-section pacing check: identify sections where the talk-track density is significantly uneven (a 10-slide section with 200 words vs a 10-slide section with 800 words). Uneven pacing causes the owner to rush through some sections and stall on others. Score pacing evenness 1-10.
5. Verify natural pause points exist: the speech should have explicit pause instructions (a line break, a breath marker, or an expression tag like `[pause]`) at the hook refrain slides and at each price drop. A hook beat with no pause marker is a scored defect (the hook must breathe).

**Outputs:**
- Total word count and computed runtime range (at 120 wpm and 140 wpm)
- Pacing verdict: PASS / AF-SPEECH-PACING-LONG / AF-SPEECH-PACING-SHORT with specific over/under amount
- Per-section pacing evenness score (1-10)
- Pause marker check result (hook and drop slides have pause markers: PASS / FAIL with specific missing slides)

**Hand to:** SOP 9.3 (claim-verification gate).

**Failure mode:** If `target_talk_minutes` is absent from intake.json, use the standard webinar length of 60 minutes as the default target. Flag the absent value to the Director and request it be added to intake.json for future runs.

---

### SOP 9.3 -- Claim-Verification Gate

**When to run:** After SOP 9.2. Focuses on every factual claim, statistic, and dollar figure spoken in the speech.

**Frequency:** Once per speech per QC cycle.

**Inputs:**
- `working/deliverables/PRESENTERS-SPEECH.md` (the speech manuscript -- the P9-SPEECH artifact)
- `working/research/proof_audit.txt` (verified facts and statistics from the research phase)
- `working/copy/intake.json` (the owner's stated facts and personal results)
- `working/copy/slides_copy.md` (the on-slide copy, where factual claims originate)

**Steps:**

1. Extract every factual claim, statistic, dollar figure, percentage, and attributed quote from the speech manuscript. Flag any claim that includes a number, a source reference, a percentage, or an attributed statement.
2. For each extracted claim, trace it to one of these acceptable sources:
   - The owner's intake interview (`working/copy/intake.json` -- a fact the owner stated about their own results)
   - The research brief (`working/research/proof_audit.txt` -- a fact verified by the research phase)
   - The on-slide copy (`working/copy/slides_copy.md` -- a fact that already passed copy QC)
3. Any claim that cannot be traced to one of these three sources = AF-SPEECH-CLAIM (fabricated or unverified fact spoken aloud). This is a hard auto-fail -- the owner could state this claim to a live audience.
4. Check for cross-speech numeric consistency: if a dollar figure or percentage appears in multiple places in the speech (the stack total stated at the offer section and then again in the re-pitch), verify the numbers are identical. A numeric mismatch within the speech = AF-SPEECH-CLAIM-MISMATCH.
5. Verify no cross-slide numeric mismatch: the numbers spoken in the speech must match the numbers on the corresponding slides. A mismatch between the spoken price and the on-slide price = AF-SPEECH-CLAIM-MISMATCH.
6. Score claim fidelity overall 1-10 (all claims verified = 10; each unverified claim reduces the score by 2; any AF-SPEECH-CLAIM forces FAIL regardless of average).

**Outputs:**
- Claim inventory: every factual claim extracted, its source trace, and its verification status
- Any triggered auto-fail codes (AF-SPEECH-CLAIM, AF-SPEECH-CLAIM-MISMATCH)
- Claim fidelity score (1-10)

**Hand to:** SOP 9.4 (expression-tag and audience-voice QC).

**Failure mode:** If a claim in the speech references "recent studies show..." or "experts agree..." with no specific source traceable to the proof audit, that is AF-SPEECH-CLAIM. Return it to the Presenters Speech Writer with the instruction to either ground it to a specific verified source from `proof_audit.txt` or remove it.

---

### SOP 9.4 -- Expression-Tag and Audience-Voice QC

**When to run:** After SOP 9.3. This is the final pre-approval check.

**Frequency:** Once per speech per QC cycle.

**Inputs:**
- `working/deliverables/PRESENTERS-SPEECH.md` (the speech manuscript -- the P9-SPEECH artifact)
- `working/copy/slides_copy.md` (the on-slide copy for voice-register comparison)

**Steps:**

1. **Expression-tag sanity check:** The speech may carry Fish Audio expression tags (`[bracket]` free-form) or ElevenLabs inline tags (`[excited]`, `[whisper]`) if the Audio Demo is planned (WANT_AUDIO_DEMO = true in intake.json). Check for:
   - Tag syntax correctness: if Fish S2 format, all tags use `[bracket]` natural-language descriptions. If ElevenLabs v3 format, tags use the documented inline set. Mixed-format tags (parenthesis S1 tags in a S2 speech) = AF-SPEECH-TAG-SYNTAX.
   - Tag density: no more than 2 expression tags per line (the audio overcrowding rule). More than 2 tags per line = AF-SPEECH-TAG-DENSITY.
   - Tag semantic sanity: a `[sobbing]` tag on the price-drop line, or a `[whisper]` on the hook refrain, are semantic mismatches. Score semantic appropriateness 1-10.
   - If WANT_AUDIO_DEMO = false in intake.json: expression tags should be absent from the speech. Tags present in a non-audio-demo speech are extraneous markup that the owner would read aloud literally. = AF-SPEECH-TAG-PRESENT-WHEN-NOT-WANTED.
2. **Audience-facing voice check:** Verify the speech is written entirely in the owner's audience-facing voice -- the words the owner speaks TO the audience. Check for:
   - **AF-SPEECH-STAGEDIRECTION**: Stage-direction language leaking into the spoken text ("Now pause here and look at the audience," "This is where you click to the next slide," "Remember to smile"). Stage directions belong in the Presenter's Guide, not the speech. Any stage-direction sentence present as spoken text = auto-fail on that section.
   - **AF-SPEECH-PITCHDOCTRINE**: Internal pitch-doctrine language read aloud as spoken content ("The lower the price, the greater the value," "We're now entering the GRADUAL DROP sequence," "This is the Wall of Wins section"). Build-logic principles are NEVER spoken to the audience -- they are build tools.
   - **AF-SPEECH-IMAGENARATION**: The speech narrates what the slide image shows rather than delivering the slide's message ("As you can see in this image, there is a woman at a desk," "This picture shows a transformation"). The speech delivers the IDEA, not a description of the visual.
3. **Voice register consistency check:** The speech should maintain the owner's voice register throughout (established in the first 5 slides of narration). A section that drops into generic corporate language, motivational-speaker cliches, or a distinctly different register = a scored defect (voice register break, -1.5 per instance, no separate auto-fail unless it constitutes the majority of a section).
4. **Off-brand claim check:** Scan the speech for any unqualified guarantee, income promise, or legally sensitive claim (e.g., "You will make $X in your first month"). Any such claim = AF-SPEECH-CLAIM (escalate to the owner for explicit approval before the speech is used).
5. Score the overall audience-voice quality 1-10 across the full speech.

**Outputs:**
- Expression-tag audit result: tag syntax, tag density, tag semantic, and presence/absence check (PASS / FAIL with specific codes)
- Audience-voice check result: PASS or FAIL with specific section-level defect notes for each triggered code
- Voice register consistency score (1-10)
- Overall audience-voice quality score (1-10)
- Final `working/qc/speech_qc_report.json` after all 4 SOPs complete

**Hand to:** Director of Presentations on PASS (the audio chain is unblocked: P9-SPEECH-WEBINAR-INTRO at 8.54 synthesized the webinarized audio from the Fish-tagged script, and P9-DELIVER at 9 renders the client `PRESENTER-AUDIO.mp3`; P7-TELEPROMPTER at 8.95 builds the teleprompter from the same speech). Presenters Speech Writer on FAIL with the specific per-section defect report.

**Failure mode:** If WANT_AUDIO_DEMO is absent from intake.json, treat it as false (no expression tags expected). Flag the absence to the Director for intake.json hygiene.

---

### SOP 9.5 -- Grade the Presenter Speech and Independent Provenance (Condensed Whole-Speech Pass)

**When to run:** Phase P-SPEECH-QC, after the Presenters Speech Writer produces the speech and before delivery closeout. This is a single whole-speech pass layered over SOPs 9.1-9.4; it does not replace them.

**Steps:**

1. Read the presenter speech (`working/deliverables/PRESENTERS-SPEECH.md` or the working speech file).
2. Grade against the WRITTEN RUBRIC: (a) pacing lands in the verified 120–140 wpm band against `target_talk_minutes`; (b) on-slide sync — each spoken block maps to the slide it narrates; (c) persuasion-arc fidelity — hook / stakes / promise / proof / offer / re-pitch beats are spoken in order; (d) audience-facing voice — no internal pitch-doctrine or stage-direction read aloud. Score each 1–10.
2a. **Run the AF-SPEECH-HOOK-COUNT auto-fail (SOP-PITCH-06 1.8):** `python3 scripts/pitch_engines_check.py --run-dir <run_dir> --phase SPEECH-QC --json`. The check counts char-exact occurrences of `intake.json.hook` in `PRESENTERS-SPEECH.md` and asserts `5 <= count <= 20`. exit 4 = triggered (record `AF-SPEECH-HOOK-COUNT` in `triggered_autofails`); below 5 = under-sung, above 20 = wallpaper. A `defer` (speech absent) is not a fail. The hook is SUNG 5-20x — this is the SPOKEN floor; the slide-side visual ceiling (`AF-HOOK-1`, 3-4 dedicated slides) is a separate VISUAL rule and is unchanged.
3. Compute the average (pass threshold 8.5). Any triggered autofail forces FAIL.
4. Write `working/qc/speech_qc_report.json`: `gate: "Phase Speech-QC"`, `average`, `triggered_autofails: []`, `pass: true|false`, and a `qc_independence` block `{graded_by: "qc-specialist-speech-presentations", independent: true, builder: "presenters-speech-writer", self_graded: false}`.
5. NEVER name the Speech Writer/self as `graded_by` — a self-graded report is refused (AF-SPEECH-QC).

---
