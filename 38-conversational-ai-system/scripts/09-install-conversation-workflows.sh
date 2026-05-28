#!/usr/bin/env bash
# 09-install-conversation-workflows.sh
#
# Creates the conversation-workflows registry under MASTER_FILES_DIR.
#
# What this does:
#   1. Reads MASTER_FILES_DIR from ~/.openclaw/.skill-38-master-files-dir
#      (this pointer file is written by 01-locate-master-files-folder.sh).
#   2. Creates `$MASTER_FILES_DIR/conversation-workflows/` if missing.
#   3. Writes `$MASTER_FILES_DIR/conversation-workflows/registry.md` with the
#      3-Layer architecture summary, file-naming conventions, and trigger
#      phrases — ONLY IF the registry does not already exist (idempotent).
#
# OS-aware (Darwin / Linux) but the source-of-truth for the path is the
# pointer file written by step 01.

set -euo pipefail

# -----------------------------------------------------------------------------
# Resolve MASTER_FILES_DIR
# -----------------------------------------------------------------------------
POINTER_FILE="${HOME}/.openclaw/.skill-38-master-files-dir"
if [[ ! -f "$POINTER_FILE" ]]; then
  echo "[09-install-conversation-workflows] pointer file missing: $POINTER_FILE" >&2
  echo "[09-install-conversation-workflows] run 01-locate-master-files-folder.sh first." >&2
  exit 1
fi

MASTER_FILES_DIR="$(cat "$POINTER_FILE")"
MASTER_FILES_DIR="${MASTER_FILES_DIR%$'\n'}"

if [[ -z "$MASTER_FILES_DIR" || ! -d "$MASTER_FILES_DIR" ]]; then
  echo "[09-install-conversation-workflows] MASTER_FILES_DIR is empty or not a directory: '$MASTER_FILES_DIR'" >&2
  exit 1
fi

WORKFLOWS_DIR="$MASTER_FILES_DIR/conversation-workflows"
REGISTRY="$WORKFLOWS_DIR/registry.md"

mkdir -p "$WORKFLOWS_DIR"

if [[ -f "$REGISTRY" ]]; then
  echo "[09-install-conversation-workflows] registry already present — leaving as-is: $REGISTRY"
  exit 0
fi

# -----------------------------------------------------------------------------
# Write registry.md
# -----------------------------------------------------------------------------
cat > "$REGISTRY" <<'REG_EOF'
# Conversation Workflows — Registry

This folder holds every Conversation Workflow installed for this client.
The agent reads `registry.md` on every inbound to see which workflow (if
any) should fire for the customer's current intent.

## What is a Conversation Workflow?

A scenario-specific behavior override. Other conversational AI platforms
make operators build workflows in visual node-based UIs (n8n, Zapier, GHL
Workflow Builder). This system has operators TALK through workflows: the
agent asks intelligent questions, synthesizes a Conversation Playbook,
AND auto-builds the GHL routing layer the customer needs to reach the AI
in the first place.

Conversation Workflows are complementary to Communication Playbooks:

- **Communication Playbook** = baseline tone/voice for a channel. One per
  channel. Applies to every reply on that channel.
- **Conversation Workflow** = specific scenario behavior override. Many
  per client. Applies only when its trigger fires (pricing inquiry,
  booking request, FAQ, etc.).

When a workflow fires, its scenario instructions override the channel
playbook's body content, but the channel playbook's tone/signature is
still honored.

## 3-Layer Architecture summary

- **Layer 0 — Routing check.** Did this inbound match an existing
  workflow's trigger? If yes, fire that workflow. If no, fall through to
  the standard channel playbook.
- **Layer 1 — GHL side.** The GHL workflow + tag automations that route
  the inbound message into the agent in the first place. Auto-built
  during workflow setup; mirrored in `<workflow-id>--ghl-side.md`.
- **Layer 2 — OpenClaw playbook.** The agent-side scenario behavior:
  Phase 1 (acknowledge), Phase 2 (gather), Phase 3 (act), Phase 4
  (handoff). Stored in `<workflow-id>.md`.

Full builder protocol (Layers 0/1/2 walkthrough): see the skill's
`protocols/conversation-workflows-protocol.md`.

## File-naming conventions

For every workflow with id `<workflow-id>` (kebab-case, alphanumeric +
hyphens only):

- `<workflow-id>.md` — Layer 2 OpenClaw playbook (Phase 1-4 + edge cases)
- `<workflow-id>--ghl-side.md` — Layer 1 GHL routing mirror (tags,
  triggers, workflow IDs)
- `<workflow-id>--workflow-ai-prompt.md` — the Workflow AI prompt used
  to build the GHL side
- `<workflow-id>--verification-checklist.md` — operator-runnable
  verification checklist confirming the workflow is live end-to-end

## How to invoke the builder

The operator can trigger the Workflow Builder by sending the agent any
of these intent phrases (case-insensitive, fuzzy match — Step 9.20
Section A):

- "Help me build a conversation playbook"
- "Help me build a conversation workflow"
- "Build me a workflow for <X>"
- "Build me a playbook for <X>"
- "Create a workflow for <X>"
- "Create a playbook for <X>"
- "Set up a conversation flow for <X>"
- "I want a workflow that does <X>"
- "Walk me through building a workflow"

The agent then hands control to the Workflow Builder subagent walkthrough
(`protocols/conversation-workflows-protocol.md` Section B) and runs the
operator through the 3-Layer setup end-to-end.

## Active workflows

(Append one bullet per installed workflow — `<workflow-id>: <one-line description>`.)

<!-- workflows: none yet -->
REG_EOF

echo "[09-install-conversation-workflows] registry created → $REGISTRY"
