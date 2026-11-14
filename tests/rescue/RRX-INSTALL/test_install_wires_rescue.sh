#!/usr/bin/env bash
# tests/rescue/RRX-INSTALL/test_install_wires_rescue.sh
# ─────────────────────────────────────────────────────────────────────────────
# RRX-121: a fresh install registers the Rescue Rangers jobs.
#
# Step 5 copies the receiver but used to run only two other skills' wiring
# scripts, so a new box had no poll job and no daily check until its first
# update roll. install.sh now runs 65-rescue-receiver/wire.sh there.
#
# This test extracts the added block from install.sh by reading it (its first
# line is the RRX-121 comment, its last line is `unset _RR_WIRE`) and runs it
# against a fixture:
#   * a stub wire.sh that records that it ran and exits 1;
#   * stub warn / success functions that record their calls.
# It asserts the stub ran once (with the roll's two flags), warn was called,
# and the block's own exit status is 0 (a wiring failure never aborts install).
#
# Fully offline. Exit 0 = all assertions pass.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
INSTALL="$REPO_ROOT/install.sh"

PASS=0
FAIL=0
ERRORS=()

ok()  { echo "  PASS: $1"; PASS=$((PASS + 1)); }
bad() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); ERRORS+=("$1"); }

echo ""
echo "=== RRX-121 install.sh wires the Rescue Rangers jobs ==="
echo ""

if [ ! -f "$INSTALL" ]; then
    echo "  FAIL: $INSTALL not found"
    exit 1
fi

# Every temp file stays on the portable drive: TMPDIR must be set by the runner.
if [ -z "${TMPDIR:-}" ]; then
    echo "  FAIL: TMPDIR is not set; refusing to write outside the portable drive"
    exit 1
fi
WORK="$(mktemp -d "$TMPDIR/rrx-install-121.XXXXXX")" || {
    echo "  FAIL: could not create a scratch folder under TMPDIR"
    exit 1
}
trap 'rm -rf "$WORK"' EXIT

BLOCK="$WORK/block.sh"

# ── Extract the block from install.sh ────────────────────────────────────────
# First line: the RRX-121 comment. Last line: `unset _RR_WIRE`. Both must be
# found exactly once after the start marker.
python3 - "$INSTALL" > "$BLOCK" <<'PYEXTRACT'
import sys

path = sys.argv[1]
with open(path, encoding='utf-8') as fh:
    lines = fh.read().splitlines()

start = None
for i, line in enumerate(lines):
    if line.strip().startswith('# RRX-121: register the Rescue Rangers jobs at install time.'):
        start = i
        break
if start is None:
    sys.stderr.write('install.sh: RRX-121 block start not found\n')
    sys.exit(1)

end = None
for j in range(start, len(lines)):
    if lines[j].strip() == 'unset _RR_WIRE':
        end = j
        break
if end is None:
    sys.stderr.write('install.sh: RRX-121 block end (unset _RR_WIRE) not found\n')
    sys.exit(1)

sys.stdout.write('\n'.join(lines[start:end + 1]) + '\n')
PYEXTRACT

if [ ! -s "$BLOCK" ]; then
    echo "  FAIL: could not extract the RRX-121 block from install.sh"
    exit 1
fi
ok "extracted the RRX-121 block from install.sh"

# ── Fixture: a skills tree whose wire.sh records a run and fails ─────────────
mkdir -p "$WORK/skills/65-rescue-receiver"
RUNLOG="$WORK/wire.calls"
cat > "$WORK/skills/65-rescue-receiver/wire.sh" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$RUNLOG"
exit 1
STUB
chmod +x "$WORK/skills/65-rescue-receiver/wire.sh"

# ── Run the block with stubs, in the installer's own shell options ───────────
block_rc=0
(
    set -euo pipefail
    SKILLS_DIR="$WORK/skills"
    LOG_FILE="$WORK/install.log"
    _warnfile="$WORK/warn.calls"
    _okfile="$WORK/success.calls"
    : > "$_warnfile"
    : > "$_okfile"
    warn()    { printf '%s\n' "$*" >> "$_warnfile"; return 0; }
    success() { printf '%s\n' "$*" >> "$_okfile"; return 0; }
    export SKILLS_DIR LOG_FILE RUNLOG
    # shellcheck disable=SC1090
    . "$BLOCK"
) || block_rc=$?

if [ "$block_rc" -eq 0 ]; then
    ok "the block exits 0 when wire.sh fails (a wiring failure never aborts install)"
else
    bad "the block exited $block_rc when wire.sh failed (expected 0)"
fi

runs="$(wc -l < "$RUNLOG" 2>/dev/null | tr -d ' ')"
if [ "${runs:-0}" = "1" ]; then
    ok "the stub wire.sh ran exactly once"
else
    bad "the stub wire.sh ran ${runs:-0} times (expected 1)"
fi

if [ -s "$RUNLOG" ]; then
    case "$(cat "$RUNLOG")" in
        *--idempotent*--reconcile-only*)
            ok "wire.sh was called with the same flags update-skills.sh passes (--idempotent --reconcile-only)" ;;
        *)
            bad "wire.sh was called without the roll's flags: $(cat "$RUNLOG")" ;;
    esac
else
    bad "the stub wire.sh recorded no arguments"
fi

if [ -s "$WORK/warn.calls" ]; then
    ok "warn was called"
else
    bad "warn was never called"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "Failures:"
    for e in "${ERRORS[@]}"; do echo "  - $e"; done
    exit 1
fi
echo "PASS: all assertions passed"
exit 0
