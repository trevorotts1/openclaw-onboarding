# Wiring map: Purple Billboard step to exact module

Every path below is relative to the skills root (the folder that holds the numbered skill folders and `shared-utils/`; on a box that is `~/.openclaw/skills/`, the same layout Skill 35's own approval gate uses when it calls `$SKILL_DIR/../shared-utils/manifest/monthly_manifest.py`). `tests/test_blueprint_wiring.py` fails if any path named here stops existing, or if a function, class or command-line subcommand named beside a module is no longer defined in that module, so this map cannot silently rot. CI runs that test as an explicit step in `.github/workflows/qc-static.yml`.

How to reach the code: every module is Python 3 standard library only. Either run its command line with `python3 -I <path> ...`, or import it after `sys.path.insert(0, "<its folder>")`. Nothing in this skill adds a runtime, a scheduler, a router, or a second copy of any rule. Where a rule lives in one module, call that module.

Status words used below:

- BUILT: the module is on main and the repository tests it (a test file for it, a self-check that CI runs, or contract tests that exercise it).
- BUILT (no dedicated test): the module is on main, but no test in the repository exercises it by name. It may work; nothing here proves it. Say so before relying on it.
- BUILT IN COMMAND CENTER: built and merged in the separate Command Center repository (pinned in `cc-compat.json`), not in this one.
- LIBRARY ONLY: built and tested, but no skill, hook, cron or script calls it. An agent reaches it only because this skill tells it to.
- BLOCKED: the capability is not available; the module reports so and the system must say so.
- NOT PRESENT: SPEC.md assumes it, the repository does not contain it.

## Step 0. Readiness, authorization and host (before anything else)

| What | Where | Status |
|---|---|---|
| Shared readiness projection: installed, running and live are three separate states; a proof is invalidated by rebind, upgrade or disconnect | `shared-utils/shared_readiness.py` (`project`, `proof_valid`); consumed by `32-command-center-setup/scripts/verify-tenant-readiness.py`; contract `38-conversational-ai-system/schemas/readiness-evidence.schema.json` | BUILT |
| Validate any record against its contract | `38-conversational-ai-system/tools/pb_contracts.py validate --kind <collection\|outbound\|approval\|readiness\|action\|lifecycle\|compatibility\|reconciliation> --file <json>` | BUILT |
| Supported host (Mac, VPS, Docker), verified persistence, external storage and restart | `shared-utils/runtime/host.py`, `shared-utils/runtime/external.py`, `shared-utils/runtime/persistence.py` | BUILT |
| Upgrades that must not roll back a newer client fix or unsend anything | `38-conversational-ai-system/tools/compat_guard.py` (`cas_update`, `migrate`, `forward_repair`), contract `38-conversational-ai-system/schemas/compatibility-record.schema.json` | BUILT |
| Activation authorization (named clients, hosts, channels, accounts, test recipients, window, operator, support, rollback) | Owner-written authorization. There is no module that grants it. | Owner decision (DEC-19). Never inferred, never assumed from a merge. |

## Step 1. Business discovery

| What | Where | Status |
|---|---|---|
| Persistent acquisition brief: business, offers, audience, proof, constraints, channels, geography, seasonality; every fact carries provenance; a recorded fact is never asked again; an assumed fact blocks readiness until a person confirms it | `38-conversational-ai-system/tools/acquisition_brief.py` (`AcquisitionBrief`) | BUILT |
| Command-line driver: `next`, `answer`, `bind owner\|approval\|capacity\|claims`, `status`, `ready` | `38-conversational-ai-system/tools/guided_discovery.py <brief.json> ...` | BUILT (no dedicated test), LIBRARY ONLY (nothing else calls it) |

Ask only what the brief reports as unanswered. Reuse known business facts before asking.

## Step 2. Asset inventory and preparation

| What | Where | Status |
|---|---|---|
| Registry of actual assets (original gifts, optional extras), rights, quality, versions, accessibility, destinations; a preparation worklist for what is missing; campaign readiness | `38-conversational-ai-system/tools/asset_registry.py` (`AssetRegistry`: `record_present`, `record_missing`, `request_preparation`, `mark_ready`, `preparation_worklist`, `campaign_readiness`, `require_ready`) | BUILT, LIBRARY ONLY |
| Immutable promise: `(item_id, version, content_sha256)`, independent of the hosting URL | `38-conversational-ai-system/tools/direct_fulfillment.py` (`PromisedItem`, `Destination`) | BUILT |
| The playbook's method for what a free resource is and how to size it | `references/playbook/04-swipe-pack.md`, `references/playbook/01-main-playbook.md` | Reference |

Never advertise a collection that does not exist. Draft a missing useful asset for owner review before promising it. No fictional collections, no token endpoints, no invented customer outcomes.

## Step 3. Existing-object discovery, plan, permitted setup

| What | Where | Status |
|---|---|---|
| Discover and reuse, scoped diff, provision only what the owner permitted, step receipts, idempotent resume, hard refusal to provision credentials or model configuration | `38-conversational-ai-system/tools/bootstrap_engine.py` (`BootstrapEngine.discover`, `.plan`, `.run`) | BUILT. It provisions FILES and receipts only (no network, no subprocess). It does not create anything inside GoHighLevel. |
| Creating or changing objects inside Convert and Flow (workflows, fields, tags) | Skill 44: `44-convert-and-flow-operator/SKILL.md` | Only inside the owner's named scope. Reuse existing objects; never overwrite a customization. |
| Missing permission, API or entitlement | Produce an exact prepared owner action. Never invent an endpoint. | Rule |
| Bonus-access capability decision | Step 8 below | BLOCKED |

## Step 4. Monthly approval of the 30 exact packs

| What | Where | Status |
|---|---|---|
| Method: monthly hunt, hooks, numbered reveal, Bonus, used-log, dedupe, spares | `references/playbook/03-ai-sop-and-rules-checklist.md` (procedures 1 to 6 and Part B), `references/playbook/04-swipe-pack.md`, `references/playbook/01-main-playbook.md` | Reference |
| Approval lifecycle: `approve` (join a draft campaign into one approved revision), `amend` (invalidates that placement only), `reapprove`, `next_cycle`, `check` | `shared-utils/manifest/monthly_manifest.py`; contract `38-conversational-ai-system/schemas/approval-manifest.schema.json` | BUILT |
| The DM door, built at pack-write time: Page binding, ref, link, keyword, canonical Bonus sentence | `shared-utils/routes/page/messenger_link.py` (`record_page_binding`, `build_ref`, `build_messenger_link`, `keyword_for`, `bonus_cta`, `build_bonus_placement`) | BUILT |
| Permanent keyword registry, tombstoned, never recycled onto another item | `38-conversational-ai-system/tools/durable_store.py` (`register_keyword`, `keyword_item`, `keyword_rows`) | BUILT |
| One joined review shown to the owner (30 dates, hook, reveal, Bonus, actual original resource, real extras, keyword, channel and account, next step, revision; blocked rows flagged first) | The agent assembles it from the manifest. No renderer exists. | NOT PRESENT as a view |

Brand color: SPEC.md says use the client's consistent brand color. The playbook text says purple and never black. The black-color exception and any cross-surface reuse are an open owner decision (DEC-17); hold only the affected variant, continue unrelated approved placements.

## Step 5. Publication through Skills 35 and 57

Scheduling and publishing stay owned by Skill 35 (`35-social-media-planner`) and Skill 57 (`57-social-media-in-a-box`). Do not build or call a second scheduler.

| What | Where | Status |
|---|---|---|
| Approval gate before a Purple placement publishes: refuses with exit 7 unless the monthly manifest covers this placement at its current terms and revision | `35-social-media-planner/scripts/run-publishing-cycle.sh --approval-manifest <path> [--placement <id>]... [--check-approval-only]`, which calls `shared-utils/manifest/monthly_manifest.py check` | BUILT and wired |
| Account-type capability: a personal profile is always assisted or unavailable, never unattended; an assisted placement reports `awaiting-operator` or `operator-confirmed`, never `published` | `35-social-media-planner/config/profile-capabilities.json`, `35-social-media-planner/scripts/profile_capability.py {capabilities,request,confirm,status,guard}`, `shared-utils/personal_profile_capability.py`, `35-social-media-planner/PROFILE-CAPABILITIES.md` | BUILT |
| Public-placement envelope (no contact; scope `public_placement`; purposes `SCHEDULED_POST`, `REVEAL_COMMENT`, `BONUS_COMMENT`) and its fresh gate | `38-conversational-ai-system/schemas/outbound-action.schema.json`, `38-conversational-ai-system/tools/pb_contracts.py dispatch`, `38-conversational-ai-system/tools/outbound_gate.py` | BUILT |
| True receipts, post-then-ordered-comments, reveal timing in minutes, resume only the missing approved pieces | `shared-utils/receipts/publication_receipts.py` (`true_receipt`, `approved_order`, `resume_plan`, `reveal_timing_errors`) | BUILT, LIBRARY ONLY (only `38-conversational-ai-system/tools/reconciliation.py` references it) |
| Skill 57 | No Purple-specific hook exists in `57-social-media-in-a-box`. Do not assume one. | NOT PRESENT |

Personal-profile unattended publishing and ongoing replies are UNPROVEN. Prepare the exact placement and hand the owner one manual step, or use only a route the owner has separately proved and authorized.

## Step 6. Comment and DM routing

| Route | Where | Status |
|---|---|---|
| Personal profile: business Messenger link plus a typed stable keyword | `shared-utils/routes/page/messenger_link.py`, `references/playbook/06-dm-door-and-agreed-flow.md` | BUILT. Link attribution is NOT PROVEN (`REF_ATTRIBUTION`). |
| Page comments and Page Messenger: entry resolution, eligibility per route (public reply, private opener, Messenger), inbound admission, opener decision, capability status | `shared-utils/routes/page/facebook_routes.py` (`resolve_entry`, `evaluate_eligibility`, `admit_inbound`, `opener_decision`, `capability_status`) | BUILT, LIBRARY ONLY |
| Instagram comments and direct: its own account record, comment filters, event admission, eligibility, gated dispatch | `shared-utils/routes/instagram/route_adapter.py` (`resolve_account`, `normalise_event`, `admit_instagram_event`, `evaluate_eligibility`, `dispatch_instagram_action`) | BUILT, LIBRARY ONLY |
| Turning a public comment into a conversation (per run, not a poller) | `35-social-media-planner/scripts/comment_reader.py` (own-author ids REQUIRED; stamps `- duty: public_answer`) | BUILT. Ongoing comment monitoring is NOT built. |
| Which channel may answer which duty (`public_answer` allows the public thread and refuses DM and SMS; `private_answer` the reverse; unreadable duty allows nothing) | `38-conversational-ai-system/tools/answer_duty.py` | BUILT and enforced at the send gate |
| Who answers an interactive step (one responder per input) | `38-conversational-ai-system/tools/interactive_owner.py`, `38-conversational-ai-system/launch/interactive-owner-contract.md` | BUILT |
| Inbound identity and dedupe before any reply: persist the provider event first; duplicate exits 3, end the turn | `38-conversational-ai-system/tools/pb_send.py admit --outbox <outbox-file> --tenant <id> --message-id <id>`, plus optional `--contact <id>`, `--direction <direction>` (default `inbound`) and `--own-actor <id>` (repeatable). `--outbox`, `--tenant` and `--message-id` are required. Exit 0 admitted, 2 usage error, 3 duplicate (end the turn, do not reply). It writes only to the local outbox file. | BUILT, enforced by Skill 38's runtime rules |
| One canonical contact per person inside a tenant; never merge by name or across tenants | `38-conversational-ai-system/tools/tenant_identity.py` | BUILT |
| Serialize at (tenant, canonical contact, collection sequence) so FB, IG and SMS share one lock and one budget | `38-conversational-ai-system/tools/collection_lock.py` | BUILT |
| Conversation workflow playbooks (parse, validate, structure hash) when a comment or DM playbook is authored or changed | `38-conversational-ai-system/tools/playbook_engine.py {parse,validate}` | BUILT |
| Contract QC for the whole outbound and publication layer | `38-conversational-ai-system/scripts/qc-pb-contracts.sh` | BUILT |
| Playbook scripts for the comment replies and openers | `references/playbook/02-strategy-guide.md` (conversation playbook), `references/playbook/05-conversation-ai-build-plan.md` | Reference. The build plan is a design for review, not an installed capability. |

A comment alone does not open a normal DM window. A private opener uses its own permission (one per comment, within the platform's stated window). Wait for the documented qualifying reply before normal fulfillment or follow-up. Do not drip to an ignored opener.

## Step 7. Original fulfillment (always first, never gated by the bonus)

| What | Where | Status |
|---|---|---|
| Deliver the actual original item directly in the eligible originating chat; accepted or sent is not delivered without a receipt; later failure pauses capture continuation and repairs the promise | `38-conversational-ai-system/tools/direct_fulfillment.py` (`fulfill`, `resume`, `can_continue`, `record_delivery_proof`, `post_gift_help`); command line `38-conversational-ai-system/tools/pb_contracts.py fulfill`, `fulfill-basis`, `fulfill-access`, `fulfill-resume`, `fulfill-proof`, `fulfill-continue` | BUILT |
| Every send goes through the one gate: fresh verdict `ALLOW`, `WAIT_UNTIL`, `SUPPRESSED`, `QUARANTINED` or `RECONCILE_UNKNOWN` on every dispatch and every retry | `38-conversational-ai-system/tools/outbound_gate.py` (`dispatch`), `38-conversational-ai-system/tools/consent_gate.py`, `38-conversational-ai-system/tools/suppression_ledger.py` | BUILT |
| Sending a reply in a live conversation. A live send needs the owner's written authorization (safety rules 5 and 7); installing or merging this skill is not that authorization | `38-conversational-ai-system/tools/pb_send.py reply --outbox <outbox-file> --tenant <id> --contact <id> --channel <channel> --text <text> --inbound-message-id <id> --identity-db <identity-db-file>`. All seven of those are required. Optional: `--conversation-id`, `--handoff-db`, `--sent-index`, `--approval-ref`, `--answer-duty-log`, `--worker-id` (default `pb-send`). The transport is chosen by `--transport {journal,ghl}` and the default is `journal`: it needs `--journal <file>`, writes the reply to that local file and sends nothing to anyone. A live send needs `--transport ghl` and the Convert and Flow location token in the environment variable named by `--pit-env` (default `GHL_LOCATION_PIT`); `--tenant` is then the location id. If that variable is missing the command stops before sending and never prints the token. Exit 0 sent, 2 usage or contract error, 4 gate blocked, 5 not claimed (already dispatched, unknown or leased); on 4 or 5 do not send. Never post to the Conversations API directly. A reply counts as sent only when a message id comes back. | BUILT |
| Unknown outcome after a crash: reconcile the same action, never resend | `38-conversational-ai-system/tools/reconciliation.py` (`needs_reconciliation`, `sweep_inflight`, `resolve_unknown`) | BUILT |
| Durable inbox and outbox, leases, truthful stages | `38-conversational-ai-system/tools/durable_store.py` | BUILT |

## Step 8. Bonus access (optional, currently blocked)

| What | Where | Status |
|---|---|---|
| Honest capability decision: identity, grant, credential, SMS pass, return and recovery as separate steps with evidence | `shared-utils/bonus/access_capability.py`; operator command line `44-convert-and-flow-operator/tools/bonus_access_decision.py {decision,route,evidence,inventory-routes,request,plan}`; write-up `shared-utils/bonus/BONUS-ACCESS-CAPABILITY-DECISION.md` | BUILT. The capability module has its own tests; the operator command line `bonus_access_decision.py` has none of its own (BUILT, no dedicated test) |
| Five separate authorizations, return access, email-later on the same member, failed-step resume | `shared-utils/bonus/access_adapter.py`; `44-convert-and-flow-operator/tools/bonus_access_decision.py {member-state,access-authorize,access-bind,access-fail,access-defer,access-resume}` | BUILT. The adapter has its own tests; its command line has none of its own (BUILT, no dedicated test) |

When this skill was written, `bonus_access_decision.py route` reported `advertised_bonus_ready: false`, `reason_code: BONUS_ACCESS_CAPABILITY_BLOCKED`, route `assisted_operator`, with identity, grant, credential, return and recovery all blocked and `no_invented_api: true`. Re-run it; do not trust this line. While it says blocked: the original gift still goes out (Step 7), the advertised bonus product stays "not ready", and the pass is never described as sent. An expired login credential is not expired guides.

## Step 9. Capture (mobile first, one SMS email ask)

| What | Where | Status |
|---|---|---|
| Reuse known fields and display name; plan the asks; field refusal; later email binds to the same verified member; ONE logical SMS email-ask action with states queued, dispatching, accepted, failed_not_sent, unknown, suppressed | `shared-utils/capture/progressive_capture.py` (`plan_capture`, `refuse`, `bind_email`, `SmsEmailAsk`) | BUILT, LIBRARY ONLY |
| Scoped refusal, global stop, channel opt-out, human ownership precedence | `38-conversational-ai-system/tools/consent_gate.py`, `38-conversational-ai-system/tools/suppression_ledger.py`; contract `38-conversational-ai-system/schemas/collection-state.schema.json` | BUILT |
| Useful help after the gift: needs discovery, approved knowledge, a real recommendation (resource, community, offer or calendar) | `38-conversational-ai-system/tools/post_delivery_discovery.py` (`Discovery`, `Catalog`, `KnowledgeBase`) | BUILT |

Delivery consent is not marketing consent. Phone-only, email-only and declining people still get the original item and help. Capture is never completion.

## Step 10. Reminders (initial invitation is separate; three shared reminders at most)

| What | Where | Status |
|---|---|---|
| Shared reminder slots, active-conversation pause, no catch-up burst, reserved `closing_final` action, STOP and completion cancel before dispatch, crash-safe reconcile | `shared-utils/reminders/reminder_state_machine.py` (`ReminderPolicy`, `ReminderStateMachine.adopt_policy`, `.open_sequence`, `.record_initial_invitation`, `.send_reminder`, `.reserve_final`, `.dispatch_final`, `.reconcile_final`) | BUILT, LIBRARY ONLY |
| Exact customer wording for the first, second and final messages and each case | `references/spec/CLIENT-EXPERIENCE.md` | Reference |

The 2h / 8h / 20h timing and the 30-minute quiet interval are PROPOSED, not activated (DEC-15). Adopt an exact policy version before any timed capture runs. Until then no timed capture activates; inbound help and direct fulfillment continue.

## Step 11. Booking and human handoff

| What | Where | Status |
|---|---|---|
| Approved calendar capacity, recheck at commit, booked only with a persisted receipt, timezone, location and change path, reschedule and cancel | `38-conversational-ai-system/tools/booking_service.py` (`load_policy`, `open_runtime`) over `shared-utils/booking/followthrough.py` (`BookingFollowThrough`: `resolve_calendar`, `offer_slots`, `book`, `reschedule`, `cancel`, `confirmation_text`); playbook `38-conversational-ai-system/launch/booking-playbook.md` | BUILT, LIBRARY ONLY. `followthrough.py` has its own tests; `booking_service.py` has only a self-check that CI runs (BUILT, no dedicated test). The operator policy and the live calendar and provider adapters are supplied by the caller; nothing is defaulted. |
| Owned handoff: context, accepted owner, due action, backup owner, bot fenced until explicit release | `shared-utils/handoff/handoff.py` (`HandoffStore`: `create`, `accept`, `escalate`, `backup_accept`, `release`, `gate_decision`) | BUILT |

## Step 12. Outcomes and attribution

| What | Where | Status |
|---|---|---|
| Attendance, sales and service outcomes only from authoritative or labeled owner evidence; keyword and multi-touch attribution kept; unknown stays unknown; a booking is not a sale | `shared-utils/booking/followthrough.py` (`record_outcome`, `outcome_state`, `attribute`), `38-conversational-ai-system/tools/post_delivery_discovery.py` (`record_outcome`, `attribution`) | BUILT |
| Command Center views (a separate repository, `trevorotts1/blackceo-command-center`, pinned in `cc-compat.json`; paths below are inside it and exist at the pinned tag `v7.6.126` and on its `main`). "Not in this repository" is a location statement, not a claim that the views are missing | Pointer table: `SKILL.md`, section "Command Center views" | BUILT IN COMMAND CENTER |
| T-31 setup readiness: READY, BLOCKED or UNKNOWN per item, with evidence | `src/components/setup/SetupReadinessPanel.tsx`, `src/app/api/setup/readiness/route.ts` (PR 598). Open `/setup`, or `GET /api/setup/readiness` with operator identity | BUILT IN COMMAND CENTER |
| T-32 campaign approval: calendar, approval state per placement, publication receipts, targeted approve or hold | `src/app/campaigns/[id]/approval/page.tsx`, `src/lib/campaigns/approval-contract.ts` (PR 603). Open `/campaigns/<campaign id>/approval`. The view cannot prove a placement's account binding, call to action or keyword: those stay UNKNOWN, never approved, and the campaign summary is never fully approved (PARTIAL at best) | BUILT IN COMMAND CENTER |
| T-33 fulfillment pause, retry and handoff (owner-only, tenant-scoped, expected-version checked, receipt per step) | `src/lib/fulfillment/operations.ts` (PR 604, 614). Library only: no screen, route or button calls it on `main` or at the pinned tag. Thread state: `GET /api/tasks/<task id>/messages` returns `fulfillment` on `main` (PR 614), not yet at the pinned tag | BUILT IN COMMAND CENTER, LIBRARY ONLY |
| T-34 failures, bookings and outcomes for one client | `src/app/workspace/[slug]/exceptions/page.tsx` (PR 602). Open `/workspace/<slug>/exceptions`. Bookings and outcomes show UNKNOWN with a reason until their producers (T-28, T-30) are on `main` | BUILT IN COMMAND CENTER |
| T-35 Kanban cards from real lifecycle events, with stale and unknown states | `src/lib/board/lifecycle-projection.ts` (PR 596). Open `/tasks/all`; each task from `GET /api/tasks` carries a `lifecycle` object | BUILT IN COMMAND CENTER |
| Other views the spec asks for (conversations and ownership, contact consent and follow-ups) | Not verified by this skill. Check the Command Center repository before saying they exist | Undetermined |

## Pieces that exist but are not part of this flow

`shared-utils/delivery/` is the Convert and Flow page-delivery stream for funnels and websites (N-page delivery, checkpoints, link resolution, publishing readback). Despite the name it is NOT how the original gift or bonus is delivered; that is Step 7 and Step 8. Do not route gift delivery through it.

`CONTROL/` holds the temporary engineering-loop controller used while the system was built. Engineering state is separate from the durable client runtime and closing engineering never stops client scheduling. Nothing in `CONTROL/` is a runtime dependency of this skill.

## Caller census (why this skill exists)

Checked on the day this skill was written with `git grep -w <module>` over non-test `*.py`, `*.sh`, `*.md` and `*.json` files (positive control: `answer_duty` is found in the Skill 35 SKILL.md; a first attempt with `\b` returned zeros because the platform's regex does not support it, which is why word matching is used).

- No SKILL.md of Skills 35, 38, 44 or 57 names any of: `publication_receipts`, `progressive_capture`, `reminder_state_machine`, `followthrough`, `booking_service`, `facebook_routes`, `guided_discovery`, `asset_registry`, `post_delivery_discovery`, `acquisition_brief`, `direct_fulfillment`, `pb_send`, `monthly_manifest`, `messenger_link`. Skill 35's SKILL.md names only `answer_duty` and the profile-capability pieces.
- No script, hook or cron calls `publication_receipts`, `progressive_capture`, `followthrough`, `booking_service`, `facebook_routes` or `guided_discovery`; their only non-test referrers are other Purple Billboard modules or documentation.
- What is wired in code today: `run-publishing-cycle.sh` calls `monthly_manifest check`; `outbound_gate` imports `answer_duty`, and `consent_gate.make_gate_evaluator` is composed into the gate by `pb_send` and `direct_fulfillment`; `direct_fulfillment` calls `outbound_gate`, `durable_store` and the Instagram eligibility evaluator; `pb_send` composes the gates for live replies and Skill 38's runtime rules require it.

So an agent that is not told about these modules never reaches them. This skill names them, in the order the work happens.
