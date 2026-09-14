#!/usr/bin/env bash
# tests/rescue/RR-028/test_readiness_states.sh — RR-028 gate (ONB receiver).
#
# Pins the readiness STATE MACHINE and the readback contract.
# SPEC RR-028: "Make enrollment and cron reconciliation report real readiness."
# Required behaviour (verified verbatim by the investigator):
#   1. Explicit readiness states UNENROLLED / ENROLLED_PENDING / SCHEDULED /
#      VERIFIED, each with an explicit reason.
#   2. Reconcile enrollment INDEPENDENT OF SOFTWARE VERSION.
#   3. Key readiness by DESIRED-CONFIG DIGEST and verified receipt.
#   4. Require resolution of slug, token, URL plus parser / curl / base64 /
#      OpenClaw / Node.
#   5. Reconcile duplicates, command, schedule, enabled state and delivery
#      flags WITH READBACK (read back what is actually there).
#   6. argv-safe invocation plus a shared host/container descriptor.
#   7. Installer success means files installed; receiver readiness is a
#      SEPARATE claim requiring a safe test claim/receipt in the intended
#      runtime.
#
# Every case drives the REAL `65-rescue-receiver/rr-readiness.sh` against a
# synthetic box and asserts the STATE + REASON + rc it printed — never a grep
# of the source. Every "it refused" assertion has a control proving the
# observer could have seen the opposite.
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

echo "== RR-028: readiness state machine + readback + digest keying =="
echo "   host: $(uname -s) $(uname -m)  python: $(python3 -V 2>&1)"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/rr028-states.XXXXXX")"
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

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
matching_job() {  # matching_job <box> [id] [overrides-json]
  _box="$1"; _id="${2:-1}"; _ov="${3:-}"
  _cmd="sh $_box/.openclaw/skills/65-rescue-receiver/rescue-poll.sh"
  _base="{\"id\":\"$_id\",\"name\":\"rescue-rr-box-poll\",\"enabled\":true,\"schedule\":{\"kind\":\"cron\",\"expr\":\"*/2 * * * *\"},\"payload\":{\"kind\":\"command\",\"command\":\"$_cmd\"},\"delivery\":{\"mode\":\"none\"}}"
  if [ -n "$_ov" ]; then
    RR028_BASE="$_base" RR028_OV="$_ov" python3 -c '
import json, os
b = json.loads(os.environ["RR028_BASE"]); o = json.loads(os.environ["RR028_OV"])
b.update(o); print(json.dumps(b))'
  else
    printf '%s' "$_base"
  fi
}

# state_of <box> -> "<state>|<reason>"; rc in RR028_RC
STATE=""; REASON=""; RC=0
state_of() {
  rr028_readiness "$1" --json
  RC=$RR028_RC
  STATE="$(rr028_field "$RR028_OUT" state)"
  REASON="$(rr028_field "$RR028_OUT" reason)"
}

# no_enabled_job <box> [id] [overrides-json] — a MANAGED row that carries NO
# `enabled` key: the shape a build whose job JSON omits the bit writes, where
# the engine cannot tell an operator-DISABLED job from an ENABLED one.
no_enabled_job() {
  _box="$1"; _id="${2:-1}"; _ov="${3:-}"
  _cmd="sh $_box/.openclaw/skills/65-rescue-receiver/rescue-poll.sh"
  _base="{\"id\":\"$_id\",\"name\":\"rescue-rr-box-poll\",\"schedule\":{\"kind\":\"cron\",\"expr\":\"*/2 * * * *\"},\"payload\":{\"kind\":\"command\",\"command\":\"$_cmd\"},\"delivery\":{\"mode\":\"none\"}}"
  if [ -n "$_ov" ]; then
    RR028_BASE="$_base" RR028_OV="$_ov" python3 -c '
import json, os
b = json.loads(os.environ["RR028_BASE"]); b.update(json.loads(os.environ["RR028_OV"])); print(json.dumps(b))'
  else
    printf '%s' "$_base"
  fi
}

# ---------------------------------------------------------------------------
# 0. CONTROL — the harness can SEE the top state. A box with a readback-matching
#    job AND a verified safe-claim receipt reports VERIFIED. If this control
#    fails, every later "it is not VERIFIED" assertion is vacuous.
# ---------------------------------------------------------------------------
echo "--- 0. control: a fully proven box reports VERIFIED ---"
B0="$WORK/box-control"
rr028_make_box "$B0"
rr028_job "$B0" "$(matching_job "$B0")"
PORT="$(rr028_port 0)"
printf 'RR_RECEIVER_URL=http://127.0.0.1:%s/rr\nRR_BOX_TOKEN="tok-synthetic-rr028"\nRR_BOX_SLUG=box-synthetic\n' "$PORT" \
  > "$B0/.openclaw/secrets/.env"; chmod 600 "$B0/.openclaw/secrets/.env"
rr028_start_receiver "$B0" "$PORT" no_work || bad "control receiver did not start"
state_of "$B0"
[ "$STATE" = "SCHEDULED" ] && ok "control: matching job + no receipt => SCHEDULED" || bad "control state" "$STATE/$REASON"
rr028_readiness "$B0" --probe >/dev/null 2>&1
state_of "$B0"
[ "$STATE" = "VERIFIED" ] && [ "$RC" = "0" ] \
  && ok "control: safe test claim receipt => VERIFIED (rc=0)" \
  || bad "control VERIFIED" "$STATE/$REASON rc=$RC"
[ -s "$B0/receiver.log" ] && grep -q "^REQ POST" "$B0/receiver.log" \
  && ok "control: the receiver stub DID receive the probe request (observer works)" \
  || bad "control receiver never saw a request — readback observer cannot fail"

# ---------------------------------------------------------------------------
# 1. THE FOUR STATES, EACH WITH ITS EXPLICIT REASON
# ---------------------------------------------------------------------------
echo "--- 1. four explicit states + reasons ---"
B1="$WORK/box-unenrolled"
rr028_make_box "$B1"
rm -f "$B1/.openclaw/secrets/.env"
state_of "$B1"
[ "$STATE" = "UNENROLLED" ] && [ "$REASON" = "enrollment_store_missing" ] \
  && ok "UNENROLLED: no enrollment store (reason=$REASON)" || bad "UNENROLLED store-missing" "$STATE/$REASON"

B2="$WORK/box-notoken"
rr028_make_box "$B2"
printf 'RR_RECEIVER_URL=http://127.0.0.1:1/rr\nRR_BOX_SLUG=box-synthetic\n' > "$B2/.openclaw/secrets/.env"
chmod 600 "$B2/.openclaw/secrets/.env"
state_of "$B2"
[ "$STATE" = "UNENROLLED" ] && [ "$REASON" = "enrollment_value_absent" ] \
  && ok "UNENROLLED: missing value named (reason=$REASON)" || bad "UNENROLLED missing value" "$STATE/$REASON"
printf '%s' "$RR028_OUT" | grep -q 'RR_BOX_TOKEN' \
  && ok "the missing value is named by NAME (RR_BOX_TOKEN)" || bad "missing name not reported"
printf '%s' "$RR028_OUT" | grep -q 'tok-synthetic' && bad "report leaked a value" || ok "report is value-free"

B3="$WORK/box-malformed"
rr028_make_box "$B3"
{ printf 'RR_RECEIVER_URL=http://127.0.0.1:1/rr\nRR_BOX_TOKEN="tok-synthetic-rr028"\nRR_BOX_SLUG=box-synthetic\n'; printf 'JUNKLINE\n'; } \
  > "$B3/.openclaw/secrets/.env"
chmod 600 "$B3/.openclaw/secrets/.env"
state_of "$B3"
[ "$STATE" = "UNENROLLED" ] && [ "$REASON" = "enrollment_store_malformed" ] \
  && ok "UNENROLLED: malformed store (reason=$REASON)" || bad "UNENROLLED malformed" "$STATE/$REASON"

B4="$WORK/box-pending"
rr028_make_box "$B4"
state_of "$B4"
[ "$STATE" = "ENROLLED_PENDING" ] && [ "$REASON" = "cron_absent" ] \
  && ok "ENROLLED_PENDING: enrolled but no cron (reason=$REASON)" || bad "ENROLLED_PENDING absent" "$STATE/$REASON"

B5="$WORK/box-nodereq"
rr028_make_box "$B5"
rr028_job "$B5" "$(matching_job "$B5")"
RR028_EXTRA_ENV="RRR_NODE_OVERRIDE=/nonexistent/rr028-node" state_of "$B5"
[ "$STATE" = "ENROLLED_PENDING" ] && [ "$REASON" = "runtime_requirement_unresolved" ] \
  && ok "ENROLLED_PENDING: unresolved runtime requirement (reason=$REASON)" || bad "requirement unresolved" "$STATE/$REASON"
printf '%s' "$RR028_OUT" | grep -q '"missing":"node"' \
  && ok "the unresolved requirement is named (node)" || bad "unresolved requirement not named"
RR028_EXTRA_ENV="RRR_NODE_OVERRIDE=$(command -v node || echo /usr/bin/node)" state_of "$B5"
[ "$STATE" = "SCHEDULED" ] \
  && ok "control: with node resolvable again the SAME box is SCHEDULED (the check discriminates)" \
  || bad "control for node requirement" "$STATE/$REASON"

B6="$WORK/box-sched"
rr028_make_box "$B6"
rr028_job "$B6" "$(matching_job "$B6")"
state_of "$B6"
[ "$STATE" = "SCHEDULED" ] && [ "$REASON" = "ready_receipt_absent" ] \
  && ok "SCHEDULED: readback matches, no verified receipt (reason=$REASON)" || bad "SCHEDULED" "$STATE/$REASON"

# VERIFIED is section 0's control.

# ---------------------------------------------------------------------------
# 1b. AD-2 (RR-028 review): A ROW WHOSE `enabled` BIT NO VIEW REPORTS.
#
# The CLI's own listing shows a managed job that carries no `enabled` key at
# all — so the engine cannot tell a job the operator switched OFF from an
# ENABLED one. The state machine must say exactly that (a NAMED reason, not a
# bare field mismatch), never claim SCHEDULED, and the reconciler must not
# touch the row (the wire battery drives the mutation half, scenarios S/G/Q).
# Covered here at CLI-only coverage: the refusal is about the unobserved bit
# itself, not about the store.
# ---------------------------------------------------------------------------
echo "--- 1b. AD-2: the enabled bit is unobservable (a NAMED reason, never SCHEDULED) ---"
B6U="$WORK/box-unobservable"
rr028_make_box "$B6U"
rr028_job "$B6U" "$(no_enabled_job "$B6U" 7)"
state_of "$B6U"
[ "$STATE" = "ENROLLED_PENDING" ] \
  && ok "AD-2: an enabled-unobservable row is ENROLLED_PENDING, never SCHEDULED" \
  || bad "unobservable row claimed a verdict" "$STATE/$REASON"
[ "$REASON" = "cron_enabled_unobservable" ] \
  && ok "AD-2: the reason NAMES the fault (cron_enabled_unobservable)" \
  || bad "reason does not name the unobservable bit" "$STATE/$REASON"
[ "$(rr028_field "$RR028_OUT" cron.state)" = "mismatch" ] \
  && ok "AD-2: the cron readback state is mismatch (the row exists but is not the desired config)" \
  || bad "cron state wrong" "$(rr028_field "$RR028_OUT" cron.state)"
printf '%s' "$(rr028_field "$RR028_OUT" cron.unobservable)" | grep -q 'enabled' \
  && ok "AD-2: the unobservable field is reported by name (enabled)" \
  || bad "unobservable field not reported" "$(rr028_field "$RR028_OUT" cron.unobservable)"
printf '%s' "$RR028_OUT" | grep -q 'tok-synthetic' && bad "report leaked a value" \
  || ok "the unobservable report is still value-free"
# CONTROL: the identical row WITH a boolean enabled is a different, honest
# verdict — the observer can see the opposite, so 1b is not vacuous.
rr028_make_box "$WORK/box-unobservable-control"
rr028_job "$WORK/box-unobservable-control" "$(matching_job "$WORK/box-unobservable-control" 7)"
RR028_JOBS="$WORK/box-unobservable-control/jobs.json" python3 -c '
import json, os, sys
p = os.environ["RR028_JOBS"]
d = json.load(open(p, encoding="utf-8"))
d["jobs"][0]["enabled"] = False
json.dump(d, open(p, "w", encoding="utf-8"))'
state_of "$WORK/box-unobservable-control"
[ "$REASON" = "cron_disabled_by_owner" ] \
  && ok "AD-2 control: the SAME row with an observable enabled=false is cron_disabled_by_owner" \
  || bad "control reason" "$STATE/$REASON"

# ---------------------------------------------------------------------------
# 2. ALL SIX REQUIRED RESOLUTIONS ARE REAL (slug / token / URL / parser /
#    curl / base64 / openclaw / node)
# ---------------------------------------------------------------------------
echo "--- 2. required resolutions are real, not prose ---"
B7="$WORK/box-slug"
rr028_make_box "$B7"
printf 'RR_RECEIVER_URL=http://127.0.0.1:1/rr\nRR_BOX_TOKEN="tok-synthetic-rr028"\n' > "$B7/.openclaw/secrets/.env"
chmod 600 "$B7/.openclaw/secrets/.env"
state_of "$B7"
[ "$STATE" = "UNENROLLED" ] && printf '%s' "$RR028_OUT" | grep -q 'RR_BOX_SLUG' \
  && ok "slug resolution is REQUIRED (absent slug => UNENROLLED naming RR_BOX_SLUG)" \
  || bad "slug not required" "$STATE/$REASON"
B8="$WORK/box-url"
rr028_make_box "$B8"
printf 'RR_BOX_TOKEN="tok-synthetic-rr028"\nRR_BOX_SLUG=box-synthetic\n' > "$B8/.openclaw/secrets/.env"
chmod 600 "$B8/.openclaw/secrets/.env"
state_of "$B8"
[ "$STATE" = "UNENROLLED" ] && printf '%s' "$RR028_OUT" | grep -q 'RR_RECEIVER_URL' \
  && ok "URL resolution is REQUIRED (absent URL => UNENROLLED naming RR_RECEIVER_URL)" \
  || bad "URL not required" "$STATE/$REASON"
# The PARSER requirement: with the shared parser absent the engine must say so.
B9="$WORK/box-noparser"
rr028_make_box "$B9"
rm -f "$B9/.openclaw/skills/shared-utils/rescue-env.sh"
rr028_readiness "$B9" --json >/dev/null 2>&1
[ "$(rr028_field "$RR028_OUT" state)" = "UNENROLLED" ] \
  && printf '%s' "$RR028_OUT" | grep -q 'enrollment_parser_unresolved' \
  && ok "parser resolution is REQUIRED (missing rescue-env.sh => explicit parser reason)" \
  || bad "parser requirement" "$(rr028_field "$RR028_OUT" state)"
# The OPENCLAW requirement (resolved via override so the case is deterministic).
B10="$WORK/box-nooc"
rr028_make_box "$B10"
rr028_job "$B10" "$(matching_job "$B10")"
RR028_EXTRA_ENV="RRR_OPENCLAW_OVERRIDE=/nonexistent/rr028-openclaw" state_of "$B10"
[ "$STATE" = "ENROLLED_PENDING" ] && [ "$REASON" = "runtime_requirement_unresolved" ] \
  && printf '%s' "$RR028_OUT" | grep -q '"missing":"openclaw"' \
  && ok "OpenClaw resolution is REQUIRED (named in the reason)" || bad "openclaw requirement" "$STATE/$REASON"

# ---------------------------------------------------------------------------
# 3. READBACK: command / schedule / delivery / enabled / duplicates / unreadable
# ---------------------------------------------------------------------------
echo "--- 3. reconcile with READBACK, never assume ---"
B11="$WORK/box-stale"
rr028_make_box "$B11"
rr028_job "$B11" "{\"id\":\"7\",\"name\":\"rescue-rr-box-poll\",\"enabled\":true,\"schedule\":{\"kind\":\"cron\",\"expr\":\"*/2 * * * *\"},\"payload\":{\"kind\":\"command\",\"command\":\"sh /gone/rescue-poll.sh\"},\"delivery\":{\"mode\":\"none\"}}"
state_of "$B11"
[ "$STATE" = "ENROLLED_PENDING" ] && [ "$REASON" = "cron_field_mismatch" ] \
  && printf '%s' "$RR028_OUT" | grep -q 'command' \
  && ok "stale COMMAND read back as a mismatch (reason=$REASON)" || bad "command mismatch" "$STATE/$REASON"

B12="$WORK/box-sched-wrong"
rr028_make_box "$B12"
rr028_job "$B12" "$(matching_job "$B12" 8 '{"schedule":{"kind":"cron","expr":"*/30 * * * *"}}')"
state_of "$B12"
[ "$STATE" = "ENROLLED_PENDING" ] && printf '%s' "$RR028_OUT" | grep -q 'schedule' \
  && ok "wrong SCHEDULE read back as a mismatch" || bad "schedule mismatch" "$STATE/$REASON"

B13="$WORK/box-deliver"
rr028_make_box "$B13"
rr028_job "$B13" "$(matching_job "$B13" 9 '{"delivery":{"mode":"announce","to":"12345"}}')"
state_of "$B13"
[ "$STATE" = "ENROLLED_PENDING" ] && printf '%s' "$RR028_OUT" | grep -q 'delivery' \
  && ok "delivery flag left ON is read back as a mismatch (no client spam unnoticed)" \
  || bad "delivery mismatch" "$STATE/$REASON"

B14="$WORK/box-disabled"
rr028_make_box "$B14"
rr028_job "$B14" "$(matching_job "$B14" 10 '{"enabled":false}')"
state_of "$B14"
[ "$STATE" = "ENROLLED_PENDING" ] && [ "$REASON" = "cron_disabled_by_owner" ] \
  && ok "DISABLED job is SEEN and reported (reason=$REASON; never silently re-enabled)" \
  || bad "disabled job" "$STATE/$REASON"
[ "$(rr028_field "$RR028_OUT" cron.count)" = "1" ] \
  && ok "control: the disabled job WAS visible to the readback (--all feature-detected)" \
  || bad "disabled job invisible to the readback — the enabled check cannot be proven"

B15="$WORK/box-dupes"
rr028_make_box "$B15"
rr028_job "$B15" "$(matching_job "$B15" 11)"
rr028_job "$B15" "$(matching_job "$B15" 12)"
state_of "$B15"
[ "$STATE" = "ENROLLED_PENDING" ] && [ "$REASON" = "cron_duplicate" ] \
  && [ "$(rr028_field "$RR028_OUT" cron.count)" = "2" ] \
  && ok "DUPLICATE jobs are read back and reported (count=2)" || bad "duplicates" "$STATE/$REASON"

B16="$WORK/box-unreadable"
rr028_make_box "$B16"
rr028_job "$B16" "$(matching_job "$B16")"
RR028_EXTRA_ENV="RR028_MOCK_LIST_MODE=unreadable" state_of "$B16"
[ "$STATE" = "ENROLLED_PENDING" ] && [ "$REASON" = "cron_readback_unreadable" ] \
  && ok "an UNREADABLE readback is never a success (reason=$REASON)" || bad "unreadable readback" "$STATE/$REASON"

# ---------------------------------------------------------------------------
# 4. DESIRED-CONFIG DIGEST KEYING
# ---------------------------------------------------------------------------
echo "--- 4. readiness keyed by the desired-config digest ---"
B17="$WORK/box-digest"
rr028_make_box "$B17"
rr028_job "$B17" "$(matching_job "$B17")"
P17="$(rr028_port 17)"
rr028_start_receiver "$B17" "$P17" no_work || bad "digest receiver did not start"
set_store_url() {  # set_store_url <box> <port> <token>
  printf 'RR_RECEIVER_URL=http://127.0.0.1:%s/rr\nRR_BOX_TOKEN="%s"\nRR_BOX_SLUG=box-synthetic\n' "$2" "$3" \
    > "$1/.openclaw/secrets/.env"
  chmod 600 "$1/.openclaw/secrets/.env"
}
set_store_url "$B17" "$P17" tok-synthetic-rr028
state_of "$B17"
D1="$(rr028_field "$RR028_OUT" digest)"
state_of "$B17"
D2="$(rr028_field "$RR028_OUT" digest)"
[ -n "$D1" ] && [ "$D1" = "$D2" ] \
  && ok "the digest is stable across runs for an unchanged desired config" \
  || bad "digest not stable" "$D1 vs $D2"
# Rotate the token: the desired config changed, so the verdict must be re-proven.
set_store_url "$B17" "$P17" tok-synthetic-ROTATED
state_of "$B17"
D3="$(rr028_field "$RR028_OUT" digest)"
[ -n "$D3" ] && [ "$D3" != "$D1" ] \
  && ok "a changed desired config (token rotation) changes the digest" \
  || bad "digest ignored the desired-config change" "$D1 == $D3"
# A verified receipt for the OLD digest must NOT verify the new one.
rr028_readiness "$B17" --probe >/dev/null 2>&1
state_of "$B17"
[ "$STATE" = "VERIFIED" ] && ok "control: the rotated box can be verified (probe works)" \
  || bad "control probe after rotation" "$STATE/$REASON"
set_store_url "$B17" "$P17" tok-synthetic-ROTATED-AGAIN
state_of "$B17"
[ "$STATE" = "SCHEDULED" ] && [ "$REASON" = "ready_receipt_stale" ] \
  && ok "the receipt is keyed by digest: a NEW desired config voids it (reason=$REASON)" \
  || bad "stale receipt did not void" "$STATE/$REASON"
# M-6 (+ re-review Z-6): with SEVERAL superseded receipts, name the NEWEST one
# from THIS runtime — and make that naming OBSERVABLE in the detail. The detail
# used to be computed and then silently discarded by the `stale` arm, so the
# M-6 claim ("names the file") could not be checked anywhere.
B17B="$WORK/box-superseded"
rr028_make_box "$B17B"
rr028_job "$B17B" "$(matching_job "$B17B")"
state_of "$B17B"
RID="$(rr028_field "$RR028_OUT" runtime.id)"
[ -n "$RID" ] \
  && ok "fixture: the intended runtime id resolves, so 'from THIS runtime' is testable" \
  || bad "runtime id unresolved — the M-6 case cannot be built" "$STATE/$REASON"
mkdir -p "$B17B/.openclaw/state/rr-receiver/readiness"
mk_superseded() {  # mk_superseded <file-digest> <runtime-id> <at>
    printf '{"schema":"rr-028/readiness-receipt/1","state":"VERIFIED","digest":"%s","runtime_id":"%s","claim":{"kind":"safe_test_claim","agent_turns":0,"acks_sent":0},"evidence":{"transport":"ok","http_status":200,"structured":true,"response_class":"no_work"},"at":"%s"}\n' \
      "$1" "$2" "$3" > "$B17B/.openclaw/state/rr-receiver/readiness/receipt-$1.json"
}
# Glob order aaaa,bbbb,cccc,dddd. aaaa is FOREIGN and dated 2030 (the first in
# glob order — what the pre-M-6 code named); bbbb is the newest from the
# intended runtime; cccc older from the intended runtime; dddd foreign, 2010.
mk_superseded aaaa "deadbeef-foreign-runtime" "2030-01-01T00:00:00Z"
mk_superseded bbbb "$RID" "2025-01-01T00:00:00Z"
mk_superseded cccc "$RID" "2020-01-01T00:00:00Z"
mk_superseded dddd "deadbeef-foreign-runtime" "2010-01-01T00:00:00Z"
state_of "$B17B"
[ "$STATE" = "SCHEDULED" ] && [ "$REASON" = "ready_receipt_stale" ] \
  && ok "control: four superseded receipts still yield ready_receipt_stale" \
  || bad "the superseded-receipt case is not the stale state" "$STATE/$REASON"
[ "$(rr028_field "$RR028_OUT" receipt.at)" = "2025-01-01T00:00:00Z" ] \
  && ok "M-6: receipt.at names the NEWEST superseded receipt from the INTENDED runtime (2025, not the foreign 2030)" \
  || bad "receipt.at names the wrong superseded receipt" "$(rr028_field "$RR028_OUT" receipt.at)"
printf '%s' "$RR028_OUT" | grep -q 'receipt-bbbb\.json' \
  && ok "Z-6: the stale detail NAMES that receipt file, so the M-6 claim is observable" \
  || bad "the stale detail does not name the superseded receipt (the M-6 detail is unreachable)" \
         "$(rr028_field "$RR028_OUT" detail)"
printf '%s' "$RR028_OUT" | grep -q 'receipt-aaaa\.json' \
  && bad "the stale detail names the FOREIGN, glob-first receipt" \
  || ok "Z-6: the foreign glob-first receipt (2030) is NOT the one named"
printf '%s' "$RR028_OUT" | grep -q 'other superseded receipts may also exist' \
  && ok "Z-6: the detail keeps the 'other superseded receipts may also exist' caveat" \
  || bad "the detail drops the other-receipts caveat"
# And a receipt from a DIFFERENT runtime must not verify this one.
B18="$WORK/box-foreign"
rr028_make_box "$B18"
rr028_job "$B18" "$(matching_job "$B18")"
state_of "$B18"
DG="$(rr028_field "$RR028_OUT" digest)"
mkdir -p "$B18/.openclaw/state/rr-receiver/readiness"
printf '{"schema":"rr-028/readiness-receipt/1","state":"VERIFIED","digest":"%s","runtime_id":"deadbeef-other-runtime","claim":{"kind":"safe_test_claim","agent_turns":0,"acks_sent":0},"evidence":{"transport":"ok","http_status":200,"structured":true,"response_class":"no_work"},"at":"2026-01-01T00:00:00Z"}\n' "$DG" \
  > "$B18/.openclaw/state/rr-receiver/readiness/receipt-$DG.json"
state_of "$B18"
[ "$STATE" = "SCHEDULED" ] && [ "$REASON" = "ready_receipt_foreign_runtime" ] \
  && ok "a receipt from a FOREIGN runtime cannot verify the intended one (reason=$REASON)" \
  || bad "foreign receipt accepted" "$STATE/$REASON"

# ---------------------------------------------------------------------------
# 5. VERSION INDEPENDENCE
# ---------------------------------------------------------------------------
echo "--- 5. reconciliation is independent of the software version ---"
B19="$WORK/box-version"
rr028_make_box "$B19"
rr028_job "$B19" "$(matching_job "$B19")"
state_of "$B19"
V_STATE_A="$STATE"; V_REASON_A="$REASON"; V_DIGEST_A="$(rr028_field "$RR028_OUT" digest)"
RR028_EXTRA_ENV="ONBOARDING_VERSION=v1.2.3 RECEIVER_VERSION=9.9.9 ONBOARDING_SKILL_VERSION=v0.0.1" state_of "$B19"
V_STATE_B="$STATE"; V_REASON_B="$REASON"; V_DIGEST_B="$(rr028_field "$RR028_OUT" digest)"
RR028_EXTRA_ENV="ONBOARDING_VERSION=v99.0.0 RECEIVER_VERSION=1.0.0" state_of "$B19"
V_STATE_C="$STATE"; V_REASON_C="$REASON"; V_DIGEST_C="$(rr028_field "$RR028_OUT" digest)"
if [ "$V_STATE_A" = "$V_STATE_B" ] && [ "$V_STATE_B" = "$V_STATE_C" ] \
   && [ "$V_REASON_A" = "$V_REASON_B" ] && [ "$V_REASON_B" = "$V_REASON_C" ] \
   && [ "$V_DIGEST_A" = "$V_DIGEST_B" ] && [ "$V_DIGEST_B" = "$V_DIGEST_C" ]; then
  ok "identical verdict + digest across a simulated version change ($V_STATE_A/$V_REASON_A)"
else
  bad "version change altered the verdict" "$V_STATE_A/$V_STATE_B/$V_STATE_C"
fi
# A version sentinel is NOT evidence of scheduling.
B20="$WORK/box-sentinel"
rr028_make_box "$B20"
: > "$B20/.openclaw/skills/65-rescue-receiver/.wired-v99.0.0"
: > "$B20/.openclaw/skills/65-rescue-receiver/.wired-v1.2.3"
state_of "$B20"
[ "$STATE" = "ENROLLED_PENDING" ] && [ "$REASON" = "cron_absent" ] \
  && ok "a .wired-<version> sentinel is NEVER evidence of a scheduled cron (state=$STATE)" \
  || bad "sentinel mistaken for scheduling" "$STATE/$REASON"
# Static guard: the engine's CODE must not read any version marker at all
# (comments explaining that rule are stripped first — the rule is about inputs).
if sed 's/#.*$//' "$REPO/shared-utils/rr-readiness.sh" \
   | grep -nE 'ONBOARDING_VERSION|RECEIVER_VERSION|\.wired-|skill-version' >/dev/null 2>&1; then
  bad "the readiness engine reads a software version marker (must be version-independent)"
else
  ok "the readiness engine's code references NO software version marker"
fi
# Static guard: update-skills.sh reconciles this skill BEFORE the sentinel gate.
if python3 - "$REPO/update-skills.sh" <<'PY'
import sys
src = open(sys.argv[1], encoding="utf-8", errors="replace").read()
reconcile = src.find('"65-rescue-receiver" ] && [ -x "$SKILL_DIR/wire.sh"')
sentinel = src.find('WIRED_SENTINEL="$SKILL_DIR/.wired-${ONBOARDING_VERSION}"')
sys.exit(0 if 0 <= reconcile < sentinel else 1)
PY
then
  ok "update-skills.sh runs 65-rescue-receiver reconciliation BEFORE the .wired sentinel gate"
else
  bad "update-skills.sh still version-gates enrollment/cron reconciliation"
fi

# ---------------------------------------------------------------------------
# 6. argv SAFETY
# ---------------------------------------------------------------------------
echo "--- 6. argv-safe invocation ---"
cat > "$WORK/argv-recorder" <<'RECEOF'
#!/usr/bin/env bash
printf 'ARGC %d\n' "$#"
i=0
for a in "$@"; do
  printf 'ARGV %d [%s]\n' "$i" "$a"
  i=$((i + 1))
done
RECEOF
chmod +x "$WORK/argv-recorder"
CANARY="$WORK/canary-should-not-exist"
ARGV_OUT="$WORK/argv-out"
rm -f "$CANARY" "$ARGV_OUT"
RR028_ARGV_OUT="$ARGV_OUT" RR028_RECORDER="$WORK/argv-recorder" RR028_CANARY="$CANARY" bash -c '
  set -u
  . "$RR028_REPO/shared-utils/rr-readiness.sh"
  rrr_argv_run "$RR028_ARGV_OUT" /dev/null "$RR028_RECORDER" \
      "two words" "semi;colon" "star*glob" "dollar\$(touch $RR028_CANARY)" "quote\"inside" "back\`tick"
  echo "rc=$RRR_ARGV_RC"
' 2>/dev/null > "$WORK/argv-result" || true
if grep -q '^ARGC 6$' "$ARGV_OUT" 2>/dev/null; then
  ok "rrr_argv_run passes 6 metacharacter-bearing arguments as 6 argv elements"
else
  bad "rrr_argv_run word-split or swallowed an argument" "$(head -3 "$WORK/argv-result" 2>/dev/null)"
fi
grep -qF 'ARGV 0 [two words]' "$ARGV_OUT" 2>/dev/null \
  && ok "an argument containing a space arrives intact (not word-split)" || bad "spaced argument mangled"
grep -qF 'ARGV 1 [semi;colon]' "$ARGV_OUT" 2>/dev/null \
  && ok "an argument containing ';' arrives intact" || bad "';' mangled"
[ -e "$CANARY" ] && bad "command substitution in an argument EXECUTED (injection)" \
  || ok "no injection: the \$(...) payload was passed literally, never executed"
# CONTROL: the naive string/eval form of the SAME payload DOES execute it, so
# the assertion above can actually fail (it is not vacuously true).
rm -f "$CANARY"
bash -c 'X="'"$CANARY"'"; v="\$(touch $X)"; eval "echo $v" >/dev/null 2>&1; :' || true
if [ -e "$CANARY" ]; then
  ok "control: the naive eval/string form DOES execute the payload (the guard discriminates)"
  rm -f "$CANARY"
else
  naive_args="$(bash -c 'set -- two words; echo "$#"' 2>/dev/null)"
  [ "$naive_args" = "2" ] \
    && ok "control: an unquoted string form DOES word-split (the guard discriminates)" \
    || bad "control could not demonstrate splitting — argv assertion may be vacuous"
fi

# The REAL wiring path: a box root full of spaces, ';' and $( ).
WEIRD="$(rr028_weird_root)"
rm -rf "$WEIRD"
mkdir -p "$WEIRD"
BW="$WEIRD/box"
rr028_make_box "$BW"
[ -f "$BW/.openclaw/skills/65-rescue-receiver/rescue-poll.sh" ] \
  && ok "a box root containing spaces, ';' and \$( ) installs normally" || bad "weird root install failed"
# Register through the same weird root and inspect the REAL argv vector of the
# mock CLI: the poll path must arrive as ONE element (the path contains a
# space, so a re-split would show two fragments and a wrong --command value).
printf '{"jobs":[]}' > "$BW/jobs.json"
rr028_wire "$BW" >/dev/null 2>&1
WANT_CMD="sh $BW/.openclaw/skills/65-rescue-receiver/rescue-poll.sh"
ADD_BLOCK="$(rr028_argv_blocks "$BW" | grep -F -e '--name' | head -1 || true)"
if [ -z "$ADD_BLOCK" ]; then
  bad "no cron add argv was recorded for the weird-root box"
else
  printf '%s' "$ADD_BLOCK" | tr '\037' '\n' > "$WORK/add-argv.txt"
  if grep -qxF -- "$WANT_CMD" "$WORK/add-argv.txt"; then
    ok "the cron --command argument is ONE argv element carrying the spaced poll path"
  else
    bad "poll path was split/altered in argv" "$(grep -c . "$WORK/add-argv.txt") elements"
  fi
  if grep -qxF -- '--name' "$WORK/add-argv.txt" && grep -qxF -- 'rescue-rr-box-poll' "$WORK/add-argv.txt"; then
    ok "the cron --name argument is its own argv element (no string re-splitting)"
  else
    bad "--name/--value not separate argv elements"
  fi
fi
ls "$WEIRD" 2>/dev/null | grep -q 'PWNED' && bad "injection: a PWNED file appeared in the weird root" \
  || ok "no injection through the box root path (no PWNED artifact)"
# Control: the stored job proves the readback path also took the whole command.
# Read through rr028_stored_command -- the SAME order the engine readback uses --
# because `payload.command` is a field the real CLI never populates, and reading
# it directly is how this battery once agreed with a double that was wrong.
SCMD="$(rr028_stored_command "$BW/jobs.json")"
if [ -n "$SCMD" ] && [ "$SCMD" != "${SCMD% *}" ] && [ "$SCMD" = "$WANT_CMD" ]; then
  ok "the job the mock STORED carries the full spaced command (round-trip intact)"
else
  bad "stored job command is truncated or split" "[$SCMD]"
fi

echo ""
echo "RESULT: $PASS passed, $FAIL failed, $SKIP skipped"
RR028_DONE=1
[ "$FAIL" -eq 0 ] || exit 1
exit 0
