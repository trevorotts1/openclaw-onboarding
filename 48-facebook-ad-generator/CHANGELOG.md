# Changelog — Skill 48 (Facebook & Instagram Ad Generator)

## 1.2.4 — 2026-07-01
- tools/ghl_media.py: unified 11-alias GHL LOCATION-PIT resolver — `_PIT_ENV_NAMES` expanded from 2 to the full 11 canonical aliases (GOHIGHLEVEL_API_KEY, GHL_API_KEY, GHL_PIT, GHL_TOKEN, GHL_PRIVATE_INTEGRATION_TOKEN, PRIVATE_INTEGRATION_TOKEN, GHL_PRIVATE_TOKEN, PIT_TOKEN, GHL_PIT_TOKEN, GOHIGHLEVEL_LOCATION_PIT, GHL_LOCATION_PIT); first non-empty match wins.

## 1.2.3 — 2026-06-30
- tools/ghl_media.py: added bounded retry-with-backoff (`_send_with_retry`) to the two GoHighLevel media HTTP calls (`upload_media`, `create_media_folder`) so a transient blip (connection/timeout or HTTP 429/500/502/503/504) self-heals instead of parking an S7 hosting step. Retries the transient set only (exponential backoff, 3 attempts); a non-transient 4xx is re-raised on the first failure and a 2xx is never re-sent — no double-upload, fail-loud behavior and name-prefix fallback preserved exactly.
- tools/ghl_media.py: rewrote the stale module docstring to describe this skill's GoHighLevel media-hosting role and the CLIENT's own LOCATION credentials (removed the misleading Skill-06 funnel narrative and the "operator's own keys" claim that contradicted the client-keys contract); made the location-id docstring canonical-first (`GOHIGHLEVEL_LOCATION_ID`/`GHL_LOCATION_ID`).
- tools/ghl_media.py: removed dead Skill-06 funnel code unused by this skill (`build_prompts_json`, `generate_images`, `kie_generate_path`, `image_tag`, `build_image_manifest` and their dead constants/imports); the media host (`upload_media`, `create_media_folder`, `resolve_location_pit`, `resolve_location_id`, `verify_png`) is unchanged.
- INSTALL.md / DEPENDENCY-MANIFEST.md: canonicalized the documented location-id env var to `GOHIGHLEVEL_LOCATION_ID` (preferred) with the `GHL_LOCATION_ID` alias, matching the code's canonical-first resolution.
