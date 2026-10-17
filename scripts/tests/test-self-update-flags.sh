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
chmod 700 "$T/bin/curl"

# The caller's exact delivery path.
COPY="/tmp/openclaw-self-update-$ROLL.sh"
cp "$SRC" "$COPY" || exit 1

CMD="bash $COPY --roll-id $ROLL --openclaw-target $OC_TARGET --ninerouter-target $NR_TARGET --foreground"
STATUS="$T/root/self-update/$ROLL.status"
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
grep -qx "roll_id=$ROLL" "$STATUS" 2>/dev/null || { echo "FAIL: status carries no roll_id=$ROLL"; fail=1; }
grep -q -- "roll=$ROLL" "$LOG" 2>/dev/null || { echo "FAIL: log did not record the roll id"; fail=1; }
grep -q -- "openclaw=$OC_TARGET" "$LOG" 2>/dev/null || { echo "FAIL: --openclaw-target was not parsed"; fail=1; }
grep -q -- "ninerouter=$NR_TARGET" "$LOG" 2>/dev/null || { echo "FAIL: --ninerouter-target was not parsed"; fail=1; }
# 22 means the parser rejected the contract. On macOS the run then stops at the
# missing 999 checkout (23); elsewhere the Mac steps are skipped (0).
case "$RC" in
  22) echo "FAIL: parser rejected the caller's flags (exit 22)"; fail=1 ;;
  0|23) : ;;
  *) echo "FAIL: unexpected exit $RC"; fail=1 ;;
esac

if [ -f "$STATUS" ]; then
  echo "--- parsed values (from the run's own status/log) ---"
  grep -E '^(step|roll_id|exit_code|gh_auth)=' "$STATUS"
  sed -n 's/.*openclaw=\([^ ]*\) ninerouter=\([^ ]*\).*/openclaw_target=\1 ninerouter_target=\2/p' "$LOG" | head -1
fi

[ "$fail" -eq 0 ] && { echo "PASS: self_update_command() flags accepted end to end"; exit 0; }
echo "FAIL: self-update flag smoke test"; exit 1
