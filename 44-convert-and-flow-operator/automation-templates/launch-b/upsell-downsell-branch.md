# Upsell / Downsell Bought-or-Declined Branch

**id:** `upsell-downsell-branch`
**category:** launch-b
**aliases:** upsell downsell branch · bought declined follow-up · option page branch · next-offer follow-up · smaller-option follow-up

---

## What this does
One small branch per offer option page (every upsell page, every downsell page). The contact reaches the page; the workflow waits for the **verified** purchase event, then sends exactly one matching follow-up:

| Branch | Condition | Follow-up |
|---|---|---|
| **Bought** | verified purchase tag `purchased-<offer_id>` present | Skill 50 `upsell_followup` for this page — moves the buyer to the **next offer** |
| **Declined** | explicit `declined-<offer_id>` tag, or no verified purchase after the wait deadline | Skill 50 `downsell_followup` for this option's downsell page — the **smaller option** |

Never both. The bought branch removes the decline tag; the declined branch never fires when the purchase tag is present.

**Branch authority:** only the Skill 44 receiver/processor writes `purchased-<offer_id>`, and only from a `purchase_observed` event with `payment_status=succeeded`. A return URL or page click is never a purchase.

## TRIGGER
- **Starts when:** Tag Added `option-branch:<slot>:<offer_id>` (set by the option page view). The No-thanks link also adds `declined-<offer_id>` before this tag, so the first IF/ELSE skips the wait.
- **Entry guard:** not already tagged `bought-<slot>` or `declined-<slot>` for this option.
- **Exits when:** either branch's follow-up is enrolled, or the contact opts out.

## ORDERED ACTIONS (Skill 44 engine build plan)
1. If/Else — `declined-<offer_id>` present? TRUE → step 6; FALSE → step 2
2. Wait — 15 minutes (purchase webhook/processor settle window)
3. If/Else — `purchased-<offer_id>` present? TRUE → step 4; FALSE → step 6
4. Add `bought-<slot>`; remove `declined-<offer_id>` and `option-branch:<slot>:<offer_id>`
5. Enroll in Skill 50 `upsell_followup` (draft); end
6. Add `declined-<slot>`; remove `option-branch:<slot>:<offer_id>`
7. Enroll in Skill 50 `downsell_followup` (draft); end

**Goal event:** `purchase_observed` (succeeded) for `<offer_id>`.
**Tags:** `option-branch:<slot>:<offer_id>`, `purchased-<offer_id>`, `declined-<offer_id>`, `bought-<slot>`, `declined-<slot>`.

## BUILD RAIL
**Skill 44 engine.** U-GHL-PROBE verdict: the official GoHighLevel API cannot create, update, publish or trigger a workflow — it only reads them. The engine writes the draft workflow; the managed-browser Tier-4 backstop applies only where the engine has no verified payload.

**Everything is `draft_only`.** Never live, never sent to a real contact.

## SUPPRESSION (checklist A2)
A verified purchase makes the contact a buyer: promotional launch emails and texts stop for that buyer. The Skill 44 purchase processor and store re-check active entitlement state at dispatch time (A21); this workflow adds no duplicate check and never sends a promotional broadcast itself.

## LAUNCH-PLAN CONTRACT
```json
{
  "id": "upsell_downsell_branch",
  "family": "upsell_downsell",
  "template": "new",
  "build_rail": "skill44_engine",
  "draft_only": true,
  "trigger": { "type": "tag_added", "detail": "option-branch:<slot>:<offer_id>" },
  "waits_for": ["upsell_followup_option", "downsell_followup_option", "page_option"]
}
```
`waits_for` shows example unit ids; each per-page instance resolves them to that page's real email-sequence and page unit ids in the launch plan.
