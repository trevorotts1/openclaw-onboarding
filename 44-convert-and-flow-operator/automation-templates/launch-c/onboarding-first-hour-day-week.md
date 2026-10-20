# Launch C — Onboarding: First Hour, Day 1, Week 1

**id:** `launch-c-onboarding-first-hour-day-week`
**family:** `onboarding_review` (spec §3.3 — "Onboarding + review/referral")
**template start:** `membership-stick-retention` (Phase A only)
**build rail:** Skill 44 engine (`caf` / `CampaignBuilder`) — **draft only**
**contract unit:** `auto_onboarding_review`

---

## What this runs

A paid buyer's first week, in three beats:

1. **First hour** — access confirmed, one instruction that produces a first result.
2. **Day 1** — a started / not-started branch, so the message matches what the buyer actually did.
3. **Week 1** — a recap plus an honest outcome check that sets `review-eligible` only when the buyer got the result or used the product.

Access delivery, the receipt and promotional suppression belong to the **post-sale** family. This workflow starts after `purchase-onboard-ready` is set, so onboarding can never say "you're in" before access exists.

## Trigger

| Field | Value |
|---|---|
| Trigger | Tag Added `purchase-onboard-ready` |
| Why a tag | CampaignBuilder creates tag triggers natively; the post-sale family owns the payment event |
| Fallback | No post-sale workflow → patch a `payment_succeeded` trigger with `caf workflows patch-trigger --trigger-json <file>` |
| Re-entry | Once per contact per launch. An upsell/downsell purchase does not restart onboarding |

## Sequence

| Beat | When | Channel | What it does |
|---|---|---|---|
| A1 — Access + start here | Immediately (SMS next eligible window) | Email + SMS | One button to START HERE, one first result, no offer |
| B1 — Started? | +1 day from the purchase timestamp | Branch | `onboard-started` → B2b, else B2a |
| B2a — Not started nudge | Same branch | Email | "If you want X, do this" — one obstacle, one action |
| B2b — Started reinforcement | Same branch | Email | Name the action taken, give the next single step |
| C1 — Week-one recap | +7 days from the same anchor | Email | Access recap, known progress, one next action, honest outcome check |
| C2 — Eligibility | Immediately after C1 | Branch + tag | Outcome met or consumed → `review-eligible`; else `onboard-help-needed` + owner task, **no review ask** |

## Timing

- First hour and day 1 are ordinary **duration waits**.
- "Seven days after purchase" is an **event-anchored** wait: set the event start from the purchase timestamp — not contact creation, build time or tag-add time.
- The internal API builder verifies duration waits only. If it rejects the event wait, build that node in the Skill 6 managed browser and leave the draft honestly unfinished. Do not replace it with a duration wait that reports the wrong clock.

## Guards

- Purchase (main, upsell or downsell) stops all launch promotional emails and texts for that buyer. This workflow carries no promotion.
- SMS is opt-in only; every text ends with a reply invitation and STOP; send window 8 a.m.–9 p.m. recipient local.
- At most two texts here, inside the launch cap of 3–5 promotional texts.
- Opt-out, refund and cancel exit every remaining step.
- No countdown, no doors-closing language, no invented results.

## GHL build

Workflow: **LC — Onboarding: First Hour, Day 1, Week 1**

1. Email A1; optional SMS A1 inside the send window.
2. Optional 1-hour check: follow up only if the start link was not clicked (skip when no click signal exists).
3. Set event start time = purchase timestamp → Wait until +1 day → If/Else `onboard-started` → B2b or B2a.
4. Wait until +7 days from the same start → Email C1 → If/Else outcome met or consumed → `review-eligible`; else `onboard-help-needed` + `task-notification`.
5. Goal `onboard-week-1-complete`.

Action types: `email`, `sms`, `wait`, `if_else`, `add_contact_tag`, `task-notification`, `workflow_goal`.

Tags: `purchase-onboard-ready`, `onboard-started`, `onboard-help-needed`, `review-eligible`, `purchase-main`, `purchase-upsell`, `purchase-downsell`, `refunded`, `cancelled`.

`CAF_DRAFT_ONLY` stays on. Nothing is published, sent or switched live. Pass `--folder-id` when the launch folder is known — no folder listing exists on either transport.

## Flexibility

A default, not a rule. Operator's own onboarding plan wins. If unsure, ship A1 + C1 first — they carry most of the value and need no consumption tracking. If handed off, build the full branch. Never remove access confirmation, the eligibility guard, opt-out handling or draft-only.

## Source fidelity

Membership-stick-retention Phase A (rapid onboarding, consumption = retention) · Marketing Secrets Blackbook Secret 53 (consumption) and Secret 54 (one gold nugget) · DotCom Secrets Soap Opera "Set the Stage" welcome · Jim Edwards "If you want X, do this" · GHL capability note (purchase trigger not auto-built; `review_request` verified). No invented mechanics.
