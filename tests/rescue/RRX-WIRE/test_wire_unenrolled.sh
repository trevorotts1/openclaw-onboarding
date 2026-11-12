#!/usr/bin/env bash
# =============================================================================
# tests/rescue/RRX-WIRE/test_wire_unenrolled.sh
# =============================================================================
# RRX-012. A box that is NOT enrolled on the reply leg can still SEND cases.
# Before this unit wire.sh exited at the "not enrolled" gate and registered
# nothing, so such a box never ran the daily escalation-intake check and never
# flushed its outbox: the sending channel was never tested on exactly the boxes
# that depend on it.
#
# What this proves, against a stub `openclaw` that records every argv vector:
#   * wire.sh exits 0 on an unenrolled box (nothing failed; nothing was claimed
#     about the receiver);
#   * it registered the daily intake auth check;
#   * it registered the outbox flush;
#   * it did NOT register the reply-leg poll.
#
# The recorder is proven to work in the same run (C0): a check whose instrument
# records nothing would pass every "did NOT record" assertion for free.
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

echo "=== test_wire_unenrolled.sh ==="

WORK="$(mktemp -d)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

BOX="$WORK/box"
OC="$BOX/.openclaw"
mkdir -p "$OC/skills/65-rescue-receiver" "$OC/skills/shared-utils" \
         "$OC/secrets" "$OC/state" "$BOX/bin"

cp "$RECEIVER/wire.sh"                 "$OC/skills/65-rescue-receiver/"
cp "$RECEIVER/rescue-poll.sh"          "$OC/skills/65-rescue-receiver/"
cp "$RECEIVER/rr-intake-auth-check.sh" "$OC/skills/65-rescue-receiver/"
cp "$RECEIVER/rr-readiness.sh"         "$OC/skills/65-rescue-receiver/"
cp "$RECEIVER/rr_escalate.py"          "$OC/skills/65-rescue-receiver/" 2>/dev/null \
  || printf '#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n' \
       > "$OC/skills/65-rescue-receiver/rr_escalate.py"
cp "$REPO_ROOT/shared-utils/rescue-env.sh"        "$OC/skills/shared-utils/"
cp "$REPO_ROOT/shared-utils/rr-readiness.sh"      "$OC/skills/shared-utils/"
cp "$REPO_ROOT/shared-utils/oc-env-descriptor.sh" "$OC/skills/shared-utils/" 2>/dev/null || true

# The store that makes this box UNENROLLED on the reply leg: URL and slug are
# present, the box token is absent. Nothing here is a real credential.
printf 'RR_RECEIVER_URL=http://127.0.0.1:1/rr\nRR_BOX_SLUG=box-synthetic\n' > "$OC/secrets/.env"
chmod 600 "$OC/secrets/.env"

LOG="$WORK/argv.jsonl"
JOBS="$WORK/jobs.json"
: > "$LOG"
printf '{"jobs":[]}' > "$JOBS"

# ---- Stub openclaw -----------------------------------------------------------
# Records every argv vector as one JSON array per line, and keeps a job store so
# `cron list` reads back what `cron add` wrote. No gateway, no network.
cat > "$BOX/bin/openclaw" <<'SH'
#!/usr/bin/env python3
import json, os, sys

LOG = os.environ["RR_STUB_LOG"]
JOBS = os.environ["RR_STUB_JOBS"]
argv = sys.argv[1:]
with open(LOG, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(argv) + "\n")

def load():
    try:
        with open(JOBS, encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception:
        d = {"jobs": []}
    d.setdefault("jobs", [])
    return d

def save(d):
    with open(JOBS, "w", encoding="utf-8") as fh:
        json.dump(d, fh)

def val(name):
    return argv[argv.index(name) + 1] if name in argv else ""

if not argv or argv[0] != "cron":
    sys.exit(0)
act = argv[1] if len(argv) > 1 else ""
if act == "list":
    print(json.dumps(load()))
    sys.exit(0)
if act == "add":
    d = load()
    d["jobs"].append({
        "id": str(len(d["jobs"]) + 1),
        "name": val("--name"),
        "enabled": True,
        "schedule": {"kind": "cron", "expr": val("--cron")},
        "payload": {"kind": "command", "argv": ["sh", "-lc", val("--command")]},
        "delivery": {"mode": "none" if "--no-deliver" in argv else "announce"},
    })
    save(d)
    sys.exit(0)
sys.exit(0)
SH
chmod +x "$BOX/bin/openclaw"

# ---- Run the real installer --------------------------------------------------
OUT="$(env \
  RR_ROOT="$OC" \
  OC_CONFIG_ROOT="$OC" \
  OC_PLATFORM=mac \
  OC_TARGET_MODE=launchd \
  OC_TARGET_ID=ai.openclaw.gateway \
  OC_SERVICE_LABEL=ai.openclaw.gateway \
  OC_SKIP_CLI_PROBE=1 \
  RR_STUB_LOG="$LOG" \
  RR_STUB_JOBS="$JOBS" \
  HOME="$BOX" \
  PATH="$BOX/bin:$PATH" \
  bash "$OC/skills/65-rescue-receiver/wire.sh" 2>&1)"
RC=$?

# ---- Assertions --------------------------------------------------------------
[ "$RC" -eq 0 ] \
    && pass "A1: wire.sh exits 0 on an unenrolled box (nothing failed, nothing claimed)" \
    || fail "A1: wire.sh exited $RC, expected 0; output: $OUT"

# The recorder's own control: the stub was reached at all. Without this, every
# "did NOT record" assertion below could pass on a dead instrument.
if [ -s "$LOG" ]; then
  pass "C0: the stub recorded calls (the instrument is live)"
else
  fail "C0: the stub recorded nothing; the recorder is not behaving as an instrument"
fi

_report="$(
  RR_STUB_LOG="$LOG" python3 - <<'PY'
import json, sys, os

calls = []
with open(os.environ["RR_STUB_LOG"], encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line:
            calls.append(json.loads(line))

def is_add(name):
    return any(len(c) >= 2 and c[0] == "cron" and c[1] == "add" and name in c for c in calls)

intake = is_add("rr-intake-auth-check")
flush = is_add("rr-escalate-flush")
poll = is_add("rescue-rr-box-poll")
print("INTAKE %d" % (1 if intake else 0))
print("FLUSH %d" % (1 if flush else 0))
print("POLL %d" % (1 if poll else 0))
print("CALLS %d" % len(calls))
sys.exit(0)
PY
)"
_intake="$(printf '%s\n' "$_report" | sed -n 's/^INTAKE \([01]\)$/\1/p')"
_flush="$(printf '%s\n' "$_report" | sed -n 's/^FLUSH \([01]\)$/\1/p')"
_poll="$(printf '%s\n' "$_report" | sed -n 's/^POLL \([01]\)$/\1/p')"
_calls="$(printf '%s\n' "$_report" | sed -n 's/^CALLS \([0-9][0-9]*\)$/\1/p')"

[ "$_intake" = "1" ] \
    && pass "A2: the stub recorded cron add --name rr-intake-auth-check" \
    || fail "A2: no cron add for the intake auth check (calls: $_calls)"
[ "$_flush" = "1" ] \
    && pass "A3: the stub recorded cron add --name rr-escalate-flush" \
    || fail "A3: no cron add for the outbox flush (calls: $_calls)"
[ "$_poll" = "0" ] \
    && pass "A4: the stub recorded NO cron add --name rescue-rr-box-poll" \
    || fail "A4: the reply-leg poll was registered on an unenrolled box"

# =============================================================================
# CASE 2 (RRX-011w). An ENROLLED box registers the outbox flush exactly once,
# with delivery off. A3 above proves registration happens on the unenrolled
# path; this proves the enrolled path adds it once, never twice, and never
# without --no-deliver.
# =============================================================================
BOX2="$WORK/box-enrolled"
OC2="$BOX2/.openclaw"
mkdir -p "$OC2/skills/65-rescue-receiver" "$OC2/skills/shared-utils" \
         "$OC2/secrets" "$OC2/state" "$BOX2/bin"

cp "$RECEIVER/wire.sh"                 "$OC2/skills/65-rescue-receiver/"
cp "$RECEIVER/rescue-poll.sh"          "$OC2/skills/65-rescue-receiver/"
cp "$RECEIVER/rr-intake-auth-check.sh" "$OC2/skills/65-rescue-receiver/"
cp "$RECEIVER/rr-readiness.sh"         "$OC2/skills/65-rescue-receiver/"
cp "$RECEIVER/rr_escalate.py"          "$OC2/skills/65-rescue-receiver/" 2>/dev/null \
  || printf '#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n' \
       > "$OC2/skills/65-rescue-receiver/rr_escalate.py"
cp "$REPO_ROOT/shared-utils/rescue-env.sh"        "$OC2/skills/shared-utils/"
cp "$REPO_ROOT/shared-utils/rr-readiness.sh"      "$OC2/skills/shared-utils/"
cp "$REPO_ROOT/shared-utils/oc-env-descriptor.sh" "$OC2/skills/shared-utils/" 2>/dev/null || true
cp "$BOX/bin/openclaw" "$BOX2/bin/openclaw"
chmod +x "$BOX2/bin/openclaw"

# All three enrollment values resolve: this box IS enrolled on the reply leg.
# Nothing here is a real credential.
printf 'RR_RECEIVER_URL=http://127.0.0.1:1/rr\nRR_BOX_TOKEN=synthetic-not-a-credential\nRR_BOX_SLUG=box-synthetic\n' > "$OC2/secrets/.env"
chmod 600 "$OC2/secrets/.env"

LOG2="$WORK/argv-enrolled.jsonl"
JOBS2="$WORK/jobs-enrolled.json"
: > "$LOG2"
printf '{"jobs":[]}' > "$JOBS2"

_OUT2="$(env \
  RR_ROOT="$OC2" \
  OC_CONFIG_ROOT="$OC2" \
  OC_PLATFORM=mac \
  OC_TARGET_MODE=launchd \
  OC_TARGET_ID=ai.openclaw.gateway \
  OC_SERVICE_LABEL=ai.openclaw.gateway \
  OC_SKIP_CLI_PROBE=1 \
  RR_STUB_LOG="$LOG2" \
  RR_STUB_JOBS="$JOBS2" \
  HOME="$BOX2" \
  PATH="$BOX2/bin:$PATH" \
  bash "$OC2/skills/65-rescue-receiver/wire.sh" 2>&1)"
RC2=$?

# The run must end with one of the installer's OWN exit codes (0 or a retryable
# 1), never a crash such as 127 (unresolved command or function).
if [ "$RC2" -eq 0 ] || [ "$RC2" -eq 1 ]; then
  pass "C1: enrolled wire.sh finished with an installer exit code (rc=$RC2)"
else
  fail "C1: enrolled wire.sh exited $RC2 (expected 0 or 1); output: $_OUT2"
fi

_report2="$(
  RR_STUB_LOG="$LOG2" python3 - <<'PY'
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

flush = adds("rr-escalate-flush")
nodeliver = [c for c in flush if "--no-deliver" in c]
good_cmd = [c for c in nodeliver
            if "rr_escalate.py" in " ".join(c) and "flush" in " ".join(c)]
print("FLUSH_ADDS %d" % len(flush))
print("FLUSH_NODELIVER %d" % len(nodeliver))
print("FLUSH_CMD %d" % len(good_cmd))
sys.exit(0)
PY
)"
_fa="$(printf '%s\n' "$_report2" | sed -n 's/^FLUSH_ADDS \([0-9][0-9]*\)$/\1/p')"
_fn="$(printf '%s\n' "$_report2" | sed -n 's/^FLUSH_NODELIVER \([0-9][0-9]*\)$/\1/p')"
_fc="$(printf '%s\n' "$_report2" | sed -n 's/^FLUSH_CMD \([0-9][0-9]*\)$/\1/p')"

[ "$_fa" = "1" ] \
    && pass "C2: enrolled box recorded exactly one cron add --name rr-escalate-flush" \
    || fail "C2: expected exactly one flush add, got ${_fa:-none}"
[ "$_fn" = "1" ] \
    && pass "C3: the flush add carries --no-deliver (delivery none)" \
    || fail "C3: the flush add was not made with --no-deliver (count: ${_fn:-none})"
[ "$_fc" = "1" ] \
    && pass "C4: the flush add runs rr_escalate.py flush" \
    || fail "C4: the flush command did not name rr_escalate.py flush (count: ${_fc:-none})"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL assertion(s) failed"
  exit 1
fi
echo "PASS: all assertions passed"
exit 0
