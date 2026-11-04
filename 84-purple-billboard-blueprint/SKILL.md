---
name: purple-billboard-blueprint
description: >
  The Purple Billboard client-acquisition system, wired end to end. Use it when
  the owner asks for the Purple Billboard Playbook, a billboard post, a hook and
  reveal thread, a giveaway keyword campaign, a monthly 30-pack of daily posts
  with one monthly approval, a comment-to-DM or DM-door flow, original gift or
  Bonus delivery, mobile and email capture with reminders, or booking and human
  handoff that comes out of a post. It routes each step of the flow (discovery,
  asset inventory, monthly approval, publication through Skills 35 and 57,
  comment and DM routing, original fulfillment, bonus, capture, reminders,
  booking and handoff, outcomes) to the exact module that already implements it
  in Skills 38, 44 and 35 and in shared-utils, and states the safety boundaries.
  It adds no new engine, scheduler, router or endpoint.
version: 0.1.1
---

# Purple Billboard Blueprint (Skill 84)

The Purple Billboard system was built as pieces inside existing skills: the conversation brain in Skill 38, transport and bonus decision in Skill 44, scheduling in Skills 35 and 57, and shared modules in `shared-utils/`. No SKILL.md named those pieces, so an agent asked for a Purple Billboard campaign did not know they existed. This skill is the missing instruction layer. It carries the method (the playbook), the behavior contract (the spec), and the map from each step to the module that implements it.

Skill 38 is the conversation brain. Skill 44 / Convert and Flow (GoHighLevel) is transport, CRM, workflows and appointments. Skills 35 and 57 own the schedule. This skill never replaces any of them and never runs a competing scheduler or router.

## Use this skill when the owner asks for

- the Purple Billboard Playbook, a "purple billboard" post, a hook-and-reveal post, or "one billboard a day"
- a giveaway or lead-magnet campaign that runs on a keyword ("comment the word ...")
- a month of daily posts prepared as 30 packs for one monthly approval, a used-log, spares, or dedupe of hooks
- comments turned into conversations, a comment-to-DM flow, a Messenger DM door, or a Bonus comment link
- delivering the promised original gift, or the optional bonus guides or membership pass
- capturing a mobile number or email after the gift, follow-up reminders, or a stop or opt-out inside that flow
- booking, a human handoff, or tracking sales and appointments that came from the posts

Do not use it for ordinary social posting with no giveaway (Skills 35 and 57 alone), for building a sales funnel (Skills 49 and 71), or for generic conversation playbooks (Skill 38 alone).

## Read first, in this order

1. `references/safety-boundaries.md` (binding; wins over every playbook file)
2. `references/spec/SPEC.md`, then `references/spec/DATA-CONTRACTS.md`, `references/spec/CLIENT-EXPERIENCE.md`, `references/spec/DECISIONS.md`, `references/spec/DEPLOYMENT.md`
3. `references/wiring-map.md` (step to exact module, status, caveats)
4. The playbook files in `references/playbook/` for the step you are on (index at the end)
5. The section "How to talk to the owner" below, before your first message to the owner

Paths below are relative to the skills root (`~/.openclaw/skills/` on a box). Run commands with `python3 -I`. Everything is Python 3 standard library.

## The flow, step by step

| # | Step | Do this | Implemented by |
|---|---|---|---|
| 0 | Readiness | Confirm host, persistence, readiness proof and written owner authorization before any live effect | `shared-utils/shared_readiness.py`, `shared-utils/runtime/host.py`, `38-conversational-ai-system/tools/compat_guard.py`; authorization is the owner's, never inferred |
| 1 | Discovery | Reuse known facts; ask only the unanswered questions; produce one approved acquisition brief | `38-conversational-ai-system/tools/guided_discovery.py`, `38-conversational-ai-system/tools/acquisition_brief.py` |
| 2 | Asset inventory | Inventory real originals and extras, rights, versions, destinations; draft missing useful assets for review; never promise what does not exist | `38-conversational-ai-system/tools/asset_registry.py`, `38-conversational-ai-system/tools/direct_fulfillment.py` (`PromisedItem`) |
| 3 | Setup | Discover and reuse existing objects, scoped diff, permitted provisioning only, receipts, resume | `38-conversational-ai-system/tools/bootstrap_engine.py` (files and receipts), Skill 44 for objects in Convert and Flow within the owner's named scope |
| 4 | Monthly approval | Build 30 exact dated packs (hook, 6 teaching comments, Bonus, keyword, channel and account, conversation path, spares); build each DM door at pack-write time; one joined review; a changed unit invalidates only itself | `shared-utils/manifest/monthly_manifest.py`, `shared-utils/routes/page/messenger_link.py`, `38-conversational-ai-system/tools/durable_store.py` (`register_keyword`); method in `references/playbook/03-ai-sop-and-rules-checklist.md` |
| 5 | Publication | Publish only approved placements, through Skill 35 or 57; personal profile is assisted; verify true receipts | `35-social-media-planner/scripts/run-publishing-cycle.sh --approval-manifest ...`, `35-social-media-planner/scripts/profile_capability.py`, `shared-utils/receipts/publication_receipts.py` |
| 6 | Comment and DM routing | Route by channel: profile (Messenger link plus keyword), Page comments and Messenger, Instagram; admit the event before replying; one canonical contact; right channel for the duty | `shared-utils/routes/page/facebook_routes.py`, `shared-utils/routes/instagram/route_adapter.py`, `35-social-media-planner/scripts/comment_reader.py`, `38-conversational-ai-system/tools/pb_send.py`, `38-conversational-ai-system/tools/answer_duty.py`, `38-conversational-ai-system/tools/tenant_identity.py` |
| 7 | Original fulfillment | Deliver the actual original item in the eligible chat first, through the gate; keep accepted, sent and delivered apart | `38-conversational-ai-system/tools/direct_fulfillment.py`, `38-conversational-ai-system/tools/outbound_gate.py`, `38-conversational-ai-system/tools/reconciliation.py` |
| 8 | Bonus | Offer real extras only; run the capability decision; while blocked, say "not ready" | `44-convert-and-flow-operator/tools/bonus_access_decision.py`, `shared-utils/bonus/access_capability.py`, `shared-utils/bonus/access_adapter.py` |
| 9 | Capture | Mobile first; ONE logical SMS email ask; honor refusal precedence; keep helping | `shared-utils/capture/progressive_capture.py`, `38-conversational-ai-system/tools/consent_gate.py`, `38-conversational-ai-system/tools/post_delivery_discovery.py` |
| 10 | Reminders | Initial invitation separate; at most three shared reminders; adopt the timing policy first; reserved final action | `shared-utils/reminders/reminder_state_machine.py`; wording in `references/spec/CLIENT-EXPERIENCE.md` |
| 11 | Booking and handoff | Recheck live capacity at commit; booked only with a persisted receipt; handoff has an accepted owner, due action and backup, and fences the bot | `38-conversational-ai-system/tools/booking_service.py`, `shared-utils/booking/followthrough.py`, `shared-utils/handoff/handoff.py` |
| 12 | Outcomes | Record sales, attendance and service outcomes only from authoritative or labeled owner evidence; unknown stays unknown | `shared-utils/booking/followthrough.py`, `38-conversational-ai-system/tools/post_delivery_discovery.py` |

`references/wiring-map.md` gives, for every row, the entry points, how to call them, whether they are BUILT, LIBRARY ONLY, BLOCKED or NOT PRESENT, and the caveats.

## Safety boundaries (short form; full text in `references/safety-boundaries.md`)

- Every outbound action passes the common gate, fresh on every dispatch and retry: `38-conversational-ai-system/tools/outbound_gate.py`. Live replies go only through `38-conversational-ai-system/tools/pb_send.py` (`admit`, then `reply`; every required argument is in `references/wiring-map.md`, Steps 6 and 7). Its default transport only writes a local file and sends nothing; a live send needs `--transport ghl` and the owner's written authorization. Drafted is not sent.
- No activation, no live effect, no customer message, no credential, no fleet or client change without the owner's written authorization naming client, host, channels, accounts, test recipients, window, operator and rollback limits. A merge or an install is not that authorization.
- Never post what the owner has not approved. Never post a Bonus that still holds a placeholder link.
- Personal-profile publishing is unproved. A personal profile is assisted or unavailable, never unattended, and an assisted placement is never reported as published.
- The original gift is delivered first and is never gated by capture, membership or a list signup. Accepted or sent is not delivered without a receipt.
- Delivery consent is not marketing consent. STOP, opt-out, refusal and human ownership always win.
- Reminder timing is proposed, not activated. Bonus access is blocked until its capability decision clears. Link attribution is not proven.
- Do not invent endpoints, tools, collections, statistics or outcomes. If a module or capability is missing, say so and prepare the owner action.

## How to talk to the owner

Act as a warm, patient, helpful guide for a business owner who is not technical and is often over 60. This applies to every word the owner reads and every word their customers read. The rest of this file is for you, not for them.

- Use plain everyday words and short sentences. Ask one question at a time, then wait for the answer.
- Never say module names, file names or technical words to the owner or to their customers. That includes: gate, envelope, DM door, tombstone, manifest, schema, keyword registry, dispatch, receipt, tenant, webhook, pack, route, capability decision. Say what it means instead: "your approved posts", "the word people comment", "your free gift", "your calendar".
- Give every blocked or not-ready state one plain sentence that says what is true and what still happens. For example, bonus access not ready yet: "The bonus area isn't switched on yet. I'll still send people your free gift right away." Waiting on approval: "I'm holding this until you say it's okay." A personal Facebook page: "Facebook needs you to press post on your own page, so I'll get it ready and show you the one step." Someone asked to stop: "They asked us to stop, so we won't message them again."
- Never mention technical problems on the box to the client. Fix them, or hand them to the operator, quietly. Tell the owner only what changes for them, in plain words, such as "This will go out a little later than planned." Quiet about the machinery is never permission to say something happened when it did not. If a post, gift or booking did not go out, say so in one plain sentence and say what happens next.
- Only promise what is switched on for this owner (Step 0, the safety boundaries and the "Not built" list below). Leave out any line of the opening that is not true yet.
- Customer-facing wording (the gift message, the reminders, the final message, the booking confirmation) comes from `references/spec/CLIENT-EXPERIENCE.md`. Use those words; do not paraphrase them into technical language.

A friendly way to open with a new owner:

> I'm here to help you bring in new customers with your Purple Billboard. Here's what I'll set up for you:
>
> - A month of daily posts, each with a free gift people can ask for in the comments
> - Friendly replies when people comment on your posts or send you a message
> - Sending your free gift to everyone who asks for it
> - Helping interested people book a call with you
>
> It all happens inside your Convert and Flow account. I'll ask you a few simple questions, one at a time, and nothing goes out until you've said yes to it. Once you've answered, you can sit back and I'll get your month of posts ready for you to look over and approve one time, then take care of the replies, the gift and the call bookings from there.

## Not built, or not proven (say so; do not paper over)

- The Command Center views are built in a separate repository (see the next section). Gaps inside them are named there. Do not claim a view that is not in that table.
- There is no renderer for the joined monthly review; assemble it from the manifest.
- Skill 57 has no Purple Billboard hook; the approval gate is wired in Skill 35's publishing cycle only.
- No poller or ongoing comment monitor exists; the comment reader is per run.
- Unattended personal-profile posting and replies, tagged-link attribution and the bonus membership pass are unproven or blocked.

## Command Center views (separate repository)

The Command Center code is not in this repository. "Not in this repository" says where the code lives, not that it is missing. It is `trevorotts1/blackceo-command-center`, pinned in `cc-compat.json` (`commandCenter.pinnedTag`; `v7.6.126` when this table was checked, so read the current value there). Every file below exists at that tag and on that repository's `main`. Paths are inside that repository.

| Task | What it shows or does | Files (pinned tag `v7.6.126`) | Merged | How an operator or agent reaches it |
|---|---|---|---|---|
| T-31 | Setup readiness: each item READY, BLOCKED or UNKNOWN with its evidence; owner actions that cannot succeed are shown disabled with the reason | `src/components/setup/SetupReadinessPanel.tsx`, `src/app/api/setup/readiness/route.ts` | PR 598 | Open `/setup`. The same data is `GET /api/setup/readiness` (operator identity only). `POST` runs one named owner action (CSRF and same-origin checked) |
| T-32 | Campaign calendar with the approval state per placement, publication receipts, and targeted approve or hold | `src/app/campaigns/[id]/approval/page.tsx`, `src/lib/campaigns/approval-contract.ts` | PR 603 | Open `/campaigns/<campaign id>/approval` with a verified company identity. Targeted approve and hold only; the page has no send path |
| T-33 | Fulfillment pause, retry and handoff, each owner-only, tenant-scoped, expected-version checked, with a receipt | `src/lib/fulfillment/operations.ts` (`pauseFulfillment`, `retryFulfillment`, `handoffFulfillment`) | PR 604, 614 | Library only: no screen, route or button calls these functions on `main` or at the pinned tag. The thread state is read through `src/lib/fulfillment/thread-state.ts`; `GET /api/tasks/<task id>/messages` returns it as `fulfillment` on `main` (PR 614) but not yet at the pinned tag |
| T-34 | Failures, bookings and outcomes for one client | `src/app/workspace/[slug]/exceptions/page.tsx` | PR 602 | Open `/workspace/<slug>/exceptions` (optionally `?client=<slug>`). Failures are real. Bookings and outcomes are shown as UNKNOWN with a reason, because their producers (T-28, T-30) are not on `main`; the page passes `null` for both |
| T-35 | Kanban cards placed from real lifecycle events, with stale and unknown states shown instead of dropped | `src/lib/board/lifecycle-projection.ts` | PR 596 | Open the all-tasks board at `/tasks/all`. Each task from `GET /api/tasks` and `GET /api/tasks/<id>` carries a `lifecycle` object (state, and the reason when stale or unknown) |

Approval caveat for T-32. The Command Center has no source for a placement's account binding, call to action or keyword (nor for the promised item version or the conversation policy version), so `approval-contract.ts` lists them as unproven on every placement. A placement that view shows as approved is approved only for its date, channel and content at the approved fingerprint. Its account binding, call to action and keyword stay UNKNOWN, never approved, and the campaign-level summary is never reported as fully approved (PARTIAL at best). A placement missing its date or its channel is UNKNOWN. Do not tell the owner a placement is approved on the strength of that view alone; the monthly manifest check in Step 5 is the proof for account, call to action and keyword.

Not in the table: the other views `references/spec/CLIENT-EXPERIENCE.md` asks for (conversations and ownership, contact consent and follow-ups). This skill did not verify them. Check the Command Center repository before saying they exist.

## Verify this skill's wiring

`python3 -I 84-purple-billboard-blueprint/tests/test_blueprint_wiring.py` checks that the version in this file matches `skill-version.txt`, that every module and path named in this file and in `references/` exists, and that every function, class and command-line subcommand named next to a module is defined in that module. CI runs it as an explicit step of `.github/workflows/qc-static.yml`. Run it after any change to the modules above.

## Playbook index (`references/playbook/`)

| File | Use it for |
|---|---|
| `01-main-playbook.md` | The method: hook post, comment reveal, Bonus comment, cadence, worked examples, research, monthly hunt, the client journey |
| `02-strategy-guide.md` | The conversation playbook scripts, posting architecture, the Convert and Flow build |
| `03-ai-sop-and-rules-checklist.md` | Six operating procedures, the DM-door link rules, the agreed DM flow, the rules checklist and the never-break rules |
| `04-swipe-pack.md` | Hooks, reveals, Bonus templates and prompts to adapt |
| `05-conversation-ai-build-plan.md` | Design reference for comment-to-DM automations and tests (not an installed capability) |
| `06-dm-door-and-agreed-flow.md` | The Messenger door, the agreed flow, evidence states |
| `07-posting-routes-approvals-and-30-day-plan.md` | Posting routes tried, how approvals really work, the 30-day plan |
| `08-examples.md` | Full worked threads and the conversation that follows |
| `09-realtor-examples.md` | Five complete real-estate billboards with placeholders for the agent's name and market |
