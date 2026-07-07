# Golden fixtures (SPEC 3.1 `fixtures/`, W1.23)

Fixed, expected-outcome synthetic replays of the **whole orchestrator ledger and
assembly machine** (`scripts/anthology_state.py`). Each fixture is a replayable
sequence of ledger subcommands with the exact expected exit code and a subset of
the JSON result per step, plus per-fixture `final_assertions` read back from the
persisted ledger. All data is fabricated: no client PII, no secret values, no
Anthropic identifiers, none of the nine Downloads JSON exports in whole or part.

The **intake webhook** battery (T1–T9) lives separately under `../webhook/`
(W1.6); this directory is everything *after* a submission is routed.

| Fixture | Drill | What it proves |
|---|---|---|
| `full-participant.json` | W5.4 | one participant walked S0 → `approved` through every stage and gate, including one S6 rewrite round (chapter v1 → v2); title-lock one-way guard; gate-bypass-via-`advance-stage` refusal; kill-and-resume idempotent replay; a lone contributor cannot arm assembly (below `min_chapters`) |
| `two-anthology-contact.json` | W5.6 | one `contact_id` in two anthologies → two independent participant rows under the composite key `contact_id::anthology_id`; re-upsert in-anthology updates the one record; independent title locks / rewrite counts / cursors |
| `exception.json` | W5.5 | exceptions-queue capture across all five typed reasons (incl. `legacy_reconciliation`), participant-tied capture stamping `stage_cursor='exception'`, resolve + idempotent replay, and the guard refusals (unknown reason → 5, non-JSON raw → 5, unknown id → 3) |
| `assembly-trio.json` | W5.7 | three synthetic frozen chapters assembled with the full S9 guard matrix: below-minimum, unapproved-participant blocking, the one explicit exclusion (which arms), confirm-name + own-producer guards, `assembly-advance` second-door refusals, one-way/double-fire no-op, order validation + producer reorder, compile-time frozen-chapter sha256 byte-identity, and `s9_producer` sign-off delivering the members |

`golden-manifest.json` binds each fixture to its drill and registers the
synthetic chapter body files (`chapters/*.md`) with their real sha256. The
assembly compile step (`assembly-advance --verify-sha`) re-proves each frozen
chapter byte-identical against the actual chapter bytes, so the shas in the
fixtures are the **real** sha256 of the referenced files.

## Replay (offline smoke test)

```
python3 fixtures/golden/replay_golden.py --list
python3 fixtures/golden/replay_golden.py --all
python3 fixtures/golden/replay_golden.py --fixture assembly-trio --explain
```

The harness runs each fixture in its **own temp state dir** with no base id
configured, so the ledger runs **mirror-only** (SPEC 7.2) — deterministic,
network-free, exit 0 on the base path. It asserts every step's exit code and
result subset, the body-file sha self-consistency, and the `final_assertions`
(participant cursors, anthology state, S9 readiness, and the one-contact /
two-anthology keying invariant). Exit 0 iff everything holds.

## Step schema

```jsonc
{
  "n": 9, "stage": "S1", "desc": "...", "door": "dashboard",
  "cmd": "record-approval",                 // an anthology_state.py subcommand
  "args": { "--gate": "s1_producer", ... }, // list/dict values are JSON-encoded
  "expect_exit": 0,                          // required exit code
  "expect": { "stage_cursor": "s2_tone" }    // subset the JSON result must match
}
```

A `negative: true` step asserts a guard refusal (non-zero exit, nothing changed).
A step with `"macro": "drive_to_approved_frozen"` expands to the exact
`S0 → approved`-with-a-frozen-chapter subcommand sequence (kept in the harness so
the fixtures stay readable; `--explain` prints the expansion). A step naming a
`body_file` alongside a `--sha256` is checked for byte-consistency.

## Both doors

On the operator canary the W5.4 / W5.6 / W5.7 drills replay these **same**
sequences but exercise each gate from **both doors** — the Command Center board
card *and* the participant token page — and verify the Doc+PDF pairs, the
Convert and Flow field read-backs, and the per-gate pipeline-stage updates. The
golden fixtures fix the ledger-side truth those drills must reproduce.
