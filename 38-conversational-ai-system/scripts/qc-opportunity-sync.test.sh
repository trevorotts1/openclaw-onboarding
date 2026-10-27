#!/usr/bin/env bash
# qc-opportunity-sync.test.sh - negative + positive fixture tests for
# qc-opportunity-sync.sh (U-13 pipeline stage-map validation).
#
# Proves the gate:
#   * PASSES a playbook whose stage-map names all exist in the declared pipeline,
#   * FAILS a playbook whose stage-map names a stage absent from the pipeline, and
#     a playbook whose declared pipeline id is absent from the caf export,
#   * treats a playbook with no pipeline/stage-map as inert (no failure),
#   * PASSES a fresh export and REJECTS a stale, undated, unparseable or
#     future-dated one, naming the file path and its age (freshness contract).
#
# Exit 0 = all assertions pass; 1 = a failure.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$SCRIPT_DIR/qc-opportunity-sync.sh"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); printf '  [PASS] %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$1"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ISO-8601 UTC timestamp N hours in the past (negative = future).
ts_ago() {
  python3 - "$1" <<'PY'
import sys
from datetime import datetime, timedelta, timezone
when = datetime.now(timezone.utc) - timedelta(hours=float(sys.argv[1]))
print(when.isoformat(timespec="seconds").replace("+00:00", "Z"))
PY
}

make_export() {
  # make_export <path> <exported_at JSON literal>
  cat > "$1" <<EOF
{"exported_at": $2, "pipelines": [{"id": "PIPE_A", "stages": [
  {"name": "New Lead"},
  {"name": "Qualified"},
  {"name": "Appointment Booked"},
  {"name": "Needs Human"}
]}]}
EOF
}

PIPE_EXPORT="$TMP/pipe-fresh.json"
make_export "$PIPE_EXPORT" "\"$(ts_ago 1)\""

FRESH_23H="$TMP/pipe-23h.json"
make_export "$FRESH_23H" "\"$(ts_ago 23)\""

STALE_EXPORT="$TMP/pipe-stale.json"
make_export "$STALE_EXPORT" "\"$(ts_ago 25)\""

ANCIENT_EXPORT="$TMP/pipe-ancient.json"
make_export "$ANCIENT_EXPORT" "\"2020-01-01T00:00:00Z\""

UNDATED_EXPORT="$TMP/pipe-undated.json"
# Exactly the fresh export minus its timestamp: only freshness can reject it.
python3 - "$PIPE_EXPORT" "$UNDATED_EXPORT" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
del data["exported_at"]
json.dump(data, open(sys.argv[2], "w", encoding="utf-8"))
PY

UNPARSEABLE_STAMP="$TMP/pipe-badstamp.json"
make_export "$UNPARSEABLE_STAMP" '"last tuesday"'

FUTURE_EXPORT="$TMP/pipe-future.json"
make_export "$FUTURE_EXPORT" "\"$(ts_ago -24)\""

verdict_of() {
  bash "$GATE" --dir "$1" --pipelines-export "${2:-$PIPE_EXPORT}" --json 2>/dev/null \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['verdict'])" 2>/dev/null
}
exit_of() {
  local rc=0
  bash "$GATE" --dir "$1" --pipelines-export "${2:-$PIPE_EXPORT}" >/dev/null 2>&1 || rc=$?
  echo "$rc"
}
json_of() {
  bash "$GATE" --dir "$1" --pipelines-export "${2:-$PIPE_EXPORT}" --json 2>/dev/null
}
# The gate's failure text only (not the echoed export path in the report header).
failures_of() {
  printf '%s' "$1" | python3 -c \
    'import json,sys; print("\n".join(json.load(sys.stdin).get("failures") or []))' 2>/dev/null
}

# --- GOOD fixture: every stage-map name is in the pipeline -> PASS. -----------
G="$TMP/good/conversation-workflows"
mkdir -p "$G"
cat > "$G/qualify.md" <<'EOF'
# Conversation Workflow: Qualify

declares
pipeline: PIPE_A
stage-map: phase 1: New Lead, phase 3: Qualified, win: Appointment Booked, exit talk-to-human: Needs Human

## What the agent does

### Phase 1 - Qualify
tools: update_tags, reference_documents
Qualify.

## Exit rules

exit-when-tag: talk-to-human, action: handoff

## On success
Booked.

## On escalation
Escalate.
EOF
# A playbook with no pipeline is inert and must not fail.
cat > "$G/inert.md" <<'EOF'
# Conversation Workflow: Inert

### Phase 1 - Chat
tools: reference_documents
Chat.

## On success
Done.
EOF

[ "$(verdict_of "$G")" = "PASS" ] && ok "good fixture: verdict PASS" || bad "good fixture: expected PASS"
[ "$(exit_of "$G")" = "0" ] && ok "good fixture: exit 0" || bad "good fixture: expected exit 0"

# --- FRESHNESS: a current export is current evidence -> PASS. ----------------
[ "$(verdict_of "$G" "$FRESH_23H")" = "PASS" ] \
  && ok "fresh export (23h old, inside the 24h limit): verdict PASS" \
  || bad "fresh export (23h old): expected PASS"
[ "$(exit_of "$G" "$FRESH_23H")" = "0" ] \
  && ok "fresh export (23h old): exit 0" \
  || bad "fresh export (23h old): expected exit 0"

# --- FRESHNESS: a stale export is rejected, naming path and age. -------------
SJSON="$(json_of "$G" "$STALE_EXPORT")"
SFAIL="$(failures_of "$SJSON")"
[ "$(verdict_of "$G" "$STALE_EXPORT")" = "FAIL" ] \
  && ok "stale export (25h old): verdict FAIL" \
  || bad "stale export (25h old): expected FAIL"
[ "$(exit_of "$G" "$STALE_EXPORT")" = "1" ] \
  && ok "stale export (25h old): exit 1" \
  || bad "stale export (25h old): expected exit 1"
printf '%s' "$SFAIL" | grep -q "EXPORT_STALE" \
  && ok "stale export: failure names EXPORT_STALE" \
  || bad "stale export: did not name EXPORT_STALE"
printf '%s' "$SFAIL" | grep -qF "$STALE_EXPORT" \
  && ok "stale export: failure text names the export file path" \
  || bad "stale export: failure text did not name the export path"
printf '%s' "$SFAIL" | grep -qE 'exported [0-9]+[dhm]' \
  && ok "stale export: failure reports the age" \
  || bad "stale export: did not report the age"
printf '%s' "$SFAIL" | grep -q "limit 24h" \
  && ok "stale export: failure reports the 24h limit" \
  || bad "stale export: did not report the limit"

# An export old enough that a deleted pipeline would still validate.
AJJSON="$(json_of "$G" "$ANCIENT_EXPORT")"
[ "$(verdict_of "$G" "$ANCIENT_EXPORT")" = "FAIL" ] \
  && ok "ancient export (2020): verdict FAIL" \
  || bad "ancient export (2020): expected FAIL"
printf '%s' "$AJJSON" | grep -qE 'exported [0-9]+d' \
  && ok "ancient export: failure reports an age in days" \
  || bad "ancient export: did not report a day-scale age"

# --- FRESHNESS: undated evidence is not current evidence. --------------------
UJSON="$(json_of "$G" "$UNDATED_EXPORT")"
UFAIL="$(failures_of "$UJSON")"
[ "$(verdict_of "$G" "$UNDATED_EXPORT")" = "FAIL" ] \
  && ok "export with no exported_at: verdict FAIL" \
  || bad "export with no exported_at: expected FAIL"
[ "$(exit_of "$G" "$UNDATED_EXPORT")" = "1" ] \
  && ok "export with no exported_at: exit 1" \
  || bad "export with no exported_at: expected exit 1"
printf '%s' "$UFAIL" | grep -q "EXPORT_UNDATED" \
  && ok "export with no exported_at: failure names EXPORT_UNDATED" \
  || bad "export with no exported_at: did not name EXPORT_UNDATED"
printf '%s' "$UFAIL" | grep -qF "$UNDATED_EXPORT" \
  && ok "export with no exported_at: failure text names the export file path" \
  || bad "export with no exported_at: failure text did not name the export path"

# --- FRESHNESS: an unparseable or future timestamp cannot be judged -> FAIL. --
BADSTAMP_JSON="$(json_of "$G" "$UNPARSEABLE_STAMP")"
FUTURE_JSON="$(json_of "$G" "$FUTURE_EXPORT")"
printf '%s' "$BADSTAMP_JSON" | grep -q "EXPORT_TIMESTAMP_UNPARSEABLE" \
  && ok "unparseable exported_at: rejected as EXPORT_TIMESTAMP_UNPARSEABLE" \
  || bad "unparseable exported_at: not rejected"
printf '%s' "$FUTURE_JSON" | grep -q "EXPORT_TIMESTAMP_IN_FUTURE" \
  && ok "future exported_at: rejected as EXPORT_TIMESTAMP_IN_FUTURE" \
  || bad "future exported_at: not rejected"

# --- DISCOVERY: a stale copy must not shadow a fresh copy. -------------------
verdict_discovered() {
  env -u CAF_PIPELINES_EXPORT bash "$GATE" --dir "$1" --json 2>/dev/null \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['verdict'])" 2>/dev/null
}
DISC_ROOT="$TMP/disc"
DISC_WF="$DISC_ROOT/conversation-workflows"
mkdir -p "$DISC_WF"
cp "$G/qualify.md" "$DISC_WF/"
cp "$STALE_EXPORT" "$DISC_ROOT/.caf-pipelines-export.json"
cp "$PIPE_EXPORT" "$DISC_WF/.caf-pipelines-export.json"

[ "$(verdict_discovered "$DISC_WF")" = "PASS" ] \
  && ok "discovery: a stale copy at the master-files level does not shadow a fresh one in the workflows dir" \
  || bad "discovery: stale copy shadowed the fresh export"

rm "$DISC_WF/.caf-pipelines-export.json"
DISC_JSON="$(env -u CAF_PIPELINES_EXPORT bash "$GATE" --dir "$DISC_WF" --json 2>/dev/null)"
[ "$(verdict_discovered "$DISC_WF")" = "FAIL" ] \
  && ok "discovery: only a stale export available -> FAIL" \
  || bad "discovery: expected FAIL with only a stale export"
printf '%s' "$(failures_of "$DISC_JSON")" | grep -qF "$DISC_ROOT/.caf-pipelines-export.json" \
  && ok "discovery: stale failure names the discovered export path" \
  || bad "discovery: stale failure did not name the discovered path"

# --- BAD fixture: bogus stage name + unknown pipeline -> FAIL. ----------------
B="$TMP/bad/conversation-workflows"
mkdir -p "$B"
cat > "$B/bogus-stage.md" <<'EOF'
# Conversation Workflow: Bogus Stage

declares
pipeline: PIPE_A
stage-map: phase 1: New Lead, win: Nonexistent Stage

## What the agent does

### Phase 1 - Qualify
tools: reference_documents
Qualify.

## On success
Win.
EOF
cat > "$B/unknown-pipeline.md" <<'EOF'
# Conversation Workflow: Unknown Pipeline

declares
pipeline: PIPE_GHOST
stage-map: phase 1: New Lead

## What the agent does

### Phase 1 - Qualify
tools: reference_documents
Qualify.

## On success
Win.
EOF

[ "$(verdict_of "$B")" = "FAIL" ] && ok "bad fixture: verdict FAIL" || bad "bad fixture: expected FAIL"
[ "$(exit_of "$B")" = "1" ] && ok "bad fixture: exit 1" || bad "bad fixture: expected exit 1"

BJSON="$(json_of "$B")"
printf '%s' "$BJSON" | grep -q "Nonexistent Stage" && ok "bad fixture: flags stage absent from pipeline" || bad "bad fixture: did not flag bogus stage"
printf '%s' "$BJSON" | grep -q "PIPE_GHOST" && ok "bad fixture: flags pipeline absent from export" || bad "bad fixture: did not flag unknown pipeline"

echo ""
echo "qc-opportunity-sync tests: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
