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
R3A_MARKER="<!-- BEGIN skill-38 round3-queueA-rules v1.5.0 -->"

if grep -qF "$MARKER_BEGIN" "$MEM_MD" && grep -qF "$BUILDER_MARKER" "$MEM_MD" && grep -qF "$R3A_MARKER" "$MEM_MD"; then
  echo "[skill 38] MEMORY.md already contains skill 38 rules (incl. builder + round-3 queue-A rules) — preserved"
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

# Block 3 — Round-3 Queue-A CORE feature rules 20-25 (v1.5.0 feature wave)
if ! grep -qF "$R3A_MARKER" "$MEM_MD"; then
cat >> "$MEM_MD" <<'BLOCK'

<!-- BEGIN skill-38 round3-queueA-rules v1.5.0 -->
## Skill 38 — Round-3 Queue-A CORE: design rules 20-25 (v1.5.0)

20. ZHC Tag-Prefix Rule — every tag the agent creates PROGRAMMATICALLY (via the GHL
    skill's create_tag, or the fallback POST /locations/{id}/tags) carries the `ZHC-`
    prefix, so agent-created tags are instantly distinguishable from operator-created ones.
    This is NOT retroactive: never rename existing or operator-owned tags; only prefix the
    names the agent creates going forward. Companion: programmatically created CRM custom
    FIELDS use the `ZHC_` prefix (Rule 24). The bot tag is `ZHC-bot-suspected` going
    forward; existing `bot-detected` tags are honored as-is. Reuse the existing D.1 /
    Section-6 tag-creation mechanism — only the NAME changes. See
    `<MASTER_FILES_DIR>/zhc-tag-prefix-protocol.md`.
21. Aggression Rule (F50) — screen every inbound for hostility BEFORE routing and BEFORE
    the model (Step 1.35). Tier 1 TENSION (multiple irritation words / 3+ message streak /
    !!!|???) → tag `ZHC-tension-detected`, heighten care, NO reroute. Tier 2 AGGRESSION
    (profanity-AT-agent / threats legal-physical-public / ALLCAPS+profanity+direct-address
    / 3+ signals in one message) → tag `ZHC-aggression-detected`, route to aggression-
    handler, notify operator. ALL CAPS ALONE never fires. Sensitivity lenient|standard|
    strict in openclaw.json. Extends bot-detection, does not replace it. See
    `<MASTER_FILES_DIR>/aggression-detection-protocol.md`.
22. Interrupt Rule (F44, detour-and-return) — always-listening layer parallel to the active
    workflow. On an interrupt (operator-urgent keyword, FAQ type, compliance redirect, F50
    aggression, F49 pixel-priority): SAVE state (step + gathered data + context) → EXECUTE
    sub-flow → RETURN to the saved step with a soft "coming back to where we were"
    transition. DISTINCT from Step 9.33's route-and-stay. Max 2 levels deep, then escalate.
    Multiple triggers: highest priority first, queue the rest. Tags `ZHC-interrupt-handled`
    / `ZHC-faq-detoured` / `ZHC-aggression-handled-and-resumed`. See
    `<MASTER_FILES_DIR>/smart-playbook-switching-protocol.md`.
23. Geo-Qualification Rule (F45, OFF by default) — when ON, location signals (pixel/IP →
    phone area code → form address → explicit ask) are HINTS only. ALWAYS ASK to confirm
    before ANY disqualification or out-of-area handling — never disqualify on a guess.
    Out-of-area handling is operator-configured (decline+referral / limited-remote /
    waitlist / full decline). Service areas per product in
    `KnowledgeBases/sales/service-areas.md`. Tags `ZHC-out-of-service-area` /
    `ZHC-service-area-confirmed` / `ZHC-service-area-flexible`. See
    `<MASTER_FILES_DIR>/geo-qualification-protocol.md`.
24. CRM Field-Write Rule (F46) — the agent writes ANY GHL contact custom field mid-convo,
    type-aware (text/number/date/dropdown), discovering via GET /locations/{id}/customFields
    and validating before write. CREATE-IF-MISSING: if no matching field exists, create one
    with the `ZHC_` prefix (operator-approved allow-list action, NEVER customer-invoked),
    notify the operator, record the mapping in `crm-field-mappings.md`. The weekly tune-up
    reviews field usage. See `<MASTER_FILES_DIR>/crm-field-write-protocol.md`.
25. Smart-FAQ Rule (F47) — answer quick known FAQs INLINE, a SENTENCE not a sub-flow, then
    return to the current step in the SAME reply ("By the way, [answer]. Coming back to
    [topic]…"). Matches `KnowledgeBases/business/faqs.md`, scoped per workflow via
    `faq-scope.md`. Bigger FAQ questions hand off to F44 as a detour. Tag
    `ZHC-faq-answered`. See `<MASTER_FILES_DIR>/smart-faq-tool-protocol.md`.

<!-- END skill-38 round3-queueA-rules v1.5.0 -->
BLOCK
fi

echo "[skill 38] MEMORY.md updated (rules 6-14 + builder design rules 15-19 + round-3 queue-A rules 20-25 appended; backup at $MEM_MD.bak-*)"
