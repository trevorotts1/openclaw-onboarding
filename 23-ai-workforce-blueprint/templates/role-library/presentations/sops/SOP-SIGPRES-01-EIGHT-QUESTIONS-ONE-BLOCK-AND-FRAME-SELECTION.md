# SOP-SIGPRES-01: THE 8 QUESTIONS IN ONE BLOCK + FRAME SELECTION (the gate that unlocks writing)

**Cluster:** Signature Presentation Doctrine (intake).
**Doctrine parent:** SOP-SIGPRES-00 (The Signature Presentation Law). Method authority: MASTERDOC Prime Directives 6, 7, 8 + `51-signature-presentation/intake/sp-8-questions.json`.
**Owning roles at write time:** Signature Presentation Architect (runs SOP 9.1 / 9.2); Brainstorming Buddy (signature mode) is the front door that emits the block via `deck-intake-driver.py --signature`.
**Enforced at the gate by:** `prove_sp_intake.py` (**P-SP-INTAKE**) → `AF-SP-8Q-MISSING`, `AF-SP-8Q-SPLIT`, `AF-SP-FRAME-UNSET`, `AF-SP-TYPE-MISMATCH`, `AF-SP-OFFER-UNDECLARED`. Validated shape: `working/copy/sp_intake.json`.
**Status:** Doctrine SOP. Prime Directives 6 & 7 are SACRED — the questions are asked ALL AT ONCE, in ONE block, BEFORE any slide is written.

---

## 1. THE RULE

> "Do NOT start writing until the 8 Questions have been asked. Ask all 8 at one time. Once answered, write all slides at one time." (Prime Directives 6, 7, 8.)

The Signature Presentation intake is the EXACT OPPOSITE of the standard one-question-per-turn deck intake. The **8 Questions AND the frame-selection question are delivered as ONE message block** — never one-per-turn. This is the signature-method gate: until `prove_sp_intake.py` passes, slide authoring (`P4-COPY` and everything downstream) is locked.

The standard per-turn deck-intake capture (representation mix, grounded content, the visual style branch) still runs one-question-per-turn BEFORE this block; this block is the additional SACRED gate that unlocks writing.

---

## 2. THE 8 QUESTIONS (verbatim ids q1…q8)

1. **q1** — What is the title of your Signature Presentation?
2. **q2** — Do you want me to provide other possible titles before I start writing?
3. **q3** — Any specific pain points to address in the avatar section?
4. **q4** — Key elements of your story to consider before crafting the personal-story section?
5. **q5** — What do you want to teach in the transformational-teaching section? ("7 Secrets to ___", "5 Ways to ___", "Mastering the ___ Protocol", "The ___ Blueprint to ___")
6. **q6** — Do you want other possible titles for the transformational-teaching section?
7. **q7** — **What product(s) will you offer at the end?** (the OFFER question — see §4)
8. **q8** — Anything else to consider before I start writing?

Any of q1…q8 missing or empty is `AF-SP-8Q-MISSING`. In a runtime record the presence test is a non-empty answer; in the spec it is a defined, non-empty prompt.

---

## 3. THE FRAME-SELECTION QUESTION (additive to the 8, asked in the SAME block)

A ninth, additive question is asked in the same block (it never replaces one of the 8):

> Which Signature frame should carry your Transformational Teaching? **(A) The Rulebook** — numbered non-negotiable Rules, each with an affirmation and a 3-step action plan. **(B) The Vault** — numbered Secrets, each paired with a famous quote and its own affirmation, tied by one running metaphor. **(C) The Quest** — a named Blueprint organized as Quests with steps and affirmations, closing on a poetic fill-in-the-blank manifesto. **(D) The Original** — a from-scratch frame around the client's own methodology. ("Show me" → sketch the teaching topic in three frames, one line each, before they pick.)

`signature_frame` MUST be set to exactly one of `rulebook | vault | quest | original` (else `AF-SP-FRAME-UNSET`). The frame governs the NARRATIVE devices/refrains/close only — it is **orthogonal to** the visual `STYLE_SOURCE` branch; a signature deck still answers the visual branch and still gets the three-variant style preview. Load the matching `51-signature-presentation/frame-templates/the-{rulebook,vault,quest,original}.md` (SOP-SIGPRES-06).

---

## 4. THE ONE-BLOCK PROOF AND THE OFFER-TOKEN LEDGER

**One-block proof (`AF-SP-8Q-SPLIT`).** The runtime record must prove single-block delivery: `asked_all_at_once: true`, `one_question_per_turn: false`, a delivery `mode` of `one_block`, the frame question's `asked_in_same_block: true`, and a `question_block_msg_id` that references EXACTLY ONE block. Any signal that the questions were split across turns fails the gate.

**Offer-token ledger (`AF-SP-OFFER-UNDECLARED`).** The EXACT product/offer name(s) captured in q7 are seeded into `offer_token_ledger` (non-empty on a runtime record). Those names are FORBIDDEN in Phase 3 (SOP-SIGPRES-04 / `prove_sp_no_pitch.py`) and REQUIRED to appear in the Phase-4 pitch. A q7 offer absent from the pitch tokens fails.

**Deck-type sanity (`AF-SP-TYPE-MISMATCH`).** `deck_type` must equal `signature_presentation`.

---

## 5. THE DRIVER (how the block is emitted and verified)

`deck-intake-driver.py --signature` emits the ONE-block turn (all 8 Questions + the frame question, `delivery.mode: one_block`), reading the SACRED spec `51-signature-presentation/intake/sp-8-questions.json`. After the client answers, `--signature --record <answers.json>` assembles `working/copy/sp_intake.json` and **runs `prove_sp_intake.py` against it** — the driver is wired straight to the `AF-SP-8Q-SPLIT` gate and exits non-zero (fail-closed) if the record is a split intake, is missing a question, or has no frame set. The driver never marks an intake verified when the gate cannot be run.

---

## 6. ENFORCEMENT NOTE (for the lockstep)

- `prove_sp_intake.py` reads the spec by default and a runtime record when passed as the positional argument; both shapes resolve through one model. Exit 0 = pass, 2 = an `AF-SP-*` violation, 3 = usage/IO (still fail-closed).
- Manifest phase **P-SP-INTAKE** (owning role: Signature Presentation Architect) attests the record; the Phase attestation is a hard pre-condition for the process certificate (SOP-SIGPRES-06 §5).
- Failure modes: `AF-SP-8Q-MISSING`, `AF-SP-8Q-SPLIT`, `AF-SP-FRAME-UNSET`, `AF-SP-TYPE-MISMATCH`, `AF-SP-OFFER-UNDECLARED`.

---

## 7. CROSS-REFERENCES
- **SOP-SIGPRES-00** — the deck-type law this gate unlocks.
- **SOP-SIGPRES-04** — where the q7 offer names are forbidden (Phase-3 hygiene).
- **SOP-SIGPRES-05** — where the q7 offer names are required (the pitch).
- **SOP-SIGPRES-06** — frame templates + the structure gate.
- `signature-presentation-architect.md` SOP 9.1 / 9.2 — the runbook this doctrine backs.
