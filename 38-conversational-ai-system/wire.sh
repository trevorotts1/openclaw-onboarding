#!/usr/bin/env bash
# wire.sh — skill 38 live-client migration runner (M3: Rules 15/16 rewrite)
# Idempotent. Prints STATUS: lines.
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

# ── Back up both files ────────────────────────────────────────────────────────
[ -f "$MEMORY_MD" ] && cp "$MEMORY_MD" "${MEMORY_MD}.bak-convertandflow-${ISO}"
[ -f "$AGENTS_MD" ] && cp "$AGENTS_MD" "${AGENTS_MD}.bak-convertandflow-${ISO}"

# ── Rewrite Rule 15 in MEMORY.md (within builder-design-rules marker span) ───
if [ -f "$MEMORY_MD" ] && grep -q 'skill-38 builder-design-rules' "$MEMORY_MD" 2>/dev/null; then
  python3 - "$MEMORY_MD" <<'PYEOF'
import sys, pathlib, re

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding='utf-8')

# Replace Rule 15 (old Terminology Rule)
r15_old = re.compile(
    r'15\. Terminology Rule[^\n]*\n'
    r'(?:    [^\n]*\n)*',
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

# Replace Rule 16 (old No-GHL-API Rule)
r16_old = re.compile(
    r'16\. No-GHL-API Rule[^\n]*\n'
    r'(?:    [^\n]*\n)*',
    re.MULTILINE
)
r16_new = (
    '16. Convert-and-Flow Build-Path Rule — GHL Automations have no PUBLIC API or MCP.\n'
    '    The Build with AI button is the public path. Skill 44 provides an internal-API\n'
    '    build path when the client\'s Firebase token is present; when absent, Build with\n'
    '    AI remains the only path. (Never claim a PUBLIC GHL Automations API exists.)\n'
)
text, n16 = re.subn(r16_old, r16_new, text, count=1)

path.write_text(text, encoding='utf-8')
print(f"MEMORY.md: Rule 15 replacements={n15}, Rule 16 replacements={n16}")
PYEOF
  echo "STATUS: M3 MEMORY.md Rules 15/16 rewritten"
else
  echo "STATUS: M3 MEMORY.md — builder-design-rules block not found; fresh install will apply on next update-skills run"
fi

# ── Rewrite GHL note in AGENTS.md (STEP_1_85_WORKFLOW_BUILDER_TRIGGERS span) ─
if [ -f "$AGENTS_MD" ] && grep -q 'STEP_1_85_WORKFLOW_BUILDER_TRIGGERS' "$AGENTS_MD" 2>/dev/null; then
  python3 - "$AGENTS_MD" <<'PYEOF'
import sys, pathlib, re

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding='utf-8')

# Replace old GHL note in AGENTS.md STEP_1_85 block
old_note = re.compile(
    r'GHL note: Automations have NO API/MCP[^\n]*\n'
    r'(?:"[^\n]*\n)*'
    r'(?:[^\n]*paste.*\n)*',
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
print(f"AGENTS.md: GHL note replacements={n}")
PYEOF
  echo "STATUS: M3 AGENTS.md GHL note rewritten"
else
  echo "STATUS: M3 AGENTS.md — STEP_1_85 block not found; will apply on next update-skills run"
fi

# ── Write success marker ──────────────────────────────────────────────────────
echo "" >> "$AGENTS_MD"
echo "<!-- $M3_MARKER -->" >> "$AGENTS_MD"
echo "STATUS: skill-38 wire.sh M3 complete ($SKILL_VERSION)"
