# Launch C — Review Ask, Then Referral Ask

**id:** `launch-c-review-referral-ask`
**family:** `onboarding_review` (spec §3.3 — "Onboarding + review/referral")
**template start:** `membership-stick-retention` (advocacy cut)
**build rail:** Skill 44 engine (`caf` / `CampaignBuilder`) — **draft only**
**contract unit:** `auto_onboarding_review`

---

## What this runs

Two asks, in order, both real:

1. **Review ask** — after the onboarding week-one gate sets `review-eligible`. One honest request plus one reminder, maximum.
2. **Referral ask** — only after a positive signal (`review-submitted` or an owner-set `positive-signal` tag). A real referral link with real terms, or one named-introduction request. Never an invented reward.

A buyer still waiting on the result is a support case, not a review candidate. The eligibility gate lives in `onboarding-first-hour-day-week.json` and this workflow trusts it.

## Prerequisites (fail closed)

| Prerequisite | If missing |
|---|---|
| Real review URL from intake (Google Business Profile, Trustpilot, GHL Reputation, client review page) | Workflow stays draft; package warns "review link missing". No placeholder is ever sent |
| Real referral program + terms, or none | No program → ask for one named introduction, no reward promised |
| Consumption or outcome signal | Fall back to "purchase + 7 days + no open support tag" and say so in the build notes |

## Sequence

| Beat | When | Channel | What it does |
|---|---|---|---|
| A1 — Review request | On `review-eligible`, inside the send window | Email + one SMS (opt-in) | Name the purchase and the result; one honest-review link; no rating language |
| B1 — One reminder | +3 days | Email | Same link, one line. Skipped if `review-submitted` or a support tag is open |
| C1 — Positive-signal branch | On `review-submitted` or `positive-signal` | Branch | Anything else ends quietly |
| C2 — Referral request | Immediately after C1 | Email + one SMS | Real referral link and terms, or one named introduction |

## Integrity rules

- **Review honesty:** never ask for a rating, never "if you loved it", never an incentive, never a filtered audience. Every eligible buyer gets the same destination and the same open ask. This is platform policy, not a preference.
- **One ask each:** one review request, one reminder, one referral request. Nothing repeats.
- **Referral honesty:** the terms come from the client's real program. No invented bonus, deadline or scarcity. Without a program, ask for one name — not a pledge.
- **Signals:** an email open or a click is not a positive signal. Only `review-submitted` or an explicit human-set `positive-signal` count.

## Guards

- SMS opt-in only; reply invitation + STOP on every text; 8 a.m.–9 p.m. recipient local.
- At most two texts here, inside the launch cap of 3–5 promotional texts.
- Opt-out, refund and cancel exit every remaining step.
- Draft only. Nothing is sent or switched live.

## GHL build

Workflow: **LC — Review Ask → Referral Ask**

1. `review_request` action (or `email` with the approved link when the destination does not support the action); optional one SMS.
2. Wait 3 days → If/Else `review-submitted` → C1; If support tag open → exit; else B1 reminder once.
3. Wait for `review-submitted` OR `positive-signal` → If/Else TRUE → C2 referral ask; FALSE → goal `advocacy-closed-no-ask`.
4. Goals: `review-requested`, `review-submitted`, `referral-asked`, `advocacy-closed-no-ask`.

Action types: `review_request`, `email`, `sms`, `wait`, `if_else`, `add_contact_tag`, `workflow_goal`.

Tags: `review-eligible`, `review-requested`, `review-submitted`, `positive-signal`, `referral-asked`, `onboard-help-needed`, `refunded`, `cancelled`.

All waits here are duration waits, which the internal API builder supports. The review platform's "submitted" event must be wired back as a tag or webhook before C1 can branch; if it cannot report, C1 uses an owner-set `positive-signal` tag and the build receipt says the referral ask depends on a human signal.

## Flexibility

A default, not a rule. Operator's own plan wins. If unsure, ship A1 and stop — one honest review ask is the useful minimum. If handed off, build A1, B1 and C2 with real links and real terms. Never remove the eligibility gate, the one-ask limit, review integrity, opt-out handling or draft-only.

## Source fidelity

Membership-stick-retention advocacy logic, reduced to a launch buyer's week one · DotCom Secrets value-first asking · Marketing Secrets Blackbook word-of-mouth follows a real result · GHL capability note (`review_request` verified; purchase triggers not auto-built) · review-platform policy (honest, unfiltered, unincentivised). No invented mechanics.
