# PD-048b — repair report (batch-sibling ejection, D-10 HOLD)

Unit PD-048b · repo `trevorotts1/openclaw-onboarding` · branch `pd/fl05-engine-reporting--hold-d10` · PR 3350
Repaired by deepseek-chain repair worker, second pass. No rebase, no force-push, no test weakened, skipped,
renamed or xfailed.

## 0. Why this is a second repair

The first repair merged `origin/main` only and was ejected again. The batch engine ejects a pull request
against its **in-batch siblings**, not only against `main`. This pass clears both: `main` **and** the one
sibling on the same batch, `pd/fl05-engine-reporting` (#3179).

## 1. Branch heads at the start

    $ git ls-remote --heads origin pd/fl05-engine-reporting--hold-d10
    e2b1a311b4d90c5d236cdb1506825d39148a6057	refs/heads/pd/fl05-engine-reporting--hold-d10    (PRE)

    $ git rev-parse origin/main
    ebf5c769a2ad5b2582bf2256588095cbef20cfac                                         (matches required)

`origin/main` was **already an ancestor** of PRE (`git merge-base --is-ancestor origin/main PRE` → rc 0;
merge base = `ebf5c769…`). The first repair's merge commit `80ec9017e` is in PRE. So this pass had no `main`
work left to merge:

    $ git merge origin/main
    Already up to date.

`git merge-base origin/pd/fl05-engine-reporting PRE` = `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc`.

## 2. Sibling test BEFORE the repair — it conflicts

    $ git merge-tree --write-tree e2b1a311… origin/pd/fl05-engine-reporting
    5c12d35fd198728f8c96b1e601ef480cb2b0baa0
    100644 88a0316c66c4b8bebccbc7e355298c786ccc14f4 1  23-ai-workforce-blueprint/.../presentation_job/report.py
    100644 6f8aeedd69f3c8be6dc0921dc9e825dbf5b3facf 2  23-ai-workforce-blueprint/.../presentation_job/report.py
    100644 34d2501ace9cdc9d0117825fe968ead22263a711 3  23-ai-workforce-blueprint/.../presentation_job/report.py
    CONFLICT (content): Merge conflict in .../presentation_job/report.py
    exit code 1

Auto-merged without conflict: `heal.py`, `phases.py`, `__main__.py`, `state.py`, and 15 test files.
Blob roles: `88a0316c` = merge base, `6f8aeedd` = ours, `34d2501a` = sibling.

## 3. What was imported and why

    $ git merge origin/pd/fl05-engine-reporting     # one content conflict, report.py
    21 commits imported (PD-018b, PD-019, PD-031, PD-042, PD-045, PD-076, PD-206b, PD-313, PD-906, PD-907)

The sibling was imported **only because it conflicted**. Importing was required: a branch that collides with
a batch sibling is re-ejected no matter how clean it is against `main`.

## 4. Resolution of the two conflicting hunks (both intents kept)

Both sides were purely additive in the same two places in
`23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/report.py`.

Hunk 1 — `to_requester` signature/docstring (lines 231-244).

- Ours (PD-048b): added the client-facing `waiting` kind — a person-pause notice that ignores quiet hours
  and is never throttled away, counted under `sent["waiting"]`.
- Sibling (PD-206b): added `force: bool = False` — bypasses the throttle for a message already proven due
  exactly once.

Resolution keeps both: signature is `reason: Optional[str] = None, force: bool = False)` and the docstring
names all five kinds `{ack, progress, blocked, done, waiting}`, with ours' WAITING paragraph and the
sibling's PD-206b paragraph both intact.

Hunk 2 — `_throttle_decision` signature and first guard (lines 380-395).

- Ours: `if kind in ("ack", "done", "waiting")` with the comment that the 10-minute progress budget must
  never swallow the pause notice.
- Sibling: `force: bool = False` plus `if force: return True` (PD-206b "proven due once").

Resolution keeps both, sibling's `force` guard first, then the three-kind set with ours' comment.

`ast.parse` on the resolved file: AST_OK. No conflict markers remain anywhere in the tree.

Merge commit: `b9368e6111803434746a745ce04a8276abd4bc73`.

## 5. Sibling test AFTER the repair — clean

    $ git merge-tree --write-tree b9368e611… origin/pd/fl05-engine-reporting
    cfe330d9fc3c868cc0cb3a18735c24d3ba921204
    exit code 0            (no conflict lines)

This is clean partly by construction — the sibling head is now an ancestor of the repair head
(`git merge-base --is-ancestor origin/pd/fl05-engine-reporting HEAD` → rc 0). `origin/main` is an ancestor
too (rc 0). No other sibling is on this batch.

## 6. Unit acceptance rows, by test id, at the repaired head

`python3 -m pytest tests/test_pd_engine_048b_waiting_install.py -rA` (run from
`.../templates/role-library/presentations/scripts`), exit code 1:

- A1 `…::TestA1WaitingIsAPause::test_install_waiting_leaves_no_failure_text_and_siblings_run` **PASSED**
- A1 `…::TestA1WaitingIsAPause::test_complete_receipt_is_not_a_wait` **PASSED**
- A2 `…::TestA2ControlOldHealPath::test_old_heal_path_still_says_regenerating` **FAILED**
- A3 `…::TestA3ResumeFinishes::test_complete_receipt_then_resume_finishes_the_phase` **PASSED**

Same command at PRE (`e2b1a311…`, detached worktree): `4 passed`, exit 0 — so A2's failure is **not**
pre-existing on this branch; it appears only once the sibling is in the tree.

### A2 is red because the sibling deliberately forbids what A2 asserts

A2 is the control that keeps A1 honest: it calls `heal.rung2_regenerate` directly and asserts the legacy
internal line ("`P-U-GHL-SALES artifact check failed … Regenerating`") reaches the client verbatim.
The sibling changes exactly that, twice:

1. `414c715ab` **PD-018b: fill client_label and keep internal text off the client** — moves the retry line
   from `to_requester("blocked", …)` to `event("report.internal", …)`, so the client hears nothing, and
   fills `client_label`, which arms `_sanitize_for_client`.
2. `aa506ba7e` **PD-018b: honest rendered step count and discriminating client-copy tests** — pins the new
   behaviour in `tests/test_pd_engine_client_copy.py::TestScriptRetryIsInternal`, which asserts the client
   transport received nothing and that the line is in the event log as `report.internal`.

Probe run (throwaway worktree, not committed) that restored the old `to_requester("blocked", …)` next to the
sibling's event line, to prove which half breaks A2:

    report.internal: P-U-GHL-SALES artifact check failed (…). Regenerating -- attempt 1 of 2.
    report.sanitized: internal text withheld from the client (P-U-GHL-SALES): …
    report.blocked: Your presentation is moving ahead.
    AssertionError: assert 'Regenerating' in 'Your presentation is moving ahead.'

So even with the client dispatch restored, the sibling's sanitizer replaces the Phase-ID-bearing internal
text. A2 cannot pass while `#3179` is in the same tree — the two pull requests make opposite claims about one
line, and the sibling's claim is the newer, tested, client-safety one.

**I did not edit, weaken, skip, rename or xfail A2.** It is left red and named here, and no production code
was pulled back towards it (that would have deleted the sibling's side of the collision).

Also observed, and not caused by this merge: the sibling's own
`tests/test_pd_engine_client_copy.py` is already `3 failed, 1 passed` at its own head (`fbfc1cf39`) with the
same three `TestEveryTemplateFillsItsOwnLabel` failures (`P-CONVERTER has no client_label`). Its
`TestScriptRetryIsInternal` passes both at its head and at the merged head.

## 7. Ancestry and remote-head proof

    $ git merge-base --is-ancestor e2b1a311… <new head>        → rc 0   (no rewrite)
    $ git push origin HEAD:refs/heads/pd/fl05-engine-reporting--hold-d10
      e2b1a311b..b9368e611  HEAD -> pd/fl05-engine-reporting--hold-d10   (fast-forward, no '+')
    $ git ls-remote --heads origin pd/fl05-engine-reporting--hold-d10
      <40-char head>	refs/heads/pd/fl05-engine-reporting--hold-d10

The literal head of this report's commit is recorded in section 8 and re-proved after the push.

## 8. What I could not prove

- I could not make A2 green and keep the sibling's tested client-safety behaviour at the same time. One
  line cannot both send and not send. Options, for the owner, not taken here: (a) retarget A2's control to
  the transport boundary — dispatch the legacy text through `to_requester("blocked", …)` and assert the same
  three strings arrive, which preserves every assertion but changes what the control points at; or
  (b) sequence the two pull requests so `#3179` lands first and PD-048b's control is updated deliberately in
  its own commit. Both are test edits and neither is mine to make unasked.
- I ran only the unit's own acceptance file plus the sibling's `test_pd_engine_client_copy.py`; no repo-wide
  suite, no CI, no container run.
- `git merge-tree` proves the pair merges without textual conflict; it proves nothing about runtime
  behaviour of the pair.
- The batch engine's own ledger and ejection reason were not available to me beyond the task card.
