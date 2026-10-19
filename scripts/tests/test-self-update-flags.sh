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

[ "$fail" -eq 0 ] && { echo "PASS: self_update_command() flags accepted end to end"; exit 0; }
echo "FAIL: self-update flag smoke test"; exit 1
