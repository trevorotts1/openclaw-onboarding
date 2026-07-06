#!/usr/bin/env bash
# qc-zhc-tag-prefix.sh — machine-enforce the ZHC tag-prefix rule (Round-3 Queue-A,
# v1.5.0): every tag the Round-3 Queue-A protocols + the agent-created tag EXAMPLES
# present in the skill use the `ZHC-` prefix, and the rule is documented where it must be.
#
# WHY: tags the agent creates PROGRAMMATICALLY must be `ZHC-`-prefixed so operators can
# tell agent-created tags apart from their own. This gate proves the skill's own
# documentation + examples are consistent with that rule, so a regression that drops the
# prefix (or an example that introduces a bare agent-created tag) fails the build.
#
# WHAT IT CHECKS (all from the repo alone — CI-safe, BASH-only so it respects the .py
# claude-/anthropic ban):
#   1. MEMORY Rule 20 is appended by 06-append-memory-rules.sh (the ZHC- prefix rule).
#   2. AGENTS.md gets the SKILL38_ZHC_TAG_PREFIX marker block (05-update-agents-md.sh).
#   3. The dedicated protocol exists (zhc-tag-prefix-protocol.md) and states "NOT
#      retroactive" + reuses the D.1 / Section-6 create_tag mechanism.
#   4. Every Round-3 Queue-A feature tag named across the new protocols carries `ZHC-`.
#   5. The D.1 example tags + the workflow-AI Section-6 Add-Tag example were updated to
#      the `ZHC-` form (no bare agent-created example tag left behind).
#
# Exit codes: 0 = clean; 1 = at least one ZHC tag-prefix-rule violation.
#
# Usage:
#   bash scripts/qc-zhc-tag-prefix.sh
#   bash scripts/qc-zhc-tag-prefix.sh --skill-dir /path/to/38-conversational-ai-system

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    -h|--help)   sed -n '1,32p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

FAIL=0
pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAIL=1; }

echo "=== qc-zhc-tag-prefix: ZHC programmatic-tag-prefix rule gate ==="
echo "skill_dir : $SKILL_DIR"
echo ""

# 1. MEMORY Rule 20 in the appender.
MEM_SCRIPT="$SKILL_DIR/scripts/06-append-memory-rules.sh"
if [ -f "$MEM_SCRIPT" ] && grep -qE '^20\. *ZHC Tag-Prefix Rule' "$MEM_SCRIPT" && grep -q 'ZHC-' "$MEM_SCRIPT"; then
  pass "06-append-memory-rules.sh appends MEMORY Rule 20 (ZHC Tag-Prefix Rule)"
else
  fail "06-append-memory-rules.sh is missing MEMORY Rule 20 (ZHC Tag-Prefix Rule)"
fi
if grep -q 'NOT retroactive\|not retroactive' "$MEM_SCRIPT" 2>/dev/null; then
  pass "MEMORY Rule 20 states the rule is NOT retroactive"
else
  fail "MEMORY Rule 20 must state the rule is NOT retroactive"
fi

# 2. AGENTS.md marker block in the updater.
AG_SCRIPT="$SKILL_DIR/scripts/05-update-agents-md.sh"
if [ -f "$AG_SCRIPT" ] && grep -q 'SKILL38_ZHC_TAG_PREFIX' "$AG_SCRIPT"; then
  pass "05-update-agents-md.sh inserts the SKILL38_ZHC_TAG_PREFIX behavioral block"
else
  fail "05-update-agents-md.sh is missing the SKILL38_ZHC_TAG_PREFIX block"
fi

# 3. Dedicated protocol exists + key clauses.
PROTO="$SKILL_DIR/protocols/zhc-tag-prefix-protocol.md"
if [ -f "$PROTO" ]; then
  pass "protocols/zhc-tag-prefix-protocol.md exists"
  grep -q 'ZHC-' "$PROTO" && pass "protocol states the ZHC- prefix" || fail "protocol must state the ZHC- prefix"
  grep -qi 'not retroactive' "$PROTO" && pass "protocol states NOT retroactive" || fail "protocol must state NOT retroactive"
  grep -qi 'create_tag\|D.1\|Section 6' "$PROTO" && pass "protocol reuses the existing create_tag mechanism (D.1 / Section 6)" || fail "protocol must reuse the existing create_tag mechanism (reference D.1 / Section 6)"
else
  fail "protocols/zhc-tag-prefix-protocol.md MISSING"
fi

# 3b. Lifecycle Status Tags (U-7) - the five standardized lifecycle tags must be
#     named in the protocol, AND the task-creation companion behavior (U-14) must
#     be documented in that same lifecycle section.
if [ -f "$PROTO" ]; then
  grep -qi 'Lifecycle Status Tags' "$PROTO" \
    && pass "U-7 Lifecycle Status Tags section present" \
    || fail "U-7 Lifecycle Status Tags section MISSING from zhc-tag-prefix-protocol.md"
  LIFECYCLE_TAGS=(
    "ZHC-ai-responded"
    "ZHC-ai-booking-error"
    "ZHC-ai-handoff"
    "ZHC-ai-completed"
    "ZHC-ai-opted-out"
  )
  for t in "${LIFECYCLE_TAGS[@]}"; do
    if grep -qF "$t" "$PROTO"; then
      pass "U-7 lifecycle tag present: $t"
    else
      fail "U-7 lifecycle tag MISSING from zhc-tag-prefix-protocol.md: $t"
    fi
  done
  # U-14 companion: the lifecycle section must document that ZHC-ai-handoff also
  # creates a GHL task (task-creation companion behavior).
  if grep -qi 'Task-creation companion' "$PROTO" && grep -qi 'creates a GHL Task' "$PROTO"; then
    pass "U-14 task-creation companion behavior documented in the lifecycle section"
  else
    fail "U-14 task-creation companion behavior MISSING (lifecycle section must document the ZHC-ai-handoff GHL task)"
  fi
fi

# 4. Every Round-3 Queue-A feature tag named in the new protocols carries ZHC-.
#    The canonical tag names this wave introduces:
EXPECTED_TAGS=(
  "ZHC-tension-detected"
  "ZHC-aggression-detected"
  "ZHC-interrupt-handled"
  "ZHC-faq-detoured"
  "ZHC-aggression-handled-and-resumed"
  "ZHC-out-of-service-area"
  "ZHC-service-area-confirmed"
  "ZHC-service-area-flexible"
  "ZHC-faq-answered"
  "ZHC-bot-suspected"
  "ZHC-stalled-sales"
  "ZHC-followup-cadence-1"
  "ZHC-followup-cadence-10"
  "ZHC-cold-lead-released"
  "ZHC-followup-opted-out"
)
for t in "${EXPECTED_TAGS[@]}"; do
  if grep -rqF "$t" "$SKILL_DIR/protocols" 2>/dev/null; then
    pass "tag present and ZHC-prefixed: $t"
  else
    fail "expected ZHC-prefixed tag not found in protocols/: $t"
  fi
done

# 4b. The F29 follow-up protocol must NOT leave a BARE agent-created tag behind.
#     This protocol APPLIES tags in prose ("tag contact as <x>") rather than via a
#     create_tag(...) literal, so the Section-6 literal parser below cannot see it.
#     These four tags are agent-created (per the single test) and MUST be ZHC- form.
FUP="$SKILL_DIR/protocols/intelligent-followup-protocol.md"
if [ -f "$FUP" ]; then
  fup_bare=0
  for bare in 'stalled-sales' 'cold-lead-released' 'followup-opted-out' 'followup-cadence-'; do
    # A bare hit = the token in back-ticks WITHOUT the ZHC- prefix immediately before it.
    if grep -nE "\`${bare}" "$FUP" | grep -vE "ZHC-${bare}" >/dev/null 2>&1; then
      fail "intelligent-followup-protocol.md applies a BARE agent-created tag \`${bare}…\` — must be ZHC-${bare}…"
      fup_bare=1
    fi
  done
  [ "$fup_bare" -eq 0 ] && pass "intelligent-followup-protocol.md: all agent-created follow-up tags are ZHC- prefixed (no bare stalled-sales/cold-lead-released/followup-opted-out/followup-cadence-N)"
else
  fail "protocols/intelligent-followup-protocol.md MISSING (cannot check F29 follow-up tags)"
fi

# 5. The D.1 example tags + the Section-6 Add-Tag example were updated to ZHC- form.
#    Catch a regression that reintroduces a BARE agent-created example tag in those
#    two authoritative tag-creation docs (NOT a blanket ban — operator-owned tags in
#    filters elsewhere are fine; these two docs are where the AGENT creates tags).
CWP="$SKILL_DIR/protocols/conversation-workflows-protocol.md"
if [ -f "$CWP" ]; then
  # The D.1 example list must now use the ZHC- forms.
  if grep -qF 'ZHC-pricing-interest' "$CWP" && grep -qF 'ZHC-discovery-scheduled' "$CWP"; then
    pass "D.1 example tags use the ZHC- form (ZHC-pricing-interest / ZHC-discovery-scheduled)"
  else
    fail "D.1 example tags must use the ZHC- form (conversation-workflows-protocol.md Section D.1)"
  fi
  # And must NOT leave the bare back-ticked agent-created example tags behind.
  if grep -qE '`pricing-interest`|`discovery-scheduled`|`quoted`' "$CWP"; then
    fail "D.1 still shows a BARE agent-created example tag (\`pricing-interest\`/\`discovery-scheduled\`/\`quoted\`) — prefix it ZHC-"
  else
    pass "D.1 has no bare agent-created example tag left behind"
  fi
else
  fail "protocols/conversation-workflows-protocol.md MISSING (cannot check D.1)"
fi

WFAI="$SKILL_DIR/references/workflow-ai-instructions-standard.md"
if [ -f "$WFAI" ]; then
  if grep -qF 'ZHC-discovery-scheduled' "$WFAI"; then
    pass "workflow-AI Section-6 Add-Tag example uses the ZHC- form"
  else
    fail "workflow-AI Section-6 Add-Tag example must use the ZHC- form (references/workflow-ai-instructions-standard.md)"
  fi
else
  fail "references/workflow-ai-instructions-standard.md MISSING (cannot check Section 6)"
fi

# 6. No "bare" programmatic-creation tag EXAMPLE (the load-bearing literal parser).
#    Scan the create-tag mechanism docs + the v1.5.0 protocols for create_tag(...)
#    name= and "name": literals, and the POST .../tags body "name": literals that
#    sit in a create-tag context. Any quoted literal value that is NOT a placeholder
#    (<...> / $...) and NOT already ZHC-prefixed is a violation. An Add-Tag / add_tag
#    action APPLYING an operator's pre-existing tag verbatim is NOT flagged.
SCAN_FILES=(
  "$SKILL_DIR/protocols/conversation-workflows-protocol.md"
  "$SKILL_DIR/references/workflow-ai-instructions-standard.md"
  "$SKILL_DIR/protocols/zhc-tag-prefix-protocol.md"
  "$SKILL_DIR/protocols/aggression-detection-protocol.md"
  "$SKILL_DIR/protocols/smart-playbook-switching-protocol.md"
  "$SKILL_DIR/protocols/geo-qualification-protocol.md"
  "$SKILL_DIR/protocols/smart-faq-tool-protocol.md"
  "$SKILL_DIR/protocols/intelligent-followup-protocol.md"
)
bare_hits=0
for f in "${SCAN_FILES[@]}"; do
  [ -f "$f" ] || continue
  while IFS= read -r line; do
    # Skip apply/Add-Tag context (applying an existing tag verbatim is allowed).
    printf '%s\n' "$line" | grep -qiE 'add_tag|add-tag|apply' && continue
    # Extract the quoted value after name= or "name":
    val="$(printf '%s\n' "$line" | sed -nE 's/.*(name=|"name"[[:space:]]*:)[[:space:]]*"([^"]*)".*/\2/p')"
    [ -z "$val" ] && val="$(printf '%s\n' "$line" | sed -nE "s/.*name=[[:space:]]*'([^']*)'.*/\1/p")"
    [ -z "$val" ] && continue
    # Allowed: a placeholder (<...> or $...) or a ZHC- value.
    case "$val" in
      "<"*|"\$"*|ZHC-*) : ;;  # ok
      *)
        fail "bare programmatic create-tag literal in $(basename "$f"): name=\"$val\" (must be ZHC- or a placeholder)"
        bare_hits=$((bare_hits+1))
        ;;
    esac
  done < <(grep -nE '(create_tag|/tags)' "$f" 2>/dev/null | grep -E '(name=|"name"[[:space:]]*:)' )
done
if [ "$bare_hits" -eq 0 ]; then
  pass "no bare programmatic create-tag examples (all are ZHC- or placeholders)"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS — the ZHC tag-prefix rule is documented (MEMORY Rule 20 + AGENTS block + protocol), every programmatic-tag example uses the ZHC- prefix, and no bare programmatic create-tag literal survives."
  exit 0
else
  echo "RESULT: FAIL — a ZHC tag-prefix-rule violation was found (see above)."
  exit 1
fi
