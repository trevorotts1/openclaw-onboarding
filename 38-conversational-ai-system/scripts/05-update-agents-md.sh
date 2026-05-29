#!/usr/bin/env bash
# 05-update-agents-md.sh
#
# Idempotently inserts skill-38 marker blocks into the workspace AGENTS.md:
#   (a) INBOUND_WEBHOOK_CLASSIFICATION   — verbatim Step 7C block from v5.14 playbook lines 1537-1645
#   (b) SKILL38_RUNTIME_ROUTING          — skill-38 runtime routing steps (1.7 / 1.75 / 1.8 / 1.9 / 2.8)
#   (c) AGENTS.md Step 0.5               — Quiet Hours (Step 9.8 → quiet-hours-protocol.md)
#   (d) AGENTS.md Step 0.7               — Compliance Keywords (Step 9.9 → compliance-keyword-detection-protocol.md)
#   (e) AGENTS.md Step 1.85              — Workflow Builder trigger phrases (Step 9.20 → conversation-workflows-protocol.md)
#
# Each block is wrapped in BEGIN/END markers so this script is safe to run
# repeatedly. Existing content is preserved; missing blocks are appended.
# A timestamped backup is made before any write.
#
# OS-aware: Darwin → $HOME/clawd/AGENTS.md
#           Linux  → /data/clawd/AGENTS.md

set -euo pipefail

# -----------------------------------------------------------------------------
# Resolve AGENTS.md location (matches existing skill-38 convention)
# -----------------------------------------------------------------------------
OS_NAME="$(uname -s)"
if [[ "$OS_NAME" == "Darwin" ]]; then
  AGENTS_MD="${AGENTS_MD:-$HOME/clawd/AGENTS.md}"
else
  AGENTS_MD="${AGENTS_MD:-/data/clawd/AGENTS.md}"
fi

if [[ ! -f "$AGENTS_MD" ]]; then
  echo "[05-update-agents-md] AGENTS.md not found at: $AGENTS_MD" >&2
  echo "[05-update-agents-md] Set AGENTS_MD env var or create the file first." >&2
  exit 1
fi

# Backup (timestamped, only if not already backed up in the same second)
BACKUP="${AGENTS_MD}.bak.$(date -u +%Y%m%dT%H%M%SZ)"
cp -p "$AGENTS_MD" "$BACKUP"
echo "[05-update-agents-md] Backup written → $BACKUP"

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
have_marker() {
  # $1 = marker name
  grep -q "<!-- BEGIN SKILL38: $1 -->" "$AGENTS_MD"
}

append_block() {
  # $1 = marker name, stdin = body content
  local name="$1"
  if have_marker "$name"; then
    echo "[05-update-agents-md] block '$name' already present — skipping"
    return 0
  fi
  {
    printf '\n<!-- BEGIN SKILL38: %s -->\n' "$name"
    cat
    printf '\n<!-- END SKILL38: %s -->\n' "$name"
  } >> "$AGENTS_MD"
  echo "[05-update-agents-md] block '$name' appended"
}

# -----------------------------------------------------------------------------
# (a) INBOUND_WEBHOOK_CLASSIFICATION — verbatim Step 7C from v5.14 lines 1537-1645
# -----------------------------------------------------------------------------
append_block "INBOUND_WEBHOOK_CLASSIFICATION" <<'BLOCK_A'

## Inbound Webhook Message Classification (added by OpenClaw GHL Webhook Playbook v5.4)

When you receive an isolated agent turn from `/hooks/ghl-inbound` (or any
`hook:ghl:*` session key), the message body in your prompt is the rendered
output of a server-side template containing the customer's actual message,
their contact ID, and their location ID.

### Step 1 — Classify before replying

Read the customer's message and silently classify it into ONE of these four
categories. Do NOT echo the classification to the customer.

1. **REPLY** — A genuine inbound from a human customer. The message asks a
   question, requests something, expresses an emotion that warrants a
   response, or continues a real conversation. Reply on the matching
   channel using the appropriate communication playbook.

2. **CONFIRM_OUTBOUND** — The webhook is firing because the agent (or a
   teammate) just sent the customer something OUT. The "message" here is
   the agent's own outbound text being looped back. Acknowledge silently
   (no reply needed) and exit. Do NOT reply to your own outbound.

3. **AUTOMATED_NOISE** — System-generated noise: appointment reminder
   confirmations the customer didn't initiate, drip-campaign deliveries,
   bulk-blast acknowledgements, opt-in confirmations, "Your message has
   been received" auto-replies, payment receipts, calendar invitations the
   agent itself just sent, two-factor authentication codes echoing back,
   carrier delivery receipts, read receipts. Exit silently.

4. **NEEDS_HUMAN** — Anything explicitly requesting a human ("speak to a
   person," "is this a bot?", "stop messaging me," abusive language,
   legal threat, refund demand the agent can't fulfill, complex
   complaint, escalation language). Escalate to the operator via the
   configured operator-notify channel and exit without auto-replying to
   the customer.

### Classification heuristics

Use these signals when deciding the category:

- Direction: webhook payload `direction == "inbound"` is the first
  signal, but a real human-typed inbound can sit alongside outbound
  auto-replies in the same conversation thread. Don't trust direction
  alone — read the actual content.
- Customer-typed vs system-generated: short structured tokens (codes,
  one-letter responses to system prompts, "Y"/"N" without context) are
  often noise; conversational prose is usually a real reply.
- Self-echo: if the message content closely matches the agent's most
  recent outbound, treat it as CONFIRM_OUTBOUND.
- Escalation language: any of "speak to a human", "real person", "stop",
  "unsubscribe", "cancel", "lawyer", "report you", "refund me now",
  "this is unacceptable" → NEEDS_HUMAN.
- Channel norms: SMS short codes / opt-out keywords (STOP, HELP, etc.)
  → AUTOMATED_NOISE for STOP/HELP that the carrier handles, NEEDS_HUMAN
  for any other language matching escalation.

### Step 2 — If REPLY: choose the channel-specific communication playbook

The webhook payload tells you which channel the inbound came in on:
SMS, Email, FB Messenger, Instagram DM, GMB chat, GBP chat, WhatsApp,
or a generic "Conversations" inbound. Match the channel to the
corresponding communication playbook in `<MASTER_FILES_DIR>/communication-playbooks/`:

- `<MASTER_FILES_DIR>/communication-playbooks/sms-communication.md`
- `<MASTER_FILES_DIR>/communication-playbooks/email-communication.md`
- `<MASTER_FILES_DIR>/communication-playbooks/facebook-messenger-communication.md`
- `<MASTER_FILES_DIR>/communication-playbooks/instagram-dm-communication.md`
- `<MASTER_FILES_DIR>/communication-playbooks/gmb-chat-communication.md`
- `<MASTER_FILES_DIR>/communication-playbooks/gbp-chat-communication.md`
- `<MASTER_FILES_DIR>/communication-playbooks/whatsapp-communication.md`
- `<MASTER_FILES_DIR>/communication-playbooks/conversations-communication.md`

Read the matching playbook before drafting your reply. It contains the
tone, signature, escalation triggers, and brand voice for that channel.

### Step 3 — Send the reply via the GHL skill

Use the installed GHL skill (`openclaw skills | grep ghl`) to send the
reply back on the same channel. Do NOT post directly to the GHL API
yourself — the skill handles auth, rate limits, and retries.

### Pointers (always-read references)

- AGENTS.md (this file) — your behavioral OS.
- MEMORY.md — long-term memories the agent has learned.
- IDENTITY.md — who you are and how you communicate.
- TOOLS.md — every connected tool, with usage examples.
- USER.md — the operator's profile and preferences.
- SOUL.md — the agent's core mission and values.
- Communication Playbooks — `<MASTER_FILES_DIR>/communication-playbooks/`
- GHL skill — How to actually call the GHL Conversations, Calendars,
  and Payments APIs (installed on every client by default)

BLOCK_A

# -----------------------------------------------------------------------------
# (b) SKILL38_RUNTIME_ROUTING — preserves the existing 53-line script's content
#     (Steps 1.7 / 1.75 / 1.8 / 1.9 / 2.8) inside a single marker block
# -----------------------------------------------------------------------------
append_block "SKILL38_RUNTIME_ROUTING" <<'BLOCK_B'

## Skill-38 Runtime Routing (added by skill-38 installer)

### Step 1.7 — Channel auto-detection

Before drafting any reply, inspect the inbound webhook payload's channel
field (sms / email / facebook / instagram / gmb / gbp / whatsapp /
conversations). Bind it to `$REPLY_CHANNEL` for the rest of the turn.
If the channel cannot be determined, escalate to NEEDS_HUMAN per Step 7C
classification rather than guessing.

### Step 1.75 — Read the per-channel communication playbook

Open the matching playbook in `<MASTER_FILES_DIR>/communication-playbooks/`
(see Step 7C list). Apply its tone, signature, and escalation triggers as
the baseline for every reply on this channel.

### Step 1.8 — Apply the active Conversation Workflow (if any)

If the inbound matches a trigger in `<MASTER_FILES_DIR>/conversation-workflows/registry.md`,
follow that workflow's `<workflow-id>.md` for phase-specific behavior. The
workflow's instructions override the channel playbook for the duration of
that scenario. Always honor the channel playbook's baseline tone/signature.

### Step 1.9 — Log the turn after sending

After the GHL skill confirms delivery, append BOTH the inbound and
outbound to the contact's log file per `conversation-log-protocol.md`.
Never log before sending; never claim delivery without the skill's
confirmation.

### Step 2.8 — Cross-channel formatting

For every outbound, apply the channel-specific formatting rules from
`<MASTER_FILES_DIR>/agent-capabilities-playbook.md` Section 3
(SMS = no markdown / short paragraphs; Email = subject lines + signature;
DMs = short paragraphs, no formal sign-off; Voice channels = plain text
that reads aloud naturally).

BLOCK_B

# -----------------------------------------------------------------------------
# (c) STEP_0_5_QUIET_HOURS
# -----------------------------------------------------------------------------
append_block "STEP_0_5_QUIET_HOURS" <<'BLOCK_C'

## Step 0.5 — Quiet Hours

Before sending any proactive outbound (drip, follow-up, scheduled
notification, operator alert that isn't tagged urgent), consult the
quiet-hours protocol:

  <MASTER_FILES_DIR>/quiet-hours.md
  Skill reference: protocols/quiet-hours-protocol.md

Reactive replies to a customer-initiated message bypass quiet hours.
Proactive sends during a quiet window queue for the next valid send
window. Per-customer override: if a contact has explicitly asked for
24/7 contact, honor that.

BLOCK_C

# -----------------------------------------------------------------------------
# (d) STEP_0_7_COMPLIANCE_KEYWORDS
# -----------------------------------------------------------------------------
append_block "STEP_0_7_COMPLIANCE_KEYWORDS" <<'BLOCK_D'

## Step 0.7 — Compliance Keywords (regulatory hard-gate)

Before any other processing on an inbound, scan the customer's message
against the compliance keyword list:

  <MASTER_FILES_DIR>/compliance-keywords.md
  Skill reference: protocols/compliance-keyword-detection-protocol.md

If any compliance trigger fires (FCC STOP/UNSUB, email unsubscribe,
GDPR data-access/data-deletion request, HIPAA mention of protected
health information, FINRA/SEC investment-advice block), follow the
specified action for that trigger and exit. Compliance overrides every
other rule — including reply, escalation, and channel routing.

BLOCK_D

# -----------------------------------------------------------------------------
# (e) STEP_1_85_WORKFLOW_BUILDER_TRIGGERS
# -----------------------------------------------------------------------------
append_block "STEP_1_85_WORKFLOW_BUILDER_TRIGGERS" <<'BLOCK_E'

## Step 1.85 — Conversation Playbook Builder trigger phrases (the differentiator)

If the operator (NOT a customer) sends the agent a message matching any
of these intent phrases, route the request into the Conversation Playbook
Builder protocol at:

  protocols/conversation-workflows-protocol.md

Trigger phrases (case-insensitive, fuzzy match):

- "Help me create a conversation playbook"
- "Help me build a conversation playbook"
- "Help me build a conversation workflow / flow / funnel"
- "Build me a workflow for <X>"
- "Build me a playbook for <X>"
- "Create a workflow for <X>"
- "Create a playbook for <X>"
- "Set up a conversation flow for <X>"
- "Let's build a funnel for <X>"
- "I want a workflow that does <X>"
- "Walk me through building a workflow"

This is the system's USP: COMMUNICATION-DRIVEN funnels — built by talking
and brainstorming, NOT click-and-drag. When triggered, run the friendly
brainstorm flow (Section I of the protocol):

- DO NOT dump 50 questions. USE what you already know (business, products,
  services, calendars, who they are, habits — from Typed Knowledge Bases +
  USER.md + MEMORY.md) and ask ONLY the smart gaps, like brainstorming.
- Regurgitate a CONCISE summary — "is this what you want to happen?" — and
  wait for YES.
- On YES, build the 3 PARTS: Part 1 (Workflow AI instruction set =
  Build-with-AI prompt + manual-build fallback + verification checklist),
  Part 2 (the conversation playbook → conversation-workflows/<id>.md,
  registered in registry.md), Part 3 (this brainstorm flow). Then write the
  bootstrap pointer (AGENTS.md/TOOLS.md/MEMORY.md as appropriate), create a
  NEW Notion doc in the CLIENT's own workspace, and register it.

GHL note: Automations have NO API/MCP — the only build path is the
"Build with AI" button (top-right of Automations); the agent generates the
prompt, the operator clicks + pastes. The prompt nails the SHAPE; the
operator pastes tokens after — always ship the verification checklist.

THE TRINITY: a GHL workflow/automation, a communications playbook, and a
workflow-AI prompt travel together — building one implies the other two.
See protocols/conversation-workflows-protocol.md (Section "THE TRINITY").

Standards (full content in reference docs — do NOT inline here):
- Communications playbook format + must-appear checklist + storage + the
  Notion→Google Docs→plain-text fallback order:
  references/communications-playbook-standard.md
- Workflow-AI prompt must-appear checklist + WHERE (Build-with-AI button in
  Automations) + field-by-field Custom Webhook (EVENT/METHOD/URL/AUTH=None/
  HEADERS via Add item/Content-Type/23-key flat RAW BODY via Custom Values) +
  multi-action (if/else, Add-Tag, tag-check) + verification checklist:
  references/workflow-ai-instructions-standard.md

Cross-refs: Step 9.33 (Intelligent Playbook Routing — cross-playbook
transitions, max 3 switches) and Step 9.34 (Proactive Features Suite —
pattern-based "want a playbook?" engine). See protocol Section K.

Confirm all 3 PARTS completed before declaring the playbook live.

BLOCK_E

echo "[05-update-agents-md] AGENTS.md update complete: $AGENTS_MD"
