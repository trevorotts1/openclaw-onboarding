#!/usr/bin/env bash
# tests/rescue/RR-030/test_receipt_noop.sh   (RR plan fix F63)
#
# A 2xx JSON answer {recorded:false, reason: already_terminal | unknown_instruction}
# carrying THIS operation's receipt means the server recorded nothing. The box must stop
# resending (pending ack removed) but must NOT call it a delivery: journal phase
# ack_settled_noop, never ack_confirmed.
#   N1  main ack path, already_terminal   -> ack_settled_noop, pending removed
#   N2  main ack path, unknown_instruction -> ack_settled_noop, pending removed
#   N3  resend path (_resend_pending)     -> ack_settled_noop, pending removed
#   N4  recorded:false + OTHER reason (row_write_missed) -> stays UNCONFIRMED, pending kept
#   N5  recorded:false + right reason but receipt for a DIFFERENT operation -> UNCONFIRMED
#   N6  recorded:false + right reason but NO receipt -> UNCONFIRMED
#   N7  control: a real delivery receipt (recorded:true + state_revision) -> ack_confirmed
#   N8  gc_journal reaps an old ack_settled_noop record, keeps an old ack_pending one
# Drives the REAL shipped functions (extracted by name from rescue-poll.sh) against a stub curl.
# Offline: synthetic box slug/token, unroutable URL.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
POLL="$REPO/65-rescue-receiver/rescue-poll.sh"
[ -f "$POLL" ] || { echo "FATAL: $POLL missing"; exit 2; }
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok   $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1 ${2:-}"; }
FIX="$(mktemp -d "${TMPDIR:-/tmp}/rr030-noop-XXXXXX")"; trap 'rm -rf "$FIX"' EXIT
mkdir -p "$FIX/bin" "$FIX/state/tmp" "$FIX/logs"
export RR_FAKE_SCENARIO="$FIX/scenario" RR_FAKE_COUNT="$FIX/count" RR_FIX_LOG="$FIX/logs/poll.log" RR_FIX_LASTBODY="$FIX/last-post-body"

extract_fn() { # extract_fn <name>  (name-anchored, first definition)
  local s e
  s="$(grep -n "^$1()" "$POLL" | head -1 | cut -d: -f1)"; [ -n "$s" ] || return 1
  e="$(awk -v s="$s" 'NR>=s && /^}/ {print NR; exit}' "$POLL")"; [ -n "$e" ] || return 1
  sed -n "${s},${e}p" "$POLL"
}
# function names carry a leading underscore in the shipped file; list them without typing it twice
FNS="json_str json_field json_get json_type post_class sha rr_hash now_iso op_id_for journal_put journal_phase pending_put receipt_match ack_send resend_pending gc_journal post ack write_done reack_cached"
{
  for fn in $FNS; do extract_fn "_$fn" || echo "echo 'EXTRACT FAILED: _$fn' >&2"; echo; done
  echo '_log() { printf "%s\n" "$1" >> "$RR_FIX_LOG"; printf "%s\n" "$1"; }'
  echo ': "${_JOURNAL:=$_STATE/journal}"; : "${_PENDING:=$_STATE/ack-pending}"; : "${_RECONCILE:=$_STATE/reconcile}"'
  echo 'mkdir -p "$_JOURNAL" "$_PENDING" 2>/dev/null || true; chmod 700 "$_JOURNAL" "$_PENDING" 2>/dev/null || true'
} > "$FIX/funcs.sh"
bash -n "$FIX/funcs.sh" 2>/dev/null && ok "extracted shipped functions parse" || { bad "extracted functions do not parse"; exit 1; }
grep -q 'EXTRACT FAILED' "$FIX/funcs.sh" && { bad "a shipped function could not be extracted" "$(grep 'EXTRACT FAILED' "$FIX/funcs.sh")"; exit 1; }

# stub curl: serves the scenario line "<code>|<bodyfile>" for each call
cat > "$FIX/bin/curl" <<'CURLSTUB'
#!/usr/bin/env bash
for a in "$@"; do [ "$a" = "--version" ] && { echo "curl 8.4.0 (stub)"; exit 0; }; done
out=""; hdr=""; data=""; prev=""
for a in "$@"; do case "$prev" in -o) out="$a";; -D) hdr="$a";; --data-binary) data="${a#@}";; esac; prev="$a"; done
[ -n "$data" ] && [ -f "$data" ] && cp "$data" "$RR_FIX_LASTBODY" 2>/dev/null
n=0; [ -f "$RR_FAKE_COUNT" ] && n="$(cat "$RR_FAKE_COUNT" 2>/dev/null || echo 0)"
n=$(( n + 1 )); printf '%s' "$n" > "$RR_FAKE_COUNT"
line="$(sed -n "${n}p" "$RR_FAKE_SCENARIO" 2>/dev/null)"; [ -n "$line" ] || line="$(tail -1 "$RR_FAKE_SCENARIO")"
code="${line%%|*}"; bodyfile="${line#*|}"
if [ -n "$bodyfile" ] && [ -f "$bodyfile" ]; then cat "$bodyfile" > "$out"; else : > "$out"; fi
[ -n "$hdr" ] && { printf 'HTTP/1.1 %s stub\r\nContent-Type: application/json\r\n\r\n' "$code" > "$hdr"; }
printf '%s' "$code"; exit 0
CURLSTUB
chmod +x "$FIX/bin/curl"

OPID="op_$(printf '%s' 'rr-delivery|idem-syn-1|tok-syn-123|2' | shasum -a 256 | cut -d' ' -f1)"
mkbody() { printf '%s' "$2" > "$FIX/body-$1"; }
field() { printf '%s\n' "$1" | grep "^$2=" | head -1 | cut -d= -f2-; }

# run_main <body-name>: fresh state, run the shipped _ack once, print JOURNAL / PENDING / LOG lines
run_main() {
  rm -rf "$FIX/state"; mkdir -p "$FIX/state/tmp" "$FIX/logs"; : > "$FIX/logs/poll.log"
  printf '200|%s\n' "$FIX/body-$1" > "$FIX/scenario"; : > "$FIX/count"
  cat > "$FIX/run.sh" <<RUNEOF
PATH="$FIX/bin:\$PATH"; RR_RECEIVER_URL="https://unroutable.invalid/rr"; RR_BOX_TOKEN="synthetic-token-value"
RR_BOX_SLUG="box-synthetic"; RECEIVER_VERSION="1.6.0"; _STATE="$FIX/state"; _DONE="\$_STATE/done"; _TMP="\$_STATE/tmp"
INSTRUCTION_ID="ins-syn-1"; IDEMPOTENCY_KEY="idem-syn-1"; TICKET_ID="RRT-syn-1"; ATTEMPT_ID="tok-syn-123"
ATTEMPT_GENERATION="2"; LEASE_EXPIRES_AT="2026-09-09T12:00:00.000Z"
mkdir -p "\$_DONE"; source "$FIX/funcs.sh"
_ack "delivered" 0 35 "" 12 "synthetic reply excerpt"
for f in "\$_STATE"/journal/op_*; do [ -f "\$f" ] || continue; printf 'JOURNAL=%s\n' "\$(_journal_phase "\$(basename "\$f")")"; done
p=0; for f in "\$_STATE"/ack-pending/op_*; do [ -f "\$f" ] && p=1; done; echo "PENDING=\$p"
RUNEOF
  bash "$FIX/run.sh" 2>&1
}

echo "== F63: no-op receipts settle the ack but are never a delivery =="
mkbody term    "{\"status\":\"ok\",\"recorded\":false,\"reason\":\"already_terminal\",\"receipt\":{\"operation_id\":\"$OPID\",\"attempt_id\":\"tok-syn-123\"}}"
mkbody unknown "{\"status\":\"ok\",\"recorded\":false,\"reason\":\"unknown_instruction\",\"receipt\":{\"operation_id\":\"$OPID\"}}"
mkbody missed  "{\"status\":\"ok\",\"recorded\":false,\"reason\":\"row_write_missed\",\"receipt\":{\"operation_id\":\"$OPID\"}}"
mkbody otherop "{\"status\":\"ok\",\"recorded\":false,\"reason\":\"already_terminal\",\"receipt\":{\"operation_id\":\"op_deadbeef\"}}"
mkbody norcpt  "{\"status\":\"ok\",\"recorded\":false,\"reason\":\"already_terminal\"}"
mkbody real    "{\"status\":\"ok\",\"recorded\":true,\"receipt\":{\"receipt_version\":1,\"operation_id\":\"$OPID\",\"attempt_id\":\"tok-syn-123\",\"state_revision\":7,\"recorded\":true}}"

out="$(run_main term)"
{ [ "$(field "$out" JOURNAL)" = "ack_settled_noop" ] && [ "$(field "$out" PENDING)" = "0" ]; } && ok "N1 already_terminal -> journal ack_settled_noop, pending ack removed" || bad "N1" "$out"
printf '%s' "$out" | grep -q 'SETTLED_NOOP' && ok "N1 log line says SETTLED_NOOP (not CONFIRMED)" || bad "N1 log" "$out"
printf '%s' "$out" | grep -q 'receipt=CONFIRMED' && bad "N1 logged a delivery" "$out" || ok "N1 never logged as a delivery"
out="$(run_main unknown)"
{ [ "$(field "$out" JOURNAL)" = "ack_settled_noop" ] && [ "$(field "$out" PENDING)" = "0" ]; } && ok "N2 unknown_instruction -> ack_settled_noop, pending removed" || bad "N2" "$out"

# N3: resend path. Seed a pending ack body the way _pending_put would, then run _resend_pending.
rm -rf "$FIX/state"; mkdir -p "$FIX/state/tmp" "$FIX/state/ack-pending" "$FIX/state/journal" "$FIX/logs"; : > "$FIX/logs/poll.log"
printf '{"action":"ack","operation_id":"%s","attempt_id":"tok-syn-123"}' "$OPID" > "$FIX/state/ack-pending/$OPID"
printf '200|%s\n' "$FIX/body-term" > "$FIX/scenario"; : > "$FIX/count"
out="$(cat > "$FIX/run3.sh" <<RUNEOF
PATH="$FIX/bin:\$PATH"; RR_RECEIVER_URL="https://unroutable.invalid/rr"; RR_BOX_TOKEN="synthetic-token-value"; RR_BOX_SLUG="box-synthetic"
RECEIVER_VERSION="1.6.0"; _STATE="$FIX/state"; _TMP="\$_STATE/tmp"; source "$FIX/funcs.sh"
_resend_pending
printf 'JOURNAL=%s\n' "\$(_journal_phase "$OPID")"; [ -f "\$_STATE/ack-pending/$OPID" ] && echo PENDING=1 || echo PENDING=0
RUNEOF
bash "$FIX/run3.sh" 2>&1)"
{ [ "$(field "$out" JOURNAL)" = "ack_settled_noop" ] && [ "$(field "$out" PENDING)" = "0" ]; } && ok "N3 resend path settles the noop (ack_settled_noop, pending removed)" || bad "N3" "$out"

for c in "missed:row_write_missed" "otherop:receipt for a different operation" "norcpt:no receipt at all"; do
  b="${c%%:*}"; d="${c#*:}"; out="$(run_main "$b")"
  { [ "$(field "$out" JOURNAL)" = "ack_pending" ] && [ "$(field "$out" PENDING)" = "1" ]; } && ok "N4-6 $d -> stays UNCONFIRMED (ack_pending, pending kept)" || bad "N4-6 $d" "$out"
done
out="$(run_main real)"
{ [ "$(field "$out" JOURNAL)" = "ack_confirmed" ] && [ "$(field "$out" PENDING)" = "0" ]; } && ok "N7 control: real delivery receipt -> ack_confirmed (detector can distinguish)" || bad "N7" "$out"

# N8: GC
rm -rf "$FIX/state"; mkdir -p "$FIX/state/journal" "$FIX/state/ack-pending" "$FIX/state/reconcile" "$FIX/state/tmp"
printf '{"operation_id":"op_noop","phase":"ack_settled_noop"}\n' > "$FIX/state/journal/op_noop"
printf '{"operation_id":"op_pend","phase":"ack_pending"}\n' > "$FIX/state/journal/op_pend"
touch -t 202001010000 "$FIX/state/journal/op_noop" "$FIX/state/journal/op_pend"
cat > "$FIX/run8.sh" <<RUNEOF
PATH="$FIX/bin:\$PATH"; _STATE="$FIX/state"; _TMP="\$_STATE/tmp"; source "$FIX/funcs.sh"; _gc_journal >/dev/null 2>&1
[ -f "\$_STATE/journal/op_noop" ] && echo NOOP=kept || echo NOOP=reaped
[ -f "\$_STATE/journal/op_pend" ] && echo PEND=kept || echo PEND=moved
RUNEOF
out="$(bash "$FIX/run8.sh" 2>&1)"
[ "$(field "$out" NOOP)" = "reaped" ] && ok "N8 old ack_settled_noop journal record is reaped like a confirmed one" || bad "N8 noop not reaped" "$out"
{ [ -f "$FIX/state/journal/op_pend" ] || [ -f "$FIX/state/reconcile/op_pend" ]; } && ok "N8 old UNCONFIRMED record is never deleted (kept or moved to reconcile/)" || bad "N8 unconfirmed record lost" "$out"

echo; echo "RR-030 receipt no-op: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
