#!/usr/bin/env bash
# verify-telegram-delivery.sh -- cross-check that the messageIds captured by
# send-telegram-celebration.sh are ACTUALLY present in the gateway sent-registry.
#
# WHY (anti-faking, the load-bearing layer):
#   `openclaw message send` can exit 0 -- and even hand back a messageId -- while
#   the message never truly lands (silent Telegram-offset-corruption; fresh-VPS
#   "scope upgrade pending approval"). The single ground-truth the gateway keeps
#   is its sent-registry:
#       agents/main/sessions/sessions.json.telegram-sent-messages.json
#   a map  { "<chatId>": { "<messageId>": <ts-ms>, ... }, ... }.
#   A messageId we sent seconds/minutes ago MUST appear under the owner's chatId
#   there. This script requires that for EVERY required deliverable. No "done"
#   is allowed until each required messageId is confirmed present.
#
# ROLLING-WINDOW / AGING:
#   The registry is a rolling window the gateway trims over time, so an id sent
#   a while ago can age out legitimately. We therefore (a) only HARD-FAIL on a
#   required id that is missing AND recent (younger than ZHC_TG_REGISTRY_TTL_SEC,
#   default 86400s); (b) treat a missing-but-old id as "aged-out" (pass with a
#   note) rather than a delivery failure -- it was confirmed at send time and the
#   registry simply rotated. Recent missing ids are real failures.
#
# REQUIRED DELIVERABLES (default): slots 1, 6, 7 -- the three text messages that
#   MUST land for a usable closeout (announcement + Command Center URL + bookmark
#   hint). Media slots (2/3/4) and the Notion slot (5) are conditional (skipped
#   when their URL is missing) so they are verified-if-present but not required.
#   Override with ZHC_TG_REQUIRED_SLOTS="1,6,7".
#
# EXIT CODES:
#   0  -> all required messageIds confirmed present (or legitimately aged out)
#   3  -> one or more required messageIds MISSING from the registry (real fail)
#   4  -> a required slot has no captured messageId at all (send never confirmed)
#   7  -> environment error (no state / no jq / no registry file)
#
# Writes a per-id pass/fail breakdown into state.telegramDeliveryVerification.

set -u

if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  OC_ROOT=""
fi

# STATE_FILE / LOG_FILE / REGISTRY all accept env overrides so the smoke test
# (and any harness) can run against a temp fixture with no real .openclaw install.
STATE_FILE="${ZHC_STATE_FILE:-$OC_ROOT/workspace/.workforce-build-state.json}"
LOG_FILE="${ZHC_LOG_FILE:-$OC_ROOT/workspace/.zhc-closeout.log}"
# The gateway sent-registry. Allow override for tests.
REGISTRY="${ZHC_TG_REGISTRY:-$OC_ROOT/agents/main/sessions/sessions.json.telegram-sent-messages.json}"

if [[ -z "$OC_ROOT" && ( -z "${ZHC_STATE_FILE:-}" || -z "${ZHC_TG_REGISTRY:-}" ) ]]; then
  echo "[verify-telegram] no OpenClaw root and no ZHC_STATE_FILE/ZHC_TG_REGISTRY override" >&2
  exit 7
fi
TTL_SEC="${ZHC_TG_REGISTRY_TTL_SEC:-86400}"
REQUIRED_SLOTS="${ZHC_TG_REQUIRED_SLOTS:-1,6,7}"

log() {
  printf '%s [%-5s] step=verify-telegram %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" >> "$LOG_FILE" 2>/dev/null || true
  printf '%s [%-5s] step=verify-telegram %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2"
}

command -v jq >/dev/null 2>&1 || { log "ERROR" "jq not installed"; exit 7; }
[[ -f "$STATE_FILE" ]] || { log "ERROR" "no state file at $STATE_FILE"; exit 7; }

if [[ ! -f "$REGISTRY" ]]; then
  log "ERROR" "sent-registry not found at $REGISTRY -- cannot confirm any delivery"
  exit 7
fi

OWNER_CHAT=$(jq -r '.ownerChat // empty' "$STATE_FILE" 2>/dev/null)
if [[ -z "$OWNER_CHAT" || "$OWNER_CHAT" == "null" ]]; then
  log "ERROR" "ownerChat missing from state -- cannot resolve registry chat key"
  exit 7
fi

now_ms=$(( $(date -u +%s) * 1000 ))
ttl_ms=$(( TTL_SEC * 1000 ))

# registry_has <chatId> <messageId> -> prints the stored ts-ms, or empty.
registry_ts() {
  jq -r --arg c "$1" --arg m "$2" '(.[$c][$m] // empty) | tostring' "$REGISTRY" 2>/dev/null
}

# Per-slot results accumulate here as JSON objects for the state breakdown.
results_json="[]"
overall_rc=0
missing_recent=()
no_msgid=()

# Normalize the required-slot CSV into a bash array.
IFS=',' read -r -a REQ_ARR <<< "$REQUIRED_SLOTS"

# Verify EVERY captured deliverable (so we get a full breakdown), then judge
# pass/fail strictly on the REQUIRED slots.
captured_slots=$(jq -r '(.messagesDelivered // []) | map(.n) | unique | .[]' "$STATE_FILE" 2>/dev/null)

is_required() {
  local n="$1" r
  for r in "${REQ_ARR[@]}"; do [[ "$n" == "$r" ]] && return 0; done
  return 1
}

check_slot() {
  local n="$1"
  local mid status verdict reg_ts age_ms note req="no"
  mid=$(jq -r --argjson n "$n" '(.messagesDelivered // []) | map(select(.n == $n)) | (.[0].messageId // "")' "$STATE_FILE" 2>/dev/null)
  status=$(jq -r --argjson n "$n" '(.messagesDelivered // []) | map(select(.n == $n)) | (.[0].status // "")' "$STATE_FILE" 2>/dev/null)
  is_required "$n" && req="yes"

  if [[ -z "$mid" || "$mid" == "null" ]]; then
    # No captured messageId. Real problem only if this slot is required.
    if [[ "$req" == "yes" ]]; then
      verdict="fail-no-messageId"
      no_msgid+=("$n")
      overall_rc=4
    else
      verdict="skip-no-messageId-optional"
    fi
    note="${status:-no captured messageId}"
  else
    reg_ts=$(registry_ts "$OWNER_CHAT" "$mid")
    if [[ -n "$reg_ts" && "$reg_ts" != "null" ]]; then
      verdict="pass-present"
      note="present in registry (ts=$reg_ts)"
    else
      # Not in registry. Distinguish recent (real fail) vs aged-out (ok).
      local sent_iso sent_ms
      sent_iso=$(jq -r --argjson n "$n" '(.messagesDelivered // []) | map(select(.n == $n)) | (.[0].ts // "")' "$STATE_FILE" 2>/dev/null)
      # epoch of the send (best-effort); fall back to "recent" if unparseable.
      sent_ms=""
      if [[ -n "$sent_iso" ]]; then
        if date -u -d "$sent_iso" +%s >/dev/null 2>&1; then
          sent_ms=$(( $(date -u -d "$sent_iso" +%s) * 1000 ))           # GNU date (VPS)
        elif date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$sent_iso" +%s >/dev/null 2>&1; then
          sent_ms=$(( $(date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$sent_iso" +%s) * 1000 ))  # BSD date (Mac)
        fi
      fi
      age_ms=$(( now_ms - ${sent_ms:-0} ))
      if [[ -n "$sent_ms" && "$age_ms" -gt "$ttl_ms" ]]; then
        verdict="pass-aged-out"
        note="absent but sent ${age_ms}ms ago > TTL ${ttl_ms}ms (registry rotated; confirmed at send time)"
      else
        verdict="fail-missing-recent"
        note="absent from registry and recent (age=${age_ms}ms <= TTL ${ttl_ms}ms) -- delivery NOT confirmed"
        if [[ "$req" == "yes" ]]; then
          missing_recent+=("$n")
          [[ "$overall_rc" -lt 3 ]] && overall_rc=3
        fi
      fi
    fi
  fi

  log "INFO" "slot=$n required=$req messageId=${mid:-none} verdict=$verdict ($note)"
  results_json=$(printf '%s' "$results_json" | jq \
    --argjson n "$n" --arg mid "$mid" --arg v "$verdict" --arg req "$req" --arg note "$note" \
    '. + [{"n": $n, "messageId": $mid, "required": ($req == "yes"), "verdict": $v, "note": $note}]')
}

if [[ -z "$captured_slots" ]]; then
  log "ERROR" "no messagesDelivered captured at all -- nothing to verify"
fi

for n in $captured_slots; do
  check_slot "$n"
done

# Any REQUIRED slot that was never even attempted (no capture record) is a fail.
for r in "${REQ_ARR[@]}"; do
  if ! jq -e --argjson n "$r" '(.messagesDelivered // []) | any(.[]; .n == $n)' "$STATE_FILE" >/dev/null 2>&1; then
    log "ERROR" "required slot $r has NO delivery record at all -- cannot confirm"
    no_msgid+=("$r")
    overall_rc=4
    results_json=$(printf '%s' "$results_json" | jq \
      --argjson n "$r" '. + [{"n": $n, "messageId": "", "required": true, "verdict": "fail-no-record", "note": "required slot never attempted"}]')
  fi
done

verified_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
status_str="pass"
[[ "$overall_rc" -ne 0 ]] && status_str="fail"
tmp=$(mktemp)
jq \
  --arg status "$status_str" \
  --arg at "$verified_at" \
  --argjson rc "$overall_rc" \
  --argjson results "$results_json" \
  --arg required "$REQUIRED_SLOTS" \
  '.telegramDeliveryVerification = {
      "status": $status,
      "rc": $rc,
      "verifiedAt": $at,
      "requiredSlots": $required,
      "results": $results
   }' "$STATE_FILE" > "$tmp" && mv "$tmp" "$STATE_FILE" || rm -f "$tmp"

if [[ "$overall_rc" -eq 0 ]]; then
  log "INFO" "PASS -- every required messageId confirmed in sent-registry (required slots: $REQUIRED_SLOTS)"
else
  reason=""
  [[ "${#missing_recent[@]}" -gt 0 ]] && reason="missing-recent=$(IFS=,; echo "${missing_recent[*]}")"
  [[ "${#no_msgid[@]}" -gt 0 ]] && reason="${reason:+$reason; }no-messageId=$(IFS=,; echo "${no_msgid[*]}")"
  log "ERROR" "FAIL (rc=$overall_rc) -- $reason"
fi
exit "$overall_rc"
