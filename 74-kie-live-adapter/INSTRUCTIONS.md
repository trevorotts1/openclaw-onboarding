# KIE Live Adapter - Instructions

Run everything from the skill 74 folder. Do not copy `scripts/kie_live_adapter.py` anywhere else, and never into a Presentations deck run directory (the render guard blocks scripts there that mention the KIE API).

All commands print one JSON object with the same keys: provider, adapter, adapter_mode, backend, model_id, capability, schema_source, schema_fetched_at, task_id, state (validated, queued, running, success, fail, skipped), result_urls, saved_paths, credits_consumed, warnings, fallback_used, raw_family (market, sync, other), error. Extra detail sits under `data`. Exit code 1 only when state is fail.

## Commands

```
python3 scripts/kie_live_adapter.py health --json
python3 scripts/kie_live_adapter.py credits --json
python3 scripts/kie_live_adapter.py discover --modality image --json        (image, video, audio, any; --query, --provider, --task-type)
python3 scripts/kie_live_adapter.py schema --model MODEL_ID --json
python3 scripts/kie_live_adapter.py validate --model MODEL_ID --payload input.json --json
python3 scripts/kie_live_adapter.py upload --file PATH [--upload-path images/in] --json   (or --url https://...)
python3 scripts/kie_live_adapter.py submit --request req.json [--dry-run] --json
python3 scripts/kie_live_adapter.py wait --task-id ID [--timeout 300] --json
python3 scripts/kie_live_adapter.py run --request req.json --save-dir DIR --json
python3 scripts/kie_live_adapter.py save --task-id ID --save-dir DIR --json
```

`req.json` is `{"model": "<exact id>", "input": {...}, "callBackUrl": "optional", "timeout": 300}`. For models whose schema declares a path other than `/api/v1/jobs/createTask` (the synchronous chat and Gemini models), `input` is the request body and the result comes back in `data.response`.

## Typical flow (operator turned on active mode)

1. `discover` to see what exists. Never type a model id from memory.
2. `schema --model ID`, then `upload` any input file and put `data.download_url` into the field the schema names.
3. `validate` the payload. Fix every listed error. Pick exactly one oneOf branch; do not mix fields.
4. `submit --dry-run`, then `run`. Use a longer `--timeout` for video and music (image default is 300 seconds).
5. The files are saved before the links expire (media may vanish within 24 hours to 14 days; the docs disagree).

## Modes and fallback

Default mode is shadow, so `submit` and `run` return `skipped` with `fallback_used: true`. The caller then uses its existing static path. The adapter never chooses another model on failure. The caller decides fallback. Details: SKILL.md.

## Credentials and limits

Key lookup: environment KIE_API_KEY first, then the shared resolver in shared-utils (secret_names.json canon). Values are never printed. 401 or 403: stop after two attempts and report; do not loop. Catalog, schema, price and success-rate share one request per second per account, so the adapter caches (catalog 6 hours, schema 24 hours) and spaces discovery calls at least 1.1 seconds apart.

## Where things live

Cache and drift receipts: `~/.openclaw/cache/kie-live-adapter` (override KIE_LIVE_CACHE_DIR, KIE_LIVE_RECEIPT_DIR). Nothing is written in the skill folder.

## Rollback

Set `KIE_LIVE_ADAPTER_MODE=off` (or write `off` in `$OC_CONFIG/kie-live-adapter-mode.conf`), or remove the skill folder. Nothing else depends on it.
