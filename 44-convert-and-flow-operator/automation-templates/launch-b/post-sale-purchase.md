# Launch Post-Sale Purchase — Access + Welcome, Promo Stop, Next Follow-Up

**id:** `launch-post-sale-purchase`
**category:** launch-b
**status:** new, small (spec §3.3)
**companion:** `post-sale-purchase.json`

---

## What this runs

One short purchase handler per paid point: **main**, **each upsell**, **each downsell**. On a verified paid transaction line it does three things, in this order:

1. **Stops promotional emails and texts for that buyer.**
2. **Grants access and sends the welcome.**
3. **Starts the buyer's next follow-up.**

No long waits. No thank-you page visit required. No promo sends after purchase. Everything is built as a **draft**; nothing goes live.

## Trigger

- **Event:** Order line paid — payment verified as settled, not merely "order submitted".
- **GHL trigger:** Order Submitted / Payment Received.
- **How it is built:** `CampaignBuilder` only auto-creates a Tag Added trigger, so this trigger is written with `caf workflows patch-trigger --trigger-json <file>` on the internal API (snapshot before write), or through the Tier-4 managed browser where the engine has no verified payload.
- **Variants:** one binding per paid point — product ID + price ID + order-page/form ID. The binding comes from the approved launch plan; never inferred from a product name.
- **Re-entry:** deliberate per transaction line. A later distinct upsell/downsell purchase can enter again; the same line cannot repeat access, welcome, suppression or enrollment. Dedupe on tenant + verified transaction/order-line identity + action type + campaign version.

## Sequence

| # | Action | Timing | What it does |
|---|--------|--------|--------------|
| 1 | `remove_contact_tag` | Immediate | Remove launch promo tags and buyer-suppressed state. Removes the buyer from promotional campaigns and abandoned-checkout / recovery workflows **before** anything else sends. |
| 2 | `add_contact_tag` | Immediate | Add the launch buyer tag and the variant tag (main / upsell-N / downsell-N). |
| 3 | `email` | Immediate | Access + welcome email: access link for the exact purchased variant, receipt reference, next step. Copy comes from the approved Skill 50 welcome/access sequence. |
| 4 | `sms` | Immediate, only when email + text launch and A2P approved | Short access link, reply invitation, STOP opt-out, launch send window. Skipped entirely when A2P is not approved. |
| 5 | `add_to_workflow` | Immediate | Enroll in exactly one variant-appropriate next follow-up: next upsell, downsell after a decline, or onboarding at the end of the stack. Never the promotional launch sequence. |
| 6 | `workflow_goal` | End | Closes the short handler. Longer onboarding and review sequences are separate workflows. |

## Buyer suppression

A paid buyer gets no further promotional emails or texts for this launch, for any variant.

**Stops:** promotional launch sequence · doors-closing / last-call · abandoned-checkout recovery · page-visit retargeting · remaining pitches for an offer already bought or included in the package.

**Does not stop:** transactional access and receipt notices · the buyer's own onboarding / review / referral sequence · a genuinely different later offer approved in the launch plan.

## Variants

| Variant | Match | Next follow-up |
|---|---|---|
| `main` | Main offer product ID + price ID + order-page/form ID | Main upsell follow-up when an upsell page exists; otherwise onboarding / review |
| `upsell` (one per page) | That page's product ID + price ID + order-page/form ID | Next upsell, matching downsell after a decline, or onboarding when the stack ends |
| `downsell` (one per page) | That page's product ID + price ID + order-page/form ID | Next downsell, or onboarding when the stack ends |

## Build path and ceiling

- **Engine:** Skill 44 internal-API engine (`caf workflows create` / `CampaignBuilder`), managed-browser Tier-4 backstop for the trigger.
- **Why not the official API:** it has no workflow create, update, publish or trigger endpoint; its only workflow operation is `GET /workflows/`.
- **Verified actions used:** `add_contact_tag`, `remove_contact_tag`, `email`, `sms`, `add_to_workflow`, `workflow_goal`.
- **Draft only:** every workflow and every trigger is written as a draft. No live switch-on; that is a separate client approval.
- **Inputs:** approved variant bindings, access URL per variant, approved welcome/access copy hash, next follow-up workflow IDs, location whitelist entry and Firebase refresh token. Missing token → Tier-4 browser backstop.

## Quality

Checklist lines **A1**, **A2**, **X1**. WF-1..21 plus FAB-QC ≥ 8.5 apply to the built workflow.

- Suppression runs before any welcome or follow-up step.
- No long wait in the short handler.
- Access granted once per verified transaction line.
- No promo node remains reachable for a paid buyer.
- Everything is `draft_only`; no live switch-on.
- No client account touched during the build.
