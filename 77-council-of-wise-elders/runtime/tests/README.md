# Runtime tests (CWE-004)

Foundation tests for the portable core, run with `npm test`
(`node --import tsx --test tests/*.test.ts`) against the real
implementations and real temporary SQLite databases:

- `core.test.ts`: data directory rules, budget ledger ceilings and
  unknown-completion accounting, operation lease fencing, local store
  round trips, compare-and-swap conflicts, event sequencing, card
  uniqueness, verdict and checkpoint persistence.
- `engine.test.ts`: full golden-score run with an honest WAIT verdict,
  grant refusal with zero dispatches, uncomposed route refusal, a
  failing seat blocking visibly and resume reusing completed cards,
  consult mode with no invented scores, the quick mode Round 3 skip
  predicate, and replay spending nothing.
- `cli.test.ts`: dispatcher behavior end to end (doctor, create,
  status, verdict not ready, authorization and probe honesty, sample
  run, exports, typed error envelopes), a data directory path with
  spaces, skill-tree data rejection, and a package import side-effect
  check in a subprocess.

The CWE-003 contracts suite lives at `src/contracts/contracts.test.ts`
and runs with `npm run test:contracts`.
