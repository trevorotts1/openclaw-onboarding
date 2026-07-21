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
#
# CAPABILITY NAMES (provider-status/v1, references/provider-status-contract.md):
#   geocode · property_lookup · street_view · comps
#   `lookup` and `streetview` are RETIRED names and are rejected by the validator.
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
# T2-32: the status artifact is governed by references/provider-status-contract.md
# (`provider-status/v1`) and validated by validate-provider-status.sh, which
# 02-configure-providers.sh also runs after writing. Validate BEFORE reading —
# a missing or non-conforming artifact must be REPORTED, never silently
# collapsed into "every capability is an honest gap". Those are different
# problems and must not produce the same message.
VALIDATOR="$_SELF_DIR/validate-provider-status.sh"
STATUS_USABLE=0
if [ ! -f "$VALIDATOR" ]; then
  echo "ERROR: validate-provider-status.sh not found beside this script — cannot verify the provider-status contract." >&2
  echo "       Refusing to guess at provider availability." >&2
  exit 2
fi
bash "$VALIDATOR" "$STATUS" --quiet
case "$?" in
  0) STATUS_USABLE=1 ;;
  1) # PRESENT but NON-CONFORMING. This cannot arise from the shipped producer,
     # which validates before reporting success, so it means the artifact was
     # hand-edited or written by something else. Refuse it — reading a
     # non-conforming contract artifact is how the three-axis mismatch happened.
     echo "ERROR: '$STATUS' does not conform to provider-status/v1." >&2
     echo "       Detail: bash $VALIDATOR '$STATUS'" >&2
     echo "       Re-run 02-configure-providers.sh. NOT treating this as 'no providers configured'." >&2
     exit 2 ;;
  *) # ABSENT. Report it LOUDLY and name the real cause, then continue with
     # every capability as an honest gap. It stays non-fatal because that is
     # today's behaviour for an unconfigured box and this item must not turn a
     # working box into a failing one — but it is no longer SILENT, which is the
     # actual defect: "the operator configured nothing" and "this skill cannot
     # find its own status file" used to produce the identical message.
     echo "WARNING: no provider-status file at '$STATUS'." >&2
     echo "         Every capability below is reported as an HONEST GAP because the" >&2
     echo "         status file is MISSING — not because a provider was checked and" >&2
     echo "         found unconfigured. Run 02-configure-providers.sh to fix this." >&2
     STATUS_USABLE=0 ;;
esac

cap_state() {  # cap_state <contract capability name> -> AVAILABLE|HONEST_GAP
  local cap="$1"
  [ "$STATUS_USABLE" -eq 1 ] || { echo "HONEST_GAP"; return 0; }
  # The artifact has already been validated against the contract, so the shape
  # below is guaranteed: capabilities.<cap>.state is exactly AVAILABLE or
  # HONEST_GAP. Capability names are the contract's four and no others.
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
    if [ "$cap" = "street_view" ]; then
      # T1-07: never send the agent to prose for the Street View request shape.
      # The shipped function keeps the key in-process and returns a LOCAL PATH;
      # a hand-built URL would carry the raw key into the conversation and the
      # event log, which is exactly what lib-property.sh:143-148 removed.
      echo "  [$cap] AVAILABLE — call streetview() in scripts/lib-property.sh and attach the returned image_path."
      echo "      NEVER construct a maps.googleapis.com URL, and never emit the key."
    else
      echo "  [$cap] AVAILABLE — issue the provider request (see references/property-providers.md → $cap)."
    fi
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
# SK1-20: the F52 log is PII-FREE by contract (see
# templates/real-estate-events.schema.json → "NEVER raw property PII"). We do
# NOT persist the raw street address or the street component. Instead we log an
# opaque, stable address_hash (sha256 of the lower-cased input) so repeat
# lookups still correlate/dedupe, plus the coarse city/state/zip (shared by many
# properties, not personally identifying). qc-no-personal-data.sh fails the build
# if this emitter is ever changed back to persisting a raw address/street.
addr_hash() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' \
    | (shasum -a 256 2>/dev/null || sha256sum) | awk '{print $1}'
}
# SK1-30 / T0-49: the event used to be written by a bare `>> "$EVENTS"`
# redirection and then ANNOUNCED unconditionally — a failed append (unwritable
# log, full disk, read-only mount) printed "F52 event appended" and the script
# still exited 0. The checked helper that returns non-zero on a failed append
# already existed at lib-re-events.sh:re_event and was simply not used here.
# The lookup now routes through it, prints the appended line ONLY in the success
# branch, and exits non-zero when the append fails.
if [ "$DO_LOG" -eq 1 ]; then
  mkdir -p "$MFD" 2>/dev/null || true
  results_json="$(IFS=,; echo "${RESULTS[*]}")"
  a_hash="$(addr_hash "$ADDRESS")"
  payload="$(printf '{"address_hash":"%s","normalized":{"city":%s,"state":%s,"zip":%s},"capabilities":{%s},"available":%d,"honest_gaps":%d}' \
    "$a_hash" \
    "$(jq_str "$norm_city")" \
    "$(jq_str "$norm_state")" \
    "$(jq_str "$norm_zip")" \
    "$results_json" "$avail_count" "$gap_count")"
  if command -v re_event >/dev/null 2>&1; then
    if MASTER_FILES_DIR="$MFD" re_event property_lookup "$payload"; then
      echo ""
      echo "  F52 event appended: $EVENTS (address recorded as opaque hash; no raw PII)"
    else
      echo "" >&2
      echo "ERROR: the F52 property_lookup event could NOT be appended to $EVENTS." >&2
      echo "       The event log is the operator's ground truth for this skill; refusing to" >&2
      echo "       report a completed lookup that was never recorded. (Use --no-log only when" >&2
      echo "       you deliberately do not want the lookup audited.)" >&2
      exit 3
    fi
  else
    echo "ERROR: lib-re-events.sh (re_event) unavailable — cannot append the F52 event." >&2
    exit 3
  fi
fi

if [ "$JSON" -eq 1 ]; then
  # SK1-20: the machine-readable summary is also PII-free — report the opaque
  # address_hash, never the raw address (a downstream tool may persist stdout).
  printf '{"address_hash":"%s","available":%d,"honest_gaps":%d}\n' \
    "$(addr_hash "$ADDRESS")" "$avail_count" "$gap_count"
fi

exit 0
