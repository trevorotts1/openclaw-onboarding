# SOP-SIGPRES-03: PHASE 2 — THE SIGNATURE STORY ("Crafting Your Personal Story")

**Cluster:** Signature Presentation Doctrine (Phase 2 of 4).
**Doctrine parent:** SOP-SIGPRES-00 (The Signature Presentation Law). Method authority: MASTERDOC Phase 2 + Prime Directives 5, 10, 14; the "story craft" methodology notes.
**Owning roles at write time:** Signature Presentation Architect (structure + labels); Slide Copywriter and the phase-authors (copy); QC Specialist (Signature Presentations) (grade).
**Enforced at the gate by:** `prove_sp_structure.py` (**P-SP-STRUCTURE**) → `AF-SP-PHASE-RANGE` (band floor 13), `AF-SP-PHASE-LABEL`, `AF-SP-QUADRANT`, `AF-SP-IMG-SUGGESTION`, `AF-SP-HOOK`.
**Status:** Doctrine SOP. Slide band 12–24, per-phase floor ≥ 13. SACRED.

---

## 1. THE RULE

> "The purpose of your story is so they know that you know where they're coming from. First you tell their story, then you tell yours."

Phase 2 tells the presenter's journey **only after** the audience's story has been told (Phase 1). It is not a résumé — it is a journey of lessons and growth the audience can see themselves inside. Structured by **N.E.E.I.T.** across the **4-Quadrant method**. Slides 12–24; label the phase with its name + purpose before its content (Directive 10).

---

## 2. THE FOUR QUADRANTS

- **Q1 — The Power of Relatability.** The audience sees themselves in your journey; emotions are universal. Don't list accomplishments — tell the journey, the lessons, the growth. Tone: authentic, vulnerable, empathetic.
- **Q2 — Embracing Vulnerability.** Share fears, doubts, weaknesses. "Nobody believes a perfect hero." "The power of vulnerability is relatability." Authenticity is strength. Tone: raw, honest, compassionate.
- **Q3 — Transforming Pain into Purpose.** Reframe pain as the catalyst; turn scars into stars ("My Story Is My Superpower"). Tone: empowering, hopeful, resilient.
- **Q4 — The Power of Your Story.** Legacy + ripple effect; a clear call to reflect and act. Tone: inspiring, empowering, purposeful. Then proceed straight to Phase 3.

---

## 3. STORY CRAFT (the non-negotiables)

- Never share information you cannot make relevant to the audience. "The stage is not the place to be guarded." "The best way to hit a target is at point-blank range." "It's the unedited version."
- **End the section on a gripping "why"** — full of passion and intensity. Lacking intensity or passion undermines the transformation.
- **Directive 14 — write in HARMONY.** If a brand bio, product bio, personal bio, or tone-style was previously shared, the story is written in harmony with it (voice, refrains, motifs).
- Ride one or two recurring **refrain hashtags**, plant a **borrowed-authority quote**, and land on a legacy line + a spoken-aloud affirmation (the anonymized archetype's style lesson). The exact devices are set by the locked frame (SOP-SIGPRES-06): a Rulebook "I'm Worth the Risk" beat, a Vault threaded metaphor, a Quest hashtag-told life narrative.

---

## 4. STRUCTURE CONTRACT FOR PHASE 2

- **Band:** slides 12–24, contiguous after Phase 1; floor ≥ 13 (`AF-SP-PHASE-RANGE`). A floor, not a fixed span.
- **Label slide:** the phase's first slide carries name + purpose (`AF-SP-PHASE-LABEL` if absent).
- **N.E.E.I.T. + 4-Quadrant markers:** required in this phase (`AF-SP-QUADRANT`). Phase 2 is one of the three quadrant-required phases (1/2/4).
- **Suggested image:** non-empty on every slide (`AF-SP-IMG-SUGGESTION`).
- **Section hook:** this phase carries one distinct section hook (SOP-SIGPRES-06) that ladders up to the central chorus.
- **Message marker:** Phase 2 typically carries the `MESSAGE` marker (of Movement + Message + Methodology).
- **Case studies:** the ≤ 2 CASE_STUDY cap is deck-wide (band 1–2). Story-section proof beats can carry a CASE_STUDY tag, but the deck total across all phases must stay in [1, 2] (`AF-SP-CASESTUDY-CAP`).

---

## 5. ENFORCEMENT NOTE (for the lockstep)
- Enforced by `prove_sp_structure.py` via `_chk_sp_structure`. Failure modes: `AF-SP-PHASE-RANGE`, `AF-SP-PHASE-LABEL`, `AF-SP-QUADRANT`, `AF-SP-IMG-SUGGESTION`, `AF-SP-HOOK`, and (deck-wide) `AF-SP-CASESTUDY-CAP`.
- Whether the story actually lands its vulnerability and its gripping "why" is graded semantically by the QC Specialist (Signature Presentations); the prover checks the deterministic structure.

---

## 6. CROSS-REFERENCES
- **SOP-SIGPRES-02** — Phase 1 (their story, told first).
- **SOP-SIGPRES-04** — Phase 3 (the teaching that follows the story).
- **SOP-STORY-01** — the villain/hero arc doctrine.
- `51-signature-presentation/MASTERDOC.md` Phase 2 + the "story craft" notes; the four `frame-templates/` Phase-2 notes.
