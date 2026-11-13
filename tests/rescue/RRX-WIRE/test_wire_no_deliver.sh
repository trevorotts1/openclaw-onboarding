#!/usr/bin/env bash
# =============================================================================
# tests/rescue/RRX-WIRE/test_wire_no_deliver.sh
# =============================================================================
# RRX-018. Two rules, both about DELIBERATE REFUSAL rather than a guess:
#
#   CASE 1 — never register the poll with delivery on. The poll runs every 2
#   minutes. The historical path used to add it WITHOUT --no-deliver whenever
#   the CLI refused the add WITH it, so a box could post into the owner's chat
#   every 2 minutes forever. Now the refusal is final: wire.sh exits 1 and the
#   poll is never registered by the delivering form.
#
#   CASE 2 — never decide by grep. When the cron list cannot be parsed as JSON
#   (no node, no python3, or a non-JSON answer) the count is UNKNOWN, not
#   "absent". register_intake_auth_cron must add NOTHING on an unknown; the
#   historical text grep could read a job that was not there, or miss one that
#   was, and register a second delivering daily job either way.
#
# Both cases run the REAL wire.sh against a stub `openclaw` that records every
# argv vector. The recorder is proven live in each case (C0 / C1), because a
# "did NOT record" assertion against a dead instrument passes for free.
#
# Exit 0 = all pass. Exit 1 = one or more failed.
# =============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
RECEIVER="$REPO_ROOT/65-rescue-receiver"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== test_wire_no_deliver.sh ==="

WORK="$(mktemp -d)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

# Shared fixture builder: creates a box tree at $1 with a stub `openclaw` that
# logs argv and, when $2 is "yes", REFUSES the --no-deliver add. What the stub
# answers for `cron list` is passed in as RR_STUB_LIST_ANSWER at run time.
make_box() {
  _box="$1"; _refuse="$2"
  _oc="$_box/.openclaw"
  mkdir -p "$_oc/skills/65-rescue-receiver" "$_oc/skills/shared-utils" \
           "$_oc/secrets" "$_oc/state" "$_box/bin"

  cp "$RECEIVER/wire.sh"                 "$_oc/skills/65-rescue-receiver/"
  cp "$RECEIVER/rescue-poll.sh"          "$_oc/skills/65-rescue-receiver/"
  cp "$RECEIVER/rr-intake-auth-check.sh" "$_oc/skills/65-rescue-receiver/"
  cp "$RECEIVER/rr_escalate.py"          "$_oc/skills/65-rescue-receiver/" 2>/dev/null \
    || printf '#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n' \
         > "$_oc/skills/65-rescue-receiver/rr_escalate.py"
  # NO rr-readiness.sh: this fixture is the HISTORICAL path (engine absent),
  # which is exactly where the delivering fallback lived.
  cp "$REPO_ROOT/shared-utils/rescue-env.sh" "$_oc/skills/shared-utils/"

  cat > "$_box/bin/openclaw" <<SH
#!/usr/bin/env python3
import json, os, sys

LOG = os.environ["RR_STUB_LOG"]
REFUSE_NODELIVER = "${_refuse}" == "yes"
LIST_ANSWER = os.environ.get("RR_STUB_LIST_ANSWER", "")

argv = sys.argv[1:]
with open(LOG, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(argv) + "\n")

if not argv or argv[0] != "cron":
    sys.exit(0)
act = argv[1] if len(argv) > 1 else ""
if act == "list":
    sys.stdout.write(LIST_ANSWER)
    sys.exit(0)
if act == "add":
    if REFUSE_NODELIVER and "--no-deliver" in argv:
        sys.stderr.write("stub: refusing --no-deliver\n")
        sys.exit(1)
    sys.exit(0)
sys.exit(0)
SH
  chmod +x "$_box/bin/openclaw"
  : > "$_box/argv.jsonl"
}

# -----------------------------------------------------------------------------
# CASE 1: the CLI refuses the add WITH --no-deliver. wire.sh must exit 1 and
# must never call `cron add` without --no-deliver.
# -----------------------------------------------------------------------------
echo "--- case 1: refused --no-deliver, historical path ---"
BOX1="$WORK/box1"
make_box "$BOX1" yes
printf 'RR_RECEIVER_URL=http://127.0.0.1:1/rr\nRR_BOX_TOKEN=synthetic-not-a-credential\nRR_BOX_SLUG=box-synthetic\n' \
  > "$BOX1/.openclaw/secrets/.env"
chmod 600 "$BOX1/.openclaw/secrets/.env"

OUT1="$(env \
  RR_ROOT="$BOX1/.openclaw" \
  OC_CONFIG_ROOT="$BOX1/.openclaw" \
  OC_PLATFORM=mac \
  OC_TARGET_MODE=launchd \
  OC_TARGET_ID=ai.openclaw.gateway \
  OC_SERVICE_LABEL=ai.openclaw.gateway \
  OC_SKIP_CLI_PROBE=1 \
  RR_STUB_LOG="$BOX1/argv.jsonl" \
  RR_STUB_LIST_ANSWER='{"jobs":[]}' \
  HOME="$BOX1" \
  PATH="$BOX1/bin:$PATH" \
  bash "$BOX1/.openclaw/skills/65-rescue-receiver/wire.sh" 2>&1)"
RC1=$?

[ "$RC1" -eq 1 ] \
  && pass "A1: wire.sh exits 1 when the CLI refuses the --no-deliver add" \
  || fail "A1: wire.sh exited $RC1, expected 1; output: $OUT1"

if [ -s "$BOX1/argv.jsonl" ]; then
  pass "C0: the stub recorded calls (the instrument is live)"
else
  fail "C0: the stub recorded nothing; the recorder is not behaving as an instrument"
fi

_report1="$(
  RR_STUB_LOG="$BOX1/argv.jsonl" python3 - <<'PY'
import json, os, sys

calls = []
with open(os.environ["RR_STUB_LOG"], encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line:
            calls.append(json.loads(line))

def adds(name):
    return [c for c in calls
            if len(c) >= 2 and c[0] == "cron" and c[1] == "add" and name in c]

poll = adds("rescue-rr-box-poll")
print("POLL_ADDS %d" % len(poll))
print("POLL_NODELIVER %d" % len([c for c in poll if "--no-deliver" in c]))
sys.exit(0)
PY
)"
_pa="$(printf '%s\n' "$_report1" | sed -n 's/^POLL_ADDS \([0-9][0-9]*\)$/\1/p')"
_pn="$(printf '%s\n' "$_report1" | sed -n 's/^POLL_NODELIVER \([0-9][0-9]*\)$/\1/p')"

[ "$_pn" = "1" ] \
  && pass "A2: the poll add WAS attempted once, with --no-deliver (it was really tried)" \
  || fail "A2: expected one poll add with --no-deliver, got ${_pn:-none}"
[ "$_pa" = "1" ] \
  && pass "A3: the poll was NEVER added again without --no-deliver" \
  || fail "A3: the poll add was retried without --no-deliver (adds: ${_pa:-none})"

# -----------------------------------------------------------------------------
# CASE 2: `cron list` answers "not json". The count is UNKNOWN, so the intake
# auth cron must NOT be added.
# -----------------------------------------------------------------------------
echo "--- case 2: cron list is not JSON ---"
BOX2="$WORK/box2"
make_box "$BOX2" no
# UNENROLLED on the reply leg: the daily intake check is still registered here,
# so this path calls register_intake_auth_cron with nothing else in the way.
printf 'RR_RECEIVER_URL=http://127.0.0.1:1/rr\nRR_BOX_SLUG=box-synthetic\n' \
  > "$BOX2/.openclaw/secrets/.env"
chmod 600 "$BOX2/.openclaw/secrets/.env"

OUT2="$(env \
  RR_ROOT="$BOX2/.openclaw" \
  OC_CONFIG_ROOT="$BOX2/.openclaw" \
  OC_PLATFORM=mac \
  OC_TARGET_MODE=launchd \
  OC_TARGET_ID=ai.openclaw.gateway \
  OC_SERVICE_LABEL=ai.openclaw.gateway \
  OC_SKIP_CLI_PROBE=1 \
  RR_STUB_LOG="$BOX2/argv.jsonl" \
  RR_STUB_LIST_ANSWER='not json' \
  HOME="$BOX2" \
  PATH="$BOX2/bin:$PATH" \
  bash "$BOX2/.openclaw/skills/65-rescue-receiver/wire.sh" 2>&1)"
RC2=$?

[ "$RC2" -eq 0 ] \
  && pass "B1: wire.sh exits 0 on an unenrolled box even when the cron list is unreadable" \
  || fail "B1: wire.sh exited $RC2, expected 0; output: $OUT2"

if [ -s "$BOX2/argv.jsonl" ]; then
  pass "C1: the stub was reached and `cron list` was read (the instrument is live)"
else
  fail "C1: the stub recorded nothing; the instrument is dead"
fi

_report2="$(
  RR_STUB_LOG="$BOX2/argv.jsonl" python3 - <<'PY'
import json, os, sys

calls = []
with open(os.environ["RR_STUB_LOG"], encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line:
            calls.append(json.loads(line))

def adds(name):
    return [c for c in calls
            if len(c) >= 2 and c[0] == "cron" and c[1] == "add" and name in c]

print("INTAKE_ADDS %d" % len(adds("rr-intake-auth-check")))
print("FLUSH_ADDS %d" % len(adds("rr-escalate-flush")))
print("TOTAL_ADDS %d" % len([c for c in calls
                             if len(c) >= 2 and c[0] == "cron" and c[1] == "add"]))
sys.exit(0)
PY
)"
_ia="$(printf '%s\n' "$_report2" | sed -n 's/^INTAKE_ADDS \([0-9][0-9]*\)$/\1/p')"
_fa="$(printf '%s\n' "$_report2" | sed -n 's/^FLUSH_ADDS \([0-9][0-9]*\)$/\1/p')"
_ta="$(printf '%s\n' "$_report2" | sed -n 's/^TOTAL_ADDS \([0-9][0-9]*\)$/\1/p')"

[ "$_ia" = "0" ] \
  && pass "B2: register_intake_auth_cron added NOTHING on an UNKNOWN count" \
  || fail "B2: the intake auth cron was added on an unreadable cron list (adds: ${_ia:-none})"
[ "$_fa" = "0" ] \
  && pass "B3: the outbox flush was not added on an UNKNOWN count either" \
  || fail "B3: the outbox flush was added on an unreadable cron list (adds: ${_fa:-none})"
[ "$_ta" = "0" ] \
  && pass "B4: no cron add of any name was made on an UNKNOWN count" \
  || fail "B4: ${_ta:-some} cron add call(s) were made despite an unreadable cron list"

case "$OUT2" in
  *"present or unknown"*) pass "B5: the box is told 'present or unknown', not 'already declared'" ;;
  *) fail "B5: the output did not say 'present or unknown'; output: $OUT2" ;;
esac

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL assertion(s) failed"
  exit 1
fi
echo "PASS: all assertions passed"
exit 0
