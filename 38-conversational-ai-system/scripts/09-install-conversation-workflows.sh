#!/usr/bin/env bash
# 09-install-conversation-workflows.sh
#
# Step 9 — "Set up conversation log system" + the conversation-workflows registry.
#
# Creates the conversation-workflows registry AND the conversational-logs dir
# under MASTER_FILES_DIR.
#
# What this does:
#   1. Reads MASTER_FILES_DIR from ~/.openclaw/.skill-38-master-files-dir
#      (this pointer file is written by 01-locate-master-files-folder.sh).
#   2. Creates `$MASTER_FILES_DIR/conversational-logs/` if missing AND ensures it
#      is OWNED BY THE RUNTIME USER (the gateway user — `node` on VPS/docker; the
#      login user on a Mac/Homebrew install) so the agent can WRITE to it. This is
#      mandatory: the per-contact conversation log is the ONLY memory a single-turn
#      GHL hook session has. On a live client the dir was created root-owned and the
#      agent could not append until it was chowned to `node` — the agent silently
#      "lost memory" mid-conversation. Read-before/append-after is dead without a
#      writable dir.
#   3. Creates `$MASTER_FILES_DIR/conversation-workflows/` if missing.
#   4. Writes `$MASTER_FILES_DIR/conversation-workflows/registry.md` with the
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
LOGS_DIR="$MASTER_FILES_DIR/conversational-logs"

# -----------------------------------------------------------------------------
# Conversation-log system (Step 9): create the per-contact conversational-logs
# dir and make it WRITABLE BY THE RUNTIME (gateway) USER.
#
# GHL inbound hook sessions are single-turn / stateless. The agent's only memory
# of a contact across messages is the per-contact log file in this dir, which it
# must READ before replying and APPEND to after sending. If this dir does not
# exist, or exists but is owned by root while the gateway runs as `node`, the
# agent silently cannot persist memory — exactly the live-client regression this
# step prevents. So: mkdir -p, then chown to the runtime user.
# -----------------------------------------------------------------------------
mkdir -p "$LOGS_DIR"

# Determine the gateway runtime user and chown the logs dir to it so the agent
# can write. On VPS/Docker the gateway runs as `node`; on a Mac/Homebrew install
# it runs as the login user (no chown needed there). Best-effort: never fail the
# install if chown is not permitted — but always report what was (or wasn't) done.
RUNTIME_USER="${OPENCLAW_RUNTIME_USER:-}"
if [[ -z "$RUNTIME_USER" ]]; then
  OS_NAME="$(uname -s 2>/dev/null || echo unknown)"
  if [[ "$OS_NAME" == "Linux" ]]; then
    # VPS/Docker default gateway user.
    RUNTIME_USER="node"
  else
    # Mac/Homebrew: the gateway runs as the current login user already.
    RUNTIME_USER="$(id -un 2>/dev/null || echo "$USER")"
  fi
fi

CURRENT_OWNER="$(stat -f '%Su' "$LOGS_DIR" 2>/dev/null || stat -c '%U' "$LOGS_DIR" 2>/dev/null || echo "")"
if [[ -n "$RUNTIME_USER" && "$CURRENT_OWNER" != "$RUNTIME_USER" ]]; then
  if chown -R "$RUNTIME_USER" "$LOGS_DIR" 2>/dev/null; then
    echo "[09-install-conversation-workflows] conversational-logs dir chowned to runtime user '$RUNTIME_USER' → $LOGS_DIR"
  elif command -v sudo >/dev/null 2>&1 && sudo -n chown -R "$RUNTIME_USER" "$LOGS_DIR" 2>/dev/null; then
    echo "[09-install-conversation-workflows] conversational-logs dir chowned (sudo) to runtime user '$RUNTIME_USER' → $LOGS_DIR"
  else
    echo "[09-install-conversation-workflows] WARNING: could not chown $LOGS_DIR to '$RUNTIME_USER' (current owner: '${CURRENT_OWNER:-unknown}')." >&2
    echo "[09-install-conversation-workflows] The gateway user MUST own this dir or the agent cannot append conversation logs (= silent memory loss)." >&2
    echo "[09-install-conversation-workflows] Run manually:  sudo chown -R $RUNTIME_USER \"$LOGS_DIR\"" >&2
  fi
else
  echo "[09-install-conversation-workflows] conversational-logs dir ready (owner '$CURRENT_OWNER') → $LOGS_DIR"
fi

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
- `<workflow-id>--build-with-ai-prompt.md` — the Build-with-AI prompt
  (pasted into GHL Automations -> "Build with AI") used to build the GHL side
  (legacy name `<workflow-id>--workflow-ai-prompt.md` still accepted by QC)
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

Append one ROW per installed workflow to the table below. This is the canonical
registry shape (matches `protocols/conversation-workflows-protocol.md` §F and the
`qc-trinity-registry.sh` validator). The `Layer 1?` column tells the validator
whether a Build-with-AI prompt is legitimately absent ("No (uses existing
inbound)") or required ("Yes").

| ID | Name | Trigger summary | Layer 1? | OpenClaw playbook | GHL prompt | Verification checklist |
|---|---|---|---|---|---|---|

<!-- workflows: none yet -->

<!--
  Legacy bullet form (- <workflow-id>: <one-line description>) is still
  understood by qc-trinity-registry.sh for older installed registries, but new
  registrations should use the table row above so the Layer-1 disposition is
  recorded.
-->
REG_EOF

echo "[09-install-conversation-workflows] registry created → $REGISTRY"
