# SOP-SIGPRES-04: PHASE 3 — TRANSFORMATIONAL TEACHING + NO-PITCH HYGIENE

**Cluster:** Signature Presentation Doctrine (Phase 3 of 4).
**Doctrine parent:** SOP-SIGPRES-00 (The Signature Presentation Law). Method authority: MASTERDOC Phase 3 + Prime Directives 5, 10, 11, 12; "How do you eat an elephant? Bite by bite."
**Owning roles at write time:** Signature Presentation Architect (steps + bridge); Slide Copywriter and the phase-authors (copy); QC Specialist (Signature Presentations) (grade + the no-pitch gate).
**Enforced at the gate by:** `prove_sp_structure.py` → `AF-SP-TEACH-STEPS` (3–7 steps), `AF-SP-PHASE-RANGE` (band floor 36), `AF-SP-PHASE-LABEL`, `AF-SP-CASESTUDY-CAP` (≤ 2), `AF-SP-IMG-SUGGESTION`, `AF-SP-HOOK`; **and** `prove_sp_no_pitch.py` (**P-SP-P3-HYGIENE**) → `AF-SP-PITCH-IN-TEACH`, `AF-SP-PRICE-IN-TEACH`, `AF-SP-CTA-IN-TEACH`, `AF-SP-BRIDGE`.
**Status:** Doctrine SOP. Slide band 25–60, per-phase floor ≥ 36. **FORBIDDEN to pitch in this phase.** SACRED.

---

## 1. THE RULE

> "Strictly teach. It is FORBIDDEN to pitch any product or service in Phase 3. Set up the sale, teach to the sale — build value first, then transition."

Phase 3 delivers the presenter's methodology as **3 to 7 steps** so the audience never feels anxiety ("how do you eat an elephant? bite by bite"). The methodology is the unique system that produced results for the presenter → their business → the people they serve. Slides 25–60; label the phase with its name + purpose (Directive 10). This phase carries the `METHODOLOGY` marker (of Movement + Message + Methodology).

---

## 2. THE FOUR QUADRANTS OF THE TEACHING

- **Q1 — Importance of the Teaching Section.** Break the methodology into **3–7 steps** to avoid audience anxiety.
- **Q2 — Crafting Engaging & Memorable Steps.** Step titles read like chapter titles; within each step MIX the learning elements: powerful questions, affirmations, action steps, stories, media moments, quotes, one-liners, definitions, formulas, downloadable content.
- **Q3 — Mastering the Art of Delivery.** Storytelling, vocal technique, body language, pacing, visual aids, authenticity/vulnerability. The MASTERDOC's 23-slide exemplar walks one step end to end (step title → hook → question → 3-part anecdote → core teaching → action steps → story cue → media moment → one-liner → definition → formula → quote → question → affirmation → downloadable → real-world example → manifesto → visualization → reinforcing quote → close).
- **Q4 — Tying It All Together + Transition to the Pitch.** The final step summarizes value, adds social proof, and builds a **seamless bridge** to the offer — the transition, not the pitch itself.

The frame decides the teaching unit: **Rules** (Rulebook), **Secrets** (Vault), a named **Blueprint of Quests** (Quest), or the client's own **named steps** (Original). See SOP-SIGPRES-06.

---

## 3. NO-PITCH HYGIENE (the fail-closed teeth)

`prove_sp_no_pitch.py` scans EVERY teaching slide — headline, body, tags, and even the `suggested_image` seed — on normalized text so padding can't hide a leak:

1. **`AF-SP-PITCH-IN-TEACH`** — no q7 offer/product NAME (from the offer-token ledger) appears on any Phase-3 slide.
2. **`AF-SP-PRICE-IN-TEACH`** — no price/monetary token (`$1,997`, `997 dollars`, `$99/mo`, `USD 497`) on any Phase-3 slide.
3. **`AF-SP-CTA-IN-TEACH`** — no enroll/buy/close/scarcity sale-mechanic CTA ("enroll now", "reserve your spot", "money-back guarantee", "doors close", "book a call", …) on any Phase-3 slide.
4. **`AF-SP-BRIDGE`** — the final teaching slide sits **directly before** the first pitch slide (contiguous handoff, no gap or overlap). The bridge slide, being a teaching slide, is ALSO subject to checks 1–3: it may PROMISE what comes next but may NOT name a price or product.

The gate is fail-closed on missing inputs too: no teaching slides (`AF-SP-TEACH-EMPTY`), an empty offer ledger (`AF-SP-OFFER-LEDGER-MISSING`), or a teaching/pitch slide with no integer index (`AF-SP-SLIDE-INDEX`) all abort — a PASS is never vacuous.

---

## 4. STRUCTURE CONTRACT FOR PHASE 3

- **Band:** slides 25–60, contiguous after Phase 2; floor ≥ 36 (`AF-SP-PHASE-RANGE`). A floor, not a fixed span — Directive 11 expansion lands here most often.
- **Teaching steps:** 3–7 (`AF-SP-TEACH-STEPS`), declared via the top-level `teaching_steps` integer or `STEP<n>` tags.
- **Label slide:** name + purpose (`AF-SP-PHASE-LABEL`).
- **Case studies:** **never more than 2** in the whole deck (Directive 12), floor 1 from the department proof battery → band [1, 2]; a missing `tags` array is itself a FAIL so the cap cannot be dodged by not tagging (`AF-SP-CASESTUDY-CAP`).
- **Suggested image / section hook:** as for every phase (`AF-SP-IMG-SUGGESTION`, `AF-SP-HOOK`).
- **No N.E.E.I.T./4-Quadrant requirement:** Phase 3 is NOT one of the quadrant-required phases (those are 1/2/4).

---

## 5. ENFORCEMENT NOTE (for the lockstep)
- Two provers guard Phase 3: `prove_sp_structure.py` (`_chk_sp_structure`) for shape and `prove_sp_no_pitch.py` (`_chk_sp_no_pitch`) for hygiene. Both DEFER for non-signature decks.
- Detection tables in `prove_sp_no_pitch.py` are deliberately NARROW (sale-mechanic / offer tokens, not generic value words) so ordinary teaching copy is never over-caught. Broadening them is a lockstep change (SOP-SLIDE-06), not an ad-hoc edit.

---

## 6. CROSS-REFERENCES
- **SOP-SIGPRES-05** — Phase 4 (where the offer names, price, and CTAs finally belong).
- **SOP-SIGPRES-01** — the offer-token ledger seeded from q7 (what is forbidden here).
- **SOP-PITCH-01…06** — the broader pitch doctrine the bridge hands into.
- `51-signature-presentation/MASTERDOC.md` Phase 3 + the 23-slide exemplar; the four `frame-templates/` Phase-3 notes.
