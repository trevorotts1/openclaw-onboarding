# Council of Wise Elders , portable runtime (current composition)

The Council runtime contains the typed protocol, SQLite local store,
authorization service, route discovery and provider transports. **An offline
doctor PASS is not a completed, usable, live Council.** It proves only that
the checks actually run by that command passed. The `doctor --json` response
separates `ok` (core diagnostics) from `usable` (end-to-end readiness);
`usable` remains `false` until the still-unverified installed/live layers
are implemented and independently accepted.

## What exists in this build

- `npm ci && npm run build` compiles TypeScript, bundles the CLI and copies
  the canonical local-store migration asset into the runtime distribution.
- `npm test` runs unit and controlled-transport tests. The `sample run`
  command is explicitly synthetic and does **not** prove a paid council run.
- Standalone `create`, `status`, controlled `start`, `replay` and
  Markdown/JSON report paths are composed. A run record is required; it is
  not inferred from a CLI flag or an agent's statement.
- Existing configured Claude-nine and supported OpenClaw OpenAI-compatible
  routes can be discovered, composed, and listed by `models` where the
  machine's real configuration, executable and credential reference permit.
  Discovery is **not** proof the provider is callable, and the host must not
  silently change the selected route or require Nine Router for OpenClaw.
- `probe` still returns a typed FEATURE_NOT_READY error; this is a
  separately authorized live probe to be completed under WER-006.
- The installed advisor source packs are present in the source tree, but
  the standalone host's pack loader and independent source qualification
  still require WER-012 and WER-013 acceptance. Bibliography-only coverage
  must not be advertised as verified source knowledge.
- The durable job worker, end-user browser front door, production PDF,
  and full installed Mac/Windows/VPS Council journeys are **not certified**
  by the local `doctor` command.

## Installation and verification boundaries

The Council's SQLite execution path requires **Node 22.13+ or Node 24+**,
not Node 20. The runtime installer must preflight the exact executable
and SQLite insert/select before modifying an installation (WER-003).

Runtime `node_modules/` and `dist/` are generated outputs. They must
not alter the portable skill's source manifest. Generate the current
source manifest and distribution archive through
`../scripts/build-bundles.mjs`, then use `../scripts/verify-bundles.mjs`
to verify the package. Rebuild and regenerate as required by the
owning release process; do not hand-edit the generated archive.
State, sessions, budgets and client secrets belong outside the skill tree.

The integration/QA definition of **usable** requires a real authorized
model call, a supervised durable worker, the nine correctly grounded
advisor seats, a responsive authenticated UI, the persisted verdict
and matching history/replay/report output. Capture that evidence on
the *installed* build, not only through fixtures or an old green check.

See the hybrid repair package's WER-002, WER-006, WER-010 through WER-028
tasks and the installed-host acceptance runbook for remaining gates.
