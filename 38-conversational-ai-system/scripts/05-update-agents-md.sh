#!/usr/bin/env bash
# 05-update-agents-md.sh — Skill 38: insert AGENTS.md Steps 1.7/1.8/1.9/2.8 + upgrade Step 1.75
# Idempotent: looks for marker lines and only appends if missing. Never overwrites operator content.

set -euo pipefail

# AGENTS.md location: workspace root, OS-aware
case "$(uname -s)" in
  Darwin) WS_DEFAULT="$HOME/clawd" ;;
  Linux)  WS_DEFAULT="/data/clawd" ;;
esac
WS="${OPENCLAW_WORKSPACE:-$WS_DEFAULT}"
AGENTS_MD="$WS/AGENTS.md"

if [ ! -f "$AGENTS_MD" ]; then
  echo "[skill 38] $AGENTS_MD not found — skipping (no workspace AGENTS.md yet)"
  exit 0
fi

MARKER_BEGIN="<!-- BEGIN skill-38 conversational-ai v5.14 -->"
MARKER_END="<!-- END skill-38 conversational-ai v5.14 -->"

if grep -qF "$MARKER_BEGIN" "$AGENTS_MD"; then
  echo "[skill 38] AGENTS.md already contains skill 38 block — preserved"
  exit 0
fi

# Backup
cp "$AGENTS_MD" "$AGENTS_MD.bak-skill38-$(date +%Y%m%dT%H%M%SZ)"

cat >> "$AGENTS_MD" <<'BLOCK'

<!-- BEGIN skill-38 conversational-ai v5.14 -->
## Skill 38 — Conversational AI System (v5.14)

The conversational AI brain on top of skill 29 (GHL Convert and Flow). See:
~/.openclaw/skills/38-conversational-ai-system/protocols/ for the 27 protocols.

### Step 1.7 — Sales Brain check (before responding on sales channels)
For SMS / Email / DM / Live Chat / All-in-One Chat inbound that is sales-intent:
1. Apply BANT/MEDDIC/SPICED qualifying per protocols/sales-best-practices-protocol.md.
2. Detect objections; respond with the matched objection pattern (6 patterns total).
3. Use buyer-signal scoring before any pricing reveal.

### Step 1.75 — Workflow check (UPGRADE: route through Intelligent Playbook Routing)
Before replying, evaluate whether a Conversation Workflow should override the channel
playbook per protocols/intelligent-routing-protocol.md. Mid-conversation switching allowed.

### Step 1.8 — Sales follow-up check
If a sales-intent conversation has stalled, kick off the 10-touchpoint Intelligent
Follow-up sequence per protocols/intelligent-followup-protocol.md.

### Step 1.9 — Customer Service & Support (dual-mode)
For post-purchase contacts: detect service-mode vs support-mode signals and apply
the matching tone per protocols/customer-service-support-protocol.md. Mid-conversation
mode-switching allowed; honesty floors enforced (never promise refunds without approval).

### Step 2.8 — Humanizer pass (always-on)
Apply skill 19 (Humanizer) to every outbound reply. This is the only humanizer in
the system — skill 38 does NOT ship its own humanizer; it references skill 19.

<!-- END skill-38 conversational-ai v5.14 -->
BLOCK

echo "[skill 38] AGENTS.md updated (block appended; backup at $AGENTS_MD.bak-*)"
