# Changelog - Skill 74 KIE Live Adapter

## [1.1.4] - 2026-10-08 - INF002

- Install QC reads the version from skill-version.txt instead of a hardcoded v1.1.2 that failed on every box after a bump (INF002 D).

## [1.1.2] - 2026-10-06
- `--allow-host` now also governs the download-url refresh link and every redirect (a handler re-checks each Location: allow-listed host and https), ignores blank values (blank-only fails closed), and any result URL with no hostname is refused.
- Consumer options for the one-KIE-path consolidation of Skills 25, 37, 58 and 59: result downloads send a product User-Agent by default (urllib's default is 403-blocked by the result CDN); `save` and `run` take `--user-agent` (replaces it, result download only) and a repeatable `--allow-host`; `run` saves a direct result link returned by a synchronous endpoint (data.resultUrls or data.response.resultUrls). Tests: `tests/test_consumer_options.py`.

## [1.1.1] - 2026-10-06
- `submit` and `run` accept `--callback-url URL` (overrides `callBackUrl` in the request file; still http or https only). This is the production route for Skill 46 (`kie-callback-relay`): the relay's signed URL is passed on the command line and the normalized result (`task_id`, `model_id`, `data.callback_url`) is what Skill 46 `adoptAdapterTask` consumes. New test `test_callback_url_flag_overrides_request_file`.

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
