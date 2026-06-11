#!/usr/bin/env bash
# wire.sh — skill 38 live-client migration runner (M3: Rules 15/16 rewrite)
# Idempotent. Prints STATUS: lines.
# Safety contract:
#   - Backups taken before any edit.
#   - Python subprocess MUST report n15 > 0 AND n16 > 0; on any miss the backup
#     is restored, the success marker is NOT written, and the script exits non-zero.
#   - The success marker is written LAST and ONLY after verified replacements.
set -euo pipefail

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
  PYOUT=$(python3 - "$MEMORY_MD" <<'PYEOF'
import sys, pathlib, re

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding='utf-8')

# Rule 15: match on "15." + any header text ending the line, then the rule body
# which may be indented with any amount of whitespace (not just 4 spaces).
# Also matches the forbidding phrase to catch variant indent styles.
r15_old = re.compile(
    r'15\. (?:Terminology Rule|Build-Routing Rule)[^\n]*\n'
    r'(?:[ \t]+[^\n]*\n)*',
    re.MULTILINE
)
r15_new = (
    '15. Build-Routing Rule — when the operator says "build me a workflow / playbook /\n'
    '    funnel," route by node type. A workflow WITH a conversational node -> skill 44\n'
    '    builds the structure and AUTO-INVOKES skill 38 for the brain in the SAME run\n'
    '    (THE TRINITY: GHL automation + communications playbook + workflow-AI prompt\n'
    '    ship together or it is NOT registered). A PURELY MECHANICAL workflow (no\n'
    '    conversational node) builds standalone via skill 41\'s structure + 12-point\n'
    '    checklist. (Supersedes the legacy "always Step 9.20" routing.)\n'
)
text, n15 = re.subn(r15_old, r15_new, text, count=1)

# Rule 16: match on "16." + any header text ending the line, then body lines
r16_old = re.compile(
    r'16\. (?:No-GHL-API Rule|Convert-and-Flow Build-Path Rule)[^\n]*\n'
    r'(?:[ \t]+[^\n]*\n)*',
    re.MULTILINE
)
r16_new = (
    '16. Convert-and-Flow Build-Path Rule — GHL Automations have no PUBLIC API or MCP.\n'
    '    The Build with AI button is the public path. Skill 44 provides an internal-API\n'
    '    build path when the client\'s Firebase token is present; when absent, Build with\n'
    '    AI remains the only path. (Never claim a PUBLIC GHL Automations API exists.)\n'
)
text, n16 = re.subn(r16_old, r16_new, text, count=1)

# Also wipe any surviving old wording lines (belt + suspenders, within the
# builder-design-rules block only — avoid touching CHANGELOG).
old_wording_re = re.compile(
    r'^([ \t]*)(?:NO API and NO MCP|NEVER write or claim code that ["“]calls the GHL Automations API["”])[^\n]*\n',
    re.MULTILINE
)
text, n_old = re.subn(old_wording_re, '', text)

path.write_text(text, encoding='utf-8')
# Print machine-readable counts for the shell to parse
print(f"n15={n15} n16={n16} n_old_wiped={n_old}")
PYEOF
  )
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
  PYOUT_A=$(python3 - "$AGENTS_MD" <<'PYEOF'
import sys, pathlib, re

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding='utf-8')

# Match the old GHL note (any variant) including multi-line quoted paste instruction
old_note = re.compile(
    r'GHL (?:note|build-path note): [^\n]*\n'
    r'(?:[ \t]*"?[^\n]*\n)*?'          # quoted body lines
    r'(?:[ \t]*[^\n]*paste[^\n]*\n)*',  # paste-instruction lines
    re.MULTILINE
)
new_note = (
    'GHL build-path note: GHL Automations have no PUBLIC API or MCP. The Build with AI\n'
    'button is the public path. Skill 44 (convert-and-flow-operator) provides an\n'
    'internal-API build path when the client\'s Firebase token is present; when absent,\n'
    'Build with AI remains the only path (the agent generates the prompt, the operator\n'
    'clicks + pastes; the prompt nails the SHAPE, the operator pastes tokens after —\n'
    'always ship the verification checklist).\n'
)
text, n = re.subn(old_note, new_note, text, count=1)
path.write_text(text, encoding='utf-8')
print(f"n={n}")
PYEOF
  )
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
