# Launch Customer Replied → Conversation AI (SMS + Chat)

- **id:** `customer-replied-conversation-ai`
- **Category:** launch-ai
- **Optional:** yes — only when the launch intake answers "Conversation AI: yes"
- **Aliases:** Customer Replied workflow · Conversation AI reply workflow · Launch reply bot · AI answers replies · Conversation AI TRINITY workflow · Keyword wake-up bot
- **Source:** `launch-automations.spec.md` §3.4. Supporting: GoHighLevel help on the Customer Replied trigger, the Conversation AI action and Update Conversation AI Bot and Status; Skill 38 `protocols/conversation-workflows-protocol.md`; `automation-templates/launch-ghl-probe/GHL-CAPABILITY-NOTE.md`.

> "If requested: a **Customer Replied** workflow (SMS + chat channels) → **Conversation AI** action (Q&A from offer facts, booking, or checkout link) → branches booked / answered / timed out → keyword wake-up via **Update Conversation AI Bot and Status**. Skill 44 builds the workflow, Skill 38 writes the playbook. If not requested: package records 'Conversation AI: not requested'." — launch-automations.spec.md §3.4

## What it is
Someone replies to a launch text or writes in web chat. The Conversation AI bot takes the thread, answers from the approved offer facts, books the call when asked, or sends the checkout link when the contact is ready. The exchange resolves into one of three outcomes — **booked**, **answered**, **timed out** — and each outcome gets its own follow-up. A keyword wakes the bot again after it goes quiet.

Skill 44 builds the workflow. Skill 38 writes the playbook. The two are one unit (TRINITY): no workflow without the playbook, no playbook without the workflow.

## Not requested
Do nothing — build nothing. The launch package records the literal line `Conversation AI: not requested`. Do **not** pass `--conversational` to `qc-built-workflow.sh`; that flag hard-gates WF-19 against a Skill 38 registry that has no row for a launch that never asked for a bot (false failure).

## TRIGGER
- **What starts it:** an inbound reply from the contact on a watched channel during the launch window.
- **Channels:** SMS and Chat (web chat / live chat). Email replies are out of scope.
- **GHL filters available:** reply channel · phrase · tag · intent. Default template uses channel only; narrow with a launch tag only when the owner asks.
- **Re-entry:** once per contact per launch, guarded by tag `launch-ai-replied`.
- **Engine note:** CampaignBuilder auto-creates only a Tag Added trigger. Customer Replied goes on with `caf --experimental workflows patch-trigger --workflow-id <id> --trigger-json <file>` (snapshot captured automatically) or through the Tier-4 managed browser. The internal trigger `type` string is **not verified** in engine source — read a live definition first, never invent it.

## CHANNELS
SMS · Chat (web chat / live chat). Email is not part of this workflow.

## THE THREE BRANCHES

### BOOKED
**Signal:** Conversation AI outcome = appointment booked.
| Action | Detail |
|---|---|
| Tag | `launch-ai-booked` |
| Message | Approved confirmation: date, time, timezone |
| Opportunity | Booked stage, when the launch pipeline exists |
| Notify | Internal notification to the owner |
| Exit | Hand to the call-reminder / show-up workflow. No more selling in this thread. |

### ANSWERED
**Signal:** the bot answered the question; no booking, no purchase.
| Action | Detail |
|---|---|
| Tag | `launch-ai-answered` |
| Sequence | Contact stays in the promotional launch sequence — the reply does not remove them |
| Exit | Workflow keeps listening; a later booking moves the contact to BOOKED on the same thread |

### TIMED OUT
**Signal:** contact went quiet before the exchange finished.
| Action | Detail |
|---|---|
| Tag | `launch-ai-timed-out` |
| Wait | 1 day (duration Wait — never an event Wait) |
| Nudge | ONE approved message with `{{booking_link}}` and/or `{{checkout_link}}` |
| Wait | 1 day |
| Close | Tag `launch-ai-dormant`, stop. The keyword is the only way back. |

One nudge, never a drip. The nudge counts toward the launch's 3–5 promotional text cap.

## KEYWORD WAKE-UP
- **Action:** Update Conversation AI Bot and Status.
- **Default keyword:** `CALL` — owner-configurable.
- **Behavior:** the keyword re-activates the bot on that conversation and sets status active, so the playbook answers again. This is the only re-entry path for a `launch-ai-dormant` contact.
- **Cap:** once per contact per day.
- **Opt-out wins:** STOP / UNSUBSCRIBE and any owner-defined opt-out always beat the keyword.

## OFFER FACTS — what the bot may answer from
Offer name, price, inclusions, who it is for · doors open / doors close / access date · booking link · checkout link · payment plans (only when the offer has them) · refund and guarantee wording exactly as approved · A2P status.

Never invented: discounts, bonuses, dates, guarantees, or outcomes the offer does not state. Skill 38 owns the wording; Skill 44 only wires the node.

## BUILD (Skill 44)
1. **Dependencies first** — Conversation AI agent (`POST /conversation-ai/agents`, `POST /conversation-ai/agents/{agentId}/actions`, Version `2021-04-15`, scope `conversation-ai.write`), booking calendar, the six tags, the custom values.
2. **Workflow** — `caf --experimental workflows create --name '<Launch> Customer Replied AI' --folder '<Launch>' --from-json <campaign.json>`.
   `create-step` supports only email / sms / wait / tag / webhook / ai, so the Conversation AI node and the keyword node are written as raw step objects.
3. **Trigger** — `patch-trigger` from the observed live shape.
4. **Read back** — `caf workflows export <id>` and confirm every branch, the agent id and the keyword node.

### Engine truth (do not paper over)
- `conversation_ai` **is** in `VERIFIED_ACTIONS` — the action type is verified — but there is **no builder helper**, so it ships as a raw step object.
- `Update Conversation AI Bot and Status` is **not** in `VERIFIED_ACTIONS`. Build it with the Tier-4 managed browser, or reuse an observed payload from the same location. If neither is possible, report that specific unfinished node — the workflow is not complete.
- CampaignBuilder writes **drafts** only; `CAF_DRAFT_ONLY` keeps triggers inactive. Nothing goes live from this lane.
- Pre-write snapshots are mandatory before `update` / `patch-email` / `patch-trigger`.

## RUNTIME OWNER, ENROLLMENT AND COMPLETION PROOF
Exactly one reply owner answers this thread.

- **`openclaw_inbound` (default, full Skill 38 route).** The existing OpenClaw inbound path owns replies; Skill 38's channel playbooks and the launch playbooks govern content. The GHL Conversation AI node is not a second responder.
- **`native_ghl` (narrower mode).** Allowed only with an operator-approved prompt/knowledge translation: `translation_approved: true` plus a named playbook and offer-knowledge version. No approval, no equivalent proof.

Both routes require:

| Requirement | Rule |
|---|---|
| Enrollment | launch, location and contact all enrolled, with matching launch and location ids |
| State | namespaced `launch-ai/<tenant>/<location>/<launch>/` — never shared across launches |
| Channel consent | `granted: true` per planned channel (`sms`, `chat`), with source and captured-at; no consent for a channel not in the plan |
| Human fallback | bounded (`max_turns` 1–10, `timeout_minutes` 1–1440), named owner, triggers, closure path |
| Offer knowledge | versioned per offer, `update_rule: operator_published_only`, `unknown_policy: escalate`, `invention_guard: true` |
| Evidence | saved graph readback **and** registered bot receipt for the exact tenant, location, workflow, launch revision and playbook |

A registry hygiene pass (row exists, files exist) never satisfies requested-bot completion. Contract and offline gate: `38-conversational-ai-system/launch/conversation-runtime-contract.md`, `qc-launch-conversation-ai.sh`.

Staging buyer-journey and channel tests run only under a separately authorized account. Without one, record `result: "blocked"` with the precise reason; never bypass.

## QUALITY GATE
```bash
caf workflows get <workflow-id> --json
qc-built-workflow.sh <workflow-id> --conversational [--fab]
```
- WF-1..21 must pass.
- **WF-19 is a hard gate:** `--conversational` runs Skill 38's `qc-trinity-registry.sh`. Skill 38's registry must hold the playbook row **and** the Build-with-AI prompt. A playbook with no prompt (or an orphan prompt) fails WF-19.
- `--fab` adds the FAB-QC overlay, gate ≥ 8.5.
- Read-back must show: all three branches, the correct agent id, the keyword node, and the re-entry tag.
- Run `bash 38-conversational-ai-system/launch/qc-launch-conversation-ai.sh --bundle <evidence.json>` for the exact target. Global registry evidence alone fails by design.

## FLEXIBILITY
Overridable at every level: channels, keyword, nudge timing and copy, whether a timed-out contact is nudged at all, and whether the bot books, sends checkout, or only answers.

Non-negotiable: never build when the intake said no; never ship the workflow without the Skill 38 playbook; never answer from unapproved facts.
