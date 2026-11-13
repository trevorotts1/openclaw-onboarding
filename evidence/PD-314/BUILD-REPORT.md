# PD-314 — One skip rule for curation and self-audit — BUILD REPORT

Unit: **PD-314** · Lane **FL32** · Repo `trevorotts1/openclaw-onboarding`
Branch: `pd/fl32-curation` · Head at code commit: `00544f04f0cf6baede04db9bd1633e25dbd3b5f7`

## 1. Spec rows, quoted

`01-BUILD-SPEC.md`, lane table (lines 4443-4449):

> ## LANE FL32 — close-time curation and the self-audit
>
> - **Repository:** trevorotts1/openclaw-onboarding · **Branch:** `pd/fl32-curation` · **Units in order:** PD-303, PD-314
> - **Files this lane owns (no other lane may edit them):**
>   - `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/curate.py`
>   - `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/self_audit.py`
>   - `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pd_curate.py`

`01-BUILD-SPEC.md`, unit row (lines 4477-4501):

> ### PD-314 — One skip rule for curation and self-audit
>
> | Field | Value |
> |---|---|
> | Findings | PD-314 |
> | Severity | Moderate |
> | Builder | deepseek-chain — difficulty mechanical: two small functions, fully specified |
> | Quality control (finds and fixes) | suggested opus-chain at thinking level high (data-loss risk); re-check of any repair by a FRESH opus-chain agent at high or above; the orchestrator decides |
> | Critical first | no |
> | Lane and repository | FL32 · trevorotts1/openclaw-onboarding |
> | Wave | 3 |
> | Depends on (must be ACCEPTED, that is QC-passed, first) | PD-303 |
> | Held by decision | D-12 (built and staged, not merged until yes) |
> | Existing tests it breaks and must update | none known in advance; the lane's reading units and the test census name the rest (rule 15) |
> | Live-action flag | none: files and stubbed tests only |
> | Acceptance rows the checker must run | A1 |
>
> **Read first — consolidation amendments (binding; they override the carried-over text below wherever the two differ):**
>
> Built on top of PD-303's branch, so it carries the same hold.
>
> **Carried-over unit text (from `PASS6-LAST.md`, section PD-314; ids, decisions and lanes already converted to final):**
>
> - **Change:** `curate._read_owner_skip_approvals`: read `run_dir/waivers.json` through `waivers.load_waivers` and accept a skip only for a record that `validate_waiver` accepts; drop the unvalidated `process_manifest` branch. Write the skipped keys to `working/checkpoints/curation_manifest.json`. `self_audit.audit_all`: read that list and report those keys as `SKIPPED (owner)`, not failed.
> - **Acceptance:** a validated waiver for one key → curation and self-audit both close; a typed string in `process_manifest.json` → no skip.

`02-SWARM-PLAN.md` rows naming this unit:

> 214: | FL32 | PD-314 [D-12] |          (wave table — "Wave 3: every other Moderate unit")
> 263: | FL32 | openclaw-onboarding | `pd/fl32-curation` | close-time curation and the self-audit | PD-303 ★ [D-12], PD-314 [D-12] |

`00-FINDINGS-RANKED.md` finding text (line 729):

> ### PD-314 — Self-audit and curation disagree about skips, and curation reads the wrong waiver file
> - **Evidence:** `curate.py` 244-277, 432-456; `waivers.py` 42.

## 2. Branch-state discrepancy (STEP 1)

The ledger row for PD-314 names branch `pd/fl32-curation--hold-d12`; the lane table in
`01-BUILD-SPEC.md` names `pd/fl32-curation`. **Neither existed on the remote.** Proof, run in
`/Volumes/mac mini m4/swarm-contract/pd-fix/clones/onboarding`:

```
$ git ls-remote --heads origin refs/heads/main
ebf5c769a2ad5b2582bf2256588095cbef20cfac	refs/heads/main            (control resolves)

$ git ls-remote --heads origin pd/fl32-curation--hold-d12
(no output, rc=0)                                                      (ledger branch ABSENT)

$ git ls-remote --heads origin pd/fl32-curation
(no output, rc=0)                                                      (lane-table branch ABSENT)
```

Base used: **`911a3f22bd21529b634d48072a075b92c98f6d15`** — the PD-303 ACCEPTED head
(`ledger.json` → PD-303 `phase: ACCEPTED`, `qc.head` and `qc.remote_head` both that SHA, QC
receipt `qc/PD-303.f43c602a...json`). This is the lane-table branch name created at PD-303's
accepted head rather than at `origin/main`, because the unit row says "Built on top of PD-303's
branch" and the acceptance needs PD-303's declared-path resolver in `curate.py`. Creating it from
`origin/main` would have built PD-314 against code the spec says it does not run on. The branch
was created new (`git worktree add -B pd/fl32-curation <scratch> 911a3f2...`) and pushed as a new
remote branch; nothing was forced and nothing on `main` was touched.

PD-303 itself was **not** rebuilt — it is already ACCEPTED at that SHA.

## 3. What changed

| File | +/− |
|---|---|
| `.../scripts/presentation_job/curate.py` | +38 / −27 |
| `.../scripts/self_audit.py` | +43 / −2 |
| `.../scripts/tests/test_pd_curate.py` | +135 / −1 |

All three paths are in this lane's owned set; no file outside it was touched.

`curate._read_owner_skip_approvals` now:

* reads `run_dir/waivers.json` through `waivers.load_waivers` (the file `waivers.py:42` reads — the
  old code read `working/waivers.json` and never saw a real waiver);
* accepts a key only when the record passes `waivers.validate_waiver` (client quote must be a real
  substring of the recorded intake value, `captured_at` present, owner-claimed records go through
  the approvals oracle);
* has **no** `working/checkpoints/process_manifest.json` branch — the engine writes that ledger, so
  a typed string there is a self-mint;
* names the skipped key from the record's `deliverable` field, falling back to `rule`;
* writes `skipped_keys` into `working/checkpoints/curation_manifest.json`.

`self_audit.audit_all` reads `working/checkpoints/curation_manifest.json` (run root resolved as the
parent of the flat `deliverables/` folder), reports those keys as `SKIPPED (owner)`, excludes them
from `missing`, returns `skipped`, and appends the skip list to the summary. `format_line` now prints
the reason for a skipped row too. Absent/unreadable manifest → no skips (fail-closed).

## 4. Tests, by acceptance row, with real output

Acceptance row **A1** has two clauses; each has its own test id.

```
$ python3 -m pytest tests/test_pd_curate.py::test_validated_waiver_skips_one_key_in_curation_and_self_audit -q
.                                                                        [100%]
1 passed in 0.14s

$ python3 -m pytest tests/test_pd_curate.py::test_typed_string_in_process_manifest_is_not_a_skip -q
.                                                                        [100%]
1 passed in 0.06s
```

Whole unit file at head:

```
$ python3 -m pytest tests/test_pd_curate.py -q
..............                                                           [100%]
14 passed in 0.35s
```

Five new tests (A1 first clause, A1 second clause, forged quote rejected, waiver in
`working/waivers.json` not read, no-manifest means no skips) plus PD-303's nine.

### Wider affected suite — base and head, both counts

Affected set: the seven test files that exercise the changed call paths —
`test_pd_curate.py`, `test_fix103_deck_size_floors.py`, `test_waivers.py`, `test_gates.py`,
`test_upload_gate.py`, `test_deliverables_single_source.py`,
`test_pd168b_infographic_skip_not_a_deadlock.py`.

```
BASE 911a3f22b:  1 failed, 148 passed in 2.20s
HEAD 00544f04f:  1 failed, 153 passed in 3.33s
```

Same single failure on both sides — proven pre-existing, not asserted:

```
tests/test_fix103_deck_size_floors.py:295: AssertionError
    assert b["floor"] == -(-b["max"] * 80 // 100)
E   assert 19000 == -((-20000 * 80) // 100)      == 16000
FAILED tests/test_fix103_deck_size_floors.py::test_prompt_floor_untouched
```

`build_deck.length_budget()` arithmetic, untouched by this unit; identical assertion at base.

The **whole** `tests/` directory was attempted at head and **timed out** at 73 % after 900 s
(`rc=124`), so no full-suite count exists for either side.

## 5. Mutation proof

Script: `mut.py` (scratch). Each half of the change is neutralised, the unit file re-run, then the
file restored and its SHA-256 compared to the pre-mutation hash.

```
BASE {'curate.py': 'a1f90e81f1d81499', 'self_audit.py': '9f384877e9dc1489'}
GREEN head: rc=0 :: 14 passed in 0.48s
RED  M1 curate: skips never granted (early return set()): rc=1 ::
     FAILED tests/test_pd_curate.py::test_validated_waiver_skips_one_key_in_curation_and_self_audit
     1 failed, 13 passed in 0.28s
restored curate.py sha_match=True
RED  M2 curate: validation neutralised (any record approves): rc=1 ::
     FAILED tests/test_pd_curate.py::test_unvalidated_waiver_record_is_not_a_skip
     1 failed, 13 passed in 0.29s
restored curate.py sha_match=True
RED  M3 self_audit: skipped keys never read: rc=1 ::
     FAILED tests/test_pd_curate.py::test_validated_waiver_skips_one_key_in_curation_and_self_audit
     1 failed, 13 passed in 0.23s
restored self_audit.py sha_match=True
GREEN restored: rc=0 :: 14 passed in 0.24s
FINAL_SHA_MATCH {'curate.py': True, 'self_audit.py': True}
```

## 6. Hunk attribution

Merge-base of `origin/main` and this branch: **`1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc`**.

Commits on the pushed branch that are not on `main`, with the unit each belongs to:

| Commit | Unit | Files |
|---|---|---|
| `f8a628fa7` | PD-215 | `build_infographic.py` |
| `aada0187b` | PD-215 | `tests/test_pd_infographic.py` |
| `2988932a6` | PD-301 | `ghl_media_push.py`, `tests/test_pd_upload.py` |
| `911a3f22b` | **PD-303** | `presentation_job/curate.py`, `self_audit.py`, `tests/test_pd_curate.py` |
| `00544f04f` | **PD-314** | `presentation_job/curate.py`, `self_audit.py`, `tests/test_pd_curate.py` |

Only the two FL32 commits touch this unit's files. The PD-215 and PD-301 commits are ancestry
carried in through PD-303's accepted head (its branch sat on the `pd/fl29-infographic` tip); this
unit neither authored nor modified them.

## 7. Remote-head proof

```
$ git rev-parse HEAD
00544f04f0cf6baede04db9bd1633e25dbd3b5f7          (pre-push head)

$ git push origin HEAD:refs/heads/pd/fl32-curation
 * [new branch]          HEAD -> pd/fl32-curation

$ git ls-remote --heads origin pd/fl32-curation
00544f04f0cf6baede04db9bd1633e25dbd3b5f7	refs/heads/pd/fl32-curation

$ git ls-remote --heads origin refs/heads/main
ebf5c769a2ad5b2582bf2256588095cbef20cfac	refs/heads/main
```

Local HEAD == remote branch head, 40 characters each. Fast-forward/new-branch only: no rebase, no
force-push, `main` untouched.

## 8. Unproved / honest gaps

1. **The waiver record's `deliverable` field is new.** `waivers.validate_waiver` requires
   `rule ∈ GATE_KEYS ("script", "teleprompter", "prompt_floor", "ghl_upload", "qc")`, so a record
   whose `rule` is a deliverable key is rejected by the validator and can never authorise a skip.
   Nothing in the tree writes `waivers.json` (the operator authors it), so no existing record shape
   was available to copy. I therefore accept the key from an explicit `deliverable` field on a
   record that `validate_waiver` accepts, with `rule` as a fallback for a future vocabulary that
   names keys directly. `waivers.py` was not touched — it is not in this lane's owned files. If the
   waiver schema changes (FL26 / PD-317b own client waivers), this field must be reconciled there.
2. **No real run's `waivers.json` was observed** — no run dir was read, so the field name is
   unproven against production data.
3. **Whole `tests/` suite has no base/head counts**: the head run timed out at 73 % (rc=124); only
   the seven-file affected set was compared.
4. **No end-to-end `Engine.close()` run.** The unit is proved at function level (`curate.curate`,
   `self_audit.audit_all`); `phases.py` close() was read, not executed.
5. **PD-303 was not rebuilt or re-verified**; its accepted head `911a3f2` is taken as given per the
   ledger QC receipt. This unit's base is that SHA, so its behaviour inherits PD-303's.
6. **D-12 hold stands.** This branch is staged, not merged.
