# WF23 prep scope — NOT acceptance

Status: prep scaffolding on ONB base 2244b00fe. Fixtures plus harness only.

## What lives here (`tests/fixtures/wf23/`)

- `companies.json` — two synthetic companies, distinct IDs and workspaces.
- `presentations.json` — deck / sales / VSL variants; two presentations in
  one company (HOST-ACCEPTANCE procedure step 2 shape).
- `intake_briefs.json` — minimal synthetic intake answers per presentation.
- `matrix.json` — host x install-profile x op enumeration. Every leg is
  NOT-RUN by construction.
- `negative_control.json` — live-process / dead-port control contract.
- `scoped_resources.json` — CC / GHL placeholders. No live credentials.
- `probes/` — adapter-readiness probe scripts (gateway listening/auth,
  skill invocation, standalone-no-gateway). Hermetic, stdlib only.
- `harness/pause_resume.py` — checkpoint save/load for pause/resume legs.
- `hooks/` — render and visual-QC hook stubs emitting PASS or PENDING
  receipts. PENDING is never a pass.
- `matrix/*.sh` — per-install-profile leg stubs. They print NOT-RUN and
  never print PASS.

## What this is NOT

- No engine run, no renderer, no provider call, no real gateway, no live
  Command Center, no live GoHighLevel location.
- Nothing here satisfies QC-PRES-055 checks 1-2 or any HOST-ACCEPTANCE.md
  procedure step. W6 acceptance reruns from fresh input against the exact
  released artifact plus scoped authorized resources.

## Harness self-tests

`tests/test_wf23_prep_harness.py`: fixtures load and cohere; probes
discriminate (positive control passes, negative control fails); matrix
stubs never claim PASS; fixture tree carries no secret patterns.
