#!/usr/bin/env bash
# =============================================================================
# tests/rescue/RRX-WIRE/test_wire_files_installed.sh
# =============================================================================
# RRX-019. wire.sh used to PRINT "files-installed=1" unconditionally — the line
# was a claim with no check behind it. The poll needs
# shared-utils/rescue-supervise.py to take its lock; with that ONE file missing
# every poll exits having done nothing, and the installer still reported a
# successful installation.
#
# Now the claim is made by rr_install_verify.py: every required file must exist,
# be non-empty and parse, or wire.sh says files-installed=0 and exits 1.
#
#   CASE A — shared-utils/rescue-supervise.py removed:
#            prints files-installed=0 and exits 1.
#   CASE B — the full file set present:
#            prints files-installed=1.
#
# Both cases run the REAL wire.sh against a stub `openclaw` that records every
# argv vector, so a fixture that never reaches the engine fails visibly instead
# of passing for free. The recorder is proven live in each case (C0 / C1).
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

echo "=== test_wire_files_installed.sh ==="

WORK="$(mktemp -d)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

# Fixture builder: a box tree at $1 carrying the FULL file set the poll needs,
# including the four files rr_install_verify.py requires from ADDED_BY_THIS_BUILD
# (they ship from lanes L1 and L2, so this lane's fixture creates them), plus a
# stub `openclaw` that records argv.
make_box() {
  _box="$1"
  _oc="$_box/.openclaw"
  _rc="$_oc/skills/65-rescue-receiver"
  _su="$_oc/skills/shared-utils"
  mkdir -p "$_rc/contracts" "$_su" "$_oc/secrets" "$_oc/state" "$_box/bin"

  # The receiver skill, as installed by the roll.
  cp "$RECEIVER/wire.sh"                 "$_rc/"
  cp "$RECEIVER/rescue-poll.sh"          "$_rc/"
  cp "$RECEIVER/rescue-notification.py"  "$_rc/"
  cp "$RECEIVER/rr-readiness.sh"         "$_rc/"
  cp "$RECEIVER/rr-intake-auth-check.sh" "$_rc/"
  cp "$RECEIVER/rr_intake_classify.py"   "$_rc/"
  cp "$RECEIVER/rr_install_verify.py"    "$_rc/"
  cp "$RECEIVER/contracts/result-v3.schema.json" "$_rc/contracts/"

  # The shared bundle the poll and the engine load.
  cp "$REPO_ROOT/shared-utils/rescue-env.sh"        "$_su/"
  cp "$REPO_ROOT/shared-utils/rr-readiness.sh"      "$_su/"
  cp "$REPO_ROOT/shared-utils/oc-env-descriptor.sh" "$_su/"
  cp "$REPO_ROOT/shared-utils/rescue-supervise.py"  "$_su/"

  # ADDED_BY_THIS_BUILD, minus the one this lane owns. Absent here, so written
  # as the smallest valid Python the verifier accepts (it checks existence,
  # non-emptiness and that it parses — nothing more).
  for _n in rr_escalate.py rr_journal_check.py rr_owner_message.py; do
    if [ -f "$RECEIVER/$_n" ]; then
      cp "$RECEIVER/$_n" "$_rc/"
    else
      printf '#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n' > "$_rc/$_n"
    fi
  done

  cat > "$_box/bin/openclaw" <<SH
#!/usr/bin/env python3
import json, os, sys

LOG = os.environ["RR_STUB_LOG"]
argv = sys.argv[1:]
with open(LOG, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(argv) + "\n")

if not argv or argv[0] != "cron":
    sys.exit(0)
act = argv[1] if len(argv) > 1 else ""
if act == "list":
    sys.stdout.write(json.dumps({"jobs": []}))
    sys.exit(0)
sys.exit(0)
SH
  chmod +x "$_box/bin/openclaw"
  : > "$_box/argv.jsonl"

  # Synthetic enrollment values. Never a real credential.
  printf 'RR_RECEIVER_URL=http://127.0.0.1:1/rr\nRR_BOX_TOKEN=synthetic-not-a-credential\nRR_BOX_SLUG=box-synthetic\n' \
    > "$_oc/secrets/.env"
  chmod 600 "$_oc/secrets/.env"
}

run_wire() {
  _box="$1"
  env \
    RR_ROOT="$_box/.openclaw" \
    OC_CONFIG_ROOT="$_box/.openclaw" \
    OC_PLATFORM=mac \
    OC_TARGET_MODE=launchd \
    OC_TARGET_ID=ai.openclaw.gateway \
    OC_SERVICE_LABEL=ai.openclaw.gateway \
    OC_SKIP_CLI_PROBE=1 \
    RR_STUB_LOG="$_box/argv.jsonl" \
    HOME="$_box" \
    PATH="$_box/bin:$PATH" \
    bash "$_box/.openclaw/skills/65-rescue-receiver/wire.sh" 2>&1
}

# -----------------------------------------------------------------------------
# CASE A: shared-utils/rescue-supervise.py removed. The poll cannot take its
# lock without it, so the installer must NOT claim installation.
# -----------------------------------------------------------------------------
echo "--- case A: shared-utils/rescue-supervise.py removed ---"
BOXA="$WORK/box-a"
make_box "$BOXA"
rm -f "$BOXA/.openclaw/skills/shared-utils/rescue-supervise.py"

OUTA="$(run_wire "$BOXA")"
RCA=$?

[ "$RCA" -eq 1 ] \
  && pass "A1: wire.sh exits 1 when a required file is missing" \
  || fail "A1: wire.sh exited $RCA, expected 1; output: $OUTA"

case "$OUTA" in
  *"files-installed=0"*) pass "A2: wire.sh reports files-installed=0" ;;
  *) fail "A2: no files-installed=0 in the output; output: $OUTA" ;;
esac

case "$OUTA" in
  *"files-installed=1"*) fail "A3: wire.sh ALSO claimed files-installed=1; output: $OUTA" ;;
  *) pass "A3: wire.sh never claimed files-installed=1 on a missing file" ;;
esac

case "$OUTA" in
  *"shared-utils/rescue-supervise.py"*) pass "A4: the failure names the missing file" ;;
  *) fail "A4: the reported detail did not name shared-utils/rescue-supervise.py; output: $OUTA" ;;
esac

if [ -s "$BOXA/argv.jsonl" ]; then
  pass "C0: the stub recorded calls (the instrument is live)"
else
  fail "C0: the stub recorded nothing; the fixture never reached the CLI"
fi

# -----------------------------------------------------------------------------
# CASE B: the full file set present. The installer MAY claim installation.
# -----------------------------------------------------------------------------
echo "--- case B: full file set present ---"
BOXB="$WORK/box-b"
make_box "$BOXB"

OUTB="$(run_wire "$BOXB")"
RCB=$?

case "$OUTB" in
  *"files-installed=1"*) pass "B1: wire.sh reports files-installed=1 when every file is present" ;;
  *) fail "B1: no files-installed=1 in the output; output: $OUTB" ;;
esac

case "$OUTB" in
  *"files-installed=0"*) fail "B2: wire.sh reported files-installed=0 on a complete file set; output: $OUTB" ;;
  *) pass "B2: no files-installed=0 on a complete file set" ;;
esac

if [ -s "$BOXB/argv.jsonl" ]; then
  pass "C1: the stub was reached in the complete fixture (the instrument is live)"
else
  fail "C1: the stub recorded nothing; the case B fixture never reached the CLI (rc=$RCB)"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL assertion(s) failed"
  exit 1
fi
echo "PASS: all assertions passed"
exit 0
