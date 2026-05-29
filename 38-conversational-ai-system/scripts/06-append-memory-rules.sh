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
BUILDER_MARKER="<!-- BEGIN skill-38 builder-design-rules v1.4.1 -->"

if grep -qF "$MARKER_BEGIN" "$MEM_MD" && grep -qF "$BUILDER_MARKER" "$MEM_MD"; then
  echo "[skill 38] MEMORY.md already contains skill 38 rules (incl. builder rules) — preserved"
  exit 0
fi
cp "$MEM_MD" "$MEM_MD.bak-skill38-$(date +%Y%m%dT%H%M%SZ)"

# Block 1 — core v5.14 design rules 6-14 (only if not already present)
if ! grep -qF "$MARKER_BEGIN" "$MEM_MD"; then
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
fi

# Block 2 — Conversation Playbook Builder design rules (v1.4.1 enhancement)
if ! grep -qF "$BUILDER_MARKER" "$MEM_MD"; then
cat >> "$MEM_MD" <<'BLOCK'

<!-- BEGIN skill-38 builder-design-rules v1.4.1 -->
## Skill 38 — Conversation Playbook Builder: design rules (v1.4.1)

These rules make the recurring "build me a conversation playbook" flow bulletproof.
The system's USP is COMMUNICATION-DRIVEN funnels / automations — built by talking and
brainstorming, NOT click-and-drag (this is what beats CloseBot).

15. Terminology Rule — "workflow" / "automation" / "Workflow AI" all mean a
    **GHL Automations-section workflow** unless the operator says otherwise. When the
    operator says "build me a workflow / playbook / funnel," it is a Conversation
    Playbook Builder request (Step 9.20).
16. No-GHL-API Rule — GHL / Convert and Flow Automations have **NO API and NO MCP**.
    The ONLY way to build one is the **"Build with AI" button** (top-right of the
    Automations section): the agent generates the prompt, the operator clicks the button
    and pastes it. (Future: Playwright / browser-control auto-paste; today it is manual.)
    NEVER write or claim code that "calls the GHL Automations API" — it does not exist.
17. 3-PART Build Rule — every conversation-playbook build produces all THREE parts:
    Part 1 = Workflow AI instruction set (Build-with-AI prompt + manual-build fallback +
    verification checklist); Part 2 = the conversation playbook itself (Layer 2 markdown,
    saved + registered in conversation-workflows/registry.md); Part 3 = the brainstorm
    trigger. The Build-with-AI prompt's job is to get the SHAPE right (trigger, branches,
    tags, webhook); it often won't set tokens correctly, so the operator pastes those
    after — always ship the verification checklist.
18. Brainstorm-Not-50-Questions Rule — when the operator asks to build a playbook, run a
    FRIENDLY proactive Q&A. USE what is already known (business, products, services,
    calendars, who they are, habits — from Typed Knowledge Bases + USER.md + MEMORY.md)
    and ask ONLY the smart gaps, like brainstorming with a colleague who already knows the
    business. NEVER dump a wall of questions. Then regurgitate a CONCISE summary —
    "is this what you want to happen?" — as the final confirmation before building. On YES:
    build Part 1 → build Part 2 → write the pointer into AGENTS.md / TOOLS.md / MEMORY.md →
    create a NEW Notion doc (client's OWN workspace) → register it.
19. Mac Env Rule — on a Mac install, secrets (HOOKS_TOKEN, GHL PIT, etc.) live in
    **~/clawd/secrets/.env** AND/OR **~/.openclaw/.env** — check BOTH before ever claiming
    a key is missing. (VPS keeps env in /docker/<project>/.env; Mac does not.)

<!-- END skill-38 builder-design-rules v1.4.1 -->
BLOCK
fi

echo "[skill 38] MEMORY.md updated (rules 6-14 + builder design rules 15-19 appended; backup at $MEM_MD.bak-*)"
