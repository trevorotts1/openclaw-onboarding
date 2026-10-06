#!/usr/bin/env bash
# tests/rescue/RR-028/test_safe_probe.sh — RR-028 gate (ONB receiver).
#
# Pins required behaviour 7: "Installer success means files installed. Receiver
# readiness is a SEPARATE claim requiring a SAFE TEST CLAIM/RECEIPT in the
# INTENDED RUNTIME."
#
# What is asserted, always from what the tool PRINTED plus what the box and the
# loopback receiver OBSERVED:
#   * only a structured no-work 2xx from the intended runtime produces a
#     receipt, and only a matching receipt produces VERIFIED;
#   * a capacity-0 dry-run probe that is handed an INSTRUCTION is REFUSED:
#     no agent turn runs and NO ack is sent (an ack would be a verdict about a
#     turn that never ran) — the box stays SCHEDULED;
#   * an unstructured 2xx is NOT a confirmation (RR-008);
#   * a receipt from a different RUNTIME cannot verify the intended one;
#   * the credential never appears in any argv: it rides a 0600 `-H @file`
#     staged in a 0700 dir and is cleaned up.
#
# Hermetic: temp dirs, synthetic slug/token, loopback HTTP only.
set -u

if [ -n "${BASH_SOURCE:-}" ]; then _HERE_SRC="${BASH_SOURCE[0]}"; else _HERE_SRC="$0"; fi
HERE="$(cd "$(dirname "$_HERE_SRC")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
RR028_REPO="$REPO"
export RR028_REPO

PASS=0; FAIL=0; SKIP=0
ok()   { PASS=$((PASS+1)); echo "  ok $1"; }
bad()  { FAIL=$((FAIL+1)); echo "  FAIL $1 ${2:-}"; }
skip() { SKIP=$((SKIP+1)); echo "  SKIP $1 ${2:-}"; }

. "$HERE/lib-readiness-harness.sh"
rr028_require_files

echo "== RR-028: safe test claim + receipt + intended runtime =="

WORK="$(mktemp -d "${TMPDIR:-/tmp}/rr028-probe.XXXXXX")"
RR028_DONE=""
# M-5: reap EVERY receiver this battery spawned (not just the last pid) and
# remove $WORK on ANY exit — including a killed/timed-out run, which is when
# the leak used to happen. RR028_PIDFILE_BOX names the box whose registry (and
# stub processes) this battery owns; the registry lives inside $WORK.
RR028_PIDFILE_BOX="$WORK"
# An ALREADY-EXPORTED RR028_PIDFILE wins, so a reviewer can neuter the registry
# (Z-5 evidence) without patching this battery.
RR028_PIDFILE="${RR028_PIDFILE:-$WORK/rr028-receivers.pid}"
trap 'rr028_cleanup' EXIT
trap 'rr028_cleanup; exit 130' INT
trap 'rr028_cleanup; exit 143' TERM

TOK="tok-synthetic-rr028-probe"
matching_job() {
  _box="$1"; _id="${2:-1}"
  _cmd="sh $_box/.openclaw/skills/65-rescue-receiver/rescue-poll.sh"
  printf '{"id":"%s","name":"rescue-rr-box-poll","enabled":true,"schedule":{"kind":"cron","expr":"*/2 * * * *"},"payload":{"kind":"command","command":"%s"},"delivery":{"mode":"none"}}' "$_id" "$_cmd"
}

BOX=""; PORT=""; STATE=""; REASON=""; RC=0
new_box() {  # new_box <name> <port-offset> <mode> [token] ; starts a receiver of that mode
  BOX="$WORK/$1"
  rr028_make_box "$BOX"
  PORT="$(rr028_port "$2")"
  printf 'RR_RECEIVER_URL=http://127.0.0.1:%s/rr\nRR_BOX_TOKEN="%s"\nRR_BOX_SLUG=box-synthetic\n' "$PORT" "${3:-$TOK}" \
    > "$BOX/.openclaw/secrets/.env"
  chmod 600 "$BOX/.openclaw/secrets/.env"
  rr028_job "$BOX" "$(matching_job "$BOX")"
  RR028_STDERR="$BOX/probe.err"
  : > "$RR028_STDERR"
  rr028_start_receiver "$BOX" "$PORT" "${3:-no_work}" || bad "receiver stub failed to start (${3:-no_work})"
}
state_of() {
  rr028_readiness "$BOX" --json
  RC=$RR028_RC
  STATE="$(rr028_field "$RR028_OUT" state)"
  REASON="$(rr028_field "$RR028_OUT" reason)"
}
receipt_path() {  # receipt_path <digest>
  printf '%s/.openclaw/state/rr-receiver/readiness/receipt-%s.json' "$BOX" "$1"
}

# ---------------------------------------------------------------------------
# 1. CONTROL — a structured no-work probe produces a matching receipt.
# ---------------------------------------------------------------------------
echo "--- 1. control: a structured no-work probe verifies ---"
new_box box-ok 1
state_of
[ "$STATE" = "SCHEDULED" ] && ok "control: scheduled, not yet verified" || bad "control pre-state" "$STATE/$REASON"
DG="$(rr028_field "$RR028_OUT" digest)"
rr028_readiness "$BOX" --probe >"$BOX/probe.out" 2>"$BOX/probe.err"
PROBE_RC=$?
state_of
[ "$PROBE_RC" = "0" ] && [ "$STATE" = "VERIFIED" ] && [ "$REASON" = "ready_receipt_verified" ] \
  && ok "--probe exit 0 and state VERIFIED (reason=$REASON)" \
  || bad "probe did not verify" "rc=$PROBE_RC state=$STATE/$REASON"
[ -f "$(receipt_path "$DG")" ] && ok "the receipt is keyed by the desired-config digest" \
  || bad "receipt file missing for digest $DG"
# Portable mode lookup. `stat -f '%Lp'` is BSD/macOS and `stat -c '%a'` is GNU, but GNU's
# `stat -f` does NOT fail -- it prints filesystem status -- so a `||` fallback can never fire
# and the mode silently reads empty on Linux. Detect the dialect once instead. (CI runs Ubuntu;
# this bug made two assertions report "mode=" with no value while passing on macOS.)
_st_mode() {
  # Try GNU first and CAPTURE -- do not call twice, and do not rely on `||`, because GNU's
  # `stat -f` succeeds while printing filesystem status, which is what silently yielded an
  # empty mode on CI. A successful `-c '%a'` prints the octal mode; anything else falls back.
  _m="$(stat -c '%a' "$1" 2>/dev/null)" && [ -n "$_m" ] && { printf '%s\n' "$_m"; return 0; }
  stat -f '%Lp' "$1"
}

if receipt_mode="$(_st_mode "$(receipt_path "$DG")")"; then
  [ "$receipt_mode" = "600" ] && ok "receipt is 0600" || bad "receipt mode=$receipt_mode (expected 600)"
else
  skip "receipt mode probe unavailable on this host"
fi
dir_mode="$(_st_mode "$BOX/.openclaw/state/rr-receiver/readiness")"
[ "$dir_mode" = "700" ] && ok "readiness dir is 0700" || bad "readiness dir mode=$dir_mode (expected 700)"
grep -q '"agent_turns":0' "$(receipt_path "$DG")" \
  && ok "receipt records ZERO agent turns" || bad "receipt does not record a zero-turn claim"
grep -q '"acks_sent":0' "$(receipt_path "$DG")" \
  && ok "receipt records ZERO acks" || bad "receipt does not record a zero-ack claim"
grep -q "^REQ POST" "$BOX/receiver.log" \
  && ok "the receiver observably received the probe (the assertion is not vacuous)" \
  || bad "receiver log empty — the probe never left the box"
grep -q '"capacity":0' "$BOX/receiver.log" \
  && ok "the probe claim carried capacity 0 (asks for no work)" || bad "probe body missing capacity 0"
grep -q '"mode":"dry_run"' "$BOX/receiver.log" \
  && ok "the probe claim carried mode dry_run (cannot be a delivery)" || bad "probe body missing dry_run"
if rr028_argv_blocks "$BOX" | grep -q -e '^agent' -e 'agent\x1f'; then
  bad "the probe invoked an openclaw agent command"
else
  ok "the probe started NO agent turn (no agent command in the CLI call log)"
fi

# ---------------------------------------------------------------------------
# 2. An INSTRUCTION returned to a probe is REFUSED: no turn, no ack, no receipt
# ---------------------------------------------------------------------------
echo "--- 2. an instruction handed to a probe is refused ---"
new_box box-ins 2 instruction
DG2="$(rr028_readiness "$BOX" --json >/dev/null 2>&1; rr028_field "$RR028_OUT" digest)"
rr028_readiness "$BOX" --probe >"$BOX/probe.out" 2>"$BOX/probe.err"
PROBE_RC=$?
state_of
[ "$PROBE_RC" = "1" ] && [ "$STATE" = "SCHEDULED" ] && [ "$REASON" = "ready_receipt_absent" ] \
  && ok "an instruction to a capacity-0 probe: probe FAILS, box stays SCHEDULED" \
  || bad "probe accepted/reported an instruction" "rc=$PROBE_RC state=$STATE/$REASON"
[ -f "$(receipt_path "$DG2")" ] && bad "a receipt was written for an instruction response" \
  || ok "no receipt written when the receiver handed back work"
grep -qi 'refus' "$BOX/probe.err" "$BOX/stderr.txt" "$BOX/probe.out" \
  && ok "the refusal is stated (no agent turn, no ack, no receipt)" || bad "refusal not reported" "$(head -2 "$BOX/stderr.txt" 2>/dev/null)"
N_ACK="$(grep -c '"action":"ack"' "$BOX/receiver.log" 2>/dev/null || true)"
[ "${N_ACK:-0}" = "0" ] && ok "NO ack was sent (a verdict about a turn that never ran is a lie)" \
  || bad "$N_ACK ack(s) sent for a refused probe"
N_REQ="$(grep -c '^REQ POST' "$BOX/receiver.log" 2>/dev/null || true)"
[ "${N_REQ:-0}" = "1" ] && ok "exactly one request was made (no retry loop, no delivery attempt)" \
  || bad "probe made $N_REQ requests"
rr028_argv_blocks "$BOX" | grep -q -e '^agent' -e 'agent\x1f' \
  && bad "a refused probe still ran an agent turn" \
  || ok "no agent turn ran for the refused instruction"

# ---------------------------------------------------------------------------
# 3. Every non-no-work outcome is NOT a confirmation
# ---------------------------------------------------------------------------
echo "--- 3. non-no-work outcomes never verify ---"
for case in "box-unstructured 3 unstructured" "box-401 4 unauthorized" "box-302 5 redirect"; do
  set -- $case
  new_box "$1" "$2" "$3"
  rr028_readiness "$BOX" --json >/dev/null 2>&1
  D="$(rr028_field "$RR028_OUT" digest)"
  rr028_readiness "$BOX" --probe >"$BOX/probe.out" 2>"$BOX/probe.err"
  PRC=$?
  state_of
  [ "$PRC" != "0" ] && [ "$STATE" = "SCHEDULED" ] \
    && ok "$3 response: NOT verified (state=$STATE rc=$PRC)" \
    || bad "$3 response verified" "state=$STATE rc=$PRC reason=$REASON"
  [ -f "$(receipt_path "$D")" ] && bad "$3 response wrote a receipt" || ok "$3 response: no receipt written"
done
# Transport failure: nothing is listening on the port.
BOX="$WORK/box-dead"
rr028_make_box "$BOX"
printf 'RR_RECEIVER_URL=http://127.0.0.1:9/rr\nRR_BOX_TOKEN="%s"\nRR_BOX_SLUG=box-synthetic\n' "$TOK" \
  > "$BOX/.openclaw/secrets/.env"; chmod 600 "$BOX/.openclaw/secrets/.env"
rr028_job "$BOX" "$(matching_job "$BOX")"
rr028_readiness "$BOX" --json >/dev/null 2>&1
D="$(rr028_field "$RR028_OUT" digest)"
rr028_readiness "$BOX" --probe >"$BOX/probe.out" 2>"$BOX/probe.err"
PRC=$?
state_of
[ "$PRC" != "0" ] && [ "$STATE" = "SCHEDULED" ] \
  && ok "transport failure: NOT verified (state=$STATE)" || bad "transport failure verified" "$STATE/$PRC"
[ -f "$(receipt_path "$D")" ] && bad "transport failure wrote a receipt" || ok "transport failure: no receipt written"

# ---------------------------------------------------------------------------
# 4. The INTENDED RUNTIME gates the receipt
# ---------------------------------------------------------------------------
echo "--- 4. the receipt is bound to the intended runtime ---"
new_box box-runtime 6
rr028_readiness "$BOX" --probe >/dev/null 2>&1
state_of
[ "$STATE" = "VERIFIED" ] && ok "verified in the runtime it was probed in" || bad "runtime control" "$STATE/$REASON"
RR028_TARGET_ID="ai.openclaw.gateway.OTHER" state_of
[ "$STATE" = "SCHEDULED" ] && [ "$REASON" = "ready_receipt_foreign_runtime" ] \
  && ok "the SAME box under a different intended runtime is NOT verified (reason=$REASON)" \
  || bad "foreign runtime accepted" "$STATE/$REASON"
RR028_TARGET_ID="ai.openclaw.gateway" state_of
[ "$STATE" = "VERIFIED" ] && ok "control: back on the probed runtime it verifies again" \
  || bad "control restore" "$STATE/$REASON"

# ---------------------------------------------------------------------------
# 5. CREDENTIAL DISCIPLINE — argv, leftovers, and the wire
# ---------------------------------------------------------------------------
echo "--- 5. the credential never enters argv ---"
new_box box-cred 7
# A recording wrapper in FRONT of the real curl: it sees exactly the argv the
# probe builds, then delegates.
REAL_CURL="$(command -v curl)"
cat > "$BOX/bin/curl" <<CREEOF
#!/usr/bin/env bash
printf '%s\n' "\$@" > "$BOX/curl-argv.txt"
exec "$REAL_CURL" "\$@"
CREEOF
chmod +x "$BOX/bin/curl"
rr028_readiness "$BOX" --probe >/dev/null 2>&1
state_of
[ "$STATE" = "VERIFIED" ] && ok "probe verified through the recording curl (control)" \
  || bad "probe failed with the recording curl" "$STATE/$REASON"
if [ -s "$BOX/curl-argv.txt" ]; then
  ok "the recording curl observed the real argv (observer works)"
else
  bad "curl argv was not recorded — the credential assertion below cannot fail"
fi
grep -qF "$TOK" "$BOX/curl-argv.txt" && bad "TOKEN APPEARED IN curl ARGV" \
  || ok "the token value never appears in curl argv"
grep -qx -- '-H' "$BOX/curl-argv.txt" && grep -q '^@' "$BOX/curl-argv.txt" \
  && ok "the credential rides a 0600 -H @file header file (not argv)" \
  || bad "no header file argument found"
HDR_PATH="$(grep '^@' "$BOX/curl-argv.txt" | head -1 | sed 's/^@//')"
if [ -n "$HDR_PATH" ]; then
  [ -e "$HDR_PATH" ] && bad "the credential header file was left on disk ($HDR_PATH)" \
    || ok "the credential header file is removed after the probe"
fi
# Nothing else on the box may carry the token either (the store itself is the
# only legitimate holder).
LEAKS="$(grep -rlF "$TOK" "$BOX" 2>/dev/null | grep -v '/secrets/.env$' || true)"
[ -z "$LEAKS" ] && ok "the token appears in NO file outside the enrollment store" \
  || bad "token leaked into: $LEAKS"
# The probe DID authenticate — so the file path works, it is not vacuous.
grep -q 'HDR X-RR-Box-Token present' "$BOX/receiver.log" \
  && ok "control: the receiver SAW the credential header (the file path works)" \
  || bad "the receiver never saw the credential header"

# ---------------------------------------------------------------------------
# 6. M-4: the probe's SUCCESS LINE must not overstate what it proved
#
# The probe can prove exactly one thing: the receiver RETURNED a transport-OK,
# structured, no-work, zero-turn/zero-ack answer and a matching receipt was
# written. It does NOT prove the cron is scheduled. The success line used to say
# "safe test claim verified in the intended runtime" even on a box with NO cron,
# which misled an operator grepping the log for "verified" — while the tool's
# final verdict was (correctly) ENROLLED_PENDING. The line now names the schedule
# readback it did NOT establish.
# ---------------------------------------------------------------------------
echo "--- 6. the probe success line does not imply the box is scheduled ---"
# Section 5 leaves RR028_EXTRA_ENV set for its own shell wrapper; clear it so
# this case runs against the plain CLI (the mock exits early on unknown args).
RR028_EXTRA_ENV=""
new_box box-nocron 12 no_work
# Fixture health, asserted BEFORE the behaviour under test: a receiver stub that
# never came up would make the assertions below fail for the wrong reason (and
# did, once, when a leaked stub from an interrupted run held the port).
[ -f "$BOX/receiver.py" ] \
  && ok "fixture: the receiver stub exists for this case" \
  || bad "receiver stub was never written — the assertions below cannot be trusted"
# Remove the cron: the receiver still answers, so the probe still succeeds —
# which is precisely the misleading case.
python3 - "$BOX/jobs.json" <<'PY'
import json, sys
p = sys.argv[1]
json.dump({"jobs": []}, open(p, "w"))
PY
state_of
[ "$STATE" = "ENROLLED_PENDING" ] \
  && ok "control: the box really has NO cron (state=ENROLLED_PENDING before the probe)" \
  || bad "control box is not in the unscheduled state" "$STATE/$REASON"
# Run the probe. The harness captures the tool's stdout in RR028_OUT (the same
# pattern every other case uses); a caller-side redirect around the harness call
# does NOT capture it, because the harness already redirects stderr itself.
#
# NOTE ON THE EXIT CODE: `--probe` reports the READINESS verdict, not the
# probe's own outcome — on this box the state is ENROLLED_PENDING (no cron), so
# the tool correctly exits 2 even though the probe itself SUCCEEDED. The probe's
# success is therefore asserted from its own line (below) and from the receipt,
# not from the process exit code.
rr028_readiness "$BOX" --probe
PROBE_RC=$?
PROBE_OUT="$RR028_OUT"
case "$PROBE_OUT" in
  *"safe test claim answer VERIFIED"*)
    ok "control: the probe itself SUCCEEDED against a live receiver (its own line says so; the exit code is the readiness verdict, rc=$PROBE_RC)" ;;
  *) bad "the probe did not succeed on a live receiver" "out=[$PROBE_OUT]" ;;
esac
# A live receiver is what makes this case discriminating, so prove the probe
# actually reached ONE before asserting on what the tool said about it.
grep -q '^REQ POST' "$BOX/receiver.log" 2>/dev/null \
  && ok "fixture: the probe really reached the loopback receiver (assertion is not vacuous)" \
  || bad "the probe never reached the receiver — receiver stub or port problem, not a product result"
state_of
[ "$STATE" = "ENROLLED_PENDING" ] \
  && ok "the verdict stays honest: ENROLLED_PENDING, never SCHEDULED/VERIFIED (reason=$REASON)" \
  || bad "probe on an unscheduled box produced $STATE/$REASON"
case "$PROBE_OUT" in
  *"not that the cron is scheduled"*)
    ok "the success line NAMES the limit (it proves the receiver answered, not that the cron is scheduled)" ;;
  *) bad "the success line still implies the box is ready" "$(printf '%s' "$PROBE_OUT" | head -1)" ;;
esac
case "$PROBE_OUT" in
  *"readback cron.state=absent_proven_by_cli)"*)
    ok "the success line reports the schedule readback it did NOT establish, as the REAL state of this box (absent_proven_by_cli: the CLI's own full-status listing proved no cron of this name exists)" ;;
  *) bad "the success line does not report the exact cron state this box is in (expected absent_proven_by_cli)" "$(printf '%s' "$PROBE_OUT" | tail -1)" ;;
esac

# ---------------------------------------------------------------------------
# 7. M-5's SECOND mechanism must actually fire (RR-028 re-review Z-5).
#
# rr028_killall reaps from a per-battery pid REGISTRY and, as a bounded
# supplement, from a command-line match. The supplement's pattern was
# "$WORK/receiver.py" while every stub lives at "$WORK/<box>/receiver.py", so it
# could never match: the protection was single-mechanism, and a battery killed
# mid-run leaked receivers while still reporting green. Both mechanisms are
# proven here, and the supplement is proven ALONE (the registry is neutered at
# runtime — no code touched, declarations intact).
# ---------------------------------------------------------------------------
echo "--- 7. the bounded pgrep supplement really reaps (Z-5) ---"
Z5_REG="$RR028_PIDFILE"
Z5_A="$WORK/z5-box-a"; Z5_B="$WORK/z5-box-b"
rr028_make_box "$Z5_A"; rr028_make_box "$Z5_B"
rr028_start_receiver "$Z5_A" "$(rr028_port 60)" no_work
rr028_start_receiver "$Z5_B" "$(rr028_port 61)" no_work
# Independent observer: count the stubs by their exact stub path (NOT by the
# supplement's own pattern), so a broken supplement cannot hide behind it.
z5_live() { pgrep -f "$1/receiver\.py" 2>/dev/null | grep -c . || true; }
if [ -s "$Z5_REG" ]; then
  Z5_REGN="$(grep -c . "$Z5_REG" 2>/dev/null || true)"
else
  Z5_REGN=0
fi
[ "${Z5_REGN:-0}" -ge 2 ] \
  && ok "Z-5 control: the pid REGISTRY recorded both receivers (the primary mechanism works)" \
  || bad "the pid registry did not record both receivers" "file=$Z5_REG entries=$Z5_REGN"
Z5_BEFORE=$(( $(z5_live "$Z5_A") + $(z5_live "$Z5_B") ))
[ "$Z5_BEFORE" -ge 2 ] \
  && ok "Z-5 control: both receiver stubs are genuinely alive before the supplement runs (n=$Z5_BEFORE)" \
  || bad "the Z-5 receiver stubs never started — the assertion below would be vacuous" "n=$Z5_BEFORE"
# NEUTER the registry: point it at a path whose directory does not exist (every
# write is refused) and clear the last-pid variable. Now only the pgrep
# supplement can reap anything.
RR028_PIDFILE="$WORK/z5-no-such-dir/rr028-receivers.pid"
RR028_RECEIVER_PID=""
[ ! -e "$WORK/z5-no-such-dir" ] && [ ! -e "$RR028_PIDFILE" ] \
  && ok "Z-5: the registry is genuinely dead at reap time (unwritable path, no file) and no last-pid is held" \
  || bad "the Z-5 registry could not be neutered" "path=$RR028_PIDFILE"
rr028_killall "$WORK"
Z5_I=0
while [ "$Z5_I" -lt 40 ]; do
  [ "$(( $(z5_live "$Z5_A") + $(z5_live "$Z5_B") ))" = "0" ] && break
  sleep 0.05; Z5_I=$((Z5_I + 1))
done
Z5_LEFT=$(( $(z5_live "$Z5_A") + $(z5_live "$Z5_B") ))
[ "$Z5_LEFT" = "0" ] \
  && ok "Z-5: the pgrep supplement reaped BOTH receivers with the registry dead (0 survivors)" \
  || bad "the pgrep supplement never matched — receivers leaked" "$Z5_LEFT still alive"
# Restore the writable registry for the EXIT/INT/TERM trap.
RR028_PIDFILE="$Z5_REG"

# ---------------------------------------------------------------------------
# 8. THE PROBE BUDGET IS SIZED FOR A REAL RECEIVER, AND BOUNDED
#
# Measured 2026-09-14 against the live production receiver: four probe attempts
# returned transport_error under the old 25s default, the SAME probe with
# RR_RECEIVER_PROBE_TIMEOUT=220 returned class=no_work/http=200 on the first try,
# and one identical request took just over 90 seconds to answer while another
# returned an n8n 500 after 99.8s. A 25s budget therefore reports a working (if
# slow) receiver as unreachable -- a false negative in the one place an operator
# looks to decide whether the box is ready.
#
# These assertions read the SHIPPED SOURCE, because the value is a default that
# no hermetic run can exercise without a 90-second stall: the point is that the
# default and its bounds are what the file says.
# ---------------------------------------------------------------------------
echo "--- 8. the probe budget: sized for a real receiver, and bounded ---"
_PROBE_SRC="$RR028_REPO/65-rescue-receiver/rr-readiness.sh"
grep -q 'RR_RECEIVER_PROBE_TIMEOUT:-120' "$_PROBE_SRC" \
  && ok "the probe budget defaults to 120s, not the 25s that failed four times on a working receiver" \
  || bad "the probe budget default is not 120s" "$(grep -n 'RR_RECEIVER_PROBE_TIMEOUT' "$_PROBE_SRC" | head -2)"
# A malformed or out-of-range override must fall back to the DEFAULT, never to the
# old undersized value: a typo must not silently restore the defect.
grep -q '\*) _pb_timeout=120 ;;' "$_PROBE_SRC" \
  && ok "a malformed override falls back to 120s, not to 25s" \
  || bad "malformed override does not fall back to the default" "$(grep -n '_pb_timeout=' "$_PROBE_SRC" | head -3)"
grep -q '\[ "$_pb_timeout" -ge 5 \]' "$_PROBE_SRC" \
  && ok "the override is bounded (5..900), so no value can hang a wiring run" \
  || bad "the override is unbounded" "$(grep -n '_pb_timeout' "$_PROBE_SRC" | head -4)"
# And the reason it changed is recorded where the next reader will look.
grep -q 'raised from 25s ON MEASUREMENT' "$_PROBE_SRC" \
  && ok "the measurement that set the budget is recorded at the constant" \
  || bad "the budget change carries no measurement" "no rationale comment"

echo ""
echo "RESULT: $PASS passed, $FAIL failed, $SKIP skipped"
RR028_DONE=1
[ "$FAIL" -eq 0 ] || exit 1
exit 0
