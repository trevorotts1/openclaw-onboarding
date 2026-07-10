# Drill D-S3 -- context vs compaction, broken-config P1 and the D5 boundary

## What it proves

S3 has two very different outcomes for what looks like "the same" signal, and the
D5 routing boundary between them is the single most important nuance in this whole
skill to get right: running-low on context is a LOCAL matter that never reaches the
operator, while a broken subtractive-compaction config that guarantees a crash IS a
P1 to the operator. This drill proves both halves and, critically, proves the
boundary between them does not leak in either direction.

## Fixture / input

- **Broken-config half**: `tests/fixtures/subtractive-misconfig.json` --
  `agents.defaults.compaction.memoryFlush.softThresholdTokens` = 900000 against the
  fixture's `_contextWindow` hint of 128000. Effective ceiling =
  `128000 - 900000` = negative.
- **Running-low half**: `tests/fixtures/baseline-clean.json` (a SANE
  `softThresholdTokens` of 20000 against the same 128000 window, effective ceiling
  108000) plus a synthetic "live usage" value fed directly to the S3 check at 70% and
  again at 85% of that effective ceiling.

## Pass condition

- Against `subtractive-misconfig.json`: the check reports exactly one P1 event to
  the OPERATOR, key path `agents.defaults.compaction.memoryFlush.softThresholdTokens`,
  classified `broken-config` (not `running-low`), with a revert line pointing at the
  last snapshot where the ceiling was positive. This fires regardless of what "live
  usage" is fed in -- the box will crash no matter what, so the check does not wait
  to see usage before alerting.
- Against `baseline-clean.json` at 70% synthetic usage: the check emits a NOTE routed
  to the box's own agent (not the operator alert path) -- zero operator-facing
  events.
- Against `baseline-clean.json` at 85% synthetic usage: the check emits a HANDOFF
  instruction, still routed to the box's own agent -- zero operator-facing events.
- The two halves never cross: a broken-config fixture never produces a "running-low"
  classification, and a sane-config fixture at any usage percentage never produces an
  operator-facing P1.
