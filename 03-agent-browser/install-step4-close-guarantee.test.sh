#!/usr/bin/env bash
# install-step4-close-guarantee.test.sh -- AUD-21 / FLEET-FIX Area 2 / B.3
#
# Proves INSTALL.md Step 4's guaranteed-close chaining actually guarantees
# `agent-browser close` runs even when an earlier step (snapshot) throws --
# and that the browser process it's responsible for tearing down does not
# survive as an orphan.
#
# Method: extract the EXACT fenced ```bash block from INSTALL.md that
# contains the `trap 'agent-browser close' EXIT` line (so this test proves
# the SHIPPED doc text, not a hand-copied duplicate that could silently
# drift from it -- and fails loud if a future edit removes the trap
# entirely, since extraction then finds nothing). Run it against a stub
# `agent-browser` binary that (a) has `open` spawn a real background process
# standing in for Chromium, (b) FORCES `snapshot -i` to fail (exit 1) --
# the exact acceptance scenario -- and (c) has `close` kill the tracked
# process and record that it ran. Then assert, against REAL OS process
# state: close ran despite the forced failure, and zero orphan processes
# survive.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_MD="$SCRIPT_DIR/INSTALL.md"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== install-step4-close-guarantee.test.sh (AUD-21) ==="
[[ -f "$INSTALL_MD" ]] || { echo "FAIL: INSTALL.md not found: $INSTALL_MD"; exit 1; }

# ── Extract the shipped guaranteed-close code block from INSTALL.md ──────────
EXTRACTED="$(mktemp)"
EXTRACT_OK=1
python3 - "$INSTALL_MD" > "$EXTRACTED" <<'PY' || EXTRACT_OK=0
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
blocks = re.findall(r"```bash\n(.*?)\n```", text, re.S)
target = None
for b in blocks:
    if "trap 'agent-browser close' EXIT" in b:
        target = b
        break
if target is None:
    sys.exit(1)
sys.stdout.write(target)
PY

if [[ "$EXTRACT_OK" -eq 1 && -s "$EXTRACTED" ]]; then
  pass "Step 4's guaranteed-close block (trap 'agent-browser close' EXIT) found in INSTALL.md"
else
  fail "INSTALL.md no longer contains a Step 4 code block with a close trap -- regression, or the doc drifted"
fi
echo "  --- extracted block ---"
sed 's/^/  | /' "$EXTRACTED"
echo "  ------------------------"

# ── Build a stub agent-browser binary ─────────────────────────────────────────
STUB_DIR="$(mktemp -d)"
LOG_FILE="$(mktemp)"
PID_FILE="$(mktemp)"
cleanup() {
  # Best-effort: if the test itself fails partway, don't leave the stand-in
  # process running either.
  [[ -s "$PID_FILE" ]] && kill -9 "$(cat "$PID_FILE")" 2>/dev/null
  rm -rf "$STUB_DIR" "$LOG_FILE" "$PID_FILE" "$EXTRACTED"
}
trap cleanup EXIT

cat > "$STUB_DIR/agent-browser" <<STUBEOF
#!/usr/bin/env bash
# Stub agent-browser for install-step4-close-guarantee.test.sh.
case "\$1" in
  open)
    # Stand in for the real Chromium process CDP would launch.
    ( sleep 300 >/dev/null 2>&1 ) &
    echo "\$!" > "$PID_FILE"
    echo "open" >> "$LOG_FILE"
    exit 0
    ;;
  --headed)
    # --headed false open URL form -- \$1=--headed \$2=false \$3=open
    shift 2
    if [[ "\${1:-}" == "open" ]]; then
      ( sleep 300 >/dev/null 2>&1 ) &
      echo "\$!" > "$PID_FILE"
      echo "open" >> "$LOG_FILE"
      exit 0
    fi
    exit 0
    ;;
  snapshot)
    echo "snapshot" >> "$LOG_FILE"
    # FORCE the acceptance-test scenario: snapshot throws.
    echo "stub agent-browser: FORCED snapshot failure (test)" >&2
    exit 1
    ;;
  close)
    echo "close" >> "$LOG_FILE"
    if [[ -s "$PID_FILE" ]]; then
      kill -TERM "\$(cat "$PID_FILE")" 2>/dev/null
    fi
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
STUBEOF
chmod +x "$STUB_DIR/agent-browser"

# ── Run the EXTRACTED block against the stub, snapshot FORCED to fail ────────
echo ""
echo "--- running the shipped Step 4 block with snapshot FORCED to fail ---"
BLOCK_RC=0
PATH="$STUB_DIR:$PATH" bash "$EXTRACTED" >/tmp/aud21-block-out.$$ 2>&1 || BLOCK_RC=$?
BLOCK_OUT="$(cat /tmp/aud21-block-out.$$ 2>/dev/null)"; rm -f "/tmp/aud21-block-out.$$"
echo "$BLOCK_OUT" | sed 's/^/  block output: /'

# (1) open ran, snapshot ran (and was the forced failure)
if printf '%s\n' "$(cat "$LOG_FILE" 2>/dev/null)" | grep -q '^open$' && \
   printf '%s\n' "$(cat "$LOG_FILE" 2>/dev/null)" | grep -q '^snapshot$'; then
  pass "open and snapshot both ran (snapshot is the forced-failure step)"
else
  fail "expected open+snapshot to run; log had: $(cat "$LOG_FILE" 2>/dev/null | tr '\n' ',')"
fi

# (2) close STILL ran despite the forced snapshot failure -- the headline assertion.
if grep -q '^close$' "$LOG_FILE" 2>/dev/null; then
  pass "close STILL executed even though snapshot threw (guaranteed-close trap fired)"
else
  fail "close did NOT run after snapshot's forced failure -- guaranteed-close is broken"
fi

# (3) the real failure (snapshot's exit 1) is still surfaced, not swallowed by close's exit 0.
if [[ "$BLOCK_RC" -ne 0 ]]; then
  pass "the block's own exit code ($BLOCK_RC) still reports the real failure -- not masked by close"
else
  fail "the block exited 0 -- the snapshot failure was silently swallowed"
fi

# (4) zero orphan processes: the PID `open` spawned must be dead after close ran.
sleep 0.5
TRACKED_PID="$(cat "$PID_FILE" 2>/dev/null || echo "")"
if [[ -n "$TRACKED_PID" ]] && ! kill -0 "$TRACKED_PID" 2>/dev/null; then
  pass "the tracked browser stand-in process (pid $TRACKED_PID) is dead -- no orphan"
else
  fail "the tracked browser stand-in process is STILL ALIVE -- orphan left behind (pid=${TRACKED_PID:-none})"
fi
LEFTOVER="$(pgrep -f "sleep 300" 2>/dev/null || true)"
if [[ -z "$LEFTOVER" ]]; then
  pass "ZERO orphan Chromium/node stand-in processes remain on the box"
else
  fail "orphan process(es) survived: $LEFTOVER"
  pkill -f "sleep 300" 2>/dev/null || true
fi

echo ""
echo "================================================="
echo "Results: $PASS passed, $FAIL failed"
echo "================================================="
if [[ "$FAIL" -eq 0 ]]; then
  echo "ALL TESTS PASSED"
  exit 0
else
  echo "TESTS FAILED"
  exit 1
fi
