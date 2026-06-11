#!/usr/bin/env bash
# wire.sh — skill 38 live-client migration runner (M3: Rules 15/16 rewrite)
# Idempotent. Prints STATUS: lines.
# Safety contract:
#   - Backups taken before any edit.
#   - Python subprocess MUST report n15 > 0 AND n16 > 0; on any miss the backup
#     is restored, the success marker is NOT written, and the script exits non-zero.
#   - The success marker is written LAST and ONLY after verified replacements.
set -euo pipefail

# STOCK-BASH-3.2 COMPATIBILITY: the two MEMORY.md / AGENTS.md rewrite snippets
# (formerly inline `python3 - "$X" <<PYEOF ... PYEOF` heredocs inside $()) are
# shipped as the sibling _wire_rules_15_16.py / _wire_agents_ghl_note.py. Stock
# macOS /bin/bash 3.2.57 mis-parses a heredoc nested in a $() — it counts the
# double-quotes inside the Python and aborts the whole script with `unexpected
# EOF while looking for matching "` at PARSE time, so wire.sh failed to run on
# every no-Homebrew client Mac. Resolve the script's own dir to find the siblings.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

SKILL_VERSION="1.6.0"
WORKSPACE="${OPENCLAW_WORKSPACE:-$HOME/.openclaw/workspace}"
ISO=$(date -u +%Y%m%dT%H%M%SZ)

MEMORY_MD="$WORKSPACE/MEMORY.md"
AGENTS_MD="$WORKSPACE/AGENTS.md"

M3_MARKER="convertandflow-migration:rules-15-16:$SKILL_VERSION"

if grep -qF "$M3_MARKER" "$AGENTS_MD" 2>/dev/null; then
  echo "STATUS: M3 rules-15-16 already applied — skipping"
  exit 0
fi

# ── Back up both files (before any edit) ─────────────────────────────────────
BAK_MEMORY="${MEMORY_MD}.bak-convertandflow-${ISO}"
BAK_AGENTS="${AGENTS_MD}.bak-convertandflow-${ISO}"
[ -f "$MEMORY_MD" ] && cp "$MEMORY_MD" "$BAK_MEMORY"
[ -f "$AGENTS_MD" ] && cp "$AGENTS_MD" "$BAK_AGENTS"

# Helper: restore from backup and abort
restore_and_fail() {
  local reason="$1"
  echo "ERROR: M3 aborted — $reason"
  [ -f "$BAK_MEMORY" ] && cp "$BAK_MEMORY" "$MEMORY_MD" && echo "STATUS: MEMORY.md restored from backup"
  [ -f "$BAK_AGENTS" ] && cp "$BAK_AGENTS" "$AGENTS_MD" && echo "STATUS: AGENTS.md restored from backup"
  exit 1
}

# ── Rewrite Rules 15/16 in MEMORY.md ─────────────────────────────────────────
MEMORY_M3_OK=0
if [ -f "$MEMORY_MD" ] && grep -q 'skill-38 builder-design-rules' "$MEMORY_MD" 2>/dev/null; then
  PYOUT=$(python3 "$SCRIPT_DIR/_wire_rules_15_16.py" "$MEMORY_MD")
  echo "MEMORY.md python output: $PYOUT"
  N15=$(echo "$PYOUT" | python3 -c "import sys,re; m=re.search(r'n15=(\d+)',sys.stdin.read()); print(m.group(1) if m else '0')")
  N16=$(echo "$PYOUT" | python3 -c "import sys,re; m=re.search(r'n16=(\d+)',sys.stdin.read()); print(m.group(1) if m else '0')")
  if [ "$N15" -gt 0 ] && [ "$N16" -gt 0 ]; then
    echo "STATUS: M3 MEMORY.md Rules 15/16 rewritten (n15=$N15 n16=$N16)"
    MEMORY_M3_OK=1
  else
    restore_and_fail "MEMORY.md regex matched n15=$N15 n16=$N16 — old wording not found; possible format drift. Review MEMORY.md manually."
  fi
else
  echo "STATUS: M3 MEMORY.md — builder-design-rules block not found; will apply on next update-skills run"
  # Not a fatal error: fresh boxes without the block are OK (block added by install)
  MEMORY_M3_OK=1
fi

# ── Rewrite GHL note in AGENTS.md ────────────────────────────────────────────
AGENTS_M3_OK=0
if [ -f "$AGENTS_MD" ] && grep -q 'STEP_1_85_WORKFLOW_BUILDER_TRIGGERS' "$AGENTS_MD" 2>/dev/null; then
  PYOUT_A=$(python3 "$SCRIPT_DIR/_wire_agents_ghl_note.py" "$AGENTS_MD")
  echo "AGENTS.md python output: $PYOUT_A"
  N_A=$(echo "$PYOUT_A" | python3 -c "import sys,re; m=re.search(r'n=(\d+)',sys.stdin.read()); print(m.group(1) if m else '0')")
  if [ "$N_A" -gt 0 ]; then
    echo "STATUS: M3 AGENTS.md GHL note rewritten (n=$N_A)"
    AGENTS_M3_OK=1
  else
    restore_and_fail "AGENTS.md GHL-note regex matched n=0 — old wording not found; possible format drift. Review AGENTS.md manually."
  fi
else
  echo "STATUS: M3 AGENTS.md — STEP_1_85 block not found; will apply on next update-skills run"
  AGENTS_M3_OK=1
fi

# ── Write success marker LAST and only on verified success ────────────────────
if [ "$MEMORY_M3_OK" -eq 1 ] && [ "$AGENTS_M3_OK" -eq 1 ]; then
  echo "" >> "$AGENTS_MD"
  echo "<!-- $M3_MARKER -->" >> "$AGENTS_MD"
  echo "STATUS: skill-38 wire.sh M3 complete ($SKILL_VERSION)"
else
  restore_and_fail "one or more M3 sub-steps did not confirm success"
fi
