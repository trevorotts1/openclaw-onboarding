#!/usr/bin/env bash
# tests/unit/roll-escalation-held.test.sh
# -----------------------------------------------------------------------------
# Big Fleet Roll 2026-10, open item 10. During a fleet roll the job's own operator
# escalation (OPERATOR_ESCALATION_CHAT_ID) can land in the Rescue Rangers Telegram
# group and wake a paid agent. Trevor's rule: the roll's watcher steps in and fixes
# a broken box; Rescue Rangers is not involved.
#
# update-skills.sh send_telegram_progress is the one sender in the roll's process
# tree. Under a roll (scripts/self-update.sh exports SELF_UPDATE_ROLL_ID and
# SELF_UPDATE_RUN_ID ap-*) it must send NOTHING and instead hold the note in
# SELF_UPDATE_ESCALATION_FILE, which self-update.sh surfaces in the status file.
#
# Proves, non-vacuously (the first case proves the send DOES fire):
#   (1) no roll env + operator chat configured -> `openclaw message send` is invoked
#       once, to the operator chat on the operator account
#   (2) SELF_UPDATE_ROLL_ID set -> ZERO sends, result held-for-roll-watcher, the
#       note is in SELF_UPDATE_ESCALATION_FILE (mode 600) and in the log
#   (3) only SELF_UPDATE_RUN_ID=ap-* set (no roll id) -> ZERO sends
#   (4) a RUN_ID that is not ap-* and no roll id -> sends (the hold is not blanket)
#   (5) held with no SELF_UPDATE_ESCALATION_FILE -> still ZERO sends, no crash
#
# Hermetic: sandbox HOME, stubbed `openclaw`, no real Telegram. The function under
# test is extracted from the real update-skills.sh. bash 3.2 safe.
# Sanctioned placeholder id (NOT real): operator=6663821679.
# -----------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPDATE_SKILLS="${UPDATE_SKILLS_SRC:-$REPO_ROOT/update-skills.sh}"
OPERATOR_ID="6663821679"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

T="$(mktemp -d "${TMPDIR:-/tmp}/roll-escalation-held.XXXXXX")" || exit 1
trap 'rm -rf "$T"' EXIT

# Extract the two functions exactly as shipped.
awk '/^_oc_under_roll\(\) \{/,/^}/' "$UPDATE_SKILLS" > "$T/fn.sh"
awk '/^send_telegram_progress\(\) \{/,/^}/' "$UPDATE_SKILLS" >> "$T/fn.sh"
if ! grep -q '^_oc_under_roll()' "$T/fn.sh" || ! grep -q '^send_telegram_progress()' "$T/fn.sh"; then
  echo "FAIL: could not extract _oc_under_roll / send_telegram_progress from $UPDATE_SKILLS"; exit 1
fi

mkdir -p "$T/bin"
cat > "$T/bin/openclaw" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$SEND_LOG"
exit 0
EOF
chmod 700 "$T/bin/openclaw"

# drive <name> [VAR=value ...]  -> sets SEND_LOG, LOGF, RESULT for the case
drive() {
  local name="$1"; shift
  local H="$T/$name/home"
  mkdir -p "$H/.openclaw"
  printf '{"env":{"vars":{"OPERATOR_ESCALATION_CHAT_ID":"%s"}}}\n' "$OPERATOR_ID" > "$H/.openclaw/openclaw.json"
  SEND_LOG="$T/$name/sends.log"; LOGF="$T/$name/update.log"
  : > "$SEND_LOG"; : > "$LOGF"
  RESULT="$(
    env -i PATH="$T/bin:/usr/bin:/bin" HOME="$H" SEND_LOG="$SEND_LOG" LOG_FILE="$LOGF" "$@" \
      bash -c '. "$0"; send_telegram_progress "HEADLINE verified-installed
second line of the note"; printf "%s" "$TELEGRAM_LAST_RESULT"' "$T/fn.sh" 2>/dev/null
  )"
}
sends() { grep -c 'message send' "$SEND_LOG" 2>/dev/null || true; }

echo "=== roll-escalation-held.test.sh ==="

# (1) control: outside a roll the send fires, to the operator chat
drive plain
if [ "$(sends)" = 1 ] && grep -q -- "--target $OPERATOR_ID" "$SEND_LOG" && grep -q -- '--account operator' "$SEND_LOG" \
   && [ "$RESULT" = "sent-operator:$OPERATOR_ID" ]; then
  pass "(1) outside a roll the operator note is sent once to the operator chat (control: the send path works)"
else
  fail "(1) control send did not fire as expected (sends=$(sends) result=$RESULT)"
fi

# (2) roll id set -> held, nothing sent
HELD="$T/roll/held.txt"; mkdir -p "$T/roll"
drive roll SELF_UPDATE_ROLL_ID=roll-1 SELF_UPDATE_RUN_ID=ap-roll-1-1-2 SELF_UPDATE_ESCALATION_FILE="$HELD"
[ "$(sends)" = 0 ] && pass "(2) under a roll: ZERO sends" || fail "(2) a send fired under a roll ($(sends))"
[ "$RESULT" = held-for-roll-watcher ] && pass "(2) result is held-for-roll-watcher" || fail "(2) result '$RESULT'"
if [ -f "$HELD" ] && [ "$(head -n1 "$HELD")" = "HEADLINE verified-installed" ] && grep -q 'second line of the note' "$HELD"; then
  pass "(2) the whole note is in SELF_UPDATE_ESCALATION_FILE, headline first"
else
  fail "(2) held file missing or wrong"
fi
case "$(ls -l "$HELD" 2>/dev/null | cut -c1-10)" in -rw-------) pass "(2) held file is mode 600" ;; *) fail "(2) held file mode: $(ls -l "$HELD" 2>/dev/null | cut -c1-10)" ;; esac
grep -q 'HELD under roll roll-1' "$LOGF" && pass "(2) the log says the note was held under that roll" || fail "(2) no HELD line in the log"

# (3) run id alone (ap-*) is enough
HELD="$T/runid/held.txt"; mkdir -p "$T/runid"
drive runid SELF_UPDATE_RUN_ID=ap--1-2 SELF_UPDATE_ESCALATION_FILE="$HELD"
[ -s "$HELD" ] && pass "(3) the note was written to the escalation file" || fail "(3) no held file"
[ "$(sends)" = 0 ] && [ "$RESULT" = held-for-roll-watcher ] && pass "(3) RUN_ID ap-* alone holds the note" \
  || fail "(3) ap-* run id alone did not hold (sends=$(sends) result=$RESULT)"

# (4) a non-roll run id does not hold
drive other SELF_UPDATE_RUN_ID=manual-123
[ "$(sends)" = 1 ] && pass "(4) a RUN_ID that is not ap-* is not held" || fail "(4) non-ap run id was held (sends=$(sends))"

# (5) held with no file to write: still no send, no crash
drive nofile SELF_UPDATE_ROLL_ID=roll-2
[ "$(sends)" = 0 ] && [ "$RESULT" = held-for-roll-watcher ] && pass "(5) held without an escalation file: zero sends, no crash" \
  || fail "(5) no-file case: sends=$(sends) result=$RESULT"

# static: the pre-existing contract strings survive (tests/unit/cron-owner-chat-guard.test.sh 6c)
awk '/^send_telegram_progress\(\) \{/,/^}/' "$UPDATE_SKILLS" | grep -qE 'OPERATOR_ESCALATION_CHAT_ID' \
  && pass "static: send_telegram_progress still resolves the operator chat outside a roll" \
  || fail "static: send_telegram_progress lost the operator-chat resolver"

echo ""
echo "Passed: $PASS  Failed: $FAIL"
[ "$FAIL" -eq 0 ] && { echo "PASS: roll escalation held"; exit 0; }
echo "FAIL: roll escalation held"; exit 1
