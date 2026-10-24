# manifest/ CHANGELOG

Module version lives in `VERSION` and in `monthly_manifest.VERSION`. This tree is
not a numbered skill folder: it has no `skill-version.txt` and is outside the
`[0-9]*` content-hash gate documented in `VERSION-ARCHITECTURE.md`, so the
module version is the local version signal.

## 1.0.0 — 2026-10-24 (PBB-116 / T-23)

Added the joined monthly approval manifest lifecycle, which the accepted
contract layer does not carry:

- `approve()` joins a DRAFT 30-day campaign into one approved revision covering
  every placement, and refuses zero placements, duplicate ids, a window that is
  not 30 days, a placement slot outside the window, a blank approver or time,
  and any placement that is not DRAFT.
- `amend()` changes one placement's approved terms and invalidates that
  placement only (`PARTIAL_INVALIDATED`); the campaign `revision` deliberately
  does not move, so unrelated approved placements keep dispatching.
- `reapprove()` returns one amended placement to APPROVED without a new campaign.
- `next_cycle()` opens the next 30-day cycle as a fresh DRAFT at a new revision.
- `check_revision()` enforces that a new approval advances its revision and never
  repeats or rolls back a trailing counter.
- `terms_errors()` refuses a blank or invisible-only approved term (whitespace,
  U+200B, U+FEFF) and a placement scheduled outside the joined window.

Dispatch binding is not re-implemented. `APPROVAL_TERMS` is imported from the
accepted T-08 guard (`38-conversational-ai-system/tools/pb_contracts.py:
PLACEMENT_BOUND_FIELDS`), and the module hands its manifests to that guard's
`approval_errors` path. Tests: `tests/test_monthly_manifest.py`, 43 cases.
