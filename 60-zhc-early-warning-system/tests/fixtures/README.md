# Skill 60 test fixtures

Every file in this directory is SYNTHETIC. No client names, no real emails or phone
numbers, no real credentials, no real box identifiers -- only `example.com`-style
placeholders and made-up ids. Nothing here is read by any production code path; these
exist for the sentinel's own test suite (and for `verify.sh`'s drill battery) to
exercise the ten signals against known inputs with a known, checkable answer.

Every `openclaw.json`-shaped fixture uses the EXACT dot-paths named in
`../../config/monitored-keys.json`, so a change to that catalog is the single source
of truth these fixtures are built from.

## `baseline-clean.json`

A clean, fully-populated baseline: every monitored key present, every model id
non-Anthropic and non-paid-family, every safety cap at the fleet-floor value, one
cron entry (the sentinel's own 15-minute tick, `delivery: "silent"`). This is the
starting point every other fixture below is derived from by exactly ONE targeted
change, so a diff between any variant and this file IS the signal under test.

## `cap-raise.json`

`baseline-clean.json` with `agents.defaults.subagents.maxConcurrent` raised
16 -> 64 and no matching `baseline_stamps` approval. Exercises S4 (safety-cap raise,
never-silently) -- the unstamped-raise P1 case. See `../drills/D-S4.md`.

## `subtractive-misconfig.json`

`baseline-clean.json` with `agents.defaults.compaction.memoryFlush.softThresholdTokens`
set to 900000 against a `_contextWindow` hint of 128000, so the effective ceiling
(`contextWindow - softThresholdTokens`) is negative. Exercises S3's broken-config
case -- a guaranteed crash regardless of usage, which is the ONE context case that
reaches the operator as a P1 under D5 (running-low never does; it stays local to the
box's own agent). See `../drills/D-S3.md`.

## `context-window-clean.json` + `context-usage-86pct.trajectory.jsonl`

A PAIR of fixtures exercising `_context_usage()` and the D5 running-low branches
end to end -- the two-part fix for the previously-dead-code S3 running-low path
(nothing computed live usage; the tick never passed `usage_pct` into `sig_s3()`).

- `context-window-clean.json`: `baseline-clean.json` plus a `_contextWindow` hint
  (128000) and a SANE `softThresholdTokens` (20000), so the effective ceiling is
  108000 -- a healthy, non-broken box (contrast with `subtractive-misconfig.json`,
  which is deliberately broken).
- `context-usage-86pct.trajectory.jsonl`: two synthetic `model.completed` events for
  the same session in the REAL trajectory shape -- usage 3 levels deep at
  `data.usage`, the normalized `{input, output, cacheRead, cacheWrite, total}` object
  the writer emits. The LATEST carries `input: 82880` + `cacheRead: 10000`, so its
  prompt-side occupancy is `92880`, exactly 86% of the 108000 ceiling above
  (`92880 / 108000 = 0.86`). Its `output: 50000` and billed `total: 147880` are
  present ON PURPOSE: occupancy uses the input/prompt side only, so a `total`/spend
  read here would compute 137%, not 86% -- the fixture discriminates the two metrics.

Together they prove `_context_usage()` reads the newest trajectory file's latest
event, computes `usage_pct` against the SUBTRACTIVE ceiling (reusing
`ews_common.subtractive_broken`'s own arithmetic), and that the resulting 86% feeds
`sig_s3()`'s handoff branch (route: the box's own agent, D5) -- and, on the
OPERATOR's own box only, the narrow Lane-2 self-notice exception. See
`../drills/D-CONTEXT-USAGE.md`.

**Field name: CONFIRMED (this was formerly an OPEN QUESTION).** The trajectory token
field is now confirmed from the OpenClaw 2026.6.11 trajectory-writer source
(read-only, no live box): a `model.completed` row carries `data.usage` (3 levels
deep) = `getUsageTotals()` = `{input, output, cacheRead, cacheWrite, [reasoningTokens],
total}` (`selection-CVIPXpKT.js:14200-14216`, `:4310-4339`; `usage-C67Kbb7n.js:44-64`).
Context-window OCCUPANCY is the prompt/input side = `input + cacheRead`, which is
OpenClaw's own `prompt_tokens` definition (`usage-C67Kbb7n.js:68-70, :83`) -- NOT
`output`, NOT the billed `total` (that is Skill 61's SPEND metric). The prior
candidate `contextTokens` was a guess: it is a SESSION-STORE field
(`agent-runner.runtime-BriI2__w.js:2310-2377`), not a trajectory-event field, and the
old reader also used the wrong nesting depth (top-level `usage`, 2 levels) and raw
provider aliases (`input_tokens`/`total_tokens`) the writer never emits -- so it was
blind on every real row. See the source-cited comment above `_extract_context_tokens`
in `ews_sentinel.py`.

## `announce-cron.json`

`baseline-clean.json` plus a second cron entry, `daily-report`, with
`"delivery": "announce"` bound to a non-operator target. Exercises S10's
announce-to-non-operator P1 case -- the exact `--no-deliver` client-spam trap this
signal exists to catch. See `../drills/D-ALERT.md`.

## `anthropic-fallback.trajectory.jsonl`

Three synthetic `*.trajectory.jsonl` events for S2 (runtime fallback, ground truth).
Two lines are in-allowlist (`provider: "openrouter"`, `modelId: "glm-5.2"`); the
third is deliberately OUT of the baseline allowlist (`provider: "openai"`,
`modelId: "gpt-paid"`) so it exercises the "any out-of-allowlist runtime event is a
P2, escalating to P1 for a paid/Anthropic-family id on a client box" branch of S2
WITHOUT the Anthropic-family escalation itself.

**Why there is no Anthropic-family line in this file, on purpose:** this repo's
merge gate runs a static Anthropic-identifier scanner
(`59-anthology-engine/scripts/guard-no-anthropic-runtime.py`) over every shipped
file, including this test tree. That scanner is designed to catch exactly the value
SHAPE a real leak would have -- a `claude-<version>` id, an `anthropic/<model>`
routed id, and so on -- and a committed fixture carrying one of those shapes would
either (a) trip the gate, defeating its purpose, or (b) require the gate to special-
case this file, which weakens the gate for every other file in the repo. Neither
trade is worth taking for a fixture.

The Anthropic-family P1 escalation path (S1/S2's "family or paid id on a client box
escalates to P1") is instead exercised by the sentinel's OWN in-code self-test, which
assembles the banned token from fragments AT RUNTIME (the same convention
`guard-no-anthropic-runtime.py` and `model_router.py` already use for their own
source) so the banned literal never ships as committed data anywhere in this repo,
including here. Run that self-test with each sentinel script's own `--self-test`
flag (see `HOW-TO-USE.md`'s `verify` verb); it is the authoritative proof that the
Anthropic-family branch of S1/S2 actually fires, and it is a stronger proof than a
static fixture would have been, because it also proves the runtime assembly itself
still resolves to a real deny hit and not a typo.

## Parsing and scanning

Every `.json` fixture here is valid JSON (`python3 -c "import json;
json.load(open(F))"`). The `.jsonl` fixture parses line-by-line the same way. All
files in this directory are scanned clean by the repo's three merge-gate scanners
(`guard-no-anthropic-runtime.py`, `scan-no-client-identifiers.sh`,
`scan-no-secrets.sh --strict`) -- see the skill's build notes for the exact
invocations; if a scanner ever flags a file in this directory, the fixture is wrong
and gets fixed, not the scanner.
