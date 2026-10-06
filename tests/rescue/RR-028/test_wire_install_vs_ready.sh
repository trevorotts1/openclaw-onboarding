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
# no_enabled_job <box> [overrides-json] — a MANAGED row carrying NO `enabled`
# key at all: the shape a build whose job JSON omits the bit writes, where the
# engine cannot tell an operator-DISABLED job from an ENABLED one. (matching_job
# always sets enabled:true, so it cannot express this fixture.)
no_enabled_job() {
  _box="$1"; _ov="${2:-}"
  _cmd="sh $_box/.openclaw/skills/65-rescue-receiver/rescue-poll.sh"
  _base="{\"id\":\"1\",\"name\":\"rescue-rr-box-poll\",\"schedule\":{\"kind\":\"cron\",\"expr\":\"*/2 * * * *\"},\"payload\":{\"kind\":\"command\",\"command\":\"$_cmd\"},\"delivery\":{\"mode\":\"none\"}}"
  if [ -n "$_ov" ]; then
    RR028_BASE="$_base" RR028_OV="$_ov" python3 -c '
import json, os
b = json.loads(os.environ["RR028_BASE"]); b.update(json.loads(os.environ["RR028_OV"])); print(json.dumps(b))'
  else
    printf '%s' "$_base"
  fi
}
# job_enabled_raw <box> <id> — the RAW `enabled` value of a stored job, with
# <ABSENT> for a row that carries no such key (a replace would have minted one).
job_enabled_raw() { RR028_JOBS="$1/jobs.json" RR028_JID="$2" python3 -c '
import json, os
d = json.load(open(os.environ["RR028_JOBS"], encoding="utf-8"))
for j in d.get("jobs", []) or []:
    if str(j.get("id")) == os.environ["RR028_JID"]:
        print(j.get("enabled", "<ABSENT>")); break
else:
    print("<NO-SUCH-ID>")'; }
# legacy_job <box> <enabled-fragment> — a job under the pre-RR-028 name the
# legacy cleanup deletes.
legacy_job() {
  python3 -c '
import json, sys
frag = json.loads(sys.argv[1])
j = {"id": "42", "name": "rescue-rangers-poll",
     "schedule": {"kind": "cron", "expr": "*/2 * * * *"},
     "payload": {"kind": "command", "command": "sh /gone/rescue-poll.sh"},
     "delivery": {"mode": "none"}}
j.update(frag)
print(json.dumps(j))' "$2"
}
job_field() { RR028_JOBS="$1/jobs.json" RR028_F="$2" python3 -c '
import json, os
d = json.load(open(os.environ["RR028_JOBS"], encoding="utf-8"))
j = (d["jobs"] or [{}])[0]
o = j
for k in os.environ["RR028_F"].split("."):
    o = (o or {}).get(k) if isinstance(o, dict) else None
print(o if o is not None else "")'; }
# job_by_id <box> <id> -> enabled | disabled | absent (looks the id up, not [0])
job_by_id() { RR028_JOBS="$1/jobs.json" RR028_JID="$2" python3 -c '
import json, os
d = json.load(open(os.environ["RR028_JOBS"], encoding="utf-8"))
for j in d.get("jobs", []) or []:
    if str(j.get("id")) == os.environ["RR028_JID"]:
        print("enabled" if j.get("enabled", True) else "disabled"); break
else:
    print("absent")'; }
# seed_store_only <box> <job-json> — put a row in the state DB and NOT in the
# CLI store: exactly the shape a diverged/alternate candidate file has.
seed_store_only() { RR028_DB="$1/.openclaw/state/openclaw.sqlite" RR028_JOB="$2" python3 - <<'PY'
import json, os, sqlite3
con = sqlite3.connect(os.environ["RR028_DB"])
con.execute("create table if not exists cron_jobs (job_id text primary key, job_json text)")
j = json.loads(os.environ["RR028_JOB"])
con.execute("insert or replace into cron_jobs (job_id, job_json) values (?,?)",
            (str(j.get("id", "")), json.dumps(j)))
con.commit(); con.close()
PY
}
store_rows() { sqlite3 -readonly "$1/.openclaw/state/openclaw.sqlite" 'select count(*) from cron_jobs;' 2>/dev/null || echo "?"; }
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

# The SAME run with the tool's STDERR appended to its stdout, for asserting on a
# reason the tool prints on the failing surface (`>&2`) — which is exactly where
# a roll log keeps its detail. The harness pins stderr to a file, so read that
# block rather than trying to re-merge streams around it. Exit code is preserved.
run_wire_combined() {
  rr028_wire "$BOX" "$@" >/dev/null 2>&1
  WRC=$?
  WOUT="$RR028_OUT
$(cat "$RR028_STDERR" 2>/dev/null)"
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
RR028_EXTRA_ENV="RR028_MOCK_ADD_MODE=silent" run_wire_combined
OUT="$WOUT"
# M-2: the readback decided the readiness state (ENROLLED_PENDING) but the EXIT
# CODE used to fall through to 0, so `update-skills.sh` printed
# "✓ enrollment/cron reconciliation ran" over a box with NO cron at all. The
# script's own contract maps "not proven" to a retryable failure, so this MUST
# be non-zero now.
[ "$WRC" != "0" ] && ok "a silent add (rc 4 add_not_read_back) exits NON-ZERO, so a roll cannot print ✓ over a box with no cron (rc=$WRC)" \
  || bad "wire.sh exited 0 although its own readback FAILED (add_not_read_back)"
[ "$WRC" = "1" ] && ok "the non-zero is exactly 1 (the documented retryable wiring failure)" \
  || bad "unexpected exit code for a failed readback" "rc=$WRC"
printf '%s' "$OUT" | grep -qi 'not proven' \
  && ok "the reason is readable on the FAILING surface (stderr says NOT proven)" \
  || bad "no readable 'not proven' reason"
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
[ "$WRC" = "0" ] && [ "$(wire_state "$WOUT")" = "SCHEDULED" ] \
  && ok "control: the same box with a working add IS SCHEDULED and exits 0 (the guard discriminates on the READBACK)" \
  || bad "control box not scheduled/zero" "rc=$WRC state=$(wire_state "$WOUT")"

# A mutation command that FAILS is a retryable wiring failure (rc=1).
new_box box-rejected
RR028_EXTRA_ENV="RR028_MOCK_ADD_MODE=reject" run_wire
[ "$WRC" = "1" ] && ok "a FAILED cron mutation exits 1 (retryable wiring failure)" \
  || bad "failed mutation did not exit 1"

# A reconciliation that FULLY reads back (including an in-place edit and a
# replace fallback) must still exit 0 — the fix must not make ordinary
# reconciliation look like a failure.
new_box box-readback-ok
rr028_job "$BOX" '{"id":"9","name":"rescue-rr-box-poll","enabled":true,"schedule":{"kind":"cron","expr":"*/30 * * * *"},"payload":{"kind":"command","command":"sh /gone/rescue-poll.sh"},"delivery":{"mode":"none"}}'
run_wire
[ "$WRC" = "0" ] && [ "$(wire_state "$WOUT")" = "SCHEDULED" ] \
  && ok "control: a fully read-back reconciliation (edit-in-place) still exits 0" \
  || bad "a proven reconciliation exited non-zero" "rc=$WRC state=$(wire_state "$WOUT")"

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
[ "$(rr028_stored_command "$BOX/jobs.json")" = "$WANT" ] \
  && ok "a stale COMMAND is reconciled in place to the desired command" \
  || bad "command not reconciled" "$(rr028_stored_command "$BOX/jobs.json")"
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
# 5-L. AD-6 (RR-028 review): the LEGACY cleanup is a REMOVAL too.
#
# `wire.sh` deletes the pre-RR-028 job name (`rescue-rangers-poll`) outside the
# reconcile ladder. That path used to be `cron list --json | grep` + an
# UNCONDITIONAL `cron rm`: it asked for no full-status flag and never looked at
# the row's `enabled` bit, so on a build whose DEFAULT listing includes disabled
# jobs it resolved the id of a job the operator had switched OFF and deleted it
# — the same destruction class as AD-2/AD-7. It now asks the LADDER'S OWN
# question (rrr_cron_removable against the engine's two-view readback): the
# CLI's own listing must show the row with an OBSERVED enabled=true.
# RR028_MOCK_LIST_ALL_DEFAULT=1 models that build.
# ---------------------------------------------------------------------------
echo "--- 5-L. AD-6: the legacy cleanup applies the ladder's removal guards ---"
legacy_default_list_shows() {  # <box> <needle> — prove the DEFAULT listing shows it
  RR028_JOBS="$1/jobs.json" RR028_CALLLOG="" RR028_MOCK_LIST_ALL_DEFAULT=1 \
    "$1/bin/openclaw" cron list --json 2>/dev/null | grep -q "$2"
}

new_box box-legacy-disabled
rr028_job "$BOX" "$(legacy_job "$BOX" '{"enabled":false}')"
[ "$(jobs_len "$BOX")" = "1" ] && [ "$(job_enabled_raw "$BOX" 42)" = "False" ] \
  && ok "AD-6 planted: a DISABLED legacy job (rescue-rangers-poll, id 42) is in the CLI's own store" \
  || bad "legacy plant failed" "$(jobs_len "$BOX") jobs"
legacy_default_list_shows "$BOX" 'rescue-rangers-poll' \
  && ok "AD-6 control: this build's DEFAULT listing SHOWS the disabled legacy row (the old grep resolved its id and rm'd it)" \
  || bad "AD-6 fixture does not discriminate: the default listing hides the legacy row"
RR028_EXTRA_ENV="RR028_MOCK_LIST_ALL_DEFAULT=1" run_wire_combined
[ "$(job_enabled_raw "$BOX" 42)" = "False" ] \
  && ok "AD-6: the operator-DISABLED legacy job was NOT deleted" \
  || bad "the disabled legacy job was destroyed" "id42=$(job_enabled_raw "$BOX" 42)"
rr028_mutating_argv "$BOX" | grep -q 'cron.rm' \
  && bad "a cron rm was still issued for the disabled legacy job" \
  || ok "AD-6: no cron.rm was issued at all"
printf '%s' "$WOUT" | grep -q 'legacy cron rescue-rangers-poll.*NOT removed' \
  && ok "AD-6: the refusal is stated on the failing surface (an operator can see why it stayed)" \
  || bad "the legacy refusal is silent"

new_box box-legacy-unobs
rr028_job "$BOX" "$(legacy_job "$BOX" '{}')"
[ "$(job_enabled_raw "$BOX" 42)" = "<ABSENT>" ] \
  && ok "AD-6 planted: a legacy row whose enabled bit NO view reports" \
  || bad "legacy-unobservable plant failed"
legacy_default_list_shows "$BOX" 'rescue-rangers-poll' \
  && ok "AD-6 control: the default listing shows the enabled-unobservable legacy row too" \
  || bad "AD-6 fixture does not discriminate (unobservable row hidden)"
RR028_EXTRA_ENV="RR028_MOCK_LIST_ALL_DEFAULT=1" run_wire_combined
[ "$(job_enabled_raw "$BOX" 42)" = "<ABSENT>" ] \
  && ok "AD-6/AD-7: a legacy row whose enabled bit is UNOBSERVABLE was NOT deleted either" \
  || bad "an unobservable legacy row was deleted or rewritten" "id42=$(job_enabled_raw "$BOX" 42)"
rr028_mutating_argv "$BOX" | grep -q 'cron.rm' \
  && bad "a cron rm was issued for the unobservable legacy job" \
  || ok "AD-6/AD-7: no cron.rm was issued for it"

new_box box-legacy-enabled
rr028_job "$BOX" "$(legacy_job "$BOX" '{"enabled":true}')"
RR028_EXTRA_ENV="RR028_MOCK_LIST_ALL_DEFAULT=1" run_wire_combined
[ "$(job_enabled_raw "$BOX" 42)" = "<NO-SUCH-ID>" ] \
  && ok "AD-6 control: an ENABLED legacy job IS still removed (the guard discriminates, no double delivery)" \
  || bad "the enabled legacy job survived" "id42=$(job_enabled_raw "$BOX" 42)"
[ "$(jobs_len "$BOX")" = "1" ] \
  && ok "AD-6 control: and the canonical name is registered in its place (exactly one job left)" \
  || bad "the canonical reconcile did not run after the legacy removal" "$(jobs_len "$BOX") jobs"

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

# ---------------------------------------------------------------------------
# 7. FAIL-CLOSED MUTATION: the blind spot must REFUSE to add (RR-028 review M-1)
#
# The coverage gap E's battery missed: RR028_MOCK_NO_ALL=1 *without* a state DB,
# driven through the MUTATION path (--reconcile), not just the read-only --json
# report. Here the CLI cannot show a DISABLED job and no gateway store resolves
# to cover for it, so `cron list` returning nothing CANNOT distinguish "no such
# cron" from "the operator's cron is disabled and hidden". Before the fix the
# ladder took the `add` arm and registered a SECOND, ENABLED poller beside the
# operator's disabled one, then reported SCHEDULED.
# ---------------------------------------------------------------------------
echo "--- 7. blind-spot reconcile REFUSES to add (fail-closed) ---"
if ! command -v sqlite3 >/dev/null 2>&1; then
  skip "blind-spot reconcile case (no sqlite3 on this host)"
else
  new_box box-blindspot
  rr028_job "$BOX" "$(matching_job "$BOX" '{"id":"7","enabled":false}')"
  [ "$(jobs_len "$BOX")" = "1" ] && [ "$(job_field "$BOX" enabled)" = "False" ] \
    && ok "planted: exactly ONE operator-DISABLED poller, and NO state DB to see it" \
    || bad "blind-spot plant failed" "$(jobs_len "$BOX") jobs"

  # (a) the read-only report names the ambiguity honestly
  RR028_EXTRA_ENV="RR028_MOCK_NO_ALL=1" rr028_readiness "$BOX" --json >/dev/null 2>&1
  [ "$(rr028_field "$RR028_OUT" cron.coverage)" = "cli-only" ] \
    && ok "blind spot: coverage is cli-only (no gateway store to prove an absence)" \
    || bad "coverage wrong" "$(rr028_field "$RR028_OUT" cron.coverage)"
  [ "$(rr028_field "$RR028_OUT" cron.visibility)" = "enabled_only" ] \
    && ok "the report states the CLI can only see ENABLED jobs (visibility=enabled_only)" \
    || bad "visibility not reported" "$(rr028_field "$RR028_OUT" cron.visibility)"
  [ "$(rr028_field "$RR028_OUT" reason)" = "cron_state_unverifiable" ] \
    && ok "reason names the real fault: cron_state_unverifiable (not 'absent')" \
    || bad "reason wrong" "$(rr028_field "$RR028_OUT" reason)"

  # (b) THE MUTATION PATH — this is the case that used to create the duplicate
  RR028_EXTRA_ENV="RR028_MOCK_NO_ALL=1" run_wire_combined --idempotent --reconcile-only
  [ "$WRC" = "0" ] \
    && ok "the fail-closed refusal exits 0 (nothing failed; no mutation was attempted — zero is deliberate)" \
    || bad "the refusal must not be reported as a wiring failure" "rc=$WRC"
  [ "$(jobs_len "$BOX")" = "1" ] \
    && ok "NO job was added: still exactly ONE job after --reconcile" \
    || bad "the blind spot ADDED a job" "$(jobs_len "$BOX") jobs"
  [ "$(job_field "$BOX" enabled)" = "False" ] \
    && ok "the operator's job is STILL DISABLED (never re-enabled, never duplicated)" \
    || bad "the operator's disabled job was mutated" "enabled=$(job_field "$BOX" enabled)"
  [ "$(job_field "$BOX" id)" = "7" ] \
    && ok "the surviving job is the OPERATOR's (id 7), not a freshly minted duplicate" \
    || bad "the operator's job was replaced" "id=$(job_field "$BOX" id)"
  rr028_argv_blocks "$BOX" | grep -q 'cron.add' \
    && bad "an add was issued in the blind spot" \
    || ok "no cron.add argv was issued at all (the reconciler refused before mutating)"
  [ "$(wire_state "$WOUT")" = "ENROLLED_PENDING" ] \
    && [ "$(wire_reason "$WOUT")" = "cron_state_unverifiable" ] \
    && ok "the installer reports the honest non-SCHEDULED state (never a false SCHEDULED)" \
    || bad "wire reported the wrong verdict" "$(wire_state "$WOUT")/$(wire_reason "$WOUT")"

  # (c) CONTROL for (b): the SAME box WITH a readable gateway store still
  #     detects the disable and refuses for the RIGHT reason — proving the
  #     engine can see the disabled job whenever it is allowed to.
  new_box box-blindspot-db
  rr028_job "$BOX" "$(matching_job "$BOX" '{"id":"7","enabled":false}')"
  rr028_make_db "$BOX" || bad "could not build the control state DB"
  RR028_EXTRA_ENV="RR028_MOCK_NO_ALL=1" run_wire --idempotent --reconcile-only
  WRC_DB="$WRC"; WOUT_DB="$WOUT"
  [ "$(jobs_len "$BOX")" = "1" ] && [ "$(job_field "$BOX" enabled)" = "False" ] \
    && ok "control: with the DB readable the disabled job is SEEN via the store and still left alone (1 job, still disabled)" \
    || bad "control mutated the operator's job" "$(jobs_len "$BOX") jobs enabled=$(job_field "$BOX" enabled)"
  [ "$(wire_reason "$WOUT_DB")" = "cron_disabled_by_owner" ] \
    && ok "control: the reason is the specific cron_disabled_by_owner (the observer really can see it)" \
    || bad "control reason wrong" "$(wire_reason "$WOUT_DB")"
  [ "$WRC_DB" = "0" ] \
    && ok "control: an operator-disabled job does not turn the roll red (exit 0)" \
    || bad "control exit code" "rc=$WRC_DB"

  # -------------------------------------------------------------------------
  # (d) Z-1 (RE-REVIEW): a resolved gateway store is NOT proof that it reflects
  #     the gateway. Here a schema-valid store resolves and holds ZERO rows,
  #     while the operator's DISABLED job exists in the CLI's store and the CLI
  #     cannot show disabled jobs. Before the fix a resolved store upgraded
  #     visibility to `full` on its own, so the ladder ADDED an ENABLED
  #     duplicate (id 8) and the dedupe pass then DELETED the operator's job
  #     (id 7). Nothing here may be added or removed, and the verdict must be
  #     the honest non-SCHEDULED one.
  # -------------------------------------------------------------------------
  new_box box-z1-empty-store
  rr028_job "$BOX" "$(matching_job "$BOX" '{"id":"7","enabled":false}')"
  Z1_DB="$BOX/.openclaw/state/openclaw.sqlite"
  rr028_make_state_db "$BOX" || bad "could not build the Z-1 empty-store fixture"
  [ -s "$Z1_DB" ] && [ "$(store_rows "$BOX")" = "0" ] \
    && ok "planted: the store resolves (>=1 table) and holds ZERO cron rows — it does not contain the operator's job" \
    || bad "Z-1 store fixture is not the empty/diverged shape" "rows=$(store_rows "$BOX")"
  [ "$(jobs_len "$BOX")" = "1" ] && [ "$(job_by_id "$BOX" 7)" = "disabled" ] \
    && ok "planted: the operator's DISABLED poller (id 7) is the only job the gateway's CLI store carries" \
    || bad "Z-1 plant failed" "$(jobs_len "$BOX") jobs id7=$(job_by_id "$BOX" 7)"
  # NO_ALL=1: this CLI cannot show disabled jobs. RR028_DB_FILE makes the mock
  # keep the sqlite store in step with any mutation, exactly as a live gateway
  # would, so a mutation here would be observable in BOTH views.
  RR028_DB_FILE="$Z1_DB" RR028_EXTRA_ENV="RR028_MOCK_NO_ALL=1" run_wire_combined --idempotent --reconcile-only
  [ "$(jobs_len "$BOX")" = "1" ] \
    && ok "Z-1: NOTHING was added (still exactly ONE job after --reconcile)" \
    || bad "the diverged store licensed an ADD" "$(jobs_len "$BOX") jobs"
  [ "$(job_by_id "$BOX" 7)" = "disabled" ] && [ "$(job_by_id "$BOX" 8)" = "absent" ] \
    && ok "Z-1: the OPERATOR's job survived (id 7, still DISABLED) and no duplicate id 8 was minted" \
    || bad "the operator's job was destroyed or duplicated" "id7=$(job_by_id "$BOX" 7) id8=$(job_by_id "$BOX" 8)"
  rr028_argv_blocks "$BOX" | grep -q 'cron.add' \
    && bad "an add was issued against the diverged store" \
    || ok "Z-1: NO cron.add argv was issued"
  rr028_argv_blocks "$BOX" | grep -q 'cron.rm' \
    && bad "a cron rm was issued against the diverged store (the destructive step ran)" \
    || ok "Z-1: NO cron.rm argv was issued"
  [ "$(wire_state "$WOUT")" = "ENROLLED_PENDING" ] \
    && [ "$(wire_reason "$WOUT")" = "cron_state_unverifiable" ] \
    && ok "Z-1: the installer reports the honest non-SCHEDULED state (never a false SCHEDULED)" \
    || bad "wire reported the wrong verdict" "$(wire_state "$WOUT")/$(wire_reason "$WOUT")"
  [ "$WRC" = "0" ] \
    && ok "Z-1: the refusal is a deliberate non-failure (nothing was attempted, nothing is claimed)" \
    || bad "the refusal must not be reported as a wiring failure" "rc=$WRC"
  RR028_DB_FILE="$Z1_DB" RR028_EXTRA_ENV="RR028_MOCK_NO_ALL=1" rr028_readiness "$BOX" --json >/dev/null 2>&1
  [ "$(rr028_field "$RR028_OUT" cron.coverage)" = "cli+db" ] \
    && [ "$(rr028_field "$RR028_OUT" cron.visibility)" = "enabled_only" ] \
    && ok "Z-1 root cause pinned: coverage=cli+db but a resolved store did NOT upgrade visibility (enabled_only)" \
    || bad "a resolved store licensed visibility=full again" \
           "coverage=$(rr028_field "$RR028_OUT" cron.coverage) visibility=$(rr028_field "$RR028_OUT" cron.visibility)"

  # -------------------------------------------------------------------------
  # (e) Z-1b: the OTHER destructive path — a duplicate whose stray is
  #     OPERATOR-DISABLED. No divergence is needed: the dedupe ladder used to
  #     keep the matching job and `cron rm` the disabled one, so a readiness
  #     pass deleted a job the operator had switched off. Readiness may never
  #     remove a row it observed DISABLED.
  # -------------------------------------------------------------------------
  new_box box-dupe-disabled
  rr028_job "$BOX" "$(matching_job "$BOX" '{"id":"7","enabled":false}')"
  rr028_job "$BOX" "$(matching_job "$BOX" '{"id":"8","enabled":true}')"
  [ "$(jobs_len "$BOX")" = "2" ] && [ "$(job_by_id "$BOX" 7)" = "disabled" ] \
    && ok "planted: the operator's DISABLED job (7) beside a matching ENABLED job (8)" \
    || bad "duplicate-with-disabled plant failed" "$(jobs_len "$BOX") jobs"
  run_wire --idempotent --reconcile-only
  [ "$(jobs_len "$BOX")" = "2" ] && [ "$(job_by_id "$BOX" 7)" = "disabled" ] \
    && ok "Z-1b: the operator's DISABLED job was NOT deleted by the dedupe pass (still 2 jobs, id 7 still disabled)" \
    || bad "the operator's disabled job was removed" "$(jobs_len "$BOX") jobs id7=$(job_by_id "$BOX" 7)"
  rr028_argv_blocks "$BOX" | grep -q 'cron.rm' \
    && bad "a cron rm was issued for the operator's disabled job" \
    || ok "Z-1b: NO cron.rm argv was issued"
  [ "$(wire_state "$WOUT")" = "ENROLLED_PENDING" ] \
    && [ "$(wire_reason "$WOUT")" = "cron_duplicate" ] \
    && ok "Z-1b: the honest verdict for an unresolvable duplicate (ENROLLED_PENDING/cron_duplicate)" \
    || bad "verdict wrong" "$(wire_state "$WOUT")/$(wire_reason "$WOUT")"
  [ "$WRC" != "0" ] \
    && ok "Z-1b: a duplicate readiness could not clear is not reported as success (rc=$WRC)" \
    || bad "an unprotected duplicate was reported as success" "rc=$WRC"

  # -------------------------------------------------------------------------
  # (f) Z-1c: only the STORE shows the job and the CLI's own listing cannot be
  #     read. The store may VETO, never ESTABLISH: a store-only match used to
  #     produce SCHEDULED and rc 0 from a file nobody had corroborated.
  # -------------------------------------------------------------------------
  new_box box-store-only
  rr028_job "$BOX" "$(matching_job "$BOX")"
  rr028_make_db "$BOX" || bad "could not build the store-only fixture"
  [ "$(jobs_len "$BOX")" = "1" ] && [ "$(store_rows "$BOX")" = "1" ] \
    && ok "planted: the store carries the matching job while the CLI listing is made unreadable" \
    || bad "store-only plant failed" "jobs=$(jobs_len "$BOX") rows=$(store_rows "$BOX")"
  RR028_EXTRA_ENV="RR028_MOCK_LIST_MODE=unreadable" run_wire_combined --idempotent --reconcile-only
  [ "$(wire_state "$WOUT")" = "ENROLLED_PENDING" ] \
    && [ "$(wire_reason "$WOUT")" = "cron_store_unconfirmed" ] \
    && ok "Z-1c: a store-only match is NOT readiness (ENROLLED_PENDING/cron_store_unconfirmed)" \
    || bad "the store alone established readiness" "$(wire_state "$WOUT")/$(wire_reason "$WOUT")"
  [ "$WRC" != "0" ] \
    && ok "Z-1c: an uncorroborated store does not report wiring success (rc=$WRC)" \
    || bad "store-only match exited 0" "rc=$WRC"
  [ "$(jobs_len "$BOX")" = "1" ] && [ "$(store_rows "$BOX")" = "1" ] \
    && ok "Z-1c: nothing was mutated (1 CLI job, 1 store row)" \
    || bad "the store-only case mutated something" "jobs=$(jobs_len "$BOX") rows=$(store_rows "$BOX")"
  rr028_argv_blocks "$BOX" | grep -q -e 'cron.add' -e 'cron.rm' -e 'cron.edit' \
    && bad "an uncorroborated store licensed a mutation" \
    || ok "Z-1c: no add/rm/edit argv was issued"

  # -------------------------------------------------------------------------
  # (g) Z-1d: the store and the CLI's own listing CONTRADICT each other — the
  #     store carries a matching ENABLED row the CLI's listing does not show,
  #     so the store is an alternate/stale candidate. Two views that do not
  #     describe the same gateway prove nothing: no SCHEDULED, no mutation.
  # -------------------------------------------------------------------------
  new_box box-store-stale
  seed_store_only "$BOX" "$(matching_job "$BOX")"
  [ "$(jobs_len "$BOX")" = "0" ] && [ "$(store_rows "$BOX")" = "1" ] \
    && ok "planted: a matching ENABLED row exists ONLY in the store (the CLI's own listing is empty)" \
    || bad "stale-store plant failed" "jobs=$(jobs_len "$BOX") rows=$(store_rows "$BOX")"
  run_wire_combined --idempotent --reconcile-only
  [ "$(wire_state "$WOUT")" = "ENROLLED_PENDING" ] \
    && [ "$(wire_reason "$WOUT")" = "cron_source_disagreement" ] \
    && ok "Z-1d: contradicting views claim nothing (ENROLLED_PENDING/cron_source_disagreement)" \
    || bad "a contradicting store still produced a verdict" "$(wire_state "$WOUT")/$(wire_reason "$WOUT")"
  [ "$WRC" != "0" ] \
    && ok "Z-1d: a self-contradicting readback does not report wiring success (rc=$WRC)" \
    || bad "a contradicting store exited 0" "rc=$WRC"
  [ "$(jobs_len "$BOX")" = "0" ] && [ "$(store_rows "$BOX")" = "1" ] \
    && ok "Z-1d: nothing was mutated on either surface (0 CLI jobs, 1 store row)" \
    || bad "the diverged store licensed a mutation" "jobs=$(jobs_len "$BOX") rows=$(store_rows "$BOX")"
  rr028_argv_blocks "$BOX" | grep -q -e 'cron.add' -e 'cron.rm' -e 'cron.edit' \
    && bad "a diverged store licensed a mutation" \
    || ok "Z-1d: no add/rm/edit argv was issued"

  # -------------------------------------------------------------------------
  # (h) RR-028 REVIEW AD-1 / AD-2 / AD-7: UNOBSERVABLE IS NOT ABSENT.
  #
  # When a row for the managed name exists but NO view reports its `enabled`
  # bit, the engine cannot tell an operator-DISABLED job from an ENABLED one.
  # Before this fix it ran `cron edit` → `cron rm` → `cron add` and reported
  # SCHEDULED with rc 0 (reviewer scenario S): the operator's row was DESTROYED
  # and replaced by a freshly minted ENABLED one. The same shape reached through
  # the gateway STORE alone (a readable CLI listing that omits the row) issued
  # `cron edit <store-only id>` and reported `store=corroborated` for a store the
  # CLI's own listing never corroborated (AD-1, scenarios G/G2/Q/Q2).
  # Nothing here may be edited, replaced or removed, and a store row the CLI's
  # listing does not show is never called corroborated.
  # -------------------------------------------------------------------------
  echo "--- (h) AD-1/AD-2/AD-7: a row whose enabled bit no view reports is never touched ---"

  # (h1) AD-2 scenario S: the row is in BOTH views, carrying NO enabled key.
  new_box box-unobs-both
  rr028_job "$BOX" "$(no_enabled_job "$BOX" '{"id":"7","schedule":{"kind":"cron","expr":"0 3 * * *"}}')"
  S2_DB="$BOX/.openclaw/state/openclaw.sqlite"
  rr028_make_db "$BOX" || bad "could not build the unobservable-in-both-views fixture"
  [ "$(jobs_len "$BOX")" = "1" ] && [ "$(store_rows "$BOX")" = "1" ] && [ "$(job_enabled_raw "$BOX" 7)" = "<ABSENT>" ] \
    && ok "AD-2 planted: ONE row for the managed name in BOTH views, carrying NO enabled key" \
    || bad "AD-2 plant failed" "jobs=$(jobs_len "$BOX") rows=$(store_rows "$BOX") enabled=$(job_enabled_raw "$BOX" 7)"
  RR028_DB_FILE="$S2_DB" rr028_readiness "$BOX" --json >/dev/null 2>&1
  [ "$(rr028_field "$RR028_OUT" cron.unobservable)" = "enabled,enabled" ] \
    && ok "AD-2: the report says BOTH views left the enabled bit unobservable (enabled,enabled)" \
    || bad "unobservable set wrong" "$(rr028_field "$RR028_OUT" cron.unobservable)"
  [ "$(rr028_field "$RR028_OUT" reason)" = "cron_enabled_unobservable" ] \
    && ok "AD-2: the named honest reason is cron_enabled_unobservable" \
    || bad "reason wrong" "$(rr028_field "$RR028_OUT" reason)"
  RR028_DB_FILE="$S2_DB" run_wire_combined
  [ "$(jobs_len "$BOX")" = "1" ] && [ "$(job_enabled_raw "$BOX" 7)" = "<ABSENT>" ] \
    && ok "AD-2: the operator's row SURVIVED untouched (still one job, id 7, still no enabled key — not replaced by an ENABLED one)" \
    || bad "the operator's job was destroyed or replaced" "jobs=$(jobs_len "$BOX") id7=$(job_enabled_raw "$BOX" 7)"
  [ "$(job_field "$BOX" schedule.expr)" = "0 3 * * *" ] \
    && ok "AD-2: its schedule was NOT rewritten either (the edit half of scenario S is refused)" \
    || bad "the unobservable row was edited in place" "$(job_field "$BOX" schedule.expr)"
  [ -z "$(rr028_mutating_argv "$BOX")" ] \
    && ok "AD-2: NO mutating argv at all — not edit, not rm, not add (scenario S is closed)" \
    || bad "a mutation was issued for an unobservable row" "$(rr028_mutating_argv "$BOX" | tr '\n' ';')"
  [ "$(wire_state "$WOUT")" = "ENROLLED_PENDING" ] \
    && ok "AD-2: the verdict is ENROLLED_PENDING, never a false SCHEDULED" \
    || bad "verdict wrong" "$(wire_state "$WOUT")/$(wire_reason "$WOUT")"
  printf '%s' "$WOUT" | grep -q 'NOT touched — enabled_unobservable' \
    && ok "AD-2: the failure surface names the fault and says the row was NOT touched (not the add-refusal wording)" \
    || bad "the enabled-unobservable refusal is silent or mis-explained"
  [ "$WRC" = "0" ] \
    && ok "AD-2: rc 0 — a deliberate no-mutation refusal is honestly not a wiring failure (rc 4/7 would be)" \
    || bad "the deliberate refusal was reported as a wiring failure" "rc=$WRC"

  # (h2) CONTROL: the SAME box with an OBSERVABLE enabled=true IS repaired in
  #      place — so (h1) is a refusal about the unobserved bit, not a dead
  #      fixture. This is the observer's proof it could have seen the opposite.
  new_box box-unobs-control
  rr028_job "$BOX" "$(matching_job "$BOX" '{"id":"7","schedule":{"kind":"cron","expr":"0 3 * * *"}}')"
  C2_DB="$BOX/.openclaw/state/openclaw.sqlite"
  rr028_make_db "$BOX" || bad "could not build the AD-2 control fixture"
  RR028_DB_FILE="$C2_DB" run_wire_combined
  [ "$(job_field "$BOX" id)" = "7" ] && [ "$(job_field "$BOX" schedule.expr)" = "*/2 * * * *" ] \
    && ok "AD-2 control: the same row WITH an observable enabled=true is reconciled IN PLACE (id 7 survives)" \
    || bad "control did not reconcile" "id=$(job_field "$BOX" id) expr=$(job_field "$BOX" schedule.expr)"
  [ "$(wire_state "$WOUT")" = "SCHEDULED" ] \
    && ok "AD-2 control: and it reads SCHEDULED — the readback really can see an enabled bit" \
    || bad "control verdict" "$(wire_state "$WOUT")/$(wire_reason "$WOUT")"

  # (h3) AD-2 on the REPLACE rung: a CLI whose `cron edit` advertises no
  #      editable field falls through to replace (rm + add). The removal guard
  #      must refuse there too — this is the path reviewer mutation mutK
  #      disables, so this case is what catches it.
  new_box box-unobs-noedit
  rr028_job "$BOX" "$(no_enabled_job "$BOX" '{"id":"7","schedule":{"kind":"cron","expr":"0 3 * * *"}}')"
  R2_DB="$BOX/.openclaw/state/openclaw.sqlite"
  rr028_make_db "$BOX" || bad "could not build the AD-2 replace-path fixture"
  RR028_DB_FILE="$R2_DB" RR028_EXTRA_ENV="RR028_MOCK_NO_EDIT_FLAGS=1" run_wire_combined
  [ "$(jobs_len "$BOX")" = "1" ] && [ "$(job_enabled_raw "$BOX" 7)" = "<ABSENT>" ] \
    && ok "AD-2/replace: a CLI that cannot edit does NOT fall through to rm+add on the unobservable row" \
    || bad "the replace rung destroyed the unobservable row" "jobs=$(jobs_len "$BOX") id7=$(job_enabled_raw "$BOX" 7)"
  [ -z "$(rr028_mutating_argv "$BOX")" ] \
    && ok "AD-3(mutK): the replace-path removal guard holds — no rm and no add was issued" \
    || bad "the replace rung mutated an unobservable row" "$(rr028_mutating_argv "$BOX" | tr '\n' ';')"

  # (h4) AD-1 scenario G: the CLI's listing is readable and EMPTY of the
  #      managed name; ONLY the store carries a row for it, with no enabled bit.
  new_box box-store-only-unobs
  seed_store_only "$BOX" "$(no_enabled_job "$BOX" '{"id":"9"}')"
  [ "$(jobs_len "$BOX")" = "0" ] && [ "$(store_rows "$BOX")" = "1" ] \
    && ok "AD-1 planted: a row for the managed name exists ONLY in the store, with NO enabled key" \
    || bad "AD-1 plant failed" "jobs=$(jobs_len "$BOX") rows=$(store_rows "$BOX")"
  rr028_readiness "$BOX" --json >/dev/null 2>&1
  [ "$(rr028_field "$RR028_OUT" cron.store)" = "unconfirmed" ] \
    && ok "AD-1: a store row the CLI's own listing never showed is reported UNCONFIRMED" \
    || bad "the store was not reported unconfirmed" "$(rr028_field "$RR028_OUT" cron.store)"
  [ "$(rr028_field "$RR028_OUT" cron.store)" != "corroborated" ] \
    && ok "AD-1: it is NEVER reported as corroborated (the CLI never corroborated it)" \
    || bad "a store the CLI never confirmed was called corroborated"
  [ -z "$(rr028_field "$RR028_OUT" cron.disagreement)" ] \
    && ok "AD-1: a merely-omitted row is a coverage gap, NOT a disagreement" \
    || bad "an omitted row was reported as a disagreement" "$(rr028_field "$RR028_OUT" cron.disagreement)"
  printf '%s' "$(rr028_field "$RR028_OUT" cron.store_note)" | grep -q 'store_row_omitted_by_cli(id=9)' \
    && ok "AD-1: the report names WHY the store was not corroborated (store_row_omitted_by_cli(id=9))" \
    || bad "the uncorroborated row is not named" "$(rr028_field "$RR028_OUT" cron.store_note)"
  run_wire_combined
  [ "$(store_rows "$BOX")" = "1" ] && [ "$(jobs_len "$BOX")" = "0" ] \
    && ok "AD-1: the store's row is intact and NOTHING was created from it" \
    || bad "the store-only row licensed something" "jobs=$(jobs_len "$BOX") rows=$(store_rows "$BOX")"
  [ -z "$(rr028_mutating_argv "$BOX")" ] \
    && ok "AD-1: NO cron.edit / cron.rm / cron.add was issued from the store-only row (scenario G is closed)" \
    || bad "the store licensed a mutation" "$(rr028_mutating_argv "$BOX" | tr '\n' ';')"

  # (h5) AD-1 scenario G2: same, but the store-only row's config also MISMATCHES
  #      the desired one (so the old ladder took the mismatch/edit arm).
  new_box box-store-only-unobs-mis
  seed_store_only "$BOX" "$(no_enabled_job "$BOX" '{"id":"11","schedule":{"kind":"cron","expr":"0 5 * * *"}}')"
  run_wire_combined
  [ "$(store_rows "$BOX")" = "1" ] && [ "$(jobs_len "$BOX")" = "0" ] \
    && ok "AD-1/G2: a MISMATCHING store-only row did not license an in-place edit either" \
    || bad "the mismatching store-only row was mutated into existence" "jobs=$(jobs_len "$BOX") rows=$(store_rows "$BOX")"
  [ -z "$(rr028_mutating_argv "$BOX")" ] \
    && ok "AD-1/G2: no edit/rm/add argv was issued" \
    || bad "the store licensed a mutation" "$(rr028_mutating_argv "$BOX" | tr '\n' ';')"

  # (h6) AD-1 scenario Q: a CLI that cannot show DISABLED jobs, whose own store
  #      holds the managed job DISABLED, plus a store-only row with no enabled
  #      bit. The store must not license an edit of a row the CLI hides.
  new_box box-store-only-noall
  rr028_job "$BOX" "$(matching_job "$BOX" '{"id":"7","enabled":false}')"
  seed_store_only "$BOX" "$(no_enabled_job "$BOX" '{"id":"7"}')"
  RR028_EXTRA_ENV="RR028_MOCK_NO_ALL=1" run_wire_combined
  [ "$(job_by_id "$BOX" 7)" = "disabled" ] \
    && ok "AD-1/Q: the operator's DISABLED job is still there and still disabled" \
    || bad "the disabled job was touched" "id7=$(job_by_id "$BOX" 7)"
  [ -z "$(rr028_mutating_argv "$BOX")" ] \
    && ok "AD-1/Q: no edit/rm/add argv was issued (the store licensed nothing)" \
    || bad "the store licensed a mutation" "$(rr028_mutating_argv "$BOX" | tr '\n' ';')"

  # (h7) AD-1 scenario Q2: the same with `"disabled": "true"` — a STRING, which
  #      is not a boolean, so the enabled bit is equally unobservable.
  new_box box-store-only-stren
  rr028_job "$BOX" "$(matching_job "$BOX" '{"id":"7","enabled":false}')"
  seed_store_only "$BOX" "$(no_enabled_job "$BOX" '{"id":"7","disabled":"true"}')"
  RR028_EXTRA_ENV="RR028_MOCK_NO_ALL=1" run_wire_combined
  [ "$(job_by_id "$BOX" 7)" = "disabled" ] \
    && ok "AD-1/Q2: a string-valued 'disabled' is treated as UNOBSERVABLE — the job is untouched" \
    || bad "the string-disabled case mutated the operator's job" "id7=$(job_by_id "$BOX" 7)"
  [ -z "$(rr028_mutating_argv "$BOX")" ] \
    && ok "AD-1/Q2: no edit/rm/add argv was issued" \
    || bad "the store licensed a mutation" "$(rr028_mutating_argv "$BOX" | tr '\n' ';')"

  # (h8) AD-1 CONTROL: the same store-only shape with an OBSERVABLE enabled=true
  #      IS contradicted and refused (store_diverged) — so the observer can see
  #      a store-only row, and (h4)-(h7) are refusals, not a dead fixture.
  new_box box-store-only-control
  seed_store_only "$BOX" "$(matching_job "$BOX" '{"id":"21"}')"
  run_wire_combined
  [ "$(wire_state "$WOUT")" = "ENROLLED_PENDING" ] && [ "$(wire_reason "$WOUT")" = "cron_source_disagreement" ] \
    && ok "AD-1 control: a store-only ENABLED row is detected as a contradiction (cron_source_disagreement)" \
    || bad "the store-only control did not diverge" "$(wire_state "$WOUT")/$(wire_reason "$WOUT")"
  [ -z "$(rr028_mutating_argv "$BOX")" ] \
    && ok "AD-1 control: and nothing was mutated" \
    || bad "the store-only control mutated something" "$(rr028_mutating_argv "$BOX" | tr '\n' ';')"

  # (h9) AD-3 (reviewer mutF2 plant): the dedupe arm must not REMOVE a row the
  #      CLI's own listing does not show. The CLI holds the matching job (5); the
  #      store holds job 5 AND a stray (6) the CLI never listed, whose enabled
  #      bit is unobservable. The stray is exactly the row `rrr_cron_removable`
  #      exists to protect, and the dedupe pass used to rm it.
  new_box box-store-only-dedupe
  rr028_job "$BOX" "$(matching_job "$BOX" '{"id":"5"}')"
  rr028_make_db "$BOX" || bad "could not build the store-only dedupe fixture"
  seed_store_only "$BOX" "$(no_enabled_job "$BOX" '{"id":"6"}')"
  [ "$(jobs_len "$BOX")" = "1" ] && [ "$(store_rows "$BOX")" = "2" ] \
    && ok "AD-3 planted: the CLI lists id 5; the store holds id 5 AND a store-only stray id 6 (no enabled key)" \
    || bad "store-only dedupe plant failed" "jobs=$(jobs_len "$BOX") rows=$(store_rows "$BOX")"
  run_wire_combined
  rr028_mutating_argv "$BOX" | grep -q 'cron.rm' \
    && bad "the dedupe pass REMOVED a row the CLI's own listing never showed" \
    || ok "AD-3(mutF2): the dedupe pass issued NO cron.rm for the uncorroborated stray"
  [ "$(store_rows "$BOX")" = "2" ] \
    && ok "AD-3(mutF2): the store-only stray SURVIVED (the store may veto, never license a removal)" \
    || bad "the store-only stray was deleted" "rows=$(store_rows "$BOX")"

  # (h10) AD-7: a stray the CLI DOES list, but whose enabled bit NO view
  #       reports. `cron list` cannot tell an operator-disabled job from an
  #       enabled one here, so the dedupe pass must not rm it either.
  new_box box-unobs-dedupe
  rr028_job "$BOX" "$(matching_job "$BOX" '{"id":"5"}')"
  rr028_job "$BOX" "$(no_enabled_job "$BOX" '{"id":"6"}')"
  D2_DB="$BOX/.openclaw/state/openclaw.sqlite"
  rr028_make_db "$BOX" || bad "could not build the unobservable dedupe fixture"
  [ "$(jobs_len "$BOX")" = "2" ] && [ "$(job_enabled_raw "$BOX" 6)" = "<ABSENT>" ] \
    && ok "AD-7 planted: two managed rows, the stray (id 6) with NO enabled key" \
    || bad "AD-7 plant failed" "jobs=$(jobs_len "$BOX") id6=$(job_enabled_raw "$BOX" 6)"
  RR028_DB_FILE="$D2_DB" run_wire_combined
  rr028_mutating_argv "$BOX" | grep -q 'cron.rm' \
    && bad "cron rm fired on a row whose enabled bit no view reports" \
    || ok "AD-7: NO cron.rm for a CLI-visible row whose enabled bit is unobservable"
  [ "$(job_enabled_raw "$BOX" 6)" = "<ABSENT>" ] \
    && ok "AD-7: the unobservable stray survived (deleting it could destroy an operator-disabled job)" \
    || bad "the unobservable stray was removed or rewritten" "id6=$(job_enabled_raw "$BOX" 6)"

  # (h11) AD-4: the documented residual, stated ACCURATELY. A CLI that
  #       ADVERTISES --all and then hides a disabled job anyway is
  #       indistinguishable in-band — but a resolved store that carries the
  #       hidden row CONTRADICTS it, and that IS detected.
  new_box box-lying-cli-store
  rr028_job "$BOX" "$(matching_job "$BOX" '{"id":"7","enabled":false}')"
  L_DB="$BOX/.openclaw/state/openclaw.sqlite"
  rr028_make_db "$BOX" || bad "could not build the lying-CLI fixture"
  RR028_DB_FILE="$L_DB" RR028_EXTRA_ENV="RR028_MOCK_NO_ALL=1 RR028_MOCK_LIE_ALL=1" rr028_readiness "$BOX" --json >/dev/null 2>&1
  [ "$(rr028_field "$RR028_OUT" cron.visibility)" = "full" ] \
    && ok "AD-4 control: the lying build DOES advertise --all, so the engine asked for and trusted its listing (visibility=full)" \
    || bad "the lying-CLI fixture does not model the residual" "$(rr028_field "$RR028_OUT" cron.visibility)"
  [ "$(rr028_field "$RR028_OUT" cron.store)" = "diverged" ] \
    && printf '%s' "$(rr028_field "$RR028_OUT" cron.disagreement)" | grep -q 'cli_all_omits_disabled_row(id=7)' \
    && ok "AD-4: the store CONTRADICTS the lying CLI and the engine detects it (cli_all_omits_disabled_row(id=7))" \
    || bad "the lying CLI's hidden row was not detected" "store=$(rr028_field "$RR028_OUT" cron.store) disagree=$(rr028_field "$RR028_OUT" cron.disagreement)"
  RR028_DB_FILE="$L_DB" RR028_EXTRA_ENV="RR028_MOCK_NO_ALL=1 RR028_MOCK_LIE_ALL=1" run_wire_combined
  [ "$(job_by_id "$BOX" 7)" = "disabled" ] \
    && ok "AD-4: nothing mutated the operator's hidden disabled job" \
    || bad "the lying-CLI path mutated the operator's job" "id7=$(job_by_id "$BOX" 7)"
  [ -z "$(rr028_mutating_argv "$BOX")" ] \
    && ok "AD-4: no add/rm/edit argv was issued — the residual is 'a false SCHEDULED is impossible here', exactly as the header now says" \
    || bad "the lying CLI still licensed a mutation" "$(rr028_mutating_argv "$BOX" | tr '\n' ';')"

  # (h12) AD-5: the MIRROR cost, pinned. A STALE/EMPTY resolved store reds a box
  #       that is genuinely scheduled: the CLI shows the one correct ENABLED job
  #       and the store carries no row for it.
  new_box box-store-lag
  rr028_job "$BOX" "$(matching_job "$BOX" '{"id":"4"}')"
  rr028_make_state_db "$BOX" || bad "could not build the store-lag fixture"
  [ "$(store_rows "$BOX")" = "0" ] \
    && ok "AD-5 planted: the CLI shows the one correct ENABLED job while the store resolves and holds ZERO rows" \
    || bad "store-lag plant failed" "rows=$(store_rows "$BOX")"
  run_wire_combined
  [ "$(wire_state "$WOUT")" = "ENROLLED_PENDING" ] && [ "$(wire_reason "$WOUT")" = "cron_source_disagreement" ] \
    && ok "AD-5: a lagging store fails closed (ENROLLED_PENDING/cron_source_disagreement), it is not silently ignored" \
    || bad "the lagging store produced the wrong verdict" "$(wire_state "$WOUT")/$(wire_reason "$WOUT")"
  printf '%s' "$WOUT" | grep -q 'store_missing_row(id=4)' \
    && ok "AD-5: the detail NAMES the missing store row and the remedy, so a red roll is diagnosable" \
    || bad "the store-lag detail does not name the missing row"
  [ "$(jobs_len "$BOX")" = "1" ] && [ "$(job_by_id "$BOX" 4)" = "enabled" ] \
    && ok "AD-5: and the healthy job is left alone (fail-closed, not destructive)" \
    || bad "the store-lag case mutated the healthy job" "jobs=$(jobs_len "$BOX")"
fi

echo ""
echo "RESULT: $PASS passed, $FAIL failed, $SKIP skipped"
RR028_DONE=1
[ "$FAIL" -eq 0 ] || exit 1
exit 0
