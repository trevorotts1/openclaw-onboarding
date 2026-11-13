# PD-069 — BUILD REPORT

**Unit:** PD-069 · lane FL16 · branch `pd/fl16-page-installer`
**Model:** deepseek-chain (builder) — a fresh opus-chain reviewer verifies.
**Repo:** trevorotts1/openclaw-onboarding

## What the unit is

Ledger title: *"Gate form and video page receipts carry what the check reads"*.

Acceptance row (A1), from `/Volumes/mac mini m4/swarm-contract/_scratch-pd-docs/acc.txt` line 156:

> a test that runs the phase check (`phase_verifiers.PHASE_VERIFIERS[...]`) on a
> completed in-memory install for `P-U-GHL-VSL` and `P-U-FORM-GATE` → pass; on a
> pending plan → fail with "pending", not with a shape reason.

The acceptance text is the only spec text for this unit; the ledger carries no
`note` and no separate finding body.

## Files changed by this unit (owned paths only)

| File | Change |
|---|---|
| `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pd048_receipt_contract.py` | +111 lines: five PD-069 tests appended (3 rows + 2 negative controls). |
| `evidence/PD-069/BUILD-REPORT.md` | this report. |

No production code change was needed. The mechanism the acceptance reads —
`ghl_external_installer.flat_receipt_fields` and `_write_receipts` — is on this
branch already, delivered by sibling unit **PD-048a**, which is a declared
dependency of PD-069. This unit is the dedicated proof for the VSL page and the
gate pair through the registry entry itself (A1), which PD-048a's tests did not
pin: PD-048a exercised `phase_verifiers.verify()` (the wrapper that adds
SIMULATED/provenance guards); A1 names `PHASE_VERIFIERS[...]`, the function the
engine actually dispatches, so these rows call the registered function directly.

## Acceptance row A1 — proven

All commands run from
`<worktree>/23-ai-workforce-blueprint/templates/role-library/presentations/scripts`
with `TMPDIR=/Volumes/mac mini m4/swarm-contract/pd-fix/tmp` (exported, never a
literal `/tmp`).

### AFTER (branch tip + this commit) — green

```
$ python3 -m pytest tests/test_pd048_receipt_contract.py -v
tests/test_pd048_receipt_contract.py::test_pd069_a1_completed_vsl_install_passes_the_registered_check PASSED
tests/test_pd048_receipt_contract.py::test_pd069_a1_completed_gate_pair_passes_the_registered_check PASSED
tests/test_pd048_receipt_contract.py::test_pd069_a1_pending_gate_plan_fails_as_pending_not_shape PASSED
tests/test_pd048_receipt_contract.py::test_pd069_a1_control_stripping_gate_flat_fields_turns_the_check_red PASSED
tests/test_pd048_receipt_contract.py::test_pd069_a1_control_stripping_vsl_flat_fields_turns_the_check_red PASSED
...
13 passed in 2.17s
```

Full log: `pd-fix/scratchpads/PD-069/after-run.log` (rc=0).
Sibling suite unchanged: `python3 -m pytest tests/test_pres011_ghl_external.py
tests/test_pd048_receipt_contract.py -q` → `37 passed in 2.32s` (rc=0,
`scratchpads/PD-069/sibling-run.log`).

Row-by-row:

- **A1.1 completed `P-U-GHL-VSL` → pass.** `MemoryPageAdapter` install
  (`status=complete`), then `phase_verifiers.PHASE_VERIFIERS["P-U-GHL-VSL"](rd)`
  returns `(True, …)` with no shape reason.
- **A1.2 completed `P-U-FORM-GATE` → pass.** `MemoryGateAdapter` pair
  (`status=complete`), then `PHASE_VERIFIERS["P-U-FORM-GATE"](rd)` returns
  `(True, …)` with no shape reason.
- **A1.3 pending plan → "pending", not a shape reason.** Gate plan emitted with
  no adapter (`status=pending_external_execution`). The registered check
  returns `(False, ["AF-U-FORM-GATE: P-U-FORM-GATE: receipt is
  pending_external_execution -- a plan was emitted, no tool result yet"])`.
  The test asserts the pending text is present **and** that no shape marker
  (`no operation name`, `no fields list`, `no actions/steps list`,
  `carries no …`, `file not found`, `file is zero bytes`, `not valid JSON`)
  appears.

### BEFORE (merge-base `1a476d2cb`, pre-PD-048a) — red

The same test file copied onto a detached worktree at the merge base:

```
$ python3 -m pytest tests/test_pd048_receipt_contract.py -k pd069 -q
FFF..
FAILED …test_pd069_a1_completed_vsl_install_passes_the_registered_check
FAILED …test_pd069_a1_completed_gate_pair_passes_the_registered_check
FAILED …test_pd069_a1_pending_gate_plan_fails_as_pending_not_shape
3 failed, 2 passed, 8 deselected in 1.06s
```

Captured failure text (full log `scratchpads/PD-069/before-run.log`):

- VSL: `AF-U-P-U-GHL-VSL: ghl_build_receipt.json: carries no
  execution_id/request_id … carries no remote artifact id (page_id/form_id/funnel_id/…)`
- Gate completed: `AF-U-P-U-FORM-GATE: ecosystem/gate-form.json: no operation
  name … workflows/gate-workflow.json: no actions/steps list`
- Gate pending: the same two **shape** reasons — i.e. before the change a
  pending plan was reported as a malformed artifact, never as `pending`.

### Negative controls (the mutation that turns the proof RED)

Two tests mutate the artefact on disk and re-run the registered check, so the
green rows above cannot be vacuous:

- `test_pd069_a1_control_stripping_gate_flat_fields_turns_the_check_red` —
  delete the top-level `name` / `fields` / `steps` from both pending gate
  receipts → check fails with a shape reason and **loses** the pending reason.
- `test_pd069_a1_control_stripping_vsl_flat_fields_turns_the_check_red` —
  delete `execution_id` / `input_sha256` / `location_id` / `funnel_id` /
  `page_id` from the completed VSL receipt on disk → check fails naming the
  missing identity fields. This also proves the check reads the **file**, not
  `execute_phase`'s return value.

Both controls fail if the mechanism they mutate is re-introduced; both pass on
the pre-fix head for the trivial reason that the check is already red there,
which is why their value is on the AFTER head.

## Measured limitation — pending *page* receipt

Measured, not assumed (`scratchpads/PD-069/pending-vsl-measure.log`):

```
P-U-GHL-VSL pending, PHASE_VERIFIERS["P-U-GHL-VSL"](rd) ->
(False, ["AF-U-P-U-GHL-VSL: ghl_build_receipt.json: carries no remote artifact id
         (page_id/form_id/funnel_id/workflow_id/file_id) -- a GHL push receipt must
         name WHAT was created", "NOTE: GHL readback skipped …"])

P-U-FORM-GATE pending, PHASE_VERIFIERS["P-U-FORM-GATE"](rd) ->
(False, ["AF-U-FORM-GATE: P-U-FORM-GATE: receipt is pending_external_execution
         -- a plan was emitted, no tool result yet"])
```

A pending **page** install has no remote artefact to name yet, and
`phase_verifiers._pu_check_receipt_identity` runs before the installer's own
`validate_receipt` (which *does* answer `pending_external_execution`). The gate
plan path is the one the acceptance's pending clause covers and it now answers
`pending`. Making the page path say `pending` first requires the ordering inside
`phase_verifiers._verify_ghl_vsl_install` / `_make_pu_verifier` to change, and
`phase_verifiers.py` is **not** in PD-069's owned paths (it belongs to lane
fl17, units PD-061/PD-072/…). `PD-069` therefore does not invent a remote id to
buy a green row: `flat_receipt_fields` keeps an unproven id empty, and PD-048a's
A4 and this unit's controls assert exactly that.

## Hunk attribution (merge-base `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc` → HEAD)

| Commit | Unit | Files / hunks |
|---|---|---|
| `164b893b3` | **PD-048a** (sibling, accepted) | `ghl_external_installer.py` +115/−12: the whole flat-receipt contract (`_canonical_json_sha256`, `_gate_plan_blocks`, `flat_receipt_fields`, `_write_receipts` flat pass, flat calls in `_emit_page_plan`/`_execute_pages`/`_emit_gate_plan`/`_execute_gate`, `_blocked_receipt`). `tests/test_pd048_receipt_contract.py` +237: A1–A5 + flat-field tests. |
| `97f99ab84` | **PD-918** (sibling, accepted) | `phase_verifiers.py` +16/−4: two hunks — (1) `_pu_check_receipt_identity` exempts the `unbound-test` sentinel from the placeholder token scan; (2) `_make_pu_verifier` splits `NOTE:` reasons out as a degraded pass. |
| `ffe5625b5` | **PD-918** | `evidence/PD-918/BUILD-REPORT.md` +74. |
| this commit | **PD-069** | `tests/test_pd048_receipt_contract.py` +111 (PD-069 section only, appended after line 234); `evidence/PD-069/BUILD-REPORT.md`. |

No other unit contributes hunks on this branch. PD-069 touches no shared file
(`update-skills.sh`, `universal-sops/_content-manifest.json`, `install.sh` are
untouched).

## Isolation / hygiene

- Work done in a scratch worktree detached at the branch tip; the lane clone
  `pd-fix/worktrees/onboarding/FL16` reports `git status --porcelain` empty
  before and after (its checkout was restored; the branch then fast-forwarded to
  the new tip).
- Scratch temp under `pd-fix/tmp`, no literal `/tmp`, no `--` in directory names.
- No test weakened, deleted, renamed, skipped or xfailed; the pre-existing 8
  tests in the file still pass unchanged.

## Push proof

Build commit **`4198c0648d8d8797155054dedcdb23ca454c4d01`**.

```
$ git rev-parse HEAD
4198c0648d8d8797155054dedcdb23ca454c4d01

$ git push origin HEAD:refs/heads/pd/fl16-page-installer
   ffe5625b5..4198c0648  HEAD -> pd/fl16-page-installer

$ git ls-remote --heads origin refs/heads/pd/fl16-page-installer
4198c0648d8d8797155054dedcdb23ca454c4d01	refs/heads/pd/fl16-page-installer
```

Remote head equals the local commit, full 40 chars compared literally.
Lane clone `pd-fix/worktrees/onboarding/FL16` `git status --porcelain` empty;
scratch worktree `git status --porcelain` empty.
