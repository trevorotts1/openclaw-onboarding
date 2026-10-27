#!/usr/bin/env bash
# Smoke test for scripts/self-update.sh against the ONLY caller contract —
# agent-pull-run.py self_update_command(), which generates exactly:
#
#   bash /tmp/openclaw-self-update-<ROLL_ID>.sh \
#        --roll-id <ROLL_ID> --openclaw-target <V> [--ninerouter-target <V>]
#
# This copies the script to that exact /tmp path, puts a stubbed curl first on
# PATH (so nothing leaves the box and no real script is executed), points HOME
# and OPENCLAW_ROOT at a temp tree, and runs the generated string in the
# foreground. Passing means argument parsing accepted every flag; anything
# unexpected exits 22 at the parser, which is the P4-does-nothing failure.
#
# Never touches the real ~/.openclaw. Prints the parsed values it observed.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/../self-update.sh"
[ -f "$SRC" ] || { echo "FAIL: $SRC not found" >&2; exit 1; }

ROLL="roll-smoke-$$"
OC_TARGET="2026.10.4"
NR_TARGET="1.0.0-pinned"

T="$(mktemp -d "${TMPDIR:-/tmp}/self-update-smoke.XXXXXX")" || exit 1
trap 'rm -rf "$T"; rm -f "/tmp/openclaw-self-update-$ROLL.sh"' EXIT
mkdir -p "$T/home" "$T/root" "$T/bin" "$T/fix"

# Stand-ins for the three scripts the runner fetches. Each proves it ran.
printf '%s\n' '#!/usr/bin/env bash' 'echo "[fixture] oc-atomic-upgrade $*"' 'exit 0' > "$T/fix/oc-atomic-upgrade.sh"
printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$T/fix/oc-schema-migrate.py"
printf 'raise SystemExit(1)\n' > "$T/fix/oc-supervisor-install.py"   # CAN015: no supervisor definition on the fixture box
printf '%s\n' '#!/usr/bin/env bash' 'echo "[fixture] weekly-full-update $*"' 'exit 0' > "$T/fix/weekly-full-update.sh"

# curl stub: copy the matching fixture instead of hitting the network.
# git stub: the F3 step clones 999 when absent. Refuse here so nothing leaves
# the box; the job must record the failure and CONTINUE to the later steps.
cat > "$T/bin/git" <<'EOF'
#!/usr/bin/env bash
[ "$1" = "--version" ] && { echo "git version 2.0"; exit 0; }
exit 1
EOF

cat > "$T/bin/curl" <<'EOF'
#!/usr/bin/env bash
url=""; dest=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) dest="$2"; shift 2 ;;
    --max-time) shift 2 ;;
    -*) shift ;;
    *) url="$1"; shift ;;
  esac
done
[ -n "$url" ] && [ -n "$dest" ] || exit 2
printf '%s\n' "$url" >> "${CURL_LOG:-/dev/null}"
src="$FIXTURES/$(basename "$url")"
[ -f "$src" ] || { echo "curl-stub: no fixture for $(basename "$url")" >&2; exit 22; }
cp "$src" "$dest"
EOF
chmod 700 "$T/bin/curl" "$T/bin/git"

# The caller's exact delivery path.
COPY="/tmp/openclaw-self-update-$ROLL.sh"
cp "$SRC" "$COPY" || exit 1

CMD="bash $COPY --roll-id $ROLL --openclaw-target $OC_TARGET --ninerouter-target $NR_TARGET --foreground"
STATUS="$T/root/fleet-refresh/agent-pull-status.json"
LOG="$T/root/self-update/$ROLL.log"
echo "running: $CMD"

# Foreground output goes to this shell's stdout; capture it where the detached
# child would have written it, so the assertions read the run's own record.
mkdir -p "$(dirname "$LOG")"
PATH="$T/bin:$PATH" HOME="$T/home" OPENCLAW_ROOT="$T/root" FIXTURES="$T/fix" \
  eval "$CMD" >>"$LOG" 2>&1
RC=$?

echo "exit=$RC"

fail=0
[ -f "$STATUS" ] || { echo "FAIL: no status file at $STATUS"; fail=1; }
[ -f "$LOG" ]    || { echo "FAIL: no log file at $LOG"; fail=1; }
grep -q -- "roll=$ROLL" "$LOG" 2>/dev/null || { echo "FAIL: log did not record the roll id"; fail=1; }
grep -q -- "openclaw=$OC_TARGET" "$LOG" 2>/dev/null || { echo "FAIL: --openclaw-target was not parsed"; fail=1; }
grep -q -- "ninerouter=$NR_TARGET" "$LOG" 2>/dev/null || { echo "FAIL: --ninerouter-target was not parsed"; fail=1; }
if [ -f "$STATUS" ]; then
  python3 -I - "$STATUS" "$ROLL" <<'PY' || { echo "FAIL: status JSON is not the 10.9 contract"; fail=1; }
import json, sys
d = json.load(open(sys.argv[1]))
need = ("run_id roll_id phase started_utc updated_utc finished_utc step_exit_codes "
        "stamp_before stamp_after openclaw_before openclaw_after ninerouter_before "
        "ninerouter_after rolled_back needs_host_restart stuck_reason error_tail").split()
missing = [k for k in need if k not in d]
if missing:
    print("missing fields: %s" % missing)
    raise SystemExit(1)
if d["roll_id"] != sys.argv[2]:
    print("roll_id %r != %r" % (d["roll_id"], sys.argv[2]))
    raise SystemExit(1)
if not isinstance(d["step_exit_codes"], dict):
    print("step_exit_codes is not a dict")
    raise SystemExit(1)
PY
  # F3: the order is 999 -> 9router -> upgrade -> update, and a failed 999 step
  # does not stop the later ones.
  ORDER="$(grep -o 'STEP [a-z0-9-]*' "$LOG" | head -4 | tr '\n' ' ')"
  [ "$ORDER" = "STEP 999-setup STEP 9router STEP upgrade STEP update " ] \
    || { echo "FAIL: step order: $ORDER"; fail=1; }
fi
# 22 means the parser rejected the contract. On macOS with the git stub refusing
# the clone, 999 is 23 and the job still runs the rest; the exit is the FIRST
# failed step (23). Elsewhere the Mac steps are skipped (0).
case "$RC" in
  22) echo "FAIL: parser rejected the caller's flags (exit 22)"; fail=1 ;;
  0|23) : ;;
  *) echo "FAIL: unexpected exit $RC"; fail=1 ;;
esac

if [ -f "$STATUS" ]; then
  echo "--- parsed values (from the run's own status/log) ---"
  python3 -I -c 'import json,sys;d=json.load(open(sys.argv[1]));print(json.dumps({k:d[k] for k in ("run_id","roll_id","phase","step_exit_codes","finished_utc")},sort_keys=True))' "$STATUS"
  sed -n 's/.*openclaw=\([^ ]*\) ninerouter=\([^ ]*\).*/openclaw_target=\1 ninerouter_target=\2/p' "$LOG" | head -1
fi

# ── onboarding-sha pin (rc5-selfupdate-sha; critic.C1 / critic.C10) ──────────
# A frozen roll must fetch every script at ITS commit, not live main. These cases
# prove the ref reaches the fetch URLs, the status file, and the detached child.

SHA_PIN="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"     # 40 hex — valid
SHA_SHORT="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"    # 39 hex — refused
SHA_LONG="${SHA_PIN}a"                                # 41 hex — refused
SHA_NONHEX="zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz" # 40 chars, not hex — refused
BASE_URL="https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding"

run_case() {  # root url_log [extra flags...] -> the job's exit code
  _r="$1"; _u="$2"; shift 2
  mkdir -p "$_r"
  _c="/tmp/openclaw-self-update-$ROLL.sh"
  cp "$SRC" "$_c" || return 99
  ( PATH="$T/bin:$PATH" HOME="$T/home" OPENCLAW_ROOT="$_r" FIXTURES="$T/fix" \
      CURL_LOG="$_u" bash "$_c" --roll-id "$ROLL" --openclaw-target "$OC_TARGET" \
      --ninerouter-target "$NR_TARGET" --foreground "$@" >/dev/null 2>&1 )
}

U1="$T/urls-pinned.log"; : > "$U1"
run_case "$T/root-pinned" "$U1" --onboarding-sha "$SHA_PIN"; RC1=$?
case "$RC1" in
  0|23) : ;;
  *) echo "FAIL: pinned run exit $RC1 (want 0 or 23)"; fail=1 ;;
esac
if [ -s "$U1" ]; then
  if grep -v "^$BASE_URL/$SHA_PIN/" "$U1" | grep -q .; then
    echo "FAIL: a fetch ignored the pin (want every URL under /$SHA_PIN/):"
    grep -v "^$BASE_URL/$SHA_PIN/" "$U1" | sed 's/^/  /'
    fail=1
  fi
  for f in oc-atomic-upgrade.sh oc-schema-migrate.py oc-supervisor-install.py weekly-full-update.sh; do
    grep -q "^$BASE_URL/$SHA_PIN/scripts/$f\$" "$U1" \
      || { echo "FAIL: pinned run did not fetch scripts/$f at the pinned sha"; fail=1; }
  done
  grep -q "/main/" "$U1" && { echo "FAIL: pinned run fetched something from main"; fail=1; }
else
  echo "FAIL: pinned run recorded no fetches — the pin is unproven"; fail=1
fi
python3 -I - "$T/root-pinned/fleet-refresh/agent-pull-status.json" "$SHA_PIN" <<'PY' || fail=1
import json, sys
d = json.load(open(sys.argv[1]))
bad = []
if d.get("onboarding_sha") != sys.argv[2]:
    bad.append("onboarding_sha=%r" % (d.get("onboarding_sha"),))
if d.get("onboarding_ref") != sys.argv[2]:
    bad.append("onboarding_ref=%r" % (d.get("onboarding_ref"),))
if bad:
    print("FAIL: status pin fields: %s" % ", ".join(bad))
    raise SystemExit(1)
print("ok - status records onboarding_sha and onboarding_ref = %s" % sys.argv[2])
PY

# Backward compatible: no flag means live main, exactly as before.
U2="$T/urls-main.log"; : > "$U2"
run_case "$T/root-main" "$U2"; RC2=$?
case "$RC2" in
  0|23) : ;;
  *) echo "FAIL: unpinned run exit $RC2 (want 0 or 23)"; fail=1 ;;
esac
if [ -s "$U2" ]; then
  if grep -v "^$BASE_URL/main/" "$U2" | grep -q .; then
    echo "FAIL: unpinned run did not fetch from main:"
    grep -v "^$BASE_URL/main/" "$U2" | sed 's/^/  /'
    fail=1
  fi
else
  echo "FAIL: unpinned run recorded no fetches"; fail=1
fi
python3 -I - "$T/root-main/fleet-refresh/agent-pull-status.json" <<'PY' || fail=1
import json, sys
d = json.load(open(sys.argv[1]))
bad = []
if d.get("onboarding_sha") != "":
    bad.append("onboarding_sha=%r (want empty)" % (d.get("onboarding_sha"),))
if d.get("onboarding_ref") != "main":
    bad.append("onboarding_ref=%r (want 'main')" % (d.get("onboarding_ref"),))
if bad:
    print("FAIL: unpinned status fields: %s" % ", ".join(bad))
    raise SystemExit(1)
print("ok - unpinned run records ref=main with no sha")
PY

# Bad shapes are refused at the parser, before any fetch or root lookup.
for bad in "$SHA_SHORT" "$SHA_LONG" "$SHA_NONHEX" "abcdef0"; do
  out="$(PATH="$T/bin:$PATH" HOME="$T/home" bash "$SRC" --roll-id "$ROLL" \
          --openclaw-target "$OC_TARGET" --onboarding-sha "$bad" 2>&1)"; rc=$?
  [ "$rc" -eq 22 ] || { echo "FAIL: --onboarding-sha '$bad' exit $rc (want 22)"; fail=1; }
  printf '%s' "$out" | grep -q -- "--onboarding-sha must be 40 hex" \
    || { echo "FAIL: --onboarding-sha '$bad' message: $out"; fail=1; }
done
out="$(PATH="$T/bin:$PATH" HOME="$T/home" bash "$SRC" --roll-id "$ROLL" \
        --openclaw-target "$OC_TARGET" --onboarding-sha 2>&1)"; rc=$?
[ "$rc" -eq 22 ] || { echo "FAIL: dangling --onboarding-sha exit $rc (want 22)"; fail=1; }
printf '%s' "$out" | grep -q -- "--onboarding-sha needs a value" \
  || { echo "FAIL: dangling --onboarding-sha message: $out"; fail=1; }

# The env form is honoured and validated the same way (parity with --999-sha).
out="$(ONBOARDING_SHA="$SHA_SHORT" PATH="$T/bin:$PATH" HOME="$T/home" bash "$SRC" \
        --roll-id "$ROLL" --openclaw-target "$OC_TARGET" 2>&1)"; rc=$?
[ "$rc" -eq 22 ] || { echo "FAIL: ONBOARDING_SHA env exit $rc (want 22)"; fail=1; }
printf '%s' "$out" | grep -q -- "--onboarding-sha must be 40 hex" \
  || { echo "FAIL: ONBOARDING_SHA env message: $out"; fail=1; }

# The real delivery is DETACHED: if the parent does not hand the pin to the child
# it starts, the worker silently reverts to main. Capture the child argv without
# spawning anything — a python3 shim records the Popen arguments and answers with
# a fake pid, then defers every other call to the real interpreter.
REAL_PY="$(command -v python3)"
cat > "$T/bin/python3" <<EOF
#!/usr/bin/env bash
if [ "\$1" = "-c" ] && printf '%s' "\$2" | grep -q 'subprocess.Popen'; then
  shift 2
  printf '%s\n' "\$@" >> "\$PY_ARGV_LOG"
  echo 999999
  exit 0
fi
exec "$REAL_PY" "\$@"
EOF
chmod 700 "$T/bin/python3"
mkdir -p "$T/root-detach"
ARGV="$T/child-argv.log"; : > "$ARGV"
PATH="$T/bin:$PATH" HOME="$T/home" OPENCLAW_ROOT="$T/root-detach" FIXTURES="$T/fix" \
  CURL_LOG="$T/urls-detach.log" PY_ARGV_LOG="$ARGV" \
  bash "$SRC" --roll-id "$ROLL" --openclaw-target "$OC_TARGET" \
  --ninerouter-target "$NR_TARGET" --onboarding-sha "$SHA_PIN" >/dev/null 2>&1
RC3=$?
[ "$RC3" -eq 0 ] || { echo "FAIL: detach launcher exit $RC3 (want 0)"; fail=1; }
[ -s "$ARGV" ] || { echo "FAIL: detach launcher never started a child"; fail=1; }
grep -qx -- "--onboarding-sha" "$ARGV" \
  || { echo "FAIL: the detached child was not given --onboarding-sha"; fail=1; }
grep -qx -- "$SHA_PIN" "$ARGV" \
  || { echo "FAIL: the detached child got no pin value"; fail=1; }

[ "$fail" -eq 0 ] && { echo "PASS: self_update_command() flags + onboarding-sha pin"; exit 0; }
echo "FAIL: self-update flag smoke test"; exit 1
