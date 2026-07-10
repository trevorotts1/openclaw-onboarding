# Drill D-S8 -- secret leaked into transcript/log, value-free by construction

## What it proves

A secret-shaped value appearing in NEW log bytes is always caught, the finding is
ALWAYS value-free (file:line + CLASS only -- the matched text itself never appears
in the event record, the alert, or any digest), and the scan never re-examines bytes
it has already scanned (the persisted per-log offset in the ledger's `offsets`
table), so re-running the same tick twice never double-alerts on the same bytes.

## Fixture / input

A synthetic log excerpt containing one line with a secret SHAPE recognized by the
reused Skill 59 class detector (`scan-no-secrets.sh`'s `provider_sk` shape: a
`sk-`-prefixed token of 20+ characters) built at drill-run time from a clearly
synthetic, low-entropy character run (never a real key, never committed to the
repo as a static fixture -- generated in-memory by the drill itself, matching the
convention `tests/fixtures/README.md` documents for the S1/S2 Anthropic-family
case: synthetic secret-shaped material is a self-test/drill-time construction, not
a committed fixture, precisely so no scanner ever has to special-case a committed
file). A second synthetic log excerpt with the SAME line already scanned once (the
offset advanced past it).

## Pass condition

- First pass: exactly one P1 event, class=`secret`, `provider_sk`, reporting
  `file:line` only. Grepping the full event record (JSON or printed form) for the
  synthetic secret text itself returns NO match anywhere -- not truncated, not
  partially reproduced, not hashed-and-shown.
- Second pass (same log, offset already advanced past the flagged line, no new
  bytes appended): zero new events. The `offsets` table advancing is what makes S8
  read only NEW bytes each tick.
- Third pass: append one MORE secret-shaped line after the offset. Exactly one new
  P1 event fires, for the new line only -- the already-scanned line is not
  re-reported.
