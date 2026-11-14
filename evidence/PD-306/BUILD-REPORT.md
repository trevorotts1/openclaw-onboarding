# PD-306 — BUILD REPORT

**Unit:** PD-306 — Execution stamps are keyed, and a human verdict never touches the graded report
**Lane:** FL35 · **Branch:** `pd/fl35-sealed-record`
**Repo:** trevorotts1/openclaw-onboarding
**Base:** `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc`
**Builder:** deepseek-chain · **Attempt:** 2 (attempt 1 returned BLOCKED with zero commits)
**Acceptance rows:** A1

---

## 1. What was built

Three defects from the FAIL receipt `PD-306.27ecf3f8…63051034f13` are all closed on this branch.

### 1.1 A1 — keyed hash leg (own work)

`presentation_job/execution_stamp.py`

| Addition | Purpose |
|---|---|
| `ROW_HASH_FIELD = "row_hash"`, `ROW_HASH_ALG`, `STAMP_LEGACY_MARK` | the row's keyed-hash field and the legacy log marker |
| `_canonical_row(row)` | canonical JSON over every row field **except** `row_hash` |
| `keyed_row_hash(row, run_key)` | `HMAC-SHA256(run_key, canonical_row)` |
| `_row_is_valid(row, run_key)` | `hmac.compare_digest` against the recomputed hash; no key → invalid |
| `resolve_run_key(run_dir, run_key=None)` | explicit key, else read back from `<run_dir>/state.json` — **never mints** |
| `trusted_rows(rows, run_key, …)` | the ONE read rule, applied to every stamp surface |
| `author_stamp(..., run_key=None)` / `qc_stamp(..., run_key=None)` | every written row now carries `row_hash` |

Every read surface now filters through `trusted_rows`: `qc_independence_reason`,
`_all_stamp_rows`/`consumed_coverage_reasons`, and `stale_units`.

### 1.2 A1 — legacy leg (own work, explicit)

The rule is explicit in the module docstring and in one function, `trusted_rows`:

* **no row in the file carries `row_hash`** → the file predates PD-306 → every row is
  accepted exactly as today, and the read logs `stamp.legacy` on stderr.
* **any row carries `row_hash`** → strict → every row without a hash valid under this
  run's key is **ignored**. A run with no key trusts no hashed row (fail-closed).

The legacy/strict decision is made **per file**, never across the store, so one hashed
file can never retroactively invalidate a neighbouring pre-PD-306 file.

### 1.3 Defect 3 — the key was not on this branch: CARRIED, DECLARED FOREIGN

`pd/fl35-sealed-record` had zero `run_key` symbols: `c40b6744d` is not an ancestor, and
`git branch --contains c40b6744d` names only `pd/fl05-engine-reporting`. No merge, no
rebase, no push to `pd/fl05-engine-reporting` was performed — the batch-merge room
reconciles.

**FOREIGN HUNKS — belong to PD-906, must be reconciled at merge:**

| File | Hunk | Source commit | Size |
|---|---|---|---|
| `presentation_job/state.py` | `import secrets`; `RUN_KEY_FIELD`, `RUN_KEY_BYTES`, `mint_run_key()`, `run_key_of()`, `ensure_run_key()` | `c15aca513a1fed8ae4c16d547da14aabf5e41635` | +46 / −0 |
| `presentation_job/phases.py` | `from .state import (… ENTRY_COMMAND, ensure_run_key,)` | `c40b6744dae34ef7e560c71166294919a7cd27e5` | +15 / −1 |
| `presentation_job/phases.py` | `_script_nonce_env` docstring paragraph: the nonce is not a run identity | `c40b6744d` | (same hunk) |
| `presentation_job/phases.py` | `Engine.run`: `with self._state_lock: ensure_run_key(self.state, self.store)` before the U024 start-up check | `c40b6744d` | (same hunk) |

Copied **semantically identical** to `c15aca513`/`c40b6744d`; the only difference is
context line numbers (FL35 has not received the other FL05 units). In the same shape as
PD-205c's declaration of the PD-300 hunks it carried. `pd/fl05-engine-reporting` was
read, never written.

The remaining PD-306 edits (`execution_stamp.py`, its tests) are this unit's own.

---

## 2. Proof

### 2.1 The unit's own tests — 11 passed

```
$ python3 -I -m pytest tests/test_pd_runfacts_306_execution_stamp.py -v
tests/test_pd_runfacts_306_execution_stamp.py::test_keyed_hash_changes_when_the_row_changes_and_not_otherwise PASSED [  9%]
tests/test_pd_runfacts_306_execution_stamp.py::test_edited_row_no_longer_verifies PASSED [ 18%]
tests/test_pd_runfacts_306_execution_stamp.py::test_run_key_mints_once_and_is_idempotent PASSED [ 27%]
tests/test_pd_runfacts_306_execution_stamp.py::test_ensure_run_key_persists_through_the_store PASSED [ 36%]
tests/test_pd_runfacts_306_execution_stamp.py::test_the_key_is_never_logged_or_printed PASSED [ 45%]
tests/test_pd_runfacts_306_execution_stamp.py::test_hashless_file_is_treated_as_today_and_logs_stamp_legacy PASSED [ 54%]
tests/test_pd_runfacts_306_execution_stamp.py::test_hashless_row_is_ignored_once_any_row_is_hashed PASSED [ 63%]
tests/test_pd_runfacts_306_execution_stamp.py::test_a_run_with_no_key_trusts_no_hashed_row PASSED [ 72%]
tests/test_pd_runfacts_306_execution_stamp.py::test_the_keyed_read_rejects_what_the_old_read_accepted PASSED [ 81%]
tests/test_pd_runfacts_306_execution_stamp.py::test_consumed_coverage_and_stale_units_use_trusted_rows PASSED [ 90%]
tests/test_pd_runfacts_306_execution_stamp.py::test_verdict_in_its_own_file_leaves_the_report_stamp_passing PASSED [100%]
============================== 11 passed in 0.05s ==============================
```

### 2.2 Point-by-point

| Claim | Test | Evidence |
|---|---|---|
| key mints once and is idempotent | `test_run_key_mints_once_and_is_idempotent`, `test_ensure_run_key_persists_through_the_store` | two `ensure_run_key` calls return the same hex; the key survives `StateStore.save/load` (resume) |
| key never logged or printed | `test_the_key_is_never_logged_or_printed` | the raw key appears in neither captured stdout nor stderr across 4 read surfaces, and not in the stamp file — only its HMAC does |
| per-row hash changes when the row changes, not otherwise | `test_keyed_hash_changes_when_the_row_changes_and_not_otherwise` | identical rows → identical hash; one changed field → different hash; hash field excluded from its own coverage |
| hashless legacy row handled by the implemented rule | `test_hashless_file_is_treated_as_today_and_logs_stamp_legacy` | pre-PD-306 pair still passes (`reason == ""`) and `stamp.legacy` is emitted |
| once rows are hashed a hashless row is not silently accepted | `test_hashless_row_is_ignored_once_any_row_is_hashed`, `test_a_run_with_no_key_trusts_no_hashed_row` | 2-row file with 1 hashed row → 1 trusted row; the sneaked reviewer is dropped and the gate returns `AF-EXEC-STAMP: no trusted REVIEWER stamp…` |

### 2.3 The keyed hash failing on the OLD behaviour

`test_the_keyed_read_rejects_what_the_old_read_accepted` is the negative half. It forges a
reviewer row (independent `claude-opus` model, no `row_hash`) into the stamp file and then
runs both reads:

* **old read** (`_load_stamps(...)["rows"]`, i.e. the pre-PD-306 path) sees the forged row
  and asserts `old_reviewer[0]["model"] == "claude-opus"` — the forgery is **trusted**;
* **new read** (`trusted_rows`) drops it → `[]` reviewers → `qc_independence_reason`
  returns `AF-EXEC-STAMP: no trusted REVIEWER stamp …`.

A test that passes on the new code and would fail on the old code is the proof that this
is a real behaviour change, not a no-op.

### 2.4 The acceptance sentence, other half

`test_verdict_in_its_own_file_leaves_the_report_stamp_passing`: after
`working/qc/human-review/representation_casting.json` is written, the graded report's
sha256 is unchanged and its keyed author+reviewer stamps still pass — the human verdict
never touches the graded report.

### 2.5 No regression — pre-existing baseline unchanged

| Test file | With this change | Baseline at `1a476d2cb` |
|---|---|---|
| `test_pres042_execution_stamps.py` | 15 passed, 1 failed | 15 passed, 1 failed |
| `test_qc_aggregate.py` | 16 passed, 3 failed | 16 passed, 3 failed |
| `test_defect5_routing_stamp_provider_identity.py` | 4 passed, 1 failed | 4 passed, 1 failed |
| `test_intake_provenance.py` | 6 passed | (unaffected) |
| `test_f19_requester_stamp.py` | 16 passed | (unaffected) |

Baseline was measured by stashing the three source files and re-running the same commands
on the same worktree. The failing test names are identical in both runs, so the failures
are pre-existing on `pd/fl35-sealed-record` and not caused by PD-306.

Note: every pre-PD-306 test fixture writes hashless stamp files, so they exercise the
legacy branch and keep passing — which is precisely the intended legacy contract, and it
is visible in the `stamp.legacy:` lines the suite emits.

---

## 3. Files touched

| File | Owner |
|---|---|
| `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/execution_stamp.py` | PD-306 (lane-owned) |
| `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pd_runfacts_306_execution_stamp.py` | PD-306 (lane-owned)`test_pd_runfacts_*` glob) |
| `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/state.py` | **FOREIGN — PD-906** |
| `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/phases.py` | **FOREIGN — PD-906** |
| `evidence/PD-306/BUILD-REPORT.md` | this report |

No other lane's files, folders, branches, PRs or worktrees were read or written.
Nothing was merged, rebased, force-pushed, or pushed to `main`.
