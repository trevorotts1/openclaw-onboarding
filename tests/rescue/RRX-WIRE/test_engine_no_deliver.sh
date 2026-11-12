#!/usr/bin/env bash
# =============================================================================
# tests/rescue/RRX-WIRE/test_engine_no_deliver.sh
# =============================================================================
# RRX-043. The readiness ENGINE must never register the poll with delivery on.
#
# The reconciler used to fall back to a plain `cron add` (delivery ON) when the
# silenced form (`--no-deliver`) failed, so a poll that fires every 2 minutes
# could post into the owner's chat for as long as the readback took to notice.
# Now the silenced form is the only one: a refused add is reported as
# `mutation_failed` (rc 7) and nothing is retried with delivery on.
#
# This drives `rrr_cron_reconcile` DIRECTLY (the ladder itself), against a stub
# `openclaw` that:
#   * ADVERTISES --all in `cron list --help` and lists no jobs (the engine's
#     honest "absent, proven by the CLI" starting point);
#   * REFUSES every `cron add` that carries --no-deliver;
#   * records every argv vector as one JSON array per line.
#
# Assertions:
#   A1  the reconciler returns 7
#   A2  the reconcile state is `mutation_failed`
#   A3  a silenced add WAS attempted (so A4 cannot pass on a dead ladder)
#   A4  NO `cron add` was ever issued without --no-deliver
#   C0  the stub recorded calls at all (the instrument is live)
#
# Exit 0 = all pass. Exit 1 = one or more failed.
# =============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
RR028_REPO="$REPO_ROOT"
export RR028_REPO

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== test_engine_no_deliver.sh ==="

WORK="$(mktemp -d "${TMPDIR:-/tmp}/rrx043-engine.XXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

. "$REPO_ROOT/tests/rescue/RR-028/lib-readiness-harness.sh"

BOX="$WORK/box"
rr028_make_box "$BOX"

# Replace the harness mock with the refusing stub this case needs: it accepts
# everything the harness mock accepts EXCEPT `cron add --no-deliver`, which it
# always rejects. `cron list` answers the documented empty envelope, so the
# engine's starting state is absent_proven_by_cli.
LOG="$BOX/argv.jsonl"
: > "$LOG"
cat > "$BOX/bin/openclaw" <<'SH'
#!/usr/bin/env python3
import json, os, sys

LOG = os.environ["RRX_LOG"]
argv = sys.argv[1:]
with open(LOG, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(argv) + "\n")

if not argv or argv[0] != "cron":
    sys.exit(0)
act = argv[1] if len(argv) > 1 else ""
if act == "list" and "--help" in argv[2:]:
    print("usage: openclaw cron list [--json] [--all]")
    print("  --json")
    print("  --all")
    sys.exit(0)
if act == "list":
    print(json.dumps({"jobs": []}))
    sys.exit(0)
if act == "add" and "--help" in argv[2:]:
    print("usage: openclaw cron add --name N --cron E --command C [--no-deliver]")
    sys.exit(0)
if act == "add":
    if "--no-deliver" in argv:
        sys.stderr.write("stub: refusing --no-deliver\n")
        sys.exit(1)
    sys.exit(0)
if act == "edit" and "--help" in argv[2:]:
    print("usage: openclaw cron edit ID [--cron E] [--command C] [--no-deliver]")
    sys.exit(0)
sys.exit(0)
SH
chmod +x "$BOX/bin/openclaw"

# ---- Run the real ladder -----------------------------------------------------
CALL_OUT="$(
  RRX_LOG="$LOG" RRX_BOX="$BOX" bash -c '
    set -u
    . "$RR028_REPO/shared-utils/rr-readiness.sh"
    RRR_ROOT="$RRX_BOX/.openclaw"
    RRR_OPENCLAW_BIN="$RRX_BOX/bin/openclaw"
    RRR_NAME="rescue-rr-box-poll"
    RRR_SCHEDULE="*/2 * * * *"
    RRR_POLL="$RRX_BOX/.openclaw/skills/65-rescue-receiver/rescue-poll.sh"
    RRR_DELIVERY="none"
    RRR_REQ_OPENCLAW="ok"
    RRR_REQ_JSON="ok"
    RRR_TOMBSTONED="0"
    RRR_DB=""
    rrr_cron_reconcile
    printf "RC=%s STATE=%s ACTION=%s\n" \
      "$RRR_RECONCILE_RC" "$RRR_RECONCILE_STATE" "$RRR_RECONCILE_ACTION"
  ' 2>/dev/null)"
CALL_RC=$?

if [ "$CALL_RC" -eq 0 ]; then
  pass "C1: the ladder call completed (rc=0 from the subshell; the verdict is reported in its output)"
else
  fail "C1: the ladder subshell aborted (rc=$CALL_RC); output: $CALL_OUT"
fi

RC_V="$(printf '%s\n' "$CALL_OUT" | sed -n 's/^RC=\([0-9][0-9]*\) .*/\1/p')"
STATE_V="$(printf '%s\n' "$CALL_OUT" | sed -n 's/^RC=[0-9][0-9]* STATE=\([a-z_]*\) .*/\1/p')"

[ "$RC_V" = "7" ] \
  && pass "A1: rrr_cron_reconcile returns 7 (a mutation command failed)" \
  || fail "A1: expected rc 7, got '${RC_V:-none}'; output: $CALL_OUT"
[ "$STATE_V" = "mutation_failed" ] \
  && pass "A2: the reconcile state is mutation_failed" \
  || fail "A2: expected state mutation_failed, got '${STATE_V:-none}'; output: $CALL_OUT"

# The recorder's own control: the stub was reached at all. Without this, the
# "never added without --no-deliver" assertion below could pass on a dead
# instrument.
if [ -s "$LOG" ]; then
  pass "C0: the stub recorded calls (the instrument is live)"
else
  fail "C0: the stub recorded nothing; the recorder is not behaving as an instrument"
fi

_report="$(
  RRX_LOG="$LOG" python3 - <<'PY'
import json, os, sys

calls = []
with open(os.environ["RRX_LOG"], encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line:
            calls.append(json.loads(line))

adds = [c for c in calls if len(c) >= 2 and c[0] == "cron" and c[1] == "add"]
silenced = [c for c in adds if "--no-deliver" in c]
delivering = [c for c in adds if "--no-deliver" not in c]
print("ADDS %d" % len(adds))
print("SILENCED %d" % len(silenced))
print("DELIVERING %d" % len(delivering))
sys.exit(0)
PY
)"
_adds="$(printf '%s\n' "$_report" | sed -n 's/^ADDS \([0-9][0-9]*\)$/\1/p')"
_silenced="$(printf '%s\n' "$_report" | sed -n 's/^SILENCED \([0-9][0-9]*\)$/\1/p')"
_delivering="$(printf '%s\n' "$_report" | sed -n 's/^DELIVERING \([0-9][0-9]*\)$/\1/p')"

[ "${_silenced:-0}" -ge 1 ] \
  && pass "A3: a silenced add WAS attempted once (the ladder really tried to register the poll)" \
  || fail "A3: no cron add with --no-deliver was recorded (adds: ${_adds:-none})"
[ "${_delivering:-0}" = "0" ] \
  && pass "A4: the stub recorded NO cron add without --no-deliver" \
  || fail "A4: a cron add was issued WITHOUT --no-deliver (delivering adds: ${_delivering:-none})"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL assertion(s) failed"
  exit 1
fi
echo "PASS: all assertions passed"
exit 0
