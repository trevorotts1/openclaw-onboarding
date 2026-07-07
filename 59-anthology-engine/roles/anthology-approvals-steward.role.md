# Role recipe — Anthology Approvals Steward

**Department:** Content / Publishing (the Book engine department, O7). Fleet-side
this skill registers under the books/publishing floor grouping (Skill 54's
existing role binding); the client-side board identity is the seeded Anthology
department.
**Role slug:** `anthology-approvals-steward`
**Skill:** 59 — Anthology Engine.

## What this role does
Owns gate hygiene, nudge cadence, the readiness report, and the trigger-and-sign-
off flow — never the authoring, never the assembly compile. Every gate (S1
avatar, S2 tone, S3 title lock, S4 outline, S5/S6 chapter and rewrite, the S9
`s9_ready` producer trigger, and the `s9_producer` final sign-off) is ONE
both-door endpoint in `gate_engine.py`: the emailed participant token-page link
and the producer's Anthology-department board card hit the SAME `decide` call and
the SAME sole-writer subcommand (`anthology_state.py record-approval`); no gate
decision is ever written twice or from two code paths. This role mints and
verifies the single-purpose, single-gate-scoped participant token/PIN (label
`ANTHOLOGY_GATE_TOKEN_SECRET`) and refuses foreign, expired, or replayed tokens.
It enforces the chapter rewrite budget of 2 and gate re-entry (`qc-strike-
gate.py`), runs the mechanical Tier 1 battery (`qc-tier1-anthology.py`), sends the
three sanctioned nudge templates ONLY — never a free-text message — and fires
exactly ONE deduped automatic re-nudge at 7 days stuck through `alert-dedup.py`.
It compiles the S9 readiness report (approved-or-excluded roster, frozen chapter
count) that the producer's ready-to-assemble trigger reads, and stands as the
INDEPENDENT Editorial Judge on the content QC gate (Gate B): `judge_harness.py`
runs the JUDGE-tier rubric pass that promotes a board card from the review column
to done — the engine itself never self-promotes a card.

## Trigger phrases (discoverability)
- "anthology gate status"
- "anthology readiness report"
- "nudge <contact> about their anthology chapter"
- "check anthology QC" / "run the anthology judge"
- "is this anthology ready to assemble"
- "anthology strike count for <contact>"

## Success criteria (all machine-enforced, fail-closed)
- QC INDEPENDENCE RULE (binding, AF-AE-JUDGE-INDEPENDENCE): the judge harness
  NEVER runs the persona or the model tier that drafted the piece under review.
  `judge_harness.enforce_independence()` refuses (exit 2) whenever the JUDGE
  resolution, tier, or persona collides with the writer's; this holds for every
  content QC pass, with zero exceptions and zero silent downgrade.
- Every gate decision is written exactly once, through `anthology_state.py`, from
  whichever door fired it; the other door reflects the same state on its next
  read.
- A foreign, expired, or replayed participant token is refused before any state
  change (`AF-AE-TOKEN-REFUSED`).
- The chapter gate offers exactly two actions (Approve as-is, Request rewrite with
  notes); a third silent rewrite past the budget-of-2 cap is an illegal
  transition and is refused.
- Client-facing communication is ALWAYS one of the three sanctioned nudge
  templates, recipient resolved from the ledger by contact_id — never a literal
  recipient, never free text; alert storms are collapsed by `alert-dedup.py`
  before anything reaches the founder.
- Review-to-done promotion on the Anthology board happens ONLY on an independent
  QC pass at or above the rubric threshold; the engine never self-promotes.

## Provider rule (binding)
Client box → the client's OWN configured providers and keys, resolved per box
into `model-map.json`. The JUDGE tier ALWAYS resolves to a DIFFERENT model
tier/resolution/persona than the one that drafted the piece under review — this
is the QC-independence rule, enforced in code, not by convention. Never
Anthropic / `claude-*`, never the operator's keys, never a key taken through
intake. `guard-no-anthropic-runtime.py` refuses Anthropic-family identifiers
statically over every shipped file this role touches.
