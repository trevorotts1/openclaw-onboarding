# SOPs Mirror -- Image-Grounding Steward ("The Witness")

**Source:** departments/Presentations/roles/image-grounding-steward.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.
**Source classification:** custom (Trevor BlackCEO; the ground-everything no-fabrication imagery doctrine is a BlackCEO standard the floor presentations library does not carry).
**Department:** Presentations -- BlackCEO
**Version:** 1.0
**Last updated:** 2026-06-14

---

## 9. Standard Operating Procedures (Numbered)

---

### SOP 9.1 -- Grounded-Content Capture

**SOP ID:** SOP-PRES-CUSTOM-09 (BlackCEO)
**Library pointer:** SOP-PITCH-02-VALUE-STACK-AND-PROMISES (proof) + SOP-SLIDE-00 AF ruleset + devils-advocate-presentations SOP 9.1 (PRESENTATION-MASTER-DOCTRINE.md §4) (no fabrication, proof inventory); World Engine (SOP-ENGINE-00-INTELLIGENCE-ENGINES-FRAMEWORK (PRESENTATION-MASTER-DOCTRINE.md §4) element 11)
**When to run:** When a deck arrives from intake and before image prompts are scored.
**Frequency:** Per deck.
**Inputs:** The client's material (book, message, offer, methodology), the Deep Research Specialist's grounded findings, the narrative architecture from the Signature Presentation Architect.

**Steps:**
1. Assemble the grounded-content reference: the concrete moments, methods, proof points, and offer specifics from the client's own material that the imagery should depict.
2. Confirm the brief carries a grounded-content variable (book, message, offer, methodology). If the field is empty, request it through the Director; do not invent client content to populate it.
3. For each key beat in the narrative architecture, identify the specific client moment the imagery should make visible (for example a particular method step, a particular proof outcome, a particular pain the audience feels).
4. Pull the Deep Research Specialist's grounded findings into the image-relevant set so research flows into the imagery, not only the copy.
5. Record the grounded-content reference in the project record as the baseline for prompt grounding scoring.

**Outputs:** A grounded-content reference mapping each key beat to the specific client moment its imagery should depict.
**Hand to:** Slide Image Creator (writes prompts against the grounded-content reference); used by SOP 9.2 for scoring.
**Failure mode:** If the client supplies no concrete content for a beat, do not fabricate a moment. Mark the beat `[CONTENT PENDING]` and request it through the Director; never ground imagery in invented content.

---

### SOP 9.2 -- Prompt Grounding Score (Specific, Not Generic)

**SOP ID:** SOP-PRES-CUSTOM-10 (BlackCEO)
**Library pointer:** `universal-sops/CLIENT-WEBINAR-DECK-SOP.md` Phase 3 prompt QC; World Engine
**When to run:** After the Slide Image Creator drafts prompts and before generation.
**Frequency:** Per deck, per prompt batch.
**Inputs:** The drafted image prompts, the grounded-content reference, the narrative architecture.

**Steps:**
1. For each people-or-scene-bearing prompt, read the scene it describes.
2. Score grounding: does the prompt depict a CONCRETE moment from the client's specific content (a method step, a proof outcome, a recognizable audience moment), or a GENERIC on-brand scene (a businessperson at a desk, a happy family stock pose) that could belong to any client?
3. Confirm the World Engine setting is not merely plausible but client-specific: an affluent family at a sunlit kitchen table is plausible, but the grounding score asks whether it depicts THIS client's actual method or audience moment.
4. Flag any prompt that scores generic (not grounded in the client's content) as a blocking fail at the prompt stage. Route it back to the Slide Image Creator with the specific client moment it should depict instead.
5. Confirm the grounded research findings made it into the relevant prompts.
6. Re-score returned prompts until every people-or-scene-bearing prompt is grounded in the client's specific content.

**Outputs:** A prompt grounding record: pass, or a flagged set of generic prompts with the specific client moment each should depict.
**Hand to:** Slide Image Creator (revise ungrounded prompts); QC Specialist (the grounding score feeds the grounding dimension of prompt QC).
**Failure mode:** If a prompt cannot be grounded because the client supplied no content for that beat, do not pass it generic. Hold the beat `[CONTENT PENDING]` and escalate to the Director to obtain the content.

---

### SOP 9.3 -- Pain-Visibility Review (Make the Pain Felt)

**SOP ID:** SOP-PRES-CUSTOM-11 (BlackCEO)
**Library pointer:** Governing intelligence GP-16; SOP-IMG-01-KIE-CALL-MECHANICS + prompt-author-presentations SOP + brand-steward SOP 9.3 (PRESENTATION-MASTER-DOCTRINE.md §4) exemplar (emotional job of the image)
**When to run:** On pain-point slides, during prompt scoring and again on the generated image.
**Frequency:** Per deck, for every pain-point slide.
**Inputs:** The pain-point slide prompts, the generated pain-point images, the SEE-journey map from the Signature Presentation Architect.

**Steps:**
1. Identify the pain-point slides from the narrative architecture and the SEE-journey map.
2. Confirm the imagery makes the pain VISIBLE: the viewer should see it and recognize their own situation ("that is exactly how I feel"), not see an abstract or decorative scene.
3. Confirm the image is emotionally-driven: it carries the emotional job of the slide (the loss, the fear, the longing) so the viewer feels spoken to at the moment the slide lands.
4. Confirm the pain depicted is the client's specific audience's pain (grounded), not a generic sad-person image.
5. Flag any pain-point image that is abstract, decorative, or generic and route it back with the specific recognizable pain it should depict.

**Outputs:** A pain-visibility review record: pass, or flagged pain-point slides with corrective instructions.
**Hand to:** Slide Image Creator (regenerate flagged pain-point slides); Signature Presentation Architect (confirm the SEE journey lands).
**Failure mode:** If a pain-point image cannot be made recognizable from the client's content, escalate to the Signature Presentation Architect and the Director; an abstract pain image breaks the emotional connection and should not ship.

---

### SOP 9.4 -- Final-Deck Grounding Pass

**SOP ID:** SOP-PRES-CUSTOM-12 (BlackCEO)
**Library pointer:** MASTER-QC-AUTOFAIL-RULESET (SOP-SLIDE-00) + qc-specialist-presentations SOP 9.x (PRESENTATION-MASTER-DOCTRINE.md §4) (final deck rendered to PDF to PNG); qc-specialist SOP 9.5
**When to run:** On the assembled, rendered deck, before delivery.
**Frequency:** Per deck, once, at final QC.
**Inputs:** The final deck rendered to PNG pages, the grounded-content reference, the prompt grounding record.

**Steps:**
1. On the rendered final-deck pages, review the imagery as a whole.
2. Confirm the deck tells the client's SPECIFIC story: the imagery depicts the client's method, audience, proof, and offer, not a generic on-brand sequence.
3. Confirm no slide silently substituted a generic scene during generation or assembly that passed prompt scoring but rendered generic.
4. Confirm the pain-point slides on the assembled deck still make the pain visible and recognizable.
5. Record the final-deck grounding result as a blocking pass-artifact (`grounding_final_pass.json`) so delivery cannot proceed without it.

**Outputs:** A blocking final-deck grounding artifact: pass, or fail with the generic slides named.
**Hand to:** Director of Presentations and Delivery Concierge (a passing grounding pass is required before delivery); Slide Image Creator (if a fail requires regeneration).
**Failure mode:** If the final deck fails the grounding pass at delivery time, do not ship. Route the generic slides back for regeneration with the specific client moment they should depict, then re-render.

---

*End of SOPs mirror for the Image-Grounding Steward. Custom Presentations SOPs SOP-PRES-CUSTOM-09 through 12 for BlackCEO. This file is regenerated from the role file and is never edited directly.*
