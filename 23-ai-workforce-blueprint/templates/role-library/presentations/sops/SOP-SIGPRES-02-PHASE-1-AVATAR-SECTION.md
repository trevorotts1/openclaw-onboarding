# SOP-SIGPRES-02: PHASE 1 — THE AVATAR SECTION ("Mastering the Audience Avatar")

**Cluster:** Signature Presentation Doctrine (Phase 1 of 4).
**Doctrine parent:** SOP-SIGPRES-00 (The Signature Presentation Law). Method authority: MASTERDOC Phase 1 + Prime Directives 5, 10; the "Trevor Otts Methodology — avatar craft" notes.
**Owning roles at write time:** Signature Presentation Architect (structure + labels); the four phase-authors and the Slide Copywriter (copy); QC Specialist (Signature Presentations) (grade).
**Enforced at the gate by:** `prove_sp_structure.py` (**P-SP-STRUCTURE**) → `AF-SP-PHASE-RANGE` (band floor 11), `AF-SP-PHASE-LABEL` (the labeled name+purpose slide), `AF-SP-QUADRANT` (N.E.E.I.T. + 4-Quadrant markers), `AF-SP-IMG-SUGGESTION` (suggested image per slide), `AF-SP-HOOK` (this phase's section hook).
**Status:** Doctrine SOP. Slide band 1–11, per-phase floor ≥ 11. SACRED.

---

## 1. THE RULE

> "The purpose of the avatar section is so that I can find myself in your presentation. First you tell THEIR story, then you tell yours."

Phase 1 opens the deck **inside the audience's story** — never with a self-introduction. Done well it captures 80–90% of the room's focus before the presenter has claimed a single credential. The section is structured by **N.E.E.I.T.** (Name, Explain, Example, Instructions, Tone) across the **4-Quadrant method** (4 quadrants @ 25% each). Slides 1–11; label the phase with its name + purpose before its content (Directive 10).

---

## 2. THE FOUR QUADRANTS

- **Q1 — Introduction & Understanding Your Audience.** Build the audience avatars (segments, needs, challenges, aspirations). Identify how each problem or aspiration manifests emotionally / visually / auditorily; pick the single most impactful manifestation per slide. Tone: empathetic, authentic, curious, non-judgmental, inspiring.
- **Q2 — Telling "Their Story" (Current State).** Dive into their problems; manifest them emotionally, mentally, visually; craft a **first-person narrative in the audience's own words**; deliver with empathy and conviction. Tone: empathetic, relatable, passionate, empowering.
- **Q3 — Guiding Toward Transformation (Aspirational Avatar).** "If I'm using three avatars, two bring problems to life; the last brings aspirations to life." Paint the desired future state; inspire massive action. Tone: inspiring, hopeful, empowering, visionary.
- **Q4 — Inspiring Action & Lasting Impact.** Weave problem → aspiration → manifestation into one cohesive narrative; review the avatar flow; craft a compelling call to reflect/act. Tone: motivating, confident, community-focused, celebratory. Then proceed straight to Phase 2.

---

## 3. AVATAR CRAFT (the non-negotiables)

- Do **not** open by introducing yourself — get straight into the audience's story.
- Use authentic, visceral language in THEIR words; embody the emotion, the visual, and the audio of each problem.
- Keep the avatar in the AUDIENCE's point of view. "People don't care who you are until they know you care about who they are."
- **Every avatar has a story** — capture the emotional journey, inner dialogue, and deeper narrative; make it multi-dimensional, not a flat demographic sketch.
- Plant the phase's **section hook** here (SOP-SIGPRES-06) — one distinct line that ladders up to the deck's central chorus. Frame-specific refrains (a Rulebook authenticity refrain, a Quest motif hashtag, a Vault metaphor line) are established in this phase and recur deck-wide.

---

## 4. STRUCTURE CONTRACT FOR PHASE 1

- **Band:** slides 1–11, contiguous from slide 1; floor ≥ 11 (`AF-SP-PHASE-RANGE`). This is a floor, not a fixed span — Phase 1 may carry more when the deck expands to ≥ 100 (SOP-SIGPRES-00 §2/§3).
- **Label slide:** the phase's first slide carries the name + purpose (`label_slide: true`, tag `PHASE-LABEL`) — `AF-SP-PHASE-LABEL` if absent.
- **N.E.E.I.T. + 4-Quadrant markers:** the phase must carry the `N.E.E.I.T.` and `4-Quadrant` tags (`AF-SP-QUADRANT` if absent). Phase 1 is one of the three quadrant-required phases (1/2/4).
- **Suggested image:** every slide carries a non-empty `suggested_image` seed (`AF-SP-IMG-SUGGESTION`) — the authoring seed the Prompt Author expands to the rich prompt; it never replaces the prompt floor.
- **Movement marker:** Phase 1 typically carries the `MOVEMENT` marker (of Movement + Message + Methodology; SOP-SIGPRES-06 §4).

---

## 5. ENFORCEMENT NOTE (for the lockstep)
- Enforced by `prove_sp_structure.py` via `_chk_sp_structure` (build_deck preflight). Failure modes: `AF-SP-PHASE-RANGE`, `AF-SP-PHASE-LABEL`, `AF-SP-QUADRANT`, `AF-SP-IMG-SUGGESTION`, `AF-SP-HOOK`.
- The semantic grade (does the avatar actually open in the audience's POV, in their words?) is the QC Specialist (Signature Presentations)' independent job — the prover checks the deterministic markers, the QC role checks the substance.

---

## 6. CROSS-REFERENCES
- **SOP-SIGPRES-03** — Phase 2 (your story, told only after theirs).
- **SOP-SIGPRES-06** — the hook doctrine (this phase's section hook) + N.E.E.I.T./4-Quadrant marker rules.
- **SOP-CAST-01** — audience composition and casting (who the avatar is).
- `51-signature-presentation/MASTERDOC.md` Phase 1; the four `frame-templates/` Phase-1 notes.
