# W0-02 provider contracts — KIE/Suno current envelope and image pins

Status: ACCEPTED. Builder DTS-102 + independent checker PASS (run wf_62c8638d-10b). Source: line-verified reads + live docs fetches 2026-10-06. Promoted verbatim from lanes/DTS-102-lane/provider-contracts.md (DRAFT header removed — content unchanged).

## 1. Skill 68 validator mismatch (R02) — live-verified

- `~/openclaw-onboarding/68-kie-audio/scripts/validate_audio_request.py` L102: `SUNO_MODELS = ("V4","V4_5","V4_5PLUS","V4_5ALL","V5","V5_5")` — no V6.
- L365 `def validate_music`; L371-375 family guard hard-rejects any `createTask` endpoint with exit 2 ("Suno is a DEDICATED family — payload routes createTask, rejected").
- Self-test reproduced live 2026-10-06: exit 0, "SELF-TEST PASS: 42 checks green" — passing tests do not cover current envelope.
- `68-kie-audio/models.json` model enum = same 6 values, grep V6 = 0 hits.

## 2. Current official KIE Suno contract (live docs 2026-10-06)

- generate-music: `POST https://api.kie.ai/api/v1/jobs/createTask`, top model `ai-music-api/generate`, input.model enum V4..V6_WILD, **default V6**, V4–V5_5 marked Discontinued (live-confirmed).
- upload-and-extend-audio: same createTask route; input keys + `data.taskId` confirmed; callback carries audio_url, source_audio_url, image_url, duration, title, tags.
- generate-persona: model `ai-music-api/generate-persona`, createTask, required task_id/audio_id/name/description, vocal capture window 10-30s.
- generate-sounds: model `ai-music-api/sounds`; body code enum 200,401,402,404,422,429,433,455,500,501,505 inside HTTP 200 — validate body code, not HTTP status alone.
- get-task-detail / query-task-detail docs: both HTTP 404 live today. No verified task-detail path — record UNVERIFIED.

## 3. Image pins (R04) — verbatim from AGENTS.md

- L1450-1466 table: legacy aspect routes `3:1`, `1:3`, `9:21` keep `gpt-image-2-*`; do NOT move to 2.5.
- `sunburst` (GPT-Image-2.5 family) pinned default; per-generation caps 20,000/25,000 (L1468-1471).
- OWNER_CONFIRMED marker present at cited lines; `flare` prohibited without operator ruling.

## 4. Discrepancy ledger entries (PROVIDER-DISCREPANCIES.md seeds)

1. generate-music page: code example uses V4 while schema default is V6 and text marks V4-V5_5 Discontinued — stale example, not a passing fixture.
2. generate-sounds: success message paired with body code 422 enum in HTTP 200 — validate body codes, never HTTP alone.
3. get-task-detail: official doc URLs 404 — task-detail verification UNVERIFIED until an authorized live smoke proves a path.
4. PROVIDER-DISCREPANCIES.md did not exist on disk pre-build (searched build tree + onboarding maxdepth 6) — this file seeds it.

## Receipts

- Builder+checker: run wf_62c8638d-10b, 8/8 agents PASS, 0 errors.
- Checker independently re-ran: validator self-test (42 green), grep V6=0, AGENTS.md L1450-1471 verbatim, live doc fetches, 404 reproduction.