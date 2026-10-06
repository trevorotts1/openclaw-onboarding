# Provider discrepancies — pointer to the Skill 68 work copy

Canonical record: `onboarding/68-kie-audio/PROVIDER-DISCREPANCIES.md`
(maintained per directive §9.2 item 7; contradictory official examples are
recorded there, never turned into passing fixtures). This file is a pointer —
read the work copy, not a summary here.

## Work-copy references

- Discrepancy ledger: `onboarding/68-kie-audio/PROVIDER-DISCREPANCIES.md`
  (3 entries: V4-example-vs-V6-text; sounds body-code 422 inside HTTP 200;
  task-detail URLs 404, record path UNVERIFIED).
- Model catalog: `onboarding/68-kie-audio/models.json` — `suno-generate` route
  `ai-music-api/generate`, default `V6`, enum
  `V4 V4_5 V4_5PLUS V4_5ALL V5 V5_5 V6 V6_MINI V6_WILD`; `suno-extend` routes
  `ai-music-api/extend` / `ai-music-api/upload-and-extend-audio`;
  `suno-sounds` route `ai-music-api/sounds`.
- Owner validator: `onboarding/68-kie-audio/scripts/validate_audio_request.py`
  — missing `input.model` defaults to `V6`; `V4`–`V5_5` accepted with a
  Discontinued warning, never dropped; current-family models ride ONLY the
  `createTask` envelope (route/model coherence gate).
- Runtime binding: `core/music_director/__init__.py` reads route ids, versions,
  and defaults from the work-copy `models.json` at runtime (`route_model`,
  `default_version`, `version_enum`) and validates payloads through the owner
  validator — never hardcoded here.
- Contract source: `planning/provider-contracts.md` §§2/§4 (live KIE docs +
  registry fetched 2026-10-06).
