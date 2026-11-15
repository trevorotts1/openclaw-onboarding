# PD-316b — BUILD REPORT

- **Unit:** PD-316b, "The upload closeout skip is an owner approval" (findings PD-316, PD-066; Moderate; acceptance rows A1, A2, A3)
- **Repository:** trevorotts1/openclaw-onboarding
- **Branch ordered by the gate row:** `pd/fl33-media-upload--hold-d12-d15-d33`
- **Branch proven ABSENT on origin before editing**, while the control resolved:
  ```
  $ git ls-remote --heads origin pd/fl33-media-upload--hold-d12-d15-d33
  (no output) rc=0
  $ git ls-remote --heads origin refs/heads/main
  ebf5c769a2ad5b2582bf2256588095cbef20cfac	refs/heads/main     rc=0
  ```
- **Base used (the spec's dependency branch), full 40 chars:** `77edffce5fcf5a19f0c8a243eaa939e307d346e0` = `origin/pd/fl33-media-upload--hold-d12`, the ACCEPTED head of PD-316.
- **Worktree used:** `…/loop-control/pd-fix/tmp/PD-316b/work.i7gNTW/repo` (git worktree, detached at `77edffce5`). The lane worktrees `…/worktrees/onboarding/FL33--hold-d12` and `…/FL33--hold-d12-d15-d33` were not edited and were clean before and after.
- **Commit (code + tests):** `00a75df45cc9c2d6d76866bac629a232d00ff1d6`
- **Remote head after push:** `00a75df45cc9c2d6d76866bac629a232d00ff1d6` (full 40 characters, below)
- **Status:** BUILT and PROVEN. Held by decisions D-15, D-33, D-12 (staged, not merged).

## Ladder discrepancy — put on the record

1. **The spec's lane branch `pd/fl33-media-upload` does not exist on origin.** `git ls-remote --heads origin 'refs/heads/pd/fl33*'` lists exactly one FL33 head: `refs/heads/pd/fl33-media-upload--hold-d12`. The lane table (`LANE FL33 — the media uploader`, `01-BUILD-SPEC.md`) names `pd/fl33-media-upload`, so the live lane head is its `--hold-d12` variant. Built on that.
2. **The unit's own branch name was absent** (proof above), so it was created from that dependency head, as the task sheet directs.
3. **PD-305 is a cross-lane dependency, not a base.** Its branch `pd/fl34-approvals--hold-d33` is at `feff12b20c9d36111bd605d08edf88434800642a` (phase IN_BATCH, QC PASS in the ledger). Both that branch and my FL33 base already define `approvals.verify_owner_skip_approvals(run_dir, gate)` with the same signature; the FL34 revision is the richer one (task-id disagreement tracking, used-approval record) and takes over at merge. My code calls the name, not a copy of the body, so either revision serves it.

## Spec quoted (`### PD-316b` of `01-BUILD-SPEC.md`)

> - **Change (`ghl_media_push.py`, `_valid_owner_skip`, lines 1075-1099):** stop accepting four typed fields. For each alias the function accepts today, call `approvals.verify_owner_skip_approvals` and open the upload closeout gate only for a record it verifies.
> - **Acceptance:** (A1) a typed four-field token with no owner message id: the gate fails with a reason naming the missing approval. (A2) a record the stub oracle verifies: the gate opens. (A3) an oracle that cannot run: the gate fails with "owner approvals cannot be checked on this machine".

Lane row (`02-SWARM-PLAN.md`): `| FL33 | PD-316 [D-12], PD-316b [D-15, D-33, D-12] |`

## Files changed

1. `…/presentations/scripts/ghl_media_push.py` (lane-owned)
   - `_valid_owner_skip` now returns `(record, reasons)`. It no longer reads the four typed fields at all: for every alias in the `_GATE_ALIASES` set it calls `approvals.verify_owner_skip_approvals(run_dir, alias)` (lazy import, matching `run_signature_deck.py` / `build_deck.py` / `deck-intake-driver.py`) and opens the gate only for a record that verifies. An `ApprovalError` naming the record becomes a gate reason (fail-closed); an UNDETERMINED oracle or an approval module that cannot be imported becomes `owner approvals cannot be checked on this machine`.
   - `gate_ghl_media_complete` consumes the pair: verified record → `(True, [])`; failure reasons → `(False, reasons)`; no record naming this gate → the gate's existing folder/slide/pptx checks speak as before.
   - Module docstring, the `has_ghl:false` reason text, and selftest case G updated to the verified-approval contract (the "four typed fields" prose would otherwise be a lie about the code). Case G now supplies `owner_msg_id` + `granted_at` and stubs the oracle for the length of the case.
2. `…/presentations/scripts/tests/test_pd_upload.py` (lane-owned) — three tests added, one per acceptance row.
3. `…/presentations/scripts/tests/test_upload_gate.py` (**NOT lane-owned — named overlap, see below**) — `test_valid_owner_skip_authorizes` asserted the removed behaviour (four typed fields → PASS). It now supplies `owner_msg_id` + `granted_at` and stubs the oracle, keeping its intent ("a valid owner skip authorizes") true under the new contract.

### Overlap named

- No lane in `01-BUILD-SPEC.md` / `02-SWARM-PLAN.md` owns `tests/test_upload_gate.py` (`grep` of both files: no match). Its `test_valid_owner_skip_authorizes` encoded the exact defect this unit removes, so leaving it untouched would publish a red suite that asserts the forgery path is legitimate. One test body changed; no other assertion in that file was touched, renamed or skipped.
- The lane worktree `…/worktrees/onboarding/FL33--hold-d12-d15-d33` already exists, holds this very branch, and sits at `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc` (clean). I did not edit or move it; I built detached in scratch and pushed to the branch ref. **A sibling builder must `git fetch` before using that worktree** — its local branch pointer is stale by design.

## Acceptance rows — one test per row, real output

Command, in `…/presentations/scripts` at HEAD:

```
$ python3 -m pytest tests/test_pd_upload.py -v -k "typed or verified or oracle_unavailable"
tests/test_pd_upload.py::test_typed_four_field_token_without_owner_msg_id_fails PASSED [ 33%]
tests/test_pd_upload.py::test_verified_owner_approval_opens_the_closeout_gate PASSED [ 66%]
tests/test_pd_upload.py::test_owner_oracle_unavailable_fails_the_gate PASSED [100%]
=========================== 3 passed, 6 deselected in 0.05s ===========================
```

| Row | Test | What the gate actually returned at HEAD |
|---|---|---|
| **A1** typed four-field token, no owner message id → gate fails, reason names the missing approval | `tests/test_pd_upload.py::test_typed_four_field_token_without_owner_msg_id_fails` | `OK=False` — `"AF-DELIVERY-COMPLETE: owner skip for gate 'ghl_media_upload' is not a verified owner approval — AF-FORGED-APPROVAL: approval for gate 'ghl_media_upload' (approved_by 'operator') has NO owner_msg_id (owner_action=''). Every owner approval must carry a non-empty owner_msg_id that resolves to a real owner-authored message in Command Center task_activities …"` The oracle in this test WOULD verify `cc-msg-1`, so the failure is the missing id, not a dead oracle. |
| **A2** record the stub oracle verifies → gate opens | `tests/test_pd_upload.py::test_verified_owner_approval_opens_the_closeout_gate` | `OK=True`, `reasons == []` for a schema-valid record whose `owner_msg_id` the stubbed `_cc_board_oracle` returns in its frozenset. |
| **A3** oracle cannot run → gate fails with the exact sentence | `tests/test_pd_upload.py::test_owner_oracle_unavailable_fails_the_gate` | `OK=False` — `"AF-DELIVERY-COMPLETE: owner approvals cannot be checked on this machine"` (board oracle `None`, gateway oracle `None`, no gateway env). |

The updated old-contract test also passes at HEAD:

```
$ python3 -m pytest tests/test_upload_gate.py -v -k "owner"
tests/test_upload_gate.py::test_valid_owner_skip_authorizes PASSED       [ 25%]
tests/test_upload_gate.py::test_owner_skip_missing_reason_fails PASSED   [ 50%]
tests/test_upload_gate.py::test_owner_skip_missing_approved_by_fails PASSED [ 75%]
tests/test_upload_gate.py::test_owner_skip_not_approved_fails PASSED     [100%]
=========================== 4 passed, 16 deselected in 0.04s ===========================
```

## Mutation — RED then GREEN (same test file both times)

**Mutation 1 — production file reverted to base `77edffce5`, tests at HEAD:**

```
$ python3 -m pytest tests/test_pd_upload.py -q -k "typed or verified or oracle_unavailable"
FAILED tests/test_pd_upload.py::test_typed_four_field_token_without_owner_msg_id_fails
FAILED tests/test_pd_upload.py::test_owner_oracle_unavailable_fails_the_gate
2 failed, 1 passed, 6 deselected in 0.06s
```

A1 and A3 RED because the base function accepts the four typed fields and returns `(True, [])`. A2 passes at base for the same reason — the defect accepts everything, so it cannot be a RED for A2; mutation 2 covers that side.

**Mutation 2 — verification short-circuited (`_valid_owner_skip` returns `(None, [])` before the approvals call):**

```
$ python3 -m pytest tests/test_pd_upload.py -q -k "typed or verified or oracle_unavailable"
FAILED tests/test_pd_upload.py::test_typed_four_field_token_without_owner_msg_id_fails
FAILED tests/test_pd_upload.py::test_verified_owner_approval_opens_the_closeout_gate
FAILED tests/test_pd_upload.py::test_owner_oracle_unavailable_fails_the_gate
3 failed, 6 deselected in 0.06s
```

**GREEN — restored HEAD file (byte-identical to the committed version, `cmp` IDENTICAL):** `3 passed`.

## Wider suite — base and head with counts

Nine affected files (every test module that imports `ghl_media_push`, plus the approvals consumer path): `test_pd_upload.py test_upload_gate.py test_ghl_media_list.py test_pres026_media_resume.py test_gates.py test_fix36_doc_code_reconcile.py test_l11_webinar_executor_no_recursion.py test_producers.py test_executor_dispatch.py`. `tests/test_pd_approvals.py` does not exist at this base (FL34 lane file, not merged) — named, not skipped silently.

```
BASE 77edffce5, five consecutive runs:   139 passed, 139 passed, 139 passed, 139 passed, 139 passed
HEAD,          five consecutive runs:   142 passed, 142 passed, 142 passed, 142 passed, 142 passed
```

`142 = 139 + 3` new rows. No test was weakened, renamed, skipped or xfailed.

**Honest flake note:** during an earlier full-suite run at HEAD (before `test_upload_gate.py` was updated) `tests/test_pres026_media_resume.py::test_two_workers_same_run_single_operation` failed once with duplicate POSTs under two threads; it passed 3/3 isolated runs at HEAD and 3/3 at BASE, and both trees ran 5/5 clean afterwards. It is the test the lane's own reading contradiction already flags (`RD-19: media-resume test test_pres026 breaks`), and this unit does not touch that path. Unproved either way; reported rather than explained away.

## Module self-test (not wired into pytest)

`python3 ghl_media_push.py --selftest` is RED at BASE and at HEAD, with the same three pre-existing cases:

```
BASE 77edffce5: V over-cap-52MB (x2 lines), W no-receipt, X under-cap-10MB
HEAD:           V over-cap-52MB (x2 lines), W no-receipt, X under-cap-10MB
```

Before case G was updated, HEAD additionally failed `G owner-skip` (the fixture used the removed four-field token). Case G now exercises a verified record and no longer fails; the count of failing cases is identical to base.

## Hunk attribution (merge-base → HEAD)

`git merge-base origin/main HEAD` = `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc`. Prior hunks on the branch (PD-215 `build_infographic.py` + its test, PD-301 `ghl_media_push.py` + `test_pd_upload.py`, PD-316 `ghl_media_push.py` + `test_pd_upload.py`, `evidence/PD-316/`). My commit touches only:

- `…/scripts/ghl_media_push.py`
- `…/scripts/tests/test_pd_upload.py`
- `…/scripts/tests/test_upload_gate.py`
- `evidence/PD-316b/BUILD-REPORT.md`

## Remote-head proof

```
$ git push origin HEAD:refs/heads/pd/fl33-media-upload--hold-d12-d15-d33
 * [new branch]          HEAD -> pd/fl33-media-upload--hold-d12-d15-d33

$ git ls-remote --heads origin pd/fl33-media-upload--hold-d12-d15-d33
00a75df45cc9c2d6d76866bac629a232d00ff1d6	refs/heads/pd/fl33-media-upload--hold-d12-d15-d33
```

Full 40 characters, equal to the local code+tests HEAD at push time:
`00a75df45cc9c2d6d76866bac629a232d00ff1d6`. Fast-forward by construction (the branch did not exist); no rebase, no force-push. This report lands as the next commit on the same branch.

## Anything unproved / notes for the QC judge

- **Live action:** none. Every oracle is a stub; no GHL call, no Command Center call, no gateway call.
- **A3 wording is matched on `"UNDETERMINED"` inside `approvals.ApprovalError`.** That is the FL34 module's own undetermined sentence on both revisions; if PD-305 rewrites that message the match must move with it. Named as the one coupling I could not remove without touching a file another lane owns.
- **The four `test_upload_gate.py` skip tests that survive** (`missing_reason`, `missing_approved_by`, `not_approved`) now fail for schema reasons before any oracle call; they still prove what their names say (an incomplete token authorizes nothing), which is a subset of the new rule.
