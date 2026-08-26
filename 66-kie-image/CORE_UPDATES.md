# KIE Image - Core File Updates

Update ONLY the files listed below. Use the EXACT text provided.
Do not update files marked NO UPDATE NEEDED.

**These updates are PERFORMED by `wire.sh`, not pasted.** `wire.sh` writes each block
behind its `<!-- BEGIN/END skill:66-kie-image:<target> -->` marker REPLACE-IN-PLACE,
with `[MASTER_FILES_FOLDER]` resolved to this box's absolute master-files path, and
stamps `<!-- skill:66-kie-image:core-update-applied -->`. Earlier versions of other
skills had no installer, so the generic merger copied this section VERBATIM and every
box ended up with the literal word `Add:`, a markdown code fence, and an unresolved
relative pointer in its AGENTS.md. Never paste the instruction — run `bash wire.sh`.

---

## AGENTS.md - UPDATE REQUIRED

Add:

```
## Media Generation Routing
- generic image -> provider router -> Agnes Image (63) or KIE Image (66)
- generic video -> provider router -> Agnes Video (64) or KIE Video (67)
- KIE audio/music/TTS -> KIE Audio (68)
- explicit model/provider wins; department manifest wins; chosen provider remembered for the task
- validators run before API dispatch
- detailed model tables live in skill references/, not here

## KIE Image (66)
- KIE.ai Market API image generation. Key: KIE_API_KEY (env var NAME per repo convention).
- Create: POST https://api.kie.ai/api/v1/jobs/createTask (async — 200 = task CREATED, not finished).
- Query: GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<TASK_ID> (state: waiting/queuing/generating/success/fail).
- Default pick: GPT Image 2 (gpt-image-2-text-to-image) when compatible; explicit user model wins.
- Validators run before dispatch: scripts/validate_prompt.py, scripts/validate_payload.py, scripts/select_image_model.py, scripts/normalize_alias.py.
- Prompt band legal per model: Wan/Ideogram/Imagen 4 caps 5,000 chars VERIFIED; Qwen is token-based (never fake char cap); others NOT_PUBLISHED (house band 5K-19K is TARGET only).
- Full registry + per-family tables: [MASTER_FILES_FOLDER]/66-kie-image/models.json, [MASTER_FILES_FOLDER]/66-kie-image/references/
```

---

## TOOLS.md - UPDATE REQUIRED

Add:

```
## KIE Image API (Skill 66)
- Auth: Bearer <KIE_API_KEY>
- POST https://api.kie.ai/api/v1/jobs/createTask (asynchronous; response 200 = task created with taskId)
- GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<TASK_ID> (state enum: waiting/queuing/generating/success/fail; resultJson.resultUrls on success)
- Callbacks: callBackUrl field; HMAC-SHA256 scheme base64(HMAC-SHA256(taskId + "." + timestampSeconds, webhookHmacKey)); headers X-Webhook-Timestamp / X-Webhook-Signature; ack {"code":200,"msg":"success"}
- Rate: 20 new generation requests/10s; 100+ concurrent. Result URLs expire ~24h; media deleted after 14 days.
- Registry: [MASTER_FILES_FOLDER]/66-kie-image/models.json + references/ (per-family limits, ratios, resolutions, reference caps)
- Validators: scripts/validate_prompt.py, scripts/validate_payload.py (run before dispatch; never after)
```

---

## MEMORY.md - UPDATE REQUIRED

Add:

```
## KIE Image (66) - Installed [DATE]
- KIE.ai Market API; async createTask -> recordInfo polling or Skill 46 callback (never treat 200 as done)
- Key: KIE_API_KEY; model default GPT Image 2 when compatible, explicit pick wins
- Registry + tables: [MASTER_FILES_FOLDER]/66-kie-image/models.json, [MASTER_FILES_FOLDER]/66-kie-image/references/
```

---

## IDENTITY.md - NO UPDATE NEEDED

---

## HEARTBEAT.md - NO UPDATE NEEDED

---

## USER.md - NO UPDATE NEEDED

---

## SOUL.md - NO UPDATE NEEDED
