# @blackceo/wise-elders-core: canonical contracts (CWE-003) - GENERATED consumer artifact

Proposed internal package identity (directive Section 6.2). This is not an
assertion that the package exists on npm; do not publish it publicly without
authorization.

**This folder is a generated consumer artifact. Do not hand-edit it.**
The single definition source is the canonical contracts home in
trevorotts1/openclaw-onboarding (CWE-003, coordinator decision D-006):

- `77-council-of-wise-elders/runtime/src/contracts/**`
- `77-council-of-wise-elders/schemas/**`

Regenerate this tree with `tools/generate-cc-consumer.mjs` from the
canonical folder and prove parity with `tools/verify-cc-parity.mjs` from
the same folder. See GENERATED.md in this folder for the provenance record
of the current generation. Fix contract defects in the canonical source,
regenerate, and re-verify; never patch this copy.

## Contents

- `schemas.ts`: the single schema source (zod), generated from the
  canonical definitions. Sessions, brief revisions, sources/evidence,
  cards, conditions, verdicts, jobs, events, approvals, action proposals,
  settings, and receipts, with all enums, scope fields, revision rules,
  unknown/null handling, supported modes, and typed errors.
- `types.ts`: TypeScript consumer types generated from the same definitions
  (z.infer), never hand-maintained copies.
- `generated/json-schemas.json`: JSON Schema artifact generated from the
  same definitions by `generate.ts`. The drift test regenerates it and
  compares byte for byte.
- `canonical-json.ts`: the one canonical JSON serializer (sorted keys,
  UTF-8, duplicate keys rejected, NaN/infinity rejected, money as integer
  minor units, unknown as null) plus the strict parser.
- `sha256.ts`: pure TypeScript SHA-256, so hashes agree across consumers
  with no host crypto dependency (test contract T148).
- `state-machine.ts`: the canonical session transition table with expected
  version and actor checks (Sections 15.1, 11.7).
- `scoring.ts`: deterministic scoring arithmetic and label bands
  (Section 12), with golden vectors in `golden-vectors.ts` (Section 32.2).
- `diagnostic-retention.ts`: the DiagnosticRetentionPolicy behavior of
  Section 16.6 (defaults, bounds, single-sink capture decisions).
- `fixtures/examples.ts`: valid and invalid fixtures; each invalid fixture
  breaks exactly one named rule.
- `contracts.test.ts`: Tier A unit tests, including T148.

## Core purity rule

The core logic imports no host, UI, network, filesystem, clock, or random
modules. Clock and ID generation enter only through the `Clock` and
`IdSource` seams in `primitives.ts`. The two exceptions are deliberate and
outside the core logic: `generate.ts` writes the JSON Schema artifact only
when invoked directly as a script, and `contracts.test.ts` uses host crypto
and filesystem as the independent second consumer T148 requires.

## Run the tests

```bash
node --import tsx --test src/lib/council/contracts/contracts.test.ts
```

## Regenerate the JSON Schema artifact

```bash
node --import tsx src/lib/council/contracts/generate.ts
```
