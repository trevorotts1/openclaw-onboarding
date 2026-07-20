#!/usr/bin/env bash
# tests/unit/podbean-publish-provision-roll.test.sh
#
# S58-U18 — sandboxed end-to-end proof of the fleet provision roll
# (scripts/fleet-roll/podbean-publish-provision-roll.sh) against a throwaway
# home root (P18_HOME + per-entry "home" override — the script's documented
# sandbox mechanism). No SSH, no docker, no network (--no-standing-probe), and
# no writes anywhere outside the mktemp sandbox. The real operator store is
# never read: P18_HOME redirects the token lookup into the sandbox too.
#
# Proves, against the REAL script:
#   1. manifest rows with EMPTY optional fields (home ordering quirk aside:
#      first_name, podcast_id, container, compose_dir) parse without column
#      shift — the recovered original used tab-delimited rows and IFS=tab,
#      which collapses consecutive tabs and blocked every production entry.
#   2. --apply writes BOTH stores (env + ocjson) and grades OK, changed=yes.
#   3. re-apply is an exact no-op: OK_ALREADY, changed=no, secrets/.env
#      byte-identical (hash-compared).
#   4. incomplete roster identity is BLOCKED fail-closed in --apply (exit 2).
#   5. --apply --local selecting more than one box is REFUSED up front (the
#      unguarded original would have written every identity onto THIS box).
#   6. an unparseable openclaw.json FAILS the box and is NOT rebuilt/clobbered
#      (the original fell back to d={} and would have destroyed the config).
#   7. the secret token value never appears on stdout or in the ledger.
#   8. --no-restart on a changed box grades PARTIAL, never a clean OK.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ROLL="$REPO_ROOT/scripts/fleet-roll/podbean-publish-provision-roll.sh"

PASS=0
FAIL=0
pass() { printf '  PASS: %s\n' "$1"; PASS=$((PASS + 1)); }
fail() { printf '  FAIL: %s\n' "$1"; FAIL=$((FAIL + 1)); }

echo "=== podbean-publish-provision-roll.test.sh ==="

[ -f "$ROLL" ] || { echo "FAIL: roll script not found at $ROLL"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

SB="$WORK/home"
mkdir -p "$SB/.openclaw/secrets"
TOKEN="sandbox-token-Zq7vK9-never-real"
printf 'PODBEAN_PUBLISH_TOKEN=%s\n' "$TOKEN" > "$SB/.openclaw/secrets/.env"
chmod 600 "$SB/.openclaw/secrets/.env"
printf '{}\n' > "$SB/.openclaw/openclaw.json"

MANIFEST="$WORK/manifest.json"
cat > "$MANIFEST" <<EOF
[
  {"name": "sandbox-op", "role": "operator", "platform": "mac",
   "ssh_target": "local", "home": "$SB",
   "identity": {"last_name": "Sandbox", "email": "sandbox@example.test",
                "first_name": "", "podcast_id": "", "complete": true}},
  {"name": "sandbox-client-incomplete", "role": "client", "platform": "mac",
   "ssh_target": "local", "home": "$SB",
   "identity": {"last_name": "", "email": "", "first_name": "",
                "podcast_id": "", "complete": false}}
]
EOF

LOG="$WORK/ledger.log"
run_roll() { P18_HOME="$SB" bash "$ROLL" --boxes-file "$MANIFEST" --log-file "$LOG" "$@" 2>&1; }

# --- 1. dry-run survey: empty optional fields must not shift columns ---------
OUT="$(run_roll)"; RC=$?
if [ "$RC" = "0" ]; then pass "dry-run exits 0"; else fail "dry-run exit=$RC"; echo "$OUT"; fi
if printf '%s\n' "$OUT" | grep -q '\[sandbox-op\] probe:PODBEAN_PUBLISH_TOKEN:env=SET'; then
  pass "probe parsed the operator row (empty first_name/podcast_id did not shift columns)"
else
  fail "operator probe line missing — manifest column shift?"; echo "$OUT"
fi
if printf '%s\n' "$OUT" | grep -q 'box=sandbox-op .*verdict=OK'; then
  pass "operator row graded OK in dry-run"
else
  fail "operator row not OK in dry-run"
fi
if printf '%s\n' "$OUT" | grep -q 'box=sandbox-client-incomplete .*verdict=BLOCKED_IDENTITY_INCOMPLETE'; then
  pass "incomplete identity BLOCKED in dry-run survey"
else
  fail "incomplete identity not blocked in dry-run"
fi

# --- 2. apply writes both stores ---------------------------------------------
OUT="$(run_roll --apply --local --box sandbox-op --no-standing-probe)"; RC=$?
if [ "$RC" = "0" ]; then pass "apply exits 0"; else fail "apply exit=$RC"; echo "$OUT"; fi
for want in 'env:PODBEAN_PUBLISH_WEBHOOK_URL=WRITTEN' 'ocjson:PODBEAN_PUBLISH_WEBHOOK_URL=WRITTEN' \
            'env:PODCAST_CLIENT_LAST_NAME=WRITTEN' 'changed=yes' 'restart=skipped_sandbox_home' 'result=OK'; do
  if printf '%s\n' "$OUT" | grep -q "$want"; then pass "apply reports $want"; else fail "apply missing $want"; echo "$OUT"; fi
done
if [ -d "$SB/.openclaw/backups" ] && ls "$SB/.openclaw/backups"/s58-u18-*/secrets.env >/dev/null 2>&1; then
  pass "timestamped backup of secrets/.env taken before write"
else
  fail "no backup dir/copy found"
fi

# --- 3. re-apply is an exact byte-identical no-op ----------------------------
H1="$(shasum -a 256 "$SB/.openclaw/secrets/.env" | cut -d' ' -f1)"
OUT="$(run_roll --apply --local --box sandbox-op --no-standing-probe)"; RC=$?
H2="$(shasum -a 256 "$SB/.openclaw/secrets/.env" | cut -d' ' -f1)"
if [ "$RC" = "0" ] && printf '%s\n' "$OUT" | grep -q 'verdict=OK_ALREADY'; then
  pass "re-apply grades OK_ALREADY"
else
  fail "re-apply not OK_ALREADY (rc=$RC)"; echo "$OUT"
fi
if printf '%s\n' "$OUT" | grep -q 'changed=no'; then pass "re-apply changed=no"; else fail "re-apply changed!=no"; fi
if [ "$H1" = "$H2" ]; then pass "secrets/.env byte-identical across re-apply"; else fail "secrets/.env mutated by a no-op re-apply"; fi

# --- 4. incomplete identity blocked fail-closed in apply ---------------------
OUT="$(run_roll --apply --local --box sandbox-client-incomplete --include-clients)"; RC=$?
if [ "$RC" = "2" ] && printf '%s\n' "$OUT" | grep -q 'verdict=BLOCKED_IDENTITY_INCOMPLETE'; then
  pass "incomplete identity BLOCKED and counted failed in apply (exit 2)"
else
  fail "incomplete identity apply: rc=$RC"; echo "$OUT"
fi

# --- 5. --apply --local with >1 selected boxes refused up front --------------
OUT="$(run_roll --apply --local --include-clients)"; RC=$?
if [ "$RC" = "1" ] && printf '%s\n' "$OUT" | grep -q 'restrict to exactly one'; then
  pass "--apply --local multi-box selection refused before any write"
else
  fail "--apply --local multi-box: rc=$RC (expected refusal rc=1)"; echo "$OUT"
fi

# --- 6. unparseable openclaw.json: FAILED, file NOT rebuilt ------------------
cp "$SB/.openclaw/openclaw.json" "$WORK/ocjson.good"
printf '{ this is not json' > "$SB/.openclaw/openclaw.json"
HB="$(shasum -a 256 "$SB/.openclaw/openclaw.json" | cut -d' ' -f1)"
OUT="$(run_roll --apply --local --box sandbox-op --no-standing-probe)"; RC=$?
HA="$(shasum -a 256 "$SB/.openclaw/openclaw.json" | cut -d' ' -f1)"
if [ "$RC" = "2" ] && printf '%s\n' "$OUT" | grep -q 'ocjson:PODBEAN_PUBLISH_WEBHOOK_URL=UNPARSEABLE'; then
  pass "unparseable openclaw.json fails the box (no silent d={} rebuild)"
else
  fail "unparseable ocjson: rc=$RC"; echo "$OUT"
fi
if [ "$HB" = "$HA" ]; then
  pass "unparseable openclaw.json left byte-identical (never clobbered)"
else
  fail "unparseable openclaw.json was MODIFIED"
fi
cp "$WORK/ocjson.good" "$SB/.openclaw/openclaw.json"

# --- 7. secret value never on stdout or in the ledger ------------------------
ALLOUT="$(run_roll; run_roll --apply --local --box sandbox-op --no-standing-probe)"
if printf '%s\n' "$ALLOUT" | grep -qF "$TOKEN"; then
  fail "token VALUE leaked to stdout"
else
  pass "token value never on stdout"
fi
if grep -qF "$TOKEN" "$LOG" 2>/dev/null; then
  fail "token VALUE leaked into the ledger log"
else
  pass "token value never in the ledger"
fi

# --- 8. --no-restart on a changed box grades PARTIAL, never OK ---------------
rm -f "$SB/.openclaw/secrets/.env"
printf 'PODBEAN_PUBLISH_TOKEN=%s\n' "$TOKEN" > "$SB/.openclaw/secrets/.env"
printf '{}\n' > "$SB/.openclaw/openclaw.json"
OUT="$(run_roll --apply --local --box sandbox-op --no-standing-probe --no-restart)"; RC=$?
if [ "$RC" = "2" ] && printf '%s\n' "$OUT" | grep -q 'result=PARTIAL reason=changed_but_not_restarted'; then
  pass "--no-restart on a changed box grades PARTIAL (exit 2), not a false OK"
else
  fail "--no-restart changed box: rc=$RC"; echo "$OUT"
fi

echo "=== result: PASS=$PASS FAIL=$FAIL ==="
[ "$FAIL" = "0" ] || exit 1
exit 0
