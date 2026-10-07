# v2-13-canary

Model-quality canary for the **lip-sync** leg of workflow **V2-13**, rebuilt for
owner decision **D33** (2026-10-07) and the BUILD-OUT order item 5
(restart copy of BO-LIP, unit `BO-LIP-R-U2`).

What changed against the original V2-13 row:

- the canary compares **`kling/ai-avatar-standard` (primary)** against
  **`infinitalk/from-audio` (backup)** — see `SPEC.md` and `canary_spec.json`;
- the roster is **closed at those two entries in that order**; a third provider
  is out of the canary and its token is not carried in this directory;
- **1 or 2 shots**, all cut from the same keyframe of the approved ad's
  painful-moment shot in the cartoon look;
- **scripted mocks only — this window spends 0 USD and makes 0 paid calls.**

## Layout

| File | What it is |
|---|---|
| `SPEC.md` | human-readable canary spec |
| `canary_spec.json` | machine-readable spec, source of truth |
| `mock_harness.py` | scripted offline harness: roster, ledger, paths |
| `run_canary.py` | driver; writes `outcomes/run.json`; `--live` refused |
| `fixtures/*.json` | canned shot + adapter responses (mock, unpaid) |
| `test_canary_spec.py` | spec checks: order, closed roster, shot bounds, zero spend |
| `test_mock_harness.py` | harness checks: primary path, fallback path, both-fail, refusals |
| `test_zero_spend.py` | no network import, sockets blocked, live entrypoint refused |
| `run_all.sh` | driver for the whole suite |
| `outcomes/` | last run only (`test-run.log`, `run.json`) |

## Run

```bash
bash run_all.sh
```

| Exit | Meaning |
|---|---|
| `0` | every check passed (`ALL_V2_13_CANARY_CHECKS_PASS`) |
| `1` | at least one check failed (`V2_13_CANARY_FAIL:...`) |
| `2` | tooling failure — nothing was tested |

Each test file also runs on its own (`python3 test_canary_spec.py`) and is
pytest-collectable.

## Last recorded run

| Metric | Value |
|---|---|
| Mode | mock |
| Paid calls | 0 |
| Spend | 0.00 USD |
| Providers | `kling/ai-avatar-standard` first, `infinitalk/from-audio` second |
| Paths exercised | primary ok, fallback, both fail |

See `outcomes/test-run.log` and `outcomes/run.json` for the exact record.

## Money

Nothing in this directory calls a provider. The harness refuses a nonzero
price, refuses a live entrypoint, and imports no network client. The later live
canary needs its own operator budget approval and then routes through Skill 74
with a spend-ledger reservation; reference prices stay in `canary_spec.json`.
