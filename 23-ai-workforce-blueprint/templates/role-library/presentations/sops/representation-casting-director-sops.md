# SOPs Mirror -- Per-Client Representation and Casting Director ("The Mirror")

**Source:** departments/Presentations/roles/representation-casting-director.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.
**Source classification:** custom (Trevor BlackCEO; the audience-as-mirror representation gate is a BlackCEO brand law the floor presentations library does not carry).
**Department:** Presentations -- BlackCEO
**Version:** 1.0
**Last updated:** 2026-06-14

---

## 9. Standard Operating Procedures (Numbered)

---

### SOP 9.1 -- Audience Capture Verification and Percentage Allocation

**SOP ID:** SOP-PRES-CUSTOM-05 (BlackCEO)
**Library pointer:** SOP-SIGPRES-01-EIGHT-QUESTIONS-ONE-BLOCK-AND-FRAME-SELECTION + deck-intake-questions.json (PRESENTATION-MASTER-DOCTRINE.md §4) Q9 (REPRESENTATION_MIX); pre-presentation audience-capture requirement
**When to run:** When a deck arrives from intake and before any people-bearing prompt is written.
**Frequency:** Per deck.
**Inputs:** intake.json, the plain-language audience-composition note (gender; race or ethnicity mix; age; defining traits).

**Steps:**
1. Confirm the intake captured the target audience the client is presenting to, including its composition: gender mix, race or ethnicity mix, age, and any defining trait. This is asked BEFORE any prompt is written.
2. If the audience composition is NOT captured, do not invent a default. Mark the deck NO-PEOPLE and notify the operator; people are not rendered until the mix is captured. This is a hard stop, not a judgment call.
3. Convert the captured composition into a per-group percentage allocation (the REPRESENTATION_MIX) so the deck-wide ratio is explicit and measurable.
4. Confirm the percentages sum to 100 and reflect the client's stated audience, not a generic assumption. If the plain-language note is ambiguous, return to the Director or Brainstorming Buddy for clarification; never resolve ambiguity by guessing.
5. Record the captured mix and the percentage allocation in the project record as the single source of truth for casting.

**Outputs:** A confirmed REPRESENTATION_MIX with percentages, or a deck flagged NO-PEOPLE with the operator notified.
**Hand to:** Slide Image Creator (for per-prompt assignment, SOP 9.2); Director of Presentations (for the gate record).
**Failure mode:** If the mix cannot be captured and the deck requires people, do not proceed with an invented ratio. Hold the deck NO-PEOPLE and escalate to the Director to obtain the audience composition from the client.

---

### SOP 9.2 -- Per-Prompt Representation Assignment

**SOP ID:** SOP-PRES-CUSTOM-06 (BlackCEO)
**Library pointer:** SOP-DESIGN-03-VARIABLE-LAYOUT-ANTI-TEMPLATE + brand-steward SOP (PRESENTATION-MASTER-DOCTRINE.md §4) (people-allocation rule); slide-image-creator Audience Engine
**When to run:** After audience capture is confirmed and before prompts are submitted for people-bearing slides.
**Frequency:** Per deck, before the prompt batch.
**Inputs:** The confirmed REPRESENTATION_MIX with percentages, the slide manifest listing which slides bear people.

**Steps:**
1. List the people-bearing slides from the manifest.
2. Distribute the captured mix across those slides so the DECK-WIDE ratio is honored; do not force every single slide to carry the full mix (the ratio is a deck-level property, not a per-slide one).
3. For each people-bearing slide, assign the specific casting the prompt must carry (who appears, the group, accurate and dimensional skin tones for whoever is cast) so the Slide Image Creator renders it exactly, never by default.
4. Confirm the assignment honors the client's audience-as-mirror: the people in the deck are the people in the audience, cast to be recognizable.
5. Where a slide also carries the client's own likeness, coordinate with the Photo Shoot Director so the audience cast and the founder likeness are handled in separate lanes.
6. Hand the per-slide representation assignments to the Slide Image Creator as a required prompt input.

**Outputs:** A per-slide representation assignment sheet that, summed across the deck, matches the captured mix.
**Hand to:** Slide Image Creator (authors prompts carrying the assigned representation).
**Failure mode:** If the manifest has too few people-bearing slides to honor the mix within ten percent, flag the Director to add a people-bearing slide or adjust the allocation; do not silently ship an unrepresentative deck.

---

### SOP 9.3 -- Image-Stage Deck-Wide Representation Tally

**SOP ID:** SOP-PRES-CUSTOM-07 (BlackCEO)
**Library pointer:** `universal-sops/CLIENT-WEBINAR-DECK-SOP.md` Phase 5 image QC (per-slide group match)
**When to run:** After the Generation Operator delivers the people-bearing slide batch and before final assembly.
**Frequency:** Per batch.
**Inputs:** All generated people-bearing slide images (from local files confirmed in receipts), the per-slide assignment sheet, the captured REPRESENTATION_MIX.

**Steps:**
1. Confirm every people-bearing slide has a receipt with a locally stored image (never tally from an expiring resultUrl).
2. Count the cast across all generated people-bearing images: how many figures of each group actually rendered, deck-wide.
3. Compute the deck-wide percentage per group and compare to the captured REPRESENTATION_MIX.
4. Flag any group whose deck-wide share is more than ten percent off the captured mix. This is an auto-fail at the image stage.
5. For each off-mix flag, identify the specific slides to regenerate (which slides should re-cast to bring the deck-wide tally into range) and route them to the Slide Image Creator with the corrective casting instruction.
6. Re-run the tally after regeneration until the deck-wide mix is within ten percent.

**Outputs:** An image-stage tally record: pass, or a flagged set of slides to regenerate with corrective casting instructions.
**Hand to:** Slide Image Creator (regenerate off-mix slides); QC Specialist (the tally record feeds the representation dimension of QC).
**Failure mode:** If repeated regeneration cannot bring a group within ten percent (the model resists casting a group), escalate to the Director and the Slide Image Creator to adjust the prompt strategy; do not approve an out-of-range deck.

---

### SOP 9.4 -- Final-Deck Representation Tally (The Audience-As-Mirror Gate)

**SOP ID:** SOP-PRES-CUSTOM-08 (BlackCEO)
**Library pointer:** MASTER-QC-AUTOFAIL-RULESET (SOP-SLIDE-00) + qc-specialist-presentations SOP 9.x (PRESENTATION-MASTER-DOCTRINE.md §4) (final deck rendered to PDF to PNG); qc-specialist SOP 9.5
**When to run:** On the assembled, rendered deck, before delivery.
**Frequency:** Per deck, once, at final QC.
**Inputs:** The final deck rendered to PNG pages (from the QC Specialist's render), the captured REPRESENTATION_MIX, the image-stage tally record.

**Steps:**
1. On the rendered final-deck pages (the same artifact the audience will see), recount the cast across every people-bearing slide.
2. Compute the deck-wide percentage per group on the assembled deck and compare to the captured mix.
3. Confirm the deck-wide cast is within ten percent of the captured REPRESENTATION_MIX. If any group is more than ten percent off, the deck is an auto-fail and does not ship.
4. Confirm no slide silently introduced people on a deck flagged NO-PEOPLE, and no slide applied a default cast.
5. Record the final-deck tally result as a blocking pass-artifact (`representation_final_tally.json`) so delivery cannot proceed without it.

**Outputs:** A blocking final-deck representation tally artifact: pass (within ten percent) or fail (with the off-mix groups and slides named).
**Hand to:** Director of Presentations and Delivery Concierge (a passing tally is required before delivery); Slide Image Creator (if a fail requires regeneration).
**Failure mode:** If the final deck fails the tally at delivery time, do not ship. Route the off-mix slides back for regeneration and re-render; a deck that misses the client's audience is not done.

---

*End of SOPs mirror for the Per-Client Representation and Casting Director. Custom Presentations SOPs SOP-PRES-CUSTOM-05 through 08 for BlackCEO. This file is regenerated from the role file and is never edited directly.*
