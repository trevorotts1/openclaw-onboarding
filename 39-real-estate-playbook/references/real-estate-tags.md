# Real-Estate Tag Vocabulary (ZHC-prefixed)

Skill 39 uses ZHC-prefixed tags so RE leads are routable and reportable across
the conversation engine. These are the canonical tags and their fire conditions.

| Tag | Fires when | Emitting flow |
|---|---|---|
| `ZHC-buyer-lead` | Buyer intent detected/qualified (looking to purchase) | buyer qualification, open-house registration |
| `ZHC-seller-lead` | Seller intent detected/qualified (looking to list/sell) | seller qualification, open-house registration |
| `ZHC-investor-lead` | Investor intent (rental/flip/portfolio, ROI-focused) | qualification (role=investor) |
| `ZHC-pre-foreclosure-prospect` | A distressed-owner record from Skill 40 enters outreach | pre-foreclosure outreach |

## Supporting (non-ZHC) status tags

These mirror the Skill 38 real-estate journey template's lifecycle tags and are
used for sequencing, not lead classification: `listing-alert-engaged`,
`showing-confirmed`, `offer-active`, `under-contract`, `closed`,
`post-close-nurture`, `sphere-reactivation`.

## Rules

- A lead may carry one PRIMARY ZHC role tag (`buyer`/`seller`/`investor`) plus
  the pre-foreclosure tag when applicable.
- Tags are routing/reporting signals only — they never encode protected-class
  information (fair-housing).
- Tag changes are reflected in the relevant `real-estate-events.jsonl` event
  (`qualify` carries `tag`; `pre_foreclosure_touch` implies the prospect tag).
