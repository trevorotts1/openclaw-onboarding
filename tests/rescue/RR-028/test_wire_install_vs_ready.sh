#!/usr/bin/env bash
# tests/rescue/RR-028/test_wire_install_vs_ready.sh — RR-028 gate (ONB receiver).
#
# Pins required behaviours 5, 7 and 2 at the INSTALLER:
#   * wire.sh's exit code is the INSTALLER's claim (files installed). It is
#     NEVER "receiver ready" — the readiness line it prints is a separate claim
#     that still needs a safe test claim receipt.
#   * a write that does not READ BACK is never reported as success;
#   * duplicates, command, schedule, enabled state and delivery flags are
#     reconciled against the readback;
#   * reconciliation is NOT version-gated (a `.wired-<version>` sentinel and a
#     changed software version change nothing);
#   * an operator-disabled cron or a tombstone is never resurrected.
#
# Every case drives the REAL wire.sh against a synthetic box + mock CLI and
# asserts on the printed readiness line, the rc, and the STORE the mock wrote.
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

echo "== RR-028: installer vs readiness, reconciliation with readback =="
echo "   host: $(uname -s) $(uname -m)"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/rr028-wire.XXXXXX")"
RR028_DONE=""
trap '[ -n "$RR028_DONE" ] && { rr028_stop_receiver; rm -rf "$WORK"; }' EXIT

matching_job() {  # matching_job <box> [overrides-json]
  _box="$1"; _ov="${2:-}"
  _cmd="sh $_box/.openclaw/skills/65-rescue-receiver/rescue-poll.sh"
  _base="{\"id\":\"1\",\"name\":\"rescue-rr-box-poll\",\"enabled\":true,\"schedule\":{\"kind\":\"cron\",\"expr\":\"*/2 * * * *\"},\"payload\":{\"kind\":\"command\",\"command\":\"$_cmd\"},\"delivery\":{\"mode\":\"none\"}}"
  if [ -n "$_ov" ]; then
    RR028_BASE="$_base" RR028_OV="$_ov" python3 -c '
import json, os
b = json.loads(os.environ["RR028_BASE"]); b.update(json.loads(os.environ["RR028_OV"])); print(json.dumps(b))'
  else
    printf '%s' "$_base"
  fi
}

jobs_len() { RR028_JOBS="$1/jobs.json" python3 -c 'import json,os; print(len(json.load(open(os.environ["RR028_JOBS"]))["jobs"]))'; }
job_field() { RR028_JOBS="$1/jobs.json" RR028_F="$2" python3 -c '
import json, os
d = json.load(open(os.environ["RR028_JOBS"], encoding="utf-8"))
j = (d["jobs"] or [{}])[0]
o = j
for k in os.environ["RR028_F"].split("."):
    o = (o or {}).get(k) if isinstance(o, dict) else None
print(o if o is not None else "")'; }
wire_state() { printf '%s' "$1" | sed -n 's/.*readiness=\([A-Z_]*\).*/\1/p' | head -1; }
wire_reason() { printf '%s' "$1" | sed -n 's/.*reason=\([a-z_]*\).*/\1/p' | head -1; }

new_box() {  # new_box <name> [store-file]
  BOX="$WORK/$1"
  rr028_make_box "$BOX" "${2:-}"
  RR028_STDERR="$BOX/probe.err"
  : > "$RR028_STDERR"
}

# run_wire — runs wire.sh on $BOX, leaves WRC (exit code) and WOUT (stdout).
WRC=0; WOUT=""
run_wire() {
  rr028_wire "$BOX" >/dev/null 2>&1
  WRC=$?
  WOUT="$RR028_OUT"
}

# ---------------------------------------------------------------------------
# 1. FILES INSTALLED != READY
# ---------------------------------------------------------------------------
echo "--- 1. installer success is files-installed, never receiver-ready ---"
new_box box-ready
rr028_job "$BOX" "$(matching_job "$BOX")"
P_READY="$(rr028_port 40)"
printf 'RR_RECEIVER_URL=http://127.0.0.1:%s/rr\nRR_BOX_TOKEN="tok-synthetic-rr028"\nRR_BOX_SLUG=box-synthetic\n' "$P_READY" \
  > "$BOX/.openclaw/secrets/.env"; chmod 600 "$BOX/.openclaw/secrets/.env"
rr028_start_receiver "$BOX" "$P_READY" no_work || bad "receiver stub for the verified control failed to start"
run_wire
OUT="$WOUT"
[ "$WRC" = "0" ] && ok "wire.sh exits 0 with the cron already correct (installer claim)" \
  || bad "wire.sh rc=$WRC with a correct cron"
printf '%s' "$OUT" | grep -q 'files-installed=1' \
  && ok "the installer states its own claim explicitly (files-installed=1)" \
  || bad "installer claim line missing"
[ "$(wire_state "$OUT")" = "SCHEDULED" ] \
  && ok "readiness is reported SEPARATELY as SCHEDULED (no receipt yet)" \
  || bad "readiness line wrong" "$(wire_state "$OUT")"
printf '%s' "$OUT" | grep -q 'readiness=VERIFIED' \
  && bad "wire.sh claimed VERIFIED without any safe test claim receipt" \
  || ok "wire.sh NEVER claims VERIFIED without a verified receipt"
printf '%s' "$OUT" | grep -qi 'separate claim' \
  && ok "the output says receiver readiness is a SEPARATE claim" \
  || bad "the output does not separate installation from readiness"
# The claim is reachable only through the probe.
rr028_readiness "$BOX" --probe >/dev/null 2>&1
run_wire
[ "$(wire_state "$WOUT")" = "VERIFIED" ] \
  && ok "control: after a safe test claim receipt the SAME box reports VERIFIED" \
  || bad "verified control failed" "$(wire_state "$WOUT")"

# ---------------------------------------------------------------------------
# 2. A WRITE THAT DOES NOT READ BACK IS NOT SUCCESS (the failing-readback plant)
# ---------------------------------------------------------------------------
echo "--- 2. a write that does not read back is NOT reported as success ---"
new_box box-silent
RR028_EXTRA_ENV="RR028_MOCK_ADD_MODE=silent" run_wire
OUT="$WOUT"
[ "$WRC" = "0" ] && ok "the add command exited 0 and the installer claim is still files-installed" \
  || bad "wire.sh rc=$WRC"
[ "$(wire_state "$OUT")" = "ENROLLED_PENDING" ] \
  && ok "the READBACK (not the exit code) decides: readiness=ENROLLED_PENDING" \
  || bad "readback failure reported as success" "$(wire_state "$OUT")"
printf '%s' "$OUT" | grep -q 'readiness=SCHEDULED' && bad "a non-read-back write was reported SCHEDULED" \
  || ok "the failing readback is NEVER reported as SCHEDULED"
printf '%s' "$OUT" | grep -qi 'not verified' \
  && ok "the output says the receiver readiness is NOT verified" || bad "no not-verified warning"
rr028_readiness "$BOX" --json >/dev/null 2>&1
[ "$(rr028_field "$RR028_OUT" state)" = "ENROLLED_PENDING" ] \
  && [ "$(rr028_field "$RR028_OUT" reason)" = "cron_absent" ] \
  && ok "the independent report agrees: ENROLLED_PENDING/cron_absent" \
  || bad "independent report disagrees" "$(rr028_field "$RR028_OUT" state)"
# CONTROL: the same box with a working add IS scheduled — so the assertion above
# is about the readback, not about the box being broken.
new_box box-silent-control
run_wire
[ "$(wire_state "$WOUT")" = "SCHEDULED" ] \
  && ok "control: the same box with a working add IS SCHEDULED (the guard discriminates)" \
  || bad "control box not scheduled" "$(wire_state "$WOUT")"

# A mutation command that FAILS is a retryable wiring failure (rc=1).
new_box box-rejected
RR028_EXTRA_ENV="RR028_MOCK_ADD_MODE=reject" run_wire
[ "$WRC" = "1" ] && ok "a FAILED cron mutation exits 1 (retryable wiring failure)" \
  || bad "failed mutation did not exit 1"

# ---------------------------------------------------------------------------
# 3. DUPLICATES, COMMAND, SCHEDULE, ENABLED, DELIVERY — all with readback
# ---------------------------------------------------------------------------
echo "--- 3. duplicate / command / enabled reconciliation with readback ---"
new_box box-dupes
rr028_job "$BOX" "$(matching_job "$BOX" '{"id":"5"}')"
rr028_job "$BOX" '{"id":"6","name":"rescue-rr-box-poll","enabled":true,"schedule":{"kind":"cron","expr":"*/2 * * * *"},"payload":{"kind":"command","command":"sh /gone/stale-poll.sh"},"delivery":{"mode":"none"}}'
[ "$(jobs_len "$BOX")" = "2" ] && ok "planted: two jobs carry the managed name" || bad "plant failed"
run_wire
[ "$(jobs_len "$BOX")" = "1" ] \
  && ok "duplicates are collapsed to exactly ONE job (readback-confirmed)" \
  || bad "duplicates remain" "$(jobs_len "$BOX") jobs"
[ "$(job_field "$BOX" id)" = "5" ] \
  && ok "the MATCHING job was kept and the stale duplicate removed" \
  || bad "wrong job kept" "id=$(job_field "$BOX" id)"
[ "$(wire_state "$WOUT")" = "SCHEDULED" ] \
  && ok "readiness=SCHEDULED after the dedupe" || bad "not scheduled after dedupe"

new_box box-stale-cmd
rr028_job "$BOX" '{"id":"9","name":"rescue-rr-box-poll","enabled":true,"schedule":{"kind":"cron","expr":"*/2 * * * *"},"payload":{"kind":"command","command":"sh /gone/rescue-poll.sh"},"delivery":{"mode":"none"}}'
run_wire
WANT="sh $BOX/.openclaw/skills/65-rescue-receiver/rescue-poll.sh"
[ "$(job_field "$BOX" payload.command)" = "$WANT" ] \
  && ok "a stale COMMAND is reconciled in place to the desired command" \
  || bad "command not reconciled" "$(job_field "$BOX" payload.command)"
[ "$(job_field "$BOX" id)" = "9" ] \
  && ok "reconciled IN PLACE (the job id and its run history survive)" \
  || bad "job was replaced instead of edited" "id=$(job_field "$BOX" id)"
[ "$(wire_state "$WOUT")" = "SCHEDULED" ] \
  && ok "readiness=SCHEDULED after the edit" || bad "not scheduled after edit"

new_box box-noedit
rr028_job "$BOX" '{"id":"3","name":"rescue-rr-box-poll","enabled":true,"schedule":{"kind":"cron","expr":"*/30 * * * *"},"payload":{"kind":"command","command":"sh /gone/rescue-poll.sh"},"delivery":{"mode":"none"}}'
RR028_EXTRA_ENV="RR028_MOCK_NO_EDIT_FLAGS=1" run_wire
[ "$(job_field "$BOX" schedule.expr)" = "*/2 * * * *" ] \
  && ok "a CLI that cannot edit falls back to replace, and the schedule IS reconciled" \
  || bad "schedule not reconciled without edit support" "$(job_field "$BOX" schedule.expr)"
[ "$(wire_state "$WOUT")" = "SCHEDULED" ] \
  && ok "readback confirms the replacement" || bad "not scheduled after replacement"

new_box box-disabled
rr028_job "$BOX" "$(matching_job "$BOX" '{"enabled":false}')"
run_wire
[ "$(wire_state "$WOUT")" = "ENROLLED_PENDING" ] \
  && ok "a DISABLED job is reported ENROLLED_PENDING, never silently 'already wired'" \
  || bad "disabled job reported ready" "$(wire_state "$WOUT")"
[ "$(wire_reason "$WOUT")" = "cron_disabled_by_owner" ] \
  && ok "reason names the operator's disable (cron_disabled_by_owner)" \
  || bad "reason wrong" "$(wire_reason "$WOUT")"
[ "$(job_field "$BOX" enabled)" = "False" ] \
  && ok "the job is STILL DISABLED after the wire run (never re-enabled behind the operator)" \
  || bad "wire.sh re-enabled an operator-disabled cron"
rr028_argv_blocks "$BOX" | grep -q 'cron.add\|cron.edit' \
  && bad "wire.sh mutated a job it must not touch" \
  || ok "no add/edit was issued for the disabled job"

new_box box-tombstone
mkdir -p "$BOX/.openclaw/workspace/.cron-tombstones"
: > "$BOX/.openclaw/workspace/.cron-tombstones/rescue-rr-box-poll"
run_wire
[ "$(jobs_len "$BOX")" = "0" ] \
  && ok "a tombstoned name is NOT resurrected (0 jobs created)" || bad "tombstone ignored"
[ "$(wire_reason "$WOUT")" = "cron_tombstoned" ] \
  && ok "the readiness reason names the tombstone" || bad "reason wrong" "$(wire_reason "$WOUT")"

# ---------------------------------------------------------------------------
# 4. VERSION INDEPENDENCE AT THE INSTALLER
# ---------------------------------------------------------------------------
echo "--- 4. reconciliation is not version-gated ---"
new_box box-sentinel
: > "$BOX/.openclaw/skills/65-rescue-receiver/.wired-v99.0.0"
RR028_EXTRA_ENV="ONBOARDING_VERSION=v99.0.0" run_wire
[ "$(jobs_len "$BOX")" = "1" ] \
  && ok "a .wired-<version> sentinel does not stop reconciliation (cron registered)" \
  || bad "version sentinel suppressed reconciliation" "$(jobs_len "$BOX") jobs"
[ "$(wire_state "$WOUT")" = "SCHEDULED" ] \
  && ok "the box is SCHEDULED on readback regardless of the sentinel" || bad "not scheduled"
# Same box, a DIFFERENT version: the verdict and the job are unchanged.
run_wire
[ "$(jobs_len "$BOX")" = "1" ] && [ "$(wire_state "$WOUT")" = "SCHEDULED" ] \
  && ok "a second pass at the same version is a no-op (idempotent, one job)" \
  || bad "second pass changed state" "$(jobs_len "$BOX") jobs $(wire_state "$WOUT")"
RR028_EXTRA_ENV="ONBOARDING_VERSION=v100.0.0" run_wire
[ "$(jobs_len "$BOX")" = "1" ] && [ "$(wire_state "$WOUT")" = "SCHEDULED" ] \
  && ok "a version change does not duplicate or re-verdict the cron" \
  || bad "version change altered reconciliation" "$(jobs_len "$BOX") jobs"

# ---------------------------------------------------------------------------
# 5. THE DARK PATH AND THE FAIL-CLOSED PATH
# ---------------------------------------------------------------------------
echo "--- 5. unenrolled / malformed / CLI-unresolved ---"
new_box box-unenrolled
printf 'RR_BOX_SLUG=box-synthetic\n' > "$BOX/.openclaw/secrets/.env"
chmod 600 "$BOX/.openclaw/secrets/.env"
run_wire
WRC=$?
[ "$WRC" = "0" ] && [ "$(wire_state "$WOUT")" = "UNENROLLED" ] \
  && ok "not enrolled: rc 0 (nothing to wire) with an explicit UNENROLLED state" \
  || bad "unenrolled path" "rc=$WRC $(wire_state "$WOUT")"
[ "$(jobs_len "$BOX")" = "0" ] && ok "no cron registered for an unenrolled box" || bad "cron registered while dark"

new_box box-malformed
{ printf 'RR_RECEIVER_URL=http://127.0.0.1:1/rr\n'; printf 'JUNKLINE\n'; } > "$BOX/.openclaw/secrets/.env"
chmod 600 "$BOX/.openclaw/secrets/.env"
run_wire
[ "$WRC" = "1" ] && ok "a MALFORMED store still fails visibly with rc 1 (RR-027 contract held)" \
  || bad "malformed store no longer exits 1"
grep -q 'malformed line' "$BOX/probe.err" && ok "the malformed line is named on stderr" \
  || bad "malformed reason missing"

new_box box-nooc
# PATH without the mock AND without a resolvable absolute fallback for this HOME.
rr028_jobs_backup="$(cat "$BOX/jobs.json")"
OUT="$(env -u RR028_JOBS RR_ROOT="$BOX/.openclaw" OC_CONFIG_ROOT="$BOX/.openclaw" \
      OC_PLATFORM=mac OC_TARGET_MODE=launchd OC_SKIP_CLI_PROBE=1 HOME="$BOX" \
      PATH="/usr/bin:/bin" bash "$BOX/.openclaw/skills/65-rescue-receiver/wire.sh" 2>&1)"
WRC=$?
if [ -x /opt/homebrew/bin/openclaw ] || [ -x /usr/local/bin/openclaw ]; then
  skip "OpenClaw CLI absent-path case (an absolute fallback CLI exists on this host)"
else
  [ "$WRC" = "1" ] && ok "an unresolvable OpenClaw CLI exits 1 (retryable, never silent)" \
    || bad "missing CLI rc=$WRC"
fi

# ---------------------------------------------------------------------------
# 6. TWO-VIEW READBACK: the disabled job the CLI hides
# ---------------------------------------------------------------------------
echo "--- 6. the disabled job the CLI alone cannot see ---"
if ! command -v sqlite3 >/dev/null 2>&1; then
  skip "two-view readback case (no sqlite3 CLI on this host — the DB view is unavailable)"
else
  new_box box-dbview
  rr028_job "$BOX" "$(matching_job "$BOX" '{"id":"4","enabled":false}')"
  rr028_make_db "$BOX" || bad "could not build the state DB fixture"
  [ -s "$BOX/.openclaw/state/openclaw.sqlite" ] \
    && ok "planted: the job is DISABLED and present in the gateway store" || bad "DB fixture missing"
  # This CLI build advertises no --all: disabled jobs are hidden from `cron list`.
  RR028_EXTRA_ENV="RR028_MOCK_NO_ALL=1" rr028_readiness "$BOX" --json >/dev/null 2>&1
  [ "$(rr028_field "$RR028_OUT" cron.coverage)" = "cli+db" ] \
    && ok "the readback used BOTH views (coverage=cli+db)" \
    || bad "coverage wrong" "$(rr028_field "$RR028_OUT" cron.coverage)"
  [ "$(rr028_field "$RR028_OUT" reason)" = "cron_disabled_by_owner" ] \
    && ok "the DISABLED job hidden from the CLI is still seen via the gateway store" \
    || bad "two-view readback failed" "$(rr028_field "$RR028_OUT" reason)"
  # Without the DB the same box is honestly reported as CLI-ONLY coverage, and
  # an absence is never presented as a DB-proven absence.
  mv "$BOX/.openclaw/state/openclaw.sqlite" "$BOX/openclaw.sqlite.bak"
  RR028_EXTRA_ENV="RR028_MOCK_NO_ALL=1" rr028_readiness "$BOX" --json >/dev/null 2>&1
  [ "$(rr028_field "$RR028_OUT" cron.coverage)" = "cli-only" ] \
    && ok "with no state DB the coverage is reported as cli-only (never overclaimed)" \
    || bad "coverage overclaimed" "$(rr028_field "$RR028_OUT" cron.coverage)"
  [ "$(rr028_field "$RR028_OUT" state)" = "ENROLLED_PENDING" ] \
    && ok "the CLI-only blind spot still yields ENROLLED_PENDING, not a false SCHEDULED" \
    || bad "CLI-only readback claimed success" "$(rr028_field "$RR028_OUT" state)"
fi

echo ""
echo "RESULT: $PASS passed, $FAIL failed, $SKIP skipped"
RR028_DONE=1
[ "$FAIL" -eq 0 ] || exit 1
exit 0
