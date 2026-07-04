#!/usr/bin/env bash
# selftest-telegram-chat-id-leak.sh — hermetic non-vacuity proof for
# scripts/qc-assert-no-telegram-chat-id-leak.sh
#
# Proves the shape gate actually BITES and does NOT false-positive, WITHOUT
# shipping any real client chat id. All planted positives use a clearly-fake
# 9-digit id (999999999) or the sanctioned placeholder (1234567890) — never a
# real id.
#
#   CASE A  planted session-key leak   "…telegram:direct:999999999"  -> FAIL (Part A)
#   CASE B  planted allowFrom leak      allowFrom ["…","999999999"]  -> FAIL (Part B)
#   CASE C  leak removed, placeholder + operator-guard only          -> PASS  (no FP)
#   CASE D  roster box-mode: 999999999 in a temp roster + repo       -> FAIL (Part C)
#
# Run:  bash tests/fixtures/telegram-chat-id-leak/selftest-telegram-chat-id-leak.sh
# Exit: 0 = selftest passed; 1 = selftest failed.
set -uo pipefail

FAKE_ID="999999999"          # clearly fake, NOT a real client id
PLACEHOLDER="1234567890"     # sanctioned placeholder
OPERATOR="5252140759"        # a real operator id (non-client, legitimately allowed)

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
GATE="$REPO_ROOT/scripts/qc-assert-no-telegram-chat-id-leak.sh"

fail() { echo "  [SELFTEST FAIL] $1" >&2; exit 1; }
[ -f "$GATE" ] || fail "gate not found at $GATE"

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
REPO="$TMP/repo"; mkdir -p "$REPO"

run_gate() { unset OPENCLAW_CLIENT_ROSTER; bash "$GATE" --repo-root "$REPO" >"$TMP/out" 2>&1; }

# ── CASE A: session-key leak must FAIL and name the id ────────────────────────
printf '{\n  "agent:main:telegram:direct:%s": { "systemSent": true }\n}\n' "$FAKE_ID" \
  > "$REPO/sessions.json"
run_gate; rc=$?
[ "$rc" -ne 0 ] || { cat "$TMP/out" >&2; fail "A: gate PASSED on a planted session-key leak"; }
grep -q "$FAKE_ID" "$TMP/out" || { cat "$TMP/out" >&2; fail "A: failure did not name the leaked id"; }
echo "  [ok] A: session-key leak detected and named (exit $rc)"

# ── CASE B: allowFrom leak must FAIL (Part B) ─────────────────────────────────
rm -f "$REPO/sessions.json"
printf 'telegram:\n  allowFrom: ["%s", "%s"]\n' "$OPERATOR" "$FAKE_ID" > "$REPO/config.yaml"
run_gate; rc=$?
[ "$rc" -ne 0 ] || { cat "$TMP/out" >&2; fail "B: gate PASSED on a planted allowFrom leak"; }
echo "  [ok] B: telegram-context allowFrom leak detected (exit $rc)"

# ── CASE C: clean (placeholder + operator-guard only) must PASS (no FP) ───────
rm -f "$REPO/config.yaml"
cat > "$REPO/clean.sh" <<EOF
OPERATOR_CHAT_IDS_RE='^(5252140759|6663821679|6771245262)\$'
allowFrom: ["$PLACEHOLDER"]
"agent:main:telegram:direct:$PLACEHOLDER"
groupAllowFrom does NOT contain 5252140759, 6663821679, or 6771245262
EOF
run_gate; rc=$?
[ "$rc" -eq 0 ] || { cat "$TMP/out" >&2; fail "C: gate FAILED on placeholder + operator-guard content (false positive)"; }
echo "  [ok] C: no false positive on placeholder + operator-guard code (exit $rc)"

# ── CASE D: roster box-mode denylist must FAIL on a rostered id ───────────────
ROSTER="$TMP/roster.txt"; printf '# fake roster\n%s\n' "$FAKE_ID" > "$ROSTER"
printf 'ownerChatId: %s\n' "$FAKE_ID" > "$REPO/box.json"
OPENCLAW_CLIENT_ROSTER="$ROSTER" bash "$GATE" --repo-root "$REPO" >"$TMP/out" 2>&1; rc=$?
[ "$rc" -ne 0 ] || { cat "$TMP/out" >&2; fail "D: gate PASSED in roster box-mode on a rostered client id"; }
grep -q "roster" "$TMP/out" || { cat "$TMP/out" >&2; fail "D: roster denylist did not fire"; }
echo "  [ok] D: roster box-mode denylist bit on a rostered client id (exit $rc)"

echo "[selftest-telegram-chat-id-leak] PASS — gate bites (session-key + telegram-context + roster) and does not false-positive."
exit 0
