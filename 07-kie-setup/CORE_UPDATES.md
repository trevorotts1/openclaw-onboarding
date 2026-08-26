# KIE Setup and HTTP Structure - Core File Updates

Update ONLY the files listed below. Use the EXACT text provided.
Do not update files marked NO UPDATE NEEDED.

**These updates are PERFORMED by `wire.sh`, not pasted.** `wire.sh` writes each block
behind its `<!-- BEGIN/END skill:07-kie-setup:<target> -->` marker REPLACE-IN-PLACE,
with `[MASTER_FILES_FOLDER]` resolved to this box's absolute master-files path, and
stamps `<!-- skill:07-kie-setup:core-update-applied -->`. Earlier versions had no
installer, so the generic merger copied this section VERBATIM and every box ended up
with the literal word `Add:`, a markdown code fence, and an unresolved relative
pointer in its AGENTS.md. Never paste the instruction — run `bash wire.sh`.

---

## AGENTS.md - UPDATE REQUIRED

Add:

```
## KIE.ai Media Setup & Router [PRIORITY: CRITICAL]
- Auth: Bearer token from KIE_API_KEY in secrets/.env (referenced, NEVER printed)
- Pattern: POST to create task -> get task_id -> poll query endpoint or use callback until complete
- Generic Market API: POST /api/v1/jobs/createTask, GET /api/v1/jobs/recordInfo?taskId=<id>
- Rate limits: 20 new requests per 10 seconds per account, 100+ concurrent running tasks
- Media retention: Generated media retained 14 days on KIE servers; persist promptly
- Modality routing:
  - generic image -> provider router -> Agnes Image (63) or KIE Image (66)
  - generic video -> provider router -> Agnes Video (64) or KIE Video (67)
  - KIE audio/music/TTS -> KIE Audio (68)
  - explicit model/provider wins; department manifest wins; chosen provider remembered for the task
  - validators run before API dispatch
  - detailed model tables live in skill references/, not here
- Full reference: [MASTER_FILES_FOLDER]/07-kie-setup/kie-setup-full.md
```

---

## TOOLS.md - UPDATE REQUIRED

Add:

```
## KIE.ai API [PRIORITY: CRITICAL]
- Base URL: https://api.kie.ai
- Auth: Bearer <KIE_API_KEY> (referenced, never printed)
- Endpoints: Generic Market (/api/v1/jobs/*), Runway (/api/v1/runway/*), Veo (/api/v1/veo/*), Suno (/api/v1/*)
- Models: consult per-modality registries in 66-kie-image, 67-kie-video, 68-kie-audio (catalog updates frequently)
- Pricing: Credit-based at $0.005/credit
- Status states: waiting, queuing, generating, success, fail (HTTP 200 = accepted, not complete)
- Full reference: [MASTER_FILES_FOLDER]/07-kie-setup/kie-setup-full.md
```

---

## MEMORY.md - UPDATE REQUIRED

Add:

```
## KIE.ai API Setup - Installed [DATE]
- API key in ~/.openclaw/secrets/.env as KIE_API_KEY (canonical credential, never printed)
- Generic Market create/query endpoints and dedicated API families (Runway, Veo, Suno)
- Modality dispatch to dedicated skills 66-kie-image, 67-kie-video, 68-kie-audio
- Full reference: [MASTER_FILES_FOLDER]/07-kie-setup/kie-setup-full.md
```

---

## IDENTITY.md - NO UPDATE NEEDED

---

## HEARTBEAT.md - NO UPDATE NEEDED

---

## USER.md - NO UPDATE NEEDED

---

## SOUL.md - NO UPDATE NEEDED
