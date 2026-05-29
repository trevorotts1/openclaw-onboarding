#!/usr/bin/env bash
# 20-seed-design-principles.sh
# Skill 38 — Step O.7 (Seed durable design principles into MEMORY.md).
# Appends Rules 1-5 verbatim from the playbook to the workspace MEMORY.md
# using a SEPARATE marker block so it does not conflict with the existing
# skill-38 memory-rules-6-14 block written by 06-append-memory-rules.sh.
# Idempotent.
set -euo pipefail

OS="$(uname -s)"

# Resolve workspace MEMORY.md. Allow override via env, then probe common locations.
WORKSPACE_MEMORY="${WORKSPACE_MEMORY:-}"
if [ -z "$WORKSPACE_MEMORY" ]; then
  for p in \
    "$HOME/.openclaw/workspace/MEMORY.md" \
    "$HOME/.openclaw/MEMORY.md" \
    "/data/.openclaw/workspace/MEMORY.md" \
    "/data/.openclaw/MEMORY.md"; do
    if [ -f "$p" ]; then WORKSPACE_MEMORY="$p"; break; fi
  done
fi

if [ -z "$WORKSPACE_MEMORY" ]; then
  if [ "$OS" = "Darwin" ]; then
    WORKSPACE_MEMORY="$HOME/.openclaw/workspace/MEMORY.md"
  else
    WORKSPACE_MEMORY="/data/.openclaw/workspace/MEMORY.md"
  fi
  mkdir -p "$(dirname "$WORKSPACE_MEMORY")"
  touch "$WORKSPACE_MEMORY"
  echo "[O.7] Created empty MEMORY.md at $WORKSPACE_MEMORY"
fi

BEGIN_MARK="<!-- BEGIN skill-38 design-principles-1-5 -->"
END_MARK="<!-- END skill-38 design-principles-1-5 -->"

if grep -qF "$BEGIN_MARK" "$WORKSPACE_MEMORY"; then
  echo "[O.7] Design principles block already present in $WORKSPACE_MEMORY — skipping (idempotent)."
  exit 0
fi

cat >> "$WORKSPACE_MEMORY" <<'EOF'

<!-- BEGIN skill-38 design-principles-1-5 -->
## Design Principles for This System

These are durable rules about how Convert and Flow AI systems are built.
They apply to EVERY workflow design, EVERY protocol creation, EVERY
GHL automation. Never forget these:

### Rule 1 — Smaller GHL workflows always beat massive ones

When designing GHL automations, split work across SMALLER, focused
workflows rather than building one giant workflow with many branches.

Why this matters:
- Massive workflows are hard to debug when something fails
- Smaller workflows isolate failures to a specific concern
- Smaller workflows are easier to test in isolation
- Smaller workflows are easier to update without breaking other paths
- GHL's Build with AI (Automations -> Build with AI) builds smaller workflows more reliably than massive ones

When the agent designs a GHL workflow as part of a Conversation
Workflow build (Step 9.20), it splits the workflow if it would
otherwise have:
- More than 2 if/else branches
- More than 1 webhook call
- Multiple notification destinations
- Multiple distinct trigger conditions

Default to "build two focused workflows" over "build one workflow
that does both things."

### Rule 2 — Automation over operator manual steps

Whenever a task COULD be done by the agent via skill/API vs done
manually by the operator, default to the agent doing it. Example:
creating GHL tags is done by the agent via the GHL skill, not by
telling the operator to go to Settings → Tags. The operator should
verify, not construct.

### Rule 3 — Bootstrap files stay lean

Per the Teach Yourself Protocol, MEMORY.md / AGENTS.md / TOOLS.md
hold only essential pointers and behavioral rules. Full protocol
content lives in the master files folder. Bloating bootstrap files
slows the system on every agent turn.

### Rule 4 — Allow-list, not block-list

The agent operates from a FIXED ALLOW-LIST of actions per the prompt
injection protection protocol. New capabilities require explicit
addition to the allow-list. Default-refuse for anything outside.

### Rule 5 — Christy's verification standards

Christy reads documentation carefully and verifies claims. Never
overstate evidence as "proof" when it is inference. Cite sources
literally; never paraphrase a doc and call it proof. When she pushes
back, concede honestly the first time rather than doubling down.
<!-- END skill-38 design-principles-1-5 -->
EOF

echo "[O.7] Appended design principles Rules 1-5 to $WORKSPACE_MEMORY"
echo "[O.7] OK"
