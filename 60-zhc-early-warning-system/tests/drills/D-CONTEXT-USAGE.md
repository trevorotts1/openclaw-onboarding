# Drill D-CONTEXT-USAGE -- live usage computation + the D5 two-lane delivery

## What it proves

Before this fix, `sig_s3()`'s 70%-note / 85%-handoff branches were real code that
was never actually reached in a live tick: `ews_sentinel.py`'s `run_tick()` called
`sig_s3(config, thresholds)` with NO `usage_pct`, so those branches were exercised
only by `sig_s3`'s own self-test fixtures, never by anything watching a real box.
Separately, the D5 self-notice this produces (`box-agent-notices.jsonl`) had NO
reader anywhere in the repo -- a pure dead end. This drill proves the whole chain is
now live, end to end, AND proves the one narrow, approved exception to "operator
never sees a running-low case" does not leak past its intended boundary.

## Fixture / input

- `tests/fixtures/context-window-clean.json` -- a healthy box: `_contextWindow`
  128000, `softThresholdTokens` 20000, effective ceiling 108000.
- `tests/fixtures/context-usage-86pct.trajectory.jsonl` -- the newest session's
  latest trajectory event carries `contextTokens: 92880` (86% of the 108000
  ceiling above).

## Pass condition

1. **Live computation is wired, not dead code.** `_context_usage(config, led)`,
   pointed at the fixture pair via `EWS_OPENCLAW_ROOT`, returns `(86, 128000)` --
   not `(None, None)`. Feeding that into `sig_s3(config, thresholds, usage_pct=86,
   context_window=128000)` produces exactly one `S3|handoff` finding, severity P2,
   route `box_agent` (D5 -- NOT the operator).
2. **The reader actually reads.** Routing that finding through `ews_alert.py`
   writes it to `box-agent-notices.jsonl`, and `read_box_agent_notices()` (the new
   D3 fix) returns it -- then returns nothing on a second call (at-most-once
   consumption via the ledger's own offset tracking, not a second, competing state
   writer).
3. **Lane 2 fires ONLY on the operator's own box.** With the box's ledger `role`
   meta set to `"operator"`, the SAME `S3|handoff` finding ALSO produces exactly
   ONE plain-language self-notice sent to the operator's own chat (Lane 2, the
   narrow approved D5 exception) -- text mentions the measured percentage, no key
   paths, no jargon.
4. **Lane 2 NEVER fires on a client box.** The IDENTICAL finding shape, on a box
   whose ledger `role` meta is `"client"`, produces ZERO operator-facing sends --
   Lane 1 (the local self-notice file) still writes, because that half of D5 is
   unchanged and applies to every box; only Lane 2 is boundary-tested here, and it
   must stay silent.
5. **Lane 2 respects its own opt-out.** With `context.operator_self_notify: false`,
   even the operator's own box produces zero Lane-2 sends for the same finding.
6. **The note/handoff boundary holds.** A 70%-note-level finding (`S3|note`,
   severity P3) NEVER produces a Lane-2 send, on any box -- only the 85%-handoff
   case does, matching the spec's Lane-2 threshold.
7. **The broken-config case is untouched.** Feeding `_context_usage()` a config
   whose ceiling is already broken (see `subtractive-misconfig.json`) returns
   `(None, None)` even when synthetic tokens are present -- it never guesses a
   percentage on a box that is going to crash regardless; the existing
   broken-config P1 (`D-S3.md`) still owns that case exclusively.

## Where this is exercised

- `scripts/ews_sentinel.py --self-test` -- the `_context_usage` case (fixture-free,
  synthetic in-line data).
- `scripts/ews_alert.py --self-test` -- the `Lane-2 owner-notice`,
  `notices-reader`, `Lane-2 note-vs-handoff`, `Lane-2 client-box`, and `Lane-2
  opt-out` cases.
- `verify.sh` -- the `D-CONTEXT-USAGE` step in the fixture-drill battery, which is
  the one that reads `context-window-clean.json` +
  `context-usage-86pct.trajectory.jsonl` off disk exactly the way a real tick
  would, rather than in-line synthetic data.
