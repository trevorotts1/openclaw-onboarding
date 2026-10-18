# STAGING NOTES — S44 production modules, Skill 44 repo home

Staged 2026-10-15 by the S44 packaging worker. Target repo home:
`44-convert-and-flow-operator/tools/siglaunch/` (S44-owned path).
Sources: `~/workspace/signature-launch/rooms/S44/work/` module dirs.
This is a staging copy only: nothing was committed, pushed, or merged,
and the source files under `work/` were not modified.

## Files placed

| Staged path | Source | State |
|---|---|---|
| `siglaunch/store/store.py` | `work/store/store.py` | byte-identical |
| `siglaunch/store/test_store.py` | `work/store/test_store.py` | byte-identical |
| `siglaunch/receiver/receiver.py` | `work/receiver/receiver.py` | byte-identical |
| `siglaunch/receiver/caf_executor.py` | `work/receiver/caf_executor.py` | byte-identical |
| `siglaunch/receiver/test_receiver.py` | `work/receiver/test_receiver.py` | byte-identical |
| `siglaunch/receiver/test_caf_executor.py` | `work/receiver/test_caf_executor.py` | byte-identical |
| `siglaunch/receiver/test_e2e_dryrun.py` | `work/receiver/test_e2e_dryrun.py` | byte-identical |
| `siglaunch/normalizer/normalizer.py` | `work/normalizer/normalizer.py` | EDITED (change 1) |
| `siglaunch/normalizer/test_normalizer.py` | `work/normalizer/test_normalizer.py` | byte-identical |
| `siglaunch/normalizer/purchase-event.schema.json` | `packet/reference/schemas/purchase-event.schema.json` | vendored copy, byte-identical |
| `siglaunch/provisioning/provisioning.py` | `work/provisioning/provisioning.py` | byte-identical |
| `siglaunch/provisioning/test_provisioning.py` | `work/provisioning/test_provisioning.py` | byte-identical |
| `siglaunch/processor/processor.py` | `work/processor/processor.py` | EDITED (change 2) |
| `siglaunch/processor/test_processor.py` | `work/processor/test_processor.py` | byte-identical |
| `siglaunch/timing/timing.py` | `work/timing/timing.py` | byte-identical |
| `siglaunch/timing/test_timing.py` | `work/timing/test_timing.py` | byte-identical |

## Import / path changes (2 files edited; everything else needed none)

Every test file's cross-module `sys.path` inserts are relative
(`Path(__file__).parent.parent / "<sibling>"`), so they resolve to the
same siblings inside the staged `siglaunch/` tree as in the `work/`
tree and were left untouched.

1. **`normalizer/normalizer.py` — schema path.**
   Was: `_PACKET_SCHEMA = Path(__file__).resolve().parents[4] / "packet" / "reference" / "schemas" / "purchase-event.schema.json"`.
   Now: `_PACKET_SCHEMA = Path(__file__).resolve().parent / "purchase-event.schema.json"`,
   i.e. the schema vendored beside the module (see file list above), so
   the staged tree is self-contained and does not depend on the packet
   directory existing at a fixed depth. A "Staging note" comment at the
   edit site records this.

2. **`processor/processor.py` — `validate_event` source.**
   Chosen option: **load the packet schema directly with jsonschema**
   (the vendoring alternative was rejected: a vendored `events.py`
   resolves the packet schema by its own `parents[4]` path, which is
   wrong at the staged depth and would have forced an edit inside the
   L1 reference file, which is staged separately).
   Was: `sys.path.insert(0, str(Path(__file__).parent.parent / "events"))` plus
   `from events import validate_event`.
   Now: the schema is loaded at import from
   `../normalizer/purchase-event.schema.json` (the single vendored copy
   in this tree) and a local `validate_event(event)` is defined with the
   identical contract (jsonschema.validate against the v1.0 schema;
   raises on invalid, returns the event). The now-unused `import sys`
   was dropped; `import json` and `import jsonschema` were added. A
   "Staging note" comment at the edit site records this. No other logic
   changed.

## Test results (staged tree, `python3 -m unittest discover -p "test_*.py"` per subdir)

| Suite | Ran | Result |
|---|---|---|
| store | 7 | OK |
| receiver (test_receiver 12 + test_caf_executor 5 + test_e2e_dryrun 2) | 19 | OK |
| normalizer | 12 | OK |
| provisioning | 3 | OK |
| processor | 7 | OK |
| timing | 5 | OK |
| **Total** | **53** | **53/53 passing** |

Matches the source-tree counts exactly. (The events L1 suite, 17
tests, is not part of this package; it is staged separately.)

## Open issues

- None blocking. Two notes for the landing step:
  - `processor.py`'s schema dependency now points across subdirs
    (`../normalizer/purchase-event.schema.json`). If the landing prefers
    zero cross-subdir references, vendor a second schema copy under
    `processor/` instead; behavior is identical either way.
  - `normalizer.py` will need its schema path revisited when S49's
    schema v1.1 (PR #2137) lands, per the recorded S44 follow-up: point
    validation at the domain v1.1 schema accepting both versions.

## Refresh — 2026-10-16 (S44 room, packaging stream)

Basis: Stream D (ev1 + fulfillment-map producer, independently
reviewed 2026-10-16), the A17–A21 acceptance streams, and the
authorized L4 sandbox run (CR-S82-002, BCEO Client Sandbox, test mode
only). Same staging discipline as the original placement: copies
only, no source file under `work/` modified, nothing pushed or
merged.

### Files added or changed in this refresh

| Staged path | Source | State |
|---|---|---|
| `siglaunch/store/store.py` | `work/store/store.py` | REPLACED — now includes the Stream D read-model section (`buyer_entitlement_rows`, `entitlement_version` ev1); byte-identical to source |
| `siglaunch/store/test_entitlement_version.py` | `work/store/test_entitlement_version.py` | byte-identical (7 tests; hashes pinned independently from the ev1 spec text) |
| `siglaunch/fulfillment_map/fulfillment_map.py` | `work/fulfillment_map/fulfillment_map.py` | byte-identical |
| `siglaunch/fulfillment_map/test_fulfillment_map.py` | `work/fulfillment_map/test_fulfillment_map.py` | byte-identical (16 tests) |
| `siglaunch/fulfillment_map/evidence-fulfillment-map.md` | `work/fulfillment_map/evidence-fulfillment-map.md` | byte-identical |
| `siglaunch/fulfillment_map/s82-contract-copy.md` | `work/fulfillment_map/s82-contract-copy.md` | byte-identical — S82's fulfillment-continuity contract, verbatim with provenance (original: `82-signature-thank-you/references/s44-fulfillment-continuity.md`, blob db6efbbe) |
| `siglaunch/acceptance/test_a17_a19_acceptance.py` | `work/acceptance/` | byte-identical (4 tests) |
| `siglaunch/acceptance/test_a18_a20_acceptance.py` | `work/acceptance/` | byte-identical (4 tests) |
| `siglaunch/acceptance/test_a21_acceptance.py` | `work/acceptance/` | byte-identical (5 tests) |
| `siglaunch/acceptance/evidence-a17-a19.md`, `evidence-a18-a20.md`, `evidence-a21-and-item5.md` | `work/acceptance/` | byte-identical |
| `siglaunch/l4/` (5 run drivers, `L4-RUN-2026-10-16.md`, `L4-COMPLETION-2026-10-16.md`, 3 results JSONs, `l4-check3-completion.json`) | `work/l4/` | byte-identical RUN RECORDS — see note below |

Acceptance-suite honesty labels are carried in the files themselves:
they are L1/L2 module-level proof, never labeled native proof. The
native (L4) proof is the `l4/` record set.

### The `l4/` folder is evidence, not a product surface

The drivers (`run_l4_pipeline.py`, `run_l4_resume.py`,
`run_l4_resume2.py`, `run_l4_check3.py`, `run_l4_refund.py`) are the
exact scripts of the authorized 2026-10-16 sandbox run. They
reference the room layout (`rooms/S44/work/`) and that run's native
object IDs, and re-running them would recreate sandbox side effects;
they are staged so the L4 proof is reproducible and auditable, not
as a runnable surface. The durable store file (`l4-store.sqlite`)
is a runtime artifact and is NOT staged; it stays in the room.

### Test results (staged tree, this refresh, `python3 -m unittest discover -p "test_*.py"` per subdir)

| Suite | Ran | Result |
|---|---|---|
| store (test_store 7 + test_entitlement_version 7) | 14 | OK |
| receiver | 19 | OK |
| normalizer | 12 | OK |
| provisioning | 3 | OK |
| processor | 7 | OK |
| timing | 5 | OK |
| fulfillment_map | 16 | OK |
| acceptance (A17/A19 4 + A18/A20 4 + A21 5) | 13 | OK |
| events (staged separately, `shared-utils/signature_launch/events`) | 17 | OK |
| **Total** | **106** | **106/106 passing** |

Matches the work-tree counts exactly (106/106, independently
reviewed 2026-10-16 before the L4 run; no module code changed
during the L4 run).


## Successor — 2026-10-16: schema v1.1 switch + receiver 0.2 (S44 swarm lane G)

Successor commit on `s44/siglaunch-production-modules` (after
57556db), placed from the room's verified work-layout builds: the
schema v1.1 switch per Lane B report section 4B, and the Lane F
receiver fixes (GAP-1 through GAP-5) as placed in the work layout by
the S44 coordinator (receiver 0.2).

### Files added or changed in this successor

| Staged path | Source | State |
|---|---|---|
| `siglaunch/normalizer/purchase-event.v1.1.schema.json` | domain v1.1 bytes (via `work/events/purchase-event.v1.1.schema.json`) | NEW vendored copy, SHA-256 `311d04820360193a892929e6cf12788372db85977caf1e1277a8f3024515806a` |
| `siglaunch/normalizer/normalizer.py` | staged file, edited in place | v1.1 wiring: the vendored v1.1 schema is loaded at module load and used as `ingest()`'s default `schema_v11`, so the pipeline stamps 1.1 and carries `contact_ref` whenever a read-back supplies it. `normalize()` itself is untouched — direct callers keep the explicit-injection contract (the pinned context-only test still passes). SHA-256 `d60cccb791745d92ee9c3bcfd2dca08a1e9c0aa9284deac08ce8a8dc3200cb10` |
| `siglaunch/processor/processor.py` | staged file, edited in place | the single-schema (v1.0) loader + `validate_event` replaced by the dual registry/dispatch (same code as the L1 events module): candidates are the two schemas vendored beside the staged normalizer, each registered by its own `schema_version` const; dispatch on the stamped version, fail closed otherwise. Back-compat surface kept (`_SCHEMA`, `SCHEMA_PATH`); `SCHEMA_SOURCES` / `SUPPORTED_SCHEMA_VERSIONS` added. SHA-256 `19dd69ae525ac1020f247ebd52330be9432d053feb93f18e67987e79082d2f9b` |
| `siglaunch/receiver/receiver.py` | `work/receiver/receiver.py` (the 0.2 build as placed by the coordinator; `SKILL44_VERSION = "siglaunch-s44-receiver-0.2"`) | REPLACED — byte-identical to the source, SHA-256 `52336bf0178019bdb6e0b4d6e615d534900f0ff261bca08b2e0af56b7001ab57`. Carries the Lane F GAP-1..GAP-5 fixes |
| `siglaunch/receiver/test_lane_f_regressions.py` | `work/receiver/test_lane_f_regressions.py` | NEW (19 tests). Two placement adaptations, assertions untouched: the module docstring now names the packaged 0.2 build, and the fixture-path constant resolves the vendored pair at `tools/siglaunch/fixtures/` instead of the room layout's `rooms/S44/fixtures/`. SHA-256 `ce16b6ec874d45f4077e087bf65c671ee8cf68e1ec300661e0f4470ccdb4d49a` |
| `siglaunch/fixtures/automation-handoff.json` | `rooms/S44/fixtures/automation-handoff.json` (lane C fixture) | NEW vendored copy, byte-identical, SHA-256 `c2191b70fbfbbe563ede63e24ac6ac51a02409e9acb53baeed47d750a5a25b78` |
| `siglaunch/fixtures/s50-email-plan.json` | `rooms/S44/fixtures/s50-email-plan.json` (lane C fixture) | NEW vendored copy, byte-identical, SHA-256 `d89bcebe51a735663909a6235198caca454ec299943405ef103fc81815a611f6` |

The fixture pair is SYNTHETIC (lane C, every value fake) and is never
live proof.

Note on the `l4/` records: they are unchanged. A hypothetical re-run
of those drivers against the now-wired normalizer would stamp 1.1
for read-backs carrying `contact_ref`; the records describe the
2026-10-16 run as executed and are not rewritten.

### Test results (staged tree, this successor, `python3 -m unittest` per subdir)

| Suite | Ran | Result |
|---|---|---|
| store (test_store 7 + test_entitlement_version 7) | 14 | OK |
| receiver (existing 19 + lane F regressions 19) | 38 | OK |
| normalizer | 12 | OK |
| provisioning | 3 | OK |
| processor | 7 | OK |
| timing | 5 | OK |
| fulfillment_map | 16 | OK |
| acceptance (A17/A19 4 + A18/A20 4 + A21 5; A18 wall 1.4477s < 5.0s) | 13 | OK |
| events (staged separately, `shared-utils/signature_launch/events`; post-merge layout harness, see its STAGING-NOTES) | 43 | OK |
| **Total** | **151** | **151/151 passing in the post-merge layout** |

Branch-layout note: run on this branch alone, the events package's
`DomainSiblingLayoutTests` errors on the absent `domain/` sibling
directory (it lands via main, which carries it) — every other suite
passes in the branch layout (150/151 branch-local, the one error
environmental). The total matches the work-tree count exactly
(151/151 after the coordinator's work-layout placements of the same
builds).


## Lane I addendum — 2026-10-16: import-depth guard fix (events package)

The lane G successor table above states the events package at 43
(post-merge layout) and the staged total at 151. Lane I's successor
commit (after 3f2dd53) changes the EVENTS package only — the
import-depth guard fix in
`shared-utils/signature_launch/events/events.py` plus its
`ShallowPathImportTests` regression — so exactly two counts in that
table change, both in the post-merge layout: **events 43 → 44** and
**total 151 → 152**. Every tools/siglaunch suite count in the table
is unchanged and was re-verified by lane I in the branch layout
under both the room TMPDIR rule and a default TMPDIR: store 14,
receiver 38, normalizer 12, provisioning 3, processor 7, timing 5,
fulfillment_map 16, acceptance 13 — all OK. Detail: the events
package STAGING-NOTES, lane I successor section.

## Successor — 2026-10-17: A16 executor realignment + store-guard reconciliation (S44 coordinator)

Branch `s44/siglaunch-a16-executor-store-fix`, based on main
`e1692494a21c037d95208e2075b657b161b5d7d9` (post-train-#2220 main;
the tools/siglaunch tree is unchanged on main since the PR #2181
landing, verified by an empty diff for this tree between main
6e1542c6 and e1692494).

Basis: the A16 execution chain of 2026-10-17. The packaged copies
landed by PR #2181 were byte-identical to the drifted work-layout
originals (packaged `receiver/caf_executor.py` SHA-256
`2d69c17f6d8ee91b905ac4521508dafb37dfbd00f7527a6465bb25da5fb0574a`,
packaged `store/store.py` SHA-256
`a5e052fd2e96af4ffe2807c853a9f80e173d230313e15c46776055924aa5ace6`),
and the drift stopped the first real A16 dispatch: the executor
called a caf CLI surface the installed engine does not have
(per-command `--json` on export, a positional build plan, a
nonexistent `workflows qc` verb, folder-based export), and the
store's superseded-version guard refused every same-version
redispatch write, so no redispatch outcome ever persisted. Both
defects were fixed in the work layout (Lane FIX-EXECUTOR and Lane
FIX-STORE, 2026-10-17), verified there (full room suite 156/156
under both TMPDIR conditions, plus the 13 acceptance tests), closed
by MAIN, and proven live (the A16 store's first persisted redispatch
outcome, state "partial", on the 2026-10-17 resume run 3). This
successor places those exact fixed bytes. No version bump is in
this candidate: `skill-version.txt` is read fresh from main at
merge time (the PR #2181 G3 lesson).

### Files added or changed in this successor

| Staged path | Source | State |
|---|---|---|
| `siglaunch/receiver/caf_executor.py` | `work/receiver/caf_executor.py` | REPLACED — realigned to the installed engine's real CLI surface (top-level `--json`/`--experimental`, build `--from-plan`, read-back via `export --workflow-id`/`--out`, AC20 snapshot re-grounded on `workflows list`, QC leg on the skill-root `qc-built-workflow.sh`). Byte-identical to source, SHA-256 `af865200f597a710901a1ee10963490e3cf09aa0e7267095d2c5c6a2027fae1d` |
| `siglaunch/receiver/test_caf_executor.py` | `work/receiver/test_caf_executor.py` | REPLACED — rebuilt on a fake runner keyed by the actually-invoked subcommands. Byte-identical, SHA-256 `2db1195cfc05511e47f6ba6babbf78e9f16b7cf08103e110aa41635d05d3ff18` |
| `siglaunch/receiver/test_cli_surface_contract.py` | `work/receiver/test_cli_surface_contract.py` | NEW — pins the adapter's assumptions to the real `caf --help` output of the room worktree's engine (skips, never fails, when no engine worktree is present). Byte-identical, SHA-256 `d80cf2ca0557df61aff455cd3b00fcc1d86b2cff7d9c1167773ed3703a8e2dde` |
| `siglaunch/receiver/test_e2e_dryrun.py` | `work/receiver/test_e2e_dryrun.py` | REPLACED — realigned onto the same real-surface fixtures. Byte-identical, SHA-256 `dfab8b4025ecff5261ec99cc5e7faf69caa2b2a046c778dbf566a5a817a09c06` |
| `siglaunch/store/store.py` | `work/store/store.py` | REPLACED — `put_request` reconciled with the receiver's resume semantics: refusal only for a greater version, or same version over a completed record. Byte-identical, SHA-256 `8b7b0d3505f82ab3991bbef87f4bb2e8340d108194aa1ffb2cd9e57631967de8` |
| `siglaunch/store/test_store.py` | `work/store/test_store.py` | REPLACED — additions only (new redispatch-persistence test); no pre-existing test modified. Byte-identical, SHA-256 `38ca392af2c9e8bc1f91154ebe8f28f4b6feaa40a8aa5853fc0d5e8fc0ac11ca` |

No placement adaptations were needed: every placed file is
byte-identical to its work-layout source, and the packaged suites
below pass as placed.

### Test results (staged tree, this successor, `python3 -m unittest discover -p "test_*.py"` per subdir)

| Suite | Ran | Result |
|---|---|---|
| store (test_store 8 + test_entitlement_version 7) | 15 | OK under both TMPDIR conditions |
| receiver (test_receiver 12 + lane F regressions 19 + test_caf_executor 10 + test_e2e_dryrun 2 + CLI surface contract 6, run against the room worktree's real engine help) | 49 | OK under both TMPDIR conditions |
| normalizer | 12 | OK |
| provisioning | 3 | OK |
| processor | 7 | OK |
| timing | 5 | OK |
| fulfillment_map | 16 | OK |
| acceptance (A17/A19 4 + A18/A20 4 + A21 5; A18 wall 1.2991s / 1.1132s, both < 5.0s) | 13 | OK under both TMPDIR conditions |
| **Total (tools/siglaunch tree)** | **120** | **120/120 passing** |

The events package (`shared-utils/signature_launch/events`, 44
tests) is untouched by this successor.
