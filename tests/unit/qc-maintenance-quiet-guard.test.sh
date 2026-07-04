#!/usr/bin/env bash
# tests/unit/qc-maintenance-quiet-guard.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# SILENT-MAINTENANCE guard regression lock (v17.0.18).
#
# THE BUG THIS LOCKS: update-skills.sh runs qc-completeness.sh INLINE after every
# skill pull. On a box with an owner chat configured, qc-completeness.sh sent a
# "workforce QC status" Telegram to the CLIENT owner whenever STATUS != PASS —
# so a routine fleet ROLL messaged the client (2 clients were messaged during a
# v17.0.17 roll). The fix: a maintenance/quiet guard (OPENCLAW_MAINTENANCE=1, or
# --quiet/--no-telegram/--no-notify) SUPPRESSES the owner-chat send entirely
# (log-only), and update-skills.sh runs the embedded QC call with
# OPENCLAW_MAINTENANCE=1 so no roll can ever notify a client.
#
# WHAT THIS TEST PROVES (non-vacuously — it first proves the send DOES fire):
#   (1) WITHOUT the flag, the REAL qc-completeness.sh, driven end-to-end against a
#       fake non-PASS workforce with an owner chat configured, INVOKES the telegram
#       send (stub `openclaw` is called with `message send`). If it did not fire,
#       the whole test fails (the suppression assertions would be vacuous otherwise).
#   (2) WITH OPENCLAW_MAINTENANCE=1, the SAME drive invokes the send ZERO times and
#       logs "maintenance mode — owner alert suppressed".
#   (3) WITH --quiet, the send is likewise NOT invoked (flag path).
#   (4) STATIC: update-skills.sh wires the embedded QC call with OPENCLAW_MAINTENANCE=1.
#
# Fully hermetic: every drive runs under its OWN `mktemp -d` sandbox HOME with a
# stubbed `openclaw` — nothing is written under the operator's ~/.openclaw and no
# real Telegram is ever sent. bash 3.2-safe (macOS system bash). Exit 0 = all pass.
# ─────────────────────────────────────────────────────────────────────────────

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
QC_SH="$REPO_ROOT/23-ai-workforce-blueprint/scripts/qc-completeness.sh"
UPDATE_SKILLS="$REPO_ROOT/update-skills.sh"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== qc-maintenance-quiet-guard.test.sh (v17.0.18 silent-maintenance guard) ==="

[ -f "$QC_SH" ] || { echo "  FAIL: qc-completeness.sh not found at $QC_SH"; exit 1; }
[ -f "$UPDATE_SKILLS" ] || { echo "  FAIL: update-skills.sh not found at $UPDATE_SKILLS"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "  FAIL: python3 not on PATH"; exit 1; }

bash -n "$QC_SH" 2>/dev/null && pass "qc-completeness.sh parses (bash -n)" || fail "qc-completeness.sh bash -n FAILED"
bash -n "$UPDATE_SKILLS" 2>/dev/null && pass "update-skills.sh parses (bash -n)" || fail "update-skills.sh bash -n FAILED"

# ── (4) STATIC — the embedded QC call in the updater runs in maintenance mode ──
if grep -qE 'OPENCLAW_MAINTENANCE=1[[:space:]]+bash[[:space:]]+"\$QC_COMPLETENESS_SCRIPT"' "$UPDATE_SKILLS"; then
  pass "update-skills.sh runs embedded qc-completeness.sh with OPENCLAW_MAINTENANCE=1"
else
  fail "update-skills.sh does NOT wire OPENCLAW_MAINTENANCE=1 on the embedded QC call"
fi

# ── Hermetic end-to-end driver of the REAL qc-completeness.sh ─────────────────
# Builds a fake mac-layout workforce (one dept, zero roles => STATUS FAIL => the
# owner-chat send path is reached), configures an owner chat (sanctioned
# placeholder id 1234567890), stubs `openclaw` to LOG its argv instead of sending,
# then runs the real script. Sets $SBX (sandbox) + $CALLLOG (stub call log) +
# $OUTLOG (script stdout/stderr) as globals for the caller to inspect.
# Populate a sandbox fixture (fake workforce + owner chat + stubbed openclaw).
# Sets $SBX/$CALLLOG/$OUTLOG globals. NOTE: env-vars are applied as LITERAL inline
# assignments at each run site below (a variable that EXPANDS to "VAR=val" is NOT
# recognised as an assignment prefix by the shell), so the mode is branched
# explicitly rather than interpolated.
setup_fixture() {
  SBX="$(mktemp -d)"
  CALLLOG="$SBX/openclaw-calls.log"
  OUTLOG="$SBX/qc-out.log"
  : > "$CALLLOG"

  # Fake workforce: mac layout, one department with NO role folders => FAIL.
  mkdir -p "$SBX/.openclaw/workspace/zero-human-company/testco/departments/sales"
  mkdir -p "$SBX/.openclaw/logs"

  # Owner chat configured so _qc_owner_chat.py resolves a non-empty target.
  # 1234567890 is the SANCTIONED placeholder (not a real client id).
  printf '%s\n' '{ "channels": { "telegram": { "allowFrom": ["1234567890"] } } }' \
    > "$SBX/.openclaw/openclaw.json"

  # Stub `openclaw`: record argv, simulate a successful send.
  mkdir -p "$SBX/bin"
  cat > "$SBX/bin/openclaw" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$CALLLOG"
exit 0
STUB
  chmod +x "$SBX/bin/openclaw"
}

# ── (1) NON-VACUITY: without the flag, the send MUST fire ─────────────────────
# Drive the REAL script, fully sandboxed. HOME override keeps every read/write
# inside $SBX; PATH keeps python3 resolvable while shadowing `openclaw` with the
# stub. OPENCLAW_BIN points the send at the stub deterministically.
setup_fixture
HOME="$SBX" OPENCLAW_PLATFORM=mac QC_SKIP_PRESENTATION_DEPS=1 \
  OPENCLAW_BIN="$SBX/bin/openclaw" PATH="$SBX/bin:$PATH" \
  bash "$QC_SH" > "$OUTLOG" 2>&1
if grep -q "message send" "$CALLLOG"; then
  pass "baseline (no maintenance): owner-chat telegram send IS invoked (harness reaches the send path)"
else
  fail "baseline (no maintenance): send was NOT invoked — harness did not reach the send path (later assertions would be vacuous). See $OUTLOG"
fi
BASELINE_SBX="$SBX"

# ── (2) OPENCLAW_MAINTENANCE=1 SUPPRESSES the send ────────────────────────────
setup_fixture
HOME="$SBX" OPENCLAW_PLATFORM=mac QC_SKIP_PRESENTATION_DEPS=1 \
  OPENCLAW_BIN="$SBX/bin/openclaw" PATH="$SBX/bin:$PATH" OPENCLAW_MAINTENANCE=1 \
  bash "$QC_SH" > "$OUTLOG" 2>&1
if [ -s "$CALLLOG" ]; then
  echo "    (unexpected stub calls:)"; sed 's/^/      /' "$CALLLOG"
  fail "OPENCLAW_MAINTENANCE=1: owner-chat send was INVOKED (should be suppressed)"
else
  pass "OPENCLAW_MAINTENANCE=1: owner-chat send invoked ZERO times (suppressed)"
fi
# ASCII substring (avoids locale-fragile em-dash matching); the maintenance
# variant of the note carries the "(OPENCLAW_MAINTENANCE=1)" marker.
if grep -q "owner alert suppressed (OPENCLAW_MAINTENANCE=1)" "$OUTLOG"; then
  pass "OPENCLAW_MAINTENANCE=1: logs the 'owner alert suppressed (OPENCLAW_MAINTENANCE=1)' note"
else
  fail "OPENCLAW_MAINTENANCE=1: suppression log line missing. See $OUTLOG"
fi
MAINT_SBX="$SBX"

# ── (3) --quiet flag also suppresses the send ─────────────────────────────────
# (--quiet is passed as a script ARG — the positional flag path.)
setup_fixture
HOME="$SBX" OPENCLAW_PLATFORM=mac QC_SKIP_PRESENTATION_DEPS=1 \
  OPENCLAW_BIN="$SBX/bin/openclaw" PATH="$SBX/bin:$PATH" \
  bash "$QC_SH" --quiet > "$OUTLOG" 2>&1
if [ -s "$CALLLOG" ]; then
  fail "--quiet: owner-chat send was INVOKED (should be suppressed)"
else
  pass "--quiet: owner-chat send invoked ZERO times (flag path suppressed)"
fi
QUIET_SBX="$SBX"

# ── Cleanup ───────────────────────────────────────────────────────────────────
rm -rf "$BASELINE_SBX" "$MAINT_SBX" "$QUIET_SBX" 2>/dev/null || true

echo ""
echo "  Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
echo "=== qc-maintenance-quiet-guard.test.sh: ALL PASS ==="
exit 0
