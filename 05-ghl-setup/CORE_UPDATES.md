# GHL / Convert and Flow Setup - Core File Updates

Update ONLY the files listed below. Use the EXACT text provided.
Do not update files marked NO UPDATE NEEDED.

---

## CREDENTIAL STORAGE - AUTHORITATIVE RULE

PRIMARY credential storage: ~/clawd/secrets/.env
  - GHL_API_KEY (Private Integration Token)
  - GHL_LOCATION_ID

SECONDARY (optional mirror): ~/.openclaw/openclaw.json under env.vars
  - Only sync here if the section already exists
  - secrets/.env is always the source of truth

All runtime code, API calls, and skill references must read from
~/clawd/secrets/.env. Do NOT create confusion by referencing openclaw.json
as the primary store.

---

---

## AGENTS.md - UPDATE REQUIRED

Add:

```
## GHL/Convert and Flow [PRIORITY: HIGH]
- GHL = GoHighLevel = Convert and Flow. All the same platform. Client-facing: always say "Convert and Flow."
- GHL does NOT use API keys. It uses Private Integration Tokens (PITs). The env var GHL_API_KEY holds a PIT, not an API key.
- Two types: Location PIT (GHL_API_KEY) for day-to-day work. Agency PIT (GOHIGHLEVEL_AGENCY_PIT) for agency-wide operations.
- Media uploads require the Location PIT, not the Agency PIT.
- API credentials stored in ~/clawd/secrets/.env (GHL_API_KEY, GHL_LOCATION_ID)
- Always include Version header: 2021-07-28 in API calls
- Full setup guide: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/05-ghl-setup/ghl-setup-full.md
```

---

## TOOLS.md - UPDATE REQUIRED

Add:

```
## GHL/Convert and Flow API
- GHL does NOT use API keys. It uses Private Integration Tokens (PITs). Never tell a client they need an "API key" for GHL.
- Base URL: https://services.leadconnectorhq.com
- Auth: Bearer token using the Location PIT (GHL_API_KEY from secrets/.env)
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
