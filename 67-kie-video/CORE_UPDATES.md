# Core File Updates: KIE Video (Skill 67)

This document describes the lean, high-signal reference updates for Skill 67 (KIE Video).
These updates are applied automatically and idempotently by `wire.sh`.

---

## 1. AGENTS.md Update

Add to the AGENTS.md file in the active workspace:

```markdown
<!-- BEGIN skill:67-kie-video:agents -->
## Media Generation Routing
- generic image -> provider router -> Agnes Image (63) or KIE Image (66)
- generic video -> provider router -> Agnes Video (64) or KIE Video (67)
- KIE audio/music/TTS -> KIE Audio (68)
- explicit model/provider wins; department manifest wins; chosen provider remembered for the task
- validators run before API dispatch
- detailed model tables live in skill references/, not here

## KIE Video (67)
- KIE.ai API video generation across 37 models. Key: KIE_API_KEY (env var NAME per repo convention).
- Create (Market): POST https://api.kie.ai/api/v1/jobs/createTask (async — 200 = task CREATED, not finished).
- Dedicated routes: Runway (POST /api/v1/runway/generate), Veo 3.1 (POST /api/v1/veo/generate).
- Query: GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<TASK_ID> (state: waiting/queuing/generating/success/fail).
- Default picks: Long-form (>15s) -> Wan 3.0 (wan/3-0-video); Multi-shot -> Kling 3.0 Omni; 2K -> MiniMax H3; explicit user model wins.
- Validators run before dispatch: scripts/validate_prompt.py, scripts/validate_payload.py, scripts/select_video_model.py, scripts/normalize_alias.py.
- Prompt bands: Wan 3.0/Gemini Omni/Seedance 2.5 (20K-30K cap, house band 5K-19K); MiniMax/PixVerse/Wan 2.7 (5K-7K caps); Kling Omni (3,072 cap); others NOT_PUBLISHED.
- Full registry + per-family tables: $REF_DEST/models.json, $REF_DEST/references/
<!-- END skill:67-kie-video:agents -->
```

---

## 2. TOOLS.md Update

Add to the TOOLS.md file in the active workspace:

```markdown
<!-- BEGIN skill:67-kie-video:tools -->
## KIE Video API (Skill 67)
- Auth: Bearer <KIE_API_KEY>
- POST https://api.kie.ai/api/v1/jobs/createTask (asynchronous; response 200 = task created with taskId)
- Dedicated APIs: POST https://api.kie.ai/api/v1/runway/generate, POST https://api.kie.ai/api/v1/veo/generate
- GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<TASK_ID> (state enum: waiting/queuing/generating/success/fail; resultJson.resultUrls on success)
- Callbacks: callBackUrl field; HMAC-SHA256 scheme base64(HMAC-SHA256(taskId + "." + timestampSeconds, webhookHmacKey)); headers X-Webhook-Timestamp / X-Webhook-Signature; ack {"code":200,"msg":"success"}
- Rate: 20 new generation requests/10s; 100+ concurrent. Result URLs expire ~24h; media deleted after 14 days.
- Registry: $REF_DEST/models.json + $REF_DEST/references/ (37 models, limits, durations, resolutions, reference caps)
- Validators: scripts/validate_prompt.py, scripts/validate_payload.py (run before dispatch; never after)
<!-- END skill:67-kie-video:tools -->
```

---

## 3. MEMORY.md Update

Add to the MEMORY.md file in the active workspace:

```markdown
<!-- BEGIN skill:67-kie-video:memory -->
## KIE Video (67) — installed
- KIE.ai Market API + Dedicated Runway/Veo endpoints; async createTask -> recordInfo polling or Skill 46 callback (never treat 200 as done)
- Key: KIE_API_KEY; autonomous routing by capability hierarchy, explicit model wins
- Registry + tables: $REF_DEST/models.json, $REF_DEST/references/
<!-- END skill:67-kie-video:memory -->
```
