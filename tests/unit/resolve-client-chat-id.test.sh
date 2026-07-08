#!/usr/bin/env bash
# tests/unit/resolve-client-chat-id.test.sh — contract test for the fleet
# client-chat-id resolver (shared-utils/resolve-client-chat-id.sh).
#
# Proves the output contract that keeps a Telegram send from ever falling back to
# a phone number:
#   - a confident, VALID match prints ONLY the numeric chat_id to stdout, exit 0;
#   - every miss prints NOTHING to stdout and exits non-zero, with a distinct code
#     (1 not-found/unconfirmed, 2 ambiguous, 3 roster-missing, 4 usage).
#
# Fully hermetic: points the resolver at a SYNTHETIC fixture roster
# (tests/fixtures/resolve-client-chat-id/roster.json) via OPENCLAW_FLEET_ROSTER.
# The fixture holds ONLY the sanctioned placeholder id 1234567890 and synthetic
# client names — no real client data.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/shared-utils/resolve-client-chat-id.sh"
FIXTURE="$REPO_ROOT/tests/fixtures/resolve-client-chat-id/roster.json"
PLACEHOLDER="1234567890"

[ -f "$SCRIPT" ]  || { echo "FAIL: resolver not found: $SCRIPT"; exit 1; }
[ -f "$FIXTURE" ] || { echo "FAIL: fixture not found: $FIXTURE"; exit 1; }

echo "=== resolve-client-chat-id.test.sh ==="

PASS=0; FAIL=0
ok(){  printf "  PASS: %s\n" "$1"; PASS=$((PASS+1)); }
bad(){ printf "  FAIL: %s\n" "$1"; FAIL=$((FAIL+1)); }

# Run the resolver against the fixture; capture stdout + exit code separately.
# stderr is discarded (diagnostics only). Usage: run "<arg>"  (omit arg for no-arg).
OUT=""; RC=0
run() {
  if [ "$#" -eq 0 ]; then
    OUT="$(OPENCLAW_FLEET_ROSTER="$FIXTURE" bash "$SCRIPT" 2>/dev/null)"; RC=$?
  else
    OUT="$(OPENCLAW_FLEET_ROSTER="$FIXTURE" bash "$SCRIPT" "$1" 2>/dev/null)"; RC=$?
  fi
}

# 1. Known synthetic name resolves to the placeholder id, exit 0.
run "Wibble Widgets"
if [ "$RC" -eq 0 ] && [ "$OUT" = "$PLACEHOLDER" ]; then
  ok "known name 'Wibble Widgets' -> $PLACEHOLDER (exit 0)"
else
  bad "known name: rc=$RC out='$OUT' (want rc=0 out=$PLACEHOLDER)"
fi

# 1b. Match is case-insensitive.
run "wibble widgets"
if [ "$RC" -eq 0 ] && [ "$OUT" = "$PLACEHOLDER" ]; then
  ok "case-insensitive 'wibble widgets' -> $PLACEHOLDER (exit 0)"
else
  bad "case-insensitive: rc=$RC out='$OUT' (want rc=0 out=$PLACEHOLDER)"
fi

# 1c. A box-slug key also resolves.
run "zorp-sprocket"
if [ "$RC" -eq 0 ] && [ "$OUT" = "$PLACEHOLDER" ]; then
  ok "box-slug 'zorp-sprocket' -> $PLACEHOLDER (exit 0)"
else
  bad "box-slug: rc=$RC out='$OUT' (want rc=0 out=$PLACEHOLDER)"
fi

# 2. Unknown name -> empty stdout + non-zero exit (code 1).
run "Nonexistent Nobody Corp"
if [ "$RC" -ne 0 ] && [ -z "$OUT" ]; then
  ok "unknown name -> empty stdout + non-zero exit (rc=$RC)"
else
  bad "unknown name: rc=$RC out='$OUT' (want non-zero + empty stdout)"
fi
[ "$RC" -eq 1 ] && ok "unknown name exit code is 1 (not-found)" \
                 || bad "unknown name exit code is $RC (want 1)"

# 3. A chatId:"unconfirmed" entry is treated as NOT FOUND (empty + non-zero).
run "Foobar Unconfirmed Co"
if [ "$RC" -ne 0 ] && [ -z "$OUT" ]; then
  ok "'unconfirmed' chatId -> empty stdout + non-zero exit (rc=$RC)"
else
  bad "unconfirmed: rc=$RC out='$OUT' (want non-zero + empty stdout)"
fi
[ "$RC" -eq 1 ] && ok "unconfirmed exit code is 1 (matched-but-unconfirmed)" \
                 || bad "unconfirmed exit code is $RC (want 1)"

# 4. No argument -> usage error, non-zero exit (code 4), empty stdout.
run
if [ "$RC" -eq 4 ] && [ -z "$OUT" ]; then
  ok "no-arg -> usage error exit 4 + empty stdout"
else
  bad "no-arg: rc=$RC out='$OUT' (want rc=4 + empty stdout)"
fi

# 5. Ambiguous substring (matches two distinct clients) -> exit 2, empty stdout.
run "wibble"
if [ "$RC" -eq 2 ] && [ -z "$OUT" ]; then
  ok "ambiguous substring 'wibble' -> exit 2 + empty stdout"
else
  bad "ambiguous: rc=$RC out='$OUT' (want rc=2 + empty stdout)"
fi

# 6. Missing roster -> exit 3, empty stdout. Hermetic: an empty HOME so the
# $HOME/clawd/... default cannot exist, and an env override pointing at a file
# that does not exist, so all first-existing-wins candidates miss.
EMPTY_HOME="$(mktemp -d)"
trap 'rm -rf "$EMPTY_HOME"' EXIT
OUT="$(HOME="$EMPTY_HOME" \
       OPENCLAW_FLEET_ROSTER="$EMPTY_HOME/does-not-exist.json" \
        bash "$SCRIPT" "Wibble Widgets" 2>/dev/null)"; RC=$?
if [ "$RC" -eq 3 ] && [ -z "$OUT" ]; then
  ok "missing roster -> exit 3 + empty stdout"
else
  bad "missing roster: rc=$RC out='$OUT' (want rc=3 + empty stdout)"
fi

echo ""
echo "=== resolve-client-chat-id: $PASS passed | $FAIL failed ==="
[ "$FAIL" -gt 0 ] && exit 1 || exit 0
