# Changelog - Skill 74 KIE Live Adapter

## [1.0.0] - 2026-10-05
- New skill. One standard-library Python entrypoint (scripts/kie_live_adapter.py) that implements the contract KIE documents in its official kie-models skill: live catalog, live schema, schema validation, file upload, createTask, recordInfo polling, result download with link refresh, and credit balance.
- Default mode is shadow: discovery, schema and validation run and write drift receipts, but paid dispatch is refused so nothing is generated twice or charged twice. Modes: off, shadow, active.
- Never picks, rewrites or auto-routes a model. Pinned models (for example the fleet image pin) pass through unchanged.
- Vendor drift probe (probe box only) (scripts/vendor_skill_probe.sh) with an approved fingerprint in vendor-approval.json. The vendor package is never installed on client boxes.
- Hermetic offline tests (qc-74-kie-live-adapter.sh). Live checks are a separate opt-in script (scripts/live_smoke.sh).
