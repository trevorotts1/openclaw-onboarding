# core/smp/sheet_migration — planner sheet 1.2.0 → 1.3.0

Wave unit **W1-B-U2** (originally SMP-W2-U2). Source: Owner D27 / decision 35 /
plan section 6.15 (2026-10-07), and manual **H5** (2026-10-08, rewrite option):

> Two different "schema 1.3.0" planner sheet layouts exist; landing the staged
> one corrupts live sheets. … **rewrite** its two constant blocks to match the
> installed contract exactly: headings, keys, U kept as key, V to Z for fields.

The owner's order for this unit chose **option 2 — rewrite, never delete**.
The installed contract is authoritative:

* `35-social-media-planner/config/sheet-template.schema.json` (stamped 1.3.0)
* the sibling `core/smp/sheet_schema_130/` module encodes the same layout
* the provisioner `35-social-media-planner/config/n8n/social-planner-sheet-create.json`
  already creates sheets this way

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

This unit owns `core/smp/sheet_migration/` only. Nothing outside it is edited.

## The installed 1.3.0 Weekly Overview layout

The **technical upsert key never moves**. It sits at index 20 / column U before
1.3.0 and stays there after; the five drama-song fields are appended to its
right at V..Z.

| Index | Column | 1.2.0 | 1.3.0 |
|---|---|---|---|
| 0–19 | A–T | the 20 client-facing headings | unchanged, same order |
| 20 | U | technical upsert key | technical upsert key `cycle_id` — **unchanged** |
| 21 | V | — | **Drama Song Style** |
| 22 | W | — | **Drama Song Status** |
| 23 | X | — | **KIE Cost (cents)** |
| 24 | Y | — | **Drama Song Video Link** |
| 25 | Z | — | **Drama Song Channels Posted** |

Payload keys, in the same order:

```
drama_song_style, drama_song_status, kie_cost_cents,
drama_song_video_url, drama_song_channels
```

They are optional on the webhook. On a sheet still stamped 1.2.0 they are
**never written** — the receipt reports them pending with a migrate-and-replay
reason, because column U there still holds the technical key.

### Why this is the only layout

The earlier staged copy of this module put the five fields at U..Y and pushed
the key to Z, under a retired heading/payload-key set of its own. Landing that
on a sheet the provisioner already made would have written the style text into
the live key column, so every weekly append would create a duplicate row.
Manual H5 named the installed contract authoritative and this rewrite removed
the retired layout. Its retired heading names and payload keys no longer appear
anywhere in this module — `test_sheet_migration.py` holds that as a permanent
static gate, and the repo-wide acceptance is a clean grep for the retired
field name.

A heading row that is neither the 1.2.0 shapes nor the installed 1.3.0 shape —
including the retired 25-heading one — is refused by name, never guessed at.

## Version match

`spreadsheet.properties.appProperties.schema_version`, stamped at provisioning,
is what the webhook reads (`Verify Sheet Metadata (F14)` →
`Build Overview Summary`). It picks the row width; the key column does not move:

* `1.3.0` → 26 cells, drama fields at 21–25, key at 20, range `A:Z`
* `1.2.0` (or unstamped) → 21 cells, key at 20, range `A:U`, fields pending

## The no-loss guarantee

`1.2.0 → 1.3.0` only adds. It never renames, reorders, blanks or drops a cell:

* every pre-existing heading survives, in order, as the prefix;
* every pre-existing cell keeps its value and its index — including the
  technical key at index 20;
* the five new drama cells exist and are empty;
* every other tab is byte-identical;
* a second run is a no-op.

`migrate.lossless(before, after)` checks all of that and
`scripts/migrate-template.py` refuses to write (`exit 4`) if it ever fails.
`--apply` writes a `.backup.json` of the untouched original first.

Refused with `exit 4`: a newer-than-1.3.0 document (never downgrade), a 1.3.0
stamp that is not the installed layout, a partial field set, a retired or
otherwise unmigratable heading row, `cycle_id` away from index 20, a 1.2.0 row
already wider than 21 cells, no Weekly Overview tab, a heading collision, a
malformed version.

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
headings must be untouched and in order, `cycle_id` must sit at index 20
(column U), and the five drama-song headings must follow at 21–25 (V–Z).
`identity_fields.schema_version` must still document the appProperties stamp
the webhook version-matches on.

With `--export` it checks the staged row-append payload: the five fields are
declared with the installed keys and columns, legacy 1.1.0 callers still pass,
the sheet version-match is wired, the upsert key stays pinned at index 20, and
no range is hardcoded to the 1.2.0 width. Skill 35's
`social-planner-sheet-create.json` F25 wiring is validated too when that file
is present.

Contract resolution with no path given: the sibling
`core/smp/sheet_schema_130/` contract first, then Skill 35's own
`35-social-media-planner/config/sheet-template.schema.json`, then the bundled
reference in `testdata/`. Every one of those three is the same installed
layout, so all three pass.

## Seams left to other units

* Skill 35's own `scripts/migrate-template.py` still performs the F22 legacy
  pass (duplicate headings, template starter rows blanked). That pass removes
  template junk and is **not** part of this bump; this migration is purely
  additive so "no data loss" is provable. A live sheet runs the F22 pass first
  if it needs it, then this bump.
* Skill 35's own `config/validate-sheet-format.py` still validates 1.2.0 and is
  untouched. This staged copy is the 1.3.0 validator for the wave.
* The n8n row-append payload ships staged here; Skill 35's own
  `config/n8n/social-planner-row-append.json` is still stamped 1.1.0 and is not
  this unit's to edit.
* Docs, SOPs, QC shell scripts and the weekly cycle scripts: SMP-W2-U3
  (`core/smp/docs/`).

## Run the tests

```
python3 core/smp/sheet_migration/test_sheet_migration.py
```

Stdlib only. Zero paid calls: the whole flow is re-run in a process whose
socket layer raises, and prints `NO_NETWORK_OK`.