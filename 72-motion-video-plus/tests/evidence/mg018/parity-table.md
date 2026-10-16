# MG-018 C05 verdict-parity evidence

Recorded from the verification run of `runtime/tests/run-catalog.ts` in
worktree wt-mg018 (branch skill72-mg018, base 9aa4e54dd) on 2026-10-14.
Each case stages a complete scene document into the shipped
powerpoint_graphic fixture job and compares three verdicts: the catalog
(`ComponentRegistry.validateSceneProps`), the shipped TypeScript
validator (`validateJob`, first error category), and the shipped Python
validator (`scripts/motion_contracts.py validate`, first error
category). The corpus itself is committed at
`tests/fixtures/catalog/parity-corpus.json` and is re-run on every
`npm test`; this file is the static record of that run.

Result of the recorded run: catalog suite 59/59 checks passed, 0
failed, including all 20 parity cases with the Python validator running
and matching (no skip notes).

| Case | Verdict (all three) | Shipped category (TS and Python) | Catalog category |
|---|---|---|---|
| valid-fixture | ACCEPT | - | - |
| valid-engine-hyperframes | ACCEPT | - | - |
| valid-layout-portrait | ACCEPT | - | - |
| valid-headline-change | ACCEPT | - | - |
| reject-extra-key | reject | MG_SCHEMA_INVALID | MG_SCHEMA_INVALID |
| reject-missing-copy | reject | MG_SCHEMA_INVALID | MG_SCHEMA_INVALID |
| reject-unknown-component-c99 | reject | MG_UNKNOWN_COMPONENT | MG_UNKNOWN_COMPONENT |
| reject-component-c06-unavailable | reject | MG_UNKNOWN_COMPONENT | MG_CAPABILITY_UNSUPPORTED |
| reject-version-2 | reject | MG_SCHEMA_INVALID | MG_SCHEMA_INVALID |
| reject-motion-kind | reject | MG_SCHEMA_INVALID | MG_SCHEMA_INVALID |
| reject-overshoot-true | reject | MG_SCHEMA_INVALID | MG_SCHEMA_INVALID |
| reject-duration-zero | reject | MG_SCHEMA_INVALID | MG_SCHEMA_INVALID |
| reject-assertions-empty | reject | MG_SCHEMA_INVALID | MG_SCHEMA_INVALID |
| reject-data-path-escape | reject | MG_SCHEMA_INVALID | MG_SCHEMA_INVALID |
| reject-engine-legacy | reject | MG_SCHEMA_INVALID | MG_SCHEMA_INVALID |
| reject-motion-end-equals-start | reject | MG_TIMELINE_INVALID | MG_TIMELINE_INVALID |
| reject-hold-past-duration | reject | MG_TIMELINE_INVALID | MG_TIMELINE_INVALID |
| reject-missing-component-id | reject | MG_SCHEMA_INVALID | MG_SCHEMA_INVALID |
| reject-bad-assertion-kind | reject | MG_SCHEMA_INVALID | MG_SCHEMA_INVALID |
| reject-missing-component-version | reject | MG_SCHEMA_INVALID | MG_SCHEMA_INVALID |

The single category divergence (reject-component-c06-unavailable) is
deliberate and documented in `references/component-catalog.md`: the
contracts layer has not registered C06 at all, so the shipped
validators report `MG_UNKNOWN_COMPONENT`; the catalog has registered
C06 by identity but cannot dispatch it until its schema, proof
contract, and tests land together under MG-016, so it reports
`MG_CAPABILITY_UNSUPPORTED` (Section 16.9, exit class 3). The
accept/reject verdict is identical.
