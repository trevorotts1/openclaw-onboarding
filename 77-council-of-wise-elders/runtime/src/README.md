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
- `index.ts`: the package surface. Importing it has no side effects.
