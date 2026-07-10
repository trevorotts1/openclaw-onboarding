# Drill D-S1-S2 -- config drift vs runtime-fallback ground truth

## What it proves

S1 (model/provider config drift) and S2 (runtime fallback, ground truth) are two
independent sources of truth for the same underlying question -- "is this box
actually running the model it claims?" -- and they must be provably independent: S1
can fire with S2 clean (the config changed but nothing ran yet), and S2 can fire with
S1 clean (the config never changed, but a fallback chain silently resolved to a
different provider at runtime). This drill exercises both paths and proves neither
one masks the other.

## Fixture / input

- **S1 path**: `tests/fixtures/baseline-clean.json` as the pinned baseline, diffed
  against a copy with `agents.defaults.model.primary` changed from `"glm-5.2"` to any
  other non-Anthropic id (for example `"deepseek-v4"`). No trajectory events needed
  for this half of the drill.
- **S2 path**: `tests/fixtures/baseline-clean.json` as the pinned baseline
  (`model_allowlist` derived from its `agents.defaults.models` map) against
  `tests/fixtures/anthropic-fallback.trajectory.jsonl`, whose third line
  (`provider: "openai"`, `modelId: "gpt-paid"`) is deliberately out of that
  allowlist while the first two lines are in it.

## Pass condition

- S1: the diffed run reports exactly one P2 event, key path
  `agents.defaults.model.primary`, measured=`deepseek-v4`, baseline=`glm-5.2`. Client
  model choice is sovereign -- the event is alert-only; nothing is changed.
- S2: the trajectory scan reports exactly one out-of-allowlist event (the third
  line), classified P2 (not P1, since `openai`/`gpt-paid` is out-of-allowlist but not
  Anthropic-family or on a client box in this drill), and reports ZERO findings for
  the first two lines.
- Running the S2 scan against a trajectory file containing ONLY in-allowlist events
  (the first two lines of the fixture, isolated) produces zero events -- proving S2
  does not fire on baseline-consistent runtime activity.
- The two checks are independent: disabling/omitting one input never changes the
  other's verdict.
