# Runtime source (CWE-004 foundation)

- `contracts/`: the canonical CWE-003 contracts. Read-only for CWE-004;
  consumed, never edited.
- `cli/`: the CWE-004 portable core foundation:
  - `host-ports.ts`: the injected host ports of directive Section 5.1.
  - `engine.ts`: the deliberation engine (state machine, budget and
    lease fencing, card validation, deterministic crux extraction,
    draft resolution, scoring via the contracts module, verdict).
  - `local-store.ts`: standalone SQLite store (`node:sqlite`) in the
    per-user data directory; local schema
    `wise-elders.local-store/v1`, not the CWE-005 migration set.
  - `local-host.ts`: the standalone host composition; no live transport
    and no grant service are composed by default.
  - `budget.ts`, `leases.ts`: in-process budget ledger (Section 15.6)
    and operation leases (Section 15.8: 60 second TTL, 15 second
    heartbeat, fencing epochs).
  - `paths.ts`: per-user data locations (Section 16.1); state never
    lives inside the synchronized skill folder.
  - `dispatcher.ts`, `main.ts`: the `blackceo-council` CLI surface
    (Section 25.3) with stable typed errors.
  - `fixture-transport.ts`: deterministic fixture transport and the
    labeled sample session; tests and replay only, never production.
- `providers/`: the CWE-009 compatible HTTP and local transports:
  - `selection.ts`: the pinned CWE-008 route-selection snapshot shapes
    (mirrored across the repo boundary), selection freezing and
    canonical hashing, identity-level derivation, and the
    route-resolution guard (mirror of CWE-008 applyHostResolution).
  - `compatible.ts`: the OpenAI-compatible HTTP transport: one
    transport per pinned selection, byte-identical wire model, route
    deadlines (verified route deadline, else the displayed 600 second
    initial default), bounded single retry reserved in the budget
    ledger, provider_submitted_unresolved as a first-class state, and
    safe attempt records.
  - `ollama.ts`: the local profile of the same adapter (loopback
    daemon endpoint, local/cloud identity preserved, no daemon side
    effects).
  - `http-core.ts`: the single-attempt wire executor: deadline and
    cancellation, failure classification, JSON and SSE envelope
    parsing, structured reported identity only.
  - `url-policy.ts`: endpoint assessment (Section 28.4): metadata and
    link-local targets blocked, credentials in URLs rejected,
    redirects never followed, configured loopback allowed.
  - `reasoning.ts`: the explicit reasoning-effort mapping table
    (Section 13.5); `auto` sends no vendor parameter, unmapped levels
    are refused, never renamed.
  - `diagnostics.ts`: the Section 16.6 diagnostic sink: safe metadata
    only, raw bodies memory-only and uncaptured without a protected
    store, planted-secret capture refusal.
  - `errors.ts`: typed transport errors carrying the engine's
    `retryable` and `unknownCompletion` contract flags.
- `index.ts`: the package surface. Importing it has no side effects.
