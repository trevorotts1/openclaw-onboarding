#!/usr/bin/env bash
# test-record-dept-decision-no-jq.sh — CI guard for the department-decision writer.
#
# WHAT IT TESTS:
#   scripts/record-dept-decision.sh must record a department decision on a box
#   that has NO jq, through the locked workforce_state writer, and must not lose
#   a decision when many are recorded at the same time.
#
#     1. `--dept marketing --decision yes --by t --session s` exits 0 and the
#        state file holds the five provenance fields.
#     2. a floor `no` without `--confirm-loss` exits 2 and leaves the file
#        byte-identical (nothing written).
#     3. the same `no` WITH `--confirm-loss` exits 0 and stamps
#        lossWarning + lossWarningAck: true.
#     4. twenty decisions for twenty different departments, launched at the same
#        time, are all present afterwards (the write is locked; none is lost).
#
# PATH is restricted to the folders of bash and python3 and is proven to hold no
# jq, so nothing here can silently fall back to jq.
#
# Exit 0 = every check passed; non-zero = at least one check failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RECORDER="$SCRIPT_DIR/record-dept-decision.sh"
LISTER="$SCRIPT_DIR/list-canonical-departments.py"

PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

# Temp on the drive when TMPDIR points there (the room exports it): the
# template path forces mktemp off the system temp folder, so state files and
# out files never land in /tmp or /var/folders.
WORK="$(mktemp -d "${TMPDIR:-/tmp}/recdept-nojq.XXXXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

# Empty HOME: the writer must resolve its state from --state alone.
HOME_DIR="$WORK/home"
mkdir -p "$HOME_DIR"

# PATH = /tmp/workdir.<pid>: exact symlinks for the writer's tools, nothing
# else. The spec needs PATH to hold only bash and python3 folders with no jq;
# /tmp/workdir.<pid> holds symlinks to /bin/bash, /usr/bin/python3 and the
# utilities the writer calls (dirname, tr, env, mktemp, date, mkdir),
# leaving out /usr/bin/jq. jq absence is proven by the SKIP gate below.
TOOLDIR="$WORK/tools"
mkdir -p "$TOOLDIR"
for _t in bash python3 dirname tr env mktemp date mkdir; do
  _src=""
  for _cand in /bin/$_t /usr/bin/$_t; do
    if [ -x "$_cand" ] && [ ! -d "$_cand" ]; then _src="$_cand"; break; fi
  done
  if [ -z "$_src" ] && [ "$_t" = "python3" ]; then
    _src="$(command -v python3)" || true
  fi
  if [ -z "$_src" ]; then echo "  FAIL: $_t not found — cannot prove a no-jq box here"; exit 1; fi
  ln -sf "$_src" "$TOOLDIR/$_t"
done
NOJQ_PATH="$TOOLDIR"

echo "== setup =="
echo "  restricted PATH: $NOJQ_PATH"
if PATH="$NOJQ_PATH" command -v jq >/dev/null 2>&1; then
  echo "SKIP: jq resolves on the restricted PATH — this box cannot prove a no-jq box here"
  exit 0
fi
echo "  PASS: jq is absent from the restricted PATH"
if [ -f "$RECORDER" ]; then
  ok "record-dept-decision.sh present"
else
  bad "record-dept-decision.sh missing at $RECORDER"
fi

# Every call runs with an EMPTY environment except HOME, PATH, TMPDIR and the
# offline rate-limit ledger. The ledger path must be explicit: with an empty
# HOME there is no workspace for the gate to find, and an unset path makes the
# gate refuse (exit 89) before the writer is ever reached. The ledger is the
# rate-limit gate's offline fixture hook — never a behaviour change.
# Concurrent calls share one ledger through one session bucket key: passing a
# distinct --session per call gives each its own bucket, so T4's twenty
# writers do not race the gate's unlocked read-modify-write.
run_rec() {
  env -i \
    HOME="$HOME_DIR" \
    PATH="$NOJQ_PATH" \
    TMPDIR="$WORK" \
    INTERVIEW_RATE_LIMIT_STATE_FILE="$WORK/rate-limit.json" \
    bash "$RECORDER" "$@"
}

# fresh_state <name> -> prints the path of a new, empty state file.
fresh_state() {
  local dir="$WORK/state-$1"
  mkdir -p "$dir"
  printf '{}\n' > "$dir/state.json"
  printf '%s' "$dir/state.json"
}

sha256_of() {
  PATH="$NOJQ_PATH" python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$1"
}

# verify <mode> <state> [args...] — reads the state file and asserts a shape.
verify() {
  PATH="$NOJQ_PATH" python3 - "$@" <<'PYVERIFY'
import json
import sys

mode, state_path = sys.argv[1], sys.argv[2]
rest = sys.argv[3:]

try:
    state = json.load(open(state_path))
except Exception as exc:  # state must be readable JSON
    print(f"state unreadable: {exc}")
    sys.exit(1)

recon = state.get("canonicalReconciliation")
if recon is not None and not isinstance(recon, dict):
    print(f"canonicalReconciliation is not an object: {type(recon).__name__}")
    sys.exit(1)
decisions = (recon or {}).get("decisions")
if decisions is not None and not isinstance(decisions, dict):
    print(f"canonicalReconciliation.decisions is not an object: {type(decisions).__name__}")
    sys.exit(1)

FIVE = ("decision", "source", "decidedAt", "decidedBy", "sessionId")

if mode == "five":
    dept, want_decision = rest[0], rest[1]
    entry = decisions.get(dept)
    if not isinstance(entry, dict):
        print(f"{dept}: missing or not an object ({entry!r})")
        sys.exit(1)
    missing = [k for k in FIVE if k not in entry]
    if missing:
        print(f"{dept}: missing fields {missing}")
        sys.exit(1)
    empties = [k for k in FIVE if not entry.get(k)]
    if empties:
        print(f"{dept}: empty provenance fields {empties}")
        sys.exit(1)
    if entry.get("decision") != want_decision:
        print(f"{dept}: decision {entry.get('decision')!r} != {want_decision!r}")
        sys.exit(1)
    if entry.get("decidedBy") != "t" or entry.get("sessionId") != "s":
        print(f"{dept}: unexpected provenance {entry!r}")
        sys.exit(1)
    print(f"{dept}: holds the five provenance fields, decision={want_decision}")
    sys.exit(0)

if mode == "ack":
    dept = rest[0]
    entry = decisions.get(dept)
    if not isinstance(entry, dict):
        print(f"{dept}: missing ({entry!r})")
        sys.exit(1)
    if entry.get("lossWarningAck") is not True:
        print(f"{dept}: lossWarningAck is {entry.get('lossWarningAck')!r}, want True")
        sys.exit(1)
    if not entry.get("lossWarning"):
        print(f"{dept}: no lossWarning text stamped")
        sys.exit(1)
    if entry.get("decision") != "no":
        print(f"{dept}: decision {entry.get('decision')!r} != 'no'")
        sys.exit(1)
    print(f"{dept}: lossWarning + lossWarningAck=true stamped")
    sys.exit(0)

if mode == "empty":
    if decisions:
        print(f"state file changed despite the refusal: found {sorted(decisions)}")
        sys.exit(1)
    print("no decisions recorded (untouched state file)")
    sys.exit(0)

# Concurrent calls share one ledger through one session bucket key: passing a
# distinct --session per call gives each its own bucket, so T4's twenty
# writers do not race the gate's unlocked read-modify-write. The session key
# is only the rate-limit bucket — the stored sessionId still records per
# call.
if mode == "all":
    wanted = rest
    missing = [d for d in wanted if not isinstance(decisions.get(d), dict)]
    if missing:
        print(f"{len(missing)} of {len(wanted)} decisions missing: {missing}")
        sys.exit(1)
    print(f"all {len(wanted)} decisions present")
    sys.exit(0)

print(f"unknown mode {mode!r}")
sys.exit(2)
PYVERIFY
}

# ── T1: a "yes" is recorded on a box with no jq ───────────────────────────────
echo "== T1: --decision yes with no jq =="
S1="$(fresh_state t1)"
run_rec --dept marketing --decision yes --by t --session s --state "$S1"
if [ "$?" -eq 0 ]; then
  ok "T1: exit 0"
else
  bad "T1: expected exit 0"
fi
if out="$(verify five "$S1" marketing yes)"; then
  ok "T1: $out"
else
  bad "T1: $out"
fi

# ── T2: a floor "no" without --confirm-loss writes nothing ────────────────────
echo "== T2: floor 'no' without --confirm-loss =="
S2="$(fresh_state t2)"
BEFORE="$(sha256_of "$S2")"
run_rec --dept marketing --decision no --by t --session s --state "$S2"
rc=$?
if [ "$rc" -eq 2 ]; then
  ok "T2: exit 2"
else
  bad "T2: expected exit 2, got $rc"
fi
AFTER="$(sha256_of "$S2")"
if [ "$BEFORE" = "$AFTER" ]; then
  ok "T2: state file byte-identical (nothing written)"
else
  bad "T2: state file changed despite the refusal"
fi
if out="$(verify empty "$S2")"; then
  ok "T2: $out"
else
  bad "T2: state file changed despite the refused write — $out"
fi

# ── T3: the same "no" with --confirm-loss is written and acknowledged ─────────
echo "== T3: floor 'no' with --confirm-loss =="
S3="$(fresh_state t3)"
run_rec --dept marketing --decision no --confirm-loss --by t --session s --state "$S3"
rc=$?
if [ "$rc" -eq 0 ]; then
  ok "T3: exit 0"
else
  bad "T3: expected exit 0, got $rc"
fi
if out="$(verify ack "$S3" marketing)"; then
  ok "T3: $out"
else
  bad "T3: $out"
fi

# ── T4: twenty departments recorded at the same time ──────────────────────────
echo "== T4: twenty concurrent department decisions =="
DEPT_IDS="$(python3 - "$LISTER" <<'PYIDS'
import json
import subprocess
import sys

run = subprocess.run([sys.executable, sys.argv[1], "--json"],
                     capture_output=True, text=True)
if run.returncode != 0:
    raise SystemExit(0)
data = json.loads(run.stdout)
ids = []
for group in ("mandatory", "universal_primary_vertical"):
    for entry in data.get(group) or []:
        did = entry.get("id")
        if did and did not in ids:
            ids.append(did)
print("\n".join(ids[:20]))
PYIDS
)"
COUNT=0
for _id in $DEPT_IDS; do COUNT=$((COUNT+1)); done
if [ "$COUNT" -eq 20 ]; then
  ok "T4: resolved 20 canonical department ids"
else
  bad "T4: resolved $COUNT canonical department ids, need 20"
fi

if [ "$COUNT" -eq 20 ]; then
  S4="$(fresh_state t4)"
  PIDS=""
  i=0
  for _id in $DEPT_IDS; do
    i=$((i+1))
    run_rec --dept "$_id" --decision yes --by t --session "t4-$i" --state "$S4" \
      >"$WORK/t4-$_id.out" 2>&1 &
    PIDS="$PIDS $!"
  done
  FAILED=0
  for _pid in $PIDS; do
    if ! wait "$_pid"; then FAILED=$((FAILED+1)); fi
  done
  if [ "$FAILED" -eq 0 ]; then
    ok "T4: all 20 calls exited 0"
  else
    bad "T4: $FAILED of 20 calls exited non-zero"
  fi
  if out="$(verify all "$S4" $DEPT_IDS)"; then
    ok "T4: $out"
  else
    bad "T4: $out"
  fi
fi

echo "--------------------------------------------"
echo "  pass=$PASS fail=$FAIL"
if [ "$FAIL" -eq 0 ]; then
  echo "ALL NO-JQ RECORD-DEPT-DECISION TESTS PASSED"
  exit 0
fi
echo "NO-JQ RECORD-DEPT-DECISION TEST FAILURES: $FAIL"
exit 1
