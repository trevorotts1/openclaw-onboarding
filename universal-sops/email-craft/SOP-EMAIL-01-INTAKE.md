# SOP-EMAIL-01: LOCK THE BRIEF IN ONE BLOCK

**Cluster:** Email-Craft Rules (`universal-sops/email-craft/`)
**Master authority:** `EMAIL-PIPELINE-MANIFEST.json` + `50-email-engine/EMAIL-MANIFEST.json` + `MASTER-EMAIL-QC-AUTOFAIL-RULESET.md`
**Owning role:** Email Campaign Strategist (Marketing)
**Stage:** P0-INTAKE
**Produces:** `working/copy/brief.json`
**Gates this stage satisfies:** AF-EMAIL-TYPE-MISMATCH, AF-EMAIL-INTAKE-SPLIT, AF-EMAIL-BRIEF-INCOMPLETE

---

## 0. WHY THIS SOP EXISTS

An email sequence authored on a thin or split brief is the sequence that misses the objective, signs with a placeholder, or picks the wrong framework. The brief is the precondition for everything downstream: it is asked as ONE block, answered, and locked before a single subject line is written. A self-attested "brief complete" flag is never trusted — the prover reads the actual fields.

## 1. THE ONE-BLOCK RULE

Ask the intake questions in a SINGLE message (`asked_all_at_once: true`), never one-question-per-turn. Record `one_question_per_turn: false` and a single `question_block_msg_id`. A brief split across turns is AF-EMAIL-INTAKE-SPLIT.

Use `50-email-engine/intake/email-intake-questions.json` as the question set.

## 2. THE SIX REQUIRED FIELDS

Every brief MUST carry all six (missing/empty = AF-EMAIL-BRIEF-INCOMPLETE):

| Field | What it is |
|---|---|
| `objective` | Exactly one of `promotional` / `abandoned-cart` / `upsell` / `downsell`. |
| `buyer_type` | `spontaneous` / `methodical` / `humanistic` / `competitive` (or `all` for a broad promo). |
| `offer` | What is being sold / promoted. |
| `brand_voice` | The founder's voice for the copy. |
| `sequence_position` | `single`, or a named sequence: `landing-page-10-promo`, `high-ticket-appointment`, `convert-and-flow-buyer-12`. |
| `founder_name` | The founder's ACTUAL name — it signs every email. No placeholder. |

Also capture `high_ticket` (y/n) — it decides the subject char band + preview count + whether a persona style + a disruptive element are required.

## 3. LOCK IT

Write `working/copy/brief.json` with `skill: "email-engine"` and the six fields under `answers{}`. A brief whose skill is not `email-engine` is AF-EMAIL-TYPE-MISMATCH.

## 4. VERIFY BEFORE ADVANCING

```
python3 50-email-engine/tools/prove-email.py working/copy/brief.json --kind intake
```

Exit 0 = the brief is locked and P1-SELECT may begin. Any AF code = fix the brief and re-run. Never guess a missing field — return the gap list to the owner and STOP.
