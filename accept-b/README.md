# PRES-055 leg B — Docker-matrix + CC/GHL + PRES-025 (W6 WF23, Opus)

Scope: NEW files ONLY under `accept-b/` in worktree `run/worktrees/wf23-onb-accept`,
branch `pres055-wf23-b` from `db4c0fdff`. READ-ONLY everywhere else in the repo.
NEVER push/tag/release/merge/stash. No live client data, no real paid calls.

## What leg B runs (all offline / synthetic except honest daemon attempts)

| Module | Leg | Nature |
|---|---|---|
| `docker_matrix_b.py` | Docker matrix (Hostinger + Contabo profiles x fresh/upgrade/restart) | Attempts REAL `docker info` / `docker version` daemon contact. Daemon DOWN here: records NOT-VERIFIED with exact daemon error, never fabricates. |
| `docker_matrix_b.py` | mac-native non-Docker legs | Runs REAL commands on this box: WF23 prep harness (17 tests, standalone + pytest), checkout selftest, upsell suites. Labeled SOURCE-RUN (source tree, not installed artifact): cannot count as deployed acceptance per QC rule. |
| `cc_ghl_leg_b.py` | CC leg | Exact released artifact receipt check (3/3 sha256 vs ARTIFACT-RECEIPT.json) + static CC TaskStatus contract test (`test_cc_contract.py`). Connected CC acceptance: NOT-VERIFIED (no scoped live Command Center designated in this packet; no live calls made). |
| `pres025_leg_b.py` | PRES-025 fold | `checkout_form_builder.py --selftest` + `fixture_acceptance_proof()` (QC-PRES-025 checks 2/3) against synthetic constants `loc_pres025_synthetic_fixture` / `pres025-synthetic-test-merchant` behind SAME signatures (`Skill44LiveAdapter` / `Skill06LiveTaskRunner` / `ProviderSandboxLiveAdapter`), zero real charge + refusal proofs + full upsell verifier suites. |
| `run_leg_b.py` | Orchestrator | Runs all legs, writes receipts to packet `run/evidence/PRES-055/b-docker/` + `run/candidates/PRES-055-b/candidate.json` (after worktree commit SHA known). |

## Labels used in receipts

- SOURCE-RUN PASS: real command ran green from the source tree on this host.
  Useful, still labeled: NOT deployed-artifact / NOT GHL acceptance.
- NOT-VERIFIED: leg attempted honestly, blocking fact recorded (daemon down /
  no scoped live resource), zero fabrication.
- FIXTURE PASS (SYNTHETIC-OFFLINE): PRES-025 checks 2/3 against designated
  synthetic fixtures, structurally incapable of real charge / real write.
- No receipt here self-approves anything. QC-PRES-055 + QC-PRES-025 stay OPEN
  pending INDEPENDENT QC verdict.
