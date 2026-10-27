#!/usr/bin/env bash
# qc-playbook-declares.test.sh - negative + positive fixture tests for
# qc-playbook-declares.sh (U-9 declares cross-validation + U-12 calendar ids).
#
# Proves the gate:
#   * PASSES a playbook whose declares block fully resolves (tools in phase lines,
#     exits in Exit rules, ZHC_ fields in crm-field-mappings, calendar ids in the
#     caf export, applies tags in the caf tags export),
#   * FAILS a playbook whose declares dangles (tool not in any phase, exit not in
#     Exit rules, ZHC_ field not in mappings, calendar id absent from the export,
#     applies tag absent from the tags export),
#   * names the tags it cannot verify when the tags export is missing,
#   * leaves a playbook with no tags-used block unaffected,
#   * WARNS (does not FAIL) a legacy playbook that carries no declares block.
#
# Exit 0 = all assertions pass; 1 = a failure.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$SCRIPT_DIR/qc-playbook-declares.sh"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); printf '  [PASS] %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$1"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Shared cross-file inputs.
CAL_EXPORT="$TMP/cal.json"
cat > "$CAL_EXPORT" <<'EOF'
{"calendars": [{"id": "CAL_REAL", "name": "Consultation"}]}
EOF
CRM="$TMP/crm-field-mappings.md"
cat > "$CRM" <<'EOF'
# CRM field mappings

| value captured | GHL field name | field id |
|---|---|---|
| Budget | ZHC_budget_range | abc123 |
EOF
TAGS_EXPORT="$TMP/tags.json"
cat > "$TAGS_EXPORT" <<'EOF'
{"tags": [{"id": "VIP", "name": "VIP"}]}
EOF

verdict_of() {
  bash "$GATE" --dir "$1" --calendars-export "$CAL_EXPORT" --tags-export "$TAGS_EXPORT" --crm-fields "$CRM" --json 2>/dev/null \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['verdict'])" 2>/dev/null
}
exit_of() {
  local rc=0
  bash "$GATE" --dir "$1" --calendars-export "$CAL_EXPORT" --tags-export "$TAGS_EXPORT" --crm-fields "$CRM" >/dev/null 2>&1 || rc=$?
  echo "$rc"
}
json_of() {
  bash "$GATE" --dir "$1" --calendars-export "$CAL_EXPORT" --tags-export "$TAGS_EXPORT" --crm-fields "$CRM" --json 2>/dev/null
}
# Deliberately supplies NO tags export: the unverifiable-tags path.
json_no_tags_of() {
  bash "$GATE" --dir "$1" --calendars-export "$CAL_EXPORT" --crm-fields "$CRM" --json 2>/dev/null
}

# --- GOOD fixture: every declared reference resolves -> PASS. -----------------
G="$TMP/good/conversation-workflows"
mkdir -p "$G"
cat > "$G/qualify.md" <<'EOF'
# Conversation Workflow: Qualify

model-tier: realtime-standard

declares
tools-used: book_appointment, update_tags
exits-used: talk-to-human
fields-used: contact.email, ZHC_budget_range
calendars: default: CAL_REAL, on-site estimate: if ZHC-service-area-confirmed then CAL_REAL else CAL_REAL

## What the agent does

### Phase 1 - Qualify
tools: update_tags, reference_documents
Qualify the lead.

### Phase 4 - Close
tools: book_appointment, update_tags, reference_documents
Close.

## Exit rules

exit-when-tag: talk-to-human, action: handoff

## On success
Booked.

## On escalation
Escalate.
EOF

[ "$(verdict_of "$G")" = "PASS" ] && ok "good fixture: verdict PASS" || bad "good fixture: expected PASS"
[ "$(exit_of "$G")" = "0" ] && ok "good fixture: exit 0" || bad "good fixture: expected exit 0"

# --- BAD fixture: four dangling declares references -> FAIL. ------------------
B="$TMP/bad/conversation-workflows"
mkdir -p "$B"
cat > "$B/rogue.md" <<'EOF'
# Conversation Workflow: Rogue

declares
tools-used: book_appointment, send_invoice
exits-used: ghost-tag
fields-used: ZHC_missing_field
calendars: default: CAL_REAL, estimate: CAL_MISSING

## What the agent does

### Phase 1 - Qualify
tools: update_tags, reference_documents
Qualify.

## Exit rules

exit-when-tag: talk-to-human, action: handoff

## On success
Win.

## On escalation
Escalate.
EOF

[ "$(verdict_of "$B")" = "FAIL" ] && ok "bad fixture: verdict FAIL" || bad "bad fixture: expected FAIL"
[ "$(exit_of "$B")" = "1" ] && ok "bad fixture: exit 1" || bad "bad fixture: expected exit 1"

BJSON="$(json_of "$B")"
printf '%s' "$BJSON" | grep -q "does not appear in any phase tools line" && ok "bad fixture: flags dangling tool" || bad "bad fixture: did not flag dangling tool"
printf '%s' "$BJSON" | grep -q "ghost-tag" && ok "bad fixture: flags dangling exit" || bad "bad fixture: did not flag dangling exit"
printf '%s' "$BJSON" | grep -q "ZHC_missing_field" && ok "bad fixture: flags missing CRM field" || bad "bad fixture: did not flag missing CRM field"
printf '%s' "$BJSON" | grep -q "CAL_MISSING" && ok "bad fixture: flags absent calendar id" || bad "bad fixture: did not flag absent calendar id"

# --- TAGS-USED: compliant block passes. -------------------------------------
# 'webinar-registered (reads)' is deliberately absent from the tags export: the
# protocol says reads tags are not membership-checked, so this must still pass.
TG="$TMP/tagsgood/conversation-workflows"
mkdir -p "$TG"
cat > "$TG/qualify.md" <<'EOF'
# Conversation Workflow: Tags Good

model-tier: realtime-standard

declares
tools-used: update_tags
exits-used: talk-to-human
tags-used: VIP (applies), webinar-registered (reads)

## What the agent does

### Phase 1 - Qualify
tools: update_tags
Qualify.

## Exit rules

exit-when-tag: talk-to-human, action: handoff

## On success
Win.

## On escalation
Escalate.
EOF

[ "$(verdict_of "$TG")" = "PASS" ] && ok "tags-used compliant: verdict PASS" || bad "tags-used compliant: expected PASS"
TGJSON="$(json_of "$TG")"
printf '%s' "$TGJSON" | python3 -c "import json,sys; d=json.load(sys.stdin); print('TAGSFAIL' if any('tags-used' in f for f in d['failures']) else 'CLEAN')" 2>/dev/null | grep -q CLEAN && ok "tags-used compliant: no tags-used violation" || bad "tags-used compliant: emitted a tags-used violation"

# --- TAGS-USED: an applies tag that cannot be verified fails naming it. ------
TB="$TMP/tagsbad/conversation-workflows"
mkdir -p "$TB"
cat > "$TB/qualify.md" <<'EOF'
# Conversation Workflow: Tags Bad

model-tier: realtime-standard

declares
tools-used: update_tags
exits-used: talk-to-human
tags-used: GHOST-TAG (applies)

## What the agent does

### Phase 1 - Qualify
tools: update_tags
Qualify.

## Exit rules

exit-when-tag: talk-to-human, action: handoff

## On success
Win.

## On escalation
Escalate.
EOF

[ "$(verdict_of "$TB")" = "FAIL" ] && ok "tags-used unverifiable: verdict FAIL" || bad "tags-used unverifiable: expected FAIL"
[ "$(exit_of "$TB")" = "1" ] && ok "tags-used unverifiable: exit 1" || bad "tags-used unverifiable: expected exit 1"
TBJSON="$(json_of "$TB")"
printf '%s' "$TBJSON" | grep -q "absent from the caf tags export" && ok "tags-used unverifiable: names the violation" || bad "tags-used unverifiable: did not name the violation"
printf '%s' "$TBJSON" | grep -q "GHOST-TAG" && ok "tags-used unverifiable: names the tag" || bad "tags-used unverifiable: did not name the tag"

# --- TAGS-USED: a missing export fails and names what it could not verify. ---
TM="$TMP/tagsmissing/conversation-workflows"
mkdir -p "$TM"
cp "$TG/qualify.md" "$TM/qualify.md"
TMJSON="$(json_no_tags_of "$TM")"
printf '%s' "$TMJSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['verdict'])" 2>/dev/null | grep -q "^FAIL$" && ok "tags-used missing export: verdict FAIL" || bad "tags-used missing export: expected FAIL"
printf '%s' "$TMJSON" | grep -q "caf tags export is missing" && ok "tags-used missing export: names the missing export" || bad "tags-used missing export: did not name it"
printf '%s' "$TMJSON" | grep -q "cannot verify VIP" && ok "tags-used missing export: names the unverified tag" || bad "tags-used missing export: did not name the unverified tag"

# --- TAGS-USED: an entry with no mode is a defect naming the entry. ----------
TN="$TMP/tagsnomode/conversation-workflows"
mkdir -p "$TN"
sed 's/^tags-used: .*/tags-used: VIP/' "$TG/qualify.md" > "$TN/qualify.md"
TNJSON="$(json_of "$TN")"
printf '%s' "$TNJSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['verdict'])" 2>/dev/null | grep -q "^FAIL$" && ok "tags-used no mode: verdict FAIL" || bad "tags-used no mode: expected FAIL"
printf '%s' "$TNJSON" | grep -q "is not '<tag> (applies|reads)'" && ok "tags-used no mode: names the entry grammar" || bad "tags-used no mode: did not name the grammar"

# --- TAGS-USED: absent block leaves the playbook unaffected. -----------------
TA="$TMP/tagsabsent/conversation-workflows"
mkdir -p "$TA"
grep -v '^tags-used:' "$TG/qualify.md" > "$TA/qualify.md"
[ "$(verdict_of "$TA")" = "PASS" ] && ok "tags-used absent: verdict PASS" || bad "tags-used absent: expected PASS"
TAJSON="$(json_of "$TA")"
printf '%s' "$TAJSON" | python3 -c "import json,sys; d=json.load(sys.stdin); print('TAGSFAIL' if any('tags-used' in f for f in d['failures']) else 'CLEAN')" 2>/dev/null | grep -q CLEAN && ok "tags-used absent: no tags-used violation" || bad "tags-used absent: emitted a tags-used violation"

# --- LEGACY fixture: no declares block -> WARN, not FAIL. ---------------------
L="$TMP/legacy/conversation-workflows"
mkdir -p "$L"
cat > "$L/legacy.md" <<'EOF'
# Conversation Workflow: Legacy

## What the agent does

### Phase 1 - Qualify
tools: update_tags, reference_documents
Qualify.

## Exit rules

exit-when-tag: talk-to-human, action: handoff

## On success
Win.

## On escalation
Escalate.
EOF

# This fixture carries `### Phase 1`, so it is MODERN by the content rule, and
# the standard (communications-playbook-standard.md item (k)) makes the declares
# block mandatory for every playbook. The gate says so in its own message:
# "legacy WARN is for playbooks with neither" phases nor a model-tier line.
# The old PASS expectation here described a lenient policy the gate no longer
# implements, so it asserted a verdict that could never occur.
[ "$(verdict_of "$L")" = "FAIL" ] && ok "modern-without-declares: verdict FAIL" || bad "modern-without-declares: expected FAIL"
[ "$(exit_of "$L")" = "1" ] && ok "modern-without-declares: exit 1" || bad "modern-without-declares: expected exit 1"
LJSON="$(json_of "$L")"
printf '%s' "$LJSON" | grep -q "no declares block" && ok "modern-without-declares: names the missing declares block" || bad "modern-without-declares: did not name it"

# The true legacy path — neither phases nor a model-tier line — must be
# NEEDS-MIGRATION with exit 0: it never PASSes, but it must not hard-fail an
# install either. Previously untested in this suite.
LL="$TMP/truelegacy/conversation-workflows"
mkdir -p "$LL"
cat > "$LL/old.md" <<'EOF'
# Old Workflow

## What the agent does
Talk to the lead.

## On success
Win.
EOF
[ "$(verdict_of "$LL")" = "NEEDS-MIGRATION" ] && ok "true-legacy: verdict NEEDS-MIGRATION" || bad "true-legacy: expected NEEDS-MIGRATION"
[ "$(exit_of "$LL")" = "0" ] && ok "true-legacy: exit 0 (does not hard-fail install)" || bad "true-legacy: expected exit 0"

echo ""
echo "qc-playbook-declares tests: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
