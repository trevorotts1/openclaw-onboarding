#!/usr/bin/env bash
# qc-followup-exclusion.sh — machine-enforce review finding C4: a Purple collection
# contact's follow-up belongs to the shared reminder machine and NEVER to the legacy
# 10-touch Intelligent Follow-up cadence.
#
# WHY: the legacy protocol runs 10 touches over 30 days (5 inside 72 hours), switches
# channel at T6 and offers a discount at T8 — beside the Purple rule of ONE initial
# invitation plus three escalating reminders, ONE shared count, no reset, no catch-up
# burst. With no precedence rule, one stalled Purple capture could receive up to 13
# unsolicited touches plus a discount the monthly approval never covered. Three copies of
# the runtime rule exist (the protocol, the AGENTS.md stanza writer, the canonical rules
# reference); this gate proves all three carry the exclusion, that the stale installer
# debris is gone, and that the gate itself is wired into the QC checklist and CI.
#
# WHAT IT CHECKS (repo alone — CI-safe, BASH-only so it respects the .py claude-/anthropic ban):
#   1. protocols/intelligent-followup-protocol.md exists.
#   2. It carries the exclusion: `collection_sequence_id`, the shared reminder machine owning
#      follow-up, the "Never enter this sequence" prohibition, and open OR closed coverage.
#   3. scripts/05-update-agents-md.sh carries the same exclusion in its runtime-invariants
#      stanza (the AGENTS.md writer is the only path to a client box).
#   4. references/agents-runtime-rules.md carries the same exclusion.
#   5. The stale notes are DELETED: "Pre-Feature-15", "Until v5.7", and the leftover
#      installer fragments ("**B. Append to MEMORY.md design principles", "**C. Append to
#      Run Manifest").
#   6. POSITIVE CONTROL: known-present text in the protocol and the stanza writer is still
#      found, so a broken scan can never be mistaken for a successful deletion.
#   7. WIRING: 11-run-qc-checklist.sh invokes this gate, qc-static.yml runs it and its
#      negative test, and both this script and qc-followup-exclusion.test.sh exist.
#
# Exit codes: 0 = clean; 1 = at least one C4 invariant violation.
#
# Usage:
#   bash scripts/qc-followup-exclusion.sh
#   bash scripts/qc-followup-exclusion.sh --skill-dir /path/to/38-conversational-ai-system
#   bash scripts/qc-followup-exclusion.sh --repo-root /path/to/repo
#     (--repo-root defaults to the skill dir's parent, for the CI wiring checks)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"; shift 2 ;;
    --repo-root) REPO_ROOT="$2"; shift 2 ;;
    -h|--help)   sed -n '1,45p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

FAIL=0
pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAIL=1; }

echo "=== qc-followup-exclusion: C4 Purple follow-up ownership gate ==="
echo "skill_dir : $SKILL_DIR"
echo "repo_root : $REPO_ROOT"
echo ""

PROTO="$SKILL_DIR/protocols/intelligent-followup-protocol.md"
AG_SCRIPT="$SKILL_DIR/scripts/05-update-agents-md.sh"
RULES="$SKILL_DIR/references/agents-runtime-rules.md"
CHECKLIST="$SKILL_DIR/scripts/11-run-qc-checklist.sh"
WORKFLOW="$REPO_ROOT/.github/workflows/qc-static.yml"
TEST="$SKILL_DIR/scripts/qc-followup-exclusion.test.sh"

# ---- 1. Protocol exists -----------------------------------------------------
if [ -f "$PROTO" ]; then
  pass "protocols/intelligent-followup-protocol.md exists"
else
  fail "protocols/intelligent-followup-protocol.md MISSING"
fi

echo ""

# ---- 6 (run first). Positive control: the scans must still see real text ----
# Without this, every "stale note is absent" result below could be produced by a scan
# that reads nothing at all.
CONTROL_OK=1
if [ -f "$PROTO" ]; then
  if grep -qF '## 10-touchpoint cadence' "$PROTO"; then
    pass "control: the protocol still carries its 10-touchpoint cadence heading"
  else
    fail "control BROKEN: '## 10-touchpoint cadence' not found in the protocol — every absence check below is meaningless; fix the scan before trusting a PASS"
    CONTROL_OK=0
  fi
else
  CONTROL_OK=0
fi
if [ -f "$AG_SCRIPT" ]; then
  if grep -qF 'Skill 38 — runtime INVARIANTS' "$AG_SCRIPT"; then
    pass "control: 05-update-agents-md.sh still carries the runtime-invariants stanza"
  else
    fail "control BROKEN: the runtime-invariants stanza not found in 05-update-agents-md.sh — absence checks below are meaningless"
    CONTROL_OK=0
  fi
else
  CONTROL_OK=0
fi

echo ""

# ---- 2. Protocol exclusion -------------------------------------------------
if [ -f "$PROTO" ]; then
  if grep -qF 'collection_sequence_id' "$PROTO"; then
    pass "protocol keys the exclusion to a present collection_sequence_id"
  else
    fail "protocol must key the exclusion to collection_sequence_id"
  fi
  if grep -qiF 'shared reminder machine owns follow-up' "$PROTO"; then
    pass "protocol states the shared reminder machine owns follow-up"
  else
    fail "protocol must state that the shared reminder machine owns follow-up"
  fi
  if grep -qF 'Never enter this sequence' "$PROTO"; then
    pass "protocol carries the literal 'Never enter this sequence' prohibition"
  else
    fail "protocol must carry the 'Never enter this sequence' prohibition"
  fi
  if grep -qiF 'open OR closed' "$PROTO"; then
    pass "protocol covers a sequence that is open OR closed"
  else
    fail "protocol must cover a Purple collection sequence that is open OR closed"
  fi
  if grep -qiF 'three escalating reminders' "$PROTO"; then
    pass "protocol names the Purple three-escalating-reminder budget it may not duplicate"
  else
    fail "protocol must name the Purple three-escalating-reminder budget"
  fi
  if grep -qiF 'no parallel sequence' "$PROTO"; then
    pass "protocol forbids a parallel sequence beside the shared reminder machine"
  else
    fail "protocol must forbid a parallel sequence beside the shared reminder machine"
  fi
else
  fail "protocol exclusion checks skipped — file missing"
fi

echo ""

# ---- 3. AGENTS.md stanza writer -------------------------------------------
if [ -f "$AG_SCRIPT" ]; then
  if grep -qF 'collection_sequence_id' "$AG_SCRIPT"; then
    pass "05-update-agents-md.sh keys the exclusion to collection_sequence_id"
  else
    fail "05-update-agents-md.sh must key the exclusion to collection_sequence_id"
  fi
  if grep -qF 'SHARED REMINDER MACHINE' "$AG_SCRIPT"; then
    pass "05-update-agents-md.sh names the SHARED REMINDER MACHINE as the owner"
  else
    fail "05-update-agents-md.sh must name the SHARED REMINDER MACHINE as the owner"
  fi
  if grep -qF 'Never enter the Intelligent Follow-up Protocol' "$AG_SCRIPT"; then
    pass "05-update-agents-md.sh carries the 'Never enter the Intelligent Follow-up Protocol' prohibition"
  else
    fail "05-update-agents-md.sh must carry the 'Never enter the Intelligent Follow-up Protocol' prohibition"
  fi
  if grep -qiF 'three escalating reminders' "$AG_SCRIPT"; then
    pass "05-update-agents-md.sh names the Purple three-escalating-reminder budget"
  else
    fail "05-update-agents-md.sh must name the Purple three-escalating-reminder budget"
  fi
else
  fail "scripts/05-update-agents-md.sh MISSING"
fi

echo ""

# ---- 4. Canonical rules reference ----------------------------------------
if [ -f "$RULES" ]; then
  if grep -qF 'collection_sequence_id' "$RULES"; then
    pass "references/agents-runtime-rules.md keys the exclusion to collection_sequence_id"
  else
    fail "references/agents-runtime-rules.md must key the exclusion to collection_sequence_id"
  fi
  if grep -qF 'SHARED REMINDER MACHINE' "$RULES"; then
    pass "references/agents-runtime-rules.md names the SHARED REMINDER MACHINE as the owner"
  else
    fail "references/agents-runtime-rules.md must name the SHARED REMINDER MACHINE as the owner"
  fi
  if grep -qF 'Never enter the Intelligent Follow-up Protocol' "$RULES"; then
    pass "references/agents-runtime-rules.md carries the prohibition"
  else
    fail "references/agents-runtime-rules.md must carry the prohibition"
  fi
else
  fail "references/agents-runtime-rules.md MISSING"
fi

echo ""

# ---- 5. Stale notes + installer fragments are DELETED --------------------
if [ "$CONTROL_OK" -eq 1 ]; then
  for stale in 'Pre-Feature-15' 'Until v5.7' '**B. Append to MEMORY.md design principles' '**C. Append to Run Manifest'; do
    if [ -f "$PROTO" ] && grep -qF "$stale" "$PROTO"; then
      fail "stale note still present in the protocol: '$stale'"
    else
      pass "stale note deleted from the protocol: '$stale'"
    fi
  done
  # A leftover code fence with no opener would mean the fragment deletion stopped
  # mid-block; the file must end on prose, not on an unterminated installer snippet.
  if [ -f "$PROTO" ]; then
    FENCE_COUNT="$(grep -cF '```' "$PROTO" || true)"
    if [ $((FENCE_COUNT % 2)) -eq 0 ]; then
      pass "protocol code fences are balanced ($FENCE_COUNT) — no half-deleted installer fragment"
    else
      fail "protocol has an ODD code-fence count ($FENCE_COUNT) — a half-deleted installer fragment remains"
    fi
  fi
else
  fail "stale-note deletion checks NOT trusted — the control failed"
fi

echo ""

# ---- 7. Wiring ----------------------------------------------------------
if [ -f "$CHECKLIST" ]; then
  if grep -qF 'qc-followup-exclusion.sh' "$CHECKLIST"; then
    pass "11-run-qc-checklist.sh invokes qc-followup-exclusion.sh"
  else
    fail "11-run-qc-checklist.sh must invoke qc-followup-exclusion.sh"
  fi
else
  fail "scripts/11-run-qc-checklist.sh MISSING"
fi
if [ -f "$WORKFLOW" ]; then
  if grep -qF 'qc-followup-exclusion.sh' "$WORKFLOW"; then
    pass "qc-static.yml runs qc-followup-exclusion.sh"
  else
    fail "qc-static.yml must run qc-followup-exclusion.sh"
  fi
  if grep -qF 'qc-followup-exclusion.test.sh' "$WORKFLOW"; then
    pass "qc-static.yml runs the negative test (qc-followup-exclusion.test.sh)"
  else
    fail "qc-static.yml must run qc-followup-exclusion.test.sh"
  fi
else
  fail ".github/workflows/qc-static.yml MISSING"
fi
if [ -f "$TEST" ]; then
  pass "qc-followup-exclusion.test.sh exists"
else
  fail "qc-followup-exclusion.test.sh MISSING (an untested gate is worthless)"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS — a Purple collection contact (collection_sequence_id present, open or closed) never enters the legacy 10-touch cadence; the shared reminder machine owns follow-up in the protocol, the AGENTS.md stanza writer and the canonical rules reference; the stale Pre-Feature-15 / Until v5.7 notes and the leftover installer fragments are gone; and the gate is wired into 11-run-qc-checklist.sh and qc-static.yml."
  exit 0
else
  echo "RESULT: FAIL — a C4 follow-up-ownership invariant is missing or a stale note survived (see above)."
  exit 1
fi
