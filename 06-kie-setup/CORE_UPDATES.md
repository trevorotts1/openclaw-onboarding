# KIE Setup and HTTP Structure - Core File Updates

Update ONLY the files listed below. Use the EXACT text provided.
Do not update files marked NO UPDATE NEEDED.

---

## AGENTS.md - UPDATE REQUIRED

Add:

```
## KIE.ai Media Generation [PRIORITY: CRITICAL]
- Auth: Bearer token from KIE_API_KEY in secrets/.env
- Pattern: POST to create task -> get task_id -> poll query endpoint until complete
- Rate limit: 20 requests per 10 seconds
- Full reference: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/06-kie-setup/kie-setup-full.md
- ALWAYS check model-specific section before making API calls
```

---

## TOOLS.md - UPDATE REQUIRED

Add:

```
## KIE.ai API [PRIORITY: CRITICAL]
- Base URL: https://api.kie.ai/api/v1/
- Auth: Bearer <KIE_API_KEY>
- Models: 19 video, 19 image, audio (Suno, ElevenLabs)
- Pricing: Credit-based at $0.005/credit
- Status field: successFlag (0=generating, 1=success, 2=failed)
- Full reference with all endpoints: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/06-kie-setup/kie-setup-full.md
```

---

## MEMORY.md - UPDATE REQUIRED

Add:

```
## KIE.ai API Setup - Installed [DATE]
- API key in ~/clawd/secrets/.env as KIE_API_KEY
- 176K char reference doc with all endpoints, params, pricing
- Full reference: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/06-kie-setup/kie-setup-full.md
```

---

## IDENTITY.md - NO UPDATE NEEDED

---

## HEARTBEAT.md - NO UPDATE NEEDED

---

## USER.md - NO UPDATE NEEDED

---

## SOUL.md - NO UPDATE NEEDED
