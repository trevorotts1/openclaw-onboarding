# SOPs Mirror -- Fish Audio / Expression Specialist

**Source:** presentations/fish-audio-expression-specialist.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Voice authority: 30-fish-audio-api-reference/.

### SOP 9.1 -- Tag the Script for the Target Tier

**Purpose:** Mark the clean script with expression tags so the demo reads with emphasis and emotion, using the correct syntax for the tier that will render it.

**The hard rule:** Add tags ONLY; never change a word of the script. Use the target tier's syntax: Fish S2 = [bracket] open-domain tags; Fish S1 = (parenthesis) fixed-emotion tags; ElevenLabs v3 = inline audio-tag cues; ElevenLabs v2 and local-no-markup = no inline tags (delivery is driven by voice settings or left plain, with guidance handed to ROLE-20). Obey the SOP tag-discipline rules: a tag affects everything after it until the next tag; pair a physical/vocal tag with at most one emotion tag; NEVER stack two emotion tags; maximum 2 tags per line unless a specific performance reason; every tag is followed by text to speak.

**Inputs:** speech.md, slides_copy.md (LADDER, HOOK_REFRAIN), intake.json TONE, the target tier.

**Steps:**
1. Set the voice posture early: the SOP says S2 uses earlier context to improve later expressiveness, so the opening lines establish the register (for example [warm, credible] for a trusted-coach TONE). Tag the first few lines deliberately.
2. Walk the script. For each beat, decide the delivery and add the minimal tag(s):
   - HOOK refrains: emphasize without rewording, for example [deliberate and measured] before the hook line so it lands as a refrain. Keep the words exactly verbatim.
   - DROP and FINAL beats: add the deliberate pause the doctrine requires, for example end the line then [long pause] (S2) so the number breathes; on the FINAL price use [voice lifts] then a pause.
   - PAIN slides: an emotion tag that makes the listener feel the weight, for example [empathetic, unhurried] or [voice drops slightly].
   - STORY slides: [storytelling tone], with a mid-sentence shift at the turn, for example [voice lifts, surprised].
   - CTA/close: [confident], landing the action; do not over-perform.
3. Use mid-sentence tag shifts where a real human would shift delivery (the SOP calls this a core technique), but stay within 2 tags per line.
4. For Fish, keep paralinguistic reactions sparse (about 1 to 2 per segment) so they read natural, not theatrical.
5. Write the tagged script to working/presenter-speech/speech_tagged.md, preserving the per-slide structure and the (PAUSE) cues from ROLE-20 (convert them to the tier's pause tag).

**Enforcement check (what auto-fails):**
- Any word changed from the clean script = FAIL.
- The hook reworded or its emphasis tag inserted INSIDE the hook words breaking them = FAIL.
- Two emotion tags stacked on one line = FAIL.
- More than 2 tags on a line with no performance justification = FAIL.
- A tag with no text following it = FAIL.
- Fish bracket tags left in a script targeted at ElevenLabs v2 or a no-markup local tool = FAIL (they would be spoken aloud).

**PASS example (Fish S2, reference failure case drop):** `Because you showed up live, it is twenty-five hundred. [long pause]` and `[deliberate and measured] There is a difference between parenting by control and parenting through clarity.`

**FAIL example:** `[excited] [happy] [warm] And here is the price!` (three stacked emotion tags) or rewording the hook to fit a tag.

**Outputs:** working/presenter-speech/speech_tagged.md.

**Hand to:** SOP 9.2 (audit), then ROLE-20 for render.

**Failure mode:** If the TONE is unclear, default to a credible, warm posture and flag the assumption; do not guess a theatrical register that misrepresents the owner.

---

### SOP 9.2 -- Word-Fidelity and Tag-Discipline Audit

**Purpose:** Prove the tagging changed zero words and obeyed every tag-discipline rule before the render consumes it.

**The hard rule:** Strip all tags from speech_tagged.md and the result MUST equal speech.md word for word. Every tag-discipline rule from SOP 9.1 holds.

**Inputs:** speech.md, speech_tagged.md.

**Steps:**
1. Programmatically remove the tags (everything in [brackets] or (parentheses), plus the converted pause cues) from speech_tagged.md and compare to speech.md. Any word-level difference is a defect; fix it.
2. Scan for stacked emotion tags, lines over 2 tags, and tags with no following text; fix any.
3. Confirm the hook refrains are present verbatim and intact.
4. Record the audit result (pass/fail and any fixes) in a comment header of speech_tagged.md.

**Enforcement check (what auto-fails):**
- Stripped tagged script does not equal the clean script = FAIL.
- Any tag-discipline violation remaining = FAIL.

**Outputs:** the audited speech_tagged.md.

**Hand to:** ROLE-20 (render).

**Failure mode:** If a word difference is found, it means a word was accidentally altered during tagging; restore the clean word, never accept the altered version.

---

### SOP 9.3 -- Cross-Tier Translation Guidance

**Purpose:** Make sure expression survives a fallback. If ROLE-20 cannot use Fish and falls to ElevenLabs or the local tool, the expression intent must translate, not vanish.

**The hard rule:** Provide ROLE-20 a translation note: how the Fish-style intent maps to ElevenLabs v3 (inline audio tags), to ElevenLabs v2 (voice settings: stability, similarity, style, plus tag stripping), and to a no-markup local tool (plain text, accept flat). The note names which beats matter most so even a flat tier keeps the pauses via ffmpeg padding.

**Inputs:** speech_tagged.md, the tier behaviors from the API references.

**Steps:**
1. For ElevenLabs v3: note that v3 supports inline audio-tag style direction, so the bracketed intent can largely carry over (verify the account has v3).
2. For ElevenLabs v2: note that v2 is driven by voice settings, not inline tags; provide a suggested stability/style profile for the TONE, and instruct ROLE-20 to STRIP the inline tags (otherwise v2 speaks them as words). List the high-priority pause points so ROLE-20 can pad them with ffmpeg silence.
3. For the local tool (no markup): note that delivery will be flat; the must-keep elements are the DROP and FINAL pauses, which ROLE-20 adds via ffmpeg silence padding at the marked points.
4. Write the guidance into the header of speech_tagged.md or a sibling note working/presenter-speech/tier_translation.md.

**Enforcement check (what auto-fails):**
- No translation guidance provided when a fallback tier is possible = FAIL.
- Guidance that leaves inline tags in for a v2/local render = FAIL.

**Outputs:** tier_translation.md (or header block).

**Hand to:** ROLE-20.

**Failure mode:** If only the local tool exists, still provide the pause-point list so the demo at least breathes at the drops.

---
