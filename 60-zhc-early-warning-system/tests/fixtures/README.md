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
