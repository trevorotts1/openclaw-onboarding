#!/usr/bin/env bash
# 06-append-memory-rules.sh — Skill 38: append MEMORY.md design rules 6-14 (v5.14)
# Idempotent. Backs up before any edit. Never overwrites operator content.

set -euo pipefail
case "$(uname -s)" in
  Darwin) WS_DEFAULT="$HOME/clawd" ;;
  Linux)  WS_DEFAULT="/data/clawd" ;;
esac
WS="${OPENCLAW_WORKSPACE:-$WS_DEFAULT}"
MEM_MD="$WS/MEMORY.md"
[ -f "$MEM_MD" ] || { echo "[skill 38] $MEM_MD not found — skipping"; exit 0; }

MARKER_BEGIN="<!-- BEGIN skill-38 memory-rules v5.14 -->"
if grep -qF "$MARKER_BEGIN" "$MEM_MD"; then
  echo "[skill 38] MEMORY.md already contains skill 38 rules — preserved"
  exit 0
fi
cp "$MEM_MD" "$MEM_MD.bak-skill38-$(date +%Y%m%dT%H%M%SZ)"

cat >> "$MEM_MD" <<'BLOCK'

<!-- BEGIN skill-38 memory-rules v5.14 -->
## Skill 38 — Conversational AI System: MEMORY.md design rules 6-14

(Rules 1-5 are skill 19 / skill 29 territory; these 9 are skill 38's per the v5.14 playbook.)

6.  Conversation Log Rule — log every inbound + outbound, real-time, never lose a turn.
7.  Quiet Hours Rule — never proactively message outside operator-defined quiet hours;
    reactive replies still go.
8.  PII Rule — scrub email/phone/SSN/credit-card patterns before any model call; replace
    with stable tokens, never log raw PII.
9.  Confidence Rule — if model confidence below threshold, escalate to operator; never
    bluff a confident answer.
10. Sales Brain Rule — apply BANT/MEDDIC/SPICED + the 6 objection patterns + buyer-signal
    scoring before any pricing reveal.
11. Customer Service vs Support Rule — detect mode by signal keywords; mid-conversation
    mode-switching allowed; honesty floors enforced.
12. Discount Code Rule — generate discount codes only per per-product policy; never
    invent a code without operator-approved rules.
13. Intelligent Routing Rule — Conversation Workflows override channel playbooks when
    context routing says they should.
14. Tune-up Rule — Sunday 2am weekly + Saturday 11pm proactive + 1st-of-month review
    cron jobs are the heartbeat. Never disable without operator approval.

<!-- END skill-38 memory-rules v5.14 -->
BLOCK

echo "[skill 38] MEMORY.md updated (rules 6-14 appended; backup at $MEM_MD.bak-*)"
