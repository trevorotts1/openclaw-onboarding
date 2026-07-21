# Agnes Video V2.0 - Core File Updates

Update ONLY the files listed below. Use the EXACT text provided (adjust the
master-files path to your box). Do not update files marked NO UPDATE NEEDED.
Keep core files LEAN — a summary plus a pointer, never the full reference.

---

## AGENTS.md - UPDATE REQUIRED

Add:

```
## Agnes Video V2.0 — Video Generation [PRIORITY: HIGH]
- Model: agnes-video-v2.0 (asynchronous)
- Auth: Bearer token from AGNES_AI_API_KEY (fleet-provisioned; NEVER print it)
- Pattern: POST https://apihub.agnes-ai.com/v1/videos to CREATE a task ->
  capture video_id -> POLL GET https://apihub.agnes-ai.com/agnesapi?video_id=<id>
  until status=completed -> read metadata.url
- Modes: text-to-video (prompt), image-to-video (image URL),
  keyframes (extra_body.image[] + extra_body.mode="keyframes")
- num_frames <= 441 AND on the 8n+1 grid; frame_rate 1-60; seconds = num_frames/frame_rate
- Trust returned size/seconds/metadata.size_mapping, NOT the request
- Full reference: [MASTER_FILES_FOLDER]/64-agnes-video/agnes-video-full.md
```

---

## TOOLS.md - UPDATE REQUIRED

Add:

```
## Agnes Video API [PRIORITY: HIGH]
- Base: https://apihub.agnes-ai.com
- Auth: Bearer <AGNES_AI_API_KEY> (referenced, never printed)
- Create task:  POST /v1/videos            (model: agnes-video-v2.0)
- Get result:   GET  /agnesapi?video_id=<VIDEO_ID>   (recommended)
- Legacy get:   GET  /v1/videos/<TASK_ID>
- Async: a 200 on create means QUEUED, not done — poll for the result
- Resolution tiers 480p/720p/1080p; ratios 16:9,9:16,1:1,4:3,3:4 (normalized)
- Pricing: currently $0/second (standard $0.005/second)
- Rate limit: metered on RPM AND daily/weekly quota by account tier; treat 429
  as the live ceiling and back off — do NOT hardcode a limit
- Full reference: [MASTER_FILES_FOLDER]/64-agnes-video/agnes-video-full.md
```

---

## MEMORY.md - UPDATE REQUIRED

Add:

```
## Agnes Video V2.0 — Installed [DATE]
- agnes-video-v2.0, ASYNC create+poll; key AGNES_AI_API_KEY (fleet infra, never printed)
- Endpoint reference doc with all params, response fields, curl examples, tier limits
- Full reference: [MASTER_FILES_FOLDER]/64-agnes-video/agnes-video-full.md
```

---

## IDENTITY.md - NO UPDATE NEEDED

---

## HEARTBEAT.md - NO UPDATE NEEDED

---

## USER.md - NO UPDATE NEEDED

---

## SOUL.md - NO UPDATE NEEDED
