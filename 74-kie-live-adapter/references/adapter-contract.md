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
