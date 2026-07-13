#!/usr/bin/env bash
# tests/unit/qc-maintenance-quiet-guard.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# SILENT-MAINTENANCE guard regression lock (v17.0.18; hardened v20.0.9).
#
# THE BUG THIS LOCKS: update-skills.sh runs qc-completeness.sh INLINE after every
# skill pull. qc-completeness.sh resolved channels.telegram.allowFrom[0] — the
# CLIENT's own chat — and sent it a "workforce QC status" Telegram whenever
# STATUS != PASS, so a routine fleet ROLL messaged the client (a real client,
# teresa-pelham, was messaged during a v17.0.17-class roll).
#
# THE v20.0.9 FIX (defense in depth):
#   • qc-completeness.sh no longer resolves allowFrom[0]. Its != PASS alert now
#     routes to the OPERATOR escalation chat ONLY (OPERATOR_ESCALATION_CHAT_ID, on
#     the operator account), and is LOG-ONLY when no operator chat is configured —
#     it NEVER messages the client owner.
#   • A HARD maintenance-silence gate OPENCLAW_MAINTENANCE_SILENT=1 suppresses the
#     send entirely, INDEPENDENT of --quiet and of any box's chat/account config.
#     The fleet roll exports it for the whole run (update-skills.sh main() +
#     shared-utils/fleet_refresh_runner.py), so no convergence re-run can leak the
#     QC table even on a box whose operator chat is mis-pointed at the client.
#   • The two roll callers ALSO pass --quiet (belt-and-suspenders).
#
# WHAT THIS TEST PROVES (non-vacuously — it first proves the send DOES fire):
#   (1)  WITH an OPERATOR chat configured and no suppression, the REAL
#        qc-completeness.sh, driven end-to-end against a fake non-PASS workforce,
#        INVOKES the telegram send to the OPERATOR chat on the operator account —
#        and NOT to the client owner (allowFrom[0]) that is ALSO present in config.
#   (1b) WITHOUT an operator chat (owner-only config), the SAME drive sends ZERO
#        times (LOG-ONLY) — it NEVER falls back to the client owner chat.
#   (2)  WITH OPENCLAW_MAINTENANCE=1, the send is invoked ZERO times and the
#        "owner alert suppressed (OPENCLAW_MAINTENANCE=1)" note is logged.
#   (2b) WITH OPENCLAW_MAINTENANCE_SILENT=1 (the hard roll-wide gate, --quiet NOT
#        passed), the send is invoked ZERO times and the maintenance-silent note is
#        logged.
#   (3)  WITH --quiet, the send is likewise NOT invoked (flag path).
#   (4)  STATIC: update-skills.sh wires the embedded QC call with OPENCLAW_MAINTENANCE=1.
#   (5)  STATIC: update-skills.sh main() exports OPENCLAW_MAINTENANCE_SILENT=1 for
#        the whole roll (so migrate + the embedded QC subprocess both inherit it).
#
# Fully hermetic: every drive runs under its OWN `mktemp -d` sandbox HOME with a
# stubbed `openclaw` — nothing is written under the operator's ~/.openclaw and no
# real Telegram is ever sent. bash 3.2-safe (macOS system bash). Exit 0 = all pass.
#
# Sanctioned placeholder ids (NOT real): owner=1234567890, operator=6663821679.
# ─────────────────────────────────────────────────────────────────────────────

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
QC_SH="$REPO_ROOT/23-ai-workforce-blueprint/scripts/qc-completeness.sh"
UPDATE_SKILLS="$REPO_ROOT/update-skills.sh"

OWNER_ID="1234567890"      # sanctioned placeholder — the CLIENT owner chat
OPERATOR_ID="6663821679"   # sanctioned placeholder — the OPERATOR escalation chat

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== qc-maintenance-quiet-guard.test.sh (v20.0.9 silent-maintenance + operator-only routing) ==="

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

# ── (5) STATIC — the roll exports the hard maintenance-silence gate ───────────
if grep -qE '^[[:space:]]*export[[:space:]]+OPENCLAW_MAINTENANCE_SILENT=1' "$UPDATE_SKILLS"; then
  pass "update-skills.sh main() exports OPENCLAW_MAINTENANCE_SILENT=1 for the whole roll"
else
  fail "update-skills.sh does NOT export OPENCLAW_MAINTENANCE_SILENT=1 (roll-wide gate missing)"
fi

# ── Hermetic end-to-end driver of the REAL qc-completeness.sh ─────────────────
# Builds a fake mac-layout workforce (one dept, zero roles => STATUS FAIL => the
# send path is reached), stubs `openclaw` to LOG its argv instead of sending, then
# runs the real script. setup_fixture <with_operator:1|0> controls whether the
# fixture openclaw.json carries an OPERATOR escalation chat. The client owner chat
# (allowFrom[0]) is ALWAYS present so we can prove the send NEVER goes to it.
# Sets $SBX (sandbox) + $CALLLOG (stub call log) + $OUTLOG (script stdout/stderr)
# as globals for the caller to inspect.
setup_fixture() {
  local with_operator="${1:-1}"
  SBX="$(mktemp -d)"
  CALLLOG="$SBX/openclaw-calls.log"
  OUTLOG="$SBX/qc-out.log"
  : > "$CALLLOG"

  # Fake workforce: mac layout, one department with NO role folders => FAIL.
  mkdir -p "$SBX/.openclaw/workspace/zero-human-company/testco/departments/sales"
  mkdir -p "$SBX/.openclaw/logs"

  # openclaw.json: the CLIENT owner chat is ALWAYS present (allowFrom[0]); the
  # OPERATOR escalation chat is present only when with_operator=1.
  if [ "$with_operator" = "1" ]; then
    printf '%s\n' "{ \"channels\": { \"telegram\": { \"allowFrom\": [\"$OWNER_ID\"] } }, \"env\": { \"vars\": { \"OPERATOR_ESCALATION_CHAT_ID\": \"$OPERATOR_ID\" } } }" \
      > "$SBX/.openclaw/openclaw.json"
  else
    printf '%s\n' "{ \"channels\": { \"telegram\": { \"allowFrom\": [\"$OWNER_ID\"] } } }" \
      > "$SBX/.openclaw/openclaw.json"
  fi

  # Stub `openclaw`: record argv, simulate a successful send.
  mkdir -p "$SBX/bin"
  cat > "$SBX/bin/openclaw" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$CALLLOG"
exit 0
STUB
  chmod +x "$SBX/bin/openclaw"
}

# ── (1) NON-VACUITY: with an OPERATOR chat, the send fires TO THE OPERATOR ─────
# Drive the REAL script, fully sandboxed. HOME override keeps every read/write
# inside $SBX; PATH keeps python3 resolvable while shadowing `openclaw` with the
# stub. OPENCLAW_BIN points the send at the stub deterministically. We explicitly
# UNSET any inherited OPERATOR_ESCALATION_CHAT_ID so resolution comes from the
# fixture openclaw.json, not the CI environment.
setup_fixture 1
HOME="$SBX" OPENCLAW_PLATFORM=mac QC_SKIP_PRESENTATION_DEPS=1 \
  OPENCLAW_BIN="$SBX/bin/openclaw" PATH="$SBX/bin:$PATH" \
  OPERATOR_ESCALATION_CHAT_ID="" OPERATOR_HELP_CHAT_ID="" OPERATOR_TELEGRAM_CHAT_ID="" \
  bash "$QC_SH" > "$OUTLOG" 2>&1
if grep -q "message send" "$CALLLOG"; then
  pass "baseline (operator configured): telegram send IS invoked (harness reaches the send path)"
else
  fail "baseline (operator configured): send was NOT invoked — harness did not reach the send path (later assertions would be vacuous). See $OUTLOG"
fi
if grep -q -- "--account operator" "$CALLLOG" && grep -q "$OPERATOR_ID" "$CALLLOG"; then
  pass "baseline: send routes to the OPERATOR chat ($OPERATOR_ID) on the operator account"
else
  fail "baseline: send did NOT route to the operator account/chat. See $CALLLOG"
fi
if grep -q "$OWNER_ID" "$CALLLOG"; then
  echo "    (leak — owner id in stub calls:)"; sed 's/^/      /' "$CALLLOG"
  fail "baseline: send LEAKED to the client owner chat ($OWNER_ID) — regression"
else
  pass "baseline: send NEVER targets the client owner chat ($OWNER_ID)"
fi
BASELINE_SBX="$SBX"

# ── (1b) OWNER-ONLY config: send must NOT fire, and NEVER to the client ───────
setup_fixture 0
HOME="$SBX" OPENCLAW_PLATFORM=mac QC_SKIP_PRESENTATION_DEPS=1 \
  OPENCLAW_BIN="$SBX/bin/openclaw" PATH="$SBX/bin:$PATH" \
  OPERATOR_ESCALATION_CHAT_ID="" OPERATOR_HELP_CHAT_ID="" OPERATOR_TELEGRAM_CHAT_ID="" \
  bash "$QC_SH" > "$OUTLOG" 2>&1
if [ -s "$CALLLOG" ]; then
  echo "    (unexpected stub calls:)"; sed 's/^/      /' "$CALLLOG"
  fail "owner-only (no operator chat): a send was INVOKED (must be LOG-ONLY, never the client)"
else
  pass "owner-only (no operator chat): send invoked ZERO times (LOG-ONLY, never falls back to the client)"
fi
OWNERONLY_SBX="$SBX"

# ── (2) OPENCLAW_MAINTENANCE=1 SUPPRESSES the send ────────────────────────────
setup_fixture 1
HOME="$SBX" OPENCLAW_PLATFORM=mac QC_SKIP_PRESENTATION_DEPS=1 \
  OPENCLAW_BIN="$SBX/bin/openclaw" PATH="$SBX/bin:$PATH" OPENCLAW_MAINTENANCE=1 \
  OPERATOR_ESCALATION_CHAT_ID="" OPERATOR_HELP_CHAT_ID="" OPERATOR_TELEGRAM_CHAT_ID="" \
  bash "$QC_SH" > "$OUTLOG" 2>&1
if [ -s "$CALLLOG" ]; then
  echo "    (unexpected stub calls:)"; sed 's/^/      /' "$CALLLOG"
  fail "OPENCLAW_MAINTENANCE=1: send was INVOKED (should be suppressed)"
else
  pass "OPENCLAW_MAINTENANCE=1: send invoked ZERO times (suppressed)"
fi
# ASCII substring (avoids locale-fragile em-dash matching).
if grep -q "owner alert suppressed (OPENCLAW_MAINTENANCE=1)" "$OUTLOG"; then
  pass "OPENCLAW_MAINTENANCE=1: logs the 'owner alert suppressed (OPENCLAW_MAINTENANCE=1)' note"
else
  fail "OPENCLAW_MAINTENANCE=1: suppression log line missing. See $OUTLOG"
fi
MAINT_SBX="$SBX"

# ── (2b) OPENCLAW_MAINTENANCE_SILENT=1 SUPPRESSES the send (hard roll-wide gate) ──
# --quiet is NOT passed here, so this proves the gate is INDEPENDENT of --quiet.
setup_fixture 1
HOME="$SBX" OPENCLAW_PLATFORM=mac QC_SKIP_PRESENTATION_DEPS=1 \
  OPENCLAW_BIN="$SBX/bin/openclaw" PATH="$SBX/bin:$PATH" OPENCLAW_MAINTENANCE_SILENT=1 \
  OPERATOR_ESCALATION_CHAT_ID="" OPERATOR_HELP_CHAT_ID="" OPERATOR_TELEGRAM_CHAT_ID="" \
  bash "$QC_SH" > "$OUTLOG" 2>&1
if [ -s "$CALLLOG" ]; then
  echo "    (unexpected stub calls:)"; sed 's/^/      /' "$CALLLOG"
  fail "OPENCLAW_MAINTENANCE_SILENT=1: send was INVOKED (hard gate should suppress it)"
else
  pass "OPENCLAW_MAINTENANCE_SILENT=1: send invoked ZERO times (hard gate suppresses, independent of --quiet)"
fi
# ASCII substring (avoids locale-fragile em-dash matching).
if grep -q "QC alert suppressed (OPENCLAW_MAINTENANCE_SILENT=1)" "$OUTLOG"; then
  pass "OPENCLAW_MAINTENANCE_SILENT=1: logs the maintenance-silent suppression note"
else
  fail "OPENCLAW_MAINTENANCE_SILENT=1: maintenance-silent log line missing. See $OUTLOG"
fi
MAINTSILENT_SBX="$SBX"

# ── (3) --quiet flag also suppresses the send ─────────────────────────────────
# (--quiet is passed as a script ARG — the positional flag path.)
setup_fixture 1
HOME="$SBX" OPENCLAW_PLATFORM=mac QC_SKIP_PRESENTATION_DEPS=1 \
  OPENCLAW_BIN="$SBX/bin/openclaw" PATH="$SBX/bin:$PATH" \
  OPERATOR_ESCALATION_CHAT_ID="" OPERATOR_HELP_CHAT_ID="" OPERATOR_TELEGRAM_CHAT_ID="" \
  bash "$QC_SH" --quiet > "$OUTLOG" 2>&1
if [ -s "$CALLLOG" ]; then
  fail "--quiet: send was INVOKED (should be suppressed)"
else
  pass "--quiet: send invoked ZERO times (flag path suppressed)"
fi
QUIET_SBX="$SBX"

# ── Cleanup ───────────────────────────────────────────────────────────────────
rm -rf "$BASELINE_SBX" "$OWNERONLY_SBX" "$MAINT_SBX" "$MAINTSILENT_SBX" "$QUIET_SBX" 2>/dev/null || true

echo ""
echo "  Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
echo "=== qc-maintenance-quiet-guard.test.sh: ALL PASS ==="
exit 0
