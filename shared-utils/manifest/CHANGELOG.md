# manifest/ CHANGELOG

Module version lives in `VERSION` and in `monthly_manifest.VERSION`. This tree is
not a numbered skill folder: it has no `skill-version.txt` and is outside the
`[0-9]*` content-hash gate documented in `VERSION-ARCHITECTURE.md`, so the
module version is the local version signal.

## 1.0.1 — 2026-10-24 (PBB-136 / T-23 repair)

Three defects from the T-23 quality-control verdict, each reproduced on the
committed 1.0.0 bytes before any edit. `monthly_manifest.py` and its tests only;
no contract-layer file, no schema, no dispatch behaviour changes.

- **Defect 1 — a rollback leaked whenever a word trailed the counter, and a
  whole class of valid revisions could never advance.** `_TRAILING_COUNTER`
  read a counter out of the trailing digits only, so a revision without a
  trailing digit was opaque and *any* differing value advanced:
  `check_revision("rev-3", "rev-2-final")` -> `[]` and
  `check_revision("rev-3", "rev-2-approval")` -> `[]`, both a rollback from 3 to
  2. The same heuristic refused the forward moves it could not read:
  `check_revision("2026-11-01", "2026-12-01")` and `check_revision("v1.0",
  "v2.0")` both came back `"does not advance"`, so a date-keyed or
  semantic-version scheme could never move at all, and the reason diagnosed a
  rollback that had not happened. The 1.0.0 line below — "never repeats or
  rolls back a trailing counter" — was true only for the one scheme that
  happened to end in digits. Ordering now reads the revision's whole number run
  and compares it position by position, numerically: `rev-2-final` is the
  number 2 whatever word trails it, `2026-12-01` advances `2026-11-01`,
  `v2.0` advances `v1.0`, `v1.10.0` advances `v1.9.0` (the numbers decide, not
  their spelling), and a repeat of the same number run is still refused. A
  revision with no digits at all stays opaque and advances by inequality, as
  promised. Two revisions that cannot be ordered against each other — one
  numbered, one not (`rev-3` vs `final`) — are refused rather than guessed at,
  because the function promises a revision never rolls back; each of those two
  schemes still approves freely against its own kind, so this is not a blanket
  refusal. `test_the_revision_decision_table_is_pinned` pins the whole table
  literally.
- **Defect 2 — the documented return contract did not hold at the JSON trust
  boundary.** The header promises "on any error the original document comes
  back unchanged", but manifests are loaded from files and a wrong-shaped
  document raised instead of returning errors: `approve` with `placements` set
  to `"P-1"`, `{"P-1": 1}`, `["P-1"]` or `[None]` raised `AttributeError`;
  `amend` with `changes=None` raised `TypeError: 'NoneType' object is not
  iterable` and with `changes=["keyword"]` raised `AttributeError: 'list'
  object has no attribute 'items'`; `approve` on a non-object document raised
  too. Every lifecycle call now refuses a non-object document and a
  non-list-of-objects `placements` with the field named (`$.placements: must be
  a list of placement objects`), `amend` requires a map of approved term to new
  value, and nothing iterates a shape it has not checked. Each refusal is
  paired in the tests with the same call on a valid document succeeding.
- **Defect 3 — a malformed window leaked the interpreter's own message.**
  `next_cycle(..., ends_on=None)` refused, but the error text was `unsupported
  operand type(s) for +: 'NoneType' and 'str'` instead of naming the field. The
  day parser now hands a non-string to `parse_ts`, so the error reads
  `campaign_window.ends_on must be a non-empty ISO-8601 string, got None`, and
  the one remaining `TypeError` fallback names the window rather than quoting
  the interpreter.

**Proof — defects, before -> after** (the probes run the module both ways, same
inputs; `before-fix-suite.txt` / `probe-before.txt` and `probe-after.txt` are in
the run's scratch lane):

| probe | 1.0.0 | 1.0.1 |
|---|---|---|
| `check_revision("rev-3", "rev-2-final")` | `[]` accepted | `rolls back` refused |
| `check_revision("rev-3", "rev-2-approval")` | `[]` accepted | `rolls back` refused |
| `check_revision("2026-11-01", "2026-12-01")` | `does not advance` refused | `[]` accepted |
| `check_revision("v1.0", "v2.0")` | `does not advance` refused | `[]` accepted |
| `approve` with `placements` in `"P-1"`, `{"P-1": 1}`, `["P-1"]`, `[None]` | `AttributeError` raised | `$.placements: must be a list of placement objects`, document unchanged |
| `amend(changes=None)` / `amend(changes=["keyword"])` | `TypeError` / `AttributeError` raised | `an amendment is a map of approved term to its new value`, document unchanged |
| `next_cycle(ends_on=None)` | `unsupported operand type(s) for +: ...` | `campaign_window.ends_on must be a non-empty ISO-8601 string, got None` |

**Proof — inverses, unchanged on both versions** (`probe-after.txt` last
block): `check_revision("rev-2-final", "rev-3")` -> `[]`, `approve(draft())`,
`amend(signed(), {"keyword": "VAULT"})`, `next_cycle(signed(), ...)` all return
no errors, and the rejections are not a blanket refusal: `2026-12-01` ->
`2026-11-01` and `v2.0` -> `v1.0` are refused as rollbacks, `alpha` -> `beta`
advances, `rev-3` -> `rev-4` advances.

**Proof — suites.** `python3 -I shared-utils/manifest/tests/test_monthly_manifest.py`
**43 -> 52 tests, OK** (nine added: five in `RevisionOrderingTests`, four in
`MalformedDocumentTests`). No existing assertion was touched: the diff to
`test_monthly_manifest.py` is additive only. The new tests are not hollow —
run against the 1.0.0 module they fail **13 assertions and raise 12 errors**
(`before-fix-suite.txt`), every one of them in the two new classes, and every
pre-existing case still passes there, so the new coverage bites exactly the new
behaviour. `python3 -m pytest 38-conversational-ai-system/tools/tests/ -q`
**247 passed, 90 subtests passed** before and after.

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
