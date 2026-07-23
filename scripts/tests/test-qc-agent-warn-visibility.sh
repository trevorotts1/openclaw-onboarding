#!/usr/bin/env bash
# U122 — STAGE 1: test qc-agent.sh surfaces per-skill warn counts in JSON
# without changing pass/fail (QC_FAIL_ON_WARN is NOT set).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
TMP_SKILL="tmp-test-u122-$$"
cleanup() { rm -rf "$ROOT/$TMP_SKILL" 2>/dev/null || true; }
trap cleanup EXIT
mkdir -p "$ROOT/$TMP_SKILL"
echo "# SKILL.md" > "$ROOT/$TMP_SKILL/SKILL.md"
echo "# INSTALL.md" > "$ROOT/$TMP_SKILL/INSTALL.md"
cat > "$ROOT/$TMP_SKILL/QC.md" << 'QCEOF'
# QC.md
## 10-point rubric (out of 10)
### Self-Audit Checklist
### Retry cap: 5-loop escalation
QCEOF
cat > "$ROOT/$TMP_SKILL/qc-${TMP_SKILL}.sh" << 'SKEWER'
#!/usr/bin/env bash
echo "═══ Skill mock — Install QC ═══"
echo "  ✓ PASS — skill folder present"
echo "  ⚠ WARN — optional dep not found"
echo "  ⚠ WARN — config file uses default"
echo "  ⚠ WARN — chroot not available"
echo "═══ Result: 1 passed | 0 failed | 3 warnings ═══"
exit 0
SKEWER
chmod +x "$ROOT/$TMP_SKILL/qc-${TMP_SKILL}.sh"
echo ""
echo "════════════════════════════════════════════════"
echo "  U122 TEST: warn visibility (STAGE 1)"
echo "════════════════════════════════════════════════"
AGENT_RC=0
JSON=$(bash scripts/qc-agent.sh "$TMP_SKILL" 2>/dev/null) || AGENT_RC=$?
echo "--- exit code: $AGENT_RC ---"
echo "$JSON"
PASSES=0; FAILS=0
assert() { if eval "$2" >/dev/null 2>&1; then echo "  ✓ $1"; PASSES=$((PASSES+1)); else echo "  ✗ FAIL — $1"; FAILS=$((FAILS+1)); fi; }
assert "exits 0 on warnings-only run" "[ $AGENT_RC -eq 0 ]"
assert "result=PASS in JSON" "echo '$JSON' | grep -q '\"result\".*\"PASS\"'"
assert "skill_warn=3 in JSON" "echo '$JSON' | grep -q '\"skill_warn\".*\"3\"'"
assert "skill_pass=1 in JSON" "echo '$JSON' | grep -q '\"skill_pass\".*\"1\"'"
assert "skill_fail=0 in JSON" "echo '$JSON' | grep -q '\"skill_fail\".*\"0\"'"
assert "checks_passed in JSON" "echo '$JSON' | grep -q '\"checks_passed\"'"
echo ""
echo "═══ U122 test: $PASSES passed | $FAILS failed ═══"
[ $FAILS -eq 0 ] && exit 0 || exit 1
