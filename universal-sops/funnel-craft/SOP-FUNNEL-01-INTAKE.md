# SOP-FUNNEL-01: LOCK THE BRIEF, ONE QUESTION AT A TIME

**Cluster:** Funnel-Craft Rules (`universal-sops/funnel-craft/`)
**Master authority:** `FUNNEL-PIPELINE-MANIFEST.json` + `49-signature-funnel/FUNNEL-MANIFEST.json` + `MASTER-FUNNEL-QC-AUTOFAIL-RULESET.md`
**Owning role:** Signature Funnel Specialist (Web-Development / Marketing)
**Stage:** P0-INTAKE
**Produces:** `working/copy/brief.json`
**Gates this stage satisfies:** AF-FUN-INTAKE-TYPE, AF-FUN-INTAKE-MISSING, AF-FUN-INTAKE-SIZE, AF-FUN-INTAKE-OFFER, AF-FUN-INTAKE-REPRESENTATION, AF-FUN-INTAKE-TRUTHGATE, AF-FUN-INTAKE-UNLOCKED

---

## 0. WHY THIS SOP EXISTS

A funnel authored on a thin or split brief is the funnel that fabricates scarcity, assumes the
audience's representation, or ships the wrong size. The brief is the precondition for everything
downstream: it is asked, answered, and LOCKED before a single section of copy is written. A
self-attested "brief complete" flag is never trusted — `prove_sf_intake.py` reads the actual fields.

## 1. ONE QUESTION AT A TIME, ONE SOURCE OF QUESTIONS

Ask ONE plain question per turn and wait for the answer. A wall of questions in a single message is
no longer the rule: it pressures the client, repeats things they already told us, and hides which
answer unlocked which next question.

The canonical question source is `shared-utils/client_intake/question-bank.json` (the shared bank
Skill 49, Skill 71 and Skill 83 all read). `49-signature-funnel/intake/sf-intake-questions.json` is
the Mirror the prover loads and it declares the same rule (`one_question_per_turn: true`); it does not
carry a second, competing set of questions. If a question is missing, add it to the bank — never
start a parallel list.

- Reuse what the client already confirmed instead of asking it again.
- Collect only the decisions that materially change the work.
- Ask about texting readiness only when text messages are part of the plan.
- Keep page-count and picture-count jargon out of the client's question text; describe the choice in
  plain words.
- On "I don't know", give a recommendation with a short reason, or a draft answer they can confirm.
  Never merely repeat the question and never say you cannot guess.
- An answer the client did not give is never invented: it stays missing, or it is recorded as a
  proposal (AI proposal / recommendation / unresolved capability) on the same launch record.

The checkpoint-gated per-offer questions (OTO1 → D1 → OTO2 → D2) are asked only for the offers the
chosen funnel size actually contains, still one at a time.

## 2. THE REQUIRED ANSWERS (size-gated)

| Field | What it is |
|---|---|
| `funnel_type` | Must be `signature-funnel` (else AF-FUN-INTAKE-TYPE). |
| `funnel_size` | Exactly one of `3` / `5` / `7` (else AF-FUN-INTAKE-SIZE). Chooses the page set (see the 3/5/7 matrix). |
| `offer_title` + `price` / `promise` | The Main offer; seeds Section 1. |
| three pains | Circumstantial / private / witnessed — three DIFFERENT pains for the Pain Ladder. |
| `personas` | 3–6 personas for Section 6. |
| `deliverables` | 5–10 concrete items for Section 7. |
| `founder_story` | The Section 12 heartfelt letter source; the founder's REAL name signs it. |
| `brand_colors` | Anchors the Signature Grade Block palette. |
| `representation` | The audience representation percentages — **NEVER assumed** (AF-FUN-INTAKE-REPRESENTATION). Ask; do not guess. |
| per-offer answers | OTO1 / D1 / OTO2 / D2 titles + framing, gated by `funnel_size` (the offer ledger). |
| `reference_images` | Optional; `mode` defaults to `none` (pure text-to-image). |

## 3. THE TRUTH GATE (Q16)

Every scarcity claim, bonus, founder-text number, and community URL MUST be confirmed REAL at intake.
An unconfirmed bonus / founder text / community is AF-FUN-INTAKE-TRUTHGATE. The engine NEVER fabricates
urgency, a bonus, or a community that does not exist.

## 4. LOCK IT

Write `working/copy/brief.json` with `funnel_type: "signature-funnel"`, the size, the offer ledger, the
representation percentages, and the truth-gate confirmations, then mark it locked. An unlocked brief is
AF-FUN-INTAKE-UNLOCKED.

## 5. VERIFY BEFORE ADVANCING

```
python3 49-signature-funnel/scripts/prove_sf_intake.py working/copy/brief.json
```

Exit 0 = the brief is locked and P1-COPY may begin. Any `AF-FUN-INTAKE-*` code = fix the brief and
re-run. Never guess a missing field — return the gap list to the owner and STOP.
