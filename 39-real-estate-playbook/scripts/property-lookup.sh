#!/usr/bin/env bash
# property-lookup.sh — Skill 39 (Real Estate Playbook)
#
# RUNTIME WORKER (not a numbered install step). Renamed from 03-property-lookup.sh
# so it no longer collides with the install step 03-init-real-estate-events-log.sh.
#
# Runtime property-intelligence worker. Given an address (and optional ZIP), it:
#   1. Normalizes the address (USPS-style component split — heuristic, no key needed)
#   2. Resolves the best AVAILABLE provider for each capability from the
#      provider-status JSON written by 02-configure-providers.sh
#   3. For each capability that is AVAILABLE, prints the exact provider request
#      shape the agent should issue (the agent performs the network call through
#      its configured tool/MCP — this script does NOT call out)
#   4. For each capability that is an HONEST GAP, prints the verbatim honest-gap
#      line the agent must say to the operator/lead (NEVER fabricated data)
#   5. APPENDS one F52-contract event to <MASTER_FILES_DIR>/real-estate-events.jsonl
#
# WHY this shape: property data must be VERIFIABLE. The skill refuses to invent a
# price, a bed/bath count, a comp, or an owner. If the provider for a capability
# is not configured, the answer is an explicit "I don't have a live data source
# for X" — the operator can then add the key (02-configure-providers.sh).
#
# Idempotent (the event log is append-only by design; re-running logs a new
# query event, which is correct — each lookup IS an event). set -uo pipefail.
#
# Usage:
#   property-lookup.sh --address "123 Main St, Springfield, IL 62701"
#   property-lookup.sh --address "..." --want comps,street_view
#   property-lookup.sh --address "..." --json
#   property-lookup.sh --address "..." --no-log   (skip the F52 event append)

set -uo pipefail

# Resolve MASTER_FILES_DIR via the SAME persisted single-source-of-truth resolver
# lib-re-events.sh uses — NEVER a $HOME/Downloads (or /data) fallback that would
# split-brain the event log across callers with different HOMEs. Loud-fail when it
# cannot be resolved (FIX-XC-10 class). Sourcing lib-re-events.sh is safe: its
# direct-invocation dispatch is guarded by BASH_SOURCE==$0.
_SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck source=/dev/null
[ -f "$_SELF_DIR/lib-re-events.sh" ] && . "$_SELF_DIR/lib-re-events.sh"

if command -v re_events_master_dir >/dev/null 2>&1; then
  if ! MFD="$(re_events_master_dir)"; then
    echo "ERROR: MASTER_FILES_DIR unresolved — set MASTER_FILES_DIR or run 01-locate-master-files-folder.sh first (refusing to fall back to Downloads)." >&2
    exit 2
  fi
else
  MFD="${MASTER_FILES_DIR:-}"
  if [ -z "$MFD" ] || [ ! -d "$MFD" ]; then
    echo "ERROR: MASTER_FILES_DIR unresolved and lib-re-events.sh resolver unavailable." >&2
    exit 2
  fi
fi
STATUS="$MFD/.skill-39-provider-status.json"
EVENTS="$MFD/real-estate-events.jsonl"

ADDRESS=""
WANT="property_lookup,geocode,street_view,comps"
JSON=0
DO_LOG=1

while [ $# -gt 0 ]; do
  case "$1" in
    --address) ADDRESS="$2"; shift 2 ;;
    --want)    WANT="$2"; shift 2 ;;
    --json)    JSON=1; shift ;;
    --no-log)  DO_LOG=0; shift ;;
    -h|--help) sed -n '1,40p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$ADDRESS" ]; then
  echo "ERROR: --address is required" >&2
  exit 2
fi

# ---------- 1. Address normalization (heuristic; no key required) ----------
# Split "street, city, ST ZIP" — best-effort, never fabricates missing parts.
norm_street=""; norm_city=""; norm_state=""; norm_zip=""
IFS=',' read -ra _parts <<< "$ADDRESS"
[ "${#_parts[@]}" -ge 1 ] && norm_street="$(echo "${_parts[0]}" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"
[ "${#_parts[@]}" -ge 2 ] && norm_city="$(echo "${_parts[1]}" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"
if [ "${#_parts[@]}" -ge 3 ]; then
  tail_part="$(echo "${_parts[2]}" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"
  norm_state="$(echo "$tail_part" | grep -oE '\b[A-Za-z]{2}\b' | head -1 | tr '[:lower:]' '[:upper:]')"
  norm_zip="$(echo "$tail_part" | grep -oE '\b[0-9]{5}(-[0-9]{4})?\b' | head -1)"
fi
[ -z "$norm_zip" ] && norm_zip="$(echo "$ADDRESS" | grep -oE '\b[0-9]{5}(-[0-9]{4})?\b' | head -1)"

echo "=== [skill 39] property lookup ==="
echo "  input:      $ADDRESS"
echo "  normalized: street='$norm_street' city='$norm_city' state='$norm_state' zip='$norm_zip'"
echo ""

# ---------- 2. Provider resolution ----------
cap_state() {  # cap_state capname -> AVAILABLE|HONEST_GAP (reads status JSON, no jq dep)
  local cap="$1"
  [ -f "$STATUS" ] || { echo "HONEST_GAP"; return 0; }
  # pull the "state" that follows "<cap>":{ ... "state":"X"
  local seg; seg="$(tr -d '\n' < "$STATUS" | grep -oE "\"$cap\"[[:space:]]*:[[:space:]]*\{[^}]*\}" | head -1)"
  if echo "$seg" | grep -q '"state"[[:space:]]*:[[:space:]]*"AVAILABLE"'; then echo "AVAILABLE"; else echo "HONEST_GAP"; fi
}

declare -a RESULTS=()
gap_count=0; avail_count=0

IFS=',' read -ra WANTS <<< "$WANT"
for cap in "${WANTS[@]}"; do
  cap="$(echo "$cap" | tr -d '[:space:]')"
  [ -z "$cap" ] && continue
  st="$(cap_state "$cap")"
  if [ "$st" = "AVAILABLE" ]; then
    avail_count=$((avail_count+1))
    echo "  [$cap] AVAILABLE — issue the provider request (see references/property-providers.md → $cap)."
    RESULTS+=("\"$cap\":\"AVAILABLE\"")
  else
    gap_count=$((gap_count+1))
    echo "  [$cap] HONEST GAP — say to the lead/operator, verbatim:"
    echo "      \"I don't have a live data source connected for $cap on this property."
    echo "       I will not guess. Add a provider key (02-configure-providers.sh) and I'll pull it.\""
    RESULTS+=("\"$cap\":\"HONEST_GAP\"")
  fi
done

# JSON-escape a string and ALWAYS emit a quoted value (works on empty strings).
jq_str() {
  local s="$1"
  s="${s//\\/\\\\}"   # backslash first
  s="${s//\"/\\\"}"   # then double-quote
  printf '"%s"' "$s"
}

# ---------- 3. F52 event append ----------
if [ "$DO_LOG" -eq 1 ]; then
  mkdir -p "$MFD" 2>/dev/null || true
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  results_json="$(IFS=,; echo "${RESULTS[*]}")"
  printf '{"ts":"%s","skill":"39-real-estate-playbook","event":"property_lookup","address":%s,"normalized":{"street":%s,"city":%s,"state":%s,"zip":%s},"capabilities":{%s},"available":%d,"honest_gaps":%d}\n' \
    "$ts" \
    "$(jq_str "$ADDRESS")" \
    "$(jq_str "$norm_street")" \
    "$(jq_str "$norm_city")" \
    "$(jq_str "$norm_state")" \
    "$(jq_str "$norm_zip")" \
    "$results_json" "$avail_count" "$gap_count" >> "$EVENTS"
  echo ""
  echo "  F52 event appended: $EVENTS"
fi

if [ "$JSON" -eq 1 ]; then
  printf '{"address":%s,"available":%d,"honest_gaps":%d}\n' \
    "$(jq_str "$ADDRESS")" "$avail_count" "$gap_count"
fi

exit 0
