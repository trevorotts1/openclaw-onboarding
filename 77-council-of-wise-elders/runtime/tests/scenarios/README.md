# Scenario fixtures and council quality evaluation (CWE-042)

This folder is the CWE-042 evaluation harness: the fixed Section 32.5
qualification set, the mechanical rubric and qualification calculator,
and the retained evaluation records for the nine advisor packs.

Run it with:

```sh
node --import tsx --test tests/scenarios/*.test.ts
```

## Files

- `qualification-cases.json`: the fixed qualification set Q01 to Q10
  from Section 32.5. Expected facts, prohibited inferences, critical
  domains, and acceptable decision distinctions were authored before
  any generation exists. Each case carries a `case_hash` (the runtime
  `canonicalHash` of the case excluding its hash field); the suite
  recomputes every hash, so a frozen case cannot be edited quietly
  after results are seen, and thresholds cannot be changed after
  seeing results (Section 32.5).
- `rubric.ts`: the Section 32.5 mechanics as pure functions. Rubric
  weights (0.25 / 0.20 / 0.15 / 0.15 / 0.15 / 0.10, summing to 1.00),
  the run-score formula, the pass thresholds (zero unresolved hard
  failures; overall mean at least 8.5; every case mean at least 8.0;
  no run below 7.5; grounding and source fidelity at least 3 of 4 in
  every run), the baseline comparison (deficit at most 0.25, no new
  hard failure), per-mode separation, and the blind differentiation
  thresholds (80 percent overall, 60 percent per seat) with the
  identifier-stripping procedure.
- `rubric.test.ts`: hand-computed synthetic grade sets proving each
  rule mechanically, including that a NOT_RUN set never qualifies.
- `pack-evals.test.ts`: the deterministic executions that can run
  honestly without a live model (the Aliche packs' affordability
  arithmetic and gate; quotation boundaries against the real pack
  corpora and the CWE-012 fixture corpora; Jakes one-seat card
  structure; the injection screen; the Section 32.2 golden fixture
  through the CWE-026 scoring service; audit determinism; ledger and
  records consistency).
- `records/qualification-ledger.json`: every planned Section 32.5 run
  retained: 30 full-council repetitions and 30 baseline repetitions,
  all NOT_RUN with the recorded reason, plus the differentiation
  record and the mechanical decision computed over the ledger.
- `records/pack-evaluation-records.json`: per-pack, per-case verdicts
  for all 70 defined pack eval cases: 7 executed deterministically
  (Aliche arithmetic), 63 defined_not_run with reasons.

## Honesty rules held here

- No live evaluation allowance exists in this build, and no generated
  council run exists to grade. Unfunded tests stay NOT_RUN, never
  PASS (Section 32.5). Scripted fixture transports were deliberately
  not used to simulate deliberation grades: that would measure the
  script author, not the packs or the council.
- No seat qualifies above `bibliographic_only`, no quotation in the
  build is verified, and nothing in this folder upgrades a seat, a
  quote, a route, or a qualification. The records contain no passed
  evaluation, so no route may be labeled quality-qualified on this
  evidence (T036).
- `runtime_verified` remains false throughout.
