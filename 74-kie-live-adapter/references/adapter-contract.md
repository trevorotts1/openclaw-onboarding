# Adapter contract

Source of truth for the vendor side: KIE's official kie-models instructions (see vendor-research.md). This file states what the adapter promises.

## Result shape (every command)

provider "kie"; adapter "74-kie-live-adapter"; adapter_mode off|shadow|active; backend "native-live"; model_id; capability; schema_source ("schema:live", "schema:cache", "catalog:live", "catalog:cache"); schema_fetched_at; task_id; state validated|queued|running|success|fail|skipped; result_urls []; saved_paths []; credits_consumed null or number; warnings []; fallback_used bool; raw_family market|sync|other; error null or {code, msg}; data {}.

## Endpoints used

| Purpose | Call |
|---|---|
| Catalog | GET https://api.kie.ai/api/v1/models (fetched once unfiltered, filtered locally) |
| Schema | GET /api/v1/models/<model>/schema (slash not encoded) |
| Submit (market) | POST /api/v1/jobs/createTask {model, input, callBackUrl?} -> data.taskId |
| Submit (sync) | POST to the path the schema declares |
| Poll | GET /api/v1/jobs/recordInfo?taskId= (waiting, queuing, generating are running; success, fail are final) |
| Refresh link | POST /api/v1/common/download-url {url} -> data is a bare URL, 20 minutes, KIE-hosted URLs only |
| Credits | GET /api/v1/chat/credit -> data is a number |
| Upload | https://kieai.redpandaai.co /api/file-base64-upload (10 MB or less), /api/file-stream-upload (larger), /api/file-url-upload |

Auth is `Authorization: Bearer` only. A header named apikey returns 401. Dead (404): /api/v1/account/balance, /api/v1/user/credits, /api/v1/jobs/create, /api/v1/veo/task.

## Behavior promises

- The body `code` is checked on every response. Body code 429 is retried (rejected requests never enter the queue), up to two retries. 401, 402, 404, 422, 433, 455 are never retried.
- createTask is not retried after a network error.
- `openapi: null` returns state fail, code schema_not_synced; no path is invented.
- $ref is resolved locally: segments are percent-decoded and matched literally, trailing spaces kept.
- oneOf: at least one branch must validate and fields may not be mixed across branches.
- Results: `response.resultUrls`; Suno audio at `response.data[].audio_url`; Suno text at `response.resultObject` (kept in data.result_object). `resultJson` is parsed when `response` is absent.
- Polling starts at 3 seconds, backs off by 1.5 up to 15 seconds, and stops at a configurable deadline (default 300). A deadline returns state running with error code timeout and keeps the task id.
- Saving: result files are fetched without the API key. On 403, 404 or 410 the link is refreshed once through download-url and retried once.
- Uploads: realpath resolved, must be a regular readable file, 1 byte to 512 MB, mime image, video, audio or pdf. expiresAt is honored if returned, otherwise assume 24 hours.
- Drift receipts: one JSON line per catalog, schema or validate event in `<cache>/receipts/YYYYMMDD.jsonl`, with a digest and a drift flag against the last digest seen. Redacted.
- Environment hooks (tests only): KIE_LIVE_API_BASE and KIE_LIVE_UPLOAD_BASE are honored only when they point at localhost. KIE_LIVE_MIN_SPACING and KIE_LIVE_POLL_INITIAL tune timing.

## v1.1 commands

- `price`: `data.pricing_desc`, `credits_min`, `credits_max`, `unit` (per-job, per-second, per-1k-chars, per-image, per-1m-tokens; "free" parses as 0 credits per-job), `units`, `credits_estimate` (highest tier, x units for every unit except per-job), `preflight_required` (estimate x 1.30, rounded up to 0.01), `price_source` (catalog:live, catalog:cache, registry). No numeric price: no estimate and a warning. Unknown model everywhere: fail `price_unavailable`.
- `preflight`: price, then `GET /api/v1/chat/credit`. `validated` with `data.ok`, or `fail` code `insufficient_credits` with `data.shortfall`. No numeric price: fail `price_unestimable`.
- `success-rate`: `GET /api/v1/models/<id>/success-rate`; `data.avg_success_rate` is the mean of non-null `successRate` buckets, null (with a warning) when there is no monitoring data. Shares the 1 request per second discovery budget.
- `prompt-budget`: `data` has `field`, `max`, `floor` (ceil 80 percent), `target_min` (ceil 95 percent), `target_max`, `verbatim`, `limit_source`, `status` (OK, BELOW_TARGET, BELOW_FLOOR, ABOVE_MAX, VERBATIM, UNKNOWN, NO_PROMPT_FIELD), `exit_code`. With `--check` also `chars` (surrounding whitespace stripped), `percent_of_max`, `add_to_floor`, `add_to_target`, `cut`. Process exit: 0, 3 (state fail, code prompt_below_floor), 4 (state fail, code prompt_above_max).
- `latest-family`: `data.family`, `version`, `variant`, `routes` (capability to model id), `default`, `chosen_by` (variant-match, only-candidate, success-rate, price), `previous_default`, `changed`, `source` (live, cache, registry), `candidates`. A live change writes a promotion receipt and updates `<cache>/promotion-state.json`; a registry answer never promotes. No eligible generation: fail `latest_unavailable` (callers fall back to their own default).
- `validate` registry fallback: result `schema_source` is `registry` with a warning naming the snapshot; unknown models still return the live error.
- Environment hooks (tests only): KIE_LIVE_REGISTRY (registry path), KIE_POLICY_ROOT (where policy-owner skills are read).

## Registry file

`references/kie-model-registry.json`: `schema_version`, `generated_at`, `source` (live-api or public-docs), `counts`, `models[]`. Model row: `id`, `provider`, `title`, `taskType`, `family`, `version`, `variant`, `schema` (`readable`, `kind`, `submit_path`, or `error`), `schema_paths`, `callback_supported`, `required`, `input_fields`, `branches`, `prompt_field` (`name`, `maxLength`, `max_source`, `verbatim`, `limits_listed`), `verbatim_fields`, `pricing` (`raw`, `status`, `credits_min`, `credits_max`, `unit`, `credits_estimate`).
