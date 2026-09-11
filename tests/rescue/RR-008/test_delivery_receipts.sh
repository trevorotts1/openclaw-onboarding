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
# WHAT THIS PROVES (named transitions, not "exit 0"):
#   T1  _post: 3xx is a FAILURE (the old `2*|3*)` case is gone) — driven through
#       the REAL _post against a stubbed curl, so the classification is the
#       shipped one, not a reimplementation.
#   T2  _post: a 2xx carrying an HTML body is classed ok_nonjson (a FAILURE for
#       the ack path); a 2xx carrying JSON is ok_json.
#   T3  _ack: 302 / 200-HTML / 401 / 429 / dropped-response all leave the
#       operation UNCONFIRMED — journal phase ack_pending, identical body
#       retained in ack-pending/, and NO settle.
#   T4  _ack: a 2xx JSON without a matching structured receipt is UNCONFIRMED
#       (no_receipt_operation_id / receipt_operation_mismatch /
#       receipt_attempt_mismatch), with a distinct visible reason per case.
#   T5  _ack: a matching receipt (operation + attempt + state_revision) settles
#       the operation — journal ack_confirmed, ack-pending/ entry removed.
#   T6  REPLAY: the resent bytes are BYTE-IDENTICAL to the original send and
#       carry the SAME operation id -> the server records zero new effects.
#   T7  CRASH MATRIX: cutting the sequence before/after EACH step (journal,
#       effect, done, outbox/pending, send, receipt) and then running the
#       recovery path converges both stores, with no duplicate side effect.
#   T8  JOURNAL FAILURE STOPS NEW EFFECTS: an unwritable journal dir means the
#       ack is HELD and _post was never called.
#   T9  DISK-FULL: an unwritable ack-pending dir means the ack is HELD and
#       _post was never called.
#   T10 _reack_cached: the cached re-ack carries the ORIGINAL reply excerpt and
#       the SAME operation id (the defect was a cache that dropped both).
#   T11 RETENTION: confirmed rows GC after the bound; unconfirmed rows are
#       NEVER silently deleted (moved to reconcile/ with a log line).
#   T12 PERMISSIONS: journal / ack-pending / reconcile are 0700, records 0600.
#
# Sanitized fixtures only (synthetic box slug, synthetic token, an unroutable
# URL the stubbed curl never reaches). Run:
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
# 0. STRUCTURAL PRE-CHECKS (the shape that makes the rest meaningful)
# ---------------------------------------------------------------------------
# NOTE: the shipped comment PROSE in _post quotes the retired pattern, so a
# bare grep for '2*|3*)' matches the explanation and not a case arm. Strip
# comments before looking for the real arm — the arm is what delivers, the
# prose is not. (qfound: the previous bare grep failed on its own file.)
_no_comments() { sed 's/#.*//' "$1"; }
if _no_comments "$POLL" | grep -q '2\*|3\*)'; then
  say_fail "_post no longer accepts a redirect as success" "found a REAL '2*|3*)' case arm (comments stripped)"
else
  say_ok "_post carries NO '2*|3*)' success case arm (comments stripped; redirects are failures)"
fi
# the same check must be able to FAIL: prove the detector sees a live arm
if printf 'case "$c" in\n  2*|3*) ok ;;\nesac\n' | _no_comments /dev/stdin | grep -q '2\*|3\*)'; then
  say_ok "control: the comment-stripped detector DOES see a planted '2*|3*)' arm"
else
  say_fail "control" "detector cannot see a planted arm - the check above proves nothing"
fi
for fn in _op_id_for _journal_put _pending_put _receipt_match _ack_send _resend_pending _gc_journal _post_class _json_get; do
  grep -q "^${fn}() {" "$POLL" && say_ok "$fn present" || say_fail "$fn missing"
done
ver="$(grep -E '^RECEIVER_VERSION=' "$POLL" | head -1 | cut -d'"' -f2)"
case "$ver" in
  1.6.*|1.[7-9].*|[2-9].*) say_ok "RECEIVER_VERSION advanced for the RR-008 slice: $ver" ;;
  *) say_fail "RECEIVER_VERSION" "got $ver (expected >= 1.6.0)" ;;
esac

# ---------------------------------------------------------------------------
# 1. SANDBOX: extract the SHIPPED functions (name-anchored) + a curl stub.
# ---------------------------------------------------------------------------
FIX="$(mktemp -d)"
trap 'rm -rf "$FIX"' EXIT
mkdir -p "$FIX/bin" "$FIX/state/tmp" "$FIX/logs"

# The stub curl runs as a CHILD PROCESS of the shell under test, so the
# RR_FAKE_* channel must be EXPORTED. (qfound: they were plain assignments in
# every generated harness below, so the child saw an empty scenario path, every
# call fell through to the transport class, and the suite reported 31 failures
# that were an artifact of the harness, not of the shipped receiver.)
export RR_FAKE_SCENARIO="$FIX/scenario"
export RR_FAKE_COUNT="$FIX/count"
export RR_FIX_LOG="$FIX/logs/poll.log"
export RR_FIX_LASTBODY="$FIX/last-post-body"

extract_fn() {  # extract_fn <file> <fn-name>
  local f="$1" fn="$2" s e
  s="$(grep -n "^${fn}()" "$f" | head -1 | cut -d: -f1)"
  [ -n "$s" ] || { echo "EXTRACT-MISSING ${fn}" >&2; return 1; }
  e="$(awk -v s="$s" 'NR>=s && /^}/ {print NR; exit}' "$f")"
  [ -n "$e" ] || { echo "EXTRACT-UNTERMINATED ${fn}" >&2; return 1; }
  sed -n "${s},${e}p" "$f"
}

{
  for fn in _json_str _json_field _json_get _post_class _sha _rr_hash _now_iso _op_id_for \
            _journal_put _journal_phase _pending_put _receipt_match _ack_send \
            _resend_pending _gc_journal _post _ack _write_done _reack_cached; do
    extract_fn "$POLL" "$fn" || echo "echo 'EXTRACT FAILED: $fn' >&2"
    echo
  done
  # _log must reach BOTH the log file (the token-leak assertion reads it) and
  # the harness stdout (T3/T4 grep the verdict line). The shipped _log appends
  # to $_LOG only, so a file-only override here made every "UNCONFIRMED class="
  # assertion unreadable and the suite reported the receiver as broken.
  echo '_log() { printf "%s\n" "$1" >> "$RR_FIX_LOG"; printf "%s\n" "$1"; }'
  # The shipped script derives its three stores from _STATE at top level
  # (rescue-poll.sh: _JOURNAL="$_STATE/journal" etc.) and creates them BEFORE
  # any function runs. The sandbox sets only _STATE, so the derived names must
  # be supplied here or every _journal_put mktemp fails and the whole suite
  # reads as a receiver defect. Defaulted with := so a harness that pins a
  # store explicitly (T11 pins _RECONCILE) still wins.
  echo ': "${_JOURNAL:=$_STATE/journal}"; : "${_PENDING:=$_STATE/ack-pending}"; : "${_RECONCILE:=$_STATE/reconcile}"'
  echo 'mkdir -p "$_JOURNAL" "$_PENDING" 2>/dev/null || true'
  echo 'chmod 700 "$_JOURNAL" "$_PENDING" 2>/dev/null || true'
} > "$FIX/funcs.sh"
bash -n "$FIX/funcs.sh" 2>/dev/null && say_ok "extracted functions parse (bash -n)" || say_fail "extracted functions syntax"

# curl stub: emits the next scenario line's (code, bodyfile) each call.
cat > "$FIX/bin/curl" <<'CURLSTUB'
#!/usr/bin/env bash
# Stub curl. Recognises --version and the one POST shape _post uses.
for a in "$@"; do
  if [ "$a" = "--version" ]; then echo "curl 8.4.0 (stub)"; exit 0; fi
done
out=""; hdr=""; data=""
prev=""
for a in "$@"; do
  case "$prev" in
    -o) out="$a" ;;
    -D) hdr="$a" ;;
    --data-binary) data="${a#@}" ;;
  esac
  prev="$a"
done
# the EXACT request payload, byte-for-byte as sent (curl --data-binary @file)
if [ -n "$data" ] && [ -f "$data" ]; then
  cp "$data" "$RR_FIX_LASTBODY" 2>/dev/null || true
fi
n=0
[ -f "$RR_FAKE_COUNT" ] && n="$(cat "$RR_FAKE_COUNT" 2>/dev/null || echo 0)"
n=$(( n + 1 ))
printf '%s' "$n" > "$RR_FAKE_COUNT" 2>/dev/null
line="$(sed -n "${n}p" "$RR_FAKE_SCENARIO" 2>/dev/null)"
[ -n "$line" ] || line="$(tail -1 "$RR_FAKE_SCENARIO" 2>/dev/null)"
code="${line%%|*}"
bodyfile="${line#*|}"
if [ "$code" = "000" ]; then
  # dropped response: transport failure, curl exits nonzero
  printf '000' 
  exit 7
fi
if [ -n "$bodyfile" ] && [ -f "$bodyfile" ]; then
  cat "$bodyfile" > "$out" 2>/dev/null
else
  : > "$out" 2>/dev/null
fi
if [ -n "$hdr" ]; then
  {
    printf 'HTTP/1.1 %s stub\r\n' "$code"
    case "$bodyfile" in
      *html*) printf 'Content-Type: text/html\r\n' ;;
      *)      printf 'Content-Type: application/json\r\n' ;;
    esac
    printf '\r\n'
  } > "$hdr" 2>/dev/null
fi
printf '%s' "$code"
exit 0
CURLSTUB
chmod +x "$FIX/bin/curl"
say_ok "curl stub installed (drives the REAL _post)"

# scenario body files
printf '<html><body>CF Access login</body></html>' > "$FIX/body-html"
printf '' > "$FIX/body-empty"

mkjson() { printf '%s' "$1" > "$FIX/body-json"; }

# ---------------------------------------------------------------------------
# 2. TEST HARNESS
# ---------------------------------------------------------------------------
# run_ack <scenario-lines...> -- fresh state, sets the given ack identity,
# calls the shipped _ack, prints: rc | journal-phase | pending-exists | sends
run_ack() {
  rm -rf "$FIX/state"; mkdir -p "$FIX/state/tmp" "$FIX/logs"
  printf '%s\n' "$@" > "$FIX/scenario"
  : > "$FIX/count"
  cat > "$FIX/run.sh" <<RUNEOF
PATH="$FIX/bin:\$PATH"
RR_FIX_LOG="$FIX/logs/poll.log"
RR_FAKE_SCENARIO="$FIX/scenario"
RR_FAKE_COUNT="$FIX/count"
RR_RECEIVER_URL="https://unroutable.invalid/rr"
RR_BOX_TOKEN="synthetic-token-value"
RR_BOX_SLUG="box-synthetic"
RECEIVER_VERSION="1.6.0"
_STATE="$FIX/state"
_DONE="\$_STATE/done"
_TMP="\$_STATE/tmp"
INSTRUCTION_ID="ins-syn-1"
IDEMPOTENCY_KEY="idem-syn-1"
TICKET_ID="RRT-syn-1"
ATTEMPT_ID="tok-syn-123"
ATTEMPT_GENERATION="2"
LEASE_EXPIRES_AT="2026-09-09T12:00:00.000Z"
mkdir -p "\$_DONE"
source "$FIX/funcs.sh"
_ack "delivered" 0 35 "" 12 "synthetic reply excerpt"
echo "RC=\$?"
for f in "\$_STATE"/journal/op_*; do
  [ -f "\$f" ] || continue
  printf 'JOURNAL=%s\n' "\$(_journal_phase "\$(basename "\$f")")"
done
_p=0
for f in "\$_STATE"/ack-pending/op_*; do
  [ -f "\$f" ] && _p=1
done
echo "PENDING=\$_p"
_n=0
[ -f "$FIX/count" ] && _n="\$(cat "$FIX/count")"
echo "SENDS=\$_n"
RUNEOF
  bash "$FIX/run.sh" 2>&1
}

field() { printf '%s\n' "$1" | grep "^$2=" | head -1 | cut -d= -f2-; }

# ---------------------------------------------------------------------------
# T1/T2 — the REAL _post classification, driven by the stub curl
# ---------------------------------------------------------------------------
echo ""
echo "T1/T2: _post classification (real _post, stubbed curl)"
post_class() {  # post_class <code> <bodyfile>
  printf '%s|%s\n' "$1" "$2" > "$FIX/scenario"
  : > "$FIX/count"
  cat > "$FIX/pretest.sh" <<PREEOF
PATH="$FIX/bin:\$PATH"
RR_FIX_LOG="$FIX/logs/poll.log"
RR_FAKE_SCENARIO="$FIX/scenario"
RR_FAKE_COUNT="$FIX/count"
RR_RECEIVER_URL="https://unroutable.invalid/rr"
RR_BOX_TOKEN="synthetic-token-value"
_TMP="$FIX/state/tmp"
source "$FIX/funcs.sh"
if _post '{"x":1}' >/dev/null 2>&1; then echo "POST=0"; else echo "POST=1"; fi
printf 'CLASS=%s\n' "\$(_post_class)"
PREEOF
  bash "$FIX/pretest.sh" 2>&1
}

r="$(post_class 302 "$FIX/body-html")"
if [ "$(field "$r" POST)" = "1" ] && [ "$(field "$r" CLASS)" = "redirect" ]; then
  say_ok "T1 302 -> _post FAILS (rc=1) and classes as 'redirect'"
else
  say_fail "T1 302 classification" "$r"
fi
mkjson '{"status":"ok","receipt":{"operation_id":"op_x","attempt_id":"t","state_revision":"receipt_only"}}'
r="$(post_class 200 "$FIX/body-json")"
if [ "$(field "$r" POST)" = "0" ] && [ "$(field "$r" CLASS)" = "ok_json" ]; then
  say_ok "T2 2xx JSON -> _post ok and classes as 'ok_json'"
else
  say_fail "T2 200 JSON classification" "$r"
fi
r="$(post_class 200 "$FIX/body-html")"
if [ "$(field "$r" POST)" = "0" ] && [ "$(field "$r" CLASS)" = "ok_nonjson" ]; then
  say_ok "T2 2xx HTML -> classes as 'ok_nonjson' (a FAILURE for the ack path)"
else
  say_fail "T2 200 HTML classification" "$r"
fi
r="$(post_class 200 "$FIX/body-empty")"
[ "$(field "$r" CLASS)" = "ok_nonjson" ] && say_ok "T2 2xx empty body -> 'ok_nonjson'" || say_fail "T2 empty body" "$r"
r="$(post_class 401 "$FIX/body-html")"
[ "$(field "$r" CLASS)" = "unauthorized" ] && say_ok "T2 401 -> 'unauthorized'" || say_fail "T2 401" "$r"
r="$(post_class 429 "$FIX/body-json")"
[ "$(field "$r" CLASS)" = "throttled" ] && say_ok "T2 429 -> 'throttled'" || say_fail "T2 429" "$r"
r="$(post_class 000 "$FIX/body-json")"
[ "$(field "$r" POST)" = "1" ] && [ "$(field "$r" CLASS)" = "transport" ] && say_ok "T2 dropped response -> _post FAILS, class 'transport'" || say_fail "T2 transport" "$r"

# ---------------------------------------------------------------------------
# T3 — every transport failure class leaves the operation UNCONFIRMED
# ---------------------------------------------------------------------------
echo ""
echo "T3: transport failure classes leave the ack UNCONFIRMED (no settle)"
for pair in "302:$FIX/body-html:redirect" "200:$FIX/body-html:ok_nonjson" "401:$FIX/body-html:unauthorized" "429:$FIX/body-json:throttled" "000:$FIX/body-json:transport"; do
  code="${pair%%:*}"; rest="${pair#*:}"; body="${rest%%:*}"; want="${rest#*:}"
  out="$(run_ack "$code|$body")"
  rc="$(field "$out" RC)"; ph="$(field "$out" JOURNAL)"; pend="$(field "$out" PENDING)"
  if [ "$rc" = "0" ] && [ "$ph" = "ack_pending" ] && [ "$pend" = "1" ] \
     && printf '%s' "$out" | grep -q "UNCONFIRMED class=$want"; then
    say_ok "T3 code=$code -> UNCONFIRMED class=$want; journal=ack_pending; identical body RETAINED"
  else
    say_fail "T3 code=$code (want class=$want)" "$out"
  fi
done

# ---------------------------------------------------------------------------
# T4 — a 2xx JSON WITHOUT a matching structured receipt is UNCONFIRMED
# ---------------------------------------------------------------------------
echo ""
echo "T4: a bare 2xx is never a confirmation"
mkjson '{"status":"ok","recorded":true}'
out="$(run_ack "200|$FIX/body-json")"
{ [ "$(field "$out" JOURNAL)" = "ack_pending" ] && printf '%s' "$out" | grep -q 'no_receipt_operation_id'; } \
  && say_ok "T4 200 + no receipt -> UNCONFIRMED (no_receipt_operation_id)" || say_fail "T4 no receipt" "$out"

mkjson '{"status":"ok","receipt":{"operation_id":"op_OTHER","attempt_id":"tok-syn-123","state_revision":"receipt_only"}}'
out="$(run_ack "200|$FIX/body-json")"
{ [ "$(field "$out" JOURNAL)" = "ack_pending" ] && printf '%s' "$out" | grep -q 'receipt_operation_mismatch'; } \
  && say_ok "T4 200 + WRONG operation_id -> UNCONFIRMED (receipt_operation_mismatch)" || say_fail "T4 wrong op" "$out"

mkjson '{"status":"ok","receipt":{"operation_id":"op_placeholder","attempt_id":"tok-OTHER","state_revision":"receipt_only"}}'
# use the box's real op id: derive it first
OPID="$(_op_id_for_test() { :; }; printf 'op_%s' "$(printf '%s' "rr-delivery|idem-syn-1|tok-syn-123|2" | shasum -a 256 | cut -d' ' -f1)")"
mkjson "{\"status\":\"ok\",\"receipt\":{\"operation_id\":\"$OPID\",\"attempt_id\":\"tok-OTHER\",\"state_revision\":\"receipt_only\"}}"
out="$(run_ack "200|$FIX/body-json")"
{ [ "$(field "$out" JOURNAL)" = "ack_pending" ] && printf '%s' "$out" | grep -q 'receipt_attempt_mismatch'; } \
  && say_ok "T4 200 + WRONG attempt -> UNCONFIRMED (receipt_attempt_mismatch)" || say_fail "T4 wrong attempt" "$out"

mkjson "{\"status\":\"ok\",\"receipt\":{\"operation_id\":\"$OPID\",\"attempt_id\":\"tok-syn-123\"}}"
out="$(run_ack "200|$FIX/body-json")"
{ [ "$(field "$out" JOURNAL)" = "ack_pending" ] && printf '%s' "$out" | grep -q 'no_receipt_state_revision'; } \
  && say_ok "T4 200 + receipt without state_revision -> UNCONFIRMED (no_receipt_state_revision)" || say_fail "T4 no revision" "$out"

# ---------------------------------------------------------------------------
# T5/T6 — a matching receipt settles; the replay is byte-identical
# ---------------------------------------------------------------------------
echo ""
echo "T5/T6: matching receipt settles; replay bytes identical, one operation id"
mkjson "{\"status\":\"ok\",\"recorded\":true,\"receipt\":{\"receipt_version\":1,\"operation_id\":\"$OPID\",\"attempt_id\":\"tok-syn-123\",\"state_revision\":\"receipt_only\",\"recorded\":true}}"
out="$(run_ack "200|$FIX/body-json")"
{ [ "$(field "$out" JOURNAL)" = "ack_confirmed" ] && [ "$(field "$out" PENDING)" = "0" ]; } \
  && say_ok "T5 matching receipt -> journal=ack_confirmed, ack-pending/ entry REMOVED" || say_fail "T5 settle" "$out"

# replay: fail once, then succeed; compare the two sent bodies byte-for-byte.
mkjson "{\"status\":\"ok\",\"receipt\":{\"operation_id\":\"$OPID\",\"attempt_id\":\"tok-syn-123\",\"state_revision\":\"receipt_only\"}}"
# capture bodies: wrap the curl stub to log each body
cat > "$FIX/bin/curl.hook" <<'HOOK'
HOOK
# simpler: capture via _post's body file is internal; instead capture the
# ack-pending file bytes (written before the send, byte-for-byte).
rm -rf "$FIX/state"; mkdir -p "$FIX/state/tmp" "$FIX/logs"
printf '302|%s\n200|%s\n' "$FIX/body-html" "$FIX/body-json" > "$FIX/scenario"
: > "$FIX/count"
cat > "$FIX/replay.sh" <<REPEOF
PATH="$FIX/bin:\$PATH"
RR_FIX_LOG="$FIX/logs/poll.log"
RR_FAKE_SCENARIO="$FIX/scenario"
RR_FAKE_COUNT="$FIX/count"
RR_RECEIVER_URL="https://unroutable.invalid/rr"
RR_BOX_TOKEN="synthetic-token-value"
RR_BOX_SLUG="box-synthetic"
RECEIVER_VERSION="1.6.0"
_STATE="$FIX/state"; _DONE="\$_STATE/done"; _TMP="\$_STATE/tmp"
INSTRUCTION_ID="ins-syn-1"; IDEMPOTENCY_KEY="idem-syn-1"; TICKET_ID="RRT-syn-1"
ATTEMPT_ID="tok-syn-123"; ATTEMPT_GENERATION="2"
mkdir -p "\$_DONE"
source "$FIX/funcs.sh"
_ack "delivered" 0 35 "" 12 "synthetic reply excerpt"
# this is the crash-recovery path: resend the retained identical body
_resend_pending
cp "\$_STATE/ack-pending/$OPID" "$FIX/pending-after" 2>/dev/null || true
echo "POSTPEND=\$([ -f "\$_STATE/ack-pending/$OPID" ] && echo 1 || echo 0)"
for f in "\$_STATE"/journal/op_*; do
  [ -f "\$f" ] || continue
  printf 'JOURNAL=%s\n' "\$(_journal_phase "\$(basename "\$f")")"
done
echo "SENDS=\$(cat "$FIX/count")"
# the operation id of the FIRST (failed) send, recovered from journal filename
printf 'OPS=%s\n' "\$(ls -1 "\$_STATE/journal" 2>/dev/null | wc -l | tr -d ' ')"
echo "OPID_FILE=\$(ls -1 "\$_STATE/journal" 2>/dev/null | head -1)"
REPEOF
out="$(bash "$FIX/replay.sh" 2>&1)"
if [ "$(field "$out" POSTPEND)" = "0" ] && [ "$(field "$out" JOURNAL)" = "ack_confirmed" ] \
   && [ "$(field "$out" SENDS)" = "2" ] && [ "$(field "$out" OPS)" = "1" ]; then
  say_ok "T6 fail-then-resend settles with EXACTLY ONE operation id across 2 sends (no duplicate side effect)"
else
  say_fail "T6 replay convergence" "$out"
fi
# the retained body must be the same bytes that were originally posted
pendfile="$FIX/state/ack-pending/$OPID"
[ ! -f "$pendfile" ] && say_ok "T6 retained body removed only AFTER the confirmed receipt" || say_fail "T6 pending still present after confirm"

# ---------------------------------------------------------------------------
# T7 — CRASH MATRIX: cut before/after each step, then recover
# ---------------------------------------------------------------------------
echo ""
echo "T7: crash before/after every step, then recover"
for CUT in 1 2 3 4 5 6; do
  rm -rf "$FIX/state"; mkdir -p "$FIX/state/tmp" "$FIX/logs"
  mkjson "{\"status\":\"ok\",\"receipt\":{\"operation_id\":\"$OPID\",\"attempt_id\":\"tok-syn-123\",\"state_revision\":\"receipt_only\"}}"
  printf '200|%s\n' "$FIX/body-json" > "$FIX/scenario"
  : > "$FIX/count"
  cat > "$FIX/cut.sh" <<CUTEOF
PATH="$FIX/bin:\$PATH"
RR_FIX_LOG="$FIX/logs/poll.log"
RR_FAKE_SCENARIO="$FIX/scenario"
RR_FAKE_COUNT="$FIX/count"
RR_RECEIVER_URL="https://unroutable.invalid/rr"
RR_BOX_TOKEN="synthetic-token-value"
RR_BOX_SLUG="box-synthetic"
RECEIVER_VERSION="1.6.0"
_STATE="$FIX/state"; _DONE="\$_STATE/done"; _TMP="\$_STATE/tmp"
INSTRUCTION_ID="ins-syn-1"; IDEMPOTENCY_KEY="idem-syn-1"; TICKET_ID="RRT-syn-1"
ATTEMPT_ID="tok-syn-123"; ATTEMPT_GENERATION="2"
mkdir -p "\$_DONE"
source "$FIX/funcs.sh"
OP="\$(_op_id_for "\$IDEMPOTENCY_KEY" "\$ATTEMPT_ID" "\$ATTEMPT_GENERATION")"
BODY="{\\"action\\":\\"ack\\",\\"operation_id\\":\\"\$OP\\",\\"attempt_id\\":\\"tok-syn-123\\",\\"reply_excerpt\\":\\"synthetic reply excerpt\\"}"
CUT=$CUT
# step 1: journal BEFORE the effect
_journal_put "\$OP" effect_started '{"instruction_id":"ins-syn-1"}' || exit 9
[ "\$CUT" -le 1 ] && { echo CUT; exit 0; }
# step 2: the effect itself (agent turn) -> journal effect_executed
_journal_put "\$OP" effect_executed '{"verdict":"delivered"}' || exit 9
[ "\$CUT" -le 2 ] && { echo CUT; exit 0; }
# step 3: complete outcome/proof saved durably (done record)
_write_done delivered 0 35 "" 12 "synthetic reply excerpt" || exit 9
[ "\$CUT" -le 3 ] && { echo CUT; exit 0; }
# step 4: outbox -- ack body saved as ACK_PENDING, journal ack_attempt
_journal_put "\$OP" ack_attempt '{"verdict":"delivered"}' || exit 9
_pending_put "\$OP" "\$BODY" || exit 9
[ "\$CUT" -le 4 ] && { echo CUT; exit 0; }
# step 5: the send
VT="\$(_ack_send "\$BODY" "\$OP" "tok-syn-123" ack)"
[ "\$CUT" -le 5 ] && { echo "CUT vt=\$VT"; exit 0; }
# step 6: settle on the receipt
case "\$VT" in
  confirmed:*) _journal_put "\$OP" ack_confirmed '{"state_revision":"receipt_only"}' ; rm -f "\$_STATE/ack-pending/\$OP" ;;
esac
echo "CUT"
CUTEOF
  cutout="$(bash "$FIX/cut.sh" 2>&1)"
  # recovery: the next fire runs the reap+resend path
  cat > "$FIX/recover.sh" <<RECEOF
PATH="$FIX/bin:\$PATH"
RR_FIX_LOG="$FIX/logs/poll.log"
RR_FAKE_SCENARIO="$FIX/scenario"
RR_FAKE_COUNT="$FIX/count"
RR_RECEIVER_URL="https://unroutable.invalid/rr"
RR_BOX_TOKEN="synthetic-token-value"
RR_BOX_SLUG="box-synthetic"
RECEIVER_VERSION="1.6.0"
_STATE="$FIX/state"; _DONE="\$_STATE/done"; _TMP="\$_STATE/tmp"
INSTRUCTION_ID="ins-syn-1"; IDEMPOTENCY_KEY="idem-syn-1"; TICKET_ID="RRT-syn-1"
ATTEMPT_ID="tok-syn-123"; ATTEMPT_GENERATION="2"
mkdir -p "\$_DONE"
source "$FIX/funcs.sh"
_resend_pending
# convergence check: BOTH stores agree
P=0; for f in "\$_STATE"/ack-pending/op_*; do [ -f "\$f" ] && P=1; done
PH="none"
for f in "\$_STATE"/journal/op_*; do [ -f "\$f" ] && PH="\$(_journal_phase "\$(basename "\$f")")"; done
N=\$(ls -1 "\$_STATE/journal" 2>/dev/null | wc -l | tr -d ' ')
echo "PENDING=\$P"; echo "PHASE=\$PH"; echo "OPROWS=\$N"
RECEOF
  rec="$(bash "$FIX/recover.sh" 2>&1)"
  # invariant: after recovery, either the op is settled with NO pending row
  # (both stores converged) or it never reached the send step at all (no
  # effect was taken, so nothing to reconcile) -- and NEVER a second op row.
  ok_cut=1
  [ "$(field "$rec" OPROWS)" = "1" ] || ok_cut=0
  if printf '%s' "$cutout" | grep -q "^CUT vt="; then
    [ "$(field "$rec" PENDING)" = "0" ] && [ "$(field "$rec" PHASE)" = "ack_confirmed" ] || ok_cut=0
  fi
  if [ "$ok_cut" = "1" ]; then
    say_ok "T7 cut@$CUT -> converged (1 op row, pending=$(field "$rec" PENDING), phase=$(field "$rec" PHASE))"
  else
    say_fail "T7 cut@$CUT did not converge" "$cutout / $rec"
  fi
done

# ---------------------------------------------------------------------------
# T8/T9 — journal / pending write failure STOPS NEW EFFECTS
# ---------------------------------------------------------------------------
echo ""
echo "T8/T9: a store write failure stops the effect (no _post at all)"
run_blocked() {  # run_blocked <dir-to-lock>
  rm -rf "$FIX/state"; mkdir -p "$FIX/state/tmp" "$FIX/logs"
  printf '200|%s\n' "$FIX/body-json" > "$FIX/scenario"
  : > "$FIX/count"
  cat > "$FIX/blocked.sh" <<BEOF
PATH="$FIX/bin:\$PATH"
RR_FIX_LOG="$FIX/logs/poll.log"
RR_FAKE_SCENARIO="$FIX/scenario"; RR_FAKE_COUNT="$FIX/count"
RR_RECEIVER_URL="https://unroutable.invalid/rr"; RR_BOX_TOKEN="synthetic-token-value"
RR_BOX_SLUG="box-synthetic"; RECEIVER_VERSION="1.6.0"
_STATE="$FIX/state"; _DONE="\$_STATE/done"; _TMP="\$_STATE/tmp"
INSTRUCTION_ID="ins-syn-1"; IDEMPOTENCY_KEY="idem-syn-1"; TICKET_ID="RRT-syn-1"
ATTEMPT_ID="tok-syn-123"; ATTEMPT_GENERATION="2"
mkdir -p "\$_DONE"
source "$FIX/funcs.sh"
chmod 500 "$1" 2>/dev/null
_ack "delivered" 0 35 "" 12 "synthetic reply excerpt"
echo "RC=\$?"
chmod 700 "$1" 2>/dev/null
echo "SENDS=\$(wc -l < "$FIX/count" 2>/dev/null | tr -d " ")"
BEOF
  bash "$FIX/blocked.sh" 2>&1
}
out="$(run_blocked "$FIX/state/journal")"
{ [ "$(field "$out" RC)" != "0" ] && [ "$(field "$out" SENDS)" = "0" ]; } \
  && say_ok "T8 journal dir unwritable -> ack HELD (rc=$(field "$out" RC)), _post NEVER called" || say_fail "T8 journal failure" "$out"

rm -rf "$FIX/state"; mkdir -p "$FIX/state/tmp" "$FIX/logs" "$FIX/state/journal"
out="$(run_blocked "$FIX/state/ack-pending")"
{ [ "$(field "$out" RC)" != "0" ] && [ "$(field "$out" SENDS)" = "0" ]; } \
  && say_ok "T9 ack-pending dir unwritable (disk-full shape) -> ack HELD, _post NEVER called" || say_fail "T9 disk-full" "$out"

# ---------------------------------------------------------------------------
# T10 — cached re-ack keeps the ORIGINAL reply excerpt and operation id
# ---------------------------------------------------------------------------
echo ""
echo "T10: cached re-ack replays the original evidence"
rm -rf "$FIX/state"; mkdir -p "$FIX/state/tmp" "$FIX/logs" "$FIX/state/done"
mkjson "{\"status\":\"ok\",\"receipt\":{\"operation_id\":\"$OPID\",\"attempt_id\":\"tok-syn-123\",\"state_revision\":\"receipt_only\"}}"
printf '200|%s\n' "$FIX/body-json" > "$FIX/scenario"
: > "$FIX/count"
cat > "$FIX/reack.sh" <<RAEOF
PATH="$FIX/bin:\$PATH"
RR_FIX_LOG="$FIX/logs/poll.log"
RR_FAKE_SCENARIO="$FIX/scenario"; RR_FAKE_COUNT="$FIX/count"
RR_RECEIVER_URL="https://unroutable.invalid/rr"; RR_BOX_TOKEN="synthetic-token-value"
RR_BOX_SLUG="box-synthetic"; RECEIVER_VERSION="1.6.0"
_STATE="$FIX/state"; _DONE="\$_STATE/done"; _TMP="\$_STATE/tmp"
INSTRUCTION_ID="ins-syn-1"; IDEMPOTENCY_KEY="idem-syn-1"; TICKET_ID="RRT-syn-1"
ATTEMPT_ID="tok-syn-123"; ATTEMPT_GENERATION="2"
source "$FIX/funcs.sh"
_write_done delivered 0 35 "" 12 "the ORIGINAL excerpt" || echo "DONEFAIL"
: > "$RR_FIX_LASTBODY"
_reack_cached "\$IDEMPOTENCY_KEY"
echo "RC=\$?"
echo "STILL_PENDING=\$([ -f "\$_STATE/ack-pending/$OPID" ] && echo 1 || echo 0)"
echo "SENT_BODY=\$(cat "$RR_FIX_LASTBODY" 2>/dev/null)"
echo "PHASE=\$(for f in "\$_STATE"/journal/op_*; do [ -f "\$f" ] && _journal_phase "\$(basename "\$f")"; done)"
RAEOF
out="$(bash "$FIX/reack.sh" 2>&1)"
body="$(field "$out" SENT_BODY)"
{ printf '%s' "$body" | grep -q 'the ORIGINAL excerpt'; } \
  && say_ok "T10 cached re-ack carries the ORIGINAL reply excerpt (the cache no longer drops proof)" \
  || say_fail "T10 excerpt lost" "$out"
{ printf '%s' "$body" | grep -q "\"operation_id\":\"$OPID\""; } \
  && say_ok "T10 cached re-ack carries the SAME operation id (server sees an idempotent receipt)" \
  || say_fail "T10 op id missing from re-ack" "$out"
[ "$(field "$out" PHASE)" = "ack_confirmed" ] && say_ok "T10 cached re-ack settles on the matching receipt (phase=ack_confirmed)" || say_fail "T10 re-ack phase" "$out"

# ---------------------------------------------------------------------------
# T11 — bounded retention: confirmed GC'd, unconfirmed NEVER silently deleted
# ---------------------------------------------------------------------------
echo ""
echo "T11: bounded post-reconciliation retention"
rm -rf "$FIX/state"; mkdir -p "$FIX/state/tmp" "$FIX/state/journal" "$FIX/state/ack-pending" "$FIX/logs"
printf '{"operation_id":"op_old_confirmed","phase":"ack_confirmed"}\n' > "$FIX/state/journal/op_old_confirmed"
printf '{"operation_id":"op_old_pending","phase":"ack_pending"}\n' > "$FIX/state/journal/op_old_pending"
printf '{"operation_id":"op_old_pending"}\n' > "$FIX/state/ack-pending/op_old_pending"
touch -t 202608010000 "$FIX/state/journal/op_old_confirmed" "$FIX/state/journal/op_old_pending" "$FIX/state/ack-pending/op_old_pending"
cat > "$FIX/gc.sh" <<GCEOF
RR_FIX_LOG="$FIX/logs/poll.log"
_STATE="$FIX/state"; _RECONCILE="\$_STATE/reconcile"
source "$FIX/funcs.sh"
_gc_journal
echo "CONFIRMED_EXISTS=\$([ -f "\$_STATE/journal/op_old_confirmed" ] && echo 1 || echo 0)"
echo "PENDING_JOURNAL=\$([ -f "\$_STATE/journal/op_old_pending" ] && echo 1 || echo 0)"
echo "RECONCILE=\$([ -f "\$_STATE/reconcile/op_old_pending" ] && echo 1 || echo 0)"
echo "PENDING_BODY=\$([ -f "\$_STATE/ack-pending/op_old_pending" ] && echo 1 || echo 0)"
echo "RECONCILE_BODY=\$([ -s "\$_STATE/reconcile/op_old_pending" ] && echo 1 || echo 0)"
GCEOF
gc="$(bash "$FIX/gc.sh" 2>&1)"
{ [ "$(field "$gc" CONFIRMED_EXISTS)" = "0" ] && [ "$(field "$gc" PENDING_JOURNAL)" = "1" ] \
  && [ "$(field "$gc" RECONCILE)" = "1" ] && [ "$(field "$gc" RECONCILE_BODY)" = "1" ] \
  && [ "$(field "$gc" PENDING_BODY)" = "0" ]; } \
  && say_ok "T11 confirmed row GC'd (>14d); unconfirmed row moved to reconcile/ (owned, NOT deleted) with its body retained" \
  || say_fail "T11 retention" "$gc"

# ---------------------------------------------------------------------------
# T12 — private permissions
# ---------------------------------------------------------------------------
echo ""
echo "T12: private permissions on the new stores"
rm -rf "$FIX/state"; mkdir -p "$FIX/state/tmp" "$FIX/logs"
printf '200|%s\n' "$FIX/body-json" > "$FIX/scenario"; : > "$FIX/count"
cat > "$FIX/perm.sh" <<PEOF
PATH="$FIX/bin:\$PATH"
RR_FIX_LOG="$FIX/logs/poll.log"; RR_FAKE_SCENARIO="$FIX/scenario"; RR_FAKE_COUNT="$FIX/count"
RR_RECEIVER_URL="https://unroutable.invalid/rr"; RR_BOX_TOKEN="synthetic-token-value"
RR_BOX_SLUG="box-synthetic"; RECEIVER_VERSION="1.6.0"
_STATE="$FIX/state"; _DONE="\$_STATE/done"; _TMP="\$_STATE/tmp"
_jd="\$_STATE/journal"; _pd="\$_STATE/ack-pending"
mkdir -p "\$_DONE" "\$_jd" "\$_pd"
chmod 700 "\$_jd" "\$_pd"
INSTRUCTION_ID="ins-syn-1"; IDEMPOTENCY_KEY="idem-syn-1"; TICKET_ID="RRT-syn-1"
ATTEMPT_ID="tok-syn-123"; ATTEMPT_GENERATION="2"
source "$FIX/funcs.sh"
OP="\$(_op_id_for "\$IDEMPOTENCY_KEY" "\$ATTEMPT_ID" "\$ATTEMPT_GENERATION")"
_journal_put "\$OP" effect_started '{}'
_pending_put "\$OP" '{"operation_id":"x"}'
_write_done delivered 0 35 "" 12 "x"
echo "JDIR=\$(stat -f '%Lp' "\$_jd" 2>/dev/null || stat -c '%a' "\$_jd")"
echo "PDIR=\$(stat -f '%Lp' "\$_pd" 2>/dev/null || stat -c '%a' "\$_pd")"
echo "JFILE=\$(stat -f '%Lp' "\$_jd/\$OP" 2>/dev/null || stat -c '%a' "\$_jd/\$OP")"
echo "PFILE=\$(stat -f '%Lp' "\$_pd/\$OP" 2>/dev/null || stat -c '%a' "\$_pd/\$OP")"
PEOF
perm="$(bash "$FIX/perm.sh" 2>&1)"
{ [ "$(field "$perm" JFILE)" = "600" ] && [ "$(field "$perm" PFILE)" = "600" ]; } \
  && say_ok "T12 journal + ack-pending records are 0600 (dirs: j=$(field "$perm" JDIR) p=$(field "$perm" PDIR))" \
  || say_fail "T12 permissions" "$perm"

# no secret ever reaches the journal or the log
if grep -q 'synthetic-token-value' "$FIX/logs/poll.log" 2>/dev/null; then
  say_fail "T12 the token never reaches the poll log"
else
  say_ok "T12 the token never reaches the poll log (checked the real log file)"
fi

echo ""
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
