# SOP-SIGPRES-01: THE 8 QUESTIONS — ASKED ONE AT A TIME, RECORDED AS ONE BLOCK + FRAME SELECTION (the gate that unlocks writing)

**Cluster:** Signature Presentation Doctrine (intake).
**Doctrine parent:** SOP-SIGPRES-00 (The Signature Presentation Law). Method authority: MASTERDOC Prime Directives 6, 7, 8 + `51-signature-presentation/intake/sp-8-questions.json` (the authoritative spec + `delivery.conversation_contract`).
**Owning roles at write time:** Signature Presentation Architect (runs SOP 9.1 / 9.2); Brainstorming Buddy (signature mode) is the front door that runs the choice-first, one-question-at-a-time intake via the REQUIRED turn-gate `deck-intake-driver.py --signature --next` / `--answer`, whose final answer assembles the answers into the one atomic record.
**Enforced at the gate by:** the deterministic RECORD gate `prove_sp_intake.py` (**P-SP-INTAKE**) → `AF-SP-8Q-MISSING`, `AF-SP-8Q-SPLIT`, `AF-SP-FRAME-UNSET`, `AF-SP-TYPE-MISMATCH`, `AF-SP-OFFER-UNDECLARED` (validated shape: `working/copy/sp_intake.json`); and the CONVERSATION guard `AF-INTAKE-BATCH` (a QC/Healer intake-trace scan, `enforced_by: qc_check` — it NEVER inspects, runs inside, or gates `build_deck.py` / `run_signature_deck.py`).
**Status:** Doctrine SOP. Under **Trevor's ruling — one-question-at-a-time wins** — Prime Directives 6 & 7 are honored as TWO distinct layers that never conflict: the 8 Questions are **ASKED one at a time** (choice-first) and **RECORDED as ONE atomic block** before any slide is written (Directive 8: once every answer is locked, all slides are written at one time).

---

## 1. THE RULE

> "Do NOT start writing until the 8 Questions have been answered. OFFER a quick-vs-in-depth interview, ask ONE question at a time, and wait for each answer. Once every answer is locked, commit them as ONE atomic record and write all slides at one time." (Prime Directives 6, 7, 8, under Trevor's one-question-at-a-time ruling.)

The Signature Presentation intake runs in **two layers**, kept distinct so they never contradict each other — the 8 Questions are **asked one at a time** and **recorded as one block**:

1. **CONVERSATION LAYER (choice-first, one question at a time).** The front-door agent FIRST offers the owner a **QUICK vs IN-DEPTH** interview, then asks **exactly one of the 8 Questions per message** and waits for the owner's answer before sending the next — never a wall of questions. Dumping two or more of the 8 Questions in a single turn, or opening with no quick-vs-in-depth CHOICE, is **`AF-INTAKE-BATCH`** (intake-conversation scoped; `enforced_by: qc_check` — the QC/Healer intake-trace scan; it NEVER gates `build_deck.py`). The canonical banned anti-pattern is one message enumerating all 8 Questions together with "give me whatever you have got and I will get moving."

2. **RECORD LAYER (one atomic commit).** Once the answers are gathered one at a time, they are **assembled into ONE atomic intake RECORD** (`working/copy/sp_intake.json`). The record fields `record_committed_atomically: true` / `mode: one_block` describe **that assembled ledger being written as one atomic commit** — they are NOT a licence to dump the 8 Questions at the owner. (`asked_all_at_once` is a DEPRECATED alias for `record_committed_atomically`, accepted for one release; `one_question_per_turn` was REMOVED from the record layer — it describes the one-per-turn conversation, never the record commit, and the prover no longer checks it.) This assembled record is what `prove_sp_intake.py` validates; until it passes, slide authoring (`P4-COPY` and everything downstream) is locked.

The standard per-turn deck-intake capture (representation mix, grounded content, the visual style branch) still runs one-question-per-turn BEFORE this intake; the signature intake above is the additional SACRED gate that unlocks writing.

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

Any of q1…q8 missing or empty on the assembled record is `AF-SP-8Q-MISSING`. In a runtime record the presence test is a non-empty answer; in the spec it is a defined, non-empty prompt.

---

## 3. THE FRAME-SELECTION QUESTION (additive to the 8, asked as its own turn in the same one-at-a-time flow)

A ninth, additive question is asked as its own turn in the same one-question-at-a-time flow (it never replaces one of the 8):

> Which Signature frame should carry your Transformational Teaching? **(A) The Rulebook** — numbered non-negotiable Rules, each with an affirmation and a 3-step action plan. **(B) The Vault** — numbered Secrets, each paired with a famous quote and its own affirmation, tied by one running metaphor. **(C) The Quest** — a named Blueprint organized as Quests with steps and affirmations, closing on a poetic fill-in-the-blank manifesto. **(D) The Original** — a from-scratch frame around the client's own methodology. ("Show me" → sketch the teaching topic in three frames, one line each, before they pick.)

`signature_frame` MUST be set to exactly one of `rulebook | vault | quest | original` (else `AF-SP-FRAME-UNSET`). The frame governs the NARRATIVE devices/refrains/close only — it is **orthogonal to** the visual `STYLE_SOURCE` branch; a signature deck still answers the visual branch and still gets the three-variant style preview. Load the matching `51-signature-presentation/frame-templates/the-{rulebook,vault,quest,original}.md` (SOP-SIGPRES-06).

---

## 4. THE TWO-LAYER PROOF AND THE OFFER-TOKEN LEDGER

**Conversation proof (`AF-INTAKE-BATCH`).** The intake conversation must OFFER the quick-vs-in-depth CHOICE first, then ask exactly ONE of the 8 Questions per turn. Two or more of the 8 Questions dumped in a single assistant turn before the owner answers, OR opening with no quick-vs-in-depth choice, is `AF-INTAKE-BATCH` — an intake-conversation autofail the QC/Healer intake-trace scan raises. It is scoped to the conversation ONLY: it never inspects, runs inside, or gates `build_deck.py` / `run_signature_deck.py`. Doctrine authority: `51-signature-presentation/intake/sp-8-questions.json` → `delivery.conversation_contract` (`choice_first: true`, `one_question_per_message: true`, `af_on_violation: "AF-INTAKE-BATCH"`).

**Record proof (`AF-SP-8Q-SPLIT`).** After the one-at-a-time conversation, the answers are committed as ONE atomic ledger. The runtime record must prove the atomic COMMIT: `record_committed_atomically: true` (deprecated alias `asked_all_at_once: true`, accepted for one release), a delivery `mode` of `one_block`, the frame question's `asked_in_same_block: true` (when present), and a `record_commit_ids` (deprecated alias `question_block_msg_id`) that references EXACTLY ONE record commit. This is deterministic (`prove_sp_intake.py`) and gates the machine RECORD, not the conversation — `AF-SP-8Q-SPLIT` fires when the assembled ledger was not committed as one atomic write (`record_committed_atomically != true`, or more than one commit id). `one_question_per_turn` is NO LONGER checked — the record layer no longer teaches batching; asking the owner one question at a time is the REQUIRED conversation behavior and never trips this gate.

**Offer-token ledger (`AF-SP-OFFER-UNDECLARED`).** The EXACT product/offer name(s) captured in q7 are seeded into `offer_token_ledger` (non-empty on a runtime record). Those names are FORBIDDEN in Phase 3 (SOP-SIGPRES-04 / `prove_sp_no_pitch.py`) and REQUIRED to appear in the Phase-4 pitch. A q7 offer absent from the pitch tokens fails.

**Deck-type sanity (`AF-SP-TYPE-MISMATCH`).** `deck_type` must equal `signature_presentation`.

---

## 5. THE DRIVER (how the intake is run and the record is verified)

**The turn-gate is REQUIRED, not optional (E5 fix).** `deck-intake-driver.py --signature --next --run-dir <RUN_DIR>` returns exactly ONE question at a time — the choice-first offer, then q1…q8, then the frame question, reading the SACRED spec `51-signature-presentation/intake/sp-8-questions.json` — and BLOCKS on the active question until `--signature --answer <ID> "<TEXT>"` records and validates it. The front-door agent drives the conversation through this turn-gate call by call (never a batch — `AF-INTAKE-BATCH`); it does not enumerate or ask the questions itself. The FINAL validated answer auto-finalizes: it **assembles the answers into ONE atomic record** `working/copy/sp_intake.json` (stamping `record_committed_atomically` / `one_block` on the COMMITTED ledger) and **runs `prove_sp_intake.py` against it** — the driver is wired straight to the `AF-SP-8Q-SPLIT` gate and exits non-zero (fail-closed) if the record is not a single atomic commit, is missing a question, or has no frame set. The driver never marks an intake verified when the gate cannot be run. (`--signature --record <answers.json>` performs the same assemble-and-verify step directly against a pre-gathered answers file, for tooling that already ran the turn-gate through another surface, e.g. the intake mini-app bridge.)

A bare `deck-intake-driver.py --signature` call — no `--next`, `--answer`, `--record`, or `--plan` — does **not** emit the question set. It was previously a legacy escape hatch that dumped the full 8-Questions-plus-frame payload in one JSON block, letting a caller bypass the turn-gate and self-pace the interview; it now returns a `{"status": "use_turn_gate", "next_command": "... --signature --next ..."}` pointer instead. `deck-intake-driver.py --signature --plan` is the explicit, clearly-labeled read-only dry-run for offline inspection of the full question set — it is never a substitute for driving the live interview.

---

## 6. ENFORCEMENT NOTE (for the lockstep)

- **Conversation layer:** `AF-INTAKE-BATCH` (`enforced_by: qc_check`) — the QC/Healer intake-trace scan. It is doctrine-owned by `51-signature-presentation/intake/sp-8-questions.json` (`delivery.conversation_contract`) and self-defended by `tests/unit/presentation-intake-conversation.test.sh` (CI: `presentation-intake-conversation-guard`). It NEVER gates `build_deck.py` / `run_signature_deck.py`, so it is deliberately NOT a `PIPELINE-MANIFEST.json` / MASTER-ruleset render-gate code — it is a conversation-quality autofail, not a build gate.
- **Record layer:** `prove_sp_intake.py` reads the spec by default and a runtime record when passed as the positional argument; both shapes resolve through one model. Exit 0 = pass, 2 = an `AF-SP-*` violation, 3 = usage/IO (still fail-closed).
- Manifest phase **P-SP-INTAKE** (owning role: Signature Presentation Architect) attests the record; the Phase attestation is a hard pre-condition for the process certificate (SOP-SIGPRES-06 §5).
- Failure modes: conversation → `AF-INTAKE-BATCH`; record → `AF-SP-8Q-MISSING`, `AF-SP-8Q-SPLIT`, `AF-SP-FRAME-UNSET`, `AF-SP-TYPE-MISMATCH`, `AF-SP-OFFER-UNDECLARED`.

---

## 7. CROSS-REFERENCES
- **SOP-SIGPRES-00** — the deck-type law this gate unlocks.
- **SOP-SIGPRES-04** — where the q7 offer names are forbidden (Phase-3 hygiene).
- **SOP-SIGPRES-05** — where the q7 offer names are required (the pitch).
- **SOP-SIGPRES-06** — frame templates + the structure gate.
- `51-signature-presentation/intake/sp-8-questions.json` — the authoritative spec; `delivery.conversation_contract` is the source of truth for the choice-first, one-at-a-time doctrine and the `AF-INTAKE-BATCH` autofail.
- `signature-presentation-architect.md` SOP 9.1 / 9.2 — the runbook this doctrine backs.
