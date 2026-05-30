<!-- BEGIN SKILL38: GHL_API_QUICK_REFERENCE -->
## GHL Convert-and-Flow API — Quick Reference (canonical request shapes)

Fast-path canonical shapes so you reply WITHOUT digging through the dense full
reference at runtime. Verified against `29-ghl-convert-and-flow/references/`
(conversations.md, calendars.md, payments.md) + Skill 38
`references/GHL-INBOUND-AND-PLAYBOOKS.md` §7-9. Full detail still lives there;
this is the cheat sheet.

**Base URL:** `https://services.leadconnectorhq.com`
**The 3 headers on EVERY call:**
`Authorization: Bearer <GHL_PRIVATE_INTEGRATION_TOKEN>` · `Version: 2021-04-15` · `Content-Type: application/json`
**Required PIT scopes (summary):** `conversations/message.write`, `calendars.readonly`, `calendars.write`, `calendars/events.readonly`, `calendars/events.write`, `invoices.write`
**Token:** the raw PIT lives ONLY in the secrets env (`secrets/.env` / `~/.openclaw/.env`) as `GHL_PRIVATE_INTEGRATION_TOKEN`; never inline it. `<LOCATION_ID>` = the sub-account id (also `GHL_LOCATION_ID`).

### MESSAGING — ONE endpoint, pick the `type` per channel
`POST /conversations/messages` · scope `conversations/message.write`
**All-in-One Chat note:** GHL's unified inbox is NOT a separate send type — EVERY channel below flows through this ONE endpoint. Match `type` to the inbound channel.

| Channel | `type` | Required body fields |
|---|---|---|
| SMS | `SMS` | `contactId`, `locationId`, `message` |
| Email | `Email` | `contactId`, `locationId`, `subject`, `html`, `emailFrom`, `emailTo` |
| Facebook Messenger | `FB` | `contactId`, `locationId`, `message` |
| Instagram DM | `IG` | `contactId`, `locationId`, `message` |
| Live Chat | `Live_Chat` | `contactId`, `locationId`, `message` |
| Chat Widget (website) | `Live_Chat` | `contactId`, `locationId`, `message` — the website widget routes through Live Chat; there is NO distinct widget `type` |
| WhatsApp | `WhatsApp` | `contactId`, `locationId`, `message` |

**VALID send types (complete list):** `SMS`, `Email`, `FB`, `IG`, `WhatsApp`, `Live_Chat`.
**INVALID as a send `type` (API rejects):** `GMB`, `TikTok`, `Call`, and the long-forms `Instagram` / `Facebook` / `Webchat`. GMB inbound EXISTS as a channel but has no GHL Conversations send type — you cannot reply to GMB via this endpoint. Always use the short codes (`FB`, `IG`).

```bash
# SMS (swap type + required fields per the table above)
curl -s -X POST 'https://services.leadconnectorhq.com/conversations/messages' \
  -H "Authorization: Bearer $GHL_PRIVATE_INTEGRATION_TOKEN" \
  -H 'Version: 2021-04-15' -H 'Content-Type: application/json' \
  -d '{"type":"SMS","contactId":"<contactId>","locationId":"<LOCATION_ID>","message":"<reply text>"}'
```
For Email use `subject` + `html` + `emailFrom` + `emailTo` instead of `message`.

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

> Exact create/send body fields: `29-ghl-convert-and-flow/references/payments.md` (`POST /invoices/` create, `POST /invoices/{invoiceId}/send`). For SCHEDULED invoices also add scope `invoices/schedule.write`.

**Common 400/401 causes (all ops):** missing the `Version: 2021-04-15` header; missing a required body/query field (esp. `locationId`); expired/wrong-type token. Deeper detail per module: `29-ghl-convert-and-flow/references/{conversations,calendars,payments}.md`.
<!-- END SKILL38: GHL_API_QUICK_REFERENCE -->
