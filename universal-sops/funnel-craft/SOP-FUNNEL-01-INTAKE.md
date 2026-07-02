# SOP-FUNNEL-01: LOCK THE BRIEF IN ONE BLOCK

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
downstream: it is asked as ONE block (the Q1–Q17 sequence), answered, and LOCKED before a single
section of copy is written. A self-attested "brief complete" flag is never trusted — `prove_sf_intake.py`
reads the actual fields.

## 1. THE ONE-BLOCK RULE

Deliver the intake questions from `49-signature-funnel/intake/sf-intake-questions.json` in a SINGLE
message, never one-question-per-turn. The checkpoint-gated per-offer questions (OTO1 → D1 → OTO2 → D2)
are asked only for the offers the chosen funnel size actually contains.

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
