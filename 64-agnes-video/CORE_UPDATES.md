# Agnes Video - Core File Updates

Update ONLY the files listed below. Do not update files marked NO UPDATE NEEDED.
Keep core files LEAN — a summary plus a pointer, never the full reference.

**These updates are PERFORMED by `wire.sh`, not pasted.** `wire.sh` writes each block
behind its `<!-- BEGIN/END skill:64-agnes-video:<target> -->` marker REPLACE-IN-PLACE,
with `[MASTER_FILES_FOLDER]` RESOLVED to this box's absolute master-files path, and
stamps `<!-- skill:64-agnes-video:core-update-applied -->`. Earlier versions had no
installer, so the generic merger copied this section VERBATIM: every box ended up with
the literal word `Add:`, a markdown code fence, and the UNFILLED template variable
`[MASTER_FILES_FOLDER]/64-agnes-video/agnes-video-full.md` — a pointer to a path that
exists nowhere. Never paste the instruction — run `bash wire.sh`.

---

## AGENTS.md - UPDATE REQUIRED

Add:

```
## Agnes Video — Video Generation [PRIORITY: HIGH]
- Model choice is NOT manual: run scripts/select_agnes_video_model.py before dispatch
  (deterministic router; explicit model wins; no silent switch; semantic guard vs keyframe reinterpretation)
- Models: agnes-video-2.5-flash (seconds STRING "4"-"12", size 720P only,
  modes text/keyframe/reference, images max 5, videos NEVER) and agnes-video-v2.0
  (num_frames <= 441 AND 8n+1, frame_rate 1-60, 480p/720p/1080p, extra_body.keyframes)
- Auth: Bearer token from AGNES_AI_API_KEY (fleet-provisioned; NEVER print it)
- Pattern: POST https://apihub.agnes-ai.com/v1/videos to CREATE a task ->
  capture video_id -> POLL GET https://apihub.agnes-ai.com/agnesapi?video_id=<id>
  (Flash: ALWAYS add &model_name=agnes-video-2.5-flash) until status=completed -> read metadata.url
- Never auto-select full agnes-video-2.5 (paid, not in token plan)
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
- Create task:  POST /v1/videos  (models: agnes-video-2.5-flash | agnes-video-v2.0)
- Get result (Flash, ALL modes):  GET  /agnesapi?video_id=<ID>&model_name=agnes-video-2.5-flash
- Get result (V2.0):              GET  /agnesapi?video_id=<ID>  (legacy /v1/videos/<TASK_ID>)
- Async: a 200 on create means QUEUED, not done — poll for the result
- Flash: seconds STRING 4-12, size 720P only, images max 5, videos NEVER, n=1
- V2.0: num_frames <=441 AND 8n+1, frame_rate 1-60, tiers 480p/720p/1080p (normalized)
- Pricing: currently $0/second (flash list $0.025/s; v2.0 list $0.005/s);
  full agnes-video-2.5 is paid and never auto-selected
- Rate limit: metered on RPM AND daily/weekly quota by account tier; treat 429
  as the live ceiling and back off — do NOT hardcode a limit
- Full reference: [MASTER_FILES_FOLDER]/64-agnes-video/agnes-video-full.md
```

---

## MEMORY.md - UPDATE REQUIRED

Add:

```
## Agnes Video — installed
- agnes-video-2.5-flash + agnes-video-v2.0, ASYNC create+poll; key AGNES_AI_API_KEY (fleet infra, never printed)
- Router: scripts/select_agnes_video_model.py — deterministic model choice, explicit model wins, no silent switch
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
