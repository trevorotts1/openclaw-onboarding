# Launch Win-Back — Closed, No Purchase → Next Offer Re-Engagement

**id:** `launch-win-back-closed-no-purchase`
**category:** launch-c · **family:** win_back · **start:** `re-engagement-winback-broadcast`
**Stays:** draft only. Nothing here sends or goes live.

---

## Who this is for

People who opted in during the launch and **did not purchase by the time the doors closed**.

In:

- approved launch opt-in / registration segment,
- no verified paid transaction line for the main offer, any upsell or any downsell,
- not already re-engaged or sunset for this launch.

Out:

- any paid buyer,
- an active abandoned-checkout recovery still inside its own window (that family owns order recovery first),
- DND / opt-out / unsubscribed.

The start moment is `launch_plan.launch_calendar.doors_close_at` — the truthful deadline from the
launch plan. Never a made-up "doors close" date.

## What this runs

| # | Step | Timing | Channel | What it does |
|---|---|---|---|---|
| 0 | Buyer check | On entry and before every send | If/Else | A verified paid line or launch buyer tag ends the workflow. Purchase always wins. |
| 1 | "The doors closed. Are we breaking up?" | Day 0, at least 1 day after doors close | Email | Us vs Them / Secret Telling hook. One CTA to stay in the loop for the next offer. |
| 2 | Best-of value + next-offer invite | +3 days | Email | The strongest launch story + the approved next offer. No invented price. |
| 3 | Takeaway / sunset | +3 days, SMS same day | Email + SMS | Honest takeaway with one CTA. SMS is one sentence with a reply invitation and STOP. **Skipped when `a2p_ready` is false or the launch is email-only.** |
| 4 | Close out | +2 days after step 3 | Tag | No response → `launch-winback-sunset`, remove `launch-winback-active` and the launch broadcast tag. |

**Goal:** click, reply, purchase or opt-out exits the workflow immediately. A buyer is moved to
the buyer state and receives no promotional win-back copy.

## Audience rule — closed, no purchase

```
doors_close_at < now
AND contact in launch opt-in segment
AND no verified paid line for any launch offer
AND contact not already launch-winback-reengaged / launch-winback-sunset
```

The buyer state is a **verified paid transaction line**, never a page visit or a guessed tag.
This launch variant differs from the broadcast template in two places only: the audience is
"launch closed, no purchase" and the offer is the approved next offer. The 30-day-cold trigger,
the goal exit and the sunset suppression come from `re-engagement-winback-broadcast`.

## Build rail

**Skill 44 engine** (`caf` / `CampaignBuilder`). The official GHL API cannot create, update,
publish or trigger a workflow — its only workflow operation is `GET /workflows/`
(`GHL-CAPABILITY-NOTE.md`, U-GHL-PROBE, 2026-10-20).

- `CampaignBuilder` creates the workflow as a draft and auto-creates a **Tag Added** trigger only.
- The **recurring / scheduled** trigger after doors close needs
  `caf workflows patch-trigger --trigger-json <file>` (snapshot before write) or the Tier-4
  managed browser.
- Duration waits are verifiable through the engine. A calendar-date wait on `doors_close_at`
  needs the managed browser — do not strip the timing contract to make the API accept it.
- Every action stays inactive until a separate client approval switches it live.

## Inputs

- `launch_calendar.doors_close_at` (truthful deadline).
- Launch opt-in segment and launch buyer state.
- Approved next offer (name + URL), or none → value-only variant with a reply invitation.
- Approved Skill 50 copy hash and text copy (reply invitation + STOP).
- `a2p_ready` and email-only vs email + text election.
- Location whitelist entry and Firebase refresh token; missing token → Tier-4 browser backstop.

## Quality

Checklist lines **A1**, **A2**, **X1**. WF-1..21 plus FAB-QC ≥ 8.5 apply to the built workflow.

- Template starts from `re-engagement-winback-broadcast` → family `win_back` (A1).
- Audience is closed-no-purchase; no buyer ever enters.
- Buyer check before every send; any purchase ends the workflow immediately (A2).
- SMS skipped when `a2p_ready` is false; every text has a reply invitation and STOP.
- Non-responders get `launch-winback-sunset` and drop out of launch promo sends.
- Everything is `draft_only`; no live switch-on, no client account touched (X1).

## Files

- `win-back-closed-no-purchase.json` — machine-readable template (audience, trigger, sequence, build plan, suppression).
- `win-back-closed-no-purchase.md` — this page.

## Check (no new test suite)

```
python3 -m json.tool 44-convert-and-flow-operator/automation-templates/launch-c/win-back-closed-no-purchase.json > /dev/null
```

Proves the template parses. Checklist **A1** for this family: the file exists under `launch-c/`,
its start is `re-engagement-winback-broadcast`, and its audience is closed-no-purchase.
Checklist **A2** is met by `draft_only: true`, the buyer check before every send, and the
purchase-stops-promo rule.
