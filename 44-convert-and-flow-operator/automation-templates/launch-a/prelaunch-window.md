# Launch A — Pre-Launch Window (Calendar, Tags, Schedule, Switches)

- **id:** `launch-a-prelaunch-window`
- **Spec row:** 3.3 Pre-launch
- **Family:** `pre_launch`
- **Build rail:** Skill 44 engine (`skill44_engine`), draft only
- **Derived from:** `sales-close-sequences/cart-open-cart-close-launch-sequence` (PRE-CART rows only) + `multichannel-automation/indoctrination-multichannel-preframe`
- **Capability note:** `launch-ghl-probe/GHL-CAPABILITY-NOTE.md` — the official API cannot create, update, publish or trigger a workflow. Build through the internal-API engine. Calendar `Wait Until` dates and the Messenger action need the Tier-4 managed browser.

## What it is

The days before doors open, and nothing else. The workflow takes a `pre-launch-list` contact through the indoctrination story series, lands the final pre-cart reminder on D-1, and hands off at `doors_open_at`.

Cart-open sends, cart-close urgency (T-48h / T-24h / T-3h / T-1h) and post-close branching belong to the cart-open/cart-close lane. This file never sends after `doors_open_at`.

## Calendar dates

Every datetime resolves from `launch_plan.launch_calendar`. No lane types or rounds a date.

| Field | Value |
|---|---|
| `launch_at` | `{{launch_at}}` |
| `doors_open_at` | `{{doors_open_at}}` |
| `doors_close_at` | `{{doors_close_at}}` |
| `timezone` | `{{timezone}}` |
| `indoc_1_at` | `doors_open_at` − 5 days, 09:00 location time |
| `indoc_2_at` | `doors_open_at` − 3 days, 09:00 |
| `indoc_3_at` | `doors_open_at` − 2 days, 09:00 |
| `indoc_4_at` (optional) | `doors_open_at` − 2 days, 14:00 |
| `precart_reminder_at` | `doors_open_at` − 1 day, 09:00 |
| `precart_sms_at` | `doors_open_at` − 1 day, 18:00 |
| `prelaunch_close_at` | `doors_open_at` |

**Wait rule:** every wait is `Wait Until` the fixed datetime above — never a duration. The API builder verifies duration waits only; calendar dates are rejected there and must be built in the managed browser. Do not shorten the timing contract to make the API accept the template.

## Tags

| Tag | Added when | Role |
|---|---|---|
| `pre-launch-list` | upstream opt-in / waitlist | entry trigger |
| `indoc-started` | first node | re-entry guard |
| `indoc-1-sent` | after D-5 origin send | beat proof |
| `indoc-2-sent` | after D-3 obsession send | beat proof |
| `indoc-3-sent` | after D-2 teaching send | beat proof |
| `indoc-4-sent` | after optional values send | beat proof |
| `doors-soon` | after D-1 reminder | urgency state |
| `cart-open-ready` | at `doors_open_at` | handoff signal to the cart-open lane |
| `prelaunch-complete` | at `doors_open_at` | closure proof |
| `sms-subscribed` | upstream | SMS gate |
| `messenger-subscribed` | upstream | Messenger gate |
| `purchased-[offer-id]` / `buyer-[offer]` | purchase event | exit, never re-enter |
| `pre-launch-stop` | operator | kill switch |

Entry filters: `purchased-[offer-id]` absent, `buyer-[offer]` absent, `indoc-started` absent. One entry per contact per launch.

## Schedule

| Beat | At | Channels | What runs |
|---|---|---|---|
| Entry | trigger | — | Add `indoc-started`; exit on purchase tags; arm D-5 wait |
| INDOC-01 Origin / Backstory | D-5 09:00 | Email, Messenger, ad | Story only. No pitch, no buy CTA. Add `indoc-1-sent` |
| INDOC-02 Obsession / Expertise | D-3 09:00 | Email, Messenger, SMS nudge | Story only. SMS nudge only if no open in 24h and opted in. Add `indoc-2-sent` |
| INDOC-03 Teaching / Method | D-2 09:00 | Email, Messenger, ad | Teaching, first stay-tuned CTA. Add `indoc-3-sent` |
| INDOC-04 Values / Mission (optional) | D-2 14:00 | Email, Messenger | Only with a genuine values story. Skip otherwise. Add `indoc-4-sent` |
| PRE-CART last reminder | D-1 09:00 + 18:00 SMS | Email, SMS | What opens tomorrow, who it is for, exact time, why it closes. Add `doors-soon` |
| Handoff | `doors_open_at` | — | Add `cart-open-ready` and `prelaunch-complete`; end |

No send at handoff. The cart-open/cart-close lane owns every message from `doors_open_at` onward.

## Switches

All switches default **closed**. Building never turns the workflow on.

| Switch | Default | Open / close rule |
|---|---|---|
| `prelaunch_open` | closed | Opens at `doors_open_at` − 5 days on `pre-launch-list`, only on explicit operator GO after calendar, copy and tags verify |
| `prelaunch_close` | closed | Automatic at `doors_open_at`. A manual close may only bring it earlier, never later |
| `cart_open_handoff` | off | Turns on at `doors_open_at`; requires `prelaunch_close` confirmed, operator GO and the cart-open lane drafted. Emits `cart-open-ready` |
| `purchase_interrupt` | always on | `purchased-[offer-id]` or `buyer-[offer]` exits immediately and stops every remaining beat |
| `kill_switch` | armed | Tag `pre-launch-stop` removes a contact at the next wait; no rebuild needed |

`CAF_DRAFT_ONLY=1` keeps the workflow and trigger in draft. Nothing in this file authorizes a live send.

## GHL build (Skill 44)

1. Resolve `launch_plan.launch_calendar`. Refuse the build if any date or timezone is missing or still a placeholder.
2. Create or confirm the tags. Location tag creation uses internal `POST /workflow/{loc}/tags/create`.
3. `caf workflows create` — name and folder; keep the draft.
4. `caf workflows create-step` for email, SMS, if/else, tag and purchase-interrupt nodes. `CampaignBuilder` auto-creates a Tag Added trigger, which is exactly this template's entry — no `patch-trigger` work for the trigger.
5. Tier-4 managed browser for every `Wait Until` calendar node and every Messenger node. Snapshot before and after each browser edit.
6. `caf workflows export` — store the finished draft as the build artifact.
7. Do not patch the trigger active and do not publish. Opening the workflow is the switch, not the build.

**Verified actions used:** `email`, `sms`, `wait`, `if_else`, `update_custom_value`, `workflow_goal`.
**Tier-4 required:** every calendar `Wait Until` node; every Messenger action node.
**Skill 44 notes:** set `order` and `parentKey` before the first save on every node. Re-verify tag nodes after the first save — tag nodes silently reorder.

## Integrity guardrails

- Every date resolves from the launch calendar. Never invent, shift or round one.
- Episodes 1–4 carry no product pitch and no buy CTA — only stay-tuned CTAs.
- The values episode is optional and must be genuine. Skip it when there is no real story.
- SMS only to `sms-subscribed` with one shared opt-out. Messenger only to `messenger-subscribed`.
- A purchase at any node exits immediately. The purchase interrupt is never simplified away.
- Building is not opening. Every switch defaults closed; live sends need explicit operator GO.

## Scope

**In:** `pre-launch-list` entry, D-5 to D-1 story and reminder beats, the tag set and channel gates, the open/close switches and the `doors_open_at` handoff.

**Out:** cart-open announcement and every cart-window send · cart-close urgency · post-close branching and downsell · the pre-launch email copy (Skill 50) · Conversation AI (Skill 38).
