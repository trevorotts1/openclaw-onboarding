# Real-Estate Tag Vocabulary (ZHC-prefixed)

Skill 39 uses ZHC-prefixed tags so RE leads are routable and reportable across
the conversation engine. These are the canonical tags and their fire conditions.

| Tag | Fires when | Emitting flow |
|---|---|---|
| `ZHC-buyer-lead` | Buyer intent detected/qualified (looking to purchase) | buyer qualification, open-house registration |
| `ZHC-seller-lead` | Seller intent detected/qualified (looking to list/sell) | seller qualification, open-house registration |
| `ZHC-investor-lead` | Investor intent (rental/flip/portfolio, ROI-focused) | qualification (role=investor) |
| `ZHC-pre-foreclosure-prospect` | A distressed-owner record from Skill 40 enters outreach | pre-foreclosure outreach |

## Supporting lifecycle status tags (also ZHC-prefixed)

These mirror the Skill 38 real-estate journey template's lifecycle tags and are
used for sequencing, not lead classification. The AGENT creates and applies them,
so per the ZHC Tag-Prefix Rule's single test ("did the AGENT create this tag?")
they are `ZHC-` prefixed exactly like the role tags above — there is no
"non-ZHC" carve-out:
`ZHC-listing-alert-engaged`, `ZHC-showing-confirmed`, `ZHC-offer-active`,
`ZHC-under-contract`, `ZHC-closed`, `ZHC-post-close-nurture`,
`ZHC-sphere-reactivation`.

> NOTE: these are agent-minted lifecycle/sequencing tags, NOT operator-owned GHL
> pipeline stages. If an operator manages their own pipeline-stage tags by hand,
> those stay in the operator's namespace untouched (see
> `38-conversational-ai-system/protocols/zhc-tag-prefix-protocol.md`).

## Rules

- A lead may carry one PRIMARY ZHC role tag (`buyer`/`seller`/`investor`) plus
  the pre-foreclosure tag when applicable.
- Tags are routing/reporting signals only — they never encode protected-class
  information (fair-housing).
- Tag changes are reflected in the relevant `real-estate-events.jsonl` event
  (`qualify` carries `tag`; `pre_foreclosure_touch` implies the prospect tag).
