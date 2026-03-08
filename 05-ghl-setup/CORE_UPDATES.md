# GHL / Convert and Flow Setup - Core File Updates

Update ONLY the files listed below. Use the EXACT text provided.
Do not update files marked NO UPDATE NEEDED.

---

## AGENTS.md - UPDATE REQUIRED

Add:

```
## GHL/Convert and Flow [PRIORITY: HIGH]
- API credentials stored in ~/clawd/secrets/.env (GHL_API_KEY, GHL_LOCATION_ID)
- Always include Version header: 2021-07-28 in API calls
- Full setup guide: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/05-ghl-setup/ghl-setup-full.md
```

---

## TOOLS.md - UPDATE REQUIRED

Add:

```
## GHL/Convert and Flow API
- Base URL: https://services.leadconnectorhq.com
- Auth: Bearer token (GHL_API_KEY from secrets/.env)
- Required header: Version: 2021-07-28 (without this you get 400 errors)
- Key endpoints: /contacts/search, /conversations/messages, /opportunities/
- Full reference: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/05-ghl-setup/ghl-setup-full.md
```

---

## MEMORY.md - UPDATE REQUIRED

Add:

```
## GHL/Convert and Flow Setup - Installed [DATE]
- API credentials in ~/clawd/secrets/.env
- Version header 2021-07-28 is MANDATORY on all API calls
- Full guide: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/05-ghl-setup/ghl-setup-full.md
```

---

## IDENTITY.md - NO UPDATE NEEDED

---

## HEARTBEAT.md - NO UPDATE NEEDED

---

## USER.md - NO UPDATE NEEDED

---

## SOUL.md - NO UPDATE NEEDED
