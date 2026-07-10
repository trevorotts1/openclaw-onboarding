# Anthology Engine (Skill 59) -- Operator Instructions

## When to use
A MULTI-CONTRIBUTOR anthology: many external co-authors each write ONE chapter
around a shared theme, curated and assembled by a producer (the OpenClaw box
owner). For a single-author twelve-chapter book use Skill 53 (Book Writer). For
the per-chapter authoring IP alone use Skill 54 (Anthology Writer); this engine
CALLS Skill 54 and owns the intake, ledger, delivery, and Command Center surfaces.

## Onboard a producer (per client, once)

1. Install and resolve the box as the NODE USER, never root:

       bash 59-anthology-engine/install.sh

   It runs the dependency check, resolves the engine tier map (`preflight.sh`),
   reports credential labels SET or NOT SET only, and names the provisioning steps.

2. Provision the client (heavy provisioning lands in `scripts/provision-anthology-client.sh`,
   W2.6): credential gate across all three env stores (live process env first),
   create-or-verify the Convert and Flow custom fields by exact key from
   `config/field-map.json` (a missing field STOPS setup with an operator surface),
   AUTO-PROVISION the standard Anthology pipeline through the CLIENT's OWN private
   integration token, register the forms, provision the Drive producer root under
   the per-client BlackCEO-hosted Shared-Drive root (resolved per box from
   `GOOGLE_DRIVE_ROOT_FOLDER`), bootstrap the ledger, generate the webhook route and
   its secret, seed the Anthology department, register the ONE daily cron tick, run
   the T1 to T9 intake proofs, fire one smoke test.

## Run a stage

Everything runs THROUGH the one sanctioned entry, which gates then dispatches:

    bash 59-anthology-engine/anthology-engine-entry.sh --stage s5 --participant-key <CONTACT_ID>::<ANTHOLOGY_ID> --run-dir <RUN_DIR>
    bash 59-anthology-engine/anthology-engine-entry.sh --stage s9 --anthology-id <ANTHOLOGY_ID> --run-dir <RUN_DIR>

Normal S0 intake arrives on the gateway webhook and drives `intake_router.py`; a
manual or exceptions replay uses `--stage s0 --payload <FILE>`. Use `--plan` to
print the S0 to S9 wiring contract and `--self-test` to run every stage runner's
self-test (the gates still run).

## The stage runners are thin

Each `scripts/stage_sN_*.py` is a THIN dispatcher: it loads the participant via
`anthology_state.py`, composes the pinned prompts, calls Layer 1 (the Skill 54
entry) or `model_router.py`, runs its provers, records artifacts, and opens its
gate. The module logic is authored by sibling units; the runner's ordered wiring
contract and its exit-code classification are fixed (`--plan` prints the contract).

## Guardrails (all fail-closed)

- No signed certificate = not done. A sub-agent's claim of done is a hypothesis
  until independent verification confirms it.
- The provers MEASURE the stripped text; a self-reported count is ignored.
- Every resolved model id is the client's own NON-Anthropic model; the run ledger
  and every shipped file are checked (AF-AE-ANTHROPIC).
- A hand-rolled ungoverned external sender in a run dir aborts the run
  (AF-AE-BYPASS); all external I/O routes through the engine's sanctioned adapters.
- Keying is contact_id, never email. Unroutable submissions land in the exceptions
  queue with the raw payload, never dropped or guessed.
- S9 assembly fires ONLY on the explicit producer trigger with every guard held in
  the writer (own-producer, every participant approved or excluded, at least the
  minimum frozen approved chapters, typed name confirmation, one-way).

## Verify / CI

    bash 59-anthology-engine/verify.sh       # read-only, idempotent, exits nonzero on drift
    bash 59-anthology-engine/verify-deps.sh  # dependency check (python3)
