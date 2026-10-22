# S75-W01-U2 — anonymous incident fixtures and privacy hygiene

Synthetic fixture suite reproducing the thirteen recorded failure patterns
(Skill_75_Universal_Repair_Spec_v1.1 sections 17.4, 17.8, 17.10), with
anonymous identities and injected runtime paths, plus the privacy scan over
every shared artifact this unit touched.

## Layout

| Path | What |
| --- | --- |
| `fixtures/S75-F01.json` … `S75-F13.json` | one fixture per named failure pattern |
| `harness/drivers.py` | reproduction drivers against real product source |
| `harness/run_suite.py` | suite runner (one isolated interpreter per fixture) |
| `tests/test_fixture_suite.py` | reproduction + anonymity assertions |
| `privacy/scan.py` | privacy scanner (classes and locations only) |
| `PRIVACY-SCAN-REPORT.md` | recorded scan report |
| `RUN-LOG.json` | per-fixture observed values from the recorded run |
| `TESTS-run.txt` | recorded test run |
| `RECEIPT.json` | receipt and acceptance evidence map |

## Pattern map

| Fixture | Named pattern | Driver target |
| --- | --- | --- |
| F01 | all-parked run reporting delivered | factory `next` selector |
| F02 | failed-blocked mixed runs | factory `next` selector |
| F03 | expired RUNNING music lease | factory `music_stage` + state store |
| F04 | positional approval reorder flips a saved Yes | `script_approval.wants_approval` |
| F05 | missing/corrupt approval records | `script_approval.record_for` + gate |
| F06 | empty tool/module/credential lists pass preflight | `preflight.check` |
| F07 | 120s profile rejection | `preflight.check` |
| F08 | four-second silent lead-in passes opening gate | `story_coverage.story_start_gate` |
| F09 | dict-only reader over a valid QC list | pending-head `_read_json` / continuity probe |
| F10 | MISSING_QC + SCHEMA_VIOLATION completes music | pending-head `music_stage` + `qc_gate.evaluate` |
| F11 | attempt ordinal stuck at 1 | `spend_ledger.plan` |
| F12 | empty take list narrated as dispatch success | `song_choices._real_generate` |
| F13 | stale keepalive registration | `install-keepalive-cron.sh` (pinned revision) |

Product revisions under test: 999 main (pinned), onboarding pending head
(pinned), onboarding timer-artifacts (pinned). Boundaries stubbed, both named
in the receipt: the dispatcher seam inside the generation wrapper (F12) and
the scheduler CLI behind a fake binary (F13) — the spec's own harness shapes.

## Run

```
python3 harness/run_suite.py \
  --core-999 <product-core-dir> --pending-head <pending-head-tree> \
  --timer-dir <timer-artifacts-dir> --tmp <scratch-dir> [--only S75-F03]
```

Each fixture executes in its own interpreter against a fresh scratch copy of
its seeded state; product trees are executed read-only. Tests:

```
S75_CORE_999=… S75_PENDING_HEAD=… S75_TIMER_DIR=… S75_TMP=… \
  python3 -B tests/test_fixture_suite.py
```

Every identity in the fixtures is synthetic (`*-synth-*`); every runtime path
is an injected placeholder. No fixture depends on any real client, run, host
or chat identity.
