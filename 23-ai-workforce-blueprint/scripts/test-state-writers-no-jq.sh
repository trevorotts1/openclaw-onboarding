#!/usr/bin/env bash
# test-state-writers-no-jq.sh — CI guard for the four state writers BU-36 routes
# through the locked workforce_state writer.
#
# WHAT IT TESTS:
#   On a box with NO jq, restricted to the folders of bash and python3 (plus the
#   handful of plain utilities each writer legitimately calls):
#
#     1. record-industry-pack.sh --slug "o'neil \"coaching\""
#        --source owner-confirmed --state <temp> exits 0 and the stored slug is
#        byte-for-byte that exact text — a quote in a slug can neither break the
#        program nor change what is stored.
#     2. verify-library-gate.sh, against a temp state and a stub
#        qc-completeness.sh, does not exit 5 (the old "jq is missing" exit) and
#        still writes its gate fields through the locked writer.
#     3. twenty runs launched at the same time — mixing record-industry-pack.sh,
#        the watchdog's blocker write and the department-decision write — lose no
#        field: every writer's output is present at the end.
#
# PATH is restricted and is proven to hold no jq, so nothing here can silently
# fall back to jq.
#
# Exit 0 = every check passed; non-zero = at least one check failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RECORD_PACK="$SCRIPT_DIR/record-industry-pack.sh"
VERIFY_GATE="$SCRIPT_DIR/verify-library-gate.sh"
WATCHDOG="$SCRIPT_DIR/closeout-readiness-watchdog.sh"
RECORD_DECISION="$SCRIPT_DIR/record-dept-decision.sh"
LISTER="$SCRIPT_DIR/list-canonical-departments.py"

PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

# Temp on the drive when TMPDIR points there (the room exports it); the template
# argument keeps mktemp off the system temp folder.
WORK="$(mktemp -d "${TMPDIR:-/tmp}/writers-nojq.XXXXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

# Empty HOME, except for the workspace folder every platform resolver looks for.
# The writers are still told their state file explicitly with --state /
# WORKFORCE_BUILD_STATE_FILE / ZHC_STATE_FILE; the folder exists only so the
# shared platform detection can succeed on a box-shaped home.
HOME_DIR="$WORK/home"
mkdir -p "$HOME_DIR/.openclaw/workspace"

# PATH = one folder of exact symlinks, nothing else. It holds bash, python3 and
# the plain utilities the writers call; it deliberately does NOT hold jq. The
# SKIP gate below proves jq is really absent.
TOOLDIR="$WORK/tools"
mkdir -p "$TOOLDIR"
for _t in bash python3 dirname tr env mktemp date mkdir ls head grep sed tee touch rm stat; do
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
for _f in "$RECORD_PACK" "$VERIFY_GATE" "$WATCHDOG" "$RECORD_DECISION"; do
  if [ -f "$_f" ]; then ok "$(basename "$_f") present"; else bad "missing at $_f"; fi
done

fresh_state() {
  local dir="$WORK/state-$1"
  mkdir -p "$dir"
  printf '{}\n' > "$dir/state.json"
  printf '%s' "$dir/state.json"
}

# verify <mode> <state> [args...] — reads the state file and asserts a shape.
verify_state() {
  PATH="$NOJQ_PATH" python3 - "$@" <<'PYVERIFY'
import json
import sys

mode, state_path = sys.argv[1], sys.argv[2]
rest = sys.argv[3:]

try:
    state = json.load(open(state_path))
except Exception as exc:
    print(f"state unreadable: {exc}")
    sys.exit(1)

if mode == "pack":
    want = rest[0]
    pack = state.get("industryPack")
    if not isinstance(pack, dict):
        print(f"industryPack missing or not an object ({pack!r})")
        sys.exit(1)
    got = pack.get("slug")
    if got != want:
        print(f"slug stored as {got!r}, want {want!r}")
        sys.exit(1)
    if pack.get("source") != "owner-confirmed":
        print(f"source stored as {pack.get('source')!r}")
        sys.exit(1)
    print(f"slug stored byte-for-byte: {got!r}")
    sys.exit(0)

if mode == "gate":
    missing = [k for k in ("roleLibraryStatus", "sopLibraryStatus", "trioStatus") if k not in state]
    if missing:
        print(f"gate fields not written: {missing}")
        sys.exit(1)
    print("gate fields written through the locked writer")
    sys.exit(0)

if mode == "mixed":
    depts = rest
    recon = state.get("canonicalReconciliation")
    decisions = (recon or {}).get("decisions") if isinstance(recon, dict) else None
    decisions = decisions if isinstance(decisions, dict) else {}
    lost = []
    if not isinstance(state.get("industryPack"), dict):
        lost.append("industryPack")
    missing_depts = [d for d in depts if not isinstance(decisions.get(d), dict)]
    if missing_depts:
        lost.append("decisions:" + ",".join(missing_depts))
    if not isinstance(state.get("closeoutBlockers"), list) or not state.get("closeoutBlockers"):
        lost.append("closeoutBlockers")
    stuck = state.get("stuckEscalations")
    if not isinstance(stuck, dict) or not stuck.get("STUCK_QC_FAILED"):
        lost.append("stuckEscalations.STUCK_QC_FAILED")
    if lost:
        print("fields lost to a concurrent write: " + "; ".join(lost))
        sys.exit(1)
    print(f"no field lost ({len(depts)} decisions, pack, blocker and throttle all present)")
    sys.exit(0)

print(f"unknown mode {mode!r}")
sys.exit(2)
PYVERIFY
}

# ── T1: a slug with a quote round-trips, with no jq ──────────────────────────
echo "== T1: record-industry-pack.sh with a quoted slug, no jq =="
S1="$(fresh_state t1)"
QUOTED_SLUG='o'"'"'neil "coaching"'
env -i HOME="$HOME_DIR" PATH="$NOJQ_PATH" TMPDIR="$WORK" \
  bash "$RECORD_PACK" --slug "$QUOTED_SLUG" --source owner-confirmed --state "$S1" \
  >"$WORK/t1.out" 2>&1
rc=$?
if [ "$rc" -eq 0 ]; then
  ok "T1: exit 0"
else
  bad "T1: expected exit 0, got $rc ($(tail -2 "$WORK/t1.out" 2>/dev/null | tr '\n' ' '))"
fi
if out="$(verify_state pack "$S1" "$QUOTED_SLUG")"; then
  ok "T1: $out"
else
  bad "T1: $out"
fi

# ── T2: verify-library-gate.sh needs no jq to run or to write ────────────────
echo "== T2: verify-library-gate.sh with a stub qc-completeness.sh, no jq =="
S2="$(fresh_state t2)"
SANDBOX="$WORK/gate"
mkdir -p "$SANDBOX"
cp "$SCRIPT_DIR/lib-workforce-state.sh" "$SCRIPT_DIR/workforce_state.py" \
   "$VERIFY_GATE" "$SANDBOX/"
for _f in lib-workforce-state.sh workforce_state.py verify-library-gate.sh; do
  if [ ! -f "$SANDBOX/$_f" ]; then bad "T2: could not stage $_f into the sandbox"; fi
done
# The stub stands in for the expensive completeness pass: one artifact, no work.
cat > "$SANDBOX/qc-completeness.sh" <<'QCSTUB'
#!/usr/bin/env bash
mkdir -p "$HOME/.openclaw/logs"
printf '%s\n' '{"departments": []}' > "$HOME/.openclaw/logs/qc-completeness-stub.json"
exit 0
QCSTUB
env -i HOME="$HOME_DIR" PATH="$NOJQ_PATH" TMPDIR="$WORK" \
  WORKFORCE_BUILD_STATE_FILE="$S2" \
  bash "$SANDBOX/verify-library-gate.sh" >"$WORK/t2.out" 2>&1
rc=$?
if [ "$rc" -eq 5 ]; then
  bad "T2: exited 5 (the old missing-jq exit) — $(tail -2 "$WORK/t2.out" | tr '\n' ' ')"
else
  ok "T2: did not exit 5 (exit $rc)"
fi
if out="$(verify_state gate "$S2")"; then
  ok "T2: $out"
else
  bad "T2: $out"
fi

# ── T3: twenty concurrent writers lose no field ──────────────────────────────
echo "== T3: twenty concurrent writers, no jq =="
DEPTS="$(python3 - "$LISTER" <<'PYIDS'
import json
import subprocess
import sys

run = subprocess.run([sys.executable, sys.argv[1], "--json"], capture_output=True, text=True)
if run.returncode != 0:
    raise SystemExit(0)
data = json.loads(run.stdout)
ids = []
for group in ("mandatory", "universal_primary_vertical"):
    for entry in data.get(group) or []:
        did = entry.get("id")
        if did and did not in ids:
            ids.append(did)
print("\n".join(ids[:7]))
PYIDS
)"
COUNT=0
for _d in $DEPTS; do COUNT=$((COUNT+1)); done
if [ "$COUNT" -eq 7 ]; then
  ok "T3: resolved 7 canonical department ids"
else
  bad "T3: resolved $COUNT canonical department ids, need 7"
fi

if [ "$COUNT" -eq 7 ]; then
  S3="$(fresh_state t3)"
  # The watchdog classifies on these two fields; the blocker write is its
  # state_append_blocker_and_throttle path.
  printf '%s\n' '{"interviewComplete": true, "interviewQc": {"status": "fail"}}' > "$S3"
  OCROOT="$WORK/oc"
  mkdir -p "$OCROOT/workspace"

  PIDS=""
  i=0
  for _d in $DEPTS; do
    i=$((i+1))
    env -i HOME="$HOME_DIR" PATH="$NOJQ_PATH" TMPDIR="$WORK" \
      INTERVIEW_RATE_LIMIT_STATE_FILE="$WORK/t3-rate-limit.json" \
      bash "$RECORD_DECISION" --dept "$_d" --decision yes --by t \
      --session "t3-$i" --state "$S3" >>"$WORK/t3-decision.out" 2>&1 &
    PIDS="$PIDS $!"
  done
  i=0
  for _d in $DEPTS; do
    i=$((i+1))
    env -i HOME="$HOME_DIR" PATH="$NOJQ_PATH" TMPDIR="$WORK" \
      bash "$RECORD_PACK" --slug "pack-$i" --source owner-confirmed --state "$S3" \
      >>"$WORK/t3-pack.out" 2>&1 &
    PIDS="$PIDS $!"
  done
  i=0
  while [ "$i" -lt 6 ]; do
    i=$((i+1))
    env -i HOME="$HOME_DIR" PATH="$NOJQ_PATH" TMPDIR="$WORK" \
      OC_ROOT="$OCROOT" ZHC_STATE_FILE="$S3" ZHC_SKIP_TG_PREFLIGHT=1 \
      bash "$WATCHDOG" --local >>"$WORK/t3-watchdog.out" 2>&1 &
    PIDS="$PIDS $!"
  done

  FAILED=0
  for _pid in $PIDS; do
    if ! wait "$_pid"; then FAILED=$((FAILED+1)); fi
  done
  if [ "$FAILED" -eq 0 ]; then
    ok "T3: all 20 calls exited 0"
  else
    bad "T3: $FAILED of 20 calls exited non-zero"
  fi
  if out="$(verify_state mixed "$S3" $DEPTS)"; then
    ok "T3: $out"
  else
    bad "T3: $out"
  fi
fi

echo "--------------------------------------------"
echo "  pass=$PASS fail=$FAIL"
if [ "$FAIL" -eq 0 ]; then
  echo "ALL STATE-WRITER NO-JQ TESTS PASSED"
  exit 0
fi
echo "STATE-WRITER NO-JQ TEST FAILURES: $FAIL"
exit 1
