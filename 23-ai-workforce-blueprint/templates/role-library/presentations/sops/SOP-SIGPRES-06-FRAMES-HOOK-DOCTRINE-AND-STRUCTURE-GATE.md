# SOP-SIGPRES-06: THE FOUR FRAMES, THE HOOK DOCTRINE & THE STRUCTURE GATE

**Cluster:** Signature Presentation Doctrine (deck-wide devices + the structure prover).
**Doctrine parent:** SOP-SIGPRES-00 (The Signature Presentation Law). Method authority: MASTERDOC "Complete Deck Examples" + "Style-Derivation Note" + the hook doctrine; the SACRED-structure contract `51-signature-presentation/structure/sp_structure.json`.
**Owning roles at write time:** Signature Presentation Architect (frame lock + structure ledger + hooks); Hook Lab (`hook-strategist.md`) (the central + section hooks); QC Specialist (Signature Presentations) (grade).
**Enforced at the gate by:** `prove_sp_structure.py` (**P-SP-STRUCTURE**) → `AF-SP-SLIDE-FLOOR`, `AF-SP-PHASE-RANGE`, `AF-SP-PHASE-ORDER`, `AF-SP-PHASE-LABEL`, `AF-SP-IMG-SUGGESTION`, `AF-SP-CASESTUDY-CAP`, `AF-SP-TEACH-STEPS`, `AF-SP-HOOK`, `AF-SP-QUADRANT`, `AF-SP-MMM`.
**Status:** Doctrine SOP. The frame changes only the teaching devices, refrains, and close; every rule below is identical across frames. SACRED.

---

## 1. THE RULE

> "Every deck feels unique while following the identical 4-phase structure. The frame governs the narrative, not the skeleton."

The three complete example decks in the MASTERDOC reveal three reusable teaching frames, plus a from-scratch door. They ship as four **client-facing frame names** (never "style one/two"). Each maps onto the identical 4-phase skeleton (Avatar 1–11, Story 12–24, Teaching 25–60, Pitch 61–100) with every sacred rule intact.

---

## 2. THE FOUR FRAMES

| Frame | `signature_frame` | Teaching unit | Phase-4 signature close |
|---|---|---|---|
| **The Rulebook** | `rulebook` | numbered non-negotiable **Rules** (3–7), each = teaching + affirmation + 3-step action plan; recap of all Rules; a teased bonus "Rule #8???" | a roll-call of iconic figures the audience admires ending "…AND YOU!" with the offer URL; explicit purpose-vs-profit slides |
| **The Vault** | `vault` | numbered **Secrets** (3–7), each = a famous quote → teaching → a numbered affirmation; ONE running metaphor motif deck-wide; a personal-manifesto triad | a blessing — "My Prayer for YOU" |
| **The Quest** | `quest` | a named **Blueprint** of steps grouped into Quests (3–7 steps), each Quest carrying named affirmations; the richest hashtag-driven narrative + a recurring motif hashtag; riddle / definition-pair / literary-passage devices | a poetic **fill-in-the-blank manifesto** the audience completes in their own words (**Directive 13's exemplar** — author it to Example-3 grade) |
| **The Original** | `original` | the client's OWN methodology chunked into 3–7 named steps, devices designed fresh (a bespoke through-line) | a fresh manifesto-grade emotional close that lands as hard as the Quest's, in the client's voice |

Load the matching contract from `51-signature-presentation/frame-templates/the-{rulebook,vault,quest,original}.md`. The frame is orthogonal to the visual `STYLE_SOURCE` branch (a signature deck still answers the visual branch and still gets the three-variant style preview). An unset or out-of-set frame is `AF-SP-FRAME-UNSET` (SOP-SIGPRES-01).

---

## 3. THE HOOK DOCTRINE

- **One central hook, repeated like a chorus.** It recurs on its **3–4 dedicated pure-typography slides** — that count is the live CEILING (banded `AF-HOOK`), never a floor; do not stamp the chorus into a footer on every slide.
- **Four section hooks — one per phase — that ladder up to the central hook.** Each section hook is a **distinct line** from the central hook and from each other (`AF-SP-HOOK`), so they never trip the verbatim-hook-elsewhere battery.
- The hooks live in `working/copy/hook_package.json` (mirrored into the structure ledger's `hook_package`): a non-empty `central_hook` string + exactly four non-empty, distinct `section_hooks`.
- "A pitch deck must always have a damn hook" — one central chorus + smaller section hooks that ladder to it. The Hook Lab owns their authoring; the client's own signature language is used whenever they have it.

---

## 4. THE DECK-WIDE MARKERS AND CAPS

- **N.E.E.I.T. + 4-Quadrant** markers present in phases **1 / 2 / 4** (`AF-SP-QUADRANT`). N.E.E.I.T. = Name, Explain, Example, Instructions, Tone; the 4-Quadrant method is 4 quadrants @ 25%.
- **Movement + Message + Methodology = Manifestation** — all three markers present somewhere in the deck (`AF-SP-MMM`); conventionally Movement in Phase 1, Message in Phase 2, Methodology in Phase 3.
- **≤ 2 case studies** deck-wide (Directive 12), floor 1 → band [1, 2]; a missing `tags` array is itself a FAIL (`AF-SP-CASESTUDY-CAP`).
- **3–7 teaching steps** (`AF-SP-TEACH-STEPS`).
- **A non-empty `suggested_image` on EVERY slide** (Directive 4 / `AF-SP-IMG-SUGGESTION`) — measured on stripped text so whitespace padding can never satisfy it.
- **≥ 100 slides** (or a logged client-exact count) and the contiguous, in-order phase floors (`AF-SP-SLIDE-FLOOR`, `AF-SP-PHASE-RANGE`, `AF-SP-PHASE-ORDER`, `AF-SP-PHASE-LABEL`). See SOP-SIGPRES-00 §2/§3.

---

## 5. THE STRUCTURE GATE AND THE GOLDEN DECKS

`prove_sp_structure.py` loads the SACRED contract (`structure/sp_structure.json`) and enforces every rule above against a deck's copy ledger (`working/copy/sp_structure.json`). Nothing is hard-coded — the floors, caps, and markers are read out of the contract. A violation is fail-closed: the deck is NOT run, NOT rendered, NOT updated.

Each frame ships a **golden regression sample** under `51-signature-presentation/examples/` — a complete, methodology-faithful deck (≥ 100 slides) that PASSES all three SP provers and drives `prove-deck.py` to a PROCESS-CERTIFICATE:

- `examples/golden-quest/` — The Quest (the recommended golden; Directive-13 manifesto close).
- `examples/golden-rulebook/` — The Rulebook (Rules + affirmations + 3-step plans; roll-call close).
- `examples/golden-vault/` — The Vault (Secrets + quotes + one running metaphor; blessing close).
- `examples/golden-original/` — The Original (a from-scratch named methodology; fresh manifesto close).

Each golden carries `sp_intake.json` (clears the intake gate), `sp_structure.json` (clears the structure gate), the `working/copy/` mirrors and `working/checkpoints/` attestations the provers and `prove-deck.py` consume, and an issued `delivery/<slug>-FINAL/PROCESS-CERTIFICATE.{json,md}`. They are the frozen contract for "what a passing signature deck of each frame looks like."

---

## 6. ENFORCEMENT NOTE (for the lockstep)
- `prove_sp_structure.py` (`_chk_sp_structure`) is the deck-wide shape gate; `prove_sp_no_pitch.py` and `prove_sp_intake.py` guard the teaching band and the intake. All three DEFER for non-signature decks.
- Changing a frame contract, a cap, or a marker set is a SOP-SLIDE-06 lockstep change (manifest + `build_deck.py` + `SOP-SLIDE-00` row + `test_preflight.py` fixture + the affected golden). Re-run the lockstep; never hand-edit one leg.

---

## 7. CROSS-REFERENCES
- **SOP-SIGPRES-00…05** — the law and the four phases the frames dress.
- **SOP-SLIDE-03** — the general hook doctrine the central+section hooks inherit.
- `51-signature-presentation/frame-templates/` — the four authoring contracts.
- `51-signature-presentation/structure/sp_structure.json` — the machine contract this gate loads.
