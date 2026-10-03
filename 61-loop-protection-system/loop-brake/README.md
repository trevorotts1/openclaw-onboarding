# loop-brake (Skill 61, Fix 9)

Small real-time brake plugin for OpenClaw (October plugin shape). It blocks a tool call; it never asks for approval. It makes zero model calls.

**Ships DISABLED.** Two independent layers:

1. The manifest omits `enabledByDefault`, so OpenClaw leaves the plugin disabled until someone enables it.
2. Even when enabled, `register()` installs no hooks unless the existing Skill 61 rollout gate is open (same precedence as `scripts/activate-loop-protection.sh`: `OPENCLAW_LOOP_PROTECTION_ROLLOUT` env override, then `config/rollout.json` `fleet_rollout_enabled === true`, else held). `config/rollout.json` stays `false`; a test asserts it.

## What it does

| Hook | Matcher | Behavior |
|---|---|---|
| `before_tool_call` | `["sessions_send"]` | Hash the normalized message (preamble stripped, whitespace collapsed) per (source session, target). The third identical hash within the window is blocked with `Already delivered; do not resend. Use timeoutSeconds: 0 or wait for the late reply.` |
| `after_tool_call` | all tools | Count results that failed and carry an auth-refusal marker (D6 two-layer test), per (run, tool). Log once at warn and once at P1. |
| `before_tool_call` | all tools | Block the call that follows `doctrine_max_attempts` counted refusals for the same (run, tool) with `Fail-closed dependency: stop and report once (N40)`. |

## Config is read at runtime, never copied

- `config/thresholds.json` `d7_cross_run_resend`: `window_seconds` (300), `p1_repeat` (3 = block), `warn_repeat` (2).
- `config/thresholds.json` `d6_futile_retry_burst`: `doctrine_max_attempts` (2), `warn_failclosed_calls` (3), `p1_failclosed_calls` (5).
- `config/signatures.json` `fail_closed_markers`: `markers`, `result_scan_exempt_tools`, `error_shape_patterns`.

This plugin edits none of those files. The payload hash is byte-identical to `scripts/loop_common.py` `cross_run_payload_hash` (a test runs both).

## Privacy

Only hashes and counters live in memory. No message body, tool argument or tool result is stored or logged, and nothing is written to disk (tests assert both). Any internal error passes the call through (fail-open): a missed brake is recoverable, a false block is the risk.

## Install note

`config/` is found at `../config` relative to this folder, so install by linking or loading this folder in place inside the skill. If the folder is copied elsewhere, the config is not found, the gate reads as held, and the plugin stays inert. That is the safe direction.

## Tests (offline, no network, no live sends)

```
node --test 61-loop-protection-system/loop-brake/tests/brake.test.mjs
```

Needs Node 18 or later and `python3` (for the hash parity test). `openclaw plugins validate` only covers tool plugins (bundled hook plugins fail it identically), so host loading is proven by the operator-box live test in a later wave, not here.
