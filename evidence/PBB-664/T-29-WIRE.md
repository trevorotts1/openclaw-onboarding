# PBB-664 T-29 — human handoff fence wired into the reminder machine

Rebuild lane PBB-1704. Branch `pb/PBB-1704-t29-handoff-fence`, based on
`origin/main` 8cb74925ad94c05ce9eb639e7554d02fcd780e20.

## What main was missing

`git diff c994359d 94d581f45 --name-status` (the audited tip) touches three
files. Line-for-line against the live `origin/main` blobs:

| file | added | already on main | absent (the work) |
|---|---|---|---|
| `shared-utils/reminders/reminder_state_machine.py` | 53 | 4 | 49 |
| `evidence/PBB-664/T-29-WIRE.md` | 292 | 0 | 292 (replaced by this file) |
| `.github/workflows/qc-static.yml` | 20 | 9 | 11 — NOT BUILT (shared CI file) |

`shared-utils/handoff/handoff.py` (HandoffStore, HandoffError, `gate_decision`)
is already on main. Only the wiring was absent.

## What this branch builds

1. `handoff` resolves from this package: `_HANDOFF_TOOLS` is put on `sys.path`
   before the upstream import block, so `from handoff import ...` works both as
   a module and as `python3 -I reminder_state_machine.py`.
2. `ReminderStateMachine.handoffs` — a lazy `HandoffStore` over the same tenant
   identity database (one database stays one tenant boundary).
3. `ReminderStateMachine._gate_evaluator()` — the T-18 consent evaluator with
   the T-29 handoff fence in front. Both must ALLOW. An unverifiable contact
   (`HandoffError`) fails closed as SUPPRESSED, never sends on a guess.
4. Both dispatch sites (`send_reminder`, `dispatch_final`) now use it.

Difference from the audited patch: the wrapper carries the consent evaluator's
own `consent_guard` marker. Without it `outbound_gate.dispatch` skips its
point-of-use recheck (`if pre_send is None and
getattr(evaluator, "consent_guard", False)`), so a handoff opened between the
first verdict and the fenced insert would be missed. Proof: the
`test_handoff_opened_after_the_first_verdict_still_blocks` case.

## Checks (every exit code printed)

```
python3 -I -m py_compile shared-utils/reminders/reminder_state_machine.py   rc=0
python3 -I shared-utils/reminders/reminder_state_machine.py                 rc=0 (21 assertions)
python3 -I -m unittest discover -s shared-utils/reminders/tests ...         rc=0 (Ran 60, OK)
python3 -I -m unittest discover -s shared-utils/handoff/tests ...           rc=0 (Ran 50, OK)
python3 -I shared-utils/reminders/tests/test_reminder_handoff_fence.py      rc=0 (Ran 6, OK)
```

## The new test bites

`shared-utils/reminders/tests/test_reminder_handoff_fence.py` cannot pass on
the consent fence alone: it opens a handoff and then releases the T-18 fence
explicitly, so only the handoff gate can suppress.

```
subject broken (both sites back to make_gate_evaluator)        rc=1  FAILED (failures=3)
subject broken (consent_guard marker dropped)                  rc=1  FAILED (failures=1)
subject restored                                               rc=0  OK
```

## Not built

`.github/workflows/qc-static.yml` — a shared CI workflow. Its 11 absent lines
were not rebuilt from a feature branch.
