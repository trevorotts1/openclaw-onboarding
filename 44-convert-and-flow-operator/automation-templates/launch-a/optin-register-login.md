# Launch Opt-In / Register / Log-In — Tag, Confirmation, Access, Nurture Start

**id:** `launch-optin-register-login`
**category:** launch-a
**status:** from `post-optin-multichannel-stack` (opt-in entry trimmed; the nurture body stays in the source template)
**companion:** `optin-register-login.json`

---

## What this runs

One entry handler for every launch opt-in surface:

1. **Opt-in / waitlist form** — lead magnet claim.
2. **Event / webinar registration** — seat claimed.
3. **Access / log-in request** — portal, membership, course or event access.

On submit it does four things, in this order: **tag it once → confirm immediately → deliver the exact access or log-in it asked for → hand to the right nurture start.** The long nurture and the reminder cadence are separate workflows; this handler owns only the front door.

Everything is built as a **draft**; nothing sends and nothing goes live.

## Trigger

- **Event:** form submitted on an opt-in, registration or access-request page.
- **GHL trigger:** Form Submitted / Funnel Step Submitted.
- **How it is built:** `CampaignBuilder` only auto-creates a Tag Added trigger, so this trigger is written with `caf workflows patch-trigger --trigger-json <file>` on the internal API (snapshot before write), or through the Tier-4 managed browser where the engine has no verified payload.
- **Binding:** each variant resolves to the approved launch plan's form ID or funnel-step ID. Never inferred from a page title, URL text or product name.
- **Re-entry:** once per contact per variant per campaign. Guard tags `launch-optin-started`, `launch-registered-started`, `launch-access-started`; a present guard means no second tag, send, access delivery or enrollment.

## Variants

| Variant | Surface | Adds tag | Confirmation | Nurture start |
|---|---|---|---|---|
| `form-optin` | Opt-in / lead magnet / waitlist form | `launch-optin` | Lead magnet delivery + what happens next | post-optin multichannel nurture |
| `registration` | Event / webinar registration form | `launch-registered` | Seat confirmed + calendar/access link | launch reminder cadence |
| `access-login` | Access / log-in request form | `launch-access-requested` | Request received + access/log-in delivery | access / onboarding follow-up |

## Sequence

| # | Action | Timing | What it does |
|---|--------|--------|--------------|
| 1 | `add_contact_tag` | Immediate | Variant tag plus the matching `*-started` guard. Makes the handler idempotent across refreshes and repeated submits. |
| 2 | `update_custom_value` | Immediate | Set `launch_optin_date`. The nurture and reminder families read this date. |
| 3 | `if_else` | Immediate | **Purchase guard.** Buyer tag `purchased-[offer-id]` present → no promotional copy; exit to the post-sale purchase workflow. This is the A2 guarantee. |
| 4 | `email` | 0 min | Immediate confirmation. form-optin delivers the lead magnet; registration confirms the seat and supplies the calendar/access link; access-login confirms the request and the log-in path. Copy comes from the approved Skill 50 launch copy. |
| 5 | `sms` | Immediate, only when email + text launch and A2P approved | One short confirmation with a reply invitation and STOP opt-out, inside the launch send window (default 8 a.m.–9 p.m. recipient local time). Skipped and recorded when A2P is not approved. |
| 6 | `email` | Immediate, registration + access-login only | Access / log-in delivery: calendar/join link, or the portal invitation / magic log-in link for the exact granted access. Never a password. form-optin skips this node. |
| 7 | `add_to_workflow` | Immediate | Exactly one variant-appropriate nurture enrollment. Never enroll twice. |
| 8 | `workflow_goal` | End | Closes the short handler. No multi-day waits live here. |

## Buyer suppression

A paid buyer gets no further promotional emails or texts for this launch, from any variant of this handler.

**Stops:** promotional launch sequence · doors-closing / last-call · abandoned-checkout recovery · page-visit retargeting · nurture pitches for an offer already bought or included in the package.

**Does not stop:** transactional confirmation, access and log-in notices · the buyer's own onboarding / review / referral sequence · a genuinely different later offer approved in the launch plan.

## Dependencies created before the workflow

- **Tags:** `launch-optin`, `launch-registered`, `launch-access-requested`, `launch-optin-started`, `launch-registered-started`, `launch-access-started`, `sms-subscribed`, `purchased-[offer-id]`.
- **Custom field:** `launch_optin_date` (date).
- **Custom values:** `{{lead_magnet_url}}`, `{{registration_calendar_url}}`, `{{access_login_url}}`, `{{ac_name}}`, `{{brand_name}}`.

## Build path and ceiling

- **Engine:** Skill 44 internal-API engine (`caf workflows create` / `CampaignBuilder`), managed-browser Tier-4 backstop for the trigger.
- **Why not the official API:** it has no workflow create, update, publish or trigger endpoint; its only workflow operation is `GET /workflows/`.
- **Verified actions used:** `add_contact_tag`, `update_custom_value`, `if_else`, `email`, `sms`, `add_to_workflow`, `workflow_goal`.
- **Draft only:** every workflow and every trigger is written as a draft; `CAF_DRAFT_ONLY` keeps `active` off. No live switch-on; that is a separate client approval.
- **Inputs:** approved variant bindings, approved Skill 50 confirmation copy, lead magnet / calendar / access URLs, nurture workflow IDs, A2P state and send window, location whitelist entry and Firebase refresh token. Missing token → Tier-4 browser backstop.

## Quality

Checklist lines **A1**, **A2**, **X1**. WF-1..21 plus FAB-QC ≥ 8.5 apply to the built workflow.

- Each variant resolves to one approved form binding; no guessed page or product.
- Tag + guard written before any send, so a refresh cannot double-send.
- Purchase guard exits before every promotional node.
- Access/log-in delivered once; no password is ever sent.
- SMS node skipped and recorded when A2P is not approved.
- Exactly one nurture enrollment per contact and variant.
- Everything is `draft_only`; no live switch-on; no client account touched during the build.
