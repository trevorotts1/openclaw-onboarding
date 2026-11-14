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

## 9. Third pass — A2 retargeted to the PD-018b contract (contradiction, not a broken repair)

This pass fixes the one red row named by the re-check: **A2**. The branch itself was structurally sound
(merges clean with `main` and the sibling; A1/A3 held; D-10 hold intact). A2 was red because two accepted
units assert opposite things about one line.

### 9.1 The two contracts, quoted

**PD-048b, row A2** (SPEC/`01-BUILD-SPEC.md`, unit PD-048b):

> (A2) control: with the heal path un-patched (test the old function directly) the same fixture produces the
> "Regenerating" message — proving the test can fail.

**PD-018b** (same spec, LANE L5; a stated dependency of PD-048b — ledger `depends_on`:
`PD-048a, PD-018b, RD-04, RD-05`):

> Replace the three close-failure messages with that same sentence and keep the technical text in the event
> log only. … (3) Add a guard in `to_requester`: if the outgoing `message` contains a manifest phase id or a
> token that starts with `AF-`, replace the message with `Your presentation is moving ahead: <client_label>.`
> and record an event `report.sanitized` (build the id list from the loaded manifest, not from a pattern).

PD-018b's acceptance:

> a visible phase sends text containing its `client_label` and none of the fixture phase ids; a deliberately
> bad message containing a phase id is sanitized and the event is recorded.

The sibling landed the change in `414c715ab` — *PD-018b: fill client_label and keep internal text off the
client* — which rewrote exactly this hunk in `heal.rung2_regenerate`:

    -        engine.report.to_requester(
    -            "blocked",
    +        # PD-018b: an artifact check that failed and is being regenerated is the
    +        # engine's own internal repair work -- the client hears nothing until a
    +        # step finishes or a real pause. The line goes to the event log.
    +        engine.report.event(
    +            "report.internal",
                 f"{phase.id} artifact check failed ({deficiency}). "
    -            f"Regenerating -- attempt {attempt} of {HEAL_CAP_REGENERATE}.",
    -            phase_id=phase.id, reason=f"rung2:{deficiency}")
    +            f"Regenerating -- attempt {attempt} of {HEAL_CAP_REGENERATE}.")

### 9.2 Which contract is authoritative, and why

**PD-018b is authoritative.** PD-048b declares PD-018b a dependency, so PD-048b must be satisfied *inside*
PD-018b's client-safety contract, not beside it. PD-018b is also later-proved and covered by its own
discriminating test (`tests/test_pd_engine_client_copy.py::TestScriptRetryIsInternal` asserts the client
transport received nothing and the line is in the event log as `report.internal`). PD-048b's A2 never says
the text must reach the *client*; its purpose is a negative control proving A1's forbidden strings really
exist on the old heal path, so that A1 is not vacuous. Under PD-018b the old heal path still produces the
line — at the boundary PD-018b defines: the event log. Retargeting A2 to that boundary keeps the control's
full strength: the row still fails if `rung2_regenerate` stops emitting "Regenerating", or if the
internal-only contract regresses (technical text reaching the client), or if the re-run stops returning
`EXIT_OK`. It is not weakened, skipped, renamed or xfailed, and no production code was changed.

### 9.3 The minimum change

One test file: `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pd_engine_048b_waiting_install.py`.

- A2 now reads `eng.state["events"]` for `kind == "report.internal"` and asserts the same four strings
  ("Regenerating", "P-U-GHL-SALES artifact check failed", "AF-U-", "artifact check failed").
- It additionally asserts none of those strings reach the client transport, and sends a `transport control`
  message through the same stub so "client received nothing" is a proved absence, not a dead pipe.
- Module docstring's A2 row gains one sentence naming the PD-018b boundary.

No other unit, test or production file touched. Code diff: that one test file, plus this report.

### 9.4 Proof — rows, mutation, wider suite

Rows at the code head `bf51fa4becca003f75dc0732971076891782a06a`:

    $ python3 -m pytest tests/test_pd_engine_048b_waiting_install.py -v
    TestA1WaitingIsAPause::test_install_waiting_leaves_no_failure_text_and_siblings_run PASSED
    TestA1WaitingIsAPause::test_complete_receipt_is_not_a_wait PASSED
    TestA2ControlOldHealPath::test_old_heal_path_still_says_regenerating PASSED
    TestA3ResumeFinishes::test_complete_receipt_then_resume_finishes_the_phase PASSED
    4 passed

Mutation that turns A2 RED (production `heal.py`, restored immediately by `git checkout --`):

    - "Regenerating -- attempt {attempt} of {HEAL_CAP_REGENERATE}."
    + "Retrying -- attempt {attempt} of {HEAL_CAP_REGENERATE}."

    $ python3 -m pytest tests/test_pd_engine_048b_waiting_install.py::TestA2ControlOldHealPath -q
    FAILED tests/test_pd_engine_048b_waiting_install.py::TestA2ControlOldHealPath::test_old_heal_path_still_says_regenerating
    1 failed in 5.21s        (pytest rc=1)

Restored: `4 passed in 5.83s` (rc=0). `git status` after restore: only the A2 test file modified.

Wider affected suite (the report/phases tests that carry the PD-018b contract):

    BASE  ebf5c769a  tests/test_engine_client_report.py only file present of the set  28 passed
    HEAD  bf51fa4be  same six-file set + PD-048b rows                     42 passed, 13 failed

The 13 head failures are **pre-existing at `23afd26e3`** and untouched by this diff (my change is confined
to `test_pd_engine_048b_waiting_install.py`):

- `tests/test_engine_client_report.py` — 10 failures. Its fixture expects 16 rendered client-visible
  phases; `universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json` (v75) on this tree has
  `client_visible` on 0 of 56 phases and `client_label` on 0. PD-018b now counts only labelled visible
  phases, so `_client_phase_index` returns 0. This needs the manifest-label work (PD-018a's lane) in the
  tree; it is not PD-048b's row and not this repair's scope.
- `tests/test_pd_engine_client_copy.py` — 3 failures, already named in section 8 as the sibling's own
  pre-existing `TestEveryTemplateFillsItsOwnLabel` failures.

No repo-wide suite, no CI, no container was run — same limitation as section 8.
