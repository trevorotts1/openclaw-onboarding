# Launch Text — Keyword Opt-In (`Text EARLY`)

**id:** `launch-text-keyword-opt-in`
**category:** launch-text
**status:** new, small (spec §3.2 keyword opt-in)
**companion:** `keyword-opt-in.json`

---

## What this runs

One inbound keyword turns a contact into a confirmed SMS subscriber for the launch. The keyword only starts the handshake — **nothing promotional is sent until the contact replies YES**.

Default keyword: **`Text EARLY`**. The actual keyword comes from the launch plan / launch intake, is compared trimmed and case-insensitive, and is never free text.

**Two messages, both non-promotional:**

1. **Double opt-in prompt** — who is texting, what they will get, how to confirm, reply invitation, STOP.
2. **Confirmed acknowledgement** — real doors-open and doors-close times, reply invitation, STOP.

Texts are drafted by Skill 50's copy voice and executed here as Skill 44 `sms` steps. Everything is a **draft**; nothing sends and no client account is touched during the build.

## Trigger

- **Event:** inbound SMS whose normalized body exactly equals `{{opt_in_keyword}}` (default `EARLY`).
- **GHL trigger:** Customer Replied — channel SMS, exact phrase, case-insensitive.
- **How it is built:** `CampaignBuilder` creates Tag Added triggers only, so this trigger is written with `caf workflows patch-trigger --trigger-json <file>` on the internal API (snapshot before write), or through the Tier-4 managed browser.
- **YES reply:** a second Customer Replied trigger, exact `YES`, filtered to contacts holding `text-optin-pending`. Scoping matters — a YES to any other conversation must never grant SMS consent.
- **Unmatched bodies:** no reply, no tag. A human or Conversation AI may answer separately and must not add consent.

## Steps

| # | Action | Timing | What it does |
|---|--------|--------|--------------|
| 1 | `trigger` | Immediate on inbound SMS | Match `{{opt_in_keyword}}` exactly (trimmed, uppercase, case-insensitive). Non-match exits. |
| 2 | `if_else` | Immediate | Exit when `sms-opted-out` or `text-optin-confirmed` is present. |
| 3 | `add_contact_tag` | Immediate | Add `text-optin-pending`; set `text_optin_keyword`, `text_optin_started_at`. |
| 4 | `wait` | Outside 08:00–21:00 recipient local only | Hold the outbound confirmation until the next 08:00 local. Inbound is captured immediately. |
| 5 | `sms` | Inside the send window | **Message 1.** Double opt-in prompt. Reply invitation + STOP. |
| 6 | `wait` | 24 hours | Wait for YES. |
| 7 | `if_else` | After the wait | Branch on `text-optin-confirmed`. |
| 8 | `add_contact_tag` | Confirmed branch | Add `text-optin-confirmed` + `sms-subscribed`; remove `text-optin-pending`; set `text_optin_confirmed_at`. |
| 9 | `sms` | Confirmed branch, inside the window | **Message 2.** Confirmed acknowledgement with the real doors-open and doors-close times. Reply invitation + STOP. |
| 10 | `remove_contact_tag` | Unconfirmed branch | Remove `text-optin-pending`. Send nothing. The contact can text the keyword again later. |
| 11 | `workflow_goal` | End | Closes this set. Reminders, doors-open, last-call and access-link texts are separate sets in `launch-text/`. |

## Message copy

**Message 1 — double opt-in prompt**

> Got it — this is {{founder_first_name}} with {{brand_name}}. Reply YES and I'll text you when the doors open and when they're about to close. Questions? Just reply here. Reply STOP to opt out.

**Message 2 — confirmed acknowledgement**

> You're in. Doors open {{doors_open_at}} and close {{doors_close_at}}. I'll text you at both, and nothing in between unless you reply. Reply STOP to opt out.

Both carry a reply invitation and **STOP**. No price, offer, bonus or checkout link — this set does not count against the 3–5 promotional text cap.

## Compliance

- **Send window:** 08:00–21:00 recipient local. Outbound confirmation outside the window waits for the next 08:00 local; inbound capture does not wait.
- **STOP:** honored by the carrier / GHL opt-out layer and by the workflow — add `sms-opted-out`, remove `sms-subscribed`, `text-optin-pending`, `text-optin-confirmed` and every launch text tag. No further launch text. No promotional reply.
- **A2P 10DLC:** required. When `a2p_ready = false` the workflow is still built as a **draft**, nothing sends, and the launch package records: *texts cannot send until A2P is approved*.
- **Duplicate keyword:** already-confirmed contacts are not re-sent the handshake. At most one confirmation per 24 hours per contact.
- **Draft only:** everything is created inactive. Live switch-on is a separate client approval.

## Launch-plan mapping

This template emits one `text_set` for the shared launch plan:

```json
{
  "id": "text_keyword_opt_in",
  "kind": "keyword_opt_in",
  "messages": 2,
  "promotional": false,
  "draft_only": true,
  "opt_out_keyword": "STOP",
  "includes_reply_invitation": true,
  "send_window": {"start": "08:00", "end": "21:00", "timezone": "recipient_local"},
  "waits_for": []
}
```

## Dependencies

Tags: `text-optin-pending` · `text-optin-confirmed` · `sms-subscribed` · `sms-opted-out`

Custom fields: `text_optin_keyword` · `text_optin_started_at` · `text_optin_confirmed_at`

## Why this shape

- **Double opt-in** proves the phone belongs to a person who asked for the texts; a single inbound keyword can be a misdial or a prank.
- **No promotional send until YES** keeps the consent record clean and keeps the promotional count honest.
- **One keyword, exact match** avoids capturing unrelated replies and avoids a second keyword quietly granting consent.
- **Re-entry after 24 hours** lets someone who missed the prompt try again without leaving a half-consented contact in the list.

## QC lines

- **T1:** two text points exist, each with a reply invitation and STOP, send window 08:00–21:00, `promotional: false`.
- **T2:** `a2p_ready = false` → workflow stays a draft and the package warns.
