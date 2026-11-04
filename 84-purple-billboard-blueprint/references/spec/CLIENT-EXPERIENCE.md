<!-- Verbatim carry of the Purple Billboard client-system build document of the same name (spec version 2.1, policy dates 2026-10-24). Only one owner-identifier token was removed from DEC-20. This is the behavior contract for skill 84: where any other file in this skill differs, this one wins. Settled policy does not mean implemented behavior; runtime status is in ../wiring-map.md. -->

# Client and reader experience
## What the AI handles
Recover the client's business/audience/offers, known contact facts, calendar and actual assets. Ask only missing business or account-owner questions. Prepare useful missing resources, a coordinated monthly campaign, setup diffs, readiness and bounded repairs. Do not hand integration wiring back to the client.
The owner supplies business truth, necessary sign-in/permissions, one monthly content-and-fulfillment approval, and meaningful sales/handoff or exception decisions. No new credentials, messages or activation happen in this authoring task.

## One joined monthly review
Show 30 dates with the target problem, hook/reveal/Bonus, actual original resource, optional real extras, stable keyword, channel/account, next conversation step and schedule revision. Flag blocked rows before approval. Bind exact versions and permitted spares. A change invalidates the affected placement only.

## Reader routes
Personal profile: business Messenger link plus typed stable keyword. Do not infer the promise from a missing m.me reference or repeat the welcome to a returning person.
Page and IG comments: independently supported public/private opener actions. A comment alone is not a normal DM window. Wait for the documented qualifying customer reply before normal fulfillment/follow-up. IG direct DM is another separately verified route.
Deliver the original actual item directly in the eligible originating chat first. Optional collection access cannot gate it.

## Help after delivery
Ask a relevant question about the person's actual need, use known context and approved knowledge, and recommend the most useful resource, community, offer, appointment or human help. Capture is not completion. Do not require three generic questions before helping.
Verify live slot availability again when booking; only an actual persisted receipt means booked. Confirm time/timezone, location and change/cancel route. Hand off with context and an accepted owner/due action. Attendance, sales and service fulfillment need real source evidence, not an AI guess.

## Complete reminder examples
Use only after actual original fulfillment continuation criteria and when the additional guides are real. Every message is conditional on a fresh gate, missing/non-refused field, shared budget, active-conversation pause and current channel eligibility. Proposed slots are 2h/8h/20h after the first actionable invitation; timing is not yet activated. Initial invitation is not a reminder.

### Mobile missing
Initial DM invitation:
“I also have [actual guide titles]. Would you like a text with your access pass so you can keep them together? If so, send me your mobile number.”

Reminder 1:
“Would you still like access to those guides? Send me your mobile number and I can text your pass.”

Reminder 2:
“The guides can help with [relevant approved benefit]. If you want the text access, send me your mobile number. If you would rather leave it here, just say so.”

Approved final mobile reminder:
“Let me be direct: do you want these guides, or should I close this out? I offered because I want to help you move forward, but I’m not going to keep asking. If you want access, send me your mobile number and I’ll text your pass. If I don’t hear back, I’ll leave it here. This is my final message about getting you access.”

The final envelope is reserved under closing_final. STOP, field completion or handoff can cancel it before dispatch. After final acceptance or terminal closure there is no fourth reminder.

### Phone known, email missing
First confirm/use a relevant known phone under the requested-delivery consent. After actual access is ready, the single logical pass SMS may say:
“Here is your access to [actual collection]: [working pass]. What email should I use for backup access and the guide directory so you can open it on your computer?”

Only one logical SMS email-ask action is allowed. Known nonexecution retries that same action; unknown sends reconcile. Any remaining prompts are original eligible FB/IG DMs:
1. “If you would like backup access and the guide directory on your computer, what email should I use?”
2. “Would backup access be useful? Send the email you want me to use, or tell me you would rather skip it.”
3. “Let me be direct: do you want backup access and the guide directory on your computer, or should I close this out? I offered because I want to help you move forward, but I’m not going to keep asking. If you want it, send me your email and I’ll send your backup access and guide directory. If I don’t hear back, I’ll leave it here. This is my final message asking for your email.”

Do not say the person received an SMS unless that receipt exists. These three are the available shared reminder slots, not three new ones after prior mobile nudges.

### Email known, mobile missing
Do not ask email again. Offer the optional text pass and use the mobile sequence only while the person wants it. If email-only access is supported and requested, provide it without forcing a phone. A mobile refusal ends mobile chasing; it does not erase the original resource or the existing email.

### Fields captured at different times
Example: invitation at t0; mobile reminder at +2h; mobile supplied at +3h; working pass plus the one SMS email ask follows. The +8h and +20h slots can ask only email if still appropriate. Count remains one, then two, then three. No new 2h/8h/20h schedule begins at +3h.
Both fields already known: fulfill/help without capture prompts or reminders. Phone-only refusal of email preserves requested SMS access. Email-only refusal of phone stops mobile prompts. Neither field: original gift and eligible useful conversation remain.

## Returning people, refusals and overlapping giveaways
Reuse verified tenant/contact identity, consent, entitlement and relevant fields. A new keyword creates a new fulfillment request, not a second capture sequence. Duplicate webhook/post arrival cannot restart a final or declined sequence. A new explicit request is served, while rejected fields remain rejected. A new delivery preference can be recorded and fulfilled without silently opening another automatic chase.
Field refusal, sequence decline, channel opt-out, global stop and human takeover have different scopes. Unknown scope is not permission. Never merge contacts by name or across tenants.

## Failures and recovery
A failed direct resource pauses collection continuation and repairs that promise. SMS rejection stops unchanged retries; unknown sends reconcile. Email bounce stops repeated email, preserves existing access and uses an eligible requested correction route. Token expiry is not guide expiry. Late reply resumes the need without replaying welcome/menu.
Disconnected accounts pause affected actions; a new account binding quarantines queued old actions. Partial reveals resume missing approved comments after actual receipts. Duplicate publications/sends stop the affected writer for reconciliation; no automatic destructive deletion.

## Command Center and workload
Real tenant-scoped views: setup readiness; campaign approval/calendar/publication; conversations and ownership; original/bonus fulfillment; contact consent and follow-ups; bookings/handoffs; failures and verified outcomes.
Actions carry tenant, target, actor and expected revision, then go through the same owner/gate. Duplicate/stale events are ignored or reconciled by monotonic version/cursor; gaps reload an authoritative snapshot. No fake-only UI or arbitrary Skill-71-only event ingestion.
P0 unsafe sends/data/opt-out faults halt the affected scope; P1 broken promises/disconnections/hot handoffs need action; P2 recovered routine events go to a digest; P3 trends to monthly review. Coalesce alerts and name one owner/next action.
