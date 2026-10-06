#!/usr/bin/env bash
# tests/rescue/RR-028/test_cron_argv_readback.sh — RR-028 argv readback gate.
#
# THE DEFECT THIS PINS (measured on a live box, ONB v25.0.52):
#   On this platform `openclaw` exposes a command job ONLY as `payload.argv`.
#   Across all 117 jobs on the box, `payload.command` is populated for ZERO of
#   them and `payload.argv` for 16; the CLI defines `--command <shell>` as
#   "Command payload run as sh -lc <shell> on the Gateway", so the canonical
#   job is exactly
#       {"kind":"command","argv":["sh","-lc","sh <poll>"]}
#   The readback looked only at payload.command / top-level command and then
#   fell through to the literal "kind=command", which can never equal the
#   desired "sh <poll>". So SCHEDULED and VERIFIED were UNREACHABLE, and a
#   correct, enabled, actively-running job (lastRunStatus=ok) was reported as
#   `cron_field_mismatch` / "does not match the desired config: command".
#
# WHY THE OLD SUITE COULD NOT CATCH IT: the harness double wrote
# `payload.command`, a field the real CLI never produces. The engine and its
# own double agreed with each other while BOTH disagreed with the real system.
# Section 1 below is the guard against that recurring: it asserts the double's
# stored job has the REAL field form.
#
# Every case drives the REAL engine (65-rescue-receiver/rr-readiness.sh and
# shared-utils/rr-readiness.sh) against a synthetic box, and asserts the state
# / reason / rc it PRINTED plus the argv it RECORDED — never a grep of source.
# Every positive is paired with a negative control that proves the assertion
# could have failed.
#
# Hermetic: temp dirs, synthetic slug/token, loopback HTTP only, no credential.
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

echo "== RR-028: cron argv readback + fail-closed command comparison =="
echo "   host: $(uname -s) $(uname -m)  python: $(python3 -V 2>&1)"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/rr028-argv.XXXXXX")"
# Every assertion prints AND tallies. If any ok/bad ran inside a subshell --
# `x=$(f)` or a pipeline -- its PASS/FAIL increment would be lost, and the
# assertion could VANISH silently whenever its parent failed. The final
# self-check compares the tally against PASS+FAIL, so that cannot happen
# unnoticed (the RR-028 "a test nested inside a test disappears" class).
RR028_TALLY="$WORK/assertions.tally"; : > "$RR028_TALLY"
ok()   { PASS=$((PASS+1)); printf '%s\n' "ok $1"     >> "$RR028_TALLY"; echo "  ok $1"; }
bad()  { FAIL=$((FAIL+1)); printf '%s\n' "FAIL $1"   >> "$RR028_TALLY"; echo "  FAIL $1 ${2:-}"; }
RR028_DONE=""
RR028_PIDFILE_BOX="$WORK"
RR028_PIDFILE="${RR028_PIDFILE:-$WORK/rr028-receivers.pid}"
trap 'rr028_cleanup' EXIT
trap 'rr028_cleanup; exit 130' INT
trap 'rr028_cleanup; exit 143' TERM

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
# state_of <box> -> sets STATE / REASON / RC from the tool's own JSON + rc.
STATE=""; REASON=""; RC=0; OUT=""
state_of() {
  rr028_readiness "$1" --json
  RC=$RR028_RC; OUT="$RR028_OUT"
  STATE="$(rr028_field "$RR028_OUT" state)"
  REASON="$(rr028_field "$RR028_OUT" reason)"
}
unobs_of() { rr028_field "$1" cron.unobservable; }
cmdkey() {  # cmdkey <raw> -> normalised key (or empty), via the REAL engine fn
  RR028_K="$1" RRR_ROOT="$2" bash -c '
    set -u
    . "$RR028_REPO/shared-utils/rr-readiness.sh"
    RRR_ROOT="$RRR_ROOT"
    rrr_cron_cmd_key_of "$RR028_K"
  ' 2>/dev/null
}

# payload_of <cmdkey-kind> <arg> -> the payload JSON object under test.
#   argv   : {"kind":"command","argv": <arg as JSON>}
#   raw    : arg is copied VERBATIM as the payload object
payload_json() {
  case "$1" in
    argv) printf '{"kind":"command","argv":%s}' "$2" ;;
    raw)  printf '%s' "$2" ;;
  esac
}

# job_json <box> <id> <payload-json> [enabled|none] [expr] [delivery]
#   `none` OMITS the enabled key entirely (the shape a build that does not
#   report the bit writes) -- `${4:-true}` could not express that, because it
#   also substitutes on an empty value.
job_json() {
  _en=""
  case "${4:-true}" in
    none) : ;;
    *) _en="\"enabled\":${4:-true}," ;;
  esac
  printf '{"id":"%s","name":"rescue-rr-box-poll",%s"schedule":{"kind":"cron","expr":"%s"},"payload":%s,"delivery":{"mode":"%s"}}' \
    "$2" "$_en" "${5:-*/2 * * * *}" "$3" "${6:-none}"
}

# box_with <name> <payload-json> [id] [enabled|none] [expr] [delivery] -> BOX
box_with() {
  BOX="$WORK/$1"
  rr028_make_box "$BOX"
  rr028_job "$BOX" "$(job_json "$BOX" "${3:-1}" "$2" "${4:-true}" "${5:-*/2 * * * *}" "${6:-none}")"
}

# POLLSEL <box> -> "sh <poll script path>"; POLLPATH <box> -> the script path.
POLLSEL()  { printf 'sh %s' "$(POLLPATH "$1")"; }
POLLPATH() { printf '%s/.openclaw/skills/65-rescue-receiver/rescue-poll.sh' "$1"; }

# tmpl <template> -> the template with %B (box root) / %S (poll script path)
# substituted. Bash-native; no sed, so a path containing '|' or '&' is safe.
tmpl() { _t="${1//%B/$BOX}"; printf '%s' "${_t//%S/$(POLLPATH "$BOX")}"; }

# box_set_cmd <raw-command-string> [id] -- replace the box's store with exactly
# ONE job whose payload carries <raw-command-string> in the legacy
# payload.command field (the form a DIFFERENT CLI build exposes; the normaliser
# must treat it identically to the argv form). Errors are FATAL here: a fixture
# that silently failed to write its job would make every following assertion
# vacuous.
box_set_cmd() {
  _c="$1"; _id="${2:-1}"
  RR028_JOBS="$BOX/jobs.json" RR028_C="$_c" RR028_I="$_id" python3 -c '
import json, os
p = os.environ["RR028_JOBS"]
d = {"jobs": [{"id": os.environ["RR028_I"], "name": "rescue-rr-box-poll",
               "enabled": True,
               "schedule": {"kind": "cron", "expr": "*/2 * * * *"},
               "payload": {"kind": "command", "command": os.environ["RR028_C"]},
               "delivery": {"mode": "none"}}]}
json.dump(d, open(p, "w", encoding="utf-8"))' \
    || { echo "FIXTURE ERROR: box_set_cmd could not write the job" >&2; exit 2; }
  [ -s "$BOX/jobs.json" ] || { echo "FIXTURE ERROR: empty store" >&2; exit 2; }
}

# ---------------------------------------------------------------------------
# 1. THE DOUBLE MIRRORS THE REAL FIELD FORM (the root cause of the escape).
#    A mock that models a field the real system never produces IS the defect:
#    it lets the engine and its own fixture agree while both are wrong.
# ---------------------------------------------------------------------------
echo "--- 1. the harness double emits the REAL CLI field form ---"
B_SHAPE="$WORK/box-shape"
rr028_make_box "$B_SHAPE"
rr028_wire "$B_SHAPE" >/dev/null 2>&1
SHAPE="$(RR028_JOBS="$B_SHAPE/jobs.json" python3 -c '
import json, os
d = json.load(open(os.environ["RR028_JOBS"], encoding="utf-8"))
j = (d.get("jobs") or [{}])[0]
p = j.get("payload") or {}
print(json.dumps({"argv": p.get("argv"), "command": p.get("command"), "kind": p.get("kind")}))')"
[ "$SHAPE" = '{"argv": ["sh", "-lc", "sh '"$B_SHAPE"'/.openclaw/skills/65-rescue-receiver/rescue-poll.sh"], "command": null, "kind": "command"}' ] \
  && ok "wire's registered job has the REAL shape: payload.argv=[sh,-lc,<cmd>], payload.command ABSENT" \
  || bad "the harness double does not mirror the real CLI field form" "$SHAPE"
# Control: RR028_MOCK_JOB_SHAPE=command reproduces the OLD, non-real form, so
# the assertion above is discriminating rather than trivially true.
B_OLD="$WORK/box-shape-old"
rr028_make_box "$B_OLD"
RR028_MOCK_JOB_SHAPE=command rr028_wire "$B_OLD" >/dev/null 2>&1
OLD="$(RR028_JOBS="$B_OLD/jobs.json" python3 -c '
import json, os
d = json.load(open(os.environ["RR028_JOBS"], encoding="utf-8"))
p = ((d.get("jobs") or [{}])[0].get("payload") or {})
print(json.dumps({"argv": p.get("argv"), "command": "set" if p.get("command") else None}))')"
[ "$OLD" = '{"argv": null, "command": "set"}' ] \
  && ok "control: the legacy payload.command form is still reachable by knob (assertion discriminates)" \
  || bad "shape control did not produce the legacy form" "$OLD"

# ---------------------------------------------------------------------------
# 2. THE READBACK PARSES THE REAL SHAPE. Drives rrr_json_rows itself, so the
#    assertion is on the exact string the readback yields -- not on a state
#    that other code could have produced for another reason.
# ---------------------------------------------------------------------------
echo "--- 2. the readback reconstructs the command from payload.argv ---"
RS=$'\036'
rb_field() {  # rb_field <json> <field-index 1..6>
  RR028_RJ="$1" RR028_FI="$2" bash -c '
    set -u
    . "$RR028_REPO/shared-utils/rr-readiness.sh"
    rows="$(rrr_json_rows "$RR028_RJ" "rescue-rr-box-poll" cli)"
    printf "%s" "$rows" | awk -F"$(printf "\036")" -v i="$RR028_FI" "{print \$i}"
  ' 2>/dev/null
}
B_RB="$WORK/box-rb"
REAL_JSON="$(job_json "$B_RB" 1 "$(payload_json argv "[\"sh\",\"-lc\",\"$(POLLSEL "$B_RB")\"]")")"
GOT_CMD="$(rb_field "{\"jobs\":[$REAL_JSON]}" 5)"
[ "$GOT_CMD" = "sh $B_RB/.openclaw/skills/65-rescue-receiver/rescue-poll.sh" ] \
  && ok "readback of the REAL payload yields the command 'sh <poll>' (was the literal 'kind=command')" \
  || bad "readback did not reconstruct the command from argv" "[$GOT_CMD]"
[ "$GOT_CMD" != "kind=command" ] \
  && ok "the dead 'kind=command' fallback is gone" \
  || bad "readback still yields the literal 'kind=command'"
WANTKEY="$(cmdkey "sh $B_RB/.openclaw/skills/65-rescue-receiver/rescue-poll.sh" "$B_RB/.openclaw")"
GOTKEY="$(cmdkey "$GOT_CMD" "$B_RB/.openclaw")"
[ -n "$WANTKEY" ] && [ "$GOTKEY" = "$WANTKEY" ] \
  && ok "the reconstructed command normalises to the desired key (it MATCHES)" \
  || bad "reconstructed command did not match the desired key" "want=[$WANTKEY] got=[$GOTKEY]"
# Control: the SAME call on the legacy payload.command form yields the same
# command, so the argv branch did not replace the documented one.
LEG_JSON="$(job_json "$B_RB" 1 "$(payload_json raw "{\"kind\":\"command\",\"command\":\"$(POLLSEL "$B_RB")\"}")")"
GOT_LEG="$(rb_field "{\"jobs\":[$LEG_JSON]}" 5)"
[ "$GOT_LEG" = "sh $B_RB/.openclaw/skills/65-rescue-receiver/rescue-poll.sh" ] \
  && ok "control: payload.command (a future CLI build's form) still reads back identically" \
  || bad "payload.command regressed" "[$GOT_LEG]"

# ---------------------------------------------------------------------------
# 3. THE POSITIVE: a correct argv-shaped job is judged MATCHING, end to end.
# ---------------------------------------------------------------------------
echo "--- 3. end to end: a correct argv-shaped job is scheduled ---"
B_OK="$WORK/box-argv-ok"
box_with box-argv-ok "$(payload_json argv "[\"sh\",\"-lc\",\"$(POLLSEL "$WORK/box-argv-ok")\"]")"
state_of "$BOX"
[ "$STATE" = "SCHEDULED" ] && [ "$RC" = "1" ] \
  && ok "REAL argv-shaped job + no receipt => SCHEDULED (rc=1) — the defect is fixed" \
  || bad "argv-shaped correct job did not reach SCHEDULED" "$STATE/$REASON rc=$RC"
[ "$REASON" != "cron_field_mismatch" ] \
  && ok "a correct job is no longer reported as cron_field_mismatch (reason=$REASON)" \
  || bad "still cron_field_mismatch" "$STATE/$REASON"
[ "$REASON" = "ready_receipt_absent" ] \
  && ok "the reason is the honest one: ready_receipt_absent" \
  || bad "unexpected reason for a matching job" "$STATE/$REASON"
[ "$(rr028_field "$OUT" cron.command)" = "sh $B_OK/.openclaw/skills/65-rescue-receiver/rescue-poll.sh" ] \
  && ok "the report's cron.command shows the reconstructed command the box actually runs" \
  || bad "cron.command not reported" "$(rr028_field "$OUT" cron.command)"
[ "$(rr028_field "$OUT" cron.coverage)" = "cli-only" ] \
  && ok "the readback really consulted the CLI's own listing (coverage=cli-only: this fixture has no state DB)" \
  || bad "coverage wrong" "$(rr028_field "$OUT" cron.coverage)"

# VERIFIED requires the SCHEDULED readback plus a real probe receipt.
PORT="$(rr028_port 3)"
printf 'RR_RECEIVER_URL=http://127.0.0.1:%s/rr\nRR_BOX_TOKEN="tok-synthetic-rr028"\nRR_BOX_SLUG=box-synthetic\n' "$PORT" \
  > "$B_OK/.openclaw/secrets/.env"; chmod 600 "$B_OK/.openclaw/secrets/.env"
rr028_start_receiver "$B_OK" "$PORT" no_work || bad "control receiver did not start"
rr028_readiness "$B_OK" --probe >/dev/null 2>&1
state_of "$B_OK"
[ "$STATE" = "VERIFIED" ] && [ "$RC" = "0" ] \
  && ok "READY-argv job + a real safe-claim receipt => VERIFIED (rc=0) — VERIFIED is reachable again" \
  || bad "argv-shaped proven box did not reach VERIFIED" "$STATE/$REASON rc=$RC"
grep -q "^REQ POST" "$B_OK/receiver.log" 2>/dev/null \
  && ok "the probe really reached the receiver (the VERIFIED claim is not vacuous)" \
  || bad "receiver never saw the probe — VERIFIED assertion cannot fail"

# ---------------------------------------------------------------------------
# 4. NEGATIVE CONTROL FOR SECTION 3: the SAME assertion shape on a DIFFERENT
#    script must NOT be scheduled. Without this, section 3 proves nothing.
# ---------------------------------------------------------------------------
echo "--- 4. negative control: a different script is not scheduled ---"
B_OTHER="$WORK/box-other-script"
box_with box-other-script "$(payload_json argv "[\"sh\",\"-lc\",\"sh $WORK/nope/rescue-poll.sh\"]")"
state_of "$BOX"
[ "$STATE" = "ENROLLED_PENDING" ] && [ "$REASON" = "cron_field_mismatch" ] \
  && ok "control: a DIFFERENT script path is a mismatch (the section-3 assertion discriminates)" \
  || bad "a different script was not a mismatch" "$STATE/$REASON"
printf '%s' "$OUT" | grep -q 'command_unobservable' \
  && bad "a readable-but-different command was reported unobservable" \
  || ok "a readable-but-different command is reported as a plain command mismatch (not unobservable)"

# ---------------------------------------------------------------------------
# 5. THE NEGATIVES — no uninterpretable/unexpected shape may MATCH. Each is
#    driven through the WHOLE state machine, and each asserts the row could
#    never be judged SCHEDULED or VERIFIED.
# ---------------------------------------------------------------------------
echo "--- 5. no uninterpretable argv shape may be judged matching ---"
neg() {  # neg <label> <payload-json> <expect-unobservable:0|1>
  _lbl="$1"; _p="$2"; _expu="${3:-0}"
  _n="$(printf '%s' "$_lbl" | tr -c 'A-Za-z0-9_.-' '_')"
  box_with "box-neg-$_n" "$_p"
  state_of "$BOX"
  case "$STATE" in
    SCHEDULED|VERIFIED) bad "$_lbl: judged MATCHING" "$STATE/$REASON"; return 0 ;;
  esac
  ok "$_lbl: never judged matching ($STATE/$REASON)"
  if [ "$_expu" = "1" ]; then
    printf '%s' "$OUT" | grep -q 'command_unobservable' \
      && ok "$_lbl: reported as command_UNOBSERVABLE, not as a plain mismatch" \
      || bad "$_lbl: unreadable command was not reported as unobservable" "$(unobs_of "$OUT")"
    [ -z "$(rr028_field "$OUT" cron.command)" ] \
      && ok "$_lbl: the unreadable command is reported EMPTY (no kind= marker masquerading as a value)" \
      || bad "$_lbl: an unreadable command was reported with a value" "[$(rr028_field "$OUT" cron.command)]"
  fi
}
neg "a different script path (argv)"      "$(payload_json argv "[\"sh\",\"-lc\",\"sh /gone/other-poll.sh\"]")"
# ISOLATES THE ARITY RULE: the command element is the CORRECT poll script, so
# only the presence of the extra element can keep this from matching. (An
# extra-element case built on a WRONG path proves nothing about arity -- it
# would mismatch for the unrelated reason, and a widened shape check would go
# unnoticed.)
neg "an unexpected EXTRA argv element"    "$(payload_json argv "[\"sh\",\"-lc\",\"sh $WORK/box-neg-x/rescue-poll.sh\",\"extra\"]")"
neg "an EXTRA argv element after the REAL poll command" \
    "$(payload_json argv "[\"sh\",\"-lc\",\"$(POLLSEL "$WORK/box-neg-real-extra")\",\"extra\"]")"
neg "empty argv"                          "$(payload_json argv "[]")" 1
neg "argv with a NON-STRING member"       "$(payload_json argv "[\"sh\",\"-lc\",42]")" 1
neg "a payload with NEITHER command NOR argv" '{"kind":"command"}' 1
neg "argv as a STRING, not a list"        "$(payload_json argv "\"sh -lc sh $WORK/x/rescue-poll.sh\"")" 1
neg "a non-shell argv[0] (python)"        "$(payload_json argv "[\"python3\",\"-lc\",\"sh $WORK/x/rescue-poll.sh\"]")"
neg "an unobserved wrapper flag (-x)"     "$(payload_json argv "[\"sh\",\"-x\",\"sh $WORK/x/rescue-poll.sh\"]")"
neg "argv with an EMPTY command element"  "$(payload_json argv "[\"sh\",\"-lc\",\"\"]")" 1
neg "a payload with an unknown kind only" '{"kind":"prompt"}' 1

# ---------------------------------------------------------------------------
# 6. THE NORMALISATION RULE — every accepted difference must be one that
#    provably runs the SAME file, and every refusal must be explicit.
# ---------------------------------------------------------------------------
echo "--- 6. the documented normalisation rule ---"
norm() {  # norm <label> <template> <expect: match|nomatch>
  _lbl="$1"; _exp="$3"
  _n="$(printf '%s' "$_lbl" | tr -c 'A-Za-z0-9_.-' '_')"
  BOX="$WORK/box-norm-$_n"; rr028_make_box "$BOX"
  # The payload carries the command this case is about; %B/%S resolve against
  # THIS box, so the wanted config and the observed command stay comparable.
  _c="$(tmpl "$2")"
  box_set_cmd "$_c" 2
  state_of "$BOX"
  if [ "$_exp" = "match" ]; then
    [ "$STATE" = "SCHEDULED" ] \
      && ok "$_lbl: SCHEDULED (normalised match)" \
      || bad "$_lbl: did not match" "$STATE/$REASON cmd=[$_c]"
  else
    case "$STATE" in
      SCHEDULED|VERIFIED) bad "$_lbl: MATCHED but must not" "$STATE/$REASON" ;;
      *) ok "$_lbl: not matching ($STATE/$REASON)" ;;
    esac
  fi
}
# Control that the section itself can fail: the plain legacy form matches.
norm "plain 'sh <poll>'" "sh %S" match
norm "shell wrapper 'sh -lc sh <poll>'" "sh -lc sh %S" match
norm "another shell 'bash -lc sh <poll>'" "bash -lc sh %S" match
norm "bare script path (no shell word)" "%S" match
norm "path relative to the openclaw root" "sh skills/65-rescue-receiver/rescue-poll.sh" match
norm "'.' / '//' path noise" "sh .//skills/65-rescue-receiver/./rescue-poll.sh" match
norm "'..' segments" "sh %B/.openclaw/skills/65-rescue-receiver/../65-rescue-receiver/rescue-poll.sh" match
nan() {  # nan <label> <template>
  _lbl="$1"
  _n="$(printf '%s' "$_lbl" | tr -c 'A-Za-z0-9_.-' '_')"
  BOX="$WORK/box-nan-$_n"; rr028_make_box "$BOX"
  _c="$(tmpl "$2")"
  box_set_cmd "$_c" 3
  state_of "$BOX"
  case "$STATE" in
    SCHEDULED|VERIFIED) bad "$_lbl: MATCHED but must not" "$STATE/$REASON cmd=[$_c]" ;;
    *) ok "$_lbl: refused / mismatched ($STATE/$REASON)" ;;
  esac
}
nan "an EXTRA word after the script (wrapper+extra)" "sh -lc sh /x/rescue-poll.sh extra"
nan "an EXTRA word after the script (real path + extra)" "sh -lc sh %S extra"
nan "a different script via the wrapper"             "sh -lc sh /gone/rescue-poll.sh"
nan "an unobserved wrapper flag (-ec)"               "sh -ec sh %S"
nan "a non-shell program (python <poll>)"            "python %S"
nan "the dead 'kind=command' marker"                 "kind=command"
nan "a bare shell word (no script at all)"           "sh"

# ---------------------------------------------------------------------------
# 7. THE WHOLE STATE MACHINE — SCHEDULED, VERIFIED and the reconcile ladder.
# ---------------------------------------------------------------------------
echo "--- 7. the state machine and the reconcile ladder ---"
B_REC="$WORK/box-reconcile"
box_with box-reconcile "$(payload_json argv "[\"sh\",\"-lc\",\"$(POLLSEL "$WORK/box-reconcile")\"]")"
RR028_STDERR="$B_REC/stderr-all.txt" rr028_readiness "$B_REC" --reconcile >/dev/null 2>&1
REC_RC=$RR028_RC
state_of "$B_REC"
[ "$STATE" = "SCHEDULED" ] && [ "$REC_RC" = "1" ] \
  && ok "reconcile on a correct argv-shaped job proves it and exits SCHEDULED (rc=1), not 'NOT proven'" \
  || bad "reconcile did not prove the correct argv-shaped job" "$STATE/$REASON rc=$REC_RC"
MOV="$(rr028_mutating_argv "$B_REC")"
[ -z "$MOV" ] \
  && ok "reconcile issued ZERO mutating argv (regex-verified absence, not a substring grep)" \
  || bad "reconcile mutated an already-correct argv-shaped job" "$MOV"
NJOBS="$(RR028_JOBS="$B_REC/jobs.json" python3 -c '
import json, os
d = json.load(open(os.environ["RR028_JOBS"], encoding="utf-8"))
print(len([j for j in d.get("jobs", []) if j.get("name") == "rescue-rr-box-poll"]))')"
[ "$NJOBS" = "1" ] && [ "$(rr028_field "$OUT" cron.id)" = "1" ] \
  && ok "still exactly ONE job, same id (nothing was removed and re-created)" \
  || bad "reconcile changed the job set" "count=$NJOBS id=$(rr028_field "$OUT" cron.id)"
grep -qi 'NOT proven' "$B_REC/stderr-all.txt" 2>/dev/null \
  && bad "reconcile still prints 'desired cron NOT proven'" || ok "reconcile no longer reports 'desired cron NOT proven'"

# The two states the brief asks for, asserted exactly as the engine defines
# them (see the note in the header of this file):
#   matching argv job, NO receipt      -> SCHEDULED
#   matching argv job + valid receipt  -> VERIFIED
B_NOREC="$WORK/box-no-receipt"
box_with box-no-receipt "$(payload_json argv "[\"sh\",\"-lc\",\"$(POLLSEL "$WORK/box-no-receipt")\"]")"
state_of "$B_NOREC"
[ "$STATE" = "SCHEDULED" ] && [ "$REASON" = "ready_receipt_absent" ] \
  && ok "matching argv job + NO receipt => SCHEDULED/ready_receipt_absent (never ENROLLED_PENDING)" \
  || bad "no-receipt argv job did not report SCHEDULED" "$STATE/$REASON"
RCPATH="$B_NOREC/.openclaw/state/rr-receiver/readiness"
# The engine legitimately creates this dir (it holds the digest .salt); what
# must NOT exist is a receipt, which only a safe test claim may write.
ls "$RCPATH"/receipt-*.json >/dev/null 2>&1 \
  && bad "a receipt appeared without a probe" "$(ls "$RCPATH" 2>/dev/null)" \
  || ok "no receipt was invented for the no-receipt box (the SCHEDULED claim is real)"

# ---------------------------------------------------------------------------
# 8. THE FAIL-CLOSED GUARANTEES ARE INTACT (regression pins, not wishful ones).
#    Each drives the real engine and asserts the job SURVIVED untouched.
# ---------------------------------------------------------------------------
echo "--- 8. fail-closed guarantees preserved ---"
# (a) a row whose `enabled` bit NO view reports must never be edited/replaced.
B_EN="$WORK/box-enabled-unobservable"
rr028_make_box "$B_EN"
rr028_job "$B_EN" "$(job_json "$B_EN" 7 "$(payload_json argv "[\"sh\",\"-lc\",\"$(POLLSEL "$B_EN")\"]")" none)"
state_of "$B_EN"
[ "$STATE" = "ENROLLED_PENDING" ] \
  && ok "(a) argv job with NO observable enabled bit is never SCHEDULED ($REASON)" \
  || bad "(a) unobservable enabled bit was claimed ready" "$STATE/$REASON"
[ "$REASON" = "cron_enabled_unobservable" ] \
  && ok "(a) the reason NAMES it: cron_enabled_unobservable" || bad "(a) reason wrong" "$STATE/$REASON"
rr028_readiness "$B_EN" --reconcile >/dev/null 2>&1
[ -z "$(rr028_mutating_argv "$B_EN")" ] \
  && ok "(a) reconcile issued NO edit/replace/rm for it (fail-closed)" \
  || bad "(a) an enabled-unobservable job was mutated" "$(rr028_mutating_argv "$B_EN")"

# (b) a job only the STORE shows is never treated as evidence and never removed.
B_ST="$WORK/box-store-only"
rr028_make_box "$B_ST"
rr028_job "$B_ST" "$(job_json "$B_ST" 5 "$(payload_json argv "[\"sh\",\"-lc\",\"$(POLLSEL "$B_ST")\"]")")"
# Build the gateway store from a state where the row EXISTS, then delete it from
# the CLI's own listing (jobs.json) ONLY. The store now carries a row the CLI's
# listing omits: the store may veto, but it must never license.
rr028_make_db "$B_ST"
RR028_JOBS="$B_ST/jobs.json" python3 -c '
import json, os
p = os.environ["RR028_JOBS"]
d = json.load(open(p, encoding="utf-8"))
d["jobs"] = [j for j in d["jobs"] if str(j.get("id")) != "5"]
json.dump(d, open(p, "w", encoding="utf-8"))'
# Control: the fixture really is "CLI silent, store carrying the row".
STORE_ROWS="$(RR028_DB="$B_ST/.openclaw/state/openclaw.sqlite" python3 -c '
import os, sqlite3
con = sqlite3.connect(os.environ["RR028_DB"])
print(con.execute("select count(*) from cron_jobs").fetchone()[0])')"
CLI_ROWS="$(RR028_JOBS="$B_ST/jobs.json" python3 -c '
import json, os
print(len(json.load(open(os.environ["RR028_JOBS"], encoding="utf-8"))["jobs"]))')"
[ "$STORE_ROWS" = "1" ] && [ "$CLI_ROWS" = "0" ] \
  && ok "(b) fixture: the store carries the row while the CLI's own listing does not (assertion can fail)" \
  || bad "(b) fixture does not isolate the store-only row" "store=$STORE_ROWS cli=$CLI_ROWS"
RR028_DB_FILE="$B_ST/.openclaw/state/openclaw.sqlite" state_of "$B_ST"
case "$STATE" in
  SCHEDULED|VERIFIED) bad "(b) the store ALONE established readiness" "$STATE/$REASON" ;;
  *) ok "(b) the store may veto, never license (store-only row => $STATE/$REASON)" ;;
esac
RR028_DB_FILE="$B_ST/.openclaw/state/openclaw.sqlite" rr028_readiness "$B_ST" --reconcile >/dev/null 2>&1
[ -z "$(rr028_mutating_argv "$B_ST")" ] \
  && ok "(b) reconcile issued no mutation from a store-only row" \
  || bad "(b) a store-only row licensed a mutation" "$(rr028_mutating_argv "$B_ST")"
# Control: the row SURVIVED in the store the CLI never corroborated.
RR028_DB="$B_ST/.openclaw/state/openclaw.sqlite" python3 -c '
import os, sqlite3, sys
con = sqlite3.connect(os.environ["RR028_DB"])
n = con.execute("select count(*) from cron_jobs where job_id = ?", ("5",)).fetchone()[0]
sys.exit(0 if n == 1 else 1)' \
  && ok "(b) the uncorroborated store row SURVIVED (the refusal was not a deletion)" \
  || bad "(b) the store-only row was removed"

# (c) an unreadable/unobservable field never looks like a match -- proven in
# section 5; here the pin is that it is also never counted as OBSERVED.
B_U="$WORK/box-unobs-field"
box_with box-unobs-field "$(payload_json argv "[\"sh\",\"-lc\",42]")"
state_of "$BOX"
[ "$(unobs_of "$OUT")" = "command" ] \
  && ok "(c) the unobservable field is reported by NAME ('command')" \
  || bad "(c) unobservable field not named" "[$(unobs_of "$OUT")]"
printf '%s' "$OUT" | grep -q 'cron_field_mismatch' \
  && ok "(c) the verdict is a refusal (cron_field_mismatch), never a readiness claim" \
  || bad "(c) unexpected verdict for an unreadable command" "$STATE/$REASON"

echo ""
# ---------------------------------------------------------------------------
# 9. DIRECT UNIT CHECK of the fail-closed comparison guard. rrr_cron_eval is
#    called directly (not through the wrapper, whose own `poll_script_missing`
#    gate would mask this) with a DESIRED command the engine cannot name. No
#    observed row -- not even one whose command is equally unreadable -- may
#    land in the MATCH set, because "we could not read either side" must never
#    compare equal.
# ---------------------------------------------------------------------------
echo "--- 9. direct unit check: an unnameable desired command matches NOTHING ---"
direct_eval() {  # direct_eval <poll> <command-cell> -> "state|match_ids"
  RR028_RS="$RS" RR028_POLLV="$1" RR028_CMDV="$2" bash -c '
    set -u
    . "$RR028_REPO/shared-utils/rr-readiness.sh"
    RS="$RR028_RS"
    RRR_ROOT=/box/.openclaw
    RRR_POLL="$RR028_POLLV"
    RRR_SCHEDULE="*/2 * * * *"
    RRR_DELIVERY="none"
    RRR_DB_STATE="none"; RRR_COVERAGE="none"
    RRR_JOBS="cli${RS}1${RS}true${RS}*/2 * * * *${RS}${RR028_CMDV}${RS}none${RS}command"
    rrr_cron_eval
    printf "%s|%s" "$RRR_CRON_STATE" "$RRR_CRON_MATCH_IDS"
  ' 2>/dev/null
}
D_NOWANT="$(direct_eval "" "")"
[ "${D_NOWANT%%|*}" != "single" ] && [ -z "${D_NOWANT#*|}" ] \
  && ok "desired command unnameable => NO row matches (state=${D_NOWANT%%|*}, match_ids empty)" \
  || bad "an unnameable desired command matched a row" "$D_NOWANT"
D_NOWANT2="$(direct_eval "" "sh /box/.openclaw/skills/65-rescue-receiver/rescue-poll.sh")"
[ "${D_NOWANT2%%|*}" != "single" ] && [ -z "${D_NOWANT2#*|}" ] \
  && ok "desired command unnameable => even a plausible observed command does not match" \
  || bad "a readable observed command matched an unnameable desired config" "$D_NOWANT2"
# CONTROL: the identical call with a NAMEABLE desired command DOES match, so the
# two assertions above are discriminating rather than vacuous.
D_WANT="$(direct_eval "/box/.openclaw/skills/65-rescue-receiver/rescue-poll.sh" "sh /box/.openclaw/skills/65-rescue-receiver/rescue-poll.sh")"
[ "${D_WANT%%|*}" = "single" ] && [ -n "${D_WANT#*|}" ] \
  && ok "control: with a nameable desired command the SAME call does match (state=single, match_ids=${D_WANT#*|})" \
  || bad "control could not produce a match — the assertions above may be vacuous" "$D_WANT"

echo ""
# W-1 self-check: every assertion this battery ran reported at TOP level.
TALLY_N="$(wc -l < "$RR028_TALLY" 2>/dev/null | tr -d ' ')"
if [ "${TALLY_N:-0}" = "$((PASS + FAIL))" ]; then
  ok "W-1: all $TALLY_N assertions reported at top level (none vanished into a subshell)"
else
  bad "W-1: $TALLY_N assertions tallied but PASS+FAIL=$((PASS + FAIL)) — at least one ran in a subshell" ""
fi
echo "RESULT: $PASS passed, $FAIL failed, $SKIP skipped"
RR028_DONE=1
[ "$FAIL" -eq 0 ] || exit 1
exit 0
