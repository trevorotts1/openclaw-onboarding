# Vercel Setup - Core File Updates

Update ONLY the files listed below. Use the EXACT text provided.
Do not update files marked NO UPDATE NEEDED.

---

## AGENTS.md - UPDATE REQUIRED

Add:

```
## Vercel Deployment [PRIORITY: STANDARD]
- Setup method: browser + API token only during onboarding
- Token: VERCEL_TOKEN
- API Base: https://api.vercel.com
- Full guide: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/08-vercel-setup/vercel-setup-full.md
```

---

## TOOLS.md - UPDATE REQUIRED

Add:

```
## Vercel API
- Setup/auth method during onboarding: browser + token
- Token: $VERCEL_TOKEN (stored in secrets file)
- Verify: curl -H "Authorization: Bearer $VERCEL_TOKEN" https://api.vercel.com/v2/user
- API Base: https://api.vercel.com
- Full guide: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/08-vercel-setup/vercel-setup-full.md
```

---

## MEMORY.md - UPDATE REQUIRED

Add:

```
## Vercel Setup - Installed [DATE]
- Token stored in secrets file as VERCEL_TOKEN
- Verified via Vercel API user endpoint
- Full guide: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/08-vercel-setup/vercel-setup-full.md
```

---

## IDENTITY.md - NO UPDATE NEEDED

---

## HEARTBEAT.md - NO UPDATE NEEDED

---

## USER.md - NO UPDATE NEEDED

---

## SOUL.md - NO UPDATE NEEDED
