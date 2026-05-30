#!/usr/bin/env bash
# qc-feature-logs.sh — machine-enforce the F52 DATA CONTRACT for the Round-3
# Queue-A features (v1.5.0).
#
# WHAT IT ENFORCES
# ----------------
# Each new behavioral feature emits a JSONL log with timestamp + event_type +
# event data at a documented <MASTER_FILES_DIR> path, and the schema is
# documented (in the protocol + INSTRUCTIONS.md). This gate proves, statically:
#
#   1. Each feature's protocol documents its JSONL path AND a JSON example line
#      carrying BOTH "timestamp" and "event_type".
#   2. INSTRUCTIONS.md documents every JSONL path + its event_type (the data
#      contract is centralized there per the task).
#   3. The installer (25-seed-round3-feature-files.sh) seeds every JSONL sink.
#   4. PII GUARD: no protocol's JSONL example line may carry a RAW customer-value
#      key (value_written / "value" / field_value / raw_value). The structured
#      logs record field NAME/ID + metadata only — the raw value is PII and must
#      stay out of the contract (lives in GHL + the conversation log). This is a
#      hard FAIL — it would have caught the F46 value_written leak.
#
# The five logs + their protocols + event_types:
#   aggression-detection-log.jsonl  aggression-detection-protocol.md      aggression_detected/tension_detected
#   interrupt-log.jsonl             smart-playbook-switching-protocol.md  interrupt_detour
#   geo-qualification-log.jsonl     geo-qualification-protocol.md         geo_qualification
#   crm-field-writes-log.jsonl      crm-field-write-protocol.md           crm_field_write
#   faq-detour-log.jsonl            smart-faq-tool-protocol.md            faq_answered
#
# Pure BASH (grep/sed) — respects qc-static's ban on claude-/anthropic strings in
# .py. bash -n clean. set -uo pipefail.
#
# Exit 0 = clean; 1 = a data-contract violation.
#
# Usage:
#   bash scripts/qc-feature-logs.sh
#   bash scripts/qc-feature-logs.sh --skill-dir /path/to/38-conversational-ai-system

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    -h|--help) sed -n '1,40p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

FAIL=0
INSTR="$SKILL_DIR/INSTRUCTIONS.md"
INSTALLER="$SKILL_DIR/scripts/25-seed-round3-feature-files.sh"

echo "=== qc-feature-logs: F52 JSONL data-contract guard ==="
echo "skill_dir : $SKILL_DIR"
echo ""

# rows: "jsonl|protocol|event_type_substring"
ROWS=(
  "aggression-detection-log.jsonl|aggression-detection-protocol.md|aggression_detected"
  "interrupt-log.jsonl|smart-playbook-switching-protocol.md|interrupt_detour"
  "geo-qualification-log.jsonl|geo-qualification-protocol.md|geo_qualification"
  "crm-field-writes-log.jsonl|crm-field-write-protocol.md|crm_field_write"
  "faq-detour-log.jsonl|smart-faq-tool-protocol.md|faq_answered"
)

for row in "${ROWS[@]}"; do
  IFS='|' read -r jsonl proto evt <<< "$row"
  proto_path="$SKILL_DIR/protocols/$proto"

  # 1. Protocol exists, names the JSONL path, has a JSON example with timestamp + event_type.
  if [ ! -f "$proto_path" ]; then
    echo "  [FAIL] missing protocol: protocols/$proto"
    FAIL=1
  else
    if ! grep -qF "$jsonl" "$proto_path"; then
      echo "  [FAIL] protocols/$proto does not document its JSONL path ($jsonl)"
      FAIL=1
    fi
    # An example JSON object line carrying both "timestamp" and "event_type".
    if grep -E '"timestamp"' "$proto_path" | grep -q '"event_type"'; then
      echo "  [PASS] protocols/$proto documents $jsonl with a timestamp+event_type JSONL example"
    else
      echo "  [FAIL] protocols/$proto JSONL example missing \"timestamp\" and/or \"event_type\" on one line"
      FAIL=1
    fi
    if ! grep -qF "$evt" "$proto_path"; then
      echo "  [FAIL] protocols/$proto JSONL example missing event_type value \"$evt\""
      FAIL=1
    fi
  fi

  # 2. INSTRUCTIONS.md documents the path + event_type (centralized data contract).
  if [ -f "$INSTR" ]; then
    if grep -qF "$jsonl" "$INSTR" && grep -qF "$evt" "$INSTR"; then
      : # ok
    else
      echo "  [FAIL] INSTRUCTIONS.md does not document the data contract for $jsonl (path + event_type \"$evt\")"
      FAIL=1
    fi
  else
    echo "  [FAIL] INSTRUCTIONS.md not found"
    FAIL=1
  fi

  # 3. Installer seeds the JSONL sink.
  if [ -f "$INSTALLER" ]; then
    if grep -qF "$jsonl" "$INSTALLER"; then
      : # ok
    else
      echo "  [FAIL] 25-seed-round3-feature-files.sh does not seed $jsonl"
      FAIL=1
    fi
  else
    echo "  [FAIL] scripts/25-seed-round3-feature-files.sh not found"
    FAIL=1
  fi

  # 4. PII guard — no JSONL example line in the protocol may carry a RAW
  #    customer-value key. The contract is field NAME/ID + metadata only; the
  #    raw value is PII (lives in GHL + the conversation log, never the log).
  if [ -f "$proto_path" ]; then
    # only inspect lines that ARE JSONL examples (timestamp + event_type present)
    if grep -E '"timestamp"' "$proto_path" \
         | grep '"event_type"' \
         | grep -Eq '"(value_written|value|field_value|raw_value)"[[:space:]]*:'; then
      echo "  [FAIL] protocols/$proto JSONL example leaks a RAW customer value (value_written/\"value\"/field_value/raw_value) — PII must stay out of the structured log (field NAME/ID + metadata only)"
      FAIL=1
    else
      echo "  [PASS] protocols/$proto JSONL example is PII-free (no raw-value key)"
    fi
  fi
done

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS — all five Round-3 feature logs are JSONL with timestamp+event_type, documented in their protocol + INSTRUCTIONS.md, and seeded by the installer."
  exit 0
else
  echo "RESULT: FAIL — an F52 data-contract item is missing. See above."
  exit 1
fi
