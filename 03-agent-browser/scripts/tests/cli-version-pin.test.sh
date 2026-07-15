#!/usr/bin/env bash
# cli-version-pin.test.sh — GK-28/U90 step (b) regression test.
#
# Proves:
#   1. bump-agent-browser-cli-pin.sh --check PASSES when agent-browser-cli.pin
#      and CLI-VERSION-PIN.md's pinned-version line agree (the shipped state).
#   2. bump-agent-browser-cli-pin.sh --check FAILS when the two are made to
#      disagree (fixture: hand-edit the .pin file only, as bump's own doc
#      warns never to do).
#   3. bump-agent-browser-cli-pin.sh <version> "<reason>" updates BOTH files
#      atomically (new pin value + a new dated bump-log row), and --check
#      PASSES again afterward.
#   4. qc-agent-browser.sh's CLI version-pin section: a stub CLI reporting the
#      PINNED version PASSES; a stub CLI reporting a DIFFERENT version FAILS,
#      naming both the pinned and the installed version (fail-closed on an
#      unpinned/mismatched CLI version, per the unit's binary acceptance).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && cd .. && pwd)"

source "$SCRIPT_DIR/lib-stub-agent-browser.sh"   # kill_stub_pidfile only

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== cli-version-pin.test.sh (GK-28/U90) ==="

WORK="$(mktemp -d)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

stage_install() {
  local home="$1" staged="$1/.openclaw/skills/03-agent-browser"
  mkdir -p "$1/.openclaw/skills"
  cp -R "$SKILL_DIR" "$staged"
  echo "$staged"
}

# ── (1) shipped state: pin + doc agree ───────────────────────────────────────
HOME1="$WORK/home-shipped"
STAGED1="$(stage_install "$HOME1")"
OUT1="$(bash "$STAGED1/scripts/bump-agent-browser-cli-pin.sh" --check 2>&1)"
RC1=$?
if [ "$RC1" -eq 0 ] && echo "$OUT1" | grep -q "^PASS"; then
  pass "shipped agent-browser-cli.pin and CLI-VERSION-PIN.md agree"
else
  fail "expected shipped state to --check clean; rc=$RC1, output: $OUT1"
fi

# ── (2) FAIL-FIRST: hand-edit the .pin file only -> disagreement -> --check FAILS
HOME2="$WORK/home-drift"
STAGED2="$(stage_install "$HOME2")"
echo "9.9.9" > "$STAGED2/agent-browser-cli.pin"
OUT2="$(bash "$STAGED2/scripts/bump-agent-browser-cli-pin.sh" --check 2>&1)"
RC2=$?
if [ "$RC2" -ne 0 ] && echo "$OUT2" | grep -q "disagree"; then
  pass "hand-edited .pin diverging from the doc is caught by --check (FAIL)"
else
  fail "expected --check to FAIL on a hand-edit drift; rc=$RC2, output: $OUT2"
fi

# ── (3) bump updates BOTH files atomically + --check clean afterward ────────
HOME3="$WORK/home-bump"
STAGED3="$(stage_install "$HOME3")"
OUT3A="$(bash "$STAGED3/scripts/bump-agent-browser-cli-pin.sh" 0.31.2 "test bump" 2>&1)"
RC3A=$?
NEWPIN="$(cat "$STAGED3/agent-browser-cli.pin" | tr -d '[:space:]')"
if [ "$RC3A" -eq 0 ] && [ "$NEWPIN" = "0.31.2" ] && grep -q "0.31.2" "$STAGED3/CLI-VERSION-PIN.md" && grep -q "test bump" "$STAGED3/CLI-VERSION-PIN.md"; then
  pass "bump updates the .pin file AND appends a dated bump-log row to CLI-VERSION-PIN.md"
else
  fail "expected a clean bump to 0.31.2 with a bump-log row; rc=$RC3A, pin='$NEWPIN', output: $OUT3A"
fi
OUT3B="$(bash "$STAGED3/scripts/bump-agent-browser-cli-pin.sh" --check 2>&1)"
RC3B=$?
if [ "$RC3B" -eq 0 ] && echo "$OUT3B" | grep -q "0.31.2"; then
  pass "--check PASSES immediately after a bump (pin/doc back in agreement at the new version)"
else
  fail "expected --check to PASS after the bump; rc=$RC3B, output: $OUT3B"
fi

# ── (4) qc-agent-browser.sh CLI version-pin section, via stub CLI ───────────
build_stub_agent_browser_versioned() {
  # $1=bin-dir $2=version-string-to-report
  local bin_dir="$1" ver="$2"
  mkdir -p "$bin_dir"
  cat > "$bin_dir/agent-browser" <<STUBEOF
#!/usr/bin/env bash
case "\$1" in
  --version) echo "agent-browser $ver"; exit 0 ;;
  --help) echo "agent-browser usage help"; exit 0 ;;
  *) exit 0 ;;
esac
STUBEOF
  chmod +x "$bin_dir/agent-browser"
}

# 4a: stub reports the PINNED version (0.27.0 in the shipped repo) -> PASS
HOME4A="$WORK/home-qc-match"
STAGED4A="$(stage_install "$HOME4A")"
BIN4A="$WORK/bin-match"
build_stub_agent_browser_versioned "$BIN4A" "0.27.0"
OUT4A="$(HOME="$HOME4A" PATH="$BIN4A:$PATH" bash "$STAGED4A/qc-agent-browser.sh" 2>&1 || true)"
if echo "$OUT4A" | grep -qE "PASS.*CLI version.*0\.27\.0|matches the pinned CLI version"; then
  pass "qc-agent-browser.sh: installed CLI version matches the pin -> PASSES the CLI-pin section"
else
  fail "qc-agent-browser.sh: expected a CLI-version-pin PASS line; output: $OUT4A"
fi

# 4b: FAIL-FIRST: stub reports a DIFFERENT version -> FAIL naming both versions
HOME4B="$WORK/home-qc-mismatch"
STAGED4B="$(stage_install "$HOME4B")"
BIN4B="$WORK/bin-mismatch"
build_stub_agent_browser_versioned "$BIN4B" "0.99.9"
OUT4B="$(HOME="$HOME4B" PATH="$BIN4B:$PATH" bash "$STAGED4B/qc-agent-browser.sh" 2>&1 || true)"
if echo "$OUT4B" | grep -q "FAIL" && echo "$OUT4B" | grep -q "0.27.0" && echo "$OUT4B" | grep -q "0.99.9"; then
  pass "qc-agent-browser.sh: installed CLI version (0.99.9) mismatches the pin (0.27.0) -> FAILS naming both"
else
  fail "qc-agent-browser.sh: expected a FAIL naming pinned 0.27.0 vs installed 0.99.9; output: $OUT4B"
fi

echo ""
echo "================================================="
echo "Results: $PASS passed, $FAIL failed"
echo "================================================="
if [ "$FAIL" -eq 0 ]; then
  echo "ALL TESTS PASSED"
  exit 0
else
  echo "TESTS FAILED"
  exit 1
fi
