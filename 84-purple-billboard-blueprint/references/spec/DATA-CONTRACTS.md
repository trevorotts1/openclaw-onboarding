<!-- Verbatim carry of the Purple Billboard client-system build document of the same name (spec version 2.1, policy dates 2026-10-24). Only one owner-identifier token was removed from DEC-20. This is the behavior contract for skill 84: where any other file in this skill differs, this one wins. Settled policy does not mean implemented behavior; runtime status is in ../wiring-map.md. -->

# Canonical data and action contracts
These are implementation requirements. Reuse existing verified durable storage and interfaces. Schemas and examples do not install enforcement.

## 1. Collection identity
Serialize at (tenant_id, canonical_contact_id, collection_sequence_id). FB, IG and SMS references share this lock, capture budget, SMS email-ask reservation and human-owner fence. A conversation ID is a channel reference, not the collection boundary.
Each requested item has a separate request/fulfillment record. A new post or keyword can add an item; it cannot restart final or declined capture. Same-tenant contact reconciliation requires verified identifiers and supported merge handling. Preserve stricter suppression, unknown sends and prior reminder totals; never merge by display name or across tenants.

## 2. Strict outbound variants
schemas/outbound-action.schema.json is a oneOf contract.

**Public placement:** scope public_placement; purpose SCHEDULED_POST, REVEAL_COMMENT or BONUS_COMMENT. Requires placement, campaign cycle, account/binding revision, exact approval manifest/revision, content/asset version, policy, owner fence, schedule, preconditions and receipt. No canonical contact or collection sequence is accepted. Reveal/Bonus requires the actual verified parent post ID.

**Person-directed:** scope person_directed; purpose original gift, ordinary AI reply, public reply to a person, comment private opener, pass, email ask, backup, reminder, booking confirmation or handoff notice. Requires tenant and canonical contact, with request/sequence references where applicable. A public reply to a particular reader belongs here even though its transport is public.

Both variants preserve action_id/logical_intent_key, immutable content, account-binding revision, policy/knowledge/playbook revisions where relevant, ownership fence, state precondition, timing, attempts, dispatch-gate record and provider receipt. Attempts are not new logical actions. A changed account binding quarantines old queued work; never reroute it silently.

## 3. Fresh gate before every dispatch and retry
Common checks: current authority/lifecycle; tenant/account binding; owner lease/fence; current state/policy; exact content/asset; logical-action receipts; applicable scheduling/quiet rules; no unknown effect being replayed.

Public placement branch: client publication pause/safety, exact approved placement/account/channel/schedule/CTA/keyword/assets/spares, actual platform publishing permission and reveal parent/order. It does not invent a recipient or require a DM window.

Person branch: trusted contact mapping; scoped consent/requested-delivery basis; field refusal, channel/global suppression and human ownership; purpose-specific platform eligibility; current sequence and precondition. A comment opener is not a normal inbound-DM window. Outbound and cross-channel messages do not refresh FB/IG eligibility.

Return ALLOW, WAIT_UNTIL, SUPPRESSED, QUARANTINED or RECONCILE_UNKNOWN with checked time, binding/policy/fence and supporting evidence. Recheck after queue delay. Original gift priority and final reminders bypass none of these checks.

## 4. Durable inbox/outbox and truthful stages
Authenticate/map the event, persist tenant/provider event dedupe before ACK, then serialize decisions. A body hash alone cannot collapse legitimate identical messages. Exclude own outgoing and reveal events by verified actor/direction.
Transactional state/outbox intent, bounded retries, leases and cancellation are required. Preserve received, durably admitted, deciding, queued, provider accepted, sent, delivered where supported, fulfilled/access verified and failed/unknown separately.
After a crash between provider acceptance and receipt persistence, reconcile history/status using the same action identity. Do not blindly resend or claim exact-once where the provider cannot guarantee it. A 200 admission is not a completed reply.

## 5. Direct original fulfillment
The original promised item's immutable content/version is independent of its hosting URL and optional membership vendor. Direct fulfillment T-13 has no dependency on bonus-access T-14/T-15.
Continue into optional collection only after: approved immutable resource; intended-reader accessibility; correct destination; supported successful transport status; no known failure. Accepted/sent is labeled as such unless an actual delivery receipt exists. A later failure pauses capture continuation and repairs original delivery. New helpful inbound questions can still be answered through their own gate.

## 6. Actual bonus access
Separate receipts: verified member identity → entitlement grant → credential issue → pass SMS → resource authorization/return access. Resume the failed step only. Later email binds to the same verified member, not a duplicate account. A login token's expiry is not entitlement or guide expiry.
GHL membership is a candidate. Its enrollment API alone does not prove mobile-only identity, credential automation or SMS recovery. Missing optional access cannot block original fulfillment, but the full advertised bonus product cannot show ready without it.

## 7. Capture, refusal and one SMS email ask
Reuse relevant known fields/display name. Standard route collects mobile for requested SMS access first. Delivery consent is separate from marketing.
Precedence: wrong binding/stale fence blocks all relevant effects; global stop suppresses unrequested outbound; channel opt-out blocks that channel; human ownership fences the bot; field refusal suppresses that ask; declined/final collection stops automatic capture. No-email does not erase requested SMS access. Unknown refusal scope is not broader permission.
One logical SMS email-ask action has queued, dispatching, accepted, failed_not_sent, unknown or suppressed state. Known nonexecution can retry the SAME action after a fresh gate; unknown must reconcile. A corrected number is not a new ask. Email arriving before dispatch suppresses the ask and leaves a separately rendered pass-only intent if needed. Accepted ask is not repeated because the person did not answer. Carrier failure after acceptance is not automatically proven nonexecution.

## 8. Reminder and final-action states
Initial invitation is separate from at most three shared escalating reminders. Proposed slots are 2h/8h/20h from the first actionable capture invitation, with a proposed 30-minute quiet interval. Adopt the exact policy before activation. A reply changes eligibility, not t0 or budget. No catch-up burst; skipped slots remain recorded.
Collection states include invited, awaiting_mobile, preparing_access, awaiting_email, paused_active, human_owned, closing_final, stopped_complete, stopped_declined, stopped_final and stopped_ineligible.

Final sequence:
1. Under the contact lock reserve final_action_id and final slot; enter closing_final(final_action_id), cancel sibling reminders and commit the final envelope with the new state version.
2. Only that exact reserved action may pass the ordinary gate while closing_final. No general bypass-stop exception.
3. STOP, field completion, refusal or handoff before dispatch cancels the reserved action.
4. Provider acceptance closes stopped_final; permanent nonexecution or expired slot closes without claiming sent. Unknown stays reserved/reconciling and cannot create another final.
5. After a crash, load reservation and actual receipt. Reconcile the same action; never reserve another. A late explicit request can receive useful help/fulfillment without restarting capture.

Worked crash trace: final action A is committed; dispatch becomes unknown; process exits. Restart reads A and does not resend. Provider reconciliation finds A accepted; state closes and siblings stay canceled. A prior STOP would instead suppress any unsubmitted A. This is distinct from the engineering loop's uppercase lifecycle.

## 9. Engineering state and action acknowledgement
Canonical lifecycle: NOT_INSTALLED → ADOPTING → RUNNING/PAUSED_RESUMABLE → CLOSING → CLOSED; CANCELED is distinct. No CLOSED_VERIFIED alias.
A control action has action_state not_requested, queued, dispatched, acknowledged, completed, unknown, failed or canceled, with separate ACK and completion receipts.
For shutdown: persist CLOSING and stop action; host ACK does not close. On verified stop completion plus finalizer terminal receipt, update loop and resume lifecycle to CLOSED at one applied event revision. Crash after ACK but before completion resumes reconciliation; it never recreates a controller or claims CLOSED early. CLIENT_RUNTIME jobs remain protected.

## 10. Approval, readiness and migration
Monthly manifest binds exact tenant/cycle/placement/account/channel/schedule/timezone/content/CTA/keyword/immutable assets/conversation policy/allowed spares. Mutation invalidates that unit only.
Shared readiness key: tenant/surface/account/environment/adapter/config/binding revision and evidence time. Disconnect, rebind and relevant upgrade invalidate affected proof in onboarding, 999 and CC.
Compatibility records schema/protocol/reader-writer versions, migration checkpoint, writer generation and config revision. Rollback compares the revision the upgrade wrote; a newer client fix causes conflict/forward repair. Never roll back sent effects, contact facts, consent/suppression, counters or unknown-send reconciliation.

## 11. Focused interface examples
- Given an approved monthly post with no person, public placement validates; adding canonical_contact_id is rejected.
- Given a direct gift, missing canonical_contact_id is rejected.
- Given a reveal before parent publication, dispatch is blocked.
- Given accepted final A with a lost local receipt, restart reconciles A and closes once.
- Given rejected SMS ask A with known nonexecution, correction retries A; unknown A is not replayed.
- Given optional access unavailable, direct gift can continue while bonus readiness remains blocked.

Full first, second and final customer wording and reverse/partial cases are in CLIENT-EXPERIENCE.md. Product handlers must prove these traces independently; authoring checks alone do not.
