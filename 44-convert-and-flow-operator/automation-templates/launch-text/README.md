# Launch Text — SMS step library (WF-TEXT)

SMS copy and step timing for the six text sets a Signature Launch can carry. **Texts only.** No email copy, no workflow construction.

**Lane:** `launch-automations/text-sms` · **Base:** `launch-automations-integration`
**Inputs:** `shared-utils/signature_launch_contract/launch-plan.schema.json` (U-CONTRACT), `launch-automations/u-ghl-probe` timing note, launch calendar (`doors_open_at`, `doors_close_at`, `launch_at`, `timezone`).

## Files

| File | Purpose |
|---|---|
| `text-sets.json` | The six sets, contract-shaped, each with its ordered SMS steps |
| `test_launch_text_catalog.py` | Runnable check: shape, promo cap, quiet hours, STOP, step/message parity |

```bash
python3 44-convert-and-flow-operator/automation-templates/launch-text/test_launch_text_catalog.py
```

## The six sets

| id | kind | Msgs | Promo | Fires | Waits for |
|---|---|---:|---|---|---|
| `text_optin_confirmation` | `opt_in_confirmation` | 1 | no | Within 60 s of opt-in | `page_landing` |
| `text_event_reminders` | `event_reminder` | 3 | no | 24 h / 1 h / 10 min before event | `page_sales` |
| `text_doors_open` | `doors_open` | 1 | **yes** | At `doors_open_at` | `page_sales` |
| `text_last_call` | `last_call` | 2 | **yes** | T-24 h and T-2 h before `doors_close_at` | `page_sales` |
| `text_abandoned_checkout` | `abandoned_checkout` | 2 | **yes** | +30 min / +24 h, exits on purchase | `page_checkout` |
| `text_access_link` | `access_link` | 1 | no | At `launch_at` / on access grant | `page_access` |

**Promotional budget:** 3 of the 5 allowed. `doors_open`, `last_call`, `abandoned_checkout` are promotional; a launch may add at most 2 more promotional sets. The U-CONTRACT validator rejects a sixth.

## Compliance rules (non-negotiable)

1. **STOP** — every message carries `STOP`; the keyword is the contract constant `STOP` in every set. HELP is named in the opt-in confirmation.
2. **Quiet hours** — `08:00–21:00` in the recipient's local time (`recipient_local`). No send before 08:00 or at/after 21:00.
   - A step whose computed time is outside the window moves to 08:00 the same day, or 08:00 the next day if that is still before the step's own deadline.
   - A deadline step (`doors_open`, `last_call`) moves **earlier** to 20:00 — never later into the night.
   - Event reminders stay event-relative; if the event itself sits outside quiet hours, the reminder uses the nearest allowed slot before it.
3. **Draft only** — `draft_only: true` in every set. Nothing here authorizes a send.
4. **A2P guard** — when `a2p_ready` is false, all six sets stay drafts and the package warns texts cannot send until A2P 10DLC is approved.
5. **Truthful deadlines only** — `{{doors_close_at}}` and `{{event_start_at}}` come from the launch plan. Never write a date or time the calendar does not contain.
6. **Reply invitation** — `includes_reply_invitation: true` in every set; every set's copy invites a reply or names HELP.
7. **Purchase exit** — `abandoned_checkout` exits on the buyer tag at either step; never text a buyer a recovery message.

## Placeholders

| Token | Source |
|---|---|
| `{{first_name}}` | contact record, falls back to `there` at send time |
| `{{business_name}}` | brand facts |
| `{{offer_name}}`, `{{price}}` | `offer.name`, formatted `offer.price_usd` |
| `{{sales_url}}` | `offer.sales_page_url` |
| `{{checkout_url}}` | `offer.checkout_url` |
| `{{access_url}}` | page `access` url |
| `{{doors_close_at}}` | `launch_calendar.doors_close_at` |
| `{{event_name}}`, `{{event_start_at}}` | launch calendar / event record |

Unknown token fails the catalog check.

## Consuming this catalog

1. Copy each `text_sets[]` entry into the launch plan. The `steps` key is extra data; the contract allows it, and the text lane strips it before handing a plan to a strict consumer.
2. Resolve `waits_for` ids against the actual plan (the ids above are the fixture conventions; remap to the plan's real page ids).
3. Build each set as a Skill 44 workflow: `sms` actions are in `VERIFIED_ACTIONS`.
   - Event-relative waits and calendar waits are not verified API payloads — use the managed-browser (Tier-4) rail per `launch-ghl-probe/GHL-CAPABILITY-NOTE.md` and `references/workflow-timing.md`.
   - Auto-created trigger is Tag Added only; form/order triggers use `caf workflows patch-trigger` or Tier 4.
   - Workflows stay draft (`CAF_DRAFT_ONLY`).
4. Copy is written for a 2-segment ceiling (≤ 320 characters before placeholder expansion). The check enforces this.

## Validation

```bash
python3 44-convert-and-flow-operator/automation-templates/launch-text/test_launch_text_catalog.py
# optional, when U-CONTRACT is present:
python3 shared-utils/signature_launch_contract/validate_launch_plan.py <plan-with-these-text-sets>.json
```
