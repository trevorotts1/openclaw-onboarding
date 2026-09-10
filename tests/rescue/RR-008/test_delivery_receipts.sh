#!/usr/bin/env bash
# tests/rescue/RR-008/test_delivery_receipts.sh — ONB-side RR-008 gate.
#
# SPEC RR-008: "Write a durable attempt journal before effects, atomically save
# complete outcome/proof as ACK_PENDING, and resend identical results until a
# matching structured receipt arrives. Accept only expected 2xx JSON with
# operation/attempt/state revision; classify redirects, HTML and unauthorized
# responses as failures. Journal failures stop new effects; uncertain external
# effects require reconciliation before rerunning. Use unique operation IDs,
# private permissions and bounded post-reconciliation retention."
#
# WHAT THIS PROVES — named state transitions, driven through the SHIPPED
# functions (extracted by name from rescue-poll.sh, never reimplemented):
#   T1  _post: 3xx is a FAILURE (the old `2*|3*)` success case is gone).
#   T2  _post/_post_class: 2xx+JSON=ok_json; 2xx+HTML / 2xx+empty=ok_nonjson;
#       401/403=unauthorized; 429=throttled; 5xx=server; dropped=transport.
#   T3  _ack under every transport failure class -> journal ack_pending,
#       ack-pending/ row RETAINED, receipt=UNCONFIRMED class=<name>.
#   T4  A bare 2xx is NEVER a confirmation: no receipt / wrong operation /
#       wrong attempt / missing state_revision each give a distinct refusal.
#   T5  A matching structured receipt settles: ack_confirmed, row REMOVED.
#   T6  REPLAY byte-identity: the resent request body hashes IDENTICALLY to the
#       original send and carries ONE operation id across two sends.
#   T7  CRASH MATRIX: cut before/after journal, effect, done, outbox, send and
#       settle; then run the recovery path — both stores converge, 1 op row.
#   T8  Journal write failure STOPS the effect (_post never called).
#   T9  ACK_PENDING write failure (disk-full shape) STOPS the effect, and the
#       pre-effect journal row survives so the attempt stays recoverable.
#   T10 _reack_cached replays the ORIGINAL excerpt and the SAME operation id.
#   T11 Retention: confirmed rows GC after the bound; unconfirmed rows are
#       NEVER silently dropped (moved to reconcile/ with an owned log line).
#   T12 Privacy: journal/pending records are 0600; the box token reaches no
#       persisted artifact under the state or log roots.
#
# Sanitized fixtures only (synthetic box slug, synthetic token, an unroutable
# URL the stubbed curl never dials). Run:
#   bash tests/rescue/RR-008/test_delivery_receipts.sh

set -u
PASS=0
FAIL=0
say_ok()   { PASS=$((PASS+1)); echo "  ok   $1"; }
say_fail() { FAIL=$((FAIL+1)); echo "  FAIL $1 ${2:-}"; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
POLL="$REPO/65-rescue-receiver/rescue-poll.sh"

echo "== RR-008 ONB: durable delivery journal + structured receipt =="
[ -f "$POLL" ] || { echo "FATAL: $POLL missing"; exit 2; }

# ---------------------------------------------------------------------------
# 0. STRUCTURAL PRE-CHECKS
# ---------------------------------------------------------------------------
# comments in the shipped file QUOTE the removed pattern (that is the fix's own
# documentation), so the check strips comments and looks only at live code.
if grep -v '^[[:space:]]*#' "$POLL" | grep -q '2\*|3\*)'; then
  say_fail "no '2*|3*)' success case in _post" "still present in live code"
else
  say_ok "_post carries NO '2*|3*)' success case in live code (a redirect is a failure)"
fi
for fn in _post_class _json_get _sha _op_id_for _journal_put _journal_phase \
          _pending_put _receipt_match _ack_send _resend_pending _gc_journal; do
  grep -q "^${fn}() {" "$POLL" && say_ok "$fn present" || say_fail "$fn missing"
done
ver="$(grep -E '^RECEIVER_VERSION=' "$POLL" | head -1 | cut -d'"' -f2)"
case "$ver" in
  1.6.*|1.[7-9].*|[2-9].*) say_ok "RECEIVER_VERSION advanced for the RR-008 slice: $ver" ;;
  *) say_fail "RECEIVER_VERSION" "got '$ver' (expected >= 1.6.0)" ;;
esac

# ---------------------------------------------------------------------------
# SANDBOX
# ---------------------------------------------------------------------------
FIX="$(mktemp -d)"
trap 'rm -rf "$FIX"' EXIT
mkdir -p "$FIX/bin" "$FIX/logs"

extract_fn() {  # extract_fn <file> <fn-name>
  local f="$1" fn="$2" s e
  s="$(grep -n "^${fn}()" "$f" | head -1 | cut -d: -f1)"
  [ -n "$s" ] || { echo "echo 'EXTRACT MISSING: ${fn}' >&2" >&2; return 0; }
  e="$(awk -v s="$s" 'NR>=s && /^}/ {print NR; exit}' "$f")"
  [ -n "$e" ] || { echo "echo 'EXTRACT UNTERMINATED: ${fn}' >&2" >&2; return 0; }
  sed -n "${s},${e}p" "$f"
  echo
}

{
  for fn in _json_str _json_field _json_get _post_class _sha _now_iso _op_id_for \
            _journal_put _journal_phase _pending_put _receipt_match _ack_send \
            _resend_pending _gc_journal _post _ack _write_done _reack_cached; do
    extract_fn "$POLL" "$fn"
  done
  echo '_log() { printf "%s\n" "$1" >> "$RR_FIX_LOG"; }'
} > "$FIX/funcs.sh"
bash -n "$FIX/funcs.sh" 2>/dev/null && say_ok "extracted shipped functions parse (bash -n)" \
                                    || say_fail "extracted functions syntax"

export OPID="op_$(printf '%s' 'rr-delivery|idem-syn-1|tok-syn-123|2' | shasum -a 256 | cut -d' ' -f1)"
echo "  --   operation id under test: $OPID"

# curl stub: emits the next scenario line's (code|bodyfile); records the sha256
# of EVERY request body it is handed, so byte-identity is provable per send.
cat > "$FIX/bin/curl" <<'CURLSTUB'
#!/usr/bin/env bash
for a in "$@"; do
  [ "$a" = "--version" ] && { echo "curl 8.4.0 (stub)"; exit 0; }
done
out=""; hdr=""; dbf=""; prev=""
for a in "$@"; do
  case "$prev" in
    -o) out="$a" ;;
    -D) hdr="$a" ;;
    --data-binary) dbf="$a" ;;
  esac
  prev="$a"
done
if [ -n "$dbf" ]; then
  _bf="${dbf#@}"
  if [ -f "$_bf" ]; then
    if [ -n "${RR_FAKE_BODIES:-}" ]; then
      shasum -a 256 < "$_bf" 2>/dev/null | cut -d' ' -f1 >> "$RR_FAKE_BODIES" 2>/dev/null
    fi
    if [ -n "${RR_FAKE_WIRE:-}" ]; then
      printf '%s\n' "$(cat "$_bf" 2>/dev/null)" >> "$RR_FAKE_WIRE" 2>/dev/null
    fi
  fi
fi
n=0
[ -f "$RR_FAKE_COUNT" ] && n="$(cat "$RR_FAKE_COUNT" 2>/dev/null || echo 0)"
n=$(( n + 1 ))
printf '%s' "$n" > "$RR_FAKE_COUNT" 2>/dev/null
line="$(sed -n "${n}p" "$RR_FAKE_SCENARIO" 2>/dev/null)"
[ -n "$line" ] || line="$(tail -1 "$RR_FAKE_SCENARIO" 2>/dev/null)"
code="${line%%|*}"
bodyfile="${line#*|}"
if [ "$code" = "000" ]; then exit 7; fi
if [ -n "$out" ]; then
  if [ -n "$bodyfile" ] && [ -f "$bodyfile" ]; then cat "$bodyfile" > "$out" 2>/dev/null
  else : > "$out" 2>/dev/null
  fi
fi
if [ -n "$hdr" ]; then
  { printf 'HTTP/1.1 %s stub\r\n' "$code"
    case "$bodyfile" in *html*) printf 'Content-Type: text/html\r\n' ;; *) printf 'Content-Type: application/json\r\n' ;; esac
    printf '\r\n'; } > "$hdr" 2>/dev/null
fi
printf '%s' "$code"
exit 0
CURLSTUB
chmod +x "$FIX/bin/curl"

printf '<html><body>CF Access login</body></html>' > "$FIX/body-html"
printf '' > "$FIX/body-empty"
printf '%s' "{\"status\":\"ok\",\"recorded\":true,\"receipt\":{\"receipt_version\":1,\"operation_id\":\"$OPID\",\"attempt_id\":\"tok-syn-123\",\"state_revision\":\"receipt_only\",\"recorded\":true}}" > "$FIX/body-good"
printf '%s' '{"status":"ok","recorded":true}' > "$FIX/body-noreceipt"
printf '%s' '{"status":"ok","receipt":{"operation_id":"op_OTHER","attempt_id":"tok-syn-123","state_revision":"receipt_only"}}' > "$FIX/body-wrongop"
printf '%s' "{\"status\":\"ok\",\"receipt\":{\"operation_id\":\"$OPID\",\"attempt_id\":\"tok-OTHER\",\"state_revision\":\"receipt_only\"}}" > "$FIX/body-wrongatt"
printf '%s' "{\"status\":\"ok\",\"receipt\":{\"operation_id\":\"$OPID\",\"attempt_id\":\"tok-syn-123\"}}" > "$FIX/body-norev"
printf '%s' "{\"action\":\"ack\",\"box_slug\":\"box-synthetic\",\"instruction_id\":\"ins-syn-1\",\"idempotency_key\":\"idem-syn-1\",\"operation_id\":\"$OPID\",\"verdict\":\"delivered\",\"attempt_id\":\"tok-syn-123\",\"attempt_generation\":2,\"reply_excerpt\":\"synthetic reply excerpt\"}" > "$FIX/cutbody"

# The prelude is generated ONCE, quoted-heredoc + placeholder substitution, so
# nothing in it is expanded by this script. Every snippet is then appended
# verbatim from its OWN quoted heredoc: no nested quote gymnastics.
cat > "$FIX/prelude.tpl" <<'PRE'
export PATH="__FIX__/bin:$PATH"
export RR_FIX_LOG="__FIX__/logs/poll.log"
export RR_FAKE_SCENARIO="__FIX__/scenario"
export RR_FAKE_COUNT="__FIX__/count"
export RR_FAKE_BODIES="__FIX__/bodies"
export RR_FAKE_WIRE="__FIX__/wire"
export RR_RECEIVER_URL="https://unroutable.invalid/rr"
export RR_BOX_TOKEN="synthetic-token-value"
export RR_BOX_SLUG="box-synthetic"
export RECEIVER_VERSION="1.6.0"
export _STATE="__FIX__/state"
export _DONE="$_STATE/done"
export _TMP="$_STATE/tmp"
export _JOURNAL="$_STATE/journal"
export _PENDING="$_STATE/ack-pending"
export _RECONCILE="$_STATE/reconcile"
export INSTRUCTION_ID="ins-syn-1"
export IDEMPOTENCY_KEY="idem-syn-1"
export TICKET_ID="RRT-syn-1"
export ATTEMPT_ID="tok-syn-123"
export ATTEMPT_GENERATION="2"
export LEASE_EXPIRES_AT="2026-09-09T12:00:00.000Z"
export OPID="__OPID__"
source "__FIX__/funcs.sh"
PRE
sed -e "s|__FIX__|$FIX|g" -e "s|__OPID__|$OPID|g" "$FIX/prelude.tpl" > "$FIX/prelude.sh"

fresh() {  # fresh <scenario-lines...>
  # Mirrors the real script's startup: the RR-008 stores exist (0700) before
  # any poll work, exactly as rescue-poll.sh creates them on load.
  rm -rf "$FIX/state"; mkdir -p "$FIX/state/tmp" "$FIX/state/done" "$FIX/logs"
  mkdir -p "$FIX/state/journal" "$FIX/state/ack-pending"
  chmod 700 "$FIX/state/journal" "$FIX/state/ack-pending"
  printf '0' > "$FIX/count"; : > "$FIX/bodies"; : > "$FIX/wire"
  printf '%s\n' "$@" > "$FIX/scenario"
}
OVERRIDES=""
run_snip() {  # snippet arrives on stdin
  { cat "$FIX/prelude.sh"; printf '%s\n' "$OVERRIDES"; cat; } > "$FIX/snip.sh"
  bash "$FIX/snip.sh" 2>&1
}
field() { printf '%s\n' "$1" | grep "^$2=" | head -1 | cut -d= -f2-; }
logtail() { tail -3 "$FIX/logs/poll.log" 2>/dev/null | tr '\n' '|'; }

# ---------------------------------------------------------------------------
echo ""
echo "T1/T2: _post / _post_class classification (real _post, stubbed curl)"
post_class() {  # post_class <code> <bodyfile>
  fresh "$1|$2"
  run_snip <<'SNIP'
if _post '{"x":1}' >/dev/null 2>&1; then echo "POST=0"; else echo "POST=1"; fi
printf 'CLASS=%s\n' "$(_post_class)"
SNIP
}
r="$(post_class 302 "$FIX/body-html")"
{ [ "$(field "$r" POST)" = "1" ] && [ "$(field "$r" CLASS)" = "redirect" ]; } \
  && say_ok "T1 302 -> _post FAILS (rc=1), class=redirect (was the old silent success)" \
  || say_fail "T1 302" "$r"
r="$(post_class 301 "$FIX/body-html")"
{ [ "$(field "$r" POST)" = "1" ] && [ "$(field "$r" CLASS)" = "redirect" ]; } \
  && say_ok "T1 301 -> _post FAILS, class=redirect" || say_fail "T1 301" "$r"
r="$(post_class 200 "$FIX/body-good")"
{ [ "$(field "$r" POST)" = "0" ] && [ "$(field "$r" CLASS)" = "ok_json" ]; } \
  && say_ok "T2 200 + JSON -> ok, class=ok_json" || say_fail "T2 200 JSON" "$r"
r="$(post_class 200 "$FIX/body-html")"
{ [ "$(field "$r" CLASS)" = "ok_nonjson" ]; } \
  && say_ok "T2 200 + HTML -> class=ok_nonjson (a FAILURE for the ack path)" || say_fail "T2 200 HTML" "$r"
r="$(post_class 200 "$FIX/body-empty")"
{ [ "$(field "$r" CLASS)" = "ok_nonjson" ]; } \
  && say_ok "T2 200 + empty body -> class=ok_nonjson" || say_fail "T2 empty" "$r"
r="$(post_class 401 "$FIX/body-html")"
{ [ "$(field "$r" CLASS)" = "unauthorized" ]; } \
  && say_ok "T2 401 -> class=unauthorized" || say_fail "T2 401" "$r"
r="$(post_class 403 "$FIX/body-html")"
{ [ "$(field "$r" CLASS)" = "unauthorized" ]; } \
  && say_ok "T2 403 -> class=unauthorized" || say_fail "T2 403" "$r"
r="$(post_class 429 "$FIX/body-good")"
{ [ "$(field "$r" CLASS)" = "throttled" ]; } \
  && say_ok "T2 429 -> class=throttled" || say_fail "T2 429" "$r"
r="$(post_class 503 "$FIX/body-html")"
{ [ "$(field "$r" CLASS)" = "server" ]; } \
  && say_ok "T2 503 -> class=server" || say_fail "T2 503" "$r"
r="$(post_class 000 "$FIX/body-good")"
{ [ "$(field "$r" POST)" = "1" ] && [ "$(field "$r" CLASS)" = "transport" ]; } \
  && say_ok "T2 dropped response -> _post FAILS, class=transport" || say_fail "T2 transport" "$r"

# ---------------------------------------------------------------------------
ack_run() {  # runs _ack; prints RC / JOURNAL / PENDING / SENDS
  run_snip <<'SNIP'
_ack "delivered" 0 35 "" 12 "synthetic reply excerpt"
echo "RC=$?"
for f in $_JOURNAL/op_*; do [ -f "$f" ] && printf 'JOURNAL=%s\n' "$(_journal_phase "$(basename "$f")")"; done
P=0; for f in $_PENDING/op_*; do [ -f "$f" ] && P=1; done
echo "PENDING=$P"
echo "SENDS=$(cat "$RR_FAKE_COUNT" 2>/dev/null || echo 0)"
SNIP
}

echo ""
echo "T3: every transport failure class leaves the ack UNCONFIRMED and retained"
for pair in "302:$FIX/body-html:redirect" "200:$FIX/body-html:ok_nonjson" "401:$FIX/body-html:unauthorized" "429:$FIX/body-good:throttled" "503:$FIX/body-html:server" "000:$FIX/body-good:transport"; do
  code="${pair%%:*}"; rest="${pair#*:}"; body="${rest%%:*}"; want="${rest#*:}"
  fresh "$code|$body"
  out="$(ack_run)"
  if [ "$(field "$out" RC)" = "0" ] && [ "$(field "$out" JOURNAL)" = "ack_pending" ] \
     && [ "$(field "$out" PENDING)" = "1" ] && [ "$(field "$out" SENDS)" = "1" ] \
     && grep -q "receipt=UNCONFIRMED class=$want" "$FIX/logs/poll.log"; then
    say_ok "T3 code=$code -> journal=ack_pending, row RETAINED, receipt=UNCONFIRMED class=$want"
  else
    say_fail "T3 code=$code (want class=$want)" "$out / $(logtail)"
  fi
done

echo ""
echo "T4: a bare 2xx is never a confirmation"
t4() {  # t4 <bodyfile> <expected-refusal> <human-label>
  fresh "200|$1"
  out="$(ack_run)"
  if [ "$(field "$out" JOURNAL)" = "ack_pending" ] && [ "$(field "$out" PENDING)" = "1" ] \
     && grep -q "class=ok_json:$2" "$FIX/logs/poll.log"; then
    say_ok "T4 2xx + $3 -> UNCONFIRMED ($2)"
  else
    say_fail "T4 2xx + $3" "$out / $(logtail)"
  fi
}
t4 "$FIX/body-noreceipt" "no_receipt_operation_id"    "NO receipt object"
t4 "$FIX/body-wrongop"   "receipt_operation_mismatch" "a receipt with the WRONG operation_id"
t4 "$FIX/body-wrongatt"  "receipt_attempt_mismatch"   "a receipt with the WRONG attempt_id"
t4 "$FIX/body-norev"     "no_receipt_state_revision"  "a receipt with NO state_revision"

echo ""
echo "T5/T6: matching receipt settles; the replay is byte-identical"
fresh "200|$FIX/body-good"
out="$(ack_run)"
{ [ "$(field "$out" JOURNAL)" = "ack_confirmed" ] && [ "$(field "$out" PENDING)" = "0" ] \
  && grep -q 'receipt=CONFIRMED rev=receipt_only' "$FIX/logs/poll.log"; } \
  && say_ok "T5 matching receipt (op+attempt+state_revision) -> journal=ack_confirmed, row REMOVED" \
  || say_fail "T5 settle" "$out / $(logtail)"

fresh "302|$FIX/body-html" "200|$FIX/body-good"
out="$(run_snip <<'SNIP'
_ack "delivered" 0 35 "" 12 "synthetic reply excerpt"
_resend_pending
P=0; for f in $_PENDING/op_*; do [ -f "$f" ] && P=1; done
echo "PENDING=$P"
echo "PHASE=$(for f in $_JOURNAL/op_*; do [ -f "$f" ] && _journal_phase "$(basename "$f")"; done)"
echo "SENDS=$(cat "$RR_FAKE_COUNT")"
echo "OPROWS=$(ls -1 $_JOURNAL 2>/dev/null | grep -c '^op_')"
echo "BODIES=$(tr '\n' ' ' < "$RR_FAKE_BODIES")"
SNIP
)"
h1="$(printf '%s' "$(field "$out" BODIES)" | awk '{print $1}')"
h2="$(printf '%s' "$(field "$out" BODIES)" | awk '{print $2}')"
if [ -n "$h1" ] && [ "$h1" = "$h2" ]; then
  say_ok "T6 resend is BYTE-IDENTICAL to the original send (same sha256 across both sends)"
else
  say_fail "T6 resend bytes differ" "send1=$h1 send2=$h2 / $out"
fi
{ [ "$(field "$out" PENDING)" = "0" ] && [ "$(field "$out" PHASE)" = "ack_confirmed" ] \
  && [ "$(field "$out" SENDS)" = "2" ] && [ "$(field "$out" OPROWS)" = "1" ]; } \
  && say_ok "T6 fail-then-resend converges: 2 sends, EXACTLY 1 operation id, 0 pending rows" \
  || say_fail "T6 convergence" "$out"
if grep -q "op=$OPID" "$FIX/logs/poll.log"; then
  say_ok "T6 every send is logged under the SAME operation id"
else
  say_fail "T6 operation id in log" "$(cat "$FIX/logs/poll.log")"
fi
if grep -q 'ack-resend CONFIRMED' "$FIX/logs/poll.log"; then
  say_ok "T6 the RESEND path (not a fresh effect) closed the operation"
else
  say_fail "T6 resend path used" "$(cat "$FIX/logs/poll.log")"
fi

echo ""
echo "T7: crash before/after every step, then recover (both stores must converge)"
for CUT in 1 2 3 4 5 6; do
  fresh "302|$FIX/body-html" "200|$FIX/body-good"
  OVERRIDES="CUT=$CUT"
  cat > "$FIX/cut.snip" <<'SNIP'
_journal_put "$OPID" effect_started "{\"instruction_id\":\"ins-syn-1\"}" || exit 9
if [ "$CUT" -le 1 ]; then echo CUTSTEP=1; exit 0; fi
_journal_put "$OPID" effect_executed '{"verdict":"delivered"}' || exit 9
if [ "$CUT" -le 2 ]; then echo CUTSTEP=2; exit 0; fi
_write_done delivered 0 35 "" 12 "synthetic reply excerpt" || exit 9
if [ "$CUT" -le 3 ]; then echo CUTSTEP=3; exit 0; fi
_journal_put "$OPID" ack_attempt '{"verdict":"delivered"}' || exit 9
_pending_put "$OPID" "$(cat "$_STATE/../cutbody")" || exit 9
if [ "$CUT" -le 4 ]; then echo CUTSTEP=4; exit 0; fi
VT=$(_ack_send "$(cat "$_STATE/../cutbody")" "$OPID" "tok-syn-123" ack)
if [ "$CUT" -le 5 ]; then echo "CUTSTEP=5 SEND=$VT"; exit 0; fi
case "$VT" in
  confirmed:*)
    _journal_put "$OPID" ack_confirmed '{}'
    rm -f "$_PENDING/$OPID" ;;
esac
echo "CUTSTEP=6 SEND=$VT"
SNIP
  cutout="$(run_snip < "$FIX/cut.snip")"
  OVERRIDES=""
  rec="$(run_snip <<'SNIP'
_resend_pending
P=0; for f in $_PENDING/op_*; do [ -f "$f" ] && P=1; done
echo "PENDING=$P"
echo "PHASE=$(for f in $_JOURNAL/op_*; do [ -f "$f" ] && _journal_phase "$(basename "$f")"; done)"
echo "OPROWS=$(ls -1 $_JOURNAL 2>/dev/null | grep -c '^op_')"
SNIP
)"
  ok=1
  [ "$(field "$rec" OPROWS)" = "1" ] || ok=0
  case "$cutout" in
    *"CUTSTEP=5"*|*"CUTSTEP=6"*)
      { [ "$(field "$rec" PENDING)" = "0" ] && [ "$(field "$rec" PHASE)" = "ack_confirmed" ]; } || ok=0 ;;
  esac
  step="$(printf '%s' "$cutout" | grep -o 'CUTSTEP=[0-9]' | head -1 | cut -d= -f2)"
  if [ "$ok" = "1" ]; then
    say_ok "T7 cut after step $step -> recovery converges (1 op row, pending=$(field "$rec" PENDING), phase=$(field "$rec" PHASE))"
  else
    say_fail "T7 cut after step $step diverged" "$cutout | $rec"
  fi
done

echo ""
echo "T8/T9: a store write failure STOPS the effect (_post never called)"
if [ "$(id -u)" = "0" ]; then
  echo "  skip T8/T9 (running as root: a mode change cannot deny the write)"
else
  fresh "200|$FIX/body-good"
  out="$(run_snip <<'SNIP'
mkdir -p "$_JOURNAL" "$_PENDING"; chmod 700 "$_JOURNAL" "$_PENDING"
chmod 500 "$_JOURNAL"
_ack "delivered" 0 35 "" 12 "synthetic reply excerpt"
echo "RC=$?"
chmod 700 "$_JOURNAL"
SNIP
)"
  { [ "$(field "$out" RC)" != "0" ] && [ "$(cat "$FIX/count")" = "0" ] \
    && grep -q 'ACK HELD: journal write failed' "$FIX/logs/poll.log"; } \
    && say_ok "T8 journal write fails -> ack HELD (rc=$(field "$out" RC)), _post NEVER called (sends=0)" \
    || say_fail "T8 journal failure" "$out / sends=$(cat "$FIX/count" 2>/dev/null)"

  fresh "200|$FIX/body-good"
  out="$(run_snip <<'SNIP'
mkdir -p "$_JOURNAL" "$_PENDING"; chmod 700 "$_JOURNAL"; chmod 500 "$_PENDING"
_ack "delivered" 0 35 "" 12 "synthetic reply excerpt"
echo "RC=$?"
chmod 700 "$_PENDING"
SNIP
)"
  { [ "$(field "$out" RC)" != "0" ] && [ "$(cat "$FIX/count")" = "0" ] \
    && grep -q 'ACK HELD: ack-pending write failed' "$FIX/logs/poll.log"; } \
    && say_ok "T9 ack-pending write fails (disk-full shape) -> ack HELD, _post NEVER called (sends=0)" \
    || say_fail "T9 disk-full" "$out / sends=$(cat "$FIX/count" 2>/dev/null)"

  ph="$(run_snip <<'SNIP'
for f in $_JOURNAL/op_*; do [ -f "$f" ] && _journal_phase "$(basename "$f")"; done
SNIP
)"
  [ "$ph" = "ack_attempt" ] \
    && say_ok "T9 the pre-effect journal row SURVIVES the failed outbox write (phase=$ph) -> recoverable, not lost" \
    || say_fail "T9 journal survival" "phase='$ph'"
fi

echo ""
echo "T10: cached re-ack replays the ORIGINAL evidence"
fresh "200|$FIX/body-good"
out="$(run_snip <<'SNIP'
_write_done delivered 0 35 "" 12 "the ORIGINAL excerpt" || echo DONEFAIL
_reack_cached "$IDEMPOTENCY_KEY"
echo "RC=$?"
echo "BODY=$(cat "$RR_FAKE_WIRE" 2>/dev/null)"
echo "PHASE=$(for f in $_JOURNAL/op_*; do [ -f "$f" ] && _journal_phase "$(basename "$f")"; done)"
SNIP
)"
body="$(field "$out" BODY)"
printf '%s' "$body" | grep -q 'the ORIGINAL excerpt' \
  && say_ok "T10 cached re-ack carries the ORIGINAL reply excerpt (the cache no longer drops proof)" \
  || say_fail "T10 excerpt lost from re-ack" "$out"
printf '%s' "$body" | grep -q "\"operation_id\":\"$OPID\"" \
  && say_ok "T10 cached re-ack carries the SAME operation id -> the server sees an idempotent receipt" \
  || say_fail "T10 op id missing from re-ack" "$out"
printf '%s' "$body" | grep -q '"attempt_id":"tok-syn-123"' \
  && say_ok "T10 cached re-ack re-establishes the ORIGINAL attempt identity" \
  || say_fail "T10 attempt id missing" "$out"
[ "$(field "$out" PHASE)" = "ack_confirmed" ] \
  && say_ok "T10 cached re-ack settles on the matching receipt (phase=ack_confirmed)" \
  || say_fail "T10 re-ack phase" "$out"

echo ""
echo "T11: bounded post-reconciliation retention"
fresh
mkdir -p "$FIX/state/journal" "$FIX/state/ack-pending"
printf '{"operation_id":"op_old_confirmed","phase":"ack_confirmed"}\n' > "$FIX/state/journal/op_old_confirmed"
printf '{"operation_id":"op_old_pending","phase":"ack_pending"}\n'   > "$FIX/state/journal/op_old_pending"
printf '{"operation_id":"op_old_pending"}\n'                          > "$FIX/state/ack-pending/op_old_pending"
touch -t 202608010000 "$FIX/state/journal/op_old_confirmed" "$FIX/state/journal/op_old_pending" "$FIX/state/ack-pending/op_old_pending"
gc="$(run_snip <<'SNIP'
_gc_journal
echo "CONFIRMED_GONE=$([ -f "$_JOURNAL/op_old_confirmed" ] && echo 0 || echo 1)"
echo "UNCONFIRMED_KEPT=$([ -f "$_JOURNAL/op_old_pending" ] && echo 1 || echo 0)"
echo "MOVED_TO_RECONCILE=$([ -f "$_RECONCILE/op_old_pending" ] && echo 1 || echo 0)"
echo "BODY_MOVED=$([ -f "$_PENDING/op_old_pending" ] && echo 0 || echo 1)"
echo "BODY_BYTES=$(cat "$_RECONCILE/op_old_pending" 2>/dev/null | grep -c op_old_pending)"
SNIP
)"
{ [ "$(field "$gc" CONFIRMED_GONE)" = "1" ] && [ "$(field "$gc" UNCONFIRMED_KEPT)" = "1" ] \
  && [ "$(field "$gc" MOVED_TO_RECONCILE)" = "1" ] && [ "$(field "$gc" BODY_MOVED)" = "1" ] \
  && [ "$(field "$gc" BODY_BYTES)" = "1" ]; } \
  && say_ok "T11 confirmed row GC'd past the bound; unconfirmed row MOVED to reconcile/ with its body retained (never silently dropped)" \
  || say_fail "T11 retention" "$gc"
grep -q 'ack-reconcile OBLIGATION is now owned by operator' "$FIX/logs/poll.log" \
  && say_ok "T11 the moved obligation is LOUD (owned-reconcile log line emitted)" \
  || say_fail "T11 reconcile log line" "$(cat "$FIX/logs/poll.log" 2>/dev/null)"

echo ""
echo "T12: private permissions + token containment"
fresh "200|$FIX/body-good"
perm="$(run_snip <<'SNIP'
mkdir -p "$_JOURNAL" "$_PENDING"; chmod 700 "$_JOURNAL" "$_PENDING"
_journal_put "$OPID" effect_started '{}'
_pending_put "$OPID" '{"operation_id":"x"}'
_write_done delivered 0 35 "" 12 "x"
st() { stat -f '%Lp' "$1" 2>/dev/null || stat -c '%a' "$1" 2>/dev/null; }
echo "JDIR=$(st "$_JOURNAL")"
echo "PDIR=$(st "$_PENDING")"
echo "JFILE=$(st "$_JOURNAL/$OPID")"
echo "PFILE=$(st "$_PENDING/$OPID")"
SNIP
)"
{ [ "$(field "$perm" JFILE)" = "600" ] && [ "$(field "$perm" PFILE)" = "600" ]; } \
  && say_ok "T12 journal + ack-pending records are 0600 (dirs j=$(field "$perm" JDIR) p=$(field "$perm" PDIR))" \
  || say_fail "T12 permissions" "$perm"
if grep -rq 'synthetic-token-value' "$FIX/state" "$FIX/logs" 2>/dev/null; then
  say_fail "T12 token containment" "the box token appears in a persisted artifact under the state or log root"
else
  say_ok "T12 the box token appears in NO persisted artifact under the state or log roots (grep -r over both)"
fi

echo ""
echo "T13/RR-002: the journal carries the ADMISSION TICKET ID as incident_id"
# RR-002 requires the admission ticket ID to be echoed into the originating
# task journal and REQUIRED on resolution. The journal is written before any
# effect, so a resolution can name the exact incident instead of guessing by
# box. Asserted on the persisted record, not on a narrative.
fresh "200|$FIX/body-good"
inc="$(run_snip <<'SNIP'
mkdir -p "$_JOURNAL"; chmod 700 "$_JOURNAL"
_journal_put "$OPID" effect_started '{}' >/dev/null 2>&1
echo "INCID=$( _json_get "$(cat "$_JOURNAL/$OPID" 2>/dev/null)" "incident_id" )"
echo "WANT=$TICKET_ID"
# an UNKNOWN ticket id must record EMPTY, never a guess
TICKET_ID_SAVED="$TICKET_ID"; TICKET_ID=""
_journal_put "${OPID}-none" effect_started '{}' >/dev/null 2>&1
echo "EMPTY=$( _json_get "$(cat "$_JOURNAL/${OPID}-none" 2>/dev/null)" "incident_id" )"
TICKET_ID="$TICKET_ID_SAVED"
SNIP
)"
if [ "$(field "$inc" INCID)" = "$(field "$inc" WANT)" ] && [ -n "$(field "$inc" WANT)" ]; then
  say_ok "T13 journal record carries incident_id=$(field "$inc" INCID) (the admission ticket id, echoed at the pre-effect write)"
else
  say_fail "T13 incident_id echo" "$inc"
fi
[ -z "$(field "$inc" EMPTY)" ] \
  && say_ok "T13 an unknown admission ticket id records EMPTY incident_id — a missing id is never invented" \
  || say_fail "T13 incident_id fabrication" "recorded [$(field "$inc" EMPTY)] with no ticket id known"

echo ""
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
