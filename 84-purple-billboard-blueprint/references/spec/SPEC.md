<!-- Verbatim carry of the Purple Billboard client-system build document of the same name (spec version 2.1, policy dates 2026-10-24). Only one owner-identifier token was removed from DEC-20. This is the behavior contract for skill 84: where any other file in this skill differs, this one wins. Settled policy does not mean implemented behavior; runtime status is in ../wiring-map.md. -->

# Reusable client acquisition system specification
Version 2.1. The typed requirements and acceptance links are in live-ledgers/requirements.json and ACCEPTANCE-MATRIX.md. Historical reviews remain evidence, not current implementation claims.

## Business outcome
Each client gets a system that discovers the business, prepares useful actual assets, plans and publishes an approved monthly campaign, handles supported public/private conversations, fulfills promises, helps people, recommends relevant next steps and follows through to verified appointments or sales.
OpenClaw Skill 38 is the conversation brain. GHL/Skill 44 provide transport, CRM and workflows. Existing 35/57 scheduling remains the content owner. No competing scheduler, router or native-only replacement is introduced silently. Each client has separate accounts, contacts, senders, assets, knowledge, consent and state.

## Setup and assets
AI reuses known business facts and discovers audience, pain, approved offers/prices/claims, geography, capacity, calendar, human owner and success measures. It asks only missing questions and prepares a concrete acquisition brief.
Inventory actual original gifts and optional extras, rights, quality, versions, accessibility and destinations. Some clients have no master guides. Prepare useful missing assets for review before promising them. Do not create fictional collections, token endpoints or customer outcomes.
Guided bootstrap discovers/reuses supported existing objects, prepares a client-scoped diff, provisions only permitted actions, persists receipts and resumes idempotently. Capability/auth exceptions go to the right owner with a prepared next step.

## Monthly approval and teaching rules
One monthly review approves 30 exact dated packs with original resource, actual Bonus, keyword, channel/account, conversation path and permitted spares. A changed unit invalidates only itself.
Use the client's consistent brand color; billboard under 45 words with hook/promise/comment pointer and no main answer, link or hashtag. Default six teaching comments plus unnumbered Bonus; five promised may mean five plus Bonus; explicit flexible template never exceeds eight authored comments. Bonus has at most two links; occasional middle links are allowed. Publish then ordered comments over minutes, not an invented one-minute absolute.
Facebook first does not imply identical IG behavior. The lecture allowed 30 days although it preferred weekly adaptation; the later monthly default is settled owner policy. Black-color exception and mirroring details remain specific decisions.

## Publication and public conversation
Scheduled posts, reveal comments and Bonus comments use a strict public-placement envelope, not a dummy contact. Verify approval, account binding, schedule, publishing pause, parent/order and platform capability at each dispatch.
Keep a single 35/57 scheduling path and distinct campaign/cycle/account/revision identity. Retry of one placement deduplicates; a genuine new cycle is not collapsed. Verify actual post/comment receipts and resume only missing approved pieces.
Page comments, IG comments, Messenger, IG direct DM and personal-profile operations have independent capability contracts. Exclude own reveal/outgoing events by verified identity. Public monitoring of old threads is separate from private follow-ups.
Personal-profile unattended publishing and ongoing replies remain unproved; one reported browser test is not a month-long service. Muse is currently document cleanup only. The Page Messenger bridge does not answer the profile's public thread.

## Routing and original promises
Personal route includes the business Messenger link and a stable promised-item keyword. Tested m.me references were not surfaced in inspected normalized GHL fields; treat this narrowly and never assume link attribution.
Page/IG comment private openers use their own permission. Comment alone is not a normal DM window; wait for the documented qualifying customer interaction. No drip to an ignored opener.
Immutable original promise/version is independent of its hosting URL. Old keywords are never recycled; host migration requires equivalent-content/access proof. Retired mappings retain a truthful tombstone rather than silently substituting another item.

## Fulfillment, access and useful help
Deliver the actual original item directly in eligible chat first, independent of optional membership. Continue only with an approved accessible resource, correct destination and supported success status without known failure. Accepted/sent is not delivered without a receipt; later failure pauses capture continuation and repairs the promise.
Offer actual extra guides/value afterward. GHL membership is a candidate pending mobile-only identity, entitlement, credential, SMS and return/recovery proof. Expired credential is not expired guides. An advertised bonus product remains not ready if this capability is unresolved.
Standard capture is mobile first, reusing relevant known fields/display name and requested-delivery consent. Ask email exactly once by a logical SMS action, preferably with working pass delivery; later asks use the original eligible DM. Delivery is not marketing consent.
Phone-only, email-only and declining people still get the original resource and help. Skill 38 continues needs discovery, knowledge-based answers and a relevant resource/community/offer/calendar recommendation. No universal three-question gate and no capture-as-completion.

## Follow-ups, refusals and final stop
Initial invitation is separate from three escalating reminders total across fields/channels. Proposed 2h/8h/20h slots anchor to the first actionable invitation; replies, restarts and new giveaways never reset the budget. Active conversation pauses reminders; timing/quiet policy must be adopted before activation. No catch-up burst or false expiry/window extension.
Serialize at tenant + canonical contact + sequence. Field refusal, sequence decline, channel opt-out, global stop and human takeover have explicit precedence.
closing_final reserves one exact final action; the normal gate still applies. STOP/completion/handoff can cancel before dispatch. Acceptance or terminal no-send closes; unknown reconciles the same action. A new explicit request can be served without restarting rejected capture.
CLIENT-EXPERIENCE.md contains first, second and final wording plus known-field/reverse/returning cases.

## Booking, handoff and outcomes
Use actual approved calendar capacity, recheck at commit and claim booked only with a real receipt. Confirm timezone/location/change path; follow the approved service process for reschedule/no-show/fulfillment.
Human handoff has context, accepted owner, due action and backup. Bot remains fenced until explicit release. Sales/attendance/service outcomes need authoritative or labeled owner evidence. Track the full funnel and preserve keyword/multi-touch/unknown attribution instead of inventing exact post causality.

## Runtime reliability and safety
All outbound actions—including public publication, original gifts, ordinary replies, pass/email, reminders and retries—pass the common dispatch gate's correct variant.
Persist inbox/dedupe before admission ACK; use durable state/outbox, bounded retry, leases/fencing, cancellation and unknown-effect reconciliation. A 200 admission, model completion, send, access grant and sale are separate states.
Account rebind quarantines queued old actions. Upgrades preserve messages, consent, links, access, counters and unknowns. Compare-and-swap prevents rollback over newer client fixes; code rollback cannot undo sent effects or restore stale customer data.

## Command Center and deployment
Implement real setup readiness, campaign approval/calendar, conversations, fulfillment, contacts/follow-ups, bookings, failure and outcome views. Tenant-scoped commands carry expected revision and use existing validated lifecycle/Kanban interfaces; stale events/commands cannot undo newer state.
Mac, VPS and Docker use actual supported supervisors and persistent storage. Do not assume a Mac browser/mount exists remotely. This build's worktrees, scratch, temporary files, outputs and supported caches remain on verified external storage with child-process propagation checks.
Shared readiness is keyed by tenant/surface/account/environment/config/binding and invalidates on disconnect/rebind/relevant upgrade. Installed, configured, running, replied, fulfilled, access-ready and activated are distinct.

## Execution boundaries
Use the actual Universal v3 foundation with the explicit repair overlay. Temporary engineering control and durable client runtime are separate. Closing engineering never stops customer scheduling.
Admit useful capacity-fitting leaf cohorts; respect 50 workflows, 10 agents per tree and 500 active globally, real resource limits and no duplicate writers. Prepare independently; build only with its essential controls; integrate compatible accepted cohorts immediately under one repo owner, with at-most-hourly fallback sweep.
Required CI, focused independent candidate checks, named repair remote proof and immediate verified hygiene remain mandatory. Optional live tests do not stall safe repo work; required capabilities cannot be hidden.
This authoring task edits the package only. Separate-terminal build/merge authority does not authorize live account changes, new credentials, customer messages, client installation or fleet rollout.
