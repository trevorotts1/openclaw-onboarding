#!/usr/bin/env bash
# qc-workflow-visual.test.sh - negative + positive fixture tests for
# qc-workflow-visual.sh (U-11 Part 4 truth-diagram enforcement).
#
# Proves the gate:
#   * PASSES a playbook whose recorded visual.json has a diagram.png that exists and
#     a structure_hash that matches the current playbook,
#   * FAILS when the recorded diagram.png is missing on disk,
#   * FAILS (STALE) when the playbook structure changed so the recorded hash no
#     longer matches,
#   * WARNS (not FAILS) when hero.png is absent (verdict stays PASS).
#
# The static-wiring layer runs against the real skill tree either way; these
# fixtures exercise the content branch.
#
# Exit 0 = all assertions pass; 1 = a failure.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GATE="$SCRIPT_DIR/qc-workflow-visual.sh"
ENGINE="$SKILL_ROOT/tools/playbook_engine.py"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); printf '  [PASS] %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$1"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

verdict_of() { bash "$GATE" --dir "$1" --json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin)['verdict'])" 2>/dev/null; }
exit_of()    { local rc=0; bash "$GATE" --dir "$1" >/dev/null 2>&1 || rc=$?; echo "$rc"; }
json_of()    { bash "$GATE" --dir "$1" --json 2>/dev/null; }

WF="$TMP/conversation-workflows"
mkdir -p "$WF"
PB="$WF/appt.md"
cat > "$PB" <<'EOF'
# Conversation Workflow: Appt

### Phase 1 - Qualify
tools: reference_documents, update_tags
Qualify.

### Phase 2 - Close
tools: book_appointment, check_availability
Close.

## On success
Book the appointment and confirm.

## On escalation
Escalate to the operator.
EOF

# Record a CURRENT visual (diagram.png + hero.png exist, hash matches).
mkdir -p "$WF/appt"
printf 'PNGDATA' > "$WF/appt/diagram.png"
printf 'PNGDATA' > "$WF/appt/hero.png"
H="$(python3 "$ENGINE" hash "$PB" 2>/dev/null | tr -d '[:space:]')"
python3 - "$WF/appt/visual.json" "$H" "$WF/appt/diagram.png" "$WF/appt/hero.png" <<'PY'
import json, sys
path, h, png, hero = sys.argv[1:5]
json.dump({"workflow_id":"appt","structure_hash":h,"model_id":"mock-gpt-image",
           "diagram_mmd":"appt/diagram.mmd","diagram_png":png,"hero_png":hero,
           "hero_status":"present","hosted_urls":{"diagram":None,"hero":None},
           "generated_at":"2026-07-05T00:00:00Z"}, open(path,"w"), indent=2)
PY

# --- POSITIVE: current visual -> PASS, exit 0. --------------------------------
[ "$(verdict_of "$WF")" = "PASS" ] && ok "current visual: verdict PASS" || bad "current visual: expected PASS"
[ "$(exit_of "$WF")" = "0" ] && ok "current visual: exit 0" || bad "current visual: expected exit 0"

# --- NEGATIVE 1: missing diagram.png -> FAIL. ---------------------------------
rm -f "$WF/appt/diagram.png"
[ "$(verdict_of "$WF")" = "FAIL" ] && ok "missing diagram.png: verdict FAIL" || bad "missing diagram.png: expected FAIL"
[ "$(exit_of "$WF")" = "1" ] && ok "missing diagram.png: exit 1" || bad "missing diagram.png: expected exit 1"
printf '%s' "$(json_of "$WF")" | grep -q "diagram.png missing" && ok "missing diagram.png: flagged" || bad "missing diagram.png: not flagged"
printf 'PNGDATA' > "$WF/appt/diagram.png"   # restore

# --- NEGATIVE 2: structure changed -> STALE -> FAIL. --------------------------
cat >> "$PB" <<'EOF'

### Phase 3 - Followup
tools: update_tags
Follow up.
EOF
[ "$(verdict_of "$WF")" = "FAIL" ] && ok "stale hash: verdict FAIL" || bad "stale hash: expected FAIL"
printf '%s' "$(json_of "$WF")" | grep -qi "STALE" && ok "stale hash: flagged STALE" || bad "stale hash: not flagged STALE"

# Re-record the hash to current so the playbook is fresh again for the WARN test.
H2="$(python3 "$ENGINE" hash "$PB" 2>/dev/null | tr -d '[:space:]')"
python3 - "$WF/appt/visual.json" "$H2" "$WF/appt/diagram.png" <<'PY'
import json, sys
path, h, png = sys.argv[1:4]
json.dump({"workflow_id":"appt","structure_hash":h,"model_id":"mock-gpt-image",
           "diagram_mmd":"appt/diagram.mmd","diagram_png":png,"hero_png":None,
           "hero_status":"pending","hosted_urls":{"diagram":None,"hero":None},
           "generated_at":"2026-07-05T00:00:00Z"}, open(path,"w"), indent=2)
PY
rm -f "$WF/appt/hero.png"

# --- WARN: missing hero.png -> still PASS, warning present. -------------------
[ "$(verdict_of "$WF")" = "PASS" ] && ok "missing hero.png: verdict still PASS" || bad "missing hero.png: expected PASS"
printf '%s' "$(json_of "$WF")" | grep -qi "hero.png absent" && ok "missing hero.png: WARN emitted" || bad "missing hero.png: no WARN"

echo ""
echo "qc-workflow-visual tests: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
