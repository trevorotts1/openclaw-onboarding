# PD-918 — BUILD REPORT

- Unit: PD-918 (added unit), lane FL16
- Branch: `pd/fl16-page-installer`
- Worktree: `/Volumes/mac mini m4/swarm-contract/pd-fix/worktrees/onboarding/FL16`
- Code commit: `97f99ab84e826f4939e0e2505239eb378a840a0f`

## Foreign hunks (for merge reconciliation)

Carried verbatim from PD-910, accepted at `021f74e24` on `pd/fl17-phase-checks`
(code commit `08a6cdcd7`, "PD-910: the unbound sentinel is not a placeholder and
a note is not a failure"). That commit is **not** an ancestor of this branch —
`git merge-base --is-ancestor 021f74e24 HEAD` exits `1`, merge-base is
`1a476d2c` — so PD-048a row A7 cannot see it. Both hunks are therefore declared
**foreign** here: when `pd/fl16-page-installer` and `pd/fl17-phase-checks` meet,
these two hunks are the same change and reconcile to one copy.

File: `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/phase_verifiers.py`

1. `_pu_check_receipt_identity` (this branch line 4349): the placeholder-token
   rule exempts the installer's documented unbound sentinel exactly — added
   `loc_l != "unbound-test" and`, so `"test"` no longer swallows it while
   `placeholder` / `example` / `changeme` / `todo` and any other `test` value
   still fail.
2. `_make_pu_verifier` (this branch line 4656): reasons split into `NOTE:`
   notes and real failures. Failures still return `False` (prefixed
   `AF-U-<phase>`, notes appended); notes alone return `True` **with** the
   notes, so a skipped GHL readback stays distinguishable from a verified pass.

Semantic identity checked against the source: snippet comparison of both hunk
regions against `git show 021f74e24:<file>` → `MATCH` / `MATCH`.
`python3 -m py_compile` on the result → OK. Diff is exactly those two hunks,
`+16 −4`, one file.

## Proof — installer's own probe, before and after

`pd048_ghl_install_probe.py` (`/Volumes/mac mini m4/swarm-contract/fable-reviews-2026-11-11/03-presentation-department/scripts/pd048_ghl_install_probe.py`),
run against this worktree's `.../presentations/scripts`, scratch
`/Volumes/mac mini m4/swarm-contract/pd-fix/scratchpads/PD-918`,
`TMPDIR=/Volumes/mac mini m4/swarm-contract/pd-fix/tmp`.

| case | old file (HEAD 164b893b3) | after carry |
|---|---|---|
| `completed-memory-adapter` | `verifier_ok false` | **`verifier_ok true`, reasons `[]`** |
| `declined-control` | `verifier_ok true` | **`verifier_ok true`** |

Old file, completed case — false for exactly the two carried defects:

```
AF-U-P-U-GHL-SALES: ghl_build_receipt.json: location_id 'unbound-test' reads as a placeholder -- a made-up location is a fabrication, not a push record
AF-U-P-U-GHL-SALES: NOTE: GHL readback skipped (env/import: GHL LOCATION PIT not found — ...)
```

After carry, completed case:

```
verifier_ok: true
verifier_reasons: []
```

Declined control both runs, unchanged (`verifier_ok true`,
`NOTE: P-U-GHL-SALES waived -- client declined ...`) — the carry does not make a
declined run pass by weakening the check.

Still-failing side is intact: the `elected` case (receipt with no remote artifact
id) stays `verifier_ok false`, and a skipped readback still appears as a bare
`NOTE:` line without the `AF-U-` failure prefix — visible, not mistaken for a
verified pass.

## Scope

Touched only `phase_verifiers.py`. No test file carried (unit names two hunks
only). No merge, no push to main, no rebase, no client box, no live system, no
other branch or worktree.
