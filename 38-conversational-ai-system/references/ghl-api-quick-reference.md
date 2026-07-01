<!-- BEGIN SKILL38: GHL_API_QUICK_REFERENCE -->
## GHL Convert-and-Flow API — Quick Reference (canonical request shapes)

Fast-path canonical shapes so you reply WITHOUT digging through the dense full
reference at runtime. Verified against `29-ghl-convert-and-flow/references/` +
Skill 38 `references/GHL-INBOUND-AND-PLAYBOOKS.md` §7-9 (full detail there).

> **Runtime tier ladder:** prefer Skill 44 `caf` (Tier 0 — `caf conversations` / `calendars` / `contacts` / `payments`; run `caf --help` for exact flags). This raw REST is the documented **Tier-3 fallback** (keep it for caf-less boxes). On a **401 / non-2xx you have NOT sent** — never report "sent": escalate to the operator AND tell the client to refresh their PIT. Full rule: AGENTS.md `SKILL38_RUNTIME_GHL_TIER_LADDER`.

**Base URL:** `https://services.leadconnectorhq.com`
**The 3 headers on EVERY call:**
`Authorization: Bearer <GHL_PRIVATE_INTEGRATION_TOKEN>` · `Version: 2021-04-15` · `Content-Type: application/json`
**Required PIT scopes (summary):** `conversations/message.write`, `conversations.readonly`, `calendars.readonly`, `calendars.write`, `calendars/events.readonly`, `calendars/events.write`, `invoices.write`
**Token:** the raw PIT lives ONLY in the secrets env (`secrets/.env` / `~/.openclaw/.env`) as `GHL_PRIVATE_INTEGRATION_TOKEN`; never inline it. `<LOCATION_ID>` = the sub-account id (also `GHL_LOCATION_ID`).

### MESSAGING — ONE endpoint, MIRROR the inbound channel's `type`
`POST /conversations/messages` · scope `conversations/message.write`
**All-in-One Chat note:** GHL's unified inbox is NOT a separate send type — EVERY channel below uses this ONE endpoint. Reply on the SAME channel the message arrived on; do NOT hardcode `SMS`.

| Channel | `type` | Required body fields |
|---|---|---|
| SMS | `SMS` | `contactId`, `locationId`, `message` |
| Email | `Email` | `contactId`, `locationId`, `subject`, `html`, `emailFrom`, `emailTo` |
| Facebook Messenger | `FB` | `contactId`, `locationId`, `message` |
| Instagram DM | `IG` | `contactId`, `locationId`, `message` |
| Live Chat / website Chat Widget | `Live_Chat` | `contactId`, `locationId`, `message` — the website widget routes through Live Chat; no distinct widget `type` |
| WhatsApp | `WhatsApp` | `contactId`, `locationId`, `message` |

**Mirror map:** SMS→`SMS`, Email→`Email`, Facebook→`FB`, Instagram→`IG`, WhatsApp→`WhatsApp`, Live Chat→`Live_Chat`.
**VALID send types (complete `SendMessageBodyDto` enum):** `SMS`, `Email`, `FB`, `IG`, `WhatsApp`, `Live_Chat` (also valid but rare: `RCS`, `Custom`, `TIKTOK`).
**INVALID as a send `type` (API rejects):** `GMB`, `Call`, and the long-forms `Instagram` / `Facebook` / `Webchat`. GMB is **inbound-only** (no send type — cannot reply via this endpoint). TikTok inbound is workflow-action-only; send type = `TIKTOK`. Always use the short codes (`FB`, `IG`).
**Threading:** the send threads into the contact's conversation BY `contactId` — `conversationId` is **NOT** a send-body field; the send returns `conversationId`+`messageId`.

```bash
# Mirror {{channel}} → type (here SMS); swap type + required fields per the table above
curl -s -X POST 'https://services.leadconnectorhq.com/conversations/messages' \
  -H "Authorization: Bearer $GHL_PRIVATE_INTEGRATION_TOKEN" \
  -H 'Version: 2021-04-15' -H 'Content-Type: application/json' \
  -d '{"type":"SMS","contactId":"<contactId>","locationId":"<LOCATION_ID>","message":"<reply text>"}'
```
For Email use `subject` + `html` + `emailFrom` + `emailTo` instead of `message`.

### MESSAGING (READ) — `conversationId` is the READ key only · scope `conversations.readonly`
| Op | Method + URL |
|---|---|
| Find the thread (by contact) | `GET /conversations/search?locationId=<LOCATION_ID>&contactId=<contactId>` |
| Read message history | `GET /conversations/<conversationId>/messages` |

> The inbound webhook payload already carries `conversationId`, `contactId`, `messageType`; use these only for deeper history than the local conversation log holds.

### CALENDARS
| Op | Method + URL | Scope | Body / Query |
|---|---|---|---|
| List calendars | `GET /calendars/?locationId=<LOCATION_ID>` | `calendars.readonly` | query: `locationId` |
| Get calendar | `GET /calendars/<calendarId>` | `calendars.readonly` | — |
| Create calendar | `POST /calendars/` | `calendars.write` | body per calendars.md (incl. `locationId`, `name`, `teamMembers`) |
| Free slots | `GET /calendars/<calendarId>/free-slots?startDate=<epochMillis>&endDate=<epochMillis>` | `calendars.readonly` | query: `startDate`, `endDate` in **epoch MILLISECONDS** (`date +%s` × 1000) |

### APPOINTMENTS
| Op | Method + URL | Scope | Body |
|---|---|---|---|
| Book | `POST /calendars/events/appointments` | `calendars/events.write` | `{"calendarId","locationId","contactId","startTime"}` — `startTime` ISO8601; `endTime` OPTIONAL (slot duration fills it). Response returns appointment `id`. |
| Reschedule | `PUT /calendars/events/appointments/<eventId>` | `calendars/events.write` | `{"startTime","endTime"}` |
| Cancel | `DELETE /calendars/events/<eventId>` | `calendars/events.write` | — (no body) |

```bash
# Book appointment
curl -s -X POST 'https://services.leadconnectorhq.com/calendars/events/appointments' \
  -H "Authorization: Bearer $GHL_PRIVATE_INTEGRATION_TOKEN" \
  -H 'Version: 2021-04-15' -H 'Content-Type: application/json' \
  -d '{"calendarId":"<calendarId>","locationId":"<LOCATION_ID>","contactId":"<contactId>","startTime":"<ISO8601 start>"}'
```

### INVOICES
2-step: create, then send by the returned `invoiceId`.
| Op | Method + URL | Scope | Body |
|---|---|---|---|
| Create invoice | `POST /invoices/` | `invoices.write` | invoice body per payments.md (incl. `altId`=`<LOCATION_ID>`, `altType`:`location`, `contactDetails`, `items`, `currency`). Response returns `invoiceId`. |
| Send invoice | `POST /invoices/<invoiceId>/send` | `invoices.write` | send body per payments.md (e.g. `{"altId":"<LOCATION_ID>","altType":"location","action":"send_manually"}`) |

> Exact body fields: `29-ghl-convert-and-flow/references/payments.md`. SCHEDULED invoices also need scope `invoices/schedule.write`.

### CUSTOM FIELDS (F46 — Step 9.40, `crm-field-write-protocol.md`)
LOCATION-scoped discover/create; the VALUE is written onto the contact via `PUT /contacts/<contactId>` `customFields` (see protocol). **Version `2021-07-28`** (NOT `2021-04-15`).
| Op | Method + URL | Returns / Body |
|---|---|---|
| Discover | `GET /locations/<LOCATION_ID>/customFields` | each field's `id`, `name`, `fieldKey`, `dataType` (TEXT/LARGE_TEXT/NUMERICAL/MONETARY/DATE/PHONE/SINGLE_OPTIONS/RADIO/MULTIPLE_OPTIONS/CHECKBOX); option types also return `options` |
| Create (if missing) | `POST /locations/<LOCATION_ID>/customFields` | `{"name":"ZHC_<lower_snake>","dataType":"<TYPE>","locationId":"<LOCATION_ID>"}` → new field `id`. Operator-approved, NEVER customer-invoked; always `ZHC_` prefix |

**Common 400/401 causes:** missing the `Version: 2021-04-15` header; a missing required field (esp. `locationId`); expired/wrong-type token. Deeper detail: `29-ghl-convert-and-flow/references/{conversations,calendars,payments}.md`.
<!-- END SKILL38: GHL_API_QUICK_REFERENCE -->
