# core/smp/sheet_migration — planner sheet 1.2.0 → 1.3.0

Wave unit **SMP-W2-U2**. Source: Owner D27 / decision 35 / plan section 6.15
(2026-10-07), which reads:

> The planner sheet (Google Sheet template, `config/sheet-template.schema.json`,
> now 1.2.0): add drama song fields to the Weekly Overview (style chosen,
> status, KIE cost, video link, channels posted) as schema 1.3.0; migrate live
> client sheets with `scripts/migrate-template.py` (no data loss); update the
> row-append webhook payload and `config/validate-sheet-format.py`.

This unit owns `core/smp/sheet_migration/` only. Nothing outside it is edited.

## What ships here

| File | Role |
|---|---|
| `migrate.py` | the migration library: pure, additive, plus `lossless()` proof |
| `scripts/migrate-template.py` | the named migration CLI (fixture mode, dry-run default, backup first) |
| `config/validate-sheet-format.py` | validates the 1.3.0 contract and the export wiring (`--export`) |
| `config/n8n/social-planner-row-append.json` | staged row-append payload carrying the five new fields |
| `testdata/sheet-template-1.3.0.json` | the Skill 35 contract after this migration (1.2.0 → 1.3.0) |
| `testdata/sheet-live-1.2.0.json` | a live-shaped sheet fixture: content rows, a technical key, a ragged row |
| `test_sheet_migration.py` | mocked tests — run this |

## The 1.3.0 Weekly Overview layout

The five fields are appended after the 20 client-facing columns. The technical
upsert key the webhook writes moves one block to the right instead of being
overwritten.

| Index | Column | 1.2.0 | 1.3.0 |
|---|---|---|---|
| 0–19 | A–T | the 20 client-facing headings | unchanged, same order |
| 20 | U | technical upsert key | **Drama Style Chosen** |
| 21 | V | — | **Drama Status** |
| 22 | W | — | **Drama KIE Cost** |
| 23 | X | — | **Drama Video Link** |
| 24 | Y | — | **Drama Channels Posted** |
| 25 | Z | — | technical upsert key |

Payload keys, in the same order:

```
drama_style_chosen, drama_status, drama_kie_cost,
drama_video_link, drama_channels_posted
```

They are optional on the webhook. On a sheet still stamped 1.2.0 they are
**never written** — the receipt reports them pending with a migrate-and-replay
reason, because column U there still holds the technical key.

## Version match

`spreadsheet.properties.appProperties.schema_version`, stamped at provisioning,
is what the webhook reads (`Verify Sheet Metadata (F14)` →
`Build Overview Summary`). It picks the row width and the key column:

* `1.3.0` → 26 cells, fields at 20–24, key at 25, range `A:Z`
* `1.2.0` (or unstamped) → 21 cells, key at 20, range `A:U`, fields pending

## The no-loss guarantee

`1.2.0 → 1.3.0` only adds. It never renames, reorders, blanks or drops a cell:

* every pre-existing heading survives, in order, as the prefix;
* every pre-existing cell keeps its value and its index;
* a row's trailing technical cell survives, shifted past the new fields;
* every other tab is byte-identical;
* a second run is a no-op.

`migrate.lossless(before, after)` checks all of that and
`scripts/migrate-template.py` refuses to write (`exit 4`) if it ever fails.
`--apply` writes a `.backup.json` of the untouched original first.

Refused with `exit 4`: a newer-than-1.3.0 document (never downgrade), a 1.3.0
stamp missing the fields, a partial field set, no Weekly Overview tab, a
heading collision, a malformed version.

## Exit codes (`scripts/migrate-template.py`)

| Code | Meaning |
|---|---|
| 0 | clean, already 1.3.0, or applied |
| 2 | changes pending — dry-run preview, nothing altered |
| 3 | nothing altered (`--apply` withheld: live sheet needs deployment-phase credentials, or the live master template was refused) |
| 4 | rejected |

The live master template is always refused. A `--sheet-id` path stops before
any transport; there is no network client in this module at all.

## Validator

```
python3 core/smp/sheet_migration/config/validate-sheet-format.py              # resolve + validate the contract
python3 core/smp/sheet_migration/config/validate-sheet-format.py PATH.json    # validate that contract
python3 core/smp/sheet_migration/config/validate-sheet-format.py --export     # + the export wiring
```

It keeps every F25 check Skill 35's own validator runs (TEXT_EQ only, colour
and written label for every status, dropdowns, frozen headers, compact This
Week view, never-copied example tab, unique headings, empty starter rows) and
adds the 1.3.0 gate: the contract must be stamped 1.3.0, the 20 legacy
headings must be untouched and in order, and the five drama-song headings must
follow at 20–24. `identity_fields.schema_version` must still document the
appProperties stamp the webhook version-matches on.

With `--export` it checks the staged row-append payload: the five fields are
declared and handled, legacy 1.1.0 callers still pass, the sheet version-match
is wired, and no range is hardcoded to the 1.2.0 width. Skill 35's
`social-planner-sheet-create.json` F25 wiring is validated too when that file
is present.

Contract resolution with no path given: the sibling
`core/smp/sheet_schema_130/` contract first, then Skill 35's own
`35-social-media-planner/config/sheet-template.schema.json`, then the bundled
reference in `testdata/`. Until the 1.3.0 contract lands, the first two resolve
to 1.2.0 and the validator fails closed with the version it found — that is the
intended behaviour, not a break.

## Seams left to other units

* The 1.3.0 **contract file** (`config/sheet-template.schema.json`) belongs to
  SMP-W2-U1 (`core/smp/sheet_schema_130/`). `testdata/sheet-template-1.3.0.json`
  here is this unit's own reference produced by running this migration over
  Skill 35's 1.2.0 contract — not the contract itself.
* Skill 35's own `scripts/migrate-template.py` still performs the F22 legacy
  pass (duplicate headings, template starter rows blanked). That pass removes
  template junk and is **not** part of this bump; this migration is purely
  additive so "no data loss" is provable. A live sheet runs the F22 pass first
  if it needs it, then this bump.
* Skill 35's own `config/validate-sheet-format.py` still validates 1.2.0 and is
  untouched. This staged copy is the 1.3.0 validator for the wave.
* Docs, SOPs, QC shell scripts and the weekly cycle scripts:
  SMP-W2-U3 (`core/smp/docs/`).

## Run the tests

```
python3 core/smp/sheet_migration/test_sheet_migration.py
```

Stdlib only. Zero paid calls: the whole flow is re-run in a process whose
socket layer raises, and prints `NO_NETWORK_OK`.
