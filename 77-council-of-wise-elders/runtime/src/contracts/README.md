# @blackceo/wise-elders-core: canonical contracts (CWE-003)

Proposed internal package identity (directive Section 6.2). This is not an
assertion that the package exists on npm; do not publish it publicly without
authorization.

**This folder is the canonical home of the Council of Wise Elders
contracts** (directive Section 34, CWE-003 owned paths; coordinator
decision D-006). It is the single definition source for the engine, the
Command Center application, and the 999 portable bundle. The Command
Center copy at `src/lib/council/contracts/**` is a generated consumer
artifact of these definitions (see `tools/` below); never the reverse.

## Contents

- `schemas.ts`: the single schema source (zod). Sessions, brief revisions,
  sources/evidence, cards, conditions, verdicts, jobs, events, approvals,
  action proposals, settings, and receipts, with all enums, scope fields,
  revision rules, unknown/null handling, supported modes, and typed errors.
- `types.ts`: TypeScript consumer types generated from the same definitions
  (z.infer), never hand-maintained copies.
- `../../../schemas/json-schemas.json`: the generated JSON Schema artifact
  for these contracts, produced by `generate.ts` into the skill-level
  `schemas/` directory. The drift test regenerates it and compares byte
  for byte.
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
- `tools/generate-cc-consumer.mjs`: emits the Command Center consumer
  artifact from these canonical definitions.
- `tools/verify-cc-parity.mjs`: byte-for-byte drift test proving the
  consumer artifact matches canonical generation.
- `tools/cc-consumer-README.md`: the README template emitted into the
  consumer artifact.

## Core purity rule

The core logic imports no host, UI, network, filesystem, clock, or random
modules. Clock and ID generation enter only through the `Clock` and
`IdSource` seams in `primitives.ts`. The two exceptions are deliberate and
outside the core logic: `generate.ts` writes the JSON Schema artifact only
when invoked directly as a script, and `contracts.test.ts` uses host crypto
and filesystem as the independent second consumer T148 requires.

## Toolchain bootstrap (local only, nothing committed)

The runtime package manifest is owned by CWE-004 and carries no dependency
pins yet. To run the contracts suite in this home, install the exact tool
versions used by the Command Center consumer (zod 4.4.3, tsx 4.22.4,
typescript 5.9.3) into the runtime folder without saving them into the
manifest, and remove `runtime/node_modules` again before committing:

```bash
cd 77-council-of-wise-elders/runtime
npm install --no-save --ignore-scripts --no-audit --no-fund zod@4.4.3 tsx@4.22.4 typescript@5.9.3 @types/node@20.19.42
```

## Run the tests

```bash
cd 77-council-of-wise-elders/runtime
node --import tsx --test src/contracts/contracts.test.ts
```

## Regenerate the JSON Schema artifact

```bash
cd 77-council-of-wise-elders/runtime
node --import tsx src/contracts/generate.ts
```

## Generate and verify the Command Center consumer artifact

```bash
node 77-council-of-wise-elders/runtime/src/contracts/tools/generate-cc-consumer.mjs \
  --target <command-center>/src/lib/council/contracts
node 77-council-of-wise-elders/runtime/src/contracts/tools/verify-cc-parity.mjs \
  --consumer <command-center>/src/lib/council/contracts
```
