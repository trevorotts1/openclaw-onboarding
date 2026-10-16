# Council Runtime: CWE-004 foundation built

This directory is the Council of Wise Elders deliberation runtime.
The CWE-004 portable core foundation is built here: canonical
contracts (CWE-003, read-only for this unit), injected host ports, a
standalone local host with a SQLite store in the per-user data
directory (never inside this skill folder), a deliberation engine that
runs the contracts state machine end to end, budget and operation
lease implementations, and the `blackceo-council` CLI dispatcher.

What is true today, honestly:

- `npm run build` compiles the package (tsc) and bundles the CLI to
  `dist/blackceo-council.mjs`, which runs under bare Node.
- `npm test` runs the CWE-004 foundation suite (24 tests) against the
  real implementations; `npm run test:contracts` re-runs the CWE-003
  contracts suite (36 tests).
- The standalone host composes NO live model transport and NO run
  authorization service. Starts on uncomposed routes refuse with
  `COUNCIL_ROUTE_UNAVAILABLE`, and starts without a resolvable run
  grant refuse with `RUN_AUTHORIZATION_REQUIRED`. Nothing is simulated.
- Live transports (CWE-009, CWE-010), the run-authorization service
  (CWE-049), canonical migrations (CWE-005), the full repository layer
  (CWE-006), durable worker scheduling (CWE-027), the production budget
  and capacity service (CWE-028), and PDF report export (CWE-038) are
  downstream units that compose through the ports defined here.
- The deterministic fixture transport exists only for isolated tests
  and the labeled sample path (`blackceo-council sample run`). It is
  not a model, not a qualification, and spends nothing.

`dist/` and `node_modules/` are generated and never committed.
