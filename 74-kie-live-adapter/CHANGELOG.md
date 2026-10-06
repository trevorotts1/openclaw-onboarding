# Changelog - Skill 74 KIE Live Adapter

## [1.1.0] - 2026-10-05
- Model registry: `scripts/build_model_registry.py` writes `references/kie-model-registry.json` for every model in KIE's live catalog (limits, enums, required fields, prompt field and max, verbatim fields, raw and parsed price). Source live-api, or public-docs when no key resolves.
- One price authority: `price` and `preflight` (balance against price x 1.30). The unit parser is built from every real video, audio and image `pricingDesc` phrasing in the live catalog (credits/s, credits / sec, credits per video second, per 1,000 characters, per image, duration prices such as "A 5-second video costs N credits" stay per-job); registry-wide tests keep per-second models from being labeled per-job.
- Limits authority and prompt budget: `prompt-budget` (80 percent floor, 95 to 100 percent target, exit 3 below the floor, exit 4 above the max); `validate` falls back to the registry and enforces maxLength, enum, minimum, maximum and required.
- GPT Image auto-latest: `latest-family` returns the newest generation with both text-to-image and image-to-image (numeric version order, variant then success rate then price, 6 hour cache, promotion receipt on change). `success-rate` added.
- `callBackUrl` (Skill 46) is recorded in the submit and run result; per-call `--mode off|shadow|active`; default mode unchanged (shadow).

## [1.0.0] - 2026-10-05
- New skill. One standard-library Python entrypoint (scripts/kie_live_adapter.py) that implements the contract KIE documents in its official kie-models skill: live catalog, live schema, schema validation, file upload, createTask, recordInfo polling, result download with link refresh, and credit balance.
- Default mode is shadow: discovery, schema and validation run and write drift receipts, but paid dispatch is refused so nothing is generated twice or charged twice. Modes: off, shadow, active.
- Never picks, rewrites or auto-routes a model. Pinned models (for example the fleet image pin) pass through unchanged.
- Vendor drift probe (probe box only) (scripts/vendor_skill_probe.sh) with an approved fingerprint in vendor-approval.json. The vendor package is never installed on client boxes.
- Hermetic offline tests (qc-74-kie-live-adapter.sh). Live checks are a separate opt-in script (scripts/live_smoke.sh).
