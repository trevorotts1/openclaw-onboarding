# T-36 (PBB-1703 rebuild) — wire the client-bootstrap engine into the journey-templates step

Unit: PBB-1703 (role BUILD, lane `PBB-1703-lane`). Task: T-36.
Rebuild of the REBUILD-classified branch `pb/PBB-651/t-36-wire`
(audited tip `7459719b86afcbbcd95d6e896556e8a068735b5a`) against live main.

## Why this is a rebuild

`git merge-base origin/main 7459719b` = `3d7135664326eeb7857252afcad5506c1381c3d5`.
`git merge-base --is-ancestor 7459719b origin/main` exits 1 — none of the branch's
added lines are on main. Comparing every added line against the corresponding
`origin/main` blob:

| file | added | present on main | absent (real work) |
|---|---|---|---|
| `38-conversational-ai-system/scripts/03-create-journey-templates.sh` | 68 | 9 | 59 |
| `.github/workflows/qc-static.yml` | 17 | 13 | 4 |
| `evidence/PBB-651/T-36-WIRE.md` | 229 | 0 | 229 |

Base for the diff: `3d7135664326eeb7857252afcad5506c1381c3d5`.

## What was built

`38-conversational-ai-system/scripts/03-create-journey-templates.sh` now provisions
through `38-conversational-ai-system/tools/bootstrap_engine.py` (already on main at
`0b99021b9e212d0f4364c0d4b7e6c738ad18aaef`) instead of a bare `mkdir`/`cp` loop:

* nine `ResourceSpec` entries — eight `journey_template` kinds plus one
  `journey_registry` — each with `adopt_existing=True`;
* permissions limited to `kind:journey_template` and `kind:journey_registry`, so the
  step can never provision a credential, secret, provider or model;
* a step receipt is written by the engine for every completed step, so a re-run
  resumes instead of restarting;
* the step fails (exit 1) with a per-resource reason when any spec ends up
  `skipped`, `refused` or `failed`; `blocked` (an unowned object is in the way) is
  preserved and reported, never overwritten;
* the heredoc runs under `python3 -I` so a shadowing module beside the checkout
  cannot be imported.

Added check: `38-conversational-ai-system/tools/tests/test_journey_templates_script.py`
(four tests: created+receipted, foreign bytes preserved, identical file adopted,
re-run writes nothing).

## Shared-file block

`.github/workflows/qc-static.yml` — the branch adds a 17-line CI step that runs
`38-conversational-ai-system/tools/tests/test_bootstrap_engine.py` (that test file
already exists on main). This lane may not touch a CI workflow, so the step is NOT
included here. It needs a lane with workflow ownership:
**SHARED-FILE-BLOCKED `.github/workflows/qc-static.yml`**.

## Check exit codes

| check | rc |
|---|---|
| `bash -n 03-create-journey-templates.sh` | 0 |
| first run into an empty `MASTER_FILES_DIR` (9 created) | 0 |
| second run (idempotent, 9 preserved, state byte-identical) | 0 |
| foreign divergent `coach/journey.md` — bytes preserved, 8 others installed | 0 |
| identical pre-existing `coach/journey.md` — receipt `adopted`, bytes unchanged | 0 |
| `python3 -I tools/tests/test_journey_templates_script.py` | 0 (4 tests OK) |
| `python3 -I tools/tests/test_bootstrap_engine.py` | 0 (35 tests OK) |

Bite-proof for the added test: dropping `kind:journey_registry` from the engine
permissions makes the registry spec `skipped`, the step exits 1, and the suite goes
red — `BITE_BROKEN_RC=1` (4 failures). Restored the permission and re-ran:
`BITE_RESTORED_RC=0`. The test is not vacuous.

## Not claimed

No CI step (blocked above). No merge, no push to main. Nothing about traffic
authorisation — the engine provisions files and receipts only.
